"""Core analysis endpoints — thin controller layer.

Route handlers for the 8 primary analysis endpoints (start, cancel, status,
results, streaming, save). Business logic delegated to service modules.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.rate_limiter import limiter
from legal_portal.api.routes._analysis_helpers import (
    AnalysisCancelledError,
    AnalysisRequest,
    AnalysisResponse,
    StreamingAnalysisSaveRequest,
    _cancel_analysis,
    _ensure_case_access,
    _update_case_with_retry,
    _upsert_with_retry,
)

# Import orchestration logic from service layer
from legal_portal.services.analysis.analysis_orchestrator import (
    ARTIFACT_BUCKET,
    ARTIFACT_PREFIX,
    SIGNED_URL_TTL,
    _attach_signed_artifact_urls,
    _dedup_email_threads,
    _download_and_extract_documents,
    _extract_deferred_documents,
    _generate_and_store_artifacts,
    _generate_eml_bytes,
    _html_to_plain_text,
    _store_artifact,
    process_case_background,
)

# Import streaming parse helpers from service layer
from legal_portal.services.analysis.streaming_parser import (
    _convert_statute_recommendations_recursive,
    _extract_embedded_json,
    _extract_list_items,
    _extract_section,
    _parse_currency,
)

from legal_portal.utils.openai_client import OpenAIClient

router = APIRouter()
logger = logging.getLogger(__name__)

# Re-export for backward compatibility (tests import from analysis module)
from legal_portal.api.routes._analysis_helpers import _db_columns_cache as _DB_COLUMNS_CACHE  # noqa: E402

__all__ = [
    "router",
    # Endpoints
    "start_analysis",
    "cancel_analysis",
    "cancel_case_analysis",
    "get_analysis_status",
    "get_analysis_results",
    "save_streaming_analysis",
    "stream_case_analysis",
    "get_streaming_result",
    # Background processing (re-exported from service layer)
    "process_case_background",
    # Core-specific helpers (re-exported from service layer)
    "_extract_deferred_documents",
    "_dedup_email_threads",
    "_download_and_extract_documents",
    # Artifact helpers (re-exported from service layer)
    "_html_to_plain_text",
    "_generate_eml_bytes",
    "_store_artifact",
    "_generate_and_store_artifacts",
    "_attach_signed_artifact_urls",
    "ARTIFACT_BUCKET",
    "ARTIFACT_PREFIX",
    "SIGNED_URL_TTL",
    # Streaming parse helpers (re-exported from service layer)
    "_convert_statute_recommendations_recursive",
    "_parse_currency",
    "_extract_embedded_json",
    "_extract_section",
    "_extract_list_items",
]


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")  # Rate limit AI analysis to prevent abuse
async def start_analysis(
    analysis_request: AnalysisRequest,
    request: Request,  # Required for rate limiter (must be named 'request')
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Start analysis for a case.

    On Vercel serverless, BackgroundTasks don't work reliably because the function
    instance is terminated after the response is sent. On Vercel, this endpoint
    returns an SSE stream that runs the analysis inline and streams progress.

    Args:
    ----
        analysis_request: Analysis request data
        request: FastAPI request object
        background_tasks: FastAPI background tasks handler (used for local dev only)
        user: Current authenticated user
        user_supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    Returns:
    -------
        On local: JSON with analysis record (202)
        On Vercel: SSE stream with progress events

    """
    import os
    is_vercel = os.getenv("VERCEL") is not None

    try:
        # Verify case ownership using user client (respects RLS)
        case_response = (
            user_supabase.table("cases")
            .select("id, status")
            .eq("id", analysis_request.case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        case = case_response.data[0]

        # Check if case already has pending/processing analysis
        if case["status"] in ["processing"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Case is already being processed"
            )

        # Clear needs_reanalysis flag when starting new analysis
        user_supabase.table("cases").update({
            "needs_reanalysis": False
        }).eq("id", analysis_request.case_id).execute()

        # Create analysis record using user client
        analysis_response = (
            user_supabase.table("analysis_results")
            .insert({"case_id": analysis_request.case_id, "status": "pending"})
            .execute()
        )

        if not analysis_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create analysis record"
            )

        analysis = analysis_response.data[0]

        # Update case status
        user_supabase.table("cases").update({"status": "processing"}).eq(
            "id", analysis_request.case_id
        ).execute()

        if is_vercel:
            # On Vercel: Return SSE stream that runs analysis inline
            # This keeps the connection alive and prevents function termination
            logger.info(f"[VERCEL] Starting SSE stream for analysis {analysis['id']}")

            async def analysis_stream():
                """Generator that runs analysis and yields progress events with heartbeats."""
                import asyncio

                analysis_id = analysis["id"]

                # First, yield the analysis record so frontend knows the ID immediately
                yield f"data: {json.dumps({'type': 'started', 'analysis': analysis})}\n\n"

                # Create a task for the analysis so we can yield heartbeats while it runs
                analysis_task = asyncio.create_task(
                    process_case_background(
                        analysis_request.case_id,
                        analysis_id,
                        service_supabase,
                        analysis_request.provider,
                        progress_manager=request.app.state.progress_manager,
                    )
                )

                last_progress = None
                heartbeat_count = 0

                try:
                    while not analysis_task.done():
                        # Check for progress updates in database
                        try:
                            result = service_supabase.table("analysis_results").select("status, progress").eq("id", analysis_id).single().execute()

                            if result.data:
                                current_status = result.data.get("status")
                                current_progress = result.data.get("progress")

                                # Yield progress if it changed
                                if current_progress and current_progress != last_progress:
                                    yield f"data: {json.dumps(current_progress)}\n\n"
                                    last_progress = current_progress
                                    heartbeat_count = 0  # Reset heartbeat counter on real progress

                                # Check if analysis completed or failed
                                if current_status in ["completed", "failed", "cancelled"]:
                                    break
                        except Exception as db_err:
                            logger.warning(f"Error checking progress: {db_err}")

                        # Send heartbeat every 10 seconds if no real progress
                        heartbeat_count += 1
                        if heartbeat_count >= 5:  # Every 5 * 2s = 10 seconds
                            yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                            heartbeat_count = 0

                        # Wait 2 seconds before checking again
                        await asyncio.sleep(2)

                    # Wait for the task to complete and get any exception
                    await analysis_task

                    # Fetch final status
                    final = service_supabase.table("analysis_results").select("status, progress").eq("id", analysis_id).single().execute()
                    final_status = final.data.get("status", "unknown") if final.data else "unknown"
                    final_progress = final.data.get("progress") if final.data else None

                    # Yield final progress if different
                    if final_progress and final_progress != last_progress:
                        yield f"data: {json.dumps(final_progress)}\n\n"

                    yield f"data: {json.dumps({'type': 'completed', 'status': final_status})}\n\n"
                    logger.info(f"[VERCEL] Analysis stream completed for {analysis_id} with status: {final_status}")

                except asyncio.CancelledError:
                    logger.warning(f"Analysis stream cancelled for {analysis_id}")
                    analysis_task.cancel()
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                except Exception as e:
                    logger.error(f"Analysis stream error for {analysis_id}: {e}", exc_info=True)
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

            return StreamingResponse(
                analysis_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-transform",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        else:
            # Local development: Use BackgroundTasks as before (returns JSON)
            logger.info(f"[LOCAL] Using BackgroundTasks for {analysis['id']}")
            background_tasks.add_task(
                process_case_background,
                analysis_request.case_id,
                analysis["id"],
                service_supabase,
                analysis_request.provider,
                progress_manager=request.app.state.progress_manager,
            )
            return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in start_analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error starting analysis: {str(e)}"
        ) from e


@router.post("/cancel/{analysis_id}", status_code=status.HTTP_200_OK)
async def cancel_analysis(
    analysis_id: str,
    request: Request,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Cancel an in-progress analysis and un-stick the case.

    This is a cooperative cancel: we mark the analysis as cancelled and set the case back to pending.
    The background worker checks this status and stops as soon as it hits a checkpoint.
    """
    try:
        # Verify analysis belongs to the user (RLS via user_supabase)
        resp = (
            user_supabase.table("analysis_results")
            .select("id, case_id, status")
            .eq("id", analysis_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found",
            )

        analysis = resp.data[0]
        case_id = analysis["case_id"]

        await _cancel_analysis(
            supabase=user_supabase,
            case_id=case_id,
            analysis_id=analysis_id,
            progress_manager=request.app.state.progress_manager,
        )

        return {"status": "cancelled", "analysis_id": analysis_id, "case_id": case_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel analysis: {str(e)}",
        ) from e


@router.post("/cancel-case/{case_id}", status_code=status.HTTP_200_OK)
async def cancel_case_analysis(
    case_id: str,
    request: Request,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    r"""Cancel the most recent in-progress analysis for a case.

    This enables "Cancel" from the cases list UI without needing an analysis_id.
    """
    try:
        # Verify ownership of the case (RLS via user_supabase)
        case_resp = (
            user_supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )
        if not case_resp.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Find the newest analysis for this case that is still pending/processing
        analysis_resp = (
            user_supabase.table("analysis_results")
            .select("id, status")
            .eq("case_id", case_id)
            .in_("status", ["pending", "processing"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not analysis_resp.data:
            return {"status": "no_active_analysis", "case_id": case_id}

        analysis_id = analysis_resp.data[0]["id"]

        await _cancel_analysis(
            supabase=user_supabase,
            case_id=case_id,
            analysis_id=analysis_id,
            progress_manager=request.app.state.progress_manager,
        )

        return {"status": "cancelled", "analysis_id": analysis_id, "case_id": case_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel case analysis: {str(e)}",
        ) from e


@router.get("/status/{case_id}", response_model=AnalysisResponse)
async def get_analysis_status(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Get the latest analysis status for a case.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Latest analysis result

    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get latest analysis for case
        response = (
            supabase.table("analysis_results")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found for this case"
            )

        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching analysis status: {str(e)}",
        ) from e


@router.get("/results/{case_id}")
async def get_analysis_results(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Get the full analysis results for a completed case.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    Returns:
    -------
        Analysis results (ProcessingResult)

    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get most recent analysis (regardless of status)
        response = (
            supabase.table("analysis_results")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data:
            return {"status": "pending", "message": "Analysis results not yet available"}

        analysis = response.data[0]
        # Include status in the response so frontend can handle it
        result_payload = analysis.get("result") or {}
        result_payload["status"] = analysis.get("status")
        result_payload["analysis_id"] = analysis.get("id")
        result_payload["created_at"] = analysis.get("created_at")
        result_payload["error"] = analysis.get("error")
        artifacts = result_payload.get("artifacts")
        if artifacts:
            result_payload["artifacts"] = _attach_signed_artifact_urls(service_supabase, artifacts)

        return result_payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching analysis results: {str(e)}",
        ) from e


@router.post("/stream/{case_id}/save")
async def save_streaming_analysis(
    case_id: str,
    request: StreamingAnalysisSaveRequest,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Save the result of a streaming analysis.

    Parses the markdown content and embedded JSON, then stores as an analysis result.
    The embedded JSON (in ```json block) contains structured data for letter generation.
    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases")
            .select("id, client_name, jurisdiction")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=404, detail="Case not found")

        case_data = case_response.data[0]

        # Parse embedded JSON from the markdown content (Layer 1: embedded extraction)
        structured_data = _extract_embedded_json(request.content)
        extraction_layer = "embedded" if structured_data else None

        # Layer 2: API extraction fallback when embedded JSON is missing
        if not structured_data:
            logger.warning(f"[STREAM:EXTRACTION] layer=embedded success=False case_id={case_id}")
            from legal_portal.config.default import get_settings
            settings = get_settings()
            if settings.enable_extraction_fallback:
                try:
                    from legal_portal.services.analysis.streaming_parser import extract_structured_data_via_api
                    structured_data = await extract_structured_data_via_api(
                        markdown_content=request.content,
                        jurisdiction=case_data.get("jurisdiction", "Florida"),
                    )
                    if structured_data:
                        extraction_layer = "api_extraction"
                        logger.info(f"[STREAM:EXTRACTION] layer=api_extraction success=True case_id={case_id}")
                    else:
                        logger.warning(f"[STREAM:EXTRACTION] layer=api_extraction success=False case_id={case_id}")
                except Exception as e:
                    logger.error(f"[STREAM:EXTRACTION] layer=api_extraction error={e} case_id={case_id}")
                    structured_data = {}

        if extraction_layer:
            logger.info(f"[STREAM:EXTRACTION] layer={extraction_layer} success=True case_id={case_id}")

        # Build case analysis from extracted data
        # Use clean issue names from structured JSON, not raw markdown
        key_issues_list = []
        if structured_data.get("primary_issues"):
            for issue in structured_data["primary_issues"]:
                issue_name = issue.get("name", "")
                if issue_name:
                    # Include strength and statutes for context
                    strength = issue.get("strength", "")
                    statutes = issue.get("statutes", [])
                    if statutes:
                        key_issues_list.append(f"{issue_name} ({strength}) - {', '.join(statutes)}")
                    else:
                        key_issues_list.append(f"{issue_name} ({strength})")

        # Fallback to markdown extraction if no structured data
        if not key_issues_list:
            key_issues_list = _extract_list_items(request.content, "Legal Issues Identified")

        case_analysis = {
            "case_summary": _extract_section(request.content, "Case Overview"),
            "key_issues": key_issues_list,
            "practice_area": structured_data.get("practice_area", "General Legal Matter"),
            "relevant_statutes": [],  # Extracted from structured_data below
        }

        # Add statutes from primary issues
        if structured_data.get("primary_issues"):
            for issue in structured_data["primary_issues"]:
                if issue.get("statutes"):
                    for statute in issue["statutes"]:
                        case_analysis["relevant_statutes"].append({
                            "statute": statute,
                            "relevance": issue.get("name", ""),
                        })

        # Build multi-stage compatible result for letter generation
        multi_stage_result = None
        if structured_data:
            logger.info("[STREAM] Building multi_stage_result from structured data")
            # Build timeline with correct field names for FactMatrix model
            timeline_events = []
            for d in structured_data.get("key_dates", []):
                timeline_events.append({
                    "date": d.get("date", ""),
                    "description": d.get("event", ""),  # FactMatrix uses 'description' not 'event'
                    "source_document": "Streaming Analysis",  # Required field
                    "significance": None,
                    "supporting_evidence": [],
                })

            # Build properly structured parties list for FactMatrix/Party model compatibility
            structured_parties = []
            for p in structured_data.get("parties", []):
                party_role = (p.get("role") or "").lower()
                is_opposing = party_role not in ["client", "plaintiff", "claimant", "attorney", "counsel"]
                structured_parties.append({
                    "name": p.get("name", ""),
                    "role": p.get("role", ""),
                    "contact_info": None,
                    "first_mentioned_in": "Streaming Analysis",
                    "is_opposing_party": is_opposing,
                    "entity_type": p.get("entity_type", "unknown"),
                })

            multi_stage_result = {
                "fact_matrix": {
                    "parties": structured_parties,
                    "timeline": timeline_events,
                    "financial_data": [],  # Required field for FactMatrix
                    "key_documents": [],   # Required field for FactMatrix
                    "preliminary_issues": [i.get("name", "") for i in structured_data.get("primary_issues", [])],  # Required
                    "financial_items": [],  # Keep for backward compatibility
                },
                "issue_map": {
                    "primary_issues": [
                        {
                            "issue_name": i.get("name", ""),  # Frontend expects issue_name for demand letters
                            "category": i.get("category", ""),
                            "applicable_statutes": i.get("statutes", []),
                            "strength": i.get("strength", "Moderate"),
                        }
                        for i in structured_data.get("primary_issues", [])
                    ],
                },
                "letter_structure": {
                    "style": structured_data.get("recommended_letter_type", "numbered_findings"),
                    "intro": "Key Findings",
                    "issue_format": "numbered_sections_with_headers",
                    "reasoning": "Default structure for comprehensive legal analysis",
                },
                # Deep analysis structure needed for letter generation
                "deep_analysis": {
                    "issue_analyses": [
                        {
                            "issue_name": i.get("name", ""),
                            "legal_standard": f"Legal standard for {i.get('name', '')} - see full analysis for details",
                            "fact_application": f"Fact application for {i.get('name', '')} - see full analysis for details",
                            "statute_analysis": ", ".join(i.get("statutes", [])) if i.get("statutes") else None,
                            "case_law_support": None,
                            "remedies_available": ["See full analysis for detailed remedies"],
                            "procedural_requirements": None,
                            "confidence_level": i.get("strength", "moderate").lower(),
                            "supporting_evidence": [],
                        }
                        for i in structured_data.get("primary_issues", [])
                    ],
                    "risk_assessment": {
                        "major_risks": [],
                        "risk_mitigation_steps": [],
                        "statute_of_limitations_concerns": None,
                        "evidence_gaps": [],
                    },
                    "deadline_tracking": [],
                    "evidence_strength": {
                        "strong_evidence": [],
                        "weak_evidence": [],
                        "missing_evidence": [],
                        "overall_strength": "moderate",
                    },
                    "overall_case_strength": structured_data.get("case_strength", "Moderate"),
                    "key_strengths": [],
                    "key_challenges": [],
                    "is_viable": True,
                    "viability_reasoning": "Based on streaming analysis",
                    "recommend_demand_letter": structured_data.get("recommended_letter_type") in ["demand", "demand_with_findings"],
                },
            }

            # Add financial data if present (parse currency strings to floats)
            if structured_data.get("financial_summary"):
                fin = structured_data["financial_summary"]

                # Prefer itemized financial_items when present
                items = fin.get("financial_items") or []
                if items:
                    for item in items:
                        amount = _parse_currency(item.get("amount"))
                        if amount > 0:
                            desc = item.get("description", "Financial item")
                            cat = item.get("category", "other")
                            ptype = item.get("payment_type", "claimed")
                            multi_stage_result["fact_matrix"]["financial_items"].append({
                                "description": desc,
                                "amount": amount,
                            })
                            multi_stage_result["fact_matrix"]["financial_data"].append({
                                "amount": amount,
                                "description": desc,
                                "source_document": "Streaming Analysis",
                                "payment_type": ptype,
                                "category": cat,
                                "date": None,
                            })
                else:
                    # Fallback: legacy 2-field parsing for old saved results
                    total_claimed = _parse_currency(fin.get("total_claimed"))
                    documented_damages = _parse_currency(fin.get("documented_damages"))

                    if total_claimed > 0:
                        multi_stage_result["fact_matrix"]["financial_items"].append({
                            "description": "Total Claimed",
                            "amount": total_claimed,
                        })
                        multi_stage_result["fact_matrix"]["financial_data"].append({
                            "amount": total_claimed,
                            "description": "Total Claimed",
                            "source_document": "Streaming Analysis",
                            "payment_type": "claimed",
                            "category": "damages_claimed",
                            "date": None,
                        })

                    if documented_damages > 0:
                        multi_stage_result["fact_matrix"]["financial_items"].append({
                            "description": "Documented Damages",
                            "amount": documented_damages,
                        })
                        multi_stage_result["fact_matrix"]["financial_data"].append({
                            "amount": documented_damages,
                            "description": "Documented Damages",
                            "source_document": "Streaming Analysis",
                            "payment_type": "claimed",
                            "category": "damages_claimed",
                            "date": None,
                        })

            # Verify statutes against legal corpus for letter generation
            # Defensive check: ensure multi_stage_result exists before modifying it
            if multi_stage_result is None:
                logger.warning("[STREAM] multi_stage_result is None, skipping verified_statutes conversion")
                multi_stage_result = {}

            try:
                from legal_portal.services.shared.statute_recommendation_service import StatuteRecommendationService
                jurisdiction = case_data.get("jurisdiction", "Florida")
                statute_service = StatuteRecommendationService(jurisdiction=jurisdiction)

                # Get legal issues from structured data
                legal_issues = [i.get("name", "") for i in structured_data.get("primary_issues", [])]

                # Get verified statutes from corpus (jurisdiction already set in constructor)
                verified_statutes = statute_service.recommend_statutes(
                    case_facts=request.content[:2000],  # First 2000 chars of analysis
                    legal_issues=legal_issues,
                )

                # Validate verified_statutes is a list
                if not isinstance(verified_statutes, list):
                    logger.warning(f"[STREAM] verified_statutes is not a list (type: {type(verified_statutes)}), converting to empty list")
                    verified_statutes = []

                # Convert StatuteRecommendation dataclass objects to dicts for JSON serialization
                from dataclasses import asdict
                converted_statutes = []
                conversion_errors = []

                for idx, statute in enumerate(verified_statutes):
                    try:
                        # Check if it's a StatuteRecommendation instance
                        from legal_portal.services.shared.statute_recommendation_service import StatuteRecommendation
                        if isinstance(statute, StatuteRecommendation):
                            converted = asdict(statute)
                            # Validate conversion produced a dict
                            if not isinstance(converted, dict):
                                raise TypeError(f"asdict() returned {type(converted)}, expected dict")
                            converted_statutes.append(converted)
                        else:
                            # If it's already a dict, validate and use it
                            if isinstance(statute, dict):
                                converted_statutes.append(statute)
                            else:
                                logger.warning(f"[STREAM] Item {idx} in verified_statutes is unexpected type: {type(statute)}")
                                conversion_errors.append(f"Item {idx}: {type(statute)}")
                    except (TypeError, AttributeError) as conv_err:
                        logger.error(f"[STREAM] Failed to convert StatuteRecommendation at index {idx}: {conv_err}")
                        conversion_errors.append(f"Item {idx}: {str(conv_err)}")
                    except Exception as conv_err:
                        logger.error(f"[STREAM] Unexpected error converting item {idx}: {conv_err}")
                        conversion_errors.append(f"Item {idx}: {str(conv_err)}")

                multi_stage_result["verified_statutes"] = converted_statutes

                if conversion_errors:
                    logger.warning(f"[STREAM] Had {len(conversion_errors)} conversion errors: {conversion_errors}")

                logger.info(f"[STREAM] Converted {len(converted_statutes)} StatuteRecommendation objects to dicts for {jurisdiction}")

            except (ImportError, ModuleNotFoundError) as import_err:
                logger.info(f"[STREAM] StatuteRecommendationService not available: {import_err}")
                if multi_stage_result is not None:
                    multi_stage_result["verified_statutes"] = []
            except (TypeError, AttributeError) as conv_err:
                logger.warning(f"[STREAM] Conversion error getting verified statutes: {conv_err}", exc_info=True)
                if multi_stage_result is not None:
                    multi_stage_result["verified_statutes"] = []
            except Exception as e:
                logger.warning(f"[STREAM] Failed to get verified statutes from corpus: {e}", exc_info=True)
                if multi_stage_result is not None:
                    multi_stage_result["verified_statutes"] = []

        # Fallback: build minimal multi_stage_result from markdown when structured_data extraction failed
        if not multi_stage_result:
            logger.warning(f"[STREAM:EXTRACTION] layer=fallback_skeleton case_id={case_id}")
            fallback_issues = _extract_list_items(request.content, "Legal Issues Identified")
            multi_stage_result = {
                "fact_matrix": {
                    "parties": [],
                    "timeline": [],
                    "financial_data": [],
                    "key_documents": [],
                    "preliminary_issues": fallback_issues,
                    "financial_items": [],
                },
                "issue_map": {
                    "primary_issues": [
                        {"issue_name": issue, "category": "", "applicable_statutes": [], "strength": "Moderate"}
                        for issue in fallback_issues
                    ],
                },
                "letter_structure": {
                    "style": "numbered_findings",
                    "intro": "Key Findings",
                    "issue_format": "numbered_sections_with_headers",
                    "reasoning": "Fallback structure — structured JSON extraction was unavailable",
                },
                "deep_analysis": {
                    "issue_analyses": [
                        {
                            "issue_name": issue,
                            "legal_standard": f"See full analysis for {issue}",
                            "fact_application": f"See full analysis for {issue}",
                            "statute_analysis": None,
                            "case_law_support": None,
                            "remedies_available": [],
                            "procedural_requirements": None,
                            "confidence_level": "moderate",
                            "supporting_evidence": [],
                        }
                        for issue in fallback_issues
                    ],
                    "risk_assessment": {
                        "major_risks": [],
                        "risk_mitigation_steps": [],
                        "statute_of_limitations_concerns": None,
                        "evidence_gaps": [],
                    },
                    "deadline_tracking": [],
                    "evidence_strength": {
                        "strong_evidence": [],
                        "weak_evidence": [],
                        "missing_evidence": [],
                        "overall_strength": "moderate",
                    },
                    "overall_case_strength": "Moderate",
                    "key_strengths": [],
                    "key_challenges": [],
                    "is_viable": True,
                    "viability_reasoning": "Based on streaming analysis (structured data unavailable)",
                    "recommend_demand_letter": False,
                },
                "verified_statutes": [],
            }

        # Fetch documents for this case (they're in a separate table, not embedded in case_data)
        # Include extracted_text since it's used for summaries and quality assessment
        docs_response = (
            service_supabase.table("documents")
            .select("id, file_name, file_type, extracted_text, extraction_quality, status, metadata")
            .eq("case_id", case_id)
            .execute()
        )
        documents = docs_response.data if docs_response.data else []
        logger.info(f"[STREAM] Building summaries for {len(documents)} documents")

        # Filter out duplicate/excluded documents from summaries and quality report
        # These documents should not appear in Document Review or Quality Report tabs
        filtered_documents = []
        excluded_count = 0
        for doc in documents:
            doc_status = doc.get("status") or ""
            metadata = doc.get("metadata") or {}
            is_excluded = metadata.get("excluded", False)
            is_duplicate = doc_status == "duplicate" or metadata.get("is_duplicate", False)

            if is_excluded or is_duplicate:
                excluded_count += 1
                continue
            filtered_documents.append(doc)

        if excluded_count > 0:
            logger.info(f"[STREAM] Filtered out {excluded_count} duplicate/excluded documents")

        # Build document summaries from filtered documents as JSON array (frontend expects this format)
        doc_summaries_array = []
        quality_report = []

        for doc in filtered_documents:
            # Handle None values explicitly - dict.get() only uses default if key is missing, not if value is None
            extracted_text = doc.get("extracted_text") or ""
            extraction_quality = doc.get("extraction_quality") or "low"
            file_type = doc.get("file_type") or ""
            file_name = doc.get("file_name") or "Document"

            # Determine document type from metadata enrichment or file_type fallback
            metadata = doc.get("metadata") or {}
            enrichment = metadata.get("attorney_enrichment") or metadata.get("enrichment") or {}
            doc_type = enrichment.get("document_type_override") or enrichment.get("document_type")
            if not doc_type and file_type:
                doc_type = file_type.split("/")[-1].upper()
            doc_type = doc_type or "Unknown"

            # Build document summary for Document Review tab
            doc_summary = {
                "document_name": file_name,
                "document_type": doc_type,
                "extraction_quality": extraction_quality,
                "relevance_to_case": "Contains extracted text" if extracted_text else "No text extracted",
                "executive_summary": (extracted_text[:300] + "...") if len(extracted_text) > 300 else (extracted_text or "No summary available"),
                "key_content": extracted_text[:1000] if extracted_text else "No text extracted",
                "key_amounts": [],
            }
            doc_summaries_array.append(doc_summary)

            # Build quality report entry for Quality Report tab
            quality_issues = []
            if not extracted_text:
                quality_issues.append("No text could be extracted from this document")
            elif len(extracted_text) < 100:
                quality_issues.append("Very little text extracted - document may be an image or scan")
            if file_type.startswith("image/"):
                quality_issues.append("Image file - text extraction may be limited")

            quality_report.append({
                "document": file_name,
                "document_id": doc.get("id") or "",
                "score": 8 if extraction_quality == "high" else 6 if extraction_quality == "medium" else 3,
                "confidence_level": extraction_quality,
                "issues": quality_issues,
            })

        # Extract opposing parties from structured data for demand letter dropdown
        opposing_parties = []
        if structured_data and structured_data.get("parties"):
            for party_data in structured_data["parties"]:
                role = (party_data.get("role") or "").lower()
                name = party_data.get("name") or ""

                # Identify opposing parties (not client or attorney)
                # Common opposing party roles include: landlord, contractor, seller, defendant, respondent
                is_opposing = (
                    "opposing" in role or
                    "defendant" in role or
                    "respondent" in role or
                    "landlord" in role or
                    "contractor" in role or
                    "seller" in role or
                    "hoa" in role or
                    "association" in role or
                    "company" in role or
                    "employer" in role or
                    (role and "client" not in role and "plaintiff" not in role and
                     "claimant" not in role and "attorney" not in role and "counsel" not in role)
                )

                if is_opposing and name:
                    opposing_parties.append({
                        "name": name,
                        "role": party_data.get("role", "Party"),
                        "entity_type": party_data.get("entity_type", "unknown"),
                        "is_opposing_party": True,
                    })

        logger.info(f"[STREAM] Identified {len(opposing_parties)} opposing parties for demand letter dropdown")

        # Build the complete result - must match ProcessingResult structure
        streaming_result = {
            # Required fields for ProcessingResult compatibility
            "main_letter": "",  # Letters are generated separately via letter generation endpoint
            "document_summaries": json.dumps(doc_summaries_array),  # Frontend expects JSON array
            "case_analysis": json.dumps(case_analysis),
            "quality_report": quality_report,  # For Quality Report tab

            # Streaming-specific fields
            "streaming_analysis": request.content,
            "multi_stage_result": multi_stage_result,
            "opposing_parties": opposing_parties,  # For demand letter party dropdown
            "artifacts": {
                "analysis_type": "streaming",
                "jurisdiction": case_data.get("jurisdiction", "Florida"),
                "structured_data": structured_data,
            },
            "status": "completed",
        }

        # Apply recursive conversion to catch any nested StatuteRecommendation objects
        logger.debug("[STREAM] Applying recursive conversion to streaming_result")
        streaming_result = _convert_statute_recommendations_recursive(streaming_result)

        # Explicit JSON serialization test before database save
        # This catches any serialization errors early with detailed error messages
        try:
            test_json = json.dumps(streaming_result)
            logger.debug(f"[STREAM] JSON serialization test passed ({len(test_json)} bytes)")
        except TypeError as json_err:
            # Find the problematic field
            error_msg = str(json_err)
            logger.error(f"[STREAM] JSON serialization test FAILED: {error_msg}")

            # Try to identify the problematic field by testing each top-level key
            problematic_fields = []
            for key, value in streaming_result.items():
                try:
                    json.dumps(value)
                except TypeError as field_err:
                    problematic_fields.append(f"{key}: {field_err}")
                    logger.error(f"[STREAM] Field '{key}' is not JSON serializable: {field_err}")

            # Apply recursive conversion one more time as a last resort
            logger.warning("[STREAM] Applying recursive conversion again to fix serialization issues")
            streaming_result = _convert_statute_recommendations_recursive(streaming_result)

            # Test again
            try:
                test_json = json.dumps(streaming_result)
                logger.info("[STREAM] JSON serialization test passed after recursive conversion")
            except TypeError as retry_err:
                # Log structure keys for debugging (not full content)
                result_keys = list(streaming_result.keys())
                logger.error(
                    f"[STREAM] JSON serialization still failing after recursive conversion. "
                    f"Error: {retry_err}. Result keys: {result_keys}. "
                    f"Problematic fields: {problematic_fields}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to serialize analysis result: {retry_err}. Problematic fields: {problematic_fields}"
                )

        # Create or update analysis result
        # Note: Gap analysis is now handled on-demand via POST /analyze-gaps endpoint
        analysis_id = str(uuid.uuid4())  # Default UUID for legacy path

        try:
            # Check if case exists before saving (prevents race condition in Clio import)
            # Retry up to 3 times with 2 second delays to allow case creation to complete
            import time
            case_exists = False
            for retry in range(3):
                case_check = service_supabase.table("cases").select("id").eq("id", case_id).limit(1).execute()
                if case_check.data:
                    case_exists = True
                    break

                if retry < 2:  # Don't wait on last attempt
                    logger.warning(f"[STREAM] Case {case_id} not found, retry {retry + 1}/3 in 2s...")
                    time.sleep(2)

            if not case_exists:
                logger.error(f"[STREAM] Case {case_id} still not found after 3 retries")
                raise HTTPException(
                    status_code=404,
                    detail=f"Case {case_id} not found in database. Please ensure the case was created before starting analysis."
                )

            logger.info(f"[STREAM] Case {case_id} confirmed, saving analysis results...")

            if request.stream_run_id:
                # Update the collector's row — single row per stream_run_id (Invariant #3)
                # Status guard: only transition processing → completed
                update_result = service_supabase.table("analysis_results") \
                    .update({
                        "status": "completed",
                        "result": streaming_result,
                        "completed_at": datetime.utcnow().isoformat(),
                    }) \
                    .eq("stream_run_id", request.stream_run_id) \
                    .eq("case_id", case_id) \
                    .eq("status", "processing") \
                    .execute()

                if update_result.data:
                    analysis_id = update_result.data[0]["id"]
                else:
                    # UPDATE matched zero rows. Determine why.
                    existing = service_supabase.table("analysis_results") \
                        .select("id, status") \
                        .eq("stream_run_id", request.stream_run_id) \
                        .limit(1).execute()

                    if existing.data:
                        existing_status = existing.data[0].get("status")
                        if existing_status == "completed":
                            # Already completed (duplicate /save call) — idempotent
                            analysis_id = existing.data[0]["id"]
                            logger.info(f"[STREAM:SAVE] Row already completed for stream_run_id={request.stream_run_id}")
                        else:
                            # Row exists but status is cancelled/error — do NOT resurrect
                            logger.warning(f"[STREAM:SAVE] Row is {existing_status}, refusing to complete")
                            raise HTTPException(status_code=409, detail=f"Analysis is {existing_status}, cannot save")
                    else:
                        # No row exists — collector hasn't saved yet. Create one.
                        try:
                            analysis_id = str(uuid.uuid4())
                            service_supabase.table("analysis_results").insert({
                                "id": analysis_id,
                                "case_id": case_id,
                                "stream_run_id": request.stream_run_id,
                                "status": "completed",
                                "result": streaming_result,
                                "completed_at": datetime.utcnow().isoformat(),
                                "created_at": datetime.utcnow().isoformat(),
                            }).execute()
                        except Exception as e:
                            if "duplicate key" in str(e) or "unique" in str(e).lower():
                                # Collector saved between our SELECT and INSERT — retry UPDATE
                                retry_result = service_supabase.table("analysis_results") \
                                    .update({
                                        "status": "completed",
                                        "result": streaming_result,
                                        "completed_at": datetime.utcnow().isoformat(),
                                    }) \
                                    .eq("stream_run_id", request.stream_run_id) \
                                    .eq("status", "processing") \
                                    .execute()
                                if retry_result.data:
                                    analysis_id = retry_result.data[0]["id"]
                            else:
                                raise
            else:
                # Legacy path: no stream_run_id, create new row (backwards compat)
                _upsert_with_retry(
                    service_supabase, "analysis_results",
                    {
                        "id": analysis_id,
                        "case_id": case_id,
                        "status": "completed",
                        "result": streaming_result,
                        "created_at": datetime.utcnow().isoformat(),
                    },
                    case_id,
                )
        except HTTPException:
            raise
        except Exception as db_err:
            # If database save fails, log detailed error
            error_detail = str(db_err)
            logger.error(
                f"[STREAM] Database save failed for case {case_id}: {error_detail}. "
                f"Result keys: {list(streaming_result.keys())}"
            )
            # Check if it's a serialization error
            if "not JSON serializable" in error_detail or "TypeError" in error_detail:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to save analysis result due to serialization error: {error_detail}"
                )
            raise

        # Update case status - must use valid status from constraint: pending, processing, completed, error, cancelled
        _update_case_with_retry(
            supabase, case_id,
            {"status": "completed", "updated_at": datetime.utcnow().isoformat()},
        )

        logger.info(f"[STREAM] Saved streaming analysis for case {case_id} | structured_data={'yes' if structured_data else 'no'}")

        return {"success": True, "analysis_id": analysis_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving streaming analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream/{case_id}")
async def stream_case_analysis(
    case_id: str,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Stream comprehensive case analysis in real-time.

    Uses GPT-4.1 to generate a complete analysis in a single streaming call.
    Output is markdown format that renders progressively in the frontend.

    This replaces the multi-stage analysis for faster, more reliable results.
    """
    from legal_portal.core.data_models import DocumentSummaryStructured
    from legal_portal.services.analysis.multi_stage_analyzer import MultiStageAnalyzer

    # Maximum characters of extracted_text to load per document.  Email
    # archives imported from Clio can contain 30+ MB of thread history — loading
    # them all in a single Supabase response causes an httpx ReadTimeout.  Only
    # the first MAX_DOC_CHARS are useful for LLM analysis anyway.
    MAX_DOC_CHARS = 200_000

    try:
        _stream_t0 = time.time()
        stream_run_id = str(uuid.uuid4())
        logger.info(f"[STREAM:ENTER] case_id={case_id} stream_run_id={stream_run_id}")

        # 1. Verify case ownership — fetch case metadata and document stubs only.
        # extracted_text is intentionally excluded from the nested relation to
        # avoid a single HTTP response that could exceed 100+ MB for cases with
        # many large email documents.
        _t_case = time.time()
        case_response = (
            supabase.table("cases")
            .select("*, documents(id,file_name,file_type,status,metadata)")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=404, detail="Case not found")

        case_data = case_response.data[0]
        doc_stubs = case_data.get("documents", [])
        logger.info(
            f"[STREAM:CASE_FETCH] elapsed={time.time()-_t_case:.2f}s "
            f"doc_stubs={len(doc_stubs)}"
        )

        if not doc_stubs:
            raise HTTPException(status_code=400, detail="No documents found for this case")

        # 1b. Fetch extracted_text for all documents in a single batch query.
        # Using .in_() avoids N+1 round trips (one per document) which was the
        # primary cause of connection count and CPU exhaustion on Supabase.
        doc_ids = [stub["id"] for stub in doc_stubs]
        text_by_id: dict = {}
        try:
            _t_text = time.time()
            text_resp = (
                supabase.table("documents")
                .select("id, extracted_text")
                .in_("id", doc_ids)
                .execute()
            )
            _text_rows = text_resp.data or []
            _nonempty = 0
            _max_doc_bytes = 0
            _total_text_bytes = 0
            for row in _text_rows:
                raw = row.get("extracted_text") or ""
                _raw_len = len(raw)
                _total_text_bytes += _raw_len
                if _raw_len > _max_doc_bytes:
                    _max_doc_bytes = _raw_len
                if _raw_len > 0:
                    _nonempty += 1
                text_by_id[row["id"]] = raw[:MAX_DOC_CHARS]
            logger.info(
                f"[STREAM:TEXT_FETCH] elapsed={time.time()-_t_text:.2f}s "
                f"rows={len(_text_rows)} nonempty={_nonempty} "
                f"total_text_bytes={_total_text_bytes:,} max_doc_bytes={_max_doc_bytes:,}"
            )
        except Exception as text_err:
            logger.warning(f"[STREAM] Could not batch-fetch extracted_text: {text_err}")

        documents = []
        for stub in doc_stubs:
            doc = dict(stub)
            doc["extracted_text"] = text_by_id.get(stub["id"], "")
            documents.append(doc)

        # 2. Build document summaries from extracted text
        doc_summaries = []
        intake_content = ""

        for doc in documents:
            extracted_text = doc.get("extracted_text", "") or ""
            file_name = doc.get("file_name", "unknown")

            # Derive doc_type from metadata or file_type since it's not a DB column
            metadata = doc.get("metadata") or {}
            doc_type = (
                metadata.get("classification")
                or metadata.get("attorney_enrichment", {}).get("document_type_override")
                or doc.get("file_type", "document")
            )

            if extracted_text:
                # Find intake form
                if "intake" in file_name.lower():
                    intake_content = extracted_text

                doc_summaries.append(DocumentSummaryStructured(
                    document_name=file_name,
                    document_type=doc_type,
                    executive_summary=extracted_text[:500],
                    key_content=extracted_text[:3000],
                ))

        if not intake_content and doc_summaries:
            # Use first document if no intake found
            intake_content = doc_summaries[0].key_content or ""

        logger.info(
            f"[STREAM:DOC_SUMMARIES] count={len(doc_summaries)} "
            f"intake_chars={len(intake_content)} "
            f"elapsed_since_entry={time.time()-_stream_t0:.2f}s"
        )

        # 3. Determine jurisdiction
        jurisdiction = case_data.get("jurisdiction", "Florida")

        # 4. Check quick preview feature flag — read from env directly to avoid
        # stale Settings() singleton on warm Vercel instances after env var changes.
        _quick_preview_enabled = os.environ.get("ENABLE_ANALYSIS_QUICK_PREVIEW", "").strip().lower() in ("true", "1", "yes")

        # Count documents for inventory event
        _doc_count = len(doc_summaries)

        # 5. Stream the analysis with thinking heartbeats
        async def generate():
            try:
                openai_client = OpenAIClient()
                analyzer = MultiStageAnalyzer(openai_client=openai_client)

                full_content = ""
                first_token_received = False
                start_time = time.time()
                last_heartbeat = start_time

                # Emit document inventory event (immediate, no LLM call)
                if _quick_preview_enabled:
                    yield f"data: {json.dumps({'phase': 'inventory', 'total': _doc_count})}\n\n"

                # Signal that we're starting (thinking phase begins)
                yield f"data: {json.dumps({'phase': 'thinking', 'elapsed': 0, 'stream_run_id': stream_run_id})}\n\n"

                # Quick preview via gpt-5-mini (fast, ~3-5s)
                _preview_classifications = []
                if _quick_preview_enabled:
                    try:
                        async for preview_msg in analyzer.quick_preview_streaming(doc_summaries):
                            if "token" in preview_msg:
                                yield f"data: {json.dumps({'phase': 'preview', 'token': preview_msg['token']})}\n\n"
                            elif "classifications" in preview_msg:
                                _preview_classifications = preview_msg["classifications"]
                                yield f"data: {json.dumps({'phase': 'preview_classifications', 'classifications': _preview_classifications})}\n\n"
                            elif preview_msg.get("done"):
                                yield f"data: {json.dumps({'phase': 'preview', 'done': True})}\n\n"
                    except Exception as preview_err:
                        logger.warning(f"[STREAM:PREVIEW] Preview failed (non-fatal): {preview_err}")

                    # Persist classifications in background (non-blocking)
                    if _preview_classifications:
                        try:
                            from legal_portal.services.documents.document_registry_service import DocumentRegistryService
                            DocumentRegistryService.apply_preview_classifications(
                                _preview_classifications, documents, service_supabase,
                            )
                        except Exception as persist_err:
                            logger.warning(f"[STREAM:PREVIEW] Classification persistence failed: {persist_err}")

                # Heartbeat before context build — the gap between preview-done
                # and the first heartbeat from the token loop can be 5-15s for
                # large cases (context build + prompt assembly).  Without this,
                # Vercel's edge proxy may consider the stream idle and drop it.
                yield f"data: {json.dumps({'phase': 'thinking', 'elapsed': int(time.time() - start_time)})}\n\n"

                # Create the token generator (now returns tuple)
                _t_analyze = time.time()
                token_generator, ctx_result = await analyzer.analyze_streaming(
                    intake_content=intake_content,
                    document_summaries=doc_summaries,
                    jurisdiction=jurisdiction,
                    preview_classifications=_preview_classifications if _quick_preview_enabled else None,
                )
                _docs_in_scope = ctx_result.docs_in_scope
                _docs_omitted = ctx_result.docs_omitted
                logger.info(
                    f"[STREAM:LLM_START] elapsed_since_entry={_t_analyze - _stream_t0:.2f}s "
                    f"analyze_streaming_setup={time.time()-_t_analyze:.2f}s "
                    f"docs_in_scope={_docs_in_scope} docs_omitted={_docs_omitted} "
                    f"context_tokens={ctx_result.total_tokens:,}"
                )

                # Section progress tracking — detect ## headings in token stream
                import re
                _section_names = [
                    "Case Overview", "Key Facts", "Legal Issues",
                    "Risk Assessment", "Recommended Actions", "Structured Data",
                ]
                _total_sections = len(_section_names)
                _sections_seen = 0
                _line_buffer = ""  # Buffer to detect headings across token boundaries

                # Use asyncio.Queue to handle tokens with heartbeat timeout.
                # The collector accumulates content independently so that if
                # the client disconnects mid-stream, the finally block can
                # save whatever the LLM has produced so far.
                token_queue: asyncio.Queue = asyncio.Queue()
                _collector_content = []  # mutable list shared with collector

                async def collect_tokens():
                    """Collect tokens, put in queue, and accumulate for recovery."""
                    try:
                        async for token in token_generator:
                            _collector_content.append(token)
                            await token_queue.put(('token', token))
                        await token_queue.put(('done', None))
                    except Exception as e:
                        await token_queue.put(('error', str(e)))
                    finally:
                        # Collector finished (success or error) — save result
                        # so recovery endpoint can find it even if the SSE
                        # generator was already cancelled by client disconnect.
                        _all = "".join(_collector_content)
                        if _all:
                            try:
                                service_supabase.table("analysis_results").insert({
                                    "id": str(uuid.uuid4()),
                                    "case_id": case_id,
                                    "stream_run_id": stream_run_id,
                                    "status": "processing",
                                    "result": {
                                        "raw_streaming_content": _all,
                                        "docs_in_scope": ctx_result.docs_in_scope,
                                        "docs_omitted": ctx_result.docs_omitted,
                                        "context_tokens": ctx_result.total_tokens,
                                        "omission_reason": ctx_result.omission_reason,
                                        "jurisdiction": jurisdiction,
                                        "collector_saved": True,
                                        "streaming_completed_at": datetime.utcnow().isoformat(),
                                    },
                                    "created_at": datetime.utcnow().isoformat(),
                                }).execute()
                                logger.info(
                                    f"[STREAM:COLLECTOR_SAVE] Saved {len(_all)} chars "
                                    f"for case {case_id} stream_run_id={stream_run_id}"
                                )
                            except Exception as _csave_err:
                                if "duplicate key" in str(_csave_err) or "unique" in str(_csave_err).lower():
                                    # Row already exists (frontend /save or prior collector).
                                    # Do NOT overwrite — existing row may be completed/cancelled.
                                    logger.info(
                                        f"[STREAM:COLLECTOR_SAVE] Row already exists for "
                                        f"stream_run_id={stream_run_id}, skipping"
                                    )
                                else:
                                    logger.error(
                                        f"[STREAM:COLLECTOR_SAVE] Failed for case "
                                        f"{case_id}: {_csave_err}"
                                    )

                # Start token collection in background
                collector_task = asyncio.create_task(collect_tokens())

                try:
                    while True:
                        try:
                            # Wait for token with 5-second timeout for heartbeat
                            msg_type, msg_data = await asyncio.wait_for(
                                token_queue.get(),
                                timeout=5.0
                            )

                            if msg_type == 'token':
                                if not first_token_received:
                                    first_token_received = True
                                    elapsed = int(time.time() - start_time)
                                    _total_ttft = time.time() - _stream_t0
                                    logger.info(
                                        f"[STREAM:FIRST_TOKEN] thinking_time={elapsed}s "
                                        f"total_time_to_first_token={_total_ttft:.1f}s"
                                    )
                                    # Signal transition from thinking to streaming
                                    yield f"data: {json.dumps({'phase': 'streaming', 'thinking_time': elapsed})}\n\n"

                                full_content += msg_data
                                yield f"data: {json.dumps({'token': msg_data})}\n\n"

                                # Detect section headings for progress tracking
                                _line_buffer += msg_data
                                if "\n" in _line_buffer:
                                    _lb_lines = _line_buffer.split("\n")
                                    _line_buffer = _lb_lines[-1]  # keep incomplete line
                                    for _lb_line in _lb_lines[:-1]:
                                        _stripped = _lb_line.strip()
                                        if _stripped.startswith("## "):
                                            _heading = _stripped[3:].strip()
                                            _sections_seen += 1
                                            yield f"data: {json.dumps({'phase': 'section', 'section': _heading, 'index': _sections_seen, 'total': _total_sections})}\n\n"

                            elif msg_type == 'done':
                                # Signal completion — include scope counts for UI warning
                                yield f"data: {json.dumps({'done': True, 'content': full_content, 'stream_run_id': stream_run_id, 'docs_in_scope': ctx_result.docs_in_scope, 'docs_omitted': ctx_result.docs_omitted, 'context_tokens': ctx_result.total_tokens, 'omission_reason': ctx_result.omission_reason, 'omitted_doc_names': ctx_result.omitted_doc_names[:10]})}\n\n"
                                logger.info(
                                    f"[STREAM] Completed streaming for case {case_id} | "
                                    f"docs_in_scope={_docs_in_scope} docs_omitted={_docs_omitted}"
                                )

                                # Auto-save is handled by the collector task's
                                # finally block (runs on both normal completion
                                # and client disconnect).  No duplicate save needed.
                                break

                            elif msg_type == 'error':
                                yield f"data: {json.dumps({'error': msg_data})}\n\n"
                                break

                        except asyncio.TimeoutError:
                            # No token received in 5 seconds - send heartbeat
                            elapsed = int(time.time() - start_time)

                            if not first_token_received:
                                # Still in thinking phase - send thinking heartbeat
                                yield f"data: {json.dumps({'phase': 'thinking', 'elapsed': elapsed})}\n\n"
                                logger.debug(f"[STREAM] Thinking heartbeat: {elapsed}s")
                            else:
                                # In streaming phase but slow - send streaming heartbeat
                                yield f"data: {json.dumps({'heartbeat': elapsed})}\n\n"

                finally:
                    # On client disconnect Starlette cancels this generator.
                    # We must NOT cancel the collector — let it finish the
                    # LLM call and save via its own finally block.
                    #
                    # asyncio.shield prevents cancellation from propagating
                    # to the collector task.  We catch CancelledError on
                    # the outer await so the finally block completes.
                    if not collector_task.done():
                        logger.info(
                            f"[STREAM:DISCONNECT] Generator exiting while "
                            f"collector still running for case {case_id} — "
                            f"awaiting LLM completion server-side "
                            f"(accumulated {len(full_content)} chars so far)"
                        )
                        try:
                            # Shield keeps collector alive; wrapping in
                            # try/except ensures CancelledError on the
                            # outer await doesn't kill the finally block.
                            await asyncio.shield(collector_task)
                        except (asyncio.CancelledError, Exception):
                            # CancelledError is expected here — the
                            # generator is being torn down.  The collector
                            # task itself is NOT cancelled (shield) and
                            # will save when it finishes.
                            logger.info(
                                f"[STREAM:DISCONNECT] Shield caught cancel "
                                f"for case {case_id} — collector will "
                                f"continue in background"
                            )

            except Exception as e:
                logger.error(f"[STREAM] Error during streaming: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable Vercel/nginx buffering
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in stream_case_analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream/{case_id}/result")
async def get_streaming_result(
    case_id: str,
    stream_run_id: Optional[str] = Query(default=None),
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Check if a streaming analysis has completed for this case (recovery endpoint).

    When stream_run_id is provided (active streaming session), filters by exact
    stream_run_id + status IN (processing, completed). This prevents returning
    stale results from a different run.

    When stream_run_id is NULL (Resume button), only returns completed analyses.
    """
    query = supabase.table("analysis_results") \
        .select("id, status, result, created_at") \
        .eq("case_id", case_id)

    if stream_run_id:
        # DB-level filter — uses the UNIQUE index on stream_run_id.
        # Only return processing (collector-saved) or completed rows.
        query = query.eq("stream_run_id", stream_run_id) \
                     .in_("status", ["processing", "completed"])
    else:
        # Legacy/Resume: latest completed only (never partial/processing)
        query = query.eq("status", "completed")

    query = query.order("created_at", desc=True).limit(1)
    response = query.execute()

    if response.data:
        row = response.data[0]
        result = row.get("result", {})
        # Content key read order: collector → legacy → /save
        content = (result.get("raw_streaming_content")
                   or result.get("streaming_analysis_content", "")
                   or result.get("streaming_analysis", ""))
        if content:
            return {
                "found": True,
                "content": content,
                "status": row.get("status"),
                "docs_in_scope": result.get("docs_in_scope", 0),
                "docs_omitted": result.get("docs_omitted", 0),
                "analysis_id": row["id"],
            }

    return {"found": False}
