import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status as http_status
from sse_starlette.sse import EventSourceResponse

from legal_portal.api.dependencies import get_supabase_client


router = APIRouter(prefix="/progress", tags=["progress"])
logger = logging.getLogger(__name__)


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
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


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
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Not authorized")


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
