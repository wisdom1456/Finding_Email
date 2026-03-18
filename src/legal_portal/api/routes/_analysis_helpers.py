"""Shared helpers, Pydantic models, and constants used across analysis route modules.

This module contains functions and classes extracted from the monolithic analysis.py
during Phase 4 refactoring. It is imported by gap_routes, letter_routes, chat_routes,
document_status_routes, and analysis_core.

Data-oriented symbols (analysis state helpers, signature detection) have been moved
to core.analysis_state and core.signature_detection. They are re-exported here for
backward compatibility.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, validator

from legal_portal.core.data_models import LetterType

# Re-export symbols moved to core modules so existing route-layer imports continue to work.
from legal_portal.core.analysis_state import *  # noqa: F401,F403
from legal_portal.core.signature_detection import *  # noqa: F401,F403

# Import __all__ from both core modules so we can build our own comprehensive __all__.
from legal_portal.core.analysis_state import __all__ as _analysis_state_all
from legal_portal.core.signature_detection import __all__ as _signature_detection_all

logger = logging.getLogger(__name__)

# Explicit __all__ so that `from _analysis_helpers import *` re-exports
# underscore-prefixed symbols (Python's default * behavior skips them).
__all__ = [
    *_analysis_state_all,
    *_signature_detection_all,
    # Metrics / SSE / quality
    "_new_generation_metrics",
    "_emit_generation_metrics",
    "_to_sse",
    "_quality_report_placeholder",
    # Case access helpers
    "_ensure_case_access",
    "_fetch_latest_analysis_result",
    # Pydantic models
    "AnalysisRequest",
    "AnalysisResponse",
    "LetterGenerationRequest",
    "LetterGenerationResponse",
    "StreamingAnalysisSaveRequest",
    "RecommendationLetterRequest",
    "RecommendationLetterResponse",
    "CalculateDemandAmountRequest",
    "CalculateDemandAmountResponse",
    "GapAnalysisRequest",
    "GapResolutionItemRequest",
    "GapResolutionRefreshRequest",
    "RetryDocumentsRequest",
    "SkipDocumentsRequest",
    "DocumentStatusResponse",
    "RecoveryActionResponse",
]


# ---------------------------------------------------------------------------
# Letter generation helpers
# ---------------------------------------------------------------------------


def _new_generation_metrics(
    *,
    analysis_id: str,
    letter_type: str,
    streaming: bool,
) -> Dict[str, Any]:
    """Create a standard metrics payload for letter generation."""
    return {
        "request_id": str(uuid.uuid4()),
        "analysis_id": analysis_id,
        "letter_type": letter_type,
        "streaming": streaming,
        "ttft_ms": None,
        "total_latency_ms": None,
        "model_calls": 0,
        "repair_attempted": False,
        "repair_applied": False,
        "strategy_used": False,
        "critic_attempted": False,
        "critic_applied": False,
        "critic_skipped_reason": None,
        "polish_applied": False,
        "polish_reverted": False,
        "polish_revert_reason": None,
        "polish_integrity_passed": None,
        "strategy_latency_ms": None,
        "critic_latency_ms": None,
        "timeout": False,
        "error_code": None,
        "lint_passed": None,
        "lint_score": None,
    }


def _emit_generation_metrics(metrics: Dict[str, Any]) -> None:
    """Emit request-level generation metrics in a single structured log line."""
    try:
        logger.info("[LETTER_METRICS] %s", json.dumps(metrics, default=str))
    except Exception:
        logger.info("[LETTER_METRICS] %s", metrics)


def _to_sse(payload: Dict[str, Any]) -> str:
    """Serialize an SSE data payload."""
    return f"data: {json.dumps(payload)}\n\n"


def _quality_report_placeholder(*, mode: str, letter_type: str) -> Dict[str, Any]:
    """Return a no-op quality report when lint is disabled/unavailable."""
    return {
        "mode": mode,
        "letter_type": letter_type,
        "lint_passed": True,
        "score": 100,
        "violations": [],
        "word_count": 0,
        "section_counts": {},
        "quality_report_v2": {
            "term_explainer_passed": True,
            "evidence_linkage_score": 1.0,
            "section_depth_score": 1.0,
            "unsupported_assertion_flags": [],
        },
    }


# ---------------------------------------------------------------------------
# Case access helpers
# ---------------------------------------------------------------------------


def _ensure_case_access(supabase_client, case_id: str, user_id: str) -> None:
    """Ensure the authenticated user owns the requested case."""
    case_response = (
        supabase_client.table("cases").select("id").eq("id", case_id).eq("user_id", user_id).execute()
    )

    if not case_response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Case not found")


def _fetch_latest_analysis_result(supabase_client, case_id: str) -> Dict[str, Any]:
    """Fetch the latest completed analysis result for a case."""
    response = (
        supabase_client.table("analysis_results")
        .select("id, result")
        .eq("case_id", case_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No completed analysis found for this case",
        )

    record = response.data[0]
    if not record.get("result"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Analysis result payload is missing",
        )

    return record


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AnalysisRequest(BaseModel):
    """Request model for starting case analysis."""

    case_id: str
    provider: Optional[str] = Field(default="openai", pattern="^(openai|anthropic)$")


class AnalysisResponse(BaseModel):
    """Response model for analysis status."""

    id: str
    case_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class LetterGenerationRequest(BaseModel):
    """Request payload for on-demand letter generation."""

    case_id: str
    letter_type: LetterType = LetterType.FINDINGS
    target_party_name: Optional[str] = None
    demand_amount: Optional[float] = None
    demand_deadline: str = "10 business days"
    specific_demands: List[str] = Field(default_factory=list)
    attorney_name: Optional[str] = None
    firm_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    client_name: Optional[str] = None
    force_generation: bool = Field(
        default=False, description="Override completeness gate for weak cases"
    )

    @validator("attorney_name", "firm_name", "contact_phone", "contact_email", "client_name", pre=True)
    def sanitize_string_fields(cls, v):
        """Convert boolean to None to prevent boolean-to-string conversion."""
        if isinstance(v, bool):
            return None
        return v


class LetterGenerationResponse(BaseModel):
    """Response payload for generated letters."""

    letter_html: str
    letter_type: LetterType = LetterType.FINDINGS
    target_party_name: Optional[str] = None
    quality_report: Optional[Dict[str, Any]] = None
    generation_metrics: Optional[Dict[str, Any]] = None


class StreamingAnalysisSaveRequest(BaseModel):
    """Request to save streaming analysis result."""

    content: str = Field(..., description="The markdown content from streaming analysis")
    stream_run_id: Optional[str] = Field(default=None, description="Stream run ID for row-level isolation")


class RecommendationLetterRequest(BaseModel):
    """Request payload for generating recommendation-based letters."""

    case_id: str
    letter_type: str = Field(
        description="Type of recommendation letter: proceed, request_documents, settlement_advisory, declination"
    )
    attorney_name: Optional[str] = None
    firm_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    client_name: Optional[str] = None


class RecommendationLetterResponse(BaseModel):
    """Response payload for generated recommendation letters."""

    letter_html: str
    letter_type: str
    recommendation_category: Optional[str] = None
    quality_report: Optional[Dict[str, Any]] = None
    generation_metrics: Optional[Dict[str, Any]] = None


class CalculateDemandAmountRequest(BaseModel):
    """Request to calculate demand amount."""

    case_id: str
    target_party_name: str


class CalculateDemandAmountResponse(BaseModel):
    """Response with calculated demand amount."""

    amount: float
    reasoning: str
    breakdown: List[Dict[str, Any]]


class GapAnalysisRequest(BaseModel):
    """Request model for on-demand gap analysis."""

    case_id: str = Field(..., description="The case ID to analyze for gaps")
    force_refresh: bool = Field(
        default=False,
        description="If true, bypass cached gap analysis and re-run AI gap analysis",
    )


class GapResolutionItemRequest(BaseModel):
    """A user-provided resolution for a specific gap."""

    gap_id: str = Field(..., description="Gap ID from the existing gap analysis")
    resolution_text: str = Field(..., description="User explanation/evidence that addresses the gap")
    mark_resolved: bool = Field(
        default=True,
        description="Whether user believes this gap is resolved",
    )
    related_document_ids: List[str] = Field(
        default_factory=list,
        description="Optional document IDs supporting this resolution",
    )

    @validator("resolution_text", pre=True)
    def sanitize_resolution_text(cls, v):
        """Convert boolean to empty string to prevent .strip() errors."""
        if isinstance(v, bool):
            return ""
        return v


class GapResolutionRefreshRequest(BaseModel):
    """Request model for applying user resolutions and refreshing gap analysis."""

    case_id: str = Field(..., description="The case ID to update")
    resolutions: List[GapResolutionItemRequest] = Field(
        default_factory=list,
        description="Per-gap user resolutions",
    )
    global_resolution_notes: Optional[str] = Field(
        default=None,
        description="General notes or context to apply across all gaps",
    )
    attached_document_ids: List[str] = Field(
        default_factory=list,
        description="Optional supporting case document IDs to prioritize",
    )
    force_refresh: bool = Field(
        default=False,
        description="If true, re-run even when resolution payload is unchanged",
    )

    @validator("global_resolution_notes", pre=True)
    def sanitize_global_notes(cls, v):
        """Convert boolean to None to prevent .strip() errors."""
        if isinstance(v, bool):
            return None
        return v


class RetryDocumentsRequest(BaseModel):
    """Request to retry failed documents."""

    document_ids: List[str] = Field(
        default=[],
        description="List of document IDs to retry, or empty to retry all failed"
    )


class SkipDocumentsRequest(BaseModel):
    """Request to skip failed documents and continue."""

    document_ids: List[str] = Field(
        default=[],
        description="List of document IDs to skip, or empty to skip all failed"
    )


class DocumentStatusResponse(BaseModel):
    """Response with document processing status."""

    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    skipped: int
    documents: Dict[str, Any] = Field(default_factory=dict)
    can_proceed: bool = False


class RecoveryActionResponse(BaseModel):
    """Response after retry/skip action."""

    success: bool
    action: str
    affected_count: int
    message: str
