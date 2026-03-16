"""Gap analysis hashing helpers.

Deterministic hash functions for gap analysis input caching, document state
tracking, and resolution dedup. Extracted from gap_helpers.py.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from legal_portal.api.routes._analysis_helpers import (
    _GAP_ANALYSIS_INPUT_SCHEMA_VERSION,
    _sample_text_for_state_hash,
)
from legal_portal.services.analysis.gap_document_context import (
    _derive_signature_detection_for_gap_doc,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core hashing
# ---------------------------------------------------------------------------

def _hash_jsonable(value: Any) -> str:
    """Compute deterministic hash for JSON-serializable payloads."""
    serialized = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Gap resolution hashing
# ---------------------------------------------------------------------------

def _build_gap_resolution_hash(request) -> str:
    """Build stable hash for resolution payload to avoid unnecessary re-runs."""
    canonical = {
        "resolutions": sorted(
            [
                {
                    "gap_id": r.gap_id,
                    "resolution_text": (r.resolution_text if isinstance(r.resolution_text, str) else "").strip(),
                    "mark_resolved": bool(r.mark_resolved),
                    "related_document_ids": sorted(r.related_document_ids or []),
                }
                for r in request.resolutions
            ],
            key=lambda x: x["gap_id"],
        ),
        "global_resolution_notes": (request.global_resolution_notes if isinstance(request.global_resolution_notes, str) else "").strip(),
        "attached_document_ids": sorted(request.attached_document_ids or []),
    }
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_supporting_document_hash(
    document_rows: List[Dict[str, Any]],
    requested_document_ids: List[str],
) -> str:
    """Build stable hash for supporting document content/state."""
    canonical_docs = []
    for doc in document_rows or []:
        text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        sig = _derive_signature_detection_for_gap_doc(doc)
        sig_status = sig.get("status") if isinstance(sig, dict) else None
        canonical_docs.append(
            {
                "id": doc.get("id"),
                "updated_at": doc.get("updated_at"),
                "text_hash": text_hash,
                "signature_status": sig_status,
            }
        )

    canonical = {
        "requested_document_ids": sorted(set(requested_document_ids or [])),
        "documents": sorted(canonical_docs, key=lambda d: (d.get("id") or "")),
    }
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Document state hashing
# ---------------------------------------------------------------------------

def _build_case_document_state_hash(document_rows: List[Dict[str, Any]]) -> str:
    """Build lightweight state hash for document set to avoid stale gap-analysis cache hits."""
    if not document_rows:
        return "no_case_documents"

    canonical_rows: List[Dict[str, Any]] = []
    for doc in document_rows:
        signature_detection = _derive_signature_detection_for_gap_doc(doc)
        signature_status = (
            signature_detection.get("status")
            if isinstance(signature_detection, dict)
            else None
        )
        sampled_text = _sample_text_for_state_hash(
            doc.get("manual_text") or doc.get("extracted_text")
        )
        text_fingerprint = hashlib.sha256(sampled_text.encode("utf-8")).hexdigest()
        canonical_rows.append(
            {
                "id": doc.get("id"),
                "updated_at": doc.get("updated_at"),
                "status": str(doc.get("status") or ""),
                "file_name": doc.get("file_name"),
                "text_fingerprint": text_fingerprint,
                "signature_status": signature_status,
            }
        )

    payload = json.dumps(
        sorted(canonical_rows, key=lambda row: (row.get("id") or "")),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_case_document_state_hash_lightweight(
    metadata_rows: List[Dict[str, Any]],
) -> str:
    """State hash for large cases using metadata-only rows.

    Trade-off (documented): This hash is sensitive to document additions,
    deletions, status changes, and re-extractions (via extracted_at timestamp),
    but NOT to manual text edits that don't update extracted_at or updated_at.
    """
    if not metadata_rows:
        return "no_case_documents"

    canonical_rows = sorted(
        (
            {
                "id": doc.get("id"),
                "updated_at": doc.get("updated_at"),
                "status": str(doc.get("status") or ""),
                "file_name": doc.get("file_name"),
                "extracted_at": doc.get("extracted_at"),
            }
            for doc in metadata_rows
        ),
        key=lambda r: r.get("id") or "",
    )
    payload = json.dumps(canonical_rows, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Gap analysis input hashing
# ---------------------------------------------------------------------------

def _build_gap_analysis_input_hash(
    analysis_id: str,
    result_payload: Dict[str, Any],
    case_document_state_hash: str,
    all_doc_metadata_hash: Optional[str] = None,
) -> str:
    """Build stable hash representing inputs that materially affect gap-analysis output."""
    document_summaries_raw = result_payload.get("document_summaries", [])
    if isinstance(document_summaries_raw, str):
        document_summaries_hash = hashlib.sha256(
            document_summaries_raw.encode("utf-8")
        ).hexdigest()
    else:
        document_summaries_hash = _hash_jsonable(document_summaries_raw)

    multi_stage = result_payload.get("multi_stage_result") or {}
    canonical = {
        "analysis_id": analysis_id,
        "analysis_logic_version": _GAP_ANALYSIS_INPUT_SCHEMA_VERSION,
        "map_reduce_version": "1",
        "fact_matrix_hash": _hash_jsonable(multi_stage.get("fact_matrix", {})),
        "issue_map_hash": _hash_jsonable(multi_stage.get("issue_map", {})),
        "deep_analysis_hash": _hash_jsonable(multi_stage.get("deep_analysis", {})),
        "document_summaries_hash": document_summaries_hash,
        "case_document_state_hash": case_document_state_hash,
    }
    if all_doc_metadata_hash:
        canonical["all_doc_metadata_hash"] = all_doc_metadata_hash
    return _hash_jsonable(canonical)


# ---------------------------------------------------------------------------
# Resolution document state hashing
# ---------------------------------------------------------------------------

def _compute_resolution_document_state_hash(
    supabase,
    case_id: str,
    attached_document_ids: List[str],
) -> str:
    """Compute a state hash for supporting docs used in selective gap refresh caching."""
    doc_ids = sorted(set(attached_document_ids or []))
    if not doc_ids:
        return "no_supporting_documents"

    try:
        docs_resp = (
            supabase.table("documents")
            .select("id, updated_at, extracted_text, manual_text, metadata")
            .eq("case_id", case_id)
            .in_("id", doc_ids)
            .execute()
        )
        rows = docs_resp.data or []
        return _build_supporting_document_hash(rows, doc_ids)
    except Exception as doc_err:
        logger.warning(f"[GAP_RESOLVE] Failed to hash supporting docs: {doc_err}")
        fallback = json.dumps({"requested_document_ids": doc_ids}, sort_keys=True)
        return f"fallback:{hashlib.sha256(fallback.encode('utf-8')).hexdigest()}"
