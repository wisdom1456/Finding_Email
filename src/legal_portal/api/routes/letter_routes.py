"""Letter generation endpoints.

Provides streaming and non-streaming letter generation, recommendation
letters, and demand amount calculation endpoints.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from legal_portal.api.dependencies import get_current_user, get_user_supabase_client
from legal_portal.api.rate_limiter import limiter
from legal_portal.api.routes._analysis_helpers import (
    _emit_generation_metrics,
    _ensure_case_access,
    _fetch_latest_analysis_result,
    _get_user_ai_preferences,
    _new_generation_metrics,
    _quality_report_placeholder,
    _resolve_client_name_for_letter,
    _resolve_letter_identity_context,
    _to_sse,
    CalculateDemandAmountRequest,
    CalculateDemandAmountResponse,
    LetterGenerationRequest,
    LetterGenerationResponse,
)
from legal_portal.services.analysis.gap_helpers import _ensure_fresh_gap_analysis_for_letter_generation
from legal_portal.config.default import get_settings
from legal_portal.core.data_models import LetterType, ProcessingResult
from legal_portal.services.letters.demand_letter_service import DemandLetterService
from legal_portal.services.observability.letter_event_logger import LetterEventLogger
from legal_portal.services.shared.document_formatter import DocumentFormatterService
from legal_portal.services.shared.json_processing_service import JsonProcessingService
from legal_portal.services.letters.letter_validation_service import LetterValidationService
from legal_portal.utils.diagnostic_logger import DiagnosticLogger
from legal_portal.utils.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

router = APIRouter()

__all__ = [
    "router",
    "stream_findings_letter",
    "generate_letter",
    "generate_recommendation_letter",
    "stream_recommendation_letter",
    "stream_demand_letter",
    "calculate_demand_amount",
]


@router.get("/{analysis_id}/letter/stream")
async def stream_findings_letter(
    analysis_id: str,
    force_generation: bool = Query(default=False, description="Override completeness gate for weak cases"),
    schema_version: int = Query(default=2, ge=1, le=2),
    mode: Literal["default", "strict_quality"] = Query(default="default"),
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Stream findings letter generation with v2 SSE events and legacy compatibility."""
    try:
        settings = get_settings()
        effective_schema_version = 2 if (schema_version == 2 and settings.letter_stream_schema_v2) else 1

        response = supabase.table("analysis_results").select("*").eq("id", analysis_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Analysis not found")

        analysis_data = response.data[0]
        await _ensure_fresh_gap_analysis_for_letter_generation(
            supabase=supabase,
            analysis_record=analysis_data,
            user_id=user["id"],
        )

        result_payload = analysis_data.get("result")
        if not result_payload:
            raise HTTPException(status_code=400, detail="Analysis result not yet available")

        processing_result = ProcessingResult(**result_payload)
        if not processing_result.multi_stage_result:
            raise HTTPException(status_code=400, detail="Multi-stage analysis results missing")

        msr = processing_result.multi_stage_result
        gap_analysis_data = msr.get("gap_analysis")
        if gap_analysis_data:
            from legal_portal.core.data_models import GapAnalysisResult

            gap_analysis = GapAnalysisResult(**gap_analysis_data)
            if gap_analysis.overall_completeness_score < 40:
                if not force_generation:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": "documentation_insufficient",
                            "message": (
                                "Case documentation is insufficient for letter generation. Please "
                                "provide the missing documents identified in Gap Analysis before "
                                "generating a letter."
                            ),
                            "completeness_score": gap_analysis.overall_completeness_score,
                            "critical_gaps": gap_analysis.critical_count,
                            "recommendation": (
                                "Review the Gap Analysis tab to identify which documents are needed."
                            ),
                            "allow_override": True,
                        },
                    )
                logger.warning(
                    f"OVERRIDE: force_generation used for streaming letter with low completeness score "
                    f"({gap_analysis.overall_completeness_score}%) - analysis_id={analysis_id}, "
                    f"critical_gaps={gap_analysis.critical_count}"
                )
            elif gap_analysis.overall_completeness_score < 60:
                logger.warning(
                    f"Streaming letter with moderate completeness score: {gap_analysis.overall_completeness_score}% "
                    f"(critical_gaps={gap_analysis.critical_count}, high_gaps={gap_analysis.high_count}) "
                    f"- analysis_id={analysis_id}"
                )

        artifacts = processing_result.artifacts or {}
        resolved_identity = _resolve_letter_identity_context(
            supabase=supabase,
            case_id=analysis_data.get("case_id"),
            artifacts=artifacts,
        )
        ai_preferences = await _get_user_ai_preferences(user["id"], supabase)

        def _event_payload(event_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
            """Build schema-v1 or schema-v2 payload for the current stream request."""
            if effective_schema_version == 1:
                if event_name == "token":
                    return {"token": kwargs.get("token", "")}
                if event_name == "done":
                    return {"done": True}
                if event_name == "error":
                    return {"error": kwargs.get("error", "Stream failed")}
                return None

            payload: Dict[str, Any] = {
                "schema_version": 2,
                "event": event_name,
                "type": event_name,
            }
            payload.update(kwargs)
            if event_name == "done":
                payload["done"] = True
            return payload

        event_logger = LetterEventLogger(supabase)

        async def generate():
            request_started = time.monotonic()
            metrics = _new_generation_metrics(
                analysis_id=analysis_id,
                letter_type="findings",
                streaming=True,
            )
            # One row per generation request — fail-safe (logger never
            # raises into the stream).
            event_id = event_logger.begin(
                user_id=user["id"],
                case_id=analysis_data.get("case_id"),
                analysis_id=analysis_id,
                letter_type="findings",
            )
            quality_report = _quality_report_placeholder(mode=mode, letter_type="findings")
            recoverable_timeout = False
            draft_markdown = ""

            def _remaining_seconds(internal_deadline: float) -> float:
                return internal_deadline - time.monotonic()

            def _emit(event_name: str, **kwargs: Any) -> Optional[str]:
                payload = _event_payload(event_name, **kwargs)
                if payload is None:
                    return None
                return _to_sse(payload)

            try:
                internal_budget = max(30, int(settings.letter_internal_budget_seconds))
                context_budget = max(1, int(settings.letter_context_budget_seconds))
                draft_budget = max(5, int(settings.letter_draft_budget_seconds))
                lint_budget = max(1, int(settings.letter_lint_budget_seconds))
                repair_budget = max(1, int(settings.letter_repair_budget_seconds))
                finalize_budget = max(1, int(settings.letter_finalize_budget_seconds))
                strategy_budget = max(1, int(settings.letter_strategy_budget_seconds))
                critic_budget = max(1, int(settings.letter_critic_budget_seconds))
                heartbeat_interval = max(1, int(settings.letter_stream_heartbeat_seconds))
                internal_deadline = request_started + internal_budget

                phase_msg = _emit("phase", phase="strategy", message="Preparing letter strategy...", percent=3)
                if phase_msg:
                    yield phase_msg
                phase_msg = _emit("phase", phase="context_build", message="Building context", percent=8)
                if phase_msg:
                    yield phase_msg

                context_started = time.monotonic()
                from legal_portal.core.data_models import (
                    DeepAnalysis,
                    FactMatrix,
                    GapAnalysisResult,
                    LetterStructure,
                )

                jurisdiction = artifacts.get("jurisdiction", "Florida")
                fact_matrix = FactMatrix(**msr["fact_matrix"])
                deep_analysis = DeepAnalysis(**msr["deep_analysis"])
                letter_structure = LetterStructure(**msr["letter_structure"])
                stream_gap_analysis = (
                    GapAnalysisResult(**msr["gap_analysis"]) if msr.get("gap_analysis") else None
                )
                client_name = _resolve_client_name_for_letter(
                    resolved_identity=resolved_identity,
                    artifacts=artifacts,
                    fact_matrix=fact_matrix,
                )

                document_summaries_for_context: List[Dict[str, Any]] = []
                if processing_result.document_summaries:
                    try:
                        parsed_summaries = json.loads(processing_result.document_summaries)
                        if isinstance(parsed_summaries, list):
                            document_summaries_for_context = [
                                item for item in parsed_summaries if isinstance(item, dict)
                            ]
                    except Exception as parse_err:
                        logger.warning(
                            f"[LETTER] Failed to parse document_summaries for stream context: {parse_err}"
                        )

                if (time.monotonic() - context_started) > context_budget:
                    metrics["timeout"] = True
                    metrics["error_code"] = "context_budget_exceeded"
                    raise TimeoutError("Context-build phase exceeded budget.")

                openai_client = OpenAIClient(user_preferences=ai_preferences)
                json_service = JsonProcessingService(client=openai_client, config={})
                normalize_markdown = getattr(json_service, "normalize_client_letter_markdown", None)

                def _normalize_markdown(text: str, letter_kind: str) -> str:
                    if callable(normalize_markdown):
                        return normalize_markdown(
                            text,
                            letter_type=letter_kind,
                            attorney_name=resolved_identity.get("attorney_name"),
                            firm_name=resolved_identity.get("firm_name"),
                        )
                    return text

                strategy_object: Optional[Dict[str, Any]] = None
                if settings.letter_strategy_enabled:
                    remaining_for_strategy = _remaining_seconds(internal_deadline)
                    reserve_for_downstream = draft_budget + lint_budget + finalize_budget
                    if remaining_for_strategy > reserve_for_downstream:
                        strategy_timeout = int(
                            min(strategy_budget, max(1, remaining_for_strategy - reserve_for_downstream))
                        )
                        strategy_started = time.monotonic()
                        try:
                            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                            strategy_object = await json_service.build_findings_strategy(
                                fact_matrix=fact_matrix,
                                deep_analysis=deep_analysis,
                                gap_analysis=stream_gap_analysis,
                                timeout_seconds=strategy_timeout,
                                allow_model=True,
                                model="gpt-5.4-mini",
                            )
                            metrics["strategy_used"] = bool(strategy_object)
                        except Exception as strategy_err:
                            logger.warning(f"[LETTER] Strategy step failed for stream: {strategy_err}")
                        finally:
                            metrics["strategy_latency_ms"] = int(
                                (time.monotonic() - strategy_started) * 1000
                            )

                phase_msg = _emit("phase", phase="draft_generation", message="Generating draft")
                if phase_msg:
                    yield phase_msg

                metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1

                stream_generator = json_service.stream_findings_letter_adaptive(
                    intake_content=processing_result.intake_content or "",
                    fact_matrix=fact_matrix,
                    legal_analysis=deep_analysis,
                    structure_guidance=letter_structure,
                    verified_statutes=msr.get("verified_statutes", []),
                    attorney_name=resolved_identity.get("attorney_name"),
                    firm_name=resolved_identity.get("firm_name"),
                    confirmed_qa_pairs=artifacts.get("confirmed_qa_pairs", []),
                    contact_phone=resolved_identity.get("contact_phone"),
                    contact_email=resolved_identity.get("contact_email"),
                    quality_context=artifacts.get("quality_context", ""),
                    clio_matter_context=artifacts.get("clio_matter_context", ""),
                    jurisdiction=jurisdiction,
                    original_documents=msr.get("original_documents"),
                    document_summaries_for_context=document_summaries_for_context,
                    document_registry=msr.get("document_registry"),
                    strategy_object=strategy_object,
                    gap_analysis=stream_gap_analysis,
                    firm_address=resolved_identity.get("firm_address"),
                    bar_number=resolved_identity.get("bar_number"),
                    signature_override=resolved_identity.get("email_signature"),
                    client_name=resolved_identity.get("client_name"),
                )

                token_queue: asyncio.Queue = asyncio.Queue()

                async def _collect_tokens() -> None:
                    try:
                        async for token in stream_generator:
                            await token_queue.put(("token", token))
                    except Exception as stream_err:
                        await token_queue.put(("error", stream_err))
                    finally:
                        await token_queue.put(("done", None))

                collector_task = asyncio.create_task(_collect_tokens())
                draft_started = time.monotonic()
                reserved_for_after_draft = lint_budget + finalize_budget
                draft_deadline = min(
                    draft_started + draft_budget,
                    internal_deadline - reserved_for_after_draft,
                )
                _draft_token_count = 0
                _last_wc_emit_token = 0

                try:
                    while True:
                        if time.monotonic() > draft_deadline:
                            metrics["timeout"] = True
                            metrics["error_code"] = "draft_budget_exceeded"
                            break

                        try:
                            msg_type, msg_data = await asyncio.wait_for(
                                token_queue.get(),
                                timeout=heartbeat_interval,
                            )
                        except asyncio.TimeoutError:
                            heartbeat_msg = _emit(
                                "heartbeat",
                                phase="draft_generation",
                                elapsed_ms=int((time.monotonic() - request_started) * 1000),
                            )
                            if heartbeat_msg:
                                yield heartbeat_msg
                            continue

                        if msg_type == "token":
                            token = str(msg_data or "")
                            if not token:
                                continue
                            draft_markdown += token
                            _draft_token_count += 1
                            if metrics["ttft_ms"] is None:
                                metrics["ttft_ms"] = int((time.monotonic() - request_started) * 1000)
                            token_msg = _emit("token", token=token)
                            if token_msg:
                                yield token_msg
                            if _draft_token_count - _last_wc_emit_token >= 200:
                                _last_wc_emit_token = _draft_token_count
                                _wc = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
                                _pct = min(88, 10 + _wc * 78 // 1000)
                                wc_msg = _emit("phase", phase="draft_generation", message=f"Drafting letter... ({_wc:,} words)", percent=_pct)
                                if wc_msg:
                                    yield wc_msg
                            continue

                        if msg_type == "error":
                            if isinstance(msg_data, Exception):
                                raise msg_data
                            raise RuntimeError(str(msg_data))

                        if msg_type == "done":
                            break
                finally:
                    if not collector_task.done():
                        collector_task.cancel()
                        try:
                            await collector_task
                        except asyncio.CancelledError:
                            pass

                draft_word_count = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
                if metrics["timeout"] and draft_word_count >= 80:
                    recoverable_timeout = True
                    timeout_msg = _emit(
                        "error",
                        error=(
                            "Draft generation exceeded time budget; finalized the best available draft."
                        ),
                        code=metrics.get("error_code"),
                        recoverable=True,
                    )
                    if timeout_msg:
                        yield timeout_msg

                if not draft_markdown.strip():
                    raise TimeoutError("Draft generation ended before any content was produced.")

                draft_markdown = _normalize_markdown(draft_markdown, "findings")

                phase_msg = _emit("phase", phase="lint_validation", message="Validating quality")
                if phase_msg:
                    yield phase_msg

                validator = LetterValidationService()
                if settings.letter_quality_lint_enabled and _remaining_seconds(internal_deadline) > finalize_budget:
                    lint_started = time.monotonic()
                    quality_report = validator.lint_client_letter(
                        draft_markdown,
                        mode=mode,
                        letter_type="findings",
                    )
                    if (time.monotonic() - lint_started) > lint_budget:
                        logger.warning("[LETTER] Lint phase exceeded budget but completed.")

                final_markdown = draft_markdown
                critic_feedback: Dict[str, Any] = {"failed_sections": []}
                if (
                    settings.letter_quality_critic_enabled
                    and not quality_report.get("lint_passed", True)
                    and settings.letter_quality_lint_enabled
                ):
                    remaining_before_critic = _remaining_seconds(internal_deadline)
                    if remaining_before_critic >= (critic_budget + finalize_budget):
                        metrics["critic_attempted"] = True
                        critic_started = time.monotonic()
                        try:
                            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                            critic_feedback = await json_service.run_quality_critic(
                                draft_markdown=draft_markdown,
                                letter_type="findings",
                                lint_violations=quality_report.get("violations", []),
                                quality_report_v2=quality_report.get("quality_report_v2"),
                                model="gpt-5.4-mini",
                                timeout_seconds=critic_budget,
                            )
                        except Exception as critic_err:
                            logger.warning(f"[LETTER] Critic step failed: {critic_err}")
                            metrics["critic_skipped_reason"] = f"critic_error:{type(critic_err).__name__}"
                            critic_feedback = {"failed_sections": []}
                        finally:
                            metrics["critic_latency_ms"] = int((time.monotonic() - critic_started) * 1000)
                    else:
                        metrics["critic_skipped_reason"] = "insufficient_budget"

                if (
                    settings.letter_conditional_repair_enabled
                    and not quality_report.get("lint_passed", True)
                    and settings.letter_quality_lint_enabled
                ):
                    remaining_after_lint = _remaining_seconds(internal_deadline)
                    if remaining_after_lint >= (repair_budget + finalize_budget):
                        phase_msg = _emit("phase", phase="repair", message="Repairing quality issues")
                        if phase_msg:
                            yield phase_msg
                        metrics["repair_attempted"] = True
                        metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                        repaired = await json_service.repair_letter_constraints(
                            draft_markdown,
                            quality_report.get("violations", []),
                            mode=mode,
                            model="gpt-5.4-mini",
                            critic_feedback=critic_feedback,
                        )
                        repaired = _normalize_markdown(repaired, "findings")
                        post_repair_report = validator.lint_client_letter(
                            repaired,
                            mode=mode,
                            letter_type="findings",
                        )
                        quality_report = {
                            **post_repair_report,
                            "pre_repair": quality_report,
                            "post_repair": post_repair_report,
                            "critic_feedback": critic_feedback,
                        }
                        if repaired.strip() and repaired.strip() != draft_markdown.strip():
                            final_markdown = repaired
                            metrics["repair_applied"] = True
                            if critic_feedback.get("failed_sections"):
                                metrics["critic_applied"] = True
                    else:
                        quality_report = {
                            **quality_report,
                            "repair_skipped": "insufficient_budget",
                            "critic_feedback": critic_feedback,
                        }

                # Polish pass: second AI call for prose formatting consistency
                if getattr(settings, "letter_polish_enabled", True):
                    polish_msg = _emit("phase", phase="polishing", message="Polishing letter...")
                    if polish_msg:
                        yield polish_msg
                    try:
                        from legal_portal.utils.letter_polish import polish_letter_async

                        pre_polish_markdown = final_markdown
                        _polish_timeout = getattr(settings, "letter_polish_timeout_seconds", 55)
                        polish_result = await polish_letter_async(
                            openai_client,
                            pre_polish_markdown,
                            timeout_seconds=float(_polish_timeout),
                        )
                        if polish_result.get("success") and polish_result.get("polished_letter"):
                            polished_candidate = polish_result["polished_letter"]
                            integrity_report = {"passed": True, "reason": "unsupported"}
                            if hasattr(validator, "check_polish_fact_integrity"):
                                integrity_report = validator.check_polish_fact_integrity(
                                    pre_polish_markdown,
                                    polished_candidate,
                                    tracked_entities=[
                                        client_name,
                                        resolved_identity.get("attorney_name") or "",
                                        resolved_identity.get("firm_name") or "",
                                    ],
                                )
                            metrics["polish_integrity_passed"] = bool(integrity_report.get("passed", True))

                            if integrity_report.get("passed", True):
                                final_markdown = polished_candidate
                                metrics["polish_applied"] = True
                            else:
                                metrics["polish_applied"] = False
                                metrics["polish_reverted"] = True
                                metrics["polish_revert_reason"] = (
                                    f"fact_integrity:{integrity_report.get('reason', 'unknown')}"
                                )
                                logger.warning(
                                    f"[LETTER] Polish reverted due to fact integrity drift: {integrity_report}"
                                )
                    except Exception as polish_err:
                        logger.warning(f"[LETTER] Polish pass failed, using raw draft: {polish_err}")
                        metrics["polish_applied"] = False
                else:
                    logger.info("[LETTER] Polish pass disabled by configuration")

                phase_msg = _emit("phase", phase="finalizing", message="Finalizing letter")
                if phase_msg:
                    yield phase_msg

                final_markdown = _normalize_markdown(final_markdown, "findings")
                final_html = json_service._convert_markdown_to_html(final_markdown)
                final_html = DocumentFormatterService.format_findings_letter(
                    letter_html=final_html,
                    client_name=client_name,
                )
                metrics["lint_passed"] = quality_report.get("lint_passed")
                metrics["lint_score"] = quality_report.get("score")
                metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)

                try:
                    persisted_result = analysis_data.get("result") or {}
                    generated_letters = persisted_result.setdefault("generated_letters", {})
                    generated_letters["findings"] = final_html
                    generated_letters["findings_meta"] = {
                        "quality_report": quality_report,
                        "quality_report_v2": quality_report.get("quality_report_v2"),
                        "generation_metrics": metrics,
                        "strategy_object": strategy_object,
                    }
                    supabase.table("analysis_results").update({"result": persisted_result}).eq(
                        "id", analysis_id
                    ).execute()
                except Exception as persist_err:
                    logger.warning(f"[LETTER] Persisting streamed findings failed: {persist_err}")

                event_logger.complete(
                    event_id,
                    qa_summary=quality_report.get("quality_report_v2"),
                    duration_ms=metrics.get("total_latency_ms"),
                )

                quality_msg = _emit(
                    "quality",
                    quality_report=quality_report,
                    generation_metrics=metrics,
                )
                if quality_msg:
                    yield quality_msg

                final_msg = _emit(
                    "final",
                    content={
                        "format": "html",
                        "html": final_html,
                        "markdown": final_markdown,
                    },
                    quality_report=quality_report,
                    generation_metrics=metrics,
                )
                if final_msg:
                    yield final_msg

                done_msg = _emit("done")
                if done_msg:
                    yield done_msg
                _emit_generation_metrics(metrics)

            except Exception as stream_err:
                if isinstance(stream_err, TimeoutError):
                    metrics["timeout"] = True
                    if not metrics.get("error_code"):
                        metrics["error_code"] = "timeout"
                elif not metrics.get("error_code"):
                    metrics["error_code"] = type(stream_err).__name__

                metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)
                _emit_generation_metrics(metrics)

                event_logger.fail(
                    event_id,
                    error=f"{metrics.get('error_code')}: {stream_err}",
                    duration_ms=metrics.get("total_latency_ms"),
                )

                error_msg = _emit(
                    "error",
                    error=str(stream_err),
                    code=metrics.get("error_code"),
                    recoverable=recoverable_timeout,
                )
                if error_msg:
                    yield error_msg

                done_msg = _emit("done")
                if done_msg:
                    yield done_msg

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in stream_findings_letter: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/generate-letter", response_model=LetterGenerationResponse)
@limiter.limit("10/minute")  # Rate limit letter generation
async def generate_letter(
    letter_request: LetterGenerationRequest,
    request: Request,  # Required for rate limiter (must be named 'request')
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Generate findings or demand letters on-demand."""
    settings = get_settings()
    started_at = time.monotonic()

    _ensure_case_access(supabase, letter_request.case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, letter_request.case_id)
    metrics = _new_generation_metrics(
        analysis_id=analysis_record["id"],
        letter_type=letter_request.letter_type.value,
        streaming=False,
    )
    internal_deadline = started_at + max(30, int(settings.letter_internal_budget_seconds))
    strategy_budget = max(1, int(settings.letter_strategy_budget_seconds))
    critic_budget = max(1, int(settings.letter_critic_budget_seconds))
    repair_budget = max(1, int(settings.letter_repair_budget_seconds))
    finalize_budget = max(1, int(settings.letter_finalize_budget_seconds))

    def _remaining_seconds() -> float:
        return internal_deadline - time.monotonic()

    try:
        await _ensure_fresh_gap_analysis_for_letter_generation(
            supabase=supabase,
            analysis_record=analysis_record,
            user_id=user["id"],
        )

        result_payload = analysis_record["result"]
        processing_result = ProcessingResult(**result_payload)

        if not processing_result.multi_stage_result:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="On-demand letters require the latest analysis. Please re-run the case analysis.",
            )

        artifacts = processing_result.artifacts or {}
        resolved_identity = _resolve_letter_identity_context(
            supabase=supabase,
            case_id=letter_request.case_id,
            artifacts=artifacts,
            overrides={
                "attorney_name": letter_request.attorney_name,
                "firm_name": letter_request.firm_name,
                "contact_phone": letter_request.contact_phone,
                "contact_email": letter_request.contact_email,
                "client_name": letter_request.client_name,
            },
        )
        ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
        openai_client = OpenAIClient(user_preferences=ai_preferences)
        attorney_info = {
            "name": resolved_identity.get("attorney_name"),
            "firm": resolved_identity.get("firm_name"),
            "firm_address": resolved_identity.get("firm_address"),
            "phone": resolved_identity.get("contact_phone"),
            "email": resolved_identity.get("contact_email"),
            "bar_number": resolved_identity.get("bar_number"),
            "signature_block": resolved_identity.get("email_signature"),
        }

        msr = processing_result.multi_stage_result
        letter_html: str
        target_party_name: Optional[str] = None
        client_name = _resolve_client_name_for_letter(
            resolved_identity=resolved_identity,
            artifacts=artifacts,
            fact_matrix=msr.get("fact_matrix"),
        )
        strategy_object: Optional[Dict[str, Any]] = None
        draft_markdown_for_repair: Optional[str] = None
        quality_report = _quality_report_placeholder(
            mode="default",
            letter_type=letter_request.letter_type.value,
        )

        jurisdiction = artifacts.get("jurisdiction", "Florida")
        logger.info(f"Generating {letter_request.letter_type} letter for {jurisdiction}")

        diag_logger = None
        if DiagnosticLogger.get_enabled():
            diag_logger = DiagnosticLogger(session_id=letter_request.case_id)

        gap_analysis = None
        fact_matrix = None
        verified_statutes: List[Dict[str, Any]] = []
        json_service = JsonProcessingService(client=openai_client, config={})
        normalize_markdown = getattr(json_service, "normalize_client_letter_markdown", None)

        def _normalize_markdown(text: str, letter_kind: str) -> str:
            if callable(normalize_markdown):
                return normalize_markdown(
                    text,
                    letter_type=letter_kind,
                    attorney_name=attorney_info.get("name"),
                    firm_name=attorney_info.get("firm"),
                )
            return text

        if letter_request.letter_type == LetterType.FINDINGS:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=(
                    "The synchronous findings letter endpoint has been retired. "
                    "Use the streaming endpoint: GET /{analysis_id}/letter/stream"
                ),
            )
        else:
            if not letter_request.target_party_name:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="target_party_name is required for demand letters",
                )
            client_name = _resolve_client_name_for_letter(
                resolved_identity=resolved_identity,
                artifacts=artifacts,
                fact_matrix=msr.get("fact_matrix"),
            )

            document_summaries = []
            if processing_result.document_summaries:
                try:
                    document_summaries = json.loads(processing_result.document_summaries)
                except Exception as parse_err:
                    logger.warning(f"Failed to parse document_summaries: {parse_err}")

            demand_service = DemandLetterService(openai_client)
            from legal_portal.core.data_models import DeepAnalysis, FactMatrix, GapAnalysisResult

            demand_fact_matrix = FactMatrix(**msr["fact_matrix"])
            demand_deep_analysis = DeepAnalysis(**msr["deep_analysis"])
            if not gap_analysis and msr.get("gap_analysis"):
                try:
                    gap_analysis = GapAnalysisResult(**msr["gap_analysis"])
                except Exception:
                    gap_analysis = None

            if settings.letter_strategy_enabled and _remaining_seconds() >= (strategy_budget + finalize_budget):
                strategy_started = time.monotonic()
                try:
                    metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                    strategy_object = await demand_service.build_demand_strategy(
                        fact_matrix=demand_fact_matrix,
                        deep_analysis=demand_deep_analysis,
                        target_party_name=letter_request.target_party_name,
                        demand_amount=letter_request.demand_amount,
                        demand_deadline=letter_request.demand_deadline,
                        specific_demands=letter_request.specific_demands,
                        client_name=client_name,
                        gap_analysis=gap_analysis,
                        timeout_seconds=strategy_budget,
                        allow_model=True,
                        model="gpt-5.4-mini",
                    )
                    metrics["strategy_used"] = bool(strategy_object)
                except Exception as strategy_err:
                    logger.warning(f"[LETTER] Demand strategy build failed: {strategy_err}")
                finally:
                    metrics["strategy_latency_ms"] = int((time.monotonic() - strategy_started) * 1000)

            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
            letter_html, draft_markdown_for_repair = await demand_service.generate_demand_letter_with_markdown(
                fact_matrix_dict=msr["fact_matrix"],
                deep_analysis_dict=msr["deep_analysis"],
                target_party_name=letter_request.target_party_name,
                demand_amount=letter_request.demand_amount,
                demand_deadline=letter_request.demand_deadline,
                specific_demands=letter_request.specific_demands,
                attorney_info=attorney_info,
                client_name=client_name,
                document_summaries=document_summaries,
                jurisdiction=jurisdiction,
                strategy_object=strategy_object,
            )
            target_party_name = letter_request.target_party_name
            # Polish pass: second AI call for prose formatting consistency
            if getattr(settings, "letter_polish_enabled", True):
                try:
                    from legal_portal.utils.letter_polish import polish_letter_async

                    pre_polish_markdown = draft_markdown_for_repair
                    _polish_timeout = getattr(settings, "letter_polish_timeout_seconds", 55)
                    polish_result = await polish_letter_async(
                        openai_client,
                        pre_polish_markdown,
                        timeout_seconds=float(_polish_timeout),
                    )
                    if polish_result.get("success") and polish_result.get("polished_letter"):
                        polished_candidate = polish_result["polished_letter"]
                        integrity_report = {"passed": True, "reason": "unsupported"}
                        if hasattr(LetterValidationService, "check_polish_fact_integrity"):
                            integrity_report = LetterValidationService().check_polish_fact_integrity(
                                pre_polish_markdown,
                                polished_candidate,
                                tracked_entities=[
                                    client_name,
                                    target_party_name,
                                    attorney_info.get("name") or "",
                                    attorney_info.get("firm") or "",
                                ],
                            )
                        metrics["polish_integrity_passed"] = bool(integrity_report.get("passed", True))

                        if integrity_report.get("passed", True):
                            draft_markdown_for_repair = polished_candidate
                            polished_html = json_service._convert_markdown_to_html(polished_candidate)
                            letter_html = DocumentFormatterService.format_demand_letter(
                                letter_html=polished_html,
                                recipient_name=target_party_name,
                            )
                            metrics["polish_applied"] = True
                        else:
                            metrics["polish_applied"] = False
                            metrics["polish_reverted"] = True
                            metrics["polish_revert_reason"] = (
                                f"fact_integrity:{integrity_report.get('reason', 'unknown')}"
                            )
                            logger.warning(
                                f"[DEMAND] Polish reverted due to fact integrity drift: {integrity_report}"
                            )
                except Exception as polish_err:
                    logger.warning(f"[DEMAND] Polish pass failed, using raw draft: {polish_err}")
            else:
                logger.info("[DEMAND] Polish pass disabled by configuration")
            letter_key = f"demand_{letter_request.target_party_name.replace(' ', '_')}".lower()

        validator = LetterValidationService()

        if gap_analysis and letter_request.letter_type == LetterType.FINDINGS and fact_matrix is not None:
            try:
                validation_result = validator.validate_letter(
                    letter_html=letter_html,
                    fact_matrix=fact_matrix,
                    gap_analysis=gap_analysis,
                    verified_statutes=verified_statutes,
                )
                if validation_result.warnings:
                    warning_summary = "; ".join([w.message for w in validation_result.warnings[:5]])
                    logger.warning(
                        f"Letter validation warnings ({len(validation_result.warnings)} total): {warning_summary}"
                    )
                else:
                    logger.info("Letter passed source-of-truth validation with no warnings")
            except Exception as validation_err:
                logger.warning(f"Letter validation skipped due to error: {validation_err}")

        if draft_markdown_for_repair:
            normalized_draft = _normalize_markdown(
                draft_markdown_for_repair,
                letter_request.letter_type.value,
            )
            if normalized_draft.strip() and normalized_draft.strip() != draft_markdown_for_repair.strip():
                draft_markdown_for_repair = normalized_draft
                if letter_request.letter_type == LetterType.DEMAND and target_party_name:
                    normalized_html = json_service._convert_markdown_to_html(draft_markdown_for_repair)
                    letter_html = DocumentFormatterService.format_demand_letter(
                        letter_html=normalized_html,
                        recipient_name=target_party_name,
                    )
                elif letter_request.letter_type == LetterType.FINDINGS:
                    normalized_html = json_service._convert_markdown_to_html(draft_markdown_for_repair)
                    letter_html = DocumentFormatterService.format_findings_letter(
                        letter_html=normalized_html,
                        client_name=client_name,
                    )
                else:
                    letter_html = json_service._convert_markdown_to_html(draft_markdown_for_repair)

        lint_input = draft_markdown_for_repair or letter_html
        if settings.letter_quality_lint_enabled:
            try:
                quality_report = validator.lint_client_letter(
                    lint_input,
                    mode="default",
                    letter_type=letter_request.letter_type.value,
                )
            except Exception as lint_err:
                logger.warning(f"Letter lint failed, using placeholder report: {lint_err}")

        critic_feedback: Dict[str, Any] = {"failed_sections": []}
        if (
            settings.letter_quality_critic_enabled
            and settings.letter_quality_lint_enabled
            and not quality_report.get("lint_passed", True)
            and _remaining_seconds() >= (critic_budget + finalize_budget)
        ):
            metrics["critic_attempted"] = True
            critic_started = time.monotonic()
            try:
                metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                critic_feedback = await json_service.run_quality_critic(
                    draft_markdown=lint_input,
                    letter_type=letter_request.letter_type.value,
                    lint_violations=quality_report.get("violations", []),
                    quality_report_v2=quality_report.get("quality_report_v2"),
                    model="gpt-5.4-mini",
                    timeout_seconds=critic_budget,
                )
            except Exception as critic_err:
                logger.warning(f"[LETTER] Critic step failed: {critic_err}")
                metrics["critic_skipped_reason"] = f"critic_error:{type(critic_err).__name__}"
            finally:
                metrics["critic_latency_ms"] = int((time.monotonic() - critic_started) * 1000)
        elif (
            settings.letter_quality_critic_enabled
            and settings.letter_quality_lint_enabled
            and not quality_report.get("lint_passed", True)
            and _remaining_seconds() < (critic_budget + finalize_budget)
        ):
            metrics["critic_skipped_reason"] = "insufficient_budget"

        if (
            settings.letter_conditional_repair_enabled
            and settings.letter_quality_lint_enabled
            and not quality_report.get("lint_passed", True)
            and _remaining_seconds() >= (repair_budget + finalize_budget)
        ):
            metrics["repair_attempted"] = True
            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
            repaired_markdown = await json_service.repair_letter_constraints(
                lint_input,
                quality_report.get("violations", []),
                mode="default",
                model="gpt-5.4-mini",
                critic_feedback=critic_feedback,
            )
            repaired_markdown = _normalize_markdown(
                repaired_markdown,
                letter_request.letter_type.value,
            )
            post_repair_report = validator.lint_client_letter(
                repaired_markdown,
                mode="default",
                letter_type=letter_request.letter_type.value,
            )
            quality_report = {
                **post_repair_report,
                "pre_repair": quality_report,
                "post_repair": post_repair_report,
                "critic_feedback": critic_feedback,
            }
            if repaired_markdown.strip() and repaired_markdown.strip() != lint_input.strip():
                if letter_request.letter_type == LetterType.DEMAND and target_party_name:
                    repaired_html = json_service._convert_markdown_to_html(repaired_markdown)
                    letter_html = DocumentFormatterService.format_demand_letter(
                        letter_html=repaired_html,
                        recipient_name=target_party_name,
                    )
                elif letter_request.letter_type == LetterType.FINDINGS:
                    repaired_html = json_service._convert_markdown_to_html(repaired_markdown)
                    letter_html = DocumentFormatterService.format_findings_letter(
                        letter_html=repaired_html,
                        client_name=client_name,
                    )
                else:
                    letter_html = json_service._convert_markdown_to_html(repaired_markdown)
                draft_markdown_for_repair = repaired_markdown
                metrics["repair_applied"] = True
                if critic_feedback.get("failed_sections"):
                    metrics["critic_applied"] = True
        elif (
            settings.letter_conditional_repair_enabled
            and settings.letter_quality_lint_enabled
            and not quality_report.get("lint_passed", True)
        ):
            quality_report = {
                **quality_report,
                "repair_skipped": "insufficient_budget",
                "critic_feedback": critic_feedback,
            }

        metrics["lint_passed"] = quality_report.get("lint_passed")
        metrics["lint_score"] = quality_report.get("score")
        metrics["total_latency_ms"] = int((time.monotonic() - started_at) * 1000)

        generated_letters = result_payload.setdefault("generated_letters", {})
        generated_letters[letter_key] = letter_html
        if letter_request.letter_type == LetterType.FINDINGS:
            generated_letters["findings_meta"] = {
                "quality_report": quality_report,
                "quality_report_v2": quality_report.get("quality_report_v2"),
                "generation_metrics": metrics,
                "strategy_object": strategy_object,
            }
        else:
            generated_letters[f"{letter_key}_meta"] = {
                "quality_report": quality_report,
                "quality_report_v2": quality_report.get("quality_report_v2"),
                "generation_metrics": metrics,
                "strategy_object": strategy_object,
            }

        supabase.table("analysis_results").update({"result": result_payload}).eq(
            "id", analysis_record["id"]
        ).execute()

        _emit_generation_metrics(metrics)

        total_elapsed = time.monotonic() - started_at
        logger.info(
            f"[LETTER_ENDPOINT] Complete | case_id={letter_request.case_id} "
            f"letter_type={letter_request.letter_type.value} "
            f"total_elapsed={total_elapsed:.1f}s"
        )

        return LetterGenerationResponse(
            letter_html=letter_html,
            letter_type=letter_request.letter_type,
            target_party_name=target_party_name,
            quality_report=quality_report,
            generation_metrics=metrics,
        )
    except HTTPException as exc:
        metrics["total_latency_ms"] = int((time.monotonic() - started_at) * 1000)
        if isinstance(exc.detail, dict):
            metrics["error_code"] = exc.detail.get("error") or str(exc.status_code)
        else:
            metrics["error_code"] = str(exc.status_code)
        _emit_generation_metrics(metrics)
        raise
    except Exception as exc:
        metrics["total_latency_ms"] = int((time.monotonic() - started_at) * 1000)
        metrics["error_code"] = type(exc).__name__
        _emit_generation_metrics(metrics)
        raise


# =============================================================================
# RECOMMENDATION LETTER GENERATION ENDPOINT (RETIRED)
# =============================================================================


@router.post("/generate-recommendation-letter")
async def generate_recommendation_letter():
    """Retired — use the streaming endpoint instead."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "The synchronous recommendation letter endpoint has been retired. "
            "Use the streaming endpoint: GET /{analysis_id}/recommendation-letter/stream"
        ),
    )


@router.get("/{analysis_id}/recommendation-letter/stream")
async def stream_recommendation_letter(
    analysis_id: str,
    letter_type: str = Query(...),
    schema_version: int = Query(default=2, ge=1, le=2),
    mode: Literal["default", "strict_quality"] = Query(default="default"),
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Stream recommendation letter generation with optional v2 SSE schema."""
    settings = get_settings()
    if not settings.recommendation_stream_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not enabled")

    from legal_portal.core.data_models import (
        DeepAnalysis,
        DocumentSummaryStructured,
        FactMatrix,
        GapAnalysisResult,
        RecommendedLetterType,
    )
    from legal_portal.services.letters.recommendation_letter_service import RecommendationLetterService

    response = supabase.table("analysis_results").select("*").eq("id", analysis_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis_data = response.data[0]
    _ensure_case_access(supabase, analysis_data["case_id"], user["id"])
    result_payload = analysis_data.get("result")
    if not result_payload:
        raise HTTPException(status_code=400, detail="Analysis result not yet available")

    processing_result = ProcessingResult(**result_payload)
    if not processing_result.multi_stage_result:
        raise HTTPException(status_code=400, detail="Multi-stage analysis results missing")

    msr = processing_result.multi_stage_result
    gap_analysis_data = msr.get("gap_analysis")
    if not gap_analysis_data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recommendation letter requires gap analysis. Please run gap analysis first.",
        )

    try:
        letter_type_enum = RecommendedLetterType(letter_type)
    except ValueError:
        valid_types = [t.value for t in RecommendedLetterType if t.value not in ["findings", "demand"]]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid letter_type '{letter_type}'. Valid types: {valid_types}",
        )

    effective_schema_version = 2 if (schema_version == 2 and settings.letter_stream_schema_v2) else 1
    artifacts = processing_result.artifacts or {}
    resolved_identity = _resolve_letter_identity_context(
        supabase=supabase,
        case_id=analysis_data["case_id"],
        artifacts=artifacts,
    )
    ai_preferences = await _get_user_ai_preferences(user["id"], supabase)

    def _event_payload(event_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if effective_schema_version == 1:
            if event_name == "token":
                return {"token": kwargs.get("token", "")}
            if event_name == "done":
                return {"done": True}
            if event_name == "error":
                return {"error": kwargs.get("error", "Stream failed")}
            return None

        payload: Dict[str, Any] = {
            "schema_version": 2,
            "event": event_name,
            "type": event_name,
        }
        payload.update(kwargs)
        if event_name == "done":
            payload["done"] = True
        return payload

    async def generate():
        request_started = time.monotonic()
        metrics = _new_generation_metrics(
            analysis_id=analysis_id,
            letter_type=letter_type,
            streaming=True,
        )
        quality_report = _quality_report_placeholder(mode=mode, letter_type="recommendation")
        draft_markdown = ""
        recoverable_timeout = False
        internal_budget = max(30, int(settings.letter_internal_budget_seconds))
        lint_budget = max(1, int(settings.letter_lint_budget_seconds))
        repair_budget = max(1, int(settings.letter_repair_budget_seconds))
        finalize_budget = max(1, int(settings.letter_finalize_budget_seconds))
        heartbeat_interval = max(1, int(settings.letter_stream_heartbeat_seconds))
        internal_deadline = request_started + internal_budget

        def _emit(event_name: str, **kwargs: Any) -> Optional[str]:
            payload = _event_payload(event_name, **kwargs)
            if payload is None:
                return None
            return _to_sse(payload)

        try:
            phase_msg = _emit("phase", phase="context_build", message="Building context", percent=8)
            if phase_msg:
                yield phase_msg

            gap_analysis = GapAnalysisResult(**gap_analysis_data)
            fact_matrix = FactMatrix(**msr.get("fact_matrix", {})) if msr.get("fact_matrix") else None
            deep_analysis = DeepAnalysis(**msr.get("deep_analysis", {})) if msr.get("deep_analysis") else None

            document_summaries = None
            if processing_result.document_summaries:
                try:
                    doc_summaries_raw = json.loads(processing_result.document_summaries)
                    document_summaries = [DocumentSummaryStructured(**ds) for ds in doc_summaries_raw]
                except Exception as parse_err:
                    logger.warning(f"Failed to parse document_summaries: {parse_err}")

            jurisdiction = artifacts.get("jurisdiction", "Florida")
            attorney_info = {
                "attorney_name": resolved_identity.get("attorney_name"),
                "firm_name": resolved_identity.get("firm_name"),
                "contact_phone": resolved_identity.get("contact_phone"),
                "contact_email": resolved_identity.get("contact_email"),
            }
            client_name = _resolve_client_name_for_letter(
                resolved_identity=resolved_identity,
                artifacts=artifacts,
                fact_matrix=fact_matrix,
            )

            phase_msg = _emit("phase", phase="draft_generation", message="Generating draft")
            if phase_msg:
                yield phase_msg

            openai_client = OpenAIClient(user_preferences=ai_preferences)
            rec_service = RecommendationLetterService(openai_client)
            json_service = JsonProcessingService(client=openai_client, config={})
            normalize_markdown = getattr(json_service, "normalize_client_letter_markdown", None)

            def _normalize_markdown(text: str, letter_kind: str) -> str:
                if callable(normalize_markdown):
                    return normalize_markdown(
                        text,
                        letter_type=letter_kind,
                        attorney_name=attorney_info.get("attorney_name"),
                        firm_name=attorney_info.get("firm_name"),
                    )
                return text

            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1

            token_queue: asyncio.Queue = asyncio.Queue()

            async def _collect_tokens() -> None:
                try:
                    async for token in rec_service.stream_recommendation_letter(
                        letter_type=letter_type_enum,
                        gap_analysis=gap_analysis,
                        deep_analysis=deep_analysis,
                        fact_matrix=fact_matrix,
                        document_summaries=document_summaries,
                        attorney_info=attorney_info,
                        client_name=client_name,
                        jurisdiction=jurisdiction,
                    ):
                        await token_queue.put(("token", token))
                except Exception as stream_err:
                    await token_queue.put(("error", stream_err))
                finally:
                    await token_queue.put(("done", None))

            collector_task = asyncio.create_task(_collect_tokens())
            draft_deadline = internal_deadline - (lint_budget + finalize_budget)
            _draft_token_count = 0
            _last_wc_emit_token = 0
            try:
                while True:
                    if time.monotonic() > draft_deadline:
                        metrics["timeout"] = True
                        metrics["error_code"] = "draft_budget_exceeded"
                        break
                    try:
                        msg_type, msg_data = await asyncio.wait_for(
                            token_queue.get(),
                            timeout=heartbeat_interval,
                        )
                    except asyncio.TimeoutError:
                        heartbeat_msg = _emit(
                            "heartbeat",
                            phase="draft_generation",
                            elapsed_ms=int((time.monotonic() - request_started) * 1000),
                        )
                        if heartbeat_msg:
                            yield heartbeat_msg
                        continue

                    if msg_type == "token":
                        token = str(msg_data or "")
                        if not token:
                            continue
                        draft_markdown += token
                        _draft_token_count += 1
                        if metrics["ttft_ms"] is None:
                            metrics["ttft_ms"] = int((time.monotonic() - request_started) * 1000)
                        token_msg = _emit("token", token=token)
                        if token_msg:
                            yield token_msg
                        if _draft_token_count - _last_wc_emit_token >= 200:
                            _last_wc_emit_token = _draft_token_count
                            _wc = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
                            _pct = min(88, 10 + _wc * 78 // 1000)
                            wc_msg = _emit("phase", phase="draft_generation", message=f"Drafting letter... ({_wc:,} words)", percent=_pct)
                            if wc_msg:
                                yield wc_msg
                    elif msg_type == "error":
                        if isinstance(msg_data, Exception):
                            raise msg_data
                        raise RuntimeError(str(msg_data))
                    elif msg_type == "done":
                        break
            finally:
                if not collector_task.done():
                    collector_task.cancel()
                    try:
                        await collector_task
                    except asyncio.CancelledError:
                        pass

            draft_word_count = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
            if metrics["timeout"] and draft_word_count >= 80:
                recoverable_timeout = True
                timeout_msg = _emit(
                    "error",
                    error="Draft generation exceeded time budget; finalizing best available content.",
                    code=metrics.get("error_code"),
                    recoverable=True,
                )
                if timeout_msg:
                    yield timeout_msg

            if not draft_markdown.strip():
                raise RuntimeError("Recommendation letter generation produced no content.")

            draft_markdown = _normalize_markdown(draft_markdown, "recommendation")

            phase_msg = _emit("phase", phase="lint_validation", message="Validating quality")
            if phase_msg:
                yield phase_msg

            validator = LetterValidationService()
            if settings.letter_quality_lint_enabled and (internal_deadline - time.monotonic()) > finalize_budget:
                quality_report = validator.lint_client_letter(
                    draft_markdown,
                    mode=mode,
                    letter_type="recommendation",
                )

            final_markdown = draft_markdown
            if (
                settings.letter_conditional_repair_enabled
                and settings.letter_quality_lint_enabled
                and not quality_report.get("lint_passed", True)
            ):
                remaining_seconds = internal_deadline - time.monotonic()
                if remaining_seconds >= (repair_budget + finalize_budget):
                    phase_msg = _emit("phase", phase="repair", message="Repairing quality issues")
                    if phase_msg:
                        yield phase_msg
                    metrics["repair_attempted"] = True
                    metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                    repaired = await rec_service.repair_recommendation_letter_constraints(
                        draft_markdown,
                        quality_report.get("violations", []),
                        mode=mode,
                        model="gpt-5.4-mini",
                    )
                    repaired = _normalize_markdown(repaired, "recommendation")
                    post_report = validator.lint_client_letter(
                        repaired,
                        mode=mode,
                        letter_type="recommendation",
                    )
                    quality_report = {
                        **post_report,
                        "pre_repair": quality_report,
                        "post_repair": post_report,
                    }
                    if repaired.strip() and repaired.strip() != draft_markdown.strip():
                        final_markdown = repaired
                        metrics["repair_applied"] = True
                else:
                    quality_report = {
                        **quality_report,
                        "repair_skipped": "insufficient_budget",
                    }

            phase_msg = _emit("phase", phase="finalizing", message="Finalizing letter")
            if phase_msg:
                yield phase_msg

            final_markdown = _normalize_markdown(final_markdown, "recommendation")
            final_html = rec_service.render_markdown_to_html(
                final_markdown,
                letter_type=letter_type_enum,
                client_name=client_name,
            )
            metrics["lint_passed"] = quality_report.get("lint_passed")
            metrics["lint_score"] = quality_report.get("score")
            metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)

            persisted_result = analysis_data.get("result") or {}
            generated_letters = persisted_result.setdefault("generated_letters", {})
            letter_key = f"recommendation_{letter_type}"
            generated_letters[letter_key] = final_html
            generated_letters[f"{letter_key}_meta"] = {
                "quality_report": quality_report,
                "generation_metrics": metrics,
            }
            supabase.table("analysis_results").update({"result": persisted_result}).eq(
                "id", analysis_id
            ).execute()

            quality_msg = _emit(
                "quality",
                quality_report=quality_report,
                generation_metrics=metrics,
            )
            if quality_msg:
                yield quality_msg

            final_msg = _emit(
                "final",
                content={
                    "format": "html",
                    "html": final_html,
                    "markdown": final_markdown,
                },
                quality_report=quality_report,
                generation_metrics=metrics,
            )
            if final_msg:
                yield final_msg

            done_msg = _emit("done")
            if done_msg:
                yield done_msg
            _emit_generation_metrics(metrics)

        except Exception as stream_err:
            if isinstance(stream_err, TimeoutError):
                metrics["timeout"] = True
                metrics["error_code"] = "timeout"
            else:
                metrics["error_code"] = type(stream_err).__name__
            metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)
            _emit_generation_metrics(metrics)

            error_msg = _emit(
                "error",
                error=str(stream_err),
                code=metrics.get("error_code"),
                recoverable=recoverable_timeout,
            )
            if error_msg:
                yield error_msg

            done_msg = _emit("done")
            if done_msg:
                yield done_msg

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# STREAMING DEMAND LETTER ENDPOINT
# =============================================================================


@router.get("/{analysis_id}/demand-letter/stream")
async def stream_demand_letter(
    analysis_id: str,
    target_party_name: str = Query(..., description="Name of the opposing party"),
    demand_amount: Optional[float] = Query(default=None, description="Dollar amount demanded"),
    demand_deadline: str = Query(default="10 business days", description="Response deadline"),
    specific_demands: str = Query(default="", description="Pipe-separated list of specific demands"),
    schema_version: int = Query(default=2, ge=1, le=2),
    mode: Literal["default", "strict_quality"] = Query(default="default"),
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Stream demand letter generation with SSE events and quality pipeline."""
    settings = get_settings()
    if not settings.demand_letter_stream_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Streaming demand letters not enabled. Use POST /generate-letter instead.",
        )

    response = supabase.table("analysis_results").select("*").eq("id", analysis_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis_data = response.data[0]
    _ensure_case_access(supabase, analysis_data["case_id"], user["id"])
    result_payload = analysis_data.get("result")
    if not result_payload:
        raise HTTPException(status_code=400, detail="Analysis result not yet available")

    processing_result = ProcessingResult(**result_payload)
    if not processing_result.multi_stage_result:
        raise HTTPException(status_code=400, detail="Multi-stage analysis results missing")

    msr = processing_result.multi_stage_result
    effective_schema_version = 2 if (schema_version == 2 and settings.letter_stream_schema_v2) else 1
    artifacts = processing_result.artifacts or {}
    resolved_identity = _resolve_letter_identity_context(
        supabase=supabase,
        case_id=analysis_data["case_id"],
        artifacts=artifacts,
    )
    ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
    demands_list = [d.strip() for d in specific_demands.split("|") if d.strip()] if specific_demands else []

    def _event_payload(event_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if effective_schema_version == 1:
            if event_name == "token":
                return {"token": kwargs.get("token", "")}
            if event_name == "done":
                return {"done": True}
            if event_name == "error":
                return {"error": kwargs.get("error", "Stream failed")}
            return None
        payload: Dict[str, Any] = {
            "schema_version": 2,
            "event": event_name,
            "type": event_name,
        }
        payload.update(kwargs)
        if event_name == "done":
            payload["done"] = True
        return payload

    async def generate():
        request_started = time.monotonic()
        metrics = _new_generation_metrics(
            analysis_id=analysis_id,
            letter_type="demand",
            streaming=True,
        )
        quality_report = _quality_report_placeholder(mode=mode, letter_type="demand")
        draft_markdown = ""
        recoverable_timeout = False
        internal_budget = max(30, int(settings.letter_internal_budget_seconds))
        lint_budget = max(1, int(settings.letter_lint_budget_seconds))
        repair_budget = max(1, int(settings.letter_repair_budget_seconds))
        finalize_budget = max(1, int(settings.letter_finalize_budget_seconds))
        strategy_budget = max(1, int(settings.letter_strategy_budget_seconds))
        heartbeat_interval = max(1, int(settings.letter_stream_heartbeat_seconds))
        internal_deadline = request_started + internal_budget

        def _emit(event_name: str, **kwargs: Any) -> Optional[str]:
            payload = _event_payload(event_name, **kwargs)
            if payload is None:
                return None
            return _to_sse(payload)

        try:
            phase_msg = _emit("phase", phase="context_build", message="Building context", percent=5)
            if phase_msg:
                yield phase_msg

            attorney_info = {
                "name": resolved_identity.get("attorney_name"),
                "firm": resolved_identity.get("firm_name"),
                "firm_address": resolved_identity.get("firm_address"),
                "phone": resolved_identity.get("contact_phone"),
                "email": resolved_identity.get("contact_email"),
                "bar_number": resolved_identity.get("bar_number"),
                "signature_block": resolved_identity.get("email_signature"),
            }
            client_name = _resolve_client_name_for_letter(
                resolved_identity=resolved_identity,
                artifacts=artifacts,
                fact_matrix=msr.get("fact_matrix"),
            )

            document_summaries = []
            if processing_result.document_summaries:
                try:
                    document_summaries = json.loads(processing_result.document_summaries)
                except Exception as parse_err:
                    logger.warning(f"Failed to parse document_summaries: {parse_err}")

            openai_client = OpenAIClient(user_preferences=ai_preferences)
            demand_service = DemandLetterService(openai_client)
            json_service = JsonProcessingService(client=openai_client, config={})
            normalize_markdown_fn = getattr(json_service, "normalize_client_letter_markdown", None)

            def _normalize_markdown(text: str, letter_kind: str) -> str:
                if callable(normalize_markdown_fn):
                    return normalize_markdown_fn(
                        text,
                        letter_type=letter_kind,
                        attorney_name=attorney_info.get("name"),
                        firm_name=attorney_info.get("firm"),
                    )
                return text

            # Strategy phase
            strategy_object = None
            if settings.letter_strategy_enabled and (internal_deadline - time.monotonic()) >= (strategy_budget + finalize_budget):
                phase_msg = _emit("phase", phase="strategy", message="Planning letter strategy", percent=8)
                if phase_msg:
                    yield phase_msg
                try:
                    from legal_portal.core.data_models import DeepAnalysis, FactMatrix, GapAnalysisResult
                    demand_fact_matrix = FactMatrix(**msr["fact_matrix"])
                    demand_deep_analysis = DeepAnalysis(**msr["deep_analysis"])
                    gap_analysis = None
                    if msr.get("gap_analysis"):
                        try:
                            gap_analysis = GapAnalysisResult(**msr["gap_analysis"])
                        except Exception:
                            pass
                    metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                    strategy_object = await demand_service.build_demand_strategy(
                        fact_matrix=demand_fact_matrix,
                        deep_analysis=demand_deep_analysis,
                        target_party_name=target_party_name,
                        demand_amount=demand_amount,
                        demand_deadline=demand_deadline,
                        specific_demands=demands_list,
                        client_name=client_name,
                        gap_analysis=gap_analysis,
                        timeout_seconds=strategy_budget,
                        allow_model=True,
                        model="gpt-5.4-mini",
                    )
                    metrics["strategy_used"] = bool(strategy_object)
                except Exception as strategy_err:
                    logger.warning(f"[DEMAND_STREAM] Strategy build failed: {strategy_err}")

            # Draft generation phase
            phase_msg = _emit("phase", phase="draft_generation", message="Generating draft", percent=15)
            if phase_msg:
                yield phase_msg

            metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
            token_queue: asyncio.Queue = asyncio.Queue()

            async def _collect_tokens() -> None:
                try:
                    async for token in demand_service.stream_demand_letter(
                        fact_matrix_dict=msr["fact_matrix"],
                        deep_analysis_dict=msr["deep_analysis"],
                        target_party_name=target_party_name,
                        demand_amount=demand_amount,
                        demand_deadline=demand_deadline,
                        specific_demands=demands_list,
                        attorney_info=attorney_info,
                        client_name=client_name,
                        document_summaries=document_summaries,
                        jurisdiction=artifacts.get("jurisdiction", "Florida"),
                        strategy_object=strategy_object,
                    ):
                        await token_queue.put(("token", token))
                except Exception as stream_err:
                    await token_queue.put(("error", stream_err))
                finally:
                    await token_queue.put(("done", None))

            collector_task = asyncio.create_task(_collect_tokens())
            draft_deadline = internal_deadline - (lint_budget + finalize_budget)
            _draft_token_count = 0
            _last_wc_emit_token = 0
            try:
                while True:
                    if time.monotonic() > draft_deadline:
                        metrics["timeout"] = True
                        metrics["error_code"] = "draft_budget_exceeded"
                        break
                    try:
                        msg_type, msg_data = await asyncio.wait_for(
                            token_queue.get(),
                            timeout=heartbeat_interval,
                        )
                    except asyncio.TimeoutError:
                        heartbeat_msg = _emit(
                            "heartbeat",
                            phase="draft_generation",
                            elapsed_ms=int((time.monotonic() - request_started) * 1000),
                        )
                        if heartbeat_msg:
                            yield heartbeat_msg
                        continue

                    if msg_type == "token":
                        token = str(msg_data or "")
                        if not token:
                            continue
                        draft_markdown += token
                        _draft_token_count += 1
                        if metrics["ttft_ms"] is None:
                            metrics["ttft_ms"] = int((time.monotonic() - request_started) * 1000)
                        token_msg = _emit("token", token=token)
                        if token_msg:
                            yield token_msg
                        if _draft_token_count - _last_wc_emit_token >= 200:
                            _last_wc_emit_token = _draft_token_count
                            _wc = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
                            _pct = min(88, 15 + _wc * 73 // 1000)
                            wc_msg = _emit("phase", phase="draft_generation", message=f"Drafting letter... ({_wc:,} words)", percent=_pct)
                            if wc_msg:
                                yield wc_msg
                    elif msg_type == "error":
                        if isinstance(msg_data, Exception):
                            raise msg_data
                        raise RuntimeError(str(msg_data))
                    elif msg_type == "done":
                        break
            finally:
                if not collector_task.done():
                    collector_task.cancel()
                    try:
                        await collector_task
                    except asyncio.CancelledError:
                        pass

            draft_word_count = len(re.findall(r"\b[\w'-]+\b", draft_markdown))
            if metrics["timeout"] and draft_word_count >= 80:
                recoverable_timeout = True
                timeout_msg = _emit(
                    "error",
                    error="Draft generation exceeded time budget; finalizing best available content.",
                    code=metrics.get("error_code"),
                    recoverable=True,
                )
                if timeout_msg:
                    yield timeout_msg

            if not draft_markdown.strip():
                raise RuntimeError("Demand letter generation produced no content.")

            draft_markdown = _normalize_markdown(draft_markdown, "demand")

            # Lint validation phase
            phase_msg = _emit("phase", phase="lint_validation", message="Validating quality", percent=90)
            if phase_msg:
                yield phase_msg

            validator = LetterValidationService()
            if settings.letter_quality_lint_enabled and (internal_deadline - time.monotonic()) > finalize_budget:
                quality_report = validator.lint_client_letter(
                    draft_markdown,
                    mode=mode,
                    letter_type="demand",
                )

            final_markdown = draft_markdown
            if (
                settings.letter_conditional_repair_enabled
                and settings.letter_quality_lint_enabled
                and not quality_report.get("lint_passed", True)
            ):
                remaining_seconds = internal_deadline - time.monotonic()
                if remaining_seconds >= (repair_budget + finalize_budget):
                    phase_msg = _emit("phase", phase="repair", message="Repairing quality issues")
                    if phase_msg:
                        yield phase_msg
                    metrics["repair_attempted"] = True
                    metrics["model_calls"] = int(metrics.get("model_calls", 0)) + 1
                    repaired = await json_service.repair_letter_constraints(
                        draft_markdown,
                        quality_report.get("violations", []),
                        mode=mode,
                        model="gpt-5.4-mini",
                    )
                    repaired = _normalize_markdown(repaired, "demand")
                    post_report = validator.lint_client_letter(
                        repaired,
                        mode=mode,
                        letter_type="demand",
                    )
                    quality_report = {
                        **post_report,
                        "pre_repair": quality_report,
                        "post_repair": post_report,
                    }
                    if repaired.strip() and repaired.strip() != draft_markdown.strip():
                        final_markdown = repaired
                        metrics["repair_applied"] = True
                else:
                    quality_report = {
                        **quality_report,
                        "repair_skipped": "insufficient_budget",
                    }

            # Polish phase
            if getattr(settings, "letter_polish_enabled", True) and (internal_deadline - time.monotonic()) > finalize_budget:
                phase_msg = _emit("phase", phase="polishing", message="Final polish", percent=93)
                if phase_msg:
                    yield phase_msg
                try:
                    from legal_portal.utils.letter_polish import polish_letter_async
                    _polish_timeout = getattr(settings, "letter_polish_timeout_seconds", 55)
                    remaining = internal_deadline - time.monotonic() - finalize_budget
                    _polish_timeout = min(_polish_timeout, max(10, remaining))
                    polish_result = await polish_letter_async(
                        openai_client,
                        final_markdown,
                        timeout_seconds=float(_polish_timeout),
                    )
                    if polish_result.get("success") and polish_result.get("polished_letter"):
                        polished_candidate = polish_result["polished_letter"]
                        integrity_report = {"passed": True, "reason": "unsupported"}
                        if hasattr(LetterValidationService, "check_polish_fact_integrity"):
                            integrity_report = LetterValidationService().check_polish_fact_integrity(
                                final_markdown,
                                polished_candidate,
                                tracked_entities=[
                                    client_name or "",
                                    target_party_name,
                                    attorney_info.get("name") or "",
                                    attorney_info.get("firm") or "",
                                ],
                            )
                        metrics["polish_integrity_passed"] = bool(integrity_report.get("passed", True))
                        if integrity_report.get("passed", True):
                            final_markdown = polished_candidate
                            metrics["polish_applied"] = True
                        else:
                            metrics["polish_applied"] = False
                            metrics["polish_reverted"] = True
                except Exception as polish_err:
                    logger.warning(f"[DEMAND_STREAM] Polish pass failed: {polish_err}")

            # Finalize phase
            phase_msg = _emit("phase", phase="finalizing", message="Finalizing letter", percent=96)
            if phase_msg:
                yield phase_msg

            final_markdown = _normalize_markdown(final_markdown, "demand")
            final_html_raw = json_service._convert_markdown_to_html(final_markdown)
            final_html = DocumentFormatterService.format_demand_letter(
                letter_html=final_html_raw,
                recipient_name=target_party_name,
            )

            metrics["lint_passed"] = quality_report.get("lint_passed")
            metrics["lint_score"] = quality_report.get("score")
            metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)

            # Persist
            persisted_result = analysis_data.get("result") or {}
            generated_letters = persisted_result.setdefault("generated_letters", {})
            letter_key = f"demand_{target_party_name.replace(' ', '_')}".lower()
            generated_letters[letter_key] = final_html
            generated_letters[f"{letter_key}_meta"] = {
                "quality_report": quality_report,
                "quality_report_v2": quality_report.get("quality_report_v2"),
                "generation_metrics": metrics,
                "strategy_object": strategy_object,
            }
            supabase.table("analysis_results").update({"result": persisted_result}).eq(
                "id", analysis_id
            ).execute()

            quality_msg = _emit(
                "quality",
                quality_report=quality_report,
                generation_metrics=metrics,
            )
            if quality_msg:
                yield quality_msg

            final_msg = _emit(
                "final",
                content={
                    "format": "html",
                    "html": final_html,
                    "markdown": final_markdown,
                },
                quality_report=quality_report,
                generation_metrics=metrics,
            )
            if final_msg:
                yield final_msg

            done_msg = _emit("done")
            if done_msg:
                yield done_msg
            _emit_generation_metrics(metrics)

            total_elapsed = time.monotonic() - request_started
            logger.info(
                f"[DEMAND_STREAM] Complete | analysis_id={analysis_id} "
                f"target_party={target_party_name} total_elapsed={total_elapsed:.1f}s"
            )

        except Exception as stream_err:
            if isinstance(stream_err, TimeoutError):
                metrics["timeout"] = True
                metrics["error_code"] = "timeout"
            else:
                metrics["error_code"] = type(stream_err).__name__
            metrics["total_latency_ms"] = int((time.monotonic() - request_started) * 1000)
            _emit_generation_metrics(metrics)

            error_msg = _emit(
                "error",
                error=str(stream_err),
                code=metrics.get("error_code"),
                recoverable=recoverable_timeout,
            )
            if error_msg:
                yield error_msg

            done_msg = _emit("done")
            if done_msg:
                yield done_msg

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/calculate-demand-amount", response_model=CalculateDemandAmountResponse)
async def calculate_demand_amount(
    request: CalculateDemandAmountRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Calculate suggested demand amount based on case analysis and selected party."""
    _ensure_case_access(supabase, request.case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, request.case_id)

    result_payload = analysis_record["result"]
    processing_result = ProcessingResult(**result_payload)

    if not processing_result.multi_stage_result:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Demand calculation requires the latest analysis. Please re-run the case analysis.",
        )

    # Fetch user's AI preferences
    ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
    openai_client = OpenAIClient(user_preferences=ai_preferences)

    msr = processing_result.multi_stage_result
    fact_matrix = msr.get("fact_matrix", {})
    deep_analysis = msr.get("deep_analysis", {})

    # Build context for AI calculation
    financial_data = fact_matrix.get("financial_data", [])
    parties = fact_matrix.get("parties", [])
    legal_issues = deep_analysis.get("issue_analyses", [])

    # Filter financial items related to the target party
    party_financial_items = []
    # general_financial_items = []

    for item in financial_data:
        description = item.get("description", "").lower()
        if request.target_party_name.lower() in description:
            party_financial_items.append(item)
        # else:
        #     general_financial_items.append(item)

    # Build AI prompt
    target_party = request.target_party_name
    prompt = f"""Analyze this case data and calculate a reasonable demand amount for: {target_party}

Financial Data:
{json.dumps(financial_data, indent=2)}

Parties Involved:
{json.dumps(parties, indent=2)}

Legal Issues:
{json.dumps(legal_issues, indent=2)}

Instructions:
1. Identify all amounts owed, damages claimed, or contract breaches related to {target_party}
2. Consider the strength of legal claims and potential recovery likelihood
3. Include reasonable attorney fees and costs if applicable
4. Provide a total demand amount that is justified by the evidence

Return a JSON object with:
- amount: float (total demand amount)
- reasoning: string (2-3 sentence explanation)
- breakdown: array of objects with {{description: string, amount: float}}

Be realistic and evidence-based. Only include amounts supported by the case data."""

    try:
        model = openai_client.get_preferred_model("demand_calculation", "gpt-5.4-mini")
        response = await asyncio.to_thread(
            openai_client.create_response,
            model=model,
            input=prompt,
            instructions="You are a legal analyst calculating demand amounts. Return only valid JSON.",
            reasoning_effort="low",
            verbosity="medium",
            max_output_tokens=1000,
        )

        result = json.loads(response["content"])

        return CalculateDemandAmountResponse(
            amount=result.get("amount", 0.0),
            reasoning=result.get("reasoning", "Unable to calculate demand amount."),
            breakdown=result.get("breakdown", []),
        )
    except Exception as e:
        logger.error(f"Error calculating demand amount: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate demand amount: {str(e)}",
        ) from e
