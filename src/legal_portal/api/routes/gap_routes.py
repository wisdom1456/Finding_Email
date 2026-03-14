"""Gap analysis endpoints and helpers.

Provides endpoints for on-demand gap analysis, user-driven gap resolution,
and streaming gap analysis with progress updates.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.rate_limiter import limiter
from legal_portal.api.routes._analysis_helpers import (
    _apply_signature_verification_override,
    _ensure_case_access,
    _extract_signature_instrument_hints,
    _fetch_latest_analysis_result,
    _GAP_ANALYSIS_INPUT_SCHEMA_VERSION,
    _get_user_ai_preferences,
    _infer_signature_detection_from_text,
    _is_signature_inference_candidate,
    _sample_text_for_state_hash,
    GapAnalysisRequest,
    GapResolutionItemRequest,
    GapResolutionRefreshRequest,
)
from legal_portal.utils.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

router = APIRouter()

__all__ = [
    "router",
    "analyze_gaps_on_demand",
    "resolve_gaps_and_refresh",
    "analyze_gaps_streaming",
    "_ensure_fresh_gap_analysis_for_letter_generation",
    "_build_gap_resolution_hash",
    "_build_supporting_document_hash",
    "_derive_signature_detection_for_gap_doc",
    "_fetch_case_documents_for_gap_context",
    "_build_case_document_state_hash",
    "_fetch_all_case_document_metadata",
    "_build_case_document_state_hash_lightweight",
    "_build_gap_analysis_batches",
    "_run_gap_analysis",
    "_build_signature_evidence",
    "_build_document_registry_for_gap_context",
    "_build_truncation_context",
    "_hash_jsonable",
    "_build_gap_analysis_input_hash",
    "_compute_resolution_document_state_hash",
    "_parse_gap_document_summaries",
    "_stamp_document_ids",
    "_fetch_gap_intake_content",
    "_collect_resolution_documents",
    "_build_resolution_context",
    "GapBatch",
    "_SMALL_GROUP_MERGE_MAP",
    "_GAP_CONTEXT_MAX_DOCS",
    "_GAP_CONTEXT_MAX_CHARS",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GAP_CONTEXT_MAX_DOCS = 50
_GAP_CONTEXT_MAX_CHARS = 200_000


# ---------------------------------------------------------------------------
# Gap resolution hashing helpers
# ---------------------------------------------------------------------------

def _build_gap_resolution_hash(request: GapResolutionRefreshRequest) -> str:
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


def _derive_signature_detection_for_gap_doc(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Derive signature detection for a document row, with text fallback for text-like docs."""
    doc_metadata = doc.get("metadata") or {}
    if not isinstance(doc_metadata, dict):
        doc_metadata = {}

    sig = doc_metadata.get("signature_detection")
    sig = _apply_signature_verification_override(
        sig if isinstance(sig, dict) else None,
        doc_metadata,
        file_name=doc.get("file_name"),
    )
    if sig:
        return sig

    if not _is_signature_inference_candidate(doc.get("file_name"), doc.get("file_type")):
        return None

    text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
    if not text:
        return _apply_signature_verification_override(
            None,
            doc_metadata,
            file_name=doc.get("file_name"),
        )

    inferred = _infer_signature_detection_from_text(text)
    return _apply_signature_verification_override(
        inferred,
        doc_metadata,
        file_name=doc.get("file_name"),
    )


# ---------------------------------------------------------------------------
# Document fetching and state hashing
# ---------------------------------------------------------------------------

def _fetch_case_documents_for_gap_context(
    supabase,
    case_id: str,
) -> List[Dict[str, Any]]:
    """Fetch case documents used to build signature evidence and cache invalidation hashes.

    Capped at _GAP_CONTEXT_MAX_DOCS rows ordered by most recently updated to prevent
    40MB+ network payloads for large cases. Per-doc text is also capped at
    _GAP_CONTEXT_MAX_CHARS characters as a secondary guard.
    """
    try:
        _fetch_start = time.time()
        docs_resp = (
            supabase.table("documents")
            .select(
                "id, file_name, file_type, status, updated_at, extracted_text, "
                "manual_text, metadata"
            )
            .eq("case_id", case_id)
            .order("updated_at", desc=True)
            .limit(_GAP_CONTEXT_MAX_DOCS)
            .execute()
        )
        rows = docs_resp.data or []
        _elapsed = time.time() - _fetch_start
        logger.info(
            f"[GAP:FETCH] case_id={case_id} rows={len(rows)} elapsed={_elapsed:.2f}s "
            f"(limit={_GAP_CONTEXT_MAX_DOCS})"
        )

        # Warn when the case has more documents than we fetched
        if len(rows) == _GAP_CONTEXT_MAX_DOCS:
            logger.warning(
                f"[GAP:TRUNCATED] case_id={case_id} gap context capped at {_GAP_CONTEXT_MAX_DOCS} docs. "
                f"Documents beyond the cap are excluded from gap analysis, letters, and demand calc."
            )

        # Per-doc character cap as secondary guard against individual oversized documents
        for doc in rows:
            for field in ("extracted_text", "manual_text"):
                if doc.get(field) and len(doc[field]) > _GAP_CONTEXT_MAX_CHARS:
                    doc[field] = doc[field][:_GAP_CONTEXT_MAX_CHARS]

        return rows
    except Exception as doc_err:
        logger.warning(f"[GAP] Failed to load case documents for context: {doc_err}")
        return []


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


def _fetch_all_case_document_metadata(
    supabase,
    case_id: str,
) -> List[Dict[str, Any]]:
    """Fetch lightweight metadata for ALL case documents (no full text)."""
    try:
        fetch_start = time.time()
        resp = (
            supabase.table("documents")
            .select("id, file_name, file_type, status, updated_at, extracted_at, metadata")
            .eq("case_id", case_id)
            .order("updated_at", desc=True)
            .execute()
        )
        rows = resp.data or []
        logger.info(
            f"[GAP:FETCH_META] case_id={case_id} total_docs={len(rows)} "
            f"elapsed={time.time() - fetch_start:.2f}s"
        )
        return rows
    except Exception as err:
        logger.warning(f"[GAP:FETCH_META] Failed to load case document metadata: {err}")
        return []


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
# Batch analysis
# ---------------------------------------------------------------------------

@dataclass
class GapBatch:
    """A batch of documents for map-phase gap analysis."""

    batch_id: str
    batch_label: str
    document_ids: List[str] = dc_field(default_factory=list)
    document_summaries: List[Any] = dc_field(default_factory=list)
    signature_evidence: List[Dict[str, Any]] = dc_field(default_factory=list)
    registry_entries: List[Dict[str, Any]] = dc_field(default_factory=list)


# Deterministic small-group merge targets.
_SMALL_GROUP_MERGE_MAP = {
    "intake": "correspondence",
    "official_record": "controlling_instrument",
    "supporting_evidence": "financial_evidence",
    "other": "correspondence",
    "correspondence": "controlling_instrument",
    "financial_evidence": "controlling_instrument",
}


def _build_gap_analysis_batches(
    doc_summaries_list: List[Any],
    signature_evidence: List[Dict[str, Any]],
    document_registry: List[Dict[str, Any]],
) -> List["GapBatch"]:
    """Partition documents into intelligent batches for map-phase analysis."""
    # Build doc_id -> role mapping from registry
    id_to_role: Dict[str, str] = {}
    for entry in document_registry:
        doc_id = entry.get("document_id") or entry.get("id")
        role = entry.get("role_in_case") or "other"
        if doc_id:
            id_to_role[doc_id] = role

    # Build doc_id -> signature evidence mapping
    id_to_sig: Dict[str, List[Dict[str, Any]]] = {}
    for sig in signature_evidence:
        doc_id = sig.get("document_id") or sig.get("id")
        if doc_id:
            id_to_sig.setdefault(doc_id, []).append(sig)

    # Build doc_id -> registry entry mapping
    id_to_registry: Dict[str, List[Dict[str, Any]]] = {}
    for entry in document_registry:
        doc_id = entry.get("document_id") or entry.get("id")
        if doc_id:
            id_to_registry.setdefault(doc_id, []).append(entry)

    # Group summaries by role
    role_groups: Dict[str, List[Any]] = {}
    for summary in doc_summaries_list:
        doc_id = summary.document_id
        role = id_to_role.get(doc_id, "other") if doc_id else "other"
        role_groups.setdefault(role, []).append(summary)

    # Overflow splitting: groups >40 docs
    split_groups: Dict[str, List[Any]] = {}
    for role, summaries in role_groups.items():
        if len(summaries) <= 40:
            split_groups[role] = summaries
        else:
            type_sub: Dict[str, List[Any]] = {}
            for s in summaries:
                dtype = (s.document_type or "unknown").lower()
                type_sub.setdefault(dtype, []).append(s)
            for dtype, type_docs in type_sub.items():
                if len(type_docs) <= 40:
                    key = f"{role}_{dtype}"
                    split_groups[key] = type_docs
                else:
                    thirds = max(1, len(type_docs) // 3)
                    for i, chunk_start in enumerate(range(0, len(type_docs), thirds)):
                        key = f"{role}_{dtype}_part{i + 1}"
                        split_groups[key] = type_docs[chunk_start : chunk_start + thirds]

    # Small-group merge
    merge_targets: Dict[str, str] = {}
    for key in sorted(split_groups.keys()):
        if len(split_groups[key]) < 3:
            target = key
            for _ in range(3):
                next_target = _SMALL_GROUP_MERGE_MAP.get(target)
                if next_target is None or next_target == target:
                    break
                if next_target in merge_targets:
                    next_target = merge_targets[next_target]
                target = next_target
            if target not in split_groups or target == key:
                target = "controlling_instrument"
            merge_targets[key] = target

    # Apply merges
    final_groups: Dict[str, List[Any]] = {}
    for key in sorted(split_groups.keys()):
        target = merge_targets.get(key, key)
        final_groups.setdefault(target, []).extend(split_groups[key])

    # Build GapBatch objects
    batches: List[GapBatch] = []
    for idx, (label, summaries) in enumerate(sorted(final_groups.items())):
        doc_ids = [s.document_id for s in summaries if s.document_id]
        doc_id_set = set(doc_ids)
        batch = GapBatch(
            batch_id=f"batch_{idx + 1}",
            batch_label=label,
            document_ids=doc_ids,
            document_summaries=summaries,
            signature_evidence=[
                sig
                for did in doc_id_set
                for sig in id_to_sig.get(did, [])
            ],
            registry_entries=[
                entry
                for did in doc_id_set
                for entry in id_to_registry.get(did, [])
            ],
        )
        batches.append(batch)

    logger.info(
        f"[GAP:BATCH] Created {len(batches)} batches from {len(doc_summaries_list)} docs: "
        + ", ".join(f"{b.batch_label}({len(b.document_summaries)})" for b in batches)
    )

    return batches


# ---------------------------------------------------------------------------
# Gap analysis routing
# ---------------------------------------------------------------------------

async def _run_gap_analysis(
    gap_service,
    doc_summaries_list: List[Any],
    fact_matrix,
    issue_map,
    deep_analysis,
    intake_content: Optional[str] = None,
    signature_evidence: Optional[List[Dict[str, Any]]] = None,
    document_registry: Optional[List[Dict[str, Any]]] = None,
    resolution_context: Optional[str] = None,
    prior_gap_analysis=None,
    truncation_context: Optional[Dict[str, Any]] = None,
) -> Any:
    """Route gap analysis to single-pass or map-reduce based on doc count."""
    if len(doc_summaries_list) > _GAP_CONTEXT_MAX_DOCS:
        logger.info(
            f"[GAP:ROUTE] Using map-reduce path | docs={len(doc_summaries_list)} "
            f"(threshold={_GAP_CONTEXT_MAX_DOCS})"
        )
        batches = _build_gap_analysis_batches(
            doc_summaries_list,
            signature_evidence or [],
            document_registry or [],
        )
        return await gap_service.analyze_gaps_map_reduce(
            batches=batches,
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            intake_content=intake_content,
            signature_evidence=signature_evidence,
            document_registry=document_registry,
            resolution_context=resolution_context,
            prior_gap_analysis=prior_gap_analysis,
            truncation_context=truncation_context,
        )
    else:
        logger.info(
            f"[GAP:ROUTE] Using single-pass path | docs={len(doc_summaries_list)}"
        )
        return await gap_service.analyze_gaps(
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            document_summaries=doc_summaries_list,
            intake_content=intake_content,
            resolution_context=resolution_context,
            prior_gap_analysis=prior_gap_analysis,
            signature_evidence=signature_evidence,
            document_registry=document_registry,
            truncation_context=truncation_context,
        )


# ---------------------------------------------------------------------------
# Signature evidence and document registry
# ---------------------------------------------------------------------------

def _build_signature_evidence(
    document_rows: List[Dict[str, Any]],
    overflow_metadata: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Create compact signature evidence list for gap-analysis prompt grounding."""
    evidence: List[Dict[str, Any]] = []
    processed_ids: set = set()

    for doc in document_rows:
        doc_id = doc.get("id")
        if doc_id:
            processed_ids.add(doc_id)

        signature_detection = _derive_signature_detection_for_gap_doc(doc)
        if not isinstance(signature_detection, dict):
            continue

        combined_text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
        instrument_hints = _extract_signature_instrument_hints(
            file_name=doc.get("file_name"),
            extracted_text=combined_text,
        )
        signer_names = signature_detection.get("signer_names")
        indicators = signature_detection.get("indicators")

        evidence.append(
            {
                "document_id": doc_id,
                "file_name": doc.get("file_name"),
                "status": signature_detection.get("status"),
                "confidence": signature_detection.get("confidence"),
                "has_digital_signature": bool(
                    signature_detection.get("has_digital_signature")
                ),
                "signing_date": signature_detection.get("signing_date"),
                "detection_source": signature_detection.get("detection_source"),
                "signer_names": signer_names if isinstance(signer_names, list) else [],
                "indicators": indicators if isinstance(indicators, list) else [],
                "instrument_hints": instrument_hints,
            }
        )

    # Add overflow docs (metadata-only, no text available)
    if overflow_metadata:
        for meta_doc in overflow_metadata:
            meta_id = meta_doc.get("id")
            if meta_id and meta_id in processed_ids:
                continue

            signature_detection = _derive_signature_detection_for_gap_doc(meta_doc)
            if not isinstance(signature_detection, dict):
                continue

            signer_names = signature_detection.get("signer_names")
            indicators = signature_detection.get("indicators")

            evidence.append(
                {
                    "document_id": meta_id,
                    "file_name": meta_doc.get("file_name"),
                    "status": signature_detection.get("status"),
                    "confidence": "low",
                    "has_digital_signature": bool(
                        signature_detection.get("has_digital_signature")
                    ),
                    "signing_date": signature_detection.get("signing_date"),
                    "detection_source": "metadata_only",
                    "signer_names": signer_names if isinstance(signer_names, list) else [],
                    "indicators": indicators if isinstance(indicators, list) else [],
                    "instrument_hints": [],
                }
            )

    return sorted(evidence, key=lambda row: (row.get("file_name") or "").lower())


def _build_document_registry_for_gap_context(
    document_rows: List[Dict[str, Any]],
    result_payload: Dict[str, Any],
    fact_matrix: Optional[Any] = None,
    overflow_metadata: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Build authoritative document registry rows from current DB document state."""
    try:
        from legal_portal.core.data_models import (
            DocumentType,
            FactMatrix,
            FileMetadata,
            FileType,
            ProcessedDocument,
        )
        from legal_portal.services.document_registry_service import DocumentRegistryService

        summaries = _parse_gap_document_summaries(result_payload)
        processed_docs: List[ProcessedDocument] = []

        def _coerce_file_type(raw: Any, file_name: str) -> FileType:
            text = str(raw or "").lower().strip()
            if text in {"application/pdf", "pdf"} or (file_name or "").lower().endswith(".pdf"):
                return FileType.PDF
            if "wordprocessingml.document" in text or (file_name or "").lower().endswith(".docx"):
                return FileType.DOCX
            if text == "application/msword" or (file_name or "").lower().endswith(".doc"):
                return FileType.DOC
            if text in {"text/plain", "txt"} or (file_name or "").lower().endswith(".txt"):
                return FileType.TXT
            if text in {"text/csv", "csv"} or (file_name or "").lower().endswith(".csv"):
                return FileType.CSV
            if text in {"message/rfc822", "eml"} or (file_name or "").lower().endswith(".eml"):
                return FileType.EML
            if text.startswith("image/"):
                if text == "image/png":
                    return FileType.PNG
                if text in {"image/jpeg", "image/jpg"}:
                    return FileType.JPG
                return FileType.IMAGE
            return FileType.PDF

        for doc in document_rows or []:
            file_name = str(doc.get("file_name") or "").strip()
            text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
            if not file_name or not text:
                continue

            doc_type = (
                DocumentType.INTAKE_FORM
                if bool((doc.get("metadata") or {}).get("is_intake_form"))
                else DocumentType.CASE_DOCUMENT
            )
            file_type = _coerce_file_type(doc.get("file_type"), file_name)
            metadata = FileMetadata(file_name=file_name, file_type=file_type, file_size=0)
            signature_detection = _derive_signature_detection_for_gap_doc(doc)

            processed_docs.append(
                ProcessedDocument(
                    file_name=file_name,
                    content=text,
                    document_type=doc_type,
                    file_type=file_type,
                    metadata=metadata,
                    document_id=doc.get("id"),
                    extraction_quality="high",
                    extraction_method="db",
                    signature_detection=signature_detection,
                )
            )

        fact_matrix_model = None
        if isinstance(fact_matrix, FactMatrix):
            fact_matrix_model = fact_matrix
        elif isinstance(fact_matrix, dict):
            fact_matrix_model = FactMatrix(**fact_matrix)

        registry_service = DocumentRegistryService()
        registry = registry_service.build_registry(
            processed_documents=processed_docs,
            document_summaries=summaries,
            fact_matrix=fact_matrix_model,
        )

        # Add stub entries for overflow docs
        if overflow_metadata:
            registry_ids = {
                row.get("document_id") for row in registry if row.get("document_id")
            }
            for meta_doc in overflow_metadata:
                meta_id = meta_doc.get("id")
                if meta_id and meta_id in registry_ids:
                    continue
                registry.append(
                    {
                        "document_id": meta_id,
                        "document_name": meta_doc.get("file_name") or "Unknown",
                        "document_type": None,
                        "authority_level": None,
                        "execution_status": None,
                        "authority_score": None,
                        "is_key_document": None,
                        "role_in_case": None,
                        "evaluation_status": "metadata_only",
                    }
                )

        return registry
    except Exception as registry_err:
        logger.warning("[GAP] Failed to build document registry context: %s", registry_err)
        return []


# ---------------------------------------------------------------------------
# Truncation and hashing helpers
# ---------------------------------------------------------------------------

def _build_truncation_context(
    case_document_rows: List[Dict[str, Any]],
    all_doc_metadata: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Build truncation disclosure context when metadata rows exceed text-fetched rows."""
    text_ids = {doc.get("id") for doc in case_document_rows}
    overflow = [m for m in all_doc_metadata if m.get("id") not in text_ids]
    if not overflow:
        return None
    return {
        "total_documents": len(all_doc_metadata),
        "evidence_window": len(case_document_rows),
        "overflow_count": len(overflow),
        "overflow_doc_ids": [m.get("id") for m in overflow if m.get("id")],
        "overflow_doc_names": [m.get("file_name", "Unknown") for m in overflow],
    }


def _hash_jsonable(value: Any) -> str:
    """Compute deterministic hash for JSON-serializable payloads."""
    serialized = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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
# Gap analysis refresh for letter generation
# ---------------------------------------------------------------------------

async def _ensure_fresh_gap_analysis_for_letter_generation(
    *,
    supabase,
    analysis_record: Dict[str, Any],
    user_id: str,
) -> None:
    """Refresh cached gap analysis when case documents changed since it was computed."""
    result_payload = analysis_record.get("result") or {}
    multi_stage_result = result_payload.get("multi_stage_result") or {}
    existing_gap_dict = multi_stage_result.get("gap_analysis")
    if not existing_gap_dict:
        return

    analysis_id = analysis_record.get("id")
    case_id = analysis_record.get("case_id")
    if not analysis_id or not case_id:
        return

    case_document_rows = _fetch_case_documents_for_gap_context(supabase, case_id)
    all_doc_metadata = _fetch_all_case_document_metadata(supabase, case_id)
    case_document_state_hash = _build_case_document_state_hash(case_document_rows)
    all_doc_metadata_hash = _build_case_document_state_hash_lightweight(all_doc_metadata)

    # Compute overflow metadata (docs beyond text window)
    text_ids = {doc.get("id") for doc in case_document_rows}
    overflow_metadata = [m for m in all_doc_metadata if m.get("id") not in text_ids]

    gap_input_hash = _build_gap_analysis_input_hash(
        analysis_id=analysis_id,
        result_payload=result_payload,
        case_document_state_hash=case_document_state_hash,
        all_doc_metadata_hash=all_doc_metadata_hash,
    )
    existing_gap_state = result_payload.get("gap_analysis_state") or {}
    if existing_gap_state.get("input_hash") == gap_input_hash:
        return

    logger.info(
        "[LETTER] Refreshing stale gap analysis before letter generation for case %s",
        case_id,
    )
    logger.info(
        f"[GAP:SCOPE] call_site=letter_refresh total_docs={len(all_doc_metadata)} "
        f"text_window_docs={len(case_document_rows)} "
        f"overflow_docs={len(overflow_metadata)}"
    )

    try:
        from legal_portal.core.data_models import DeepAnalysis, FactMatrix, LegalIssueMap
        from legal_portal.services.gap_analysis_service import GapAnalysisService

        fact_matrix = FactMatrix(**multi_stage_result.get("fact_matrix", {}))
        issue_map = LegalIssueMap(**multi_stage_result.get("issue_map", {}))
        deep_analysis_data = multi_stage_result.get("deep_analysis", {})
        deep_analysis = DeepAnalysis(**deep_analysis_data) if deep_analysis_data else None
        if not deep_analysis:
            logger.warning(
                "[LETTER] Cannot refresh stale gap analysis for case %s: deep analysis missing",
                case_id,
            )
            return

        doc_summaries_list = _parse_gap_document_summaries(result_payload)
        intake_content = _fetch_gap_intake_content(supabase, case_id, result_payload)
        signature_evidence = _build_signature_evidence(case_document_rows, overflow_metadata=overflow_metadata)
        truncation_context = _build_truncation_context(case_document_rows, all_doc_metadata)
        document_registry = _build_document_registry_for_gap_context(
            document_rows=case_document_rows,
            result_payload=result_payload,
            fact_matrix=fact_matrix,
            overflow_metadata=overflow_metadata,
        )

        ai_preferences = await _get_user_ai_preferences(user_id, supabase)
        openai_client = OpenAIClient(user_preferences=ai_preferences)
        gap_service = GapAnalysisService(openai_client=openai_client)

        gap_result = await _run_gap_analysis(
            gap_service=gap_service,
            doc_summaries_list=doc_summaries_list,
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            intake_content=intake_content,
            signature_evidence=signature_evidence,
            document_registry=document_registry,
            truncation_context=truncation_context,
        )

        gap_dict = gap_result.model_dump(mode="json")
        multi_stage_result["gap_analysis"] = gap_dict
        multi_stage_result["document_registry"] = document_registry
        result_payload["multi_stage_result"] = multi_stage_result
        result_payload["gap_analysis_state"] = {
            "input_hash": gap_input_hash,
            "case_document_state_hash": case_document_state_hash,
            "signature_record_count": len(signature_evidence),
            "signed_document_count": sum(
                1
                for row in signature_evidence
                if (row.get("status") or "").lower() == "signed"
            ),
            "updated_at": datetime.utcnow().isoformat(),
        }

        supabase.table("analysis_results").update({"result": result_payload}).eq(
            "id", analysis_id
        ).execute()
        analysis_record["result"] = result_payload
        logger.info(
            "[LETTER] Refreshed gap analysis for case %s (score=%.1f, total_gaps=%s)",
            case_id,
            gap_result.overall_completeness_score,
            gap_result.total_gaps,
        )
    except Exception as refresh_err:
        logger.warning(
            "[LETTER] Failed to refresh stale gap analysis for case %s: %s",
            case_id,
            refresh_err,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Resolution helpers
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


def _parse_gap_document_summaries(
    result_payload: Dict[str, Any],
    metadata_rows: Optional[List[Dict[str, Any]]] = None,
):
    """Parse and validate document summaries for gap analysis."""
    from legal_portal.core.data_models import DocumentSummaryStructured

    doc_summaries_raw = result_payload.get("document_summaries", [])
    doc_summaries_array = []

    if isinstance(doc_summaries_raw, str):
        try:
            doc_summaries_array = json.loads(doc_summaries_raw)
            logger.info(
                f"[GAP] Parsed {len(doc_summaries_array)} document summaries from JSON string"
            )
        except json.JSONDecodeError as json_err:
            logger.warning(f"[GAP] Could not parse document_summaries JSON: {json_err}")
    elif isinstance(doc_summaries_raw, list):
        doc_summaries_array = doc_summaries_raw

    doc_summaries_list = []
    for doc_sum in doc_summaries_array:
        try:
            if isinstance(doc_sum, dict):
                doc_summaries_list.append(DocumentSummaryStructured(**doc_sum))
            elif hasattr(doc_sum, "model_dump"):
                doc_summaries_list.append(doc_sum)
            else:
                logger.warning(f"[GAP] Unexpected doc summary type: {type(doc_sum)}")
        except Exception as doc_err:
            logger.warning(f"[GAP] Could not convert doc summary: {doc_err}")

    # Stamp document_id from metadata rows
    if metadata_rows:
        _stamp_document_ids(doc_summaries_list, metadata_rows)

    return doc_summaries_list


def _stamp_document_ids(
    summaries: List,
    metadata_rows: List[Dict[str, Any]],
) -> None:
    """Stamp document_id on summaries by matching normalized file_name."""
    name_to_id: Dict[str, str] = {}
    for row in metadata_rows:
        normalized = (row.get("file_name") or "").lower().strip()
        if not normalized:
            continue
        if normalized in name_to_id:
            logger.warning(
                f'[GAP:ID_STAMP] Collision on normalized name "{normalized}" — '
                f"multiple docs match, using most recent (id={name_to_id[normalized]})"
            )
        else:
            name_to_id[normalized] = row["id"]

    stamped = 0
    for summary in summaries:
        if summary.document_id:
            stamped += 1
            continue
        normalized = (summary.document_name or "").lower().strip()
        doc_id = name_to_id.get(normalized)
        if doc_id:
            summary.document_id = doc_id
            stamped += 1
        else:
            logger.warning(
                f'[GAP:ID_STAMP] No metadata match for summary "{summary.document_name}" '
                f"— will use name-based fallback"
            )

    logger.info(f"[GAP:ID_STAMP] Stamped {stamped}/{len(summaries)} summaries with document_id")


def _fetch_gap_intake_content(supabase, case_id: str, result_payload: Dict[str, Any]) -> Optional[str]:
    """Get intake content from result payload, falling back to streaming summary."""
    intake = result_payload.get("intake_content")
    if intake:
        return intake
    return result_payload.get("streaming_analysis", "")[:5000]


def _collect_resolution_documents(
    supabase,
    case_id: str,
    attached_document_ids: List[str],
) -> List[Dict[str, Any]]:
    """Fetch selected documents to enrich resolution context."""
    if not attached_document_ids:
        return []

    try:
        docs_resp = (
            supabase.table("documents")
            .select("id, file_name, file_type, extracted_text, manual_text, metadata")
            .eq("case_id", case_id)
            .in_("id", attached_document_ids)
            .execute()
        )
        docs = docs_resp.data or []
    except Exception as doc_err:
        logger.warning(f"[GAP_RESOLVE] Failed to load attached docs: {doc_err}")
        return []

    condensed_docs = []
    for doc in docs:
        text = (doc.get("manual_text") or doc.get("extracted_text") or "").strip()
        if len(text) > 2200:
            text = text[:1200] + "\n... [excerpt omitted] ...\n" + text[-800:]

        sig = _derive_signature_detection_for_gap_doc(doc)
        condensed_docs.append(
            {
                "id": doc.get("id"),
                "file_name": doc.get("file_name"),
                "signature_detection": sig,
                "text_excerpt": text,
            }
        )

    return condensed_docs


def _build_resolution_context(
    existing_gap: Dict[str, Any],
    request: GapResolutionRefreshRequest,
    supporting_docs: List[Dict[str, Any]],
) -> str:
    """Create compact, structured context for selective gap re-analysis."""
    lines = []
    lines.append("USER GAP RESOLUTIONS")
    lines.append(f"Total user resolutions: {len(request.resolutions)}")
    if request.global_resolution_notes and isinstance(request.global_resolution_notes, str):
        lines.append("Global notes:")
        lines.append(request.global_resolution_notes.strip())

    gap_lookup = {}
    for gaps in (existing_gap or {}).get("gaps_by_category", {}).values():
        for gap in gaps:
            if isinstance(gap, dict) and gap.get("gap_id"):
                gap_lookup[gap["gap_id"]] = gap

    for idx, resolution in enumerate(request.resolutions, start=1):
        original_gap = gap_lookup.get(resolution.gap_id, {})
        lines.append("")
        lines.append(f"Resolution {idx}:")
        lines.append(f"- gap_id: {resolution.gap_id}")
        lines.append(f"- user_mark_resolved: {resolution.mark_resolved}")
        if original_gap:
            lines.append(f"- original_title: {original_gap.get('title', '')}")
            lines.append(f"- original_severity: {original_gap.get('severity', '')}")
            lines.append(f"- original_category: {original_gap.get('category', '')}")
        if resolution.related_document_ids:
            lines.append(f"- related_document_ids: {', '.join(resolution.related_document_ids)}")
        lines.append("- resolution_text:")
        res_text = resolution.resolution_text if isinstance(resolution.resolution_text, str) else ""
        lines.append(res_text.strip())

    if supporting_docs:
        lines.append("")
        lines.append("ATTACHED SUPPORTING DOCUMENT EXCERPTS")
        for doc in supporting_docs[:8]:
            lines.append(f"- {doc.get('file_name')} (id={doc.get('id')})")
            if doc.get("signature_detection"):
                lines.append(f"  signature_detection={doc.get('signature_detection')}")
            if doc.get("text_excerpt"):
                lines.append(f"  excerpt={doc.get('text_excerpt')}")

    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/analyze-gaps")
@limiter.limit("5/minute")
async def analyze_gaps_on_demand(
    gap_request: GapAnalysisRequest,
    request: Request,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Run gap analysis on-demand for a completed case analysis."""
    case_id = gap_request.case_id
    logger.info(f"[GAP_ENDPOINT] Starting on-demand gap analysis for case {case_id}")

    _ensure_case_access(supabase, case_id, user["id"])

    analysis_record = _fetch_latest_analysis_result(supabase, case_id)
    result_payload = analysis_record["result"]
    analysis_id = analysis_record["id"]

    multi_stage_result = result_payload.get("multi_stage_result")
    if not multi_stage_result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Gap analysis requires a completed multi-stage analysis. Please run case analysis first.",
        )

    case_document_rows = _fetch_case_documents_for_gap_context(supabase, case_id)
    all_doc_metadata = _fetch_all_case_document_metadata(supabase, case_id)
    case_document_state_hash = _build_case_document_state_hash(case_document_rows)
    all_doc_metadata_hash = _build_case_document_state_hash_lightweight(all_doc_metadata)

    text_ids = {doc.get("id") for doc in case_document_rows}
    overflow_metadata = [m for m in all_doc_metadata if m.get("id") not in text_ids]

    signature_evidence = _build_signature_evidence(case_document_rows, overflow_metadata=overflow_metadata)
    gap_input_hash = _build_gap_analysis_input_hash(
        analysis_id=analysis_id,
        result_payload=result_payload,
        case_document_state_hash=case_document_state_hash,
        all_doc_metadata_hash=all_doc_metadata_hash,
    )
    truncation_context = _build_truncation_context(case_document_rows, all_doc_metadata)

    logger.info(
        f"[GAP:SCOPE] call_site=primary total_docs={len(all_doc_metadata)} "
        f"text_window_docs={len(case_document_rows)} "
        f"overflow_docs={len(overflow_metadata)}"
    )

    existing_gap = multi_stage_result.get("gap_analysis")
    existing_gap_state = result_payload.get("gap_analysis_state") or {}
    if existing_gap and not gap_request.force_refresh:
        if existing_gap_state.get("input_hash") == gap_input_hash:
            logger.info(f"[GAP_ENDPOINT] Returning cached gap analysis for case {case_id}")
            return existing_gap
        logger.info(
            "[GAP_ENDPOINT] Cached gap analysis invalidated for case %s (state mismatch)",
            case_id,
        )

    try:
        from legal_portal.core.data_models import (
            DeepAnalysis,
            FactMatrix,
            LegalIssueMap,
        )
        from legal_portal.services.gap_analysis_service import GapAnalysisService

        ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
        openai_client = OpenAIClient(user_preferences=ai_preferences)
        gap_service = GapAnalysisService(openai_client=openai_client)

        fact_matrix = FactMatrix(**multi_stage_result.get("fact_matrix", {}))
        issue_map = LegalIssueMap(**multi_stage_result.get("issue_map", {}))
        deep_analysis_data = multi_stage_result.get("deep_analysis", {})
        deep_analysis = DeepAnalysis(**deep_analysis_data) if deep_analysis_data else None

        if not deep_analysis:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Gap analysis requires deep analysis data. Please re-run case analysis.",
            )

        doc_summaries_list = _parse_gap_document_summaries(result_payload)
        intake_content = _fetch_gap_intake_content(supabase, case_id, result_payload)
        document_registry = _build_document_registry_for_gap_context(
            document_rows=case_document_rows,
            result_payload=result_payload,
            fact_matrix=fact_matrix,
            overflow_metadata=overflow_metadata,
        )

        logger.info(f"[GAP_ENDPOINT] Running gap analysis with {len(doc_summaries_list)} documents")

        gap_result = await _run_gap_analysis(
            gap_service=gap_service,
            doc_summaries_list=doc_summaries_list,
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            intake_content=intake_content,
            signature_evidence=signature_evidence,
            document_registry=document_registry,
            truncation_context=truncation_context,
        )

        logger.info(f"[GAP_ENDPOINT] Gap analysis complete: {gap_result.total_gaps} gaps found")

        gap_dict = gap_result.model_dump(mode="json")
        multi_stage_result["gap_analysis"] = gap_dict
        multi_stage_result["document_registry"] = document_registry
        result_payload["multi_stage_result"] = multi_stage_result
        result_payload["gap_analysis_state"] = {
            "input_hash": gap_input_hash,
            "case_document_state_hash": case_document_state_hash,
            "signature_record_count": len(signature_evidence),
            "signed_document_count": sum(
                1
                for row in signature_evidence
                if (row.get("status") or "").lower() == "signed"
            ),
            "updated_at": datetime.utcnow().isoformat(),
        }

        service_supabase.table("analysis_results").update({
            "result": result_payload,
        }).eq("id", analysis_id).execute()

        logger.info(f"[GAP_ENDPOINT] Gap analysis saved for case {case_id}")
        return gap_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GAP_ENDPOINT] Gap analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gap analysis failed: {str(e)}",
        ) from e


@router.post("/analyze-gaps/resolve")
@limiter.limit("10/minute")
async def resolve_gaps_and_refresh(
    resolution_request: GapResolutionRefreshRequest,
    request: Request,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Apply user-provided gap resolutions and refresh gap analysis selectively."""
    case_id = resolution_request.case_id
    logger.info(f"[GAP_RESOLVE] Starting selective gap refresh for case {case_id}")

    _ensure_case_access(supabase, case_id, user["id"])

    analysis_record = _fetch_latest_analysis_result(supabase, case_id)
    result_payload = analysis_record["result"]
    analysis_id = analysis_record["id"]

    multi_stage_result = result_payload.get("multi_stage_result")
    if not multi_stage_result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Gap resolution requires a completed multi-stage analysis. Please run case analysis first.",
        )

    existing_gap_dict = multi_stage_result.get("gap_analysis")
    if not existing_gap_dict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No existing gap analysis found. Run gap analysis first.",
        )

    resolution_hash = _build_gap_resolution_hash(resolution_request)
    prior_resolution_state = result_payload.get("gap_resolution_state") or {}

    all_doc_ids = set(resolution_request.attached_document_ids or [])
    for item in resolution_request.resolutions:
        all_doc_ids.update(item.related_document_ids or [])
    all_doc_ids_list = sorted(all_doc_ids)

    case_document_rows = _fetch_case_documents_for_gap_context(supabase, case_id)
    all_doc_metadata = _fetch_all_case_document_metadata(supabase, case_id)
    case_document_state_hash = _build_case_document_state_hash(case_document_rows)

    text_ids = {doc.get("id") for doc in case_document_rows}
    overflow_metadata = [m for m in all_doc_metadata if m.get("id") not in text_ids]

    logger.info(
        f"[GAP:SCOPE] call_site=resolution total_docs={len(all_doc_metadata)} "
        f"text_window_docs={len(case_document_rows)} "
        f"overflow_docs={len(overflow_metadata)}"
    )

    supporting_doc_hash = _compute_resolution_document_state_hash(
        supabase=supabase,
        case_id=case_id,
        attached_document_ids=all_doc_ids_list,
    )
    if (
        not resolution_request.force_refresh
        and prior_resolution_state.get("resolution_hash") == resolution_hash
        and prior_resolution_state.get("supporting_doc_hash") == supporting_doc_hash
        and prior_resolution_state.get("case_document_state_hash") == case_document_state_hash
        and existing_gap_dict
    ):
        logger.info(f"[GAP_RESOLVE] Returning cached selective refresh for case {case_id}")
        return {
            "gap_analysis": existing_gap_dict,
            "cache_hit": True,
            "resolution_state": prior_resolution_state,
        }

    try:
        from legal_portal.core.data_models import (
            DeepAnalysis,
            FactMatrix,
            GapAnalysisResult,
            LegalIssueMap,
        )
        from legal_portal.services.gap_analysis_service import GapAnalysisService

        ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
        openai_client = OpenAIClient(user_preferences=ai_preferences)
        gap_service = GapAnalysisService(openai_client=openai_client)

        signature_evidence = _build_signature_evidence(case_document_rows, overflow_metadata=overflow_metadata)

        fact_matrix = FactMatrix(**multi_stage_result.get("fact_matrix", {}))
        issue_map = LegalIssueMap(**multi_stage_result.get("issue_map", {}))
        deep_analysis_data = multi_stage_result.get("deep_analysis", {})
        deep_analysis = DeepAnalysis(**deep_analysis_data) if deep_analysis_data else None

        if not deep_analysis:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Gap resolution requires deep analysis data. Please re-run case analysis.",
            )

        doc_summaries_list = _parse_gap_document_summaries(result_payload)
        intake_content = _fetch_gap_intake_content(supabase, case_id, result_payload)
        existing_gap_model = GapAnalysisResult(**existing_gap_dict)
        truncation_context = _build_truncation_context(case_document_rows, all_doc_metadata)
        document_registry = _build_document_registry_for_gap_context(
            document_rows=case_document_rows,
            result_payload=result_payload,
            fact_matrix=fact_matrix,
            overflow_metadata=overflow_metadata,
        )

        supporting_docs = _collect_resolution_documents(
            supabase=supabase,
            case_id=case_id,
            attached_document_ids=all_doc_ids_list,
        )
        resolution_context = _build_resolution_context(
            existing_gap=existing_gap_dict,
            request=resolution_request,
            supporting_docs=supporting_docs,
        )

        logger.info(
            f"[GAP_RESOLVE] Re-running gap stage with "
            f"resolutions={len(resolution_request.resolutions)} "
            f"supporting_docs={len(supporting_docs)}"
        )

        gap_result = await _run_gap_analysis(
            gap_service=gap_service,
            doc_summaries_list=doc_summaries_list,
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
            intake_content=intake_content,
            signature_evidence=signature_evidence,
            document_registry=document_registry,
            resolution_context=resolution_context,
            prior_gap_analysis=existing_gap_model,
            truncation_context=truncation_context,
        )

        gap_dict = gap_result.model_dump(mode="json")
        multi_stage_result["gap_analysis"] = gap_dict
        multi_stage_result["document_registry"] = document_registry
        result_payload["multi_stage_result"] = multi_stage_result

        resolution_state = {
            "resolution_hash": resolution_hash,
            "updated_at": datetime.utcnow().isoformat(),
            "applied_resolution_count": len(resolution_request.resolutions),
            "applied_gap_ids": [r.gap_id for r in resolution_request.resolutions],
            "attached_document_ids": all_doc_ids_list,
            "supporting_doc_hash": supporting_doc_hash,
            "case_document_state_hash": case_document_state_hash,
            "signature_record_count": len(signature_evidence),
            "signed_document_count": sum(
                1
                for row in signature_evidence
                if (row.get("status") or "").lower() == "signed"
            ),
            "global_resolution_notes": (resolution_request.global_resolution_notes if isinstance(resolution_request.global_resolution_notes, str) else "").strip(),
        }
        result_payload["gap_resolution_state"] = resolution_state

        service_supabase.table("analysis_results").update({
            "result": result_payload,
        }).eq("id", analysis_id).execute()

        logger.info(
            f"[GAP_RESOLVE] Selective gap refresh complete for case {case_id} | "
            f"total_gaps={gap_result.total_gaps} score={gap_result.overall_completeness_score:.1f}"
        )

        return {
            "gap_analysis": gap_dict,
            "cache_hit": False,
            "resolution_state": resolution_state,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GAP_RESOLVE] Selective gap refresh failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Selective gap refresh failed: {str(e)}",
        ) from e


@router.post("/analyze-gaps/stream")
@limiter.limit("5/minute")
async def analyze_gaps_streaming(
    gap_request: GapAnalysisRequest,
    request: Request,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Run gap analysis on-demand with streaming progress updates."""
    case_id = gap_request.case_id
    logger.info(f"[GAP_STREAM] Starting streaming gap analysis for case {case_id}")

    _ensure_case_access(supabase, case_id, user["id"])

    async def generate():
        start_time = time.time()

        try:
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'preparing', 'message': 'Loading case data...', 'elapsed': 0})}\n\n"

            analysis_record = _fetch_latest_analysis_result(supabase, case_id)
            result_payload = analysis_record["result"]
            analysis_id = analysis_record["id"]

            multi_stage_result = result_payload.get("multi_stage_result")
            if not multi_stage_result:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Gap analysis requires a completed multi-stage analysis. Please run case analysis first.'})}\n\n"
                return

            case_document_rows = _fetch_case_documents_for_gap_context(supabase, case_id)
            all_doc_metadata = _fetch_all_case_document_metadata(supabase, case_id)
            case_document_state_hash = _build_case_document_state_hash(case_document_rows)
            all_doc_metadata_hash = _build_case_document_state_hash_lightweight(all_doc_metadata)

            text_ids = {doc.get("id") for doc in case_document_rows}
            overflow_metadata = [m for m in all_doc_metadata if m.get("id") not in text_ids]

            signature_evidence = _build_signature_evidence(case_document_rows, overflow_metadata=overflow_metadata)
            gap_input_hash = _build_gap_analysis_input_hash(
                analysis_id=analysis_id,
                result_payload=result_payload,
                case_document_state_hash=case_document_state_hash,
                all_doc_metadata_hash=all_doc_metadata_hash,
            )
            truncation_context = _build_truncation_context(case_document_rows, all_doc_metadata)

            logger.info(
                f"[GAP:SCOPE] call_site=streaming total_docs={len(all_doc_metadata)} "
                f"text_window_docs={len(case_document_rows)} "
                f"overflow_docs={len(overflow_metadata)}"
            )

            existing_gap = multi_stage_result.get("gap_analysis")
            existing_gap_state = result_payload.get("gap_analysis_state") or {}
            if existing_gap and not gap_request.force_refresh:
                if existing_gap_state.get("input_hash") == gap_input_hash:
                    logger.info(f"[GAP_STREAM] Returning cached gap analysis for case {case_id}")
                    yield f"data: {json.dumps({'type': 'phase', 'phase': 'cached', 'message': 'Using cached analysis', 'elapsed': time.time() - start_time})}\n\n"
                    yield f"data: {json.dumps({'type': 'result', 'data': existing_gap})}\n\n"
                    return
                logger.info(
                    "[GAP_STREAM] Cached gap analysis invalidated for case %s (state mismatch)",
                    case_id,
                )

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'preparing', 'message': 'Converting documents...', 'elapsed': time.time() - start_time})}\n\n"

            from legal_portal.core.data_models import (
                DeepAnalysis,
                FactMatrix,
                LegalIssueMap,
            )
            from legal_portal.services.gap_analysis_service import GapAnalysisService

            ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
            openai_client = OpenAIClient(user_preferences=ai_preferences)
            gap_service = GapAnalysisService(openai_client=openai_client)

            fact_matrix = FactMatrix(**multi_stage_result.get("fact_matrix", {}))
            issue_map = LegalIssueMap(**multi_stage_result.get("issue_map", {}))
            deep_analysis_data = multi_stage_result.get("deep_analysis", {})
            deep_analysis = DeepAnalysis(**deep_analysis_data) if deep_analysis_data else None

            if not deep_analysis:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Gap analysis requires deep analysis data. Please re-run case analysis.'})}\n\n"
                return

            doc_summaries_list = _parse_gap_document_summaries(result_payload)
            intake_content = _fetch_gap_intake_content(supabase, case_id, result_payload)
            document_registry = _build_document_registry_for_gap_context(
                document_rows=case_document_rows,
                result_payload=result_payload,
                fact_matrix=fact_matrix,
                overflow_metadata=overflow_metadata,
            )

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'analyzing', 'message': 'AI is analyzing case for gaps...', 'elapsed': time.time() - start_time, 'doc_count': len(doc_summaries_list)})}\n\n"

            logger.info(f"[GAP_STREAM] Running gap analysis with {len(doc_summaries_list)} documents")

            gap_result = await _run_gap_analysis(
                gap_service=gap_service,
                doc_summaries_list=doc_summaries_list,
                fact_matrix=fact_matrix,
                issue_map=issue_map,
                deep_analysis=deep_analysis,
                intake_content=intake_content,
                signature_evidence=signature_evidence,
                document_registry=document_registry,
                truncation_context=truncation_context,
            )

            logger.info(f"[GAP_STREAM] Gap analysis complete: {gap_result.total_gaps} gaps found")

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'saving', 'message': 'Saving results...', 'elapsed': time.time() - start_time, 'gaps_found': gap_result.total_gaps})}\n\n"

            gap_dict = gap_result.model_dump(mode="json")
            multi_stage_result["gap_analysis"] = gap_dict
            multi_stage_result["document_registry"] = document_registry
            result_payload["multi_stage_result"] = multi_stage_result
            result_payload["gap_analysis_state"] = {
                "input_hash": gap_input_hash,
                "case_document_state_hash": case_document_state_hash,
                "signature_record_count": len(signature_evidence),
                "signed_document_count": sum(
                    1
                    for row in signature_evidence
                    if (row.get("status") or "").lower() == "signed"
                ),
                "updated_at": datetime.utcnow().isoformat(),
            }

            service_supabase.table("analysis_results").update({
                "result": result_payload,
            }).eq("id", analysis_id).execute()

            logger.info(f"[GAP_STREAM] Gap analysis saved for case {case_id}")

            yield f"data: {json.dumps({'type': 'result', 'data': gap_dict, 'elapsed': time.time() - start_time})}\n\n"

        except Exception as e:
            logger.error(f"[GAP_STREAM] Gap analysis failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
