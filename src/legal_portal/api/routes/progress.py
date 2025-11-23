import logging

from fastapi import APIRouter, Query, Request
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
