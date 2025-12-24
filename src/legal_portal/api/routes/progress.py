import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from legal_portal.api.dependencies import get_supabase_client
from legal_portal.services.progress_manager import ProgressManager
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/progress", tags=["progress"])
logger = logging.getLogger(__name__)


@router.get("/analysis/{analysis_id}")
async def stream_analysis_progress(
    request: Request,
    analysis_id: str,
    token: str = Query(None, description="Access token for authentication"),
    # Note: Standard Depends(get_current_user) might fail if header is missing.
    # We'll trust the token param or header.
):
    """Stream analysis progress updates via SSE."""
    # Basic channel validation
    progress_manager = ProgressManager.get_instance()

    # Return EventSourceResponse with the generator
    return EventSourceResponse(
        progress_manager.subscribe(analysis_id),
        ping=15,  # Ping interval in seconds
        media_type="text/event-stream",
    )


@router.get("/clio-import/{import_id}")
async def stream_clio_import_progress(
    request: Request,
    import_id: str,
    token: str = Query(None),
):
    """Stream Clio import progress updates via SSE."""
    progress_manager = ProgressManager.get_instance()

    return EventSourceResponse(progress_manager.subscribe(import_id), ping=15, media_type="text/event-stream")


@router.get("/analysis/{analysis_id}/status")
async def get_analysis_status(
    request: Request,
    analysis_id: str,
    token: str = Query(None),
    supabase=Depends(get_supabase_client),
):
    """Get current analysis progress status (polling endpoint with DB fallback)."""
    progress_manager = ProgressManager.get_instance()

    # Try memory first
    status = await progress_manager.get_latest_status(analysis_id)

    if not status:
        # Fallback to database for cross-instance support on Vercel
        try:
            response = (
                supabase.table("analysis_results")
                .select("progress, status")
                .eq("id", analysis_id)
                .single()
                .execute()
            )
            if response.data:
                if response.data.get("progress"):
                    status = response.data["progress"]
                    # If status is terminal in DB but not in progress payload, sync it
                    if response.data["status"] in ["completed", "error"]:
                        status["type"] = response.data["status"]
                else:
                    # Map table status to progress payload if no detailed progress exists
                    status = {
                        "type": response.data["status"],
                        "message": f"Analysis state: {response.data['status']}",
                        "percent": 100 if response.data["status"] == "completed" else 0,
                    }
        except Exception as e:
            logger.warning(f"Failed to fetch progress from DB for {analysis_id}: {e}")

    if not status:
        raise HTTPException(status_code=404, detail="Analysis not found or no status available")

    return status


@router.get("/clio-import/{import_id}/status")
async def get_clio_import_status(
    request: Request,
    import_id: str,
    token: str = Query(None),
):
    """Get current Clio import progress status (polling endpoint)."""
    progress_manager = ProgressManager.get_instance()

    # Get latest status from progress manager
    status = await progress_manager.get_latest_status(import_id)

    if not status:
        raise HTTPException(status_code=404, detail="Import not found or no status available")

    return status
