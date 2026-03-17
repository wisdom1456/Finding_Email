"""Gap analysis endpoints.

Thin controller layer — all business logic lives in
legal_portal.services.analysis.gap_helpers.
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.rate_limiter import limiter
from legal_portal.api.routes._analysis_helpers import (
    _ensure_case_access,
    _fetch_latest_analysis_result,
    _GAP_ANALYSIS_INPUT_SCHEMA_VERSION,
    _get_user_ai_preferences,
    GapAnalysisRequest,
    GapResolutionRefreshRequest,
)
from legal_portal.services.analysis.gap_helpers import (
    _build_case_document_state_hash,
    _build_case_document_state_hash_lightweight,
    _build_document_registry_for_gap_context,
    _build_gap_analysis_batches,
    _build_gap_analysis_input_hash,
    _build_gap_resolution_hash,
    _build_resolution_context,
    _build_signature_evidence,
    _build_supporting_document_hash,
    _build_truncation_context,
    _collect_resolution_documents,
    _compute_resolution_document_state_hash,
    _derive_signature_detection_for_gap_doc,
    _ensure_fresh_gap_analysis_for_letter_generation,
    _fetch_all_case_document_metadata,
    _fetch_case_documents_for_gap_context,
    _fetch_gap_intake_content,
    _GAP_CONTEXT_MAX_CHARS,
    _GAP_CONTEXT_MAX_DOCS,
    _hash_jsonable,
    _parse_gap_document_summaries,
    _run_gap_analysis,
    _SMALL_GROUP_MERGE_MAP,
    _stamp_document_ids,
    GapBatch,
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
    request_start = time.monotonic()
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
            total_elapsed = time.monotonic() - request_start
            logger.info(
                f"[GAP_ENDPOINT] Complete | case_id={case_id} "
                f"total_elapsed={total_elapsed:.1f}s cache_hit=True"
            )
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
        from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService

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

        total_elapsed = time.monotonic() - request_start
        logger.info(
            f"[GAP_ENDPOINT] Complete | case_id={case_id} "
            f"total_elapsed={total_elapsed:.1f}s cache_hit=False"
        )
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
        from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService

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
            from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService

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
