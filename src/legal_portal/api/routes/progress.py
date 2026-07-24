import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status as http_status
from sse_starlette.sse import EventSourceResponse

from legal_portal.api.dependencies import get_supabase_client
from legal_portal.core import run_state


router = APIRouter(prefix="/progress", tags=["progress"])
logger = logging.getLogger(__name__)


def _build_ui_fields(j: dict, progress: dict, heartbeat_age, elapsed_in_step: float) -> dict:
    """Compute the Trustworthy-Wait UI fields. Pure w.r.t. its inputs; never raises."""
    stage = j.get("stage")
    doc_count = j.get("doc_count") or 0
    ui_state = run_state.compute_ui_state(
        job=j, has_result=False, heartbeat_age_seconds=heartbeat_age,
    )
    healthy = not (heartbeat_age is not None and heartbeat_age >= 180)
    step_index = run_state.stage_to_step(stage)

    stats = (progress or {}).get("stats") or {}
    items_done = stats.get("items_done")
    items_total = stats.get("items_total")

    eta_seconds = None
    if ui_state == "running":
        eta_seconds = run_state.estimate_eta(
            current_step=step_index, doc_count=doc_count,
            elapsed_in_step_seconds=elapsed_in_step or 0,
        )

    cancel_reason = run_state.cancel_reason(j.get("error")) if ui_state == "cancelled" else None

    return {
        "ui_state": ui_state,
        "step_index": step_index,
        "step_total": run_state.STEP_TOTAL,
        "step_label": run_state.step_label(stage),
        "items_done": items_done,
        "items_total": items_total,
        "eta_seconds": eta_seconds,
        "healthy": healthy,
        "cancel_reason": cancel_reason,
    }


def _extract_token(request: Request, token: str | None = None) -> str:
    """Extract auth token from Authorization header (preferred) or query param (legacy).

    Priority: Authorization header > query parameter.
    This allows clients to stop sending tokens in URLs while maintaining
    backwards compatibility with older clients that still do.
    """
    # 1. Try Authorization header first (secure — not logged in URLs)
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    # 2. Fall back to query parameter (legacy EventSource clients)
    if token:
        return token

    raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Token required")


async def _authenticate_from_token(token: str) -> dict:
    """Validate a Bearer token (extracted from header or query param)."""
    if not token:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Token required")
    supabase = get_supabase_client()
    try:
        response = supabase.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return {"id": response.user.id, "email": response.user.email}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None


async def _authenticate_request(request: Request, token: str | None = None) -> dict:
    """Authenticate from Authorization header (preferred) or query param (legacy)."""
    resolved_token = _extract_token(request, token)
    return await _authenticate_from_token(resolved_token)


async def _verify_analysis_ownership(supabase, analysis_id: str, user_id: str):
    """Verify the user owns the case associated with an analysis."""
    try:
        response = (
            supabase.table("analysis_results")
            .select("case_id, cases!inner(user_id)")
            .eq("id", analysis_id)
            .single()
            .execute()
        )
        if not response.data or response.data.get("cases", {}).get("user_id") != user_id:
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Not authorized")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Not authorized") from None


async def poll_database_for_progress(
    analysis_id: str,
    supabase,
    poll_interval: float = 2.0,
    max_duration: float = 290.0,  # Stay under Vercel's 300s limit
) -> AsyncGenerator[str, None]:
    """Poll database for progress updates and yield SSE events.
    
    This is designed for Vercel serverless where in-memory pub/sub doesn't work
    across function instances.
    """
    start_time = asyncio.get_event_loop().time()
    last_progress = None
    last_percent = -1

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > max_duration:
            # Approaching Vercel timeout, send final event and close gracefully
            yield json.dumps({
                "type": "timeout",
                "message": "Connection timeout - please refresh to continue monitoring",
                "percent": last_percent if last_percent >= 0 else 0,
                "timestamp": datetime.utcnow().isoformat(),
            })
            break

        try:
            # Query both status and progress columns
            response = (
                supabase.table("analysis_results")
                .select("status, progress")
                .eq("id", analysis_id)
                .single()
                .execute()
            )

            if response.data:
                db_status = response.data.get("status")
                progress_data = response.data.get("progress") or {}

                # Build current progress state
                current_progress = {
                    "type": progress_data.get("status", db_status) or "progress",
                    "message": progress_data.get("message", f"Status: {db_status}"),
                    "phase": progress_data.get("phase", db_status),
                    "percent": progress_data.get("percent", 0),
                    "timestamp": progress_data.get("timestamp", datetime.utcnow().isoformat()),
                    **{k: v for k, v in progress_data.items() if k not in ["type", "message", "phase", "percent", "timestamp", "status"]}
                }

                current_percent = current_progress.get("percent", 0)

                # Only yield if progress has changed
                if current_progress != last_progress:
                    last_progress = current_progress
                    last_percent = current_percent
                    yield json.dumps(current_progress)

                # Check for terminal states
                if db_status in ["completed", "error", "cancelled", "failed"]:
                    # Send final completion event
                    final_event = {
                        "type": db_status,
                        "message": progress_data.get("message", f"Analysis {db_status}"),
                        "phase": db_status,
                        "percent": 100 if db_status == "completed" else current_percent,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    if db_status == "error":
                        final_event["error"] = progress_data.get("error", "Unknown error")
                    yield json.dumps(final_event)
                    break

        except Exception as e:
            logger.warning(f"Error polling progress for {analysis_id}: {e}")
            # Don't break on transient errors, just skip this poll

        await asyncio.sleep(poll_interval)


@router.get("/analysis/{analysis_id}")
async def stream_analysis_progress(
    request: Request,
    analysis_id: str,
    token: str | None = Query(None, description="Access token (legacy, prefer Authorization header)"),
    supabase=Depends(get_supabase_client),
):
    """Stream analysis progress updates via SSE.

    Uses database polling instead of in-memory pub/sub to work across
    Vercel serverless function instances.
    """
    user = await _authenticate_request(request, token)
    await _verify_analysis_ownership(supabase, analysis_id, user["id"])

    # Use database polling for cross-instance compatibility on Vercel
    return EventSourceResponse(
        poll_database_for_progress(analysis_id, supabase),
        ping=15,  # Keep-alive ping interval
        media_type="text/event-stream",
    )


async def poll_database_for_clio_import_progress(
    import_id: str,
    supabase,
    poll_interval: float = 2.0,
    max_duration: float = 780.0,  # Stay under Vercel's 800s SSE limit
) -> AsyncGenerator[str, None]:
    """Poll database for Clio import progress and yield SSE events.

    On Vercel, the run-import endpoint runs in a separate function instance,
    so in-memory pub/sub doesn't work. This polls cases.import_progress instead.
    """
    start_time = asyncio.get_event_loop().time()
    last_progress = None
    last_percent = -1

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > max_duration:
            yield json.dumps({
                "type": "timeout",
                "message": "Connection timeout - please refresh to continue monitoring",
                "percent": last_percent if last_percent >= 0 else 0,
            })
            break

        try:
            response = (
                supabase.table("cases")
                .select("import_progress, status")
                .filter("import_progress->>import_id", "eq", import_id)
                .limit(1)
                .execute()
            )

            if response.data and len(response.data) > 0:
                case_data = response.data[0]
                import_progress = case_data.get("import_progress", {})
                progress_data = import_progress.get("progress", {})

                if progress_data:
                    current_progress = {
                        "type": progress_data.get("type", "progress"),
                        "message": progress_data.get("message", "Importing..."),
                        "phase": progress_data.get("phase", "import"),
                        "percent": progress_data.get("percent", 0),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    # Pass through extra fields (current_doc, sub_step, data, etc.)
                    for k, v in progress_data.items():
                        if k not in current_progress:
                            current_progress[k] = v

                    current_percent = current_progress.get("percent", 0)

                    if current_progress != last_progress:
                        last_progress = current_progress
                        last_percent = current_percent
                        yield json.dumps(current_progress)

                    # Check terminal states
                    progress_type = progress_data.get("type", "")
                    progress_status = progress_data.get("status", "")
                    if progress_type in ("completed", "error") or progress_status in ("completed", "error"):
                        break

        except Exception as e:
            logger.warning(f"Error polling import progress for {import_id}: {e}")

        await asyncio.sleep(poll_interval)


@router.get("/clio-import/{import_id}")
async def stream_clio_import_progress(
    request: Request,
    import_id: str,
    token: str | None = Query(None, description="Access token (legacy, prefer Authorization header)"),
    supabase=Depends(get_supabase_client),
):
    """Stream Clio import progress updates via SSE.

    Uses database polling for cross-instance compatibility on Vercel
    (same approach as analysis progress streaming).
    """
    await _authenticate_request(request, token)

    return EventSourceResponse(
        poll_database_for_clio_import_progress(import_id, supabase),
        ping=15,
        media_type="text/event-stream",
    )


@router.get("/analysis/{analysis_id}/status")
async def get_analysis_status(
    request: Request,
    analysis_id: str,
    token: str | None = Query(None, description="Access token (legacy, prefer Authorization header)"),
    supabase=Depends(get_supabase_client),
):
    """Get current analysis progress status (polling endpoint with DB fallback)."""
    user = await _authenticate_request(request, token)
    await _verify_analysis_ownership(supabase, analysis_id, user["id"])

    progress_manager = request.app.state.progress_manager

    # Try memory first
    status = await progress_manager.get_latest_status(analysis_id)

    if not status:
        # Fallback to database for cross-instance support on Vercel
        try:
            # Check if progress column exists by selecting status first
            response = (
                supabase.table("analysis_results").select("status").eq("id", analysis_id).single().execute()
            )
            if response.data:
                db_status = response.data["status"]
                # Map table status to progress payload
                status = {
                    "type": db_status,
                    "message": f"Analysis state: {db_status}",
                    "percent": 100 if db_status == "completed" else 0,
                }

                # Try to get progress column separately if it might exist
                try:
                    p_res = (
                        supabase.table("analysis_results")
                        .select("progress")
                        .eq("id", analysis_id)
                        .single()
                        .execute()
                    )
                    if p_res.data and p_res.data.get("progress"):
                        status.update(p_res.data["progress"])
                except Exception:
                    # Column likely doesn't exist, ignore
                    pass
        except Exception as e:
            logger.warning(f"Failed to fetch progress from DB for {analysis_id}: {e}")

    if not status:
        raise HTTPException(status_code=404, detail="Analysis not found or no status available")

    # Add server timestamp for client-side staleness detection
    status["server_time"] = datetime.utcnow().isoformat()

    return status


@router.get("/jobs/{job_id}/status")
async def get_job_status(
    request: Request,
    job_id: str,
    token: str | None = Query(None, description="Access token (legacy, prefer Authorization header)"),
    supabase=Depends(get_supabase_client),
):
    """Get analysis job status for durable worker mode (polling endpoint).

    Returns a flat, typed response — frontend should not parse raw progress JSONB.
    The stage field maps directly to the 6-stage UI.
    """
    user = await _authenticate_request(request, token)

    try:
        job_resp = (
            supabase.table("analysis_jobs")
            .select(
                "id, status, stage, progress, attempts, max_attempts, error, "
                "heartbeat_at, created_at, started_at, completed_at, analysis_id, case_id, doc_count"
            )
            .eq("id", job_id)
            .single()
            .execute()
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found") from None

    if not job_resp.data:
        raise HTTPException(status_code=404, detail="Job not found")

    j = job_resp.data

    # Verify ownership via case_id → user_id
    case_resp = supabase.table("cases").select("user_id").eq("id", j["case_id"]).single().execute()
    if not case_resp.data or case_resp.data["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Job not found")

    progress = j.get("progress") or {}

    # Compute heartbeat age for frontend stall detection
    heartbeat_age = None
    if j.get("heartbeat_at"):
        try:
            from dateutil.parser import parse as parse_dt
            hb_time = parse_dt(j["heartbeat_at"])
            now = datetime.utcnow()
            if hb_time.tzinfo:
                from datetime import timezone
                now = now.replace(tzinfo=timezone.utc)
            heartbeat_age = round((now - hb_time).total_seconds(), 1)
        except Exception:
            pass

    # Queue position info (only when pending)
    queue_position = None
    worker_busy = None
    if j["status"] == "pending":
        try:
            ahead = (
                supabase.table("analysis_jobs")
                .select("id", count="exact")
                .eq("status", "pending")
                .lt("created_at", j["created_at"])
                .execute()
            )
            queue_position = (ahead.count or 0) + 1

            running = (
                supabase.table("analysis_jobs")
                .select("id", count="exact")
                .eq("status", "running")
                .execute()
            )
            worker_busy = (running.count or 0) > 0
        except Exception:
            pass  # Non-critical — omit queue info on error

    # elapsed within the current step: prefer progress.timestamp; fall back to started_at
    elapsed_in_step = 0.0
    ts = (progress or {}).get("timestamp") or j.get("started_at")
    if ts:
        try:
            from dateutil.parser import parse as parse_dt
            from datetime import timezone
            t = parse_dt(ts)
            now2 = datetime.utcnow().replace(tzinfo=timezone.utc) if t.tzinfo else datetime.utcnow()
            elapsed_in_step = max(0.0, (now2 - t).total_seconds())
        except Exception:
            elapsed_in_step = 0.0

    ui_fields = _build_ui_fields(j, progress, heartbeat_age, elapsed_in_step)

    return {
        "job_id": j["id"],
        "analysis_id": j["analysis_id"],
        "status": j["status"],
        "stage": j["stage"],
        "message": progress.get("message", ""),
        "percent": progress.get("percent", 0),
        "attempts": j["attempts"],
        "max_attempts": j["max_attempts"],
        "error": j["error"],
        "heartbeat_age_seconds": heartbeat_age,
        **ui_fields,
        "queue_position": queue_position,
        "worker_busy": worker_busy,
        "created_at": j["created_at"],
        "started_at": j["started_at"],
        "completed_at": j["completed_at"],
        "server_time": datetime.utcnow().isoformat(),
    }


@router.get("/clio-import/{import_id}/status")
async def get_clio_import_status(
    request: Request,
    import_id: str,
    token: str | None = Query(None, description="Access token (legacy, prefer Authorization header)"),
    supabase=Depends(get_supabase_client),
):
    """Get current Clio import progress status (polling endpoint with DB fallback)."""
    await _authenticate_request(request, token)
    progress_manager = request.app.state.progress_manager

    # Try memory first
    status = await progress_manager.get_latest_status(import_id)

    if not status:
        # Fallback to database for cross-instance support on Vercel
        try:
            # Query cases table for import_progress matching import_id
            # Using contains operator since import_progress is a JSONB column
            response = (
                supabase.table("cases")
                .select("import_progress, status")
                .filter("import_progress->>import_id", "eq", import_id)
                .limit(1)
                .execute()
            )

            if response.data and len(response.data) > 0:
                case_data = response.data[0]
                import_progress = case_data.get("import_progress", {})
                if import_progress and import_progress.get("progress"):
                    status = import_progress["progress"]
                    logger.info(f"Retrieved import progress from DB for {import_id}")
                elif case_data.get("status") == "completed":
                    # Case is completed, import must have finished
                    status = {
                        "type": "completed",
                        "message": "Import completed",
                        "phase": "completed",
                        "percent": 100,
                    }
        except Exception as e:
            logger.warning(f"Failed to fetch import progress from DB for {import_id}: {e}")

    if not status:
        # Return a "pending" status instead of 404 to prevent error spam
        # The import may still be in progress on another serverless instance
        status = {
            "type": "pending",
            "message": "Import status unavailable - it may still be in progress",
            "phase": "unknown",
            "percent": 0,
        }

    # Add server timestamp for client-side staleness detection
    status["server_time"] = datetime.utcnow().isoformat()

    return status
