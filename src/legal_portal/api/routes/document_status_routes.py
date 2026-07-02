"""Document status and recovery endpoints.

Provides endpoints for monitoring document processing status and
recovering from failures (retry/skip) during analysis.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from legal_portal.api.dependencies import get_current_user, get_user_supabase_client
from legal_portal.api.routes._analysis_helpers import (
    _ensure_case_access,
    DocumentStatusResponse,
    RecoveryActionResponse,
    RetryDocumentsRequest,
    SkipDocumentsRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

__all__ = [
    "router",
    "get_document_status",
    "retry_failed_documents",
    "skip_failed_documents",
    "get_analysis_state",
]


@router.get("/{analysis_id}/documents", response_model=DocumentStatusResponse)
async def get_document_status(
    analysis_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Get detailed status of all documents in an analysis."""
    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, chunk_state"
    ).eq("id", analysis_id).single().execute()

    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    analysis = response.data
    case_id = analysis.get("case_id")

    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])

    chunk_state = analysis.get("chunk_state") or {}
    documents = chunk_state.get("documents", {})

    # Calculate summary
    statuses = [info.get("status", "pending") for info in documents.values()]

    summary = {
        "total": len(documents),
        "pending": statuses.count("pending"),
        "processing": statuses.count("processing"),
        "completed": statuses.count("completed"),
        "failed": statuses.count("failed"),
        "skipped": statuses.count("skipped"),
    }

    can_proceed = summary["pending"] == 0 and summary["processing"] == 0 and summary["failed"] == 0

    return DocumentStatusResponse(
        **summary,
        documents=documents,
        can_proceed=can_proceed
    )


@router.post("/{analysis_id}/retry", response_model=RecoveryActionResponse)
async def retry_failed_documents(
    analysis_id: str,
    request: RetryDocumentsRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Retry processing of failed documents.

    If document_ids is empty, all failed documents will be retried.
    """
    from legal_portal.services.documents.chunk_state_manager import ChunkStateManager

    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, chunk_state"
    ).eq("id", analysis_id).single().execute()

    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    analysis = response.data
    case_id = analysis.get("case_id")

    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])

    chunk_state_mgr = ChunkStateManager(supabase, analysis_id)

    # Get failed documents
    failed_docs = await chunk_state_mgr.get_failed_documents()

    if not failed_docs:
        return RecoveryActionResponse(
            success=True,
            action="retry",
            affected_count=0,
            message="No failed documents to retry"
        )

    # Determine which docs to retry
    if request.document_ids:
        doc_ids_to_retry = [d for d in request.document_ids if d in [f["id"] for f in failed_docs]]
    else:
        doc_ids_to_retry = [f["id"] for f in failed_docs]

    if not doc_ids_to_retry:
        return RecoveryActionResponse(
            success=False,
            action="retry",
            affected_count=0,
            message="No matching failed documents found"
        )

    # Reset documents to pending
    count = await chunk_state_mgr.reset_documents_for_retry(doc_ids_to_retry)

    # Update analysis status to allow re-processing
    supabase.table("analysis_results").update({
        "status": "pending"
    }).eq("id", analysis_id).execute()

    logger.info(f"[RETRY] Reset {count} documents for retry in analysis {analysis_id}")

    return RecoveryActionResponse(
        success=True,
        action="retry",
        affected_count=count,
        message=f"Reset {count} documents for retry. Re-run analysis to process them."
    )


@router.post("/{analysis_id}/skip", response_model=RecoveryActionResponse)
async def skip_failed_documents(
    analysis_id: str,
    request: SkipDocumentsRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Skip failed documents and continue with synthesis.

    If document_ids is empty, all failed documents will be skipped.
    """
    from legal_portal.services.documents.chunk_state_manager import ChunkStateManager

    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, chunk_state"
    ).eq("id", analysis_id).single().execute()

    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    analysis = response.data
    case_id = analysis.get("case_id")

    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])

    chunk_state_mgr = ChunkStateManager(supabase, analysis_id)

    # Get failed documents
    failed_docs = await chunk_state_mgr.get_failed_documents()

    if not failed_docs:
        return RecoveryActionResponse(
            success=True,
            action="skip",
            affected_count=0,
            message="No failed documents to skip"
        )

    # Determine which docs to skip
    if request.document_ids:
        doc_ids_to_skip = [d for d in request.document_ids if d in [f["id"] for f in failed_docs]]
    else:
        doc_ids_to_skip = [f["id"] for f in failed_docs]

    if not doc_ids_to_skip:
        return RecoveryActionResponse(
            success=False,
            action="skip",
            affected_count=0,
            message="No matching failed documents found"
        )

    # Mark documents as skipped
    count = await chunk_state_mgr.mark_documents_skipped(doc_ids_to_skip)

    logger.info(f"[SKIP] Skipped {count} documents in analysis {analysis_id}")

    # Check if we can now proceed to synthesis
    can_proceed = await chunk_state_mgr.can_proceed_to_synthesis()

    message = f"Skipped {count} documents."
    if can_proceed:
        message += " Analysis can now proceed to synthesis."

    return RecoveryActionResponse(
        success=True,
        action="skip",
        affected_count=count,
        message=message
    )


@router.get("/{analysis_id}/state")
async def get_analysis_state(
    analysis_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Get full analysis state for recovery/resume.

    Returns chunk_state with all document statuses, chunk plan, and summaries.
    """
    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, status, chunk_state, created_at, updated_at"
    ).eq("id", analysis_id).single().execute()

    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    analysis = response.data
    case_id = analysis.get("case_id")

    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])

    chunk_state = analysis.get("chunk_state") or {}

    # Add computed fields
    documents = chunk_state.get("documents", {})
    statuses = [info.get("status", "pending") for info in documents.values()]

    return {
        "analysis_id": analysis_id,
        "status": analysis.get("status"),
        "phase": chunk_state.get("phase", "unknown"),
        "current_chunk": chunk_state.get("current_chunk", 0),
        "total_chunks": len(chunk_state.get("chunks", [])),
        "summary": {
            "total": len(documents),
            "pending": statuses.count("pending"),
            "processing": statuses.count("processing"),
            "completed": statuses.count("completed"),
            "failed": statuses.count("failed"),
            "skipped": statuses.count("skipped"),
        },
        "can_proceed": (
            statuses.count("pending") == 0 and
            statuses.count("processing") == 0 and
            statuses.count("failed") == 0
        ),
        "chunk_state": chunk_state,
        "created_at": analysis.get("created_at"),
        "updated_at": analysis.get("updated_at"),
    }
