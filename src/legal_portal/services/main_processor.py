from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re  # Added for _clean_and_parse_json
import time
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Tuple

from legal_portal.config.default import get_settings
from legal_portal.core.data_models import (
    AnalyzedDocument,
    CaseAnalysisResult,
    DocumentSummaryStructured,
    IntakeAnalysis,
    Party,
    ProcessedDocument,
    ProcessingError,
    ProcessingResult,
    QualityScore,
    SkippedDocument,
)
from legal_portal.services.chunk_service import build_document_tracking_ids
from legal_portal.services.chunk_state_manager import ChunkStateManager
from legal_portal.services.corpus_coverage_service import CorpusCoverageService
from legal_portal.services.document_registry_service import DocumentRegistryService
from legal_portal.services.document_quality_validator import DocumentQualityValidator
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer
from legal_portal.services.statute_recommendation_service import StatuteRecommendationService
from legal_portal.utils.diagnostic_logger import DiagnosticLogger
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


async def _run_with_heartbeat(
    coro_or_callable,
    progress_callback: Optional[Callable],
    phase: str,
    percent: int,
    heartbeat_interval: float = 10.0,
    *args,
    **kwargs
):
    """Run a coroutine or callable while sending heartbeat progress updates.
    
    This prevents SSE connections from timing out during long-running operations
    like case synthesis or multi-stage analysis.
    """
    import time as _time
    start = _time.time()

    # Determine if we have a coroutine or a sync function
    if asyncio.iscoroutinefunction(coro_or_callable):
        task = asyncio.create_task(coro_or_callable(*args, **kwargs))
    elif callable(coro_or_callable):
        # Wrap sync function in a thread
        task = asyncio.create_task(asyncio.to_thread(coro_or_callable, *args, **kwargs))
    else:
        # Already a coroutine
        task = asyncio.create_task(coro_or_callable)

    # Send heartbeats while waiting for the task to complete
    while not task.done():
        try:
            # Wait for either the task to complete or the heartbeat interval
            await asyncio.wait_for(asyncio.shield(task), timeout=heartbeat_interval)
            break  # Task completed
        except asyncio.TimeoutError:
            # Task still running, send heartbeat
            elapsed = int(_time.time() - start)
            if progress_callback:
                await progress_callback(
                    f"Processing... ({elapsed}s)",
                    [],
                    phase,
                    percent,
                )

    # Return the task result (may raise if task failed)
    return await task


# Shared prompt instructions for image document handling
IMAGE_HANDLING_INSTRUCTIONS = """
---
**CRITICAL INSTRUCTIONS FOR IMAGE DOCUMENTS:**
Documents marked with [📷 IMAGE FILE] are images. For these:
- Base analysis ONLY on the visual description provided in the content
- DO NOT infer `parties`, `key_dates`, or `key_amounts` unless explicitly visible/readable
  in the image description
- Set `document_type` to "Evidence"
- For `issues_identified`: describe what is visually shown (e.g., "Visible water damage on flooring")
- For `relevance_to_case`: explain what the image depicts and why it matters to the case
- Leave `parties`, `key_dates`, `key_amounts` empty unless the image shows readable text containing these
---
"""

_SIGNATURE_INSTRUMENT_HINT_PATTERNS = [
    ("subscription agreement", re.compile(r"\bsubscription\s+agreement\b", re.IGNORECASE)),
    ("investment agreement", re.compile(r"\binvestment\s+agreement\b", re.IGNORECASE)),
    ("purchase agreement", re.compile(r"\b(?:unit\s+)?purchase\s+agreement\b", re.IGNORECASE)),
    ("operating agreement", re.compile(r"\boperating\s+agreement\b", re.IGNORECASE)),
    ("promissory note", re.compile(r"\bpromissory\s+note\b", re.IGNORECASE)),
    ("convertible note", re.compile(r"\bconvertible\s+note\b", re.IGNORECASE)),
    ("loan agreement", re.compile(r"\bloan\s+agreement\b", re.IGNORECASE)),
    ("financing agreement", re.compile(r"\bfinancing\s+agreement\b", re.IGNORECASE)),
    ("membership units", re.compile(r"\bclass\s+[a-z0-9]+\s+units?\b", re.IGNORECASE)),
]

# Prompt-shaping controls for document summarization.
# Long documents are chunked into excerpts so batching/token estimates stay stable.
PROMPT_MAX_DOC_CHARS = 24000
PROMPT_LONG_DOC_CHUNKS = 3
PROMPT_MAX_DOCS_PER_BATCH = 10
PROMPT_MAX_CONCURRENT_BATCHES = 3

# Prompt-shaping controls for case synthesis.
CASE_SYNTHESIS_MAX_INTAKE_CHARS = 12000
CASE_SYNTHESIS_MAX_SUMMARIES = 40
CASE_SYNTHESIS_MAX_SUMMARY_TEXT_CHARS = 2200
CASE_SYNTHESIS_MAX_TOTAL_SUMMARY_CHARS = 75000


def _extract_signature_instrument_hints(file_name: str, content: str) -> List[str]:
    """Extract lightweight instrument hints for gap-analysis reconciliation."""
    corpus = f"{file_name or ''}\n{(content or '')[:24000]}"
    hints: List[str] = []
    seen = set()

    for label, pattern in _SIGNATURE_INSTRUMENT_HINT_PATTERNS:
        if not pattern.search(corpus):
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        hints.append(label)
        if len(hints) >= 6:
            break

    return hints


def _build_signature_evidence_for_gap_analysis(
    processed_documents: List[ProcessedDocument],
) -> List[Dict[str, Any]]:
    """Build authoritative signature evidence for stage 3.5 gap reconciliation."""
    evidence: List[Dict[str, Any]] = []

    for doc in processed_documents:
        signature_detection = doc.signature_detection
        if not isinstance(signature_detection, dict):
            continue

        instrument_hints = _extract_signature_instrument_hints(
            file_name=doc.file_name,
            content=doc.content,
        )
        signer_names = signature_detection.get("signer_names")
        indicators = signature_detection.get("indicators")

        evidence.append(
            {
                "document_id": doc.document_id,
                "file_name": doc.file_name,
                "status": signature_detection.get("status"),
                "confidence": signature_detection.get("confidence"),
                "has_digital_signature": bool(signature_detection.get("has_digital_signature")),
                "signing_date": signature_detection.get("signing_date"),
                "detection_source": signature_detection.get("detection_source"),
                "signer_names": signer_names if isinstance(signer_names, list) else [],
                "indicators": indicators if isinstance(indicators, list) else [],
                "instrument_hints": instrument_hints,
            }
        )

    return sorted(evidence, key=lambda row: (row.get("file_name") or "").lower())


def _build_original_documents_map(
    processed_documents: List[ProcessedDocument],
) -> Dict[str, str]:
    """Build stable, collision-safe keys for raw document injection context."""
    doc_map: Dict[str, str] = {}
    seen_names: Dict[str, int] = {}

    for doc in processed_documents:
        base_name = (doc.file_name or "Document").strip() or "Document"
        seen_names[base_name] = seen_names.get(base_name, 0) + 1
        occurrence = seen_names[base_name]

        if occurrence == 1 and base_name not in doc_map:
            key = base_name
        else:
            suffix = str(doc.document_id or occurrence)
            key = f"{base_name} [id:{suffix}]"
            while key in doc_map:
                occurrence += 1
                key = f"{base_name} [id:{suffix}-{occurrence}]"

        doc_map[key] = doc.content

    return doc_map


def _convert_to_case_analysis_result(
    structured_summaries: List[DocumentSummaryStructured], client_name: str, intake_content: str
) -> CaseAnalysisResult:
    """Convert structured summaries to legacy CaseAnalysisResult format for citation service.

    Args:
    ----
        structured_summaries: List of DocumentSummaryStructured objects
        client_name: Client name for the case
        intake_content: Intake form content

    Returns:
    -------
        CaseAnalysisResult compatible with CitationTrackingService

    """
    # Create analyzed documents from structured summaries
    analyzed_docs = []
    for summary in structured_summaries:
        # Build key_information from structured fields
        key_info_parts = []
        if summary.parties:
            key_info_parts.append(f"Parties: {', '.join(summary.parties)}")
        if summary.key_dates:
            dates_str = "; ".join([f"{kd.event} on {kd.date}" for kd in summary.key_dates])
            key_info_parts.append(f"Key Dates: {dates_str}")
        if summary.key_amounts:
            amounts_str = "; ".join([f"{ka.description}: {ka.amount}" for ka in summary.key_amounts])
            key_info_parts.append(f"Amounts: {amounts_str}")
        if summary.issues_identified:
            key_info_parts.append(f"Issues: {'; '.join(summary.issues_identified)}")

        # Build summary text
        summary_text = f"{summary.relevance_to_case}. {' '.join(key_info_parts)}"

        analyzed_doc = AnalyzedDocument(
            file_name=summary.document_name,
            document_type=summary.document_type,
            inferred_title=summary.document_name,
            summary=summary_text,
            relevance_to_case=summary.relevance_to_case,
            key_information=" | ".join(key_info_parts) if key_info_parts else "",
        )
        analyzed_docs.append(analyzed_doc)

    # Create minimal intake analysis
    intake_analysis = IntakeAnalysis(
        client_name=client_name,
        case_type="Legal Matter",
        summary=intake_content[:500] if intake_content else "",
    )

    return CaseAnalysisResult(
        intake_analysis=intake_analysis, analyzed_documents=analyzed_docs, legal_assessment=None, errors=[]
    )


JURISDICTION_CITATION_MAP = {
    "Florida": {
        "name": "Florida",
        "name_upper": "FLORIDA",
        "statute_example": "Fla. Stat. § 718.116",
        "statute_citation_prefix": "Florida Statute §",
        "statute_citation_short_prefix": "Fla. Stat. §",
        "guidance_file": "florida_guidance.md",
    },
    "New Mexico": {
        "name": "New Mexico",
        "name_upper": "NEW MEXICO",
        "statute_example": "N.M. Stat. Ann. § 57-12-2",
        "statute_citation_prefix": "N.M. Stat. Ann. §",
        "statute_citation_short_prefix": "NMSA 1978 §",
        "guidance_file": "new_mexico_guidance.md",
    },
}


def _truncate_for_prompt(value: Any, max_chars: int) -> str:
    """Trim long text for prompt safety while preserving beginning and tail context."""
    text = str(value or "")
    if len(text) <= max_chars:
        return text

    if max_chars < 120:
        return text[:max_chars]

    tail_chars = max(40, max_chars // 3)
    head_chars = max_chars - tail_chars - len("\n... [truncated] ...\n")
    if head_chars < 40:
        return text[:max_chars]

    return f"{text[:head_chars]}\n... [truncated] ...\n{text[-tail_chars:]}"


def _build_case_synthesis_payload(
    intake_content: str,
    structured_summaries: List[DocumentSummaryStructured],
) -> Dict[str, Any]:
    """Build a bounded synthesis payload from intake and document summaries."""
    summary_pool = structured_summaries[:CASE_SYNTHESIS_MAX_SUMMARIES]
    omitted_for_count_limit = max(0, len(structured_summaries) - len(summary_pool))

    condensed_summaries: List[Dict[str, Any]] = []
    total_summary_chars = 0
    omitted_for_budget = 0

    for idx, summary in enumerate(summary_pool):
        s = summary.model_dump(mode="json") if hasattr(summary, "model_dump") else summary

        key_content = _truncate_for_prompt(s.get("key_content"), CASE_SYNTHESIS_MAX_SUMMARY_TEXT_CHARS)
        executive_summary = _truncate_for_prompt(s.get("executive_summary"), 900)
        legal_significance = _truncate_for_prompt(s.get("legal_significance"), 800)
        relevance_to_case = _truncate_for_prompt(s.get("relevance_to_case"), 800)

        compact_summary = {
            "document_name": s.get("document_name"),
            "document_type": s.get("document_type"),
            "executive_summary": executive_summary,
            "key_content": key_content,
            "legal_significance": legal_significance,
            "relevance_to_case": relevance_to_case,
            "parties": (s.get("parties") or [])[:10],
            "key_quotes": [_truncate_for_prompt(item, 280) for item in (s.get("key_quotes") or [])[:5]],
            "statute_citations": (s.get("statute_citations") or [])[:8],
            "important_details": [
                _truncate_for_prompt(item, 300) for item in (s.get("important_details") or [])[:8]
            ],
            "key_dates": (s.get("key_dates") or [])[:8],
            "key_amounts": (s.get("key_amounts") or [])[:8],
        }

        estimated_chars = len(executive_summary) + len(key_content) + len(legal_significance) + len(relevance_to_case)
        if condensed_summaries and (total_summary_chars + estimated_chars > CASE_SYNTHESIS_MAX_TOTAL_SUMMARY_CHARS):
            omitted_for_budget = len(summary_pool) - idx
            break

        condensed_summaries.append(compact_summary)
        total_summary_chars += estimated_chars

    return {
        "intake_excerpt": _truncate_for_prompt(intake_content, CASE_SYNTHESIS_MAX_INTAKE_CHARS),
        "document_summaries": condensed_summaries,
        "source_counts": {
            "input_document_summaries": len(structured_summaries),
            "included_document_summaries": len(condensed_summaries),
            "omitted_for_count_limit": omitted_for_count_limit,
            "omitted_for_budget_limit": omitted_for_budget,
            "intake_chars_input": len(intake_content or ""),
            "summary_chars_included": total_summary_chars,
        },
    }


def _generate_case_analysis_summary(
    intake_content: str,
    structured_summaries: List[DocumentSummaryStructured],
    openai_client_wrapper: OpenAIClient,
    review_data: dict,
    jurisdiction: str = "Florida",
) -> dict:
    """Generate high-level case analysis from structured summaries.

    AI Call #2.5: Synthesize all document summaries into case-level insights.

    Args:
    ----
        intake_content: Raw intake form content
        structured_summaries: List of DocumentSummaryStructured objects
        openai_client_wrapper: OpenAI client for API calls
        review_data: Dictionary containing legal issue and key documents
        jurisdiction: Jurisdiction name ("Florida" or "New Mexico")

    Returns:
    -------
        Dictionary with case_summary, practice_area, key_issues, relevant_statutes, additional_details

    """
    # Build prompt with bounded intake/summaries to avoid context overflow.
    synthesis_payload = _build_case_synthesis_payload(intake_content, structured_summaries)
    summaries_json = json.dumps(synthesis_payload["document_summaries"], indent=2)
    intake_excerpt = synthesis_payload["intake_excerpt"]
    source_counts = synthesis_payload["source_counts"]
    legal_issue = review_data.get("legal_issue", "") if review_data else ""

    # Get jurisdiction-specific config
    juris_config = JURISDICTION_CITATION_MAP.get(jurisdiction, JURISDICTION_CITATION_MAP["Florida"])
    statute_format = juris_config["statute_citation_short_prefix"] + " XXX.XX"

    prompt = f"""You are a senior legal analyst. Based on the intake form and document summaries below, \
create a high-level case analysis for a matter in {jurisdiction}.

INTAKE INFORMATION:
{intake_excerpt}

{f"IDENTIFIED LEGAL ISSUE: {legal_issue}" if legal_issue else ""}

DOCUMENT SUMMARIES:
{summaries_json}

SOURCE COVERAGE METADATA:
{json.dumps(source_counts, indent=2)}

Generate a structured case analysis with:
1. **case_summary**: 120-200 word executive summary of the case, covering who, what, when, where, why
2. **practice_area**: Primary legal practice area (e.g., "Construction Law", "Consumer Protection")
3. **key_issues**: List 3-7 specific legal issues or problems identified
4. **relevant_statutes**: Identify 2-5 potentially relevant {jurisdiction} statutes with brief \
relevance notes (Format: {statute_format})
5. **additional_details**: Any other important context not captured above

OUTPUT AS STRICT JSON:
{{
  "case_summary": "...",
  "practice_area": "...",
  "key_issues": ["issue 1", "issue 2", ...],
  "relevant_statutes": [
    {{"statute": "{juris_config['statute_example']}", "relevance": "..."}},
    ...
  ],
  "additional_details": "..."
}}
"""

    try:
        model = openai_client_wrapper.get_preferred_model("document_analysis", "gpt-5.4")
        response = openai_client_wrapper.create_response(
            model=model,
            input=prompt,
            instructions="You are a senior legal analyst. Return only valid JSON.",
            reasoning_effort="medium",
        )

        analysis_json = json.loads(response["content"])
        practice_area = analysis_json.get("practice_area")
        logger.info(f"Generated case analysis for practice area: {practice_area} in {jurisdiction}")

        # Ensure all required fields are present with defaults
        return {
            "case_summary": analysis_json.get("case_summary", "No summary available"),
            "practice_area": analysis_json.get("practice_area", "General Legal Matter"),
            "key_issues": analysis_json.get("key_issues", []),
            "relevant_statutes": analysis_json.get("relevant_statutes", []),
            "additional_details": analysis_json.get("additional_details", None),
        }
    except Exception as e:
        logger.error(f"Failed to generate case analysis summary for {jurisdiction}: {e}", exc_info=True)
        # Return minimal fallback structure
        return {
            "case_summary": "Unable to generate case summary due to processing error.",
            "practice_area": "General Legal Matter",
            "key_issues": ["Analysis error - manual review required"],
            "relevant_statutes": [],
            "additional_details": f"Error: {str(e)}",
        }


async def process_case_documents(
    processed_intake: List[ProcessedDocument],
    processed_case_docs: List[ProcessedDocument],
    case_info: dict,
    review_data: dict,
    progress_callback: Optional[Callable] = None,
    jurisdiction: str = "Florida",
    skipped_documents: Optional[List[SkippedDocument]] = None,
    analysis_id: Optional[str] = None,
    supabase_client: Optional[Any] = None,
) -> ProcessingResult:
    """Decoupled document processing workflow using already extracted text."""
    start_time = time.time()
    errors = []
    case_id = case_info.get("case_id", "unknown")

    # Initialize Chunk State Manager for per-document status tracking
    chunk_state_mgr = None
    if analysis_id and supabase_client:
        chunk_state_mgr = ChunkStateManager(supabase_client, analysis_id)
        logger.info(f"[PROCESSOR] ChunkStateManager initialized for analysis {analysis_id}")

    # Initialize Diagnostic Logger if enabled
    diag_logger = None
    if DiagnosticLogger.get_enabled():
        diag_logger = DiagnosticLogger(session_id=case_id)

    logger.info(
        f"[PROCESSOR:START] [CASE:{case_id}] Starting document processing | "
        f"intake_docs={len(processed_intake)} case_docs={len(processed_case_docs)} "
        f"jurisdiction={jurisdiction}"
    )

    try:
        # 1. Initialize services
        logger.info(f"[PROCESSOR:INIT] [CASE:{case_id}] Initializing processing services")
        settings = get_settings()

        # Stage 1: Log Raw Extracted Text
        if diag_logger:
            raw_docs = {d.file_name: d.content for d in processed_case_docs}
            raw_intake = {d.file_name: d.content for d in processed_intake}
            diag_logger.log_stage("stage1_raw_text", {"case_docs": raw_docs, "intake_docs": raw_intake})

        openai_client_wrapper = OpenAIClient()
        json_processing_service = JsonProcessingService(
            client=openai_client_wrapper,
            config={"openai_max_tokens": settings.openai_max_tokens},
        )

        logger.info(f"Processing case for jurisdiction: {jurisdiction}")

        # 2. Validate inputs
        if not processed_intake:
            raise ValueError("An intake form is required for the analysis.")

        intake_content = processed_intake[0].content
        logger.info(f"Intake form loaded: {len(intake_content)} characters")

        # 3. Collect case documents for summarization analysis.
        # Intake is passed separately as context and should not be summarized as a case document.
        all_processed_docs = list(processed_case_docs)

        if not all_processed_docs:
            logger.warning("No documents provided for analysis.")

        if progress_callback:
            await progress_callback(
                f"Loaded {len(all_processed_docs)} case documents for analysis",
                [d.file_name for d in all_processed_docs],
                "extraction_complete",
                15,
            )

        # 4.3 Deduplication
        if all_processed_docs:
            logger.info(f"Checking {len(all_processed_docs)} documents for duplicates...")
            if progress_callback:
                await progress_callback("Deduplicating documents...")

            all_processed_docs = await asyncio.to_thread(_deduplicate_documents, all_processed_docs)
            logger.info(f"After deduplication: {len(all_processed_docs)} unique documents")

            await asyncio.to_thread(_detect_near_duplicates, all_processed_docs)

        # Initialize chunk_state after dedupe so tracked IDs align with analyzed documents.
        if chunk_state_mgr and all_processed_docs:
            try:
                await chunk_state_mgr.initialize_chunk_state(
                    all_processed_docs, settings.max_tokens_per_batch
                )
                logger.info(f"[PROCESSOR] Chunk state initialized for {len(all_processed_docs)} documents")
            except Exception as e:
                logger.warning(f"[PROCESSOR] Failed to initialize chunk state: {e}")

        # 4.5. Quality validation on processed documents
        quality_validator = DocumentQualityValidator()
        quality_results = []
        if all_processed_docs:
            logger.info("Running document quality validation...")
            if progress_callback:
                await progress_callback("Validating document quality...")

            for doc in all_processed_docs:
                res = await asyncio.to_thread(quality_validator.validate_document, doc)
                quality_results.append(res)

                # Update document status based on quality score if not already high
                if res.confidence_level == "low" or res.score < 5.0:
                    doc.extraction_quality = "low"
                elif res.confidence_level == "medium" or res.score < 8.0:
                    if doc.extraction_quality != "high":
                        doc.extraction_quality = "medium"
                else:
                    doc.extraction_quality = "high"

        # Aggregate quality results and create context string
        aggregated_quality_report = _aggregate_quality_results(quality_results)
        quality_context = _format_quality_context(aggregated_quality_report)

        # Pass new context to summary generation
        # Get statute recommendations early so we can use them in document summarization
        statute_context = ""
        if settings.suggest_statutes:
            try:
                recommendation_service = StatuteRecommendationService(jurisdiction=jurisdiction)
                legal_issues = []
                if review_data and "legal_issues" in review_data:
                    legal_issues = review_data.get("legal_issues", [])
                case_type = case_info.get("caseType") if case_info else None
                recommendations = await asyncio.to_thread(
                    recommendation_service.recommend_statutes,
                    case_facts=intake_content[:2000],
                    legal_issues=legal_issues,
                    case_type=case_type,
                    limit=5,
                )
                if recommendations:
                    statute_context = recommendation_service.get_statute_context_for_prompt(
                        recommendations, max_statutes=5
                    )
                    logger.info(
                        f"Generated {len(recommendations)} statute recommendations for document analysis",
                        extra={"recommendation_count": len(recommendations)},
                    )
            except Exception as e:
                logger.warning(f"Failed to generate statute recommendations: {e}", exc_info=True)

        structured_summaries: List[DocumentSummaryStructured] = []
        if all_processed_docs:
            if progress_callback:
                await progress_callback(
                    "Analyzing extracted content...",
                    [d.file_name for d in all_processed_docs],
                    "document_analysis",
                    15,
                    stage={"id": "doc_summary", "name": "Document Analysis", "status": "active", "progress": 10}
                )
            structured_summaries, summary_errors = await _generate_document_summaries(
                intake_content,
                all_processed_docs,
                openai_client_wrapper,
                json_processing_service,  # Pass the instance here
                review_data,  # Pass through
                progress_callback,
                statute_context,  # NEW: Pass statute context
                jurisdiction=jurisdiction,  # NEW: Pass jurisdiction
                chunk_state_mgr=chunk_state_mgr,  # NEW: For per-doc status tracking
            )
            errors.extend(summary_errors)

            if progress_callback:
                await progress_callback(
                    "Document analysis complete.",
                    [],
                    "document_analysis",
                    20,
                    stage={"id": "doc_summary", "name": "Document Analysis", "status": "completed", "progress": 100}
                )
        else:
            logger.info("No case documents provided; skipping document summary stage")
            if progress_callback:
                await progress_callback(
                    "No case documents uploaded. Skipping document analysis stage.",
                    [],
                    "document_analysis",
                    20,
                    stage={"id": "doc_summary", "name": "Document Analysis", "status": "skipped", "progress": 100}
                )

        # Stage 3: Log Per-Document Summaries
        if diag_logger:
            diag_logger.log_stage("stage3_document_summaries", [s.model_dump() for s in structured_summaries])

        # ========================================================================
        # SYNTHESIS GATE CHECK
        # ========================================================================
        # Check if we can proceed to synthesis (all docs completed or skipped)
        if chunk_state_mgr:
            can_proceed = await chunk_state_mgr.can_proceed_to_synthesis()
            if not can_proceed:
                failed_docs = await chunk_state_mgr.get_failed_documents()
                await chunk_state_mgr.update_phase("awaiting_recovery")

                logger.warning(
                    f"[SYNTHESIS_GATE] Cannot proceed - {len(failed_docs)} documents need attention"
                )

                if progress_callback:
                    await progress_callback(
                        f"Waiting for {len(failed_docs)} failed documents to be addressed",
                        [],
                        "awaiting_recovery",
                        20,
                        chunk_status={
                            "type": "chunk_complete_with_errors",
                            "completed": len(structured_summaries),
                            "failed": len(failed_docs),
                            "failed_docs": [
                                {"id": d.get("id"), "name": d.get("name"), "error": d.get("error"), "error_type": d.get("error_type")}
                                for d in failed_docs
                            ]
                        }
                    )

                # Return partial results - frontend will show recovery modal
                return ProcessingResult(
                    document_summaries=[],
                    status="awaiting_recovery",
                    errors=errors,
                    processing_time=time.time() - start_time,
                )
            else:
                await chunk_state_mgr.update_phase("synthesis")
                logger.info("[SYNTHESIS_GATE] All documents addressed, proceeding to synthesis")

        # ========================================================================
        # CASE SYNTHESIS STAGE (25-40%)
        # ========================================================================
        if progress_callback:
            await progress_callback(
                "Synthesizing case analysis...",
                [],
                "case_synthesis",
                25,
                stage={"id": "case_synthesis", "name": "Extracting Facts", "status": "active", "progress": 0}
            )

        # 5.5. AI Call #2.5: Generate case-level analysis summary (with heartbeats)
        logger.info("AI Call #2.5: Generating case-level analysis summary...")
        try:
            # Use heartbeat wrapper to prevent SSE timeout during long GPT call
            case_analysis_dict = await _run_with_heartbeat(
                _generate_case_analysis_summary,
                progress_callback,
                "case_synthesis",
                25,
                10.0,
                intake_content,
                structured_summaries,
                openai_client_wrapper,
                review_data,
                jurisdiction=jurisdiction,
            )
            logger.info("Case-level analysis summary generated successfully")
        except Exception as e:
            logger.error(f"Case synthesis failed: {e}", exc_info=True)
            if progress_callback:
                await progress_callback(
                    f"Error in case synthesis: {str(e)[:100]}",
                    [],
                    "error",
                    25,
                    stage={"id": "case_synthesis", "name": "Extracting Facts", "status": "failed", "progress": 0}
                )
            raise  # Re-raise to fail the analysis properly

        if progress_callback:
            await progress_callback(
                "Case synthesis complete.",
                [],
                "case_synthesis",
                35,
                stage={"id": "case_synthesis", "name": "Extracting Facts", "status": "completed", "progress": 100}
            )

        # Stage 4: Log Case Synthesis
        if diag_logger:
            diag_logger.log_stage("stage4_case_synthesis", case_analysis_dict)
        client_name_for_case = (
            (case_info or {}).get("client_name") or (case_info or {}).get("clientName") or "Client"
        )
        _convert_to_case_analysis_result(structured_summaries, client_name_for_case, intake_content)

        document_summaries_json_str = json.dumps([s.model_dump() for s in structured_summaries], indent=2)

        # Extract information for downstream letter/chat generation
        attorney_name = case_info.get("attorneyName") if case_info else None
        firm_name = case_info.get("firmName") if case_info else None
        contact_phone = case_info.get("contactPhone") if case_info else None
        contact_email = case_info.get("contactEmail") if case_info else None
        confirmed_qa_pairs = review_data.get("confirmed_qa_pairs", []) if review_data else []

        # ========================================================================
        # COVERAGE & DEADLINE EXTRACTION STAGE (40-55%)
        # ========================================================================
        if progress_callback:
            await progress_callback(
                "Checking legal coverage and extracting deadlines...",
                [],
                "deadline_extraction",
                40,
                stage={"id": "legal_issues", "name": "Legal Issues", "status": "active", "progress": 0}
            )

        # Check corpus coverage for this case
        coverage_warnings = []
        if settings.corpus_coverage_warnings:
            try:
                coverage_service = CorpusCoverageService()
                legal_issues = []
                if review_data and "legal_issues" in review_data:
                    legal_issues = review_data.get("legal_issues", [])

                case_type = case_info.get("caseType") if case_info else None

                coverage_result = await asyncio.to_thread(
                    coverage_service.analyze_coverage,
                    case_type=case_type,
                    case_facts=intake_content[:2000],
                    legal_issues=legal_issues,
                    jurisdiction=jurisdiction,
                )

                if coverage_result["warnings"]:
                    coverage_warnings = coverage_result["warnings"]
                    for warning in coverage_warnings:
                        logger.warning(f"Corpus coverage: {warning}")

                if not coverage_result["is_covered"]:
                    logger.warning(
                        f"Case type may be outside {jurisdiction} Legal Corpus coverage. "
                        f"Detected areas: {coverage_result.get('unsupported_areas', [])}"
                    )
            except Exception as e:
                logger.warning(f"Failed to analyze corpus coverage: {e}", exc_info=True)

        if progress_callback:
            await progress_callback(
                "Extracting critical deadlines...",
                [],
                "deadline_extraction",
                45,
            )

        # NEW: Extract deadlines using corpus and documents
        deadline_context = ""
        try:
            from legal_portal.services.deadline_extraction_service import DeadlineExtractionService

            deadline_service = DeadlineExtractionService(jurisdiction=jurisdiction)
            deadlines = deadline_service.extract_deadlines(
                structured_summaries=structured_summaries,
                case_type=case_analysis_dict.get("practice_area", "General"),
                case_facts=intake_content[:2000],
            )

            if deadlines:
                deadline_context = deadline_service.format_deadlines_for_prompt(deadlines)
                logger.info(
                    f"Extracted {len(deadlines)} deadlines for {jurisdiction}: "
                    f"{sum(1 for d in deadlines if d.urgency == 'critical')} critical, "
                    f"{sum(1 for d in deadlines if d.urgency == 'important')} important"
                )
        except Exception as e:
            logger.warning(f"Failed to extract deadlines for {jurisdiction}: {e}", exc_info=True)

        # Append deadline context to statute context for prompt
        if deadline_context:
            statute_context = (
                f"{statute_context}\n\n{deadline_context}" if statute_context else deadline_context
            )

        if progress_callback:
            await progress_callback(
                "Deadlines and coverage analysis complete.",
                [],
                "deadline_extraction",
                50,
                stage={"id": "legal_issues", "name": "Legal Issues", "status": "completed", "progress": 100}
            )

        # Check if CLIO context is available in review_data
        clio_context_str = ""
        if review_data.get("clio_matter_context"):
            from legal_portal.services.clio_context_builder import ClioContextBuilder

            builder = ClioContextBuilder()
            clio_context_str = builder.format_clio_context_for_prompt(review_data["clio_matter_context"])
            logger.info("Using CLIO matter context for enhanced letter generation")

        multi_stage_error = None
        fact_matrix = None
        legal_issue_map = None
        letter_structure = None

        # ========================================================================
        # MULTI-STAGE DEEP ANALYSIS (55-75%)
        # ========================================================================
        if progress_callback:
            await progress_callback(
                "Starting deep legal analysis...",
                [],
                "deep_analysis",
                55,
                stage={"id": "deep_analysis", "name": "Deep Analysis", "status": "active", "progress": 0}
            )

        # Multi-stage analysis is REQUIRED for letter generation
        # Always run it - no feature flag
        elapsed = time.time() - start_time
        logger.info(
            f"[PROCESSOR:MULTISTAGE] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Starting multi-stage analysis | jurisdiction={jurisdiction} summaries={len(structured_summaries)}"
        )

        try:
            statute_service = StatuteRecommendationService(jurisdiction=jurisdiction)
            multi_stage_analyzer = MultiStageAnalyzer(
                openai_client=openai_client_wrapper, statute_service=statute_service
            )
            legal_issues_hint = []
            if isinstance((review_data or {}).get("legal_issues"), list):
                legal_issues_hint = [
                    str(issue).strip() for issue in review_data.get("legal_issues", []) if str(issue).strip()
                ]
            if not legal_issues_hint and (review_data or {}).get("legal_issue"):
                legal_issues_hint = [str(review_data.get("legal_issue")).strip()]

            registry_service = DocumentRegistryService()
            all_docs = all_processed_docs + processed_intake

            # --- Load existing registries or build initial ones ---
            # Documents uploaded after Phase 3 carry metadata.registry.
            # Legacy documents (pre-migration) get a fresh initial registry.
            registry_by_name: Dict[str, Dict[str, Any]] = {}
            for pdoc in all_docs:
                fn = (pdoc.file_name or "").strip()
                if not fn:
                    continue
                norm = registry_service._normalize_name(fn)
                if norm in registry_by_name:
                    continue
                if pdoc.registry:
                    reg = pdoc.registry
                    # Ensure document_id is set (defensive for legacy registry data)
                    if not reg.get("document_id") and pdoc.document_id:
                        reg["document_id"] = pdoc.document_id
                    registry_by_name[norm] = reg
                else:
                    registry_by_name[norm] = registry_service.build_initial_registry(pdoc)

            # --- Cross-document enrichment (Stage 2) ---
            # Detect email threads, sequential photos, contract families.
            # Runs before AI so multi-stage analysis can see relationships.
            cross_doc_registries = list(registry_by_name.values())
            cross_doc_registries = registry_service.enrich_cross_document(
                cross_doc_registries, all_docs
            )
            # Update registry_by_name with enriched entries
            for reg in cross_doc_registries:
                norm = registry_service._normalize_name(reg.get("document_name", ""))
                if norm:
                    registry_by_name[norm] = reg

            # --- Enrich with AI summaries (Stage 4, pass 1) ---
            summary_by_name = {
                registry_service._normalize_name(s.document_name): s.model_dump(mode="json")
                for s in (structured_summaries or [])
                if (s.document_name or "").strip()
            }
            for norm, summary in summary_by_name.items():
                if norm in registry_by_name:
                    registry_by_name[norm] = registry_service.enrich_with_ai(
                        registry_by_name[norm], summary
                    )

            document_registry_seed = list(registry_by_name.values())

            if progress_callback:
                await progress_callback(
                    "Running multi-stage legal analysis...",
                    [],
                    "deep_analysis",
                    60,
                )

            multi_stage_start = time.time()
            signature_evidence = _build_signature_evidence_for_gap_analysis(all_docs)
            multi_stage_result = await multi_stage_analyzer.analyze_case(
                intake_content=intake_content,
                document_summaries=structured_summaries,
                progress_callback=progress_callback,
                case_type=case_analysis_dict.get("practice_area"),
                legal_issues=legal_issues_hint or None,
                jurisdiction=jurisdiction,
                diag_logger=diag_logger,
                signature_evidence=signature_evidence,
                document_registry=document_registry_seed,
            )
            multi_stage_duration = time.time() - multi_stage_start

            fact_matrix = multi_stage_result.fact_matrix
            legal_issue_map = multi_stage_result.issue_map
            letter_structure = multi_stage_result.letter_structure

            # --- Enrich with key document flags (Stage 4, pass 2) ---
            key_docs_by_name = {
                registry_service._normalize_name(k.document_name): k.model_dump(mode="json")
                for k in ((fact_matrix.key_documents if fact_matrix else []) or [])
                if (k.document_name or "").strip()
            }
            for norm, key_doc in key_docs_by_name.items():
                if norm in registry_by_name:
                    reg = registry_by_name[norm]
                    reg["is_key_document"] = True
                    reg["key_document_significance"] = key_doc.get("significance")

            # --- Persist enriched registries back to DB ---
            if supabase_client:
                for norm, reg in registry_by_name.items():
                    doc_id = reg.get("document_id")
                    if doc_id:
                        try:
                            registry_service.persist_to_document(
                                doc_id, reg, supabase_client
                            )
                        except Exception as persist_err:
                            logger.warning(
                                f"Failed to persist enriched registry for {doc_id}: {persist_err}"
                            )

            # Attach original documents to multi-stage result for letter generation
            multi_stage_result.original_documents = _build_original_documents_map(all_docs)
            multi_stage_result.document_registry = list(registry_by_name.values())

            elapsed = time.time() - start_time
            logger.info(
                f"[PROCESSOR:MULTISTAGE] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
                f"Multi-stage analysis complete | duration={multi_stage_duration:.1f}s "
                f"timeline_events={len(fact_matrix.timeline)} primary_issues={len(legal_issue_map.primary_issues)} "
                f"letter_style={letter_structure.style}"
            )

            if progress_callback:
                await progress_callback(
                    "Deep analysis complete.",
                    [],
                    "deep_analysis",
                    75,
                    stage={"id": "deep_analysis", "name": "Deep Analysis", "status": "completed", "progress": 100}
                )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"[PROCESSOR:MULTISTAGE] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
                f"Multi-stage analysis FAILED | error_type={type(e).__name__} error={str(e)}",
                exc_info=True
            )
            multi_stage_result = None
            multi_stage_error = str(e)
            # Surface the error so it's visible in results
            if progress_callback:
                await progress_callback(
                    f"⚠️ Advanced analysis failed: {str(e)[:100]}",
                    [],
                    "deep_analysis",
                    75,
                    stage={"id": "deep_analysis", "name": "Deep Analysis", "status": "failed", "progress": 100}
                )

        # Derive opposing parties from fact matrix
        opposing_parties: List[Party] = []
        if fact_matrix:
            for party in fact_matrix.parties:
                role_label = (party.role or "").lower()
                if party.is_opposing_party or "opposing" in role_label:
                    opposing_parties.append(party)
            if not opposing_parties:
                for party in fact_matrix.parties:
                    role_label = (party.role or "").lower()
                    if "client" not in role_label and "attorney" not in role_label:
                        opposing_parties.append(party)

        multi_stage_result_dict = multi_stage_result.model_dump(mode="json") if multi_stage_result else None

        # ========================================================================
        # LETTER STRUCTURE & FINALIZATION (80-100%)
        # ========================================================================
        if progress_callback:
            await progress_callback(
                "Preparing letter structure...",
                [],
                "letter_structure",
                80,
                stage={"id": "letter_structure", "name": "Letter Structure", "status": "active", "progress": 0}
            )

        # 9. Calculate processing time
        processing_time = time.time() - start_time

        if progress_callback:
            await progress_callback(
                "Finalizing analysis results...",
                [],
                "letter_structure",
                90,
                stage={"id": "letter_structure", "name": "Letter Structure", "status": "completed", "progress": 100}
            )

        logger.info(
            f"Successfully completed document processing in {processing_time:.2f}s (letters deferred)"
        )

    # Track which models were used for each operation
        models_used = {
            "document_analysis": openai_client_wrapper.get_preferred_model("document_analysis", "gpt-5.4"),
            "letter_generation": openai_client_wrapper.get_preferred_model("letter_generation", "gpt-5.4"),
            "case_chat": openai_client_wrapper.get_preferred_model("case_chat", "gpt-5-mini"),
            "multi_stage_analysis": openai_client_wrapper.get_preferred_model(
                "multi_stage_analysis", "gpt-5.4"
            ),
        }

        artifacts_payload = {
            "statute_context": statute_context,
            "deadline_context": deadline_context,
            "clio_matter_context": clio_context_str,
            "quality_context": quality_context,
            "attorney_name": attorney_name,
            "firm_name": firm_name,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "confirmed_qa_pairs": confirmed_qa_pairs,
            "document_summaries_json": document_summaries_json_str,
            "models_used": models_used,
            "jurisdiction": jurisdiction,  # Include jurisdiction in artifacts
            "multi_stage_error": multi_stage_error,  # Include error if multi-stage failed
            "document_registry_count": len(
                (multi_stage_result.document_registry if multi_stage_result else []) or []
            ),
        }

        result = ProcessingResult(
            main_letter="",
            main_letter_with_citations="",
            document_summaries=json.dumps([s.model_dump() for s in structured_summaries], indent=2),
            case_analysis=json.dumps(case_analysis_dict, indent=2),
            quality_report=[q.model_dump() for q in quality_results] if quality_results else None,
            status="completed",
            processing_time_seconds=processing_time,
            intake_content=intake_content,
            document_count=len(all_processed_docs),
            errors=errors,
            warnings=coverage_warnings,
            citation_summary=None,
            citation_appendix=None,
            citation_map=None,
            statute_validation=None,
            qa_warnings=None,
            artifacts=artifacts_payload,
            opposing_parties=opposing_parties,
            multi_stage_result=multi_stage_result_dict,
            generated_letters={},
            processed_documents=all_processed_docs,  # Return analyzed (deduped) case documents
            skipped_documents=skipped_documents or [],  # NEW: Include skipped documents
        )

        # ========================================================================
        # ANALYSIS COMPLETE (100%)
        # ========================================================================
        
        # Flush any pending chunk state updates
        if chunk_state_mgr:
            try:
                await chunk_state_mgr.finalize()
            except Exception as e:
                logger.warning(f"[PROCESSOR] Failed to finalize chunk state: {e}")
        
        if progress_callback:
            await progress_callback(
                "Analysis complete!",
                [],
                "completed",
                100,
            )

        logger.info(
            f"[PROCESSOR:COMPLETE] [CASE:{case_id}] [ELAPSED:{processing_time:.1f}s] "
            f"Document processing completed | doc_count={len(all_processed_docs)} "
            f"summaries={len(structured_summaries)} multi_stage={'SUCCESS' if multi_stage_result else 'FAILED'}"
        )
        return result

    except ValueError as e:
        # Known validation errors
        logger.error(f"Validation error during document processing: {e}")
        processing_time = time.time() - start_time

        error = ProcessingError(
            source="main_processor",
            error_type="ValidationError",
            error_message=str(e),
        )
        errors.append(error)
        
        # Flush any pending chunk state updates
        if chunk_state_mgr:
            try:
                await chunk_state_mgr.finalize()
            except Exception as flush_error:
                logger.warning(f"[PROCESSOR] Failed to finalize chunk state on error: {flush_error}")

        # Emit error progress so frontend knows
        if progress_callback:
            await progress_callback(
                f"Analysis failed: {str(e)[:100]}",
                [],
                "error",
                0,
            )

        return ProcessingResult(
            main_letter="<html><body><p>Processing failed due to validation error.</p></body></html>",
            document_summaries="",
            case_analysis=json.dumps(
                {
                    "case_summary": "Processing failed - validation error",
                    "practice_area": "Unknown",
                    "key_issues": ["Processing error"],
                    "relevant_statutes": [],
                    "additional_details": str(e),
                }
            ),
            status="failed",
            processing_time_seconds=processing_time,
            document_count=0,
            errors=errors,
        )

    except Exception as e:
        # Unexpected errors
        logger.exception(f"Unexpected error during document processing: {e}")
        processing_time = time.time() - start_time

        error = ProcessingError(
            source="main_processor",
            error_type=type(e).__name__,
            error_message=str(e),
        )
        errors.append(error)
        
        # Flush any pending chunk state updates
        if chunk_state_mgr:
            try:
                await chunk_state_mgr.finalize()
            except Exception as flush_error:
                logger.warning(f"[PROCESSOR] Failed to finalize chunk state on error: {flush_error}")

        # Emit error progress so frontend knows
        if progress_callback:
            await progress_callback(
                f"Unexpected error: {str(e)[:100]}",
                [],
                "error",
                0,
            )

        return ProcessingResult(
            main_letter="<html><body><p>Processing failed due to an unexpected error.</p></body></html>",
            document_summaries="",
            case_analysis=json.dumps(
                {
                    "case_summary": "Processing failed - unexpected error",
                    "practice_area": "Unknown",
                    "key_issues": ["Processing error"],
                    "relevant_statutes": [],
                    "additional_details": str(e),
                }
            ),
            status="failed",
            processing_time_seconds=processing_time,
            document_count=0,
            errors=errors,
        )


def _build_quality_context(case_documents: list) -> str:
    """Format document quality metadata for AI context."""
    if not case_documents:
        return "No case documents provided."

    quality_notes = []
    for doc in case_documents:
        quality = doc.extraction_quality or "unknown"
        method = doc.extraction_method or "unknown"
        quality_notes.append(f"- {doc.file_name}: Quality={quality}, Method={method}")
    return "\n".join(quality_notes)


def _is_image_document(doc) -> bool:
    """Check if a document is an image based on file extension."""
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}
    file_ext = os.path.splitext(doc.file_name)[1].lower()
    return file_ext in image_extensions


def _deduplicate_documents(documents: List[Any]) -> List[Any]:
    """Remove documents with identical content using SHA256 hash."""
    seen_hashes = {}
    unique_docs = []

    for doc in documents:
        # Hash the actual content (works for both text and binary)
        try:
            if isinstance(doc.content, bytes):
                content_hash = hashlib.sha256(doc.content).hexdigest()
            else:
                content_hash = hashlib.sha256(doc.content.encode("utf-8", errors="ignore")).hexdigest()
        except Exception as e:
            logger.warning(f"Could not hash {doc.file_name}: {e}. Including anyway.")
            unique_docs.append(doc)
            continue

        if content_hash not in seen_hashes:
            seen_hashes[content_hash] = doc.file_name
            unique_docs.append(doc)
        else:
            logger.warning(
                f"Duplicate detected: '{doc.file_name}' is identical to '{seen_hashes[content_hash]}'. Skipping."  # noqa: E501
            )

    return unique_docs


def _detect_near_duplicates(documents: List[Any]) -> None:
    """Log warnings about potentially duplicate files based on filename similarity."""
    filenames = [doc.file_name for doc in documents]
    for i, name1 in enumerate(filenames):
        for _j, name2 in enumerate(filenames[i + 1 :], start=i + 1):
            # Check filename similarity (ignoring extension)
            base1 = os.path.splitext(name1)[0].lower()
            base2 = os.path.splitext(name2)[0].lower()
            similarity = SequenceMatcher(None, base1, base2).ratio()

            settings = get_settings()
            if similarity > settings.duplicate_similarity_threshold:  # Configurable threshold
                logger.warning(
                    f"Possible near-duplicate files detected: '{name1}' and '{name2}' "
                    f"(similarity: {similarity:.1%}). Both will be processed."
                )


def _normalize_document_content(content: Any) -> str:
    """Normalize document content to text for prompt construction."""
    if content is None:
        return ""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore")
    return str(content)


def _chunk_document_content_for_prompt(content: str, max_chars: int = PROMPT_MAX_DOC_CHARS) -> str:
    """Chunk long content into bounded excerpts for prompt stability."""
    if len(content) <= max_chars:
        return content

    first_len = max_chars // PROMPT_LONG_DOC_CHUNKS
    middle_len = max_chars // PROMPT_LONG_DOC_CHUNKS
    last_len = max_chars - first_len - middle_len

    middle_start = max(0, (len(content) - middle_len) // 2)
    middle_end = middle_start + middle_len

    first_excerpt = content[:first_len]
    middle_excerpt = content[middle_start:middle_end]
    last_excerpt = content[-last_len:]

    excerpt_chars = len(first_excerpt) + len(middle_excerpt) + len(last_excerpt)
    omitted_chars = max(0, len(content) - excerpt_chars)

    return (
        f"[TRUNCATED_DOCUMENT total_chars={len(content)} excerpt_chars={excerpt_chars} "
        f"omitted_chars≈{omitted_chars}]\n"
        "[EXCERPT 1/3 - BEGINNING]\n"
        f"{first_excerpt}\n"
        "[EXCERPT 2/3 - MIDDLE]\n"
        f"{middle_excerpt}\n"
        "[EXCERPT 3/3 - END]\n"
        f"{last_excerpt}"
    )


def _format_registry_context(doc: Any) -> str:
    """Build a compact prior-classification block from a document's registry.

    Gives the AI model context about preliminary classification, quick facts,
    signature status, and any attorney input so it can refine rather than
    classify from scratch.
    """
    registry = getattr(doc, "registry", None) or {}
    enrichment = getattr(doc, "attorney_enrichment", None) or {}
    if not registry and not enrichment:
        return ""

    parts: list[str] = []

    # Pre-classified type (heuristic or prior AI)
    doc_type = enrichment.get("document_type_override") or registry.get("document_type")
    if doc_type:
        confidence = registry.get("document_type_confidence", "")
        source = registry.get("document_type_source", "")
        parts.append(f"pre_classified_type={doc_type} (confidence={confidence}, source={source})")

    instrument = registry.get("primary_instrument")
    if instrument:
        parts.append(f"instrument={instrument}")

    # Quick facts (prefer AI > raw)
    facts_ai = registry.get("quick_facts_ai") or {}
    facts_raw = registry.get("quick_facts_raw") or {}
    dates = facts_ai.get("dates") or facts_raw.get("dates") or []
    amounts = facts_ai.get("amounts") or facts_raw.get("amounts") or []
    if dates:
        parts.append(f"dates={dates[:4]}")
    if amounts:
        parts.append(f"amounts={amounts[:4]}")

    # Signature status
    sig_expected = registry.get("signature_expected")
    exec_status = registry.get("execution_status")
    if sig_expected is not None:
        parts.append(f"signature_expected={sig_expected}; signed={exec_status or 'unknown'}")

    # System summary
    summary = registry.get("system_summary")
    if summary:
        parts.append(f"summary=\"{summary[:120]}\"")

    # Attorney overrides — these are authoritative
    attorney_parts: list[str] = []
    if enrichment.get("document_type_override"):
        attorney_parts.append(f"type_override={enrichment['document_type_override']}")
    if enrichment.get("attorney_notes"):
        attorney_parts.append(f"notes=\"{str(enrichment['attorney_notes'])[:100]}\"")
    if enrichment.get("key_facts") and isinstance(enrichment["key_facts"], dict):
        facts_str = ", ".join(f"{k}={v}" for k, v in list(enrichment["key_facts"].items())[:5])
        attorney_parts.append(f"confirmed_facts=[{facts_str}]")

    if not parts and not attorney_parts:
        return ""

    lines = ["[PRIOR_CLASSIFICATION: " + "; ".join(parts) + "]"] if parts else []
    if attorney_parts:
        lines.append("[ATTORNEY_INPUT: " + "; ".join(attorney_parts) + "]")

    return "\n".join(lines) + "\n"


def _format_single_document_with_metadata(doc: Any, document_index: Optional[int] = None) -> str:
    """Format a single document block for AI prompt input."""
    quality_flag = ""
    extraction_quality = getattr(doc, "extraction_quality", None)
    if extraction_quality == "low":
        quality_flag = " [⚠️ LOW QUALITY - may have extraction errors]"
    elif extraction_quality == "medium":
        quality_flag = " [⚠️ MEDIUM QUALITY - verify critical facts]"

    doc_type_flag = " [📷 IMAGE FILE]" if _is_image_document(doc) else ""

    signature_flag = ""
    signature_data = getattr(doc, "signature_detection", None) or {}
    signature_status = signature_data.get("status")
    if signature_status:
        signature_confidence = signature_data.get("confidence", "none")
        signature_markers = signature_data.get("signature_marker_count", 0)
        signature_flag = (
            f" [SIGNATURE_STATUS={signature_status}; "
            f"confidence={signature_confidence}; markers={signature_markers}]"
        )
        signing_date = signature_data.get("signing_date")
        if signing_date:
            signature_flag += f" [SIGNING_DATE={signing_date}]"

    # Prior registry context (pre-classification, quick facts, attorney input)
    registry_context = _format_registry_context(doc)

    content = _normalize_document_content(getattr(doc, "content", ""))
    content_preview = _chunk_document_content_for_prompt(content)
    doc_name = getattr(doc, "file_name", "Unknown document")
    label = f"Document {document_index}" if document_index is not None else "Document"

    return f"\n--- {label}: {doc_name}{quality_flag}{doc_type_flag}{signature_flag} ---\n{registry_context}{content_preview}\n"


def _format_documents_with_metadata(case_documents: list) -> str:
    """Format documents with quality flags for AI analysis."""
    return "".join(
        _format_single_document_with_metadata(doc, document_index=i)
        for i, doc in enumerate(case_documents, start=1)
    )


def _format_quality_context(quality_results: dict) -> str:
    """Format quality results for AI context."""
    lines = [
        f"Overall Confidence: {quality_results['overall_confidence']}",
        f"Average Quality Score: {quality_results['overall_average_score']:.1f}/10",
        "",
    ]

    if quality_results["low_quality_documents_count"] > 0:
        lines.append("⚠️ DOCUMENTS WITH QUALITY ISSUES:")
        for doc_name, result in quality_results["batch_results"].items():
            if result["confidence_level"] == "low":
                lines.append(f"- {doc_name}: Score {result['score']:.1f}/10")
                if result["issues"]:
                    lines.append(f"  Issues: {', '.join(result['issues'])}")
        lines.append("")

    return "\n".join(lines)


def _aggregate_quality_results(results: List[QualityScore]) -> Dict[str, Any]:
    """Aggregate a list of individual document quality results into a summary dictionary."""
    if not results:
        return {
            "overall_confidence": "high",
            "overall_average_score": 10.0,
            "low_quality_documents_count": 0,
            "batch_results": {},
        }

    total_score = sum(r.score for r in results)
    average_score = total_score / len(results) if results else 0
    low_quality_docs = [r for r in results if r.score < 7.0]

    batch_results = {r.document: r.model_dump() for r in results}

    confidence = "high"
    if average_score < 5.0:
        confidence = "low"
    elif average_score < 8.0:
        confidence = "medium"

    return {
        "overall_confidence": confidence,
        "overall_average_score": average_score,
        "low_quality_documents_count": len(low_quality_docs),
        "batch_results": batch_results,
    }


def _estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 characters."""
    return len(text) // 4


def _create_smart_batches(documents: list, max_tokens_per_batch: int | None = None) -> list:
    """Group documents into batches based on token estimates.

    Args:
    ----
        documents: List of ProcessedDocument objects
        max_tokens_per_batch: Maximum tokens per batch (uses config default if not provided)

    Returns:
    -------
        List of document batches

    """
    # Use configured default if not specified
    if max_tokens_per_batch is None:
        max_tokens_per_batch = get_settings().max_tokens_per_batch

    batches = []
    current_batch = []
    current_tokens = 0
    max_docs_per_batch = PROMPT_MAX_DOCS_PER_BATCH  # Hard limit to prevent API timeouts

    for doc in documents:
        # Estimate based on actual prompt-rendered content, not raw full-text content.
        doc_tokens = _estimate_tokens(_format_single_document_with_metadata(doc))

        # Start new batch if: would exceed token limit OR already have 10 docs
        if (current_tokens + doc_tokens > max_tokens_per_batch and current_batch) or len(
            current_batch
        ) >= max_docs_per_batch:
            batches.append(current_batch)
            current_batch = [doc]
            current_tokens = doc_tokens
        else:
            current_batch.append(doc)
            current_tokens += doc_tokens

    # Don't forget the last batch
    if current_batch:
        batches.append(current_batch)

    return batches


def _estimate_summary_prompt_tokens(
    intake_content: str,
    documents: List[Any],
    review_data: dict,
    statute_context: str,
    jurisdiction: str,
    batch_num: int = 1,
    total_batches: int = 1,
) -> int:
    """Estimate tokens for the full summary prompt for a given document batch."""
    prompt = _build_summary_prompt(
        intake_content=intake_content,
        documents=documents,
        review_data=review_data,
        is_batch=True,
        batch_info=(batch_num, total_batches),
        statute_context=statute_context,
        jurisdiction=jurisdiction,
    )
    return _estimate_tokens(prompt)


def _create_prompt_aware_batches(
    documents: List[Any],
    intake_content: str,
    review_data: dict,
    statute_context: str,
    jurisdiction: str,
    max_tokens_per_batch: int,
) -> List[List[Any]]:
    """Create batches using full prompt token estimates (includes intake + fixed instructions)."""
    if not documents:
        return []

    batches: List[List[Any]] = []
    current_batch: List[Any] = []

    for doc in documents:
        candidate_batch = current_batch + [doc]
        candidate_tokens = _estimate_summary_prompt_tokens(
            intake_content=intake_content,
            documents=candidate_batch,
            review_data=review_data,
            statute_context=statute_context,
            jurisdiction=jurisdiction,
        )

        should_split = (
            bool(current_batch)
            and (
                candidate_tokens > max_tokens_per_batch
                or len(current_batch) >= PROMPT_MAX_DOCS_PER_BATCH
            )
        )
        if should_split:
            batches.append(current_batch)
            current_batch = [doc]
        else:
            current_batch = candidate_batch

    if current_batch:
        batches.append(current_batch)

    return batches


async def _generate_document_summaries(
    intake_content: str,
    case_documents: List[Any],
    openai_client_wrapper: OpenAIClient,
    json_processing_service: JsonProcessingService,  # Add this parameter
    review_data: dict,  # NEW
    progress_callback: Optional[Callable] = None,
    statute_context: str = "",  # NEW: Pass statute recommendations
    jurisdiction: str = "Florida",  # NEW: Pass jurisdiction
    chunk_state_mgr: Optional[ChunkStateManager] = None,  # NEW: For per-doc status tracking
) -> Tuple[List[Dict[str, Any]], List[ProcessingError]]:
    """AI Call #1: Generate structured JSON summaries of case documents.

    Args:
    ----
        intake_content: Extracted text from intake form
        case_documents: List of ProcessedDocument objects (can be empty)
        openai_client_wrapper: An instance of the custom OpenAIClient wrapper.
        json_processing_service: Service for processing JSON responses from AI
        review_data: Dictionary containing key documents and legal issue from review step
        progress_callback: Optional callback function for progress updates
        statute_context: Formatted statute recommendations
        jurisdiction: Jurisdiction name ("Florida" or "New Mexico")

    Returns:
    -------
        Dictionary with 'summaries' (list of DocumentSummaryStructured) and 'raw_json' (string)

    """
    errors = []

    # Handle case with no case documents: request intake-only structured analysis.
    if not case_documents:
        prompt = f"""You are a legal document analyst. \
Given the client intake information below, provide a structured JSON analysis for a matter in {jurisdiction}.

INTAKE INFORMATION:
{intake_content}

---
OUTPUT FORMAT (STRICT JSON):
{{
  "case_overview": "Brief description of the case",
  "parties": ["Party 1", "Party 2"],
  "key_dates": [
    {{"date": "YYYY-MM-DD", "event": "Event description", "source_document": "Intake Form"}}
  ],
  "key_amounts": [
    {{"amount": "$XXX,XXX.XX", "description": "What it represents", "source_document": "Intake Form"}}
  ],
  "legal_issues": ["Issue 1", "Issue 2"],
  "information_gaps": ["What additional documents would be helpful"]
}}

Return ONLY valid JSON, no markdown code blocks.
"""
        response_json, batch_errors = await json_processing_service.process_documents_to_json(prompt)
        errors.extend(batch_errors)
        parsed_data = _clean_and_parse_json(response_json) if response_json else None
        if not parsed_data:
            return [], errors

        validated_summaries = []
        for doc_data in parsed_data.get("documents", []):
            try:
                validated_summaries.append(DocumentSummaryStructured(**doc_data))
            except Exception as e:
                logger.warning(
                    f"Failed to validate document summary for {doc_data.get('document_name', 'unknown')}: {e}"
                )
        return validated_summaries, errors

    total_docs = len(case_documents)
    all_summaries = []
    processed_count = 0
    tracking_ids = build_document_tracking_ids(case_documents)
    doc_tracking_id_map = {id(doc): tracking_ids[idx] for idx, doc in enumerate(case_documents)}

    def tracking_doc_id(doc: Any) -> str:
        return doc_tracking_id_map.get(id(doc)) or getattr(doc, "document_id", None) or getattr(doc, "id", None) or f"doc_{getattr(doc, 'file_name', 'unknown')}"

    max_tokens_per_batch = get_settings().max_tokens_per_batch
    batches = _create_prompt_aware_batches(
        documents=case_documents,
        intake_content=intake_content,
        review_data=review_data,
        statute_context=statute_context,
        jurisdiction=jurisdiction,
        max_tokens_per_batch=max_tokens_per_batch,
    )
    total_batches = len(batches)
    batch_token_estimates = [
        _estimate_summary_prompt_tokens(
            intake_content=intake_content,
            documents=batch,
            review_data=review_data,
            statute_context=statute_context,
            jurisdiction=jurisdiction,
            batch_num=i + 1,
            total_batches=total_batches,
        )
        for i, batch in enumerate(batches)
    ]

    semaphore = asyncio.Semaphore(min(PROMPT_MAX_CONCURRENT_BATCHES, max(1, total_batches)))

    logger.info(
        f"[BATCH-PARALLEL] Starting analysis of {total_docs} documents in "
        f"{total_batches} token-aware batches for {jurisdiction} "
        f"(max_tokens_per_batch={max_tokens_per_batch})"
    )

    async def process_batch_with_limit(batch: List[Any], batch_idx: int):
        """Process a batch of documents with semaphore-controlled concurrency."""
        nonlocal processed_count

        async with semaphore:
            batch_num = batch_idx + 1
            batch_doc_names = [d.file_name for d in batch]
            batch_doc_count = len(batch)
            batch_est_tokens = batch_token_estimates[batch_idx]

            logger.info(
                f"[BATCH {batch_num}/{total_batches}] Starting: {batch_doc_count} docs "
                f"(estimated_tokens={batch_est_tokens}) - {', '.join(batch_doc_names[:3])}..."
            )

            for doc in batch:
                doc_id = tracking_doc_id(doc)
                if chunk_state_mgr:
                    await chunk_state_mgr.update_document_status(doc_id, "processing")

            if progress_callback:
                await progress_callback(
                    message=(
                        f"Analyzing batch {batch_num}/{total_batches} "
                        f"({batch_doc_count} documents, ~{batch_est_tokens} tokens)..."
                    ),
                    phase="document_analysis",
                    percent=15 + int((processed_count / total_docs) * 60),
                )

            try:
                batch_result, batch_errors = await asyncio.wait_for(
                    _process_document_batch(
                        batch,
                        intake_content,
                        batch_num,
                        total_batches,
                        openai_client_wrapper,
                        json_processing_service,
                        review_data,
                        [],
                        statute_context,
                        jurisdiction=jurisdiction,
                    ),
                    timeout=180.0,
                )

                processed_count += batch_doc_count

                completed_doc_count = 0
                if batch_result:
                    logger.info(
                        f"[BATCH {batch_num}/{total_batches}] Completed: {len(batch_result)} summaries "
                        f"from {batch_doc_count} docs"
                    )

                    summaries_by_name: Dict[str, List[Any]] = {}
                    for summary in batch_result:
                        summaries_by_name.setdefault(summary.document_name, []).append(summary)

                    missing_docs: List[str] = []
                    for doc in batch:
                        doc_id = tracking_doc_id(doc)
                        doc_name = getattr(doc, "file_name", "unknown")
                        candidates = summaries_by_name.get(doc_name, [])
                        matching_summary = candidates.pop(0) if candidates else None
                        if chunk_state_mgr:
                            if matching_summary:
                                summary_data = (
                                    matching_summary.model_dump()
                                    if hasattr(matching_summary, "model_dump")
                                    else matching_summary
                                )
                                await chunk_state_mgr.update_document_status(doc_id, "completed", summary=summary_data)
                                completed_doc_count += 1
                            else:
                                await chunk_state_mgr.update_document_status(
                                    doc_id,
                                    "failed",
                                    error=f"Model did not return summary for {doc_name}",
                                    error_type="MISSING_SUMMARY",
                                )
                                missing_docs.append(doc_name)
                        elif matching_summary:
                            completed_doc_count += 1

                    if missing_docs:
                        missing_error = ProcessingError(
                            source=f"batch_{batch_num}",
                            error_type="MISSING_SUMMARY",
                            error_message=(
                                f"Model omitted {len(missing_docs)} document summaries in batch {batch_num}: "
                                + ", ".join(missing_docs[:5])
                            ),
                        )
                        batch_errors = [*(batch_errors or []), missing_error]
                else:
                    logger.warning(f"[BATCH {batch_num}/{total_batches}] No results from batch")
                    primary_error = next(iter(batch_errors or []), None)
                    if primary_error:
                        error_msg = primary_error.error_message
                        error_type = primary_error.error_type
                    else:
                        error_msg = (
                            f"Batch {batch_num} returned no summaries for {batch_doc_count} documents"
                        )
                        error_type = "EMPTY_BATCH_RESULT"
                        batch_errors = [
                            ProcessingError(
                                source=f"batch_{batch_num}",
                                error_type=error_type,
                                error_message=error_msg,
                            )
                        ]
                    for doc in batch:
                        doc_id = tracking_doc_id(doc)
                        if chunk_state_mgr:
                            await chunk_state_mgr.update_document_status(
                                doc_id,
                                "failed",
                                error=error_msg,
                                error_type=error_type,
                            )

                if progress_callback:
                    await progress_callback(
                        message=f"Batch {batch_num} complete ({completed_doc_count}/{batch_doc_count} docs summarized)",
                        docs_processed=batch_doc_names,
                        phase="document_analysis",
                        percent=15 + int((processed_count / total_docs) * 60),
                    )

                return batch_result or [], batch_errors or []

            except asyncio.TimeoutError:
                processed_count += batch_doc_count
                error_msg = f"Batch {batch_num} timed out after 3 minutes ({batch_doc_count} docs)"
                logger.error(f"[BATCH {batch_num}/{total_batches}] TIMEOUT: {', '.join(batch_doc_names)}")

                for doc in batch:
                    doc_id = tracking_doc_id(doc)
                    if chunk_state_mgr:
                        await chunk_state_mgr.update_document_status(
                            doc_id, "failed", error=error_msg, error_type="TIMEOUT"
                        )

                if progress_callback:
                    await progress_callback(
                        message=f"Timeout on batch {batch_num}",
                        phase="document_analysis",
                        percent=15 + int((processed_count / total_docs) * 60),
                    )

                return [], [
                    ProcessingError(
                        source=f"batch_{batch_num}",
                        error_type="TIMEOUT",
                        error_message=error_msg,
                    )
                ]

            except Exception as e:
                processed_count += batch_doc_count
                error_msg = str(e)
                logger.error(f"[BATCH {batch_num}/{total_batches}] ERROR: {e}", exc_info=True)

                for doc in batch:
                    doc_id = tracking_doc_id(doc)
                    if chunk_state_mgr:
                        await chunk_state_mgr.update_document_status(
                            doc_id, "failed", error=error_msg, error_type="PROCESSING_ERROR"
                        )

                if progress_callback:
                    await progress_callback(
                        message=f"Error in batch {batch_num}",
                        phase="document_analysis",
                        percent=15 + int((processed_count / total_docs) * 60),
                    )

                return [], [
                    ProcessingError(
                        source=f"batch_{batch_num}",
                        error_type="PROCESSING_ERROR",
                        error_message=error_msg,
                    )
                ]

    tasks = [process_batch_with_limit(batch, i) for i, batch in enumerate(batches)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[BATCH {i+1}/{total_batches}] Task exception: {result}")
            errors.append(
                ProcessingError(
                    source=f"batch_{i + 1}",
                    error_type="TASK_ERROR",
                    error_message=str(result),
                )
            )
        elif result:
            summaries, batch_errors = result
            all_summaries.extend(summaries)
            errors.extend(batch_errors)

    logger.info(
        f"[BATCH-PARALLEL] Complete: {len(all_summaries)} summaries from {total_docs} documents in {total_batches} batches, "
        f"{len(errors)} errors"
    )

    if errors and progress_callback:
        failed_docs = [{"name": e.source, "error": e.error_message, "error_type": e.error_type} for e in errors]
        await progress_callback(
            message=f"Document analysis complete with {len(errors)} failures",
            phase="document_analysis",
            percent=75,
            chunk_status={
                "type": "chunk_complete_with_errors",
                "completed": len(all_summaries),
                "failed": len(errors),
                "failed_docs": failed_docs,
            },
        )

    return all_summaries, errors


async def _process_document_batch(
    batch_documents: List[Any],
    intake_content: str,
    batch_num: int,
    total_batches: int,
    openai_client_wrapper: OpenAIClient,
    json_processing_service: JsonProcessingService,
    review_data: dict,  # NEW
    errors: List[ProcessingError],
    statute_context: str = "",  # NEW: Pass statute context
    jurisdiction: str = "Florida",  # NEW: Pass jurisdiction
) -> Tuple[List[Dict[str, Any]], List[ProcessingError]]:
    """Process a single batch of documents."""
    logger.info(
        f"📦 Processing batch {batch_num}/{total_batches} "
        f"({len(batch_documents)} documents) for {jurisdiction}"
    )

    # Build the prompt with the new context
    prompt = _build_summary_prompt(
        intake_content,
        batch_documents,
        review_data,
        is_batch=True,
        batch_info=(batch_num, total_batches),
        statute_context=statute_context,
        jurisdiction=jurisdiction,
    )

    response_json, batch_errors = await json_processing_service.process_documents_to_json(prompt)
    errors.extend(batch_errors)
    if not response_json:
        errors.append(
            ProcessingError(
                source=f"batch_{batch_num}",
                error_type="EMPTY_RESPONSE",
                error_message=f"Model returned empty response for batch {batch_num}",
            )
        )
        return [], errors

    # Clean and parse the JSON response
    parsed_data = _clean_and_parse_json(response_json, batch_num)
    if not parsed_data:
        errors.append(
            ProcessingError(
                source=f"batch_{batch_num}",
                error_type="PARSE_ERROR",
                error_message=f"Failed to parse JSON response for batch {batch_num}",
            )
        )
        return [], errors

    from legal_portal.core.data_models import DocumentSummaryStructured

    try:
        # Validate each document summary
        validated_summaries = []
        for doc_data in parsed_data.get("documents", []):
            try:
                summary = DocumentSummaryStructured(**doc_data)
                validated_summaries.append(summary)
            except Exception as e:
                logger.warning(
                    f"Failed to validate document summary for {doc_data.get('document_name', 'unknown')}: {e}"
                )
                # Continue without this summary

        if batch_documents and not validated_summaries:
            errors.append(
                ProcessingError(
                    source=f"batch_{batch_num}",
                    error_type="EMPTY_BATCH_RESULT",
                    error_message=f"No valid document summaries returned for batch {batch_num}",
                )
            )

        logger.info(f"✅ Batch {batch_num}/{total_batches} complete: {len(validated_summaries)} summaries")

        return validated_summaries, errors

    except Exception as e:
        logger.error(f"❌ Batch {batch_num} validation failed: {e}")
        return [], errors


def _clean_and_parse_json(json_string: str, batch_num: int = None) -> Optional[Dict[str, Any]]:
    """Clean a JSON string by removing markdown code blocks and then parse it.

    Args:
    ----
        json_string: The raw string response from the AI model.
        batch_num: The batch number for logging purposes.

    Returns:
    -------
        The parsed JSON data as a dictionary, or None if parsing fails.

    """
    if not isinstance(json_string, str):
        logger.error(f"Invalid input to _clean_and_parse_json: expected a string, got {type(json_string)}")
        return None

    # Remove markdown code blocks
    cleaned_json = re.sub(r"```json\s*|\s*```", "", json_string.strip())

    try:
        return json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        log_msg = f"Batch {batch_num} JSON parsing failed" if batch_num else "JSON parsing failed"
        logger.error(f"❌ {log_msg}: {e}")
        logger.error(f"Raw response: {cleaned_json[:500]}...")
        return None


def _build_summary_prompt(
    intake_content: str,
    documents: List[Any],
    review_data: dict,
    is_batch: bool = False,
    batch_info: tuple = (),
    statute_context: str = "",
    jurisdiction: str = "Florida",
) -> str:
    """Build the prompt for the document summarization AI call."""
    # Prepare context from review step
    legal_issue = review_data.get("legal_issue", "Not specified")
    key_documents_list = review_data.get("key_documents", [])

    key_docs_str = "\n".join([f"- {doc}" for doc in key_documents_list])
    if not key_docs_str:
        key_docs_str = "No documents were prioritized by the user."

    user_context_section = f"""
USER-DEFINED CONTEXT:
- Primary Legal Issue: {legal_issue}
- Key Documents (to give extra weight):
{key_docs_str}
"""

    # Add statute context if available
    statute_section = ""
    if statute_context:
        juris_config = JURISDICTION_CITATION_MAP.get(jurisdiction, JURISDICTION_CITATION_MAP["Florida"])
        statute_section = f"""

RELEVANT {juris_config['name_upper']} STATUTES (for cross-reference):
{statute_context}

When analyzing documents, identify relevant statutes from the list above.
List them in "statute_citations" as: "{juris_config['statute_citation_prefix']} XXX.XX"
"""

    if is_batch:
        batch_num, total_batches = batch_info
        batch_header = f"BATCH {batch_num} of {total_batches} - "
        main_header = (
            f"You are a legal document analyst for a matter in {jurisdiction}. "
            "Analyze each document in this batch and return structured JSON with complete facts."
        )
    else:
        batch_header = ""
        main_header = (
            f"You are a legal document analyst for a matter in {jurisdiction}. "
            "Analyze each document and return structured JSON with complete facts."
        )

    juris_config = JURISDICTION_CITATION_MAP.get(jurisdiction, JURISDICTION_CITATION_MAP["Florida"])
    statute_placeholder = juris_config["statute_citation_prefix"] + " XXX.XX"

    return f"""{main_header}

{user_context_section}

{statute_section}

INTAKE INFORMATION (for context):
{intake_content}

{IMAGE_HANDLING_INSTRUCTIONS}

Some documents include [PRIOR_CLASSIFICATION] and [ATTORNEY_INPUT] blocks.
Use these as starting context — refine the classification rather than starting from scratch.
Attorney-provided values (type overrides, confirmed facts, notes) are authoritative.

{batch_header}DOCUMENTS TO ANALYZE:
{_format_documents_with_metadata(documents)}

If a document includes `[TRUNCATED_DOCUMENT ...]`, only the listed excerpts
(beginning/middle/end) were provided to fit token limits.
Do not invent facts from omitted portions.

Your task is to provide a comprehensive analysis of EACH document with FLEXIBILITY.
Focus on capturing ALL relevant information, not just predefined fields.
---
OUTPUT FORMAT (STRICT JSON):
{{
  "documents": [
    {{
      "document_name": "exact_filename.pdf",
      "document_type": "Contract" | "Evidence" | "Notice" | "Correspondence" | "Other",

          "executive_summary": "2-3 sentence overview: What this document is and why it matters",

          "key_content": "Detailed narrative of the most important information in this document.",

          "key_quotes": [
            "Direct verbatim excerpt from document that serves as evidence"
          ],

      "statute_citations": [
        "{statute_placeholder} (if this document relates to a provided statute)",
        "Only include statutes that are clearly relevant to this specific document"
      ],

      "structured_data": {{
        "parties": ["Only include if clearly identifiable names/entities are present"],
        "dates": [
          {{
            "date": "YYYY-MM-DD or Month DD, YYYY",
            "event": "What happened",
            "source": "Page or section reference"
          }}
        ],
        "amounts": [
          {{
            "amount": "$XXX,XXX.XX",
            "description": "What this represents",
            "source": "Page or section reference"
          }}
        ],
        "contract_clauses": [
          {{
            "clause_id": "Section number if applicable",
            "description": "What the clause covers",
            "snippet": "Brief relevant quote"
          }}
        ]
      }},

      "important_details": [
        "Any other critical information that doesn't fit above",
        "Flag dual roles/conflicts: 'CONFLICT: Client is both [Role 1] and [Role 2]'",
        "Note procedural requirements, deadlines, notice requirements",
        "Identify risks, limitations, or potential problems",
        "Highlight admissions, contradictions, or smoking guns"
      ],

          "legal_significance": "Why this document matters legally (e.g., establishes liability)",

      "relevance_to_case": "How this document supports or weakens the claim",

      "extraction_quality": "high" | "medium" | "low",
      "extraction_notes": "Only note if there were text extraction issues or if document is incomplete"
    }}
  ]
}}

CRITICAL RULES:
- PRIORITIZE COMPREHENSIVE CAPTURE over fitting into boxes
- The "key_content" and "important_details" fields should contain EVERYTHING relevant
- **KEY_QUOTES**: Extract 2-5 direct verbatim quotes that serve as evidence (if document has readable text)
- **STATUTE_CITATIONS**: Only include statutes if the document content clearly relates to them
- Structured fields are OPTIONAL - only populate if data is clearly present
- NEVER say "not found" - simply omit optional fields or leave arrays empty
- If a document type doesn't have contracts clauses (like an estimate), that's fine - focus on what IS there
- **CONFLICTS OF INTEREST**: If client has dual roles, ALWAYS flag in "important_details"
- Include page numbers or section references when possible
- Be specific with amounts, dates, and names when they appear
- Capture admissions, contradictions, or particularly strong/weak points
- Use "Correspondence" for letters, emails, and documented correspondence regardless of file extension
- Return ONLY valid JSON, no markdown code blocks
"""
