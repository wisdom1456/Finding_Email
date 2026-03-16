"""Gap analysis document context helpers.

Functions for fetching case documents, building signature evidence,
document registries, truncation context, and parsing document summaries
for gap analysis. Extracted from gap_helpers.py.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from legal_portal.api.routes._analysis_helpers import (
    _apply_signature_verification_override,
    _extract_signature_instrument_hints,
    _infer_signature_detection_from_text,
    _is_signature_inference_candidate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GAP_CONTEXT_MAX_DOCS = 50
_GAP_CONTEXT_MAX_CHARS = 200_000


# ---------------------------------------------------------------------------
# Signature detection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Document fetching
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


# ---------------------------------------------------------------------------
# Document registry building
# ---------------------------------------------------------------------------

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
        from legal_portal.services.documents.document_registry_service import DocumentRegistryService

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
# Truncation context
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


# ---------------------------------------------------------------------------
# Document summary parsing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Resolution context building
# ---------------------------------------------------------------------------

def _build_resolution_context(
    existing_gap: Dict[str, Any],
    request,
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
