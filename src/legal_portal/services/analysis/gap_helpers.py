"""Gap analysis helper functions extracted from gap_routes.

Pure business logic for gap analysis: hashing, batching, document registry
building, parsing, and gap freshness checks. No HTTP or route concerns.
"""

import logging
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from typing import Any, Dict, List, Optional

from legal_portal.core.analysis_state import (
    _get_user_ai_preferences,
)

# ---------------------------------------------------------------------------
# Re-exports: all symbols that were moved to sub-modules but are still
# imported by gap_routes.py, letter_routes.py, and analysis_core.py.
# ---------------------------------------------------------------------------
from legal_portal.services.analysis.gap_document_context import (  # noqa: F401
    _GAP_CONTEXT_MAX_CHARS,
    _GAP_CONTEXT_MAX_DOCS,
    _build_document_registry_for_gap_context,
    _build_resolution_context,
    _build_signature_evidence,
    _build_truncation_context,
    _collect_resolution_documents,
    _derive_signature_detection_for_gap_doc,
    _fetch_all_case_document_metadata,
    _fetch_case_documents_for_gap_context,
    _fetch_gap_intake_content,
    _parse_gap_document_summaries,
    _stamp_document_ids,
)
from legal_portal.services.analysis.gap_hashing import (  # noqa: F401
    _build_case_document_state_hash,
    _build_case_document_state_hash_lightweight,
    _build_gap_analysis_input_hash,
    _build_gap_resolution_hash,
    _build_supporting_document_hash,
    _compute_resolution_document_state_hash,
    _hash_jsonable,
)

logger = logging.getLogger(__name__)


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
        from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService

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
        from legal_portal.utils.openai_client import OpenAIClient
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
