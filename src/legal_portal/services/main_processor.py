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
    ProcessingError,
    ProcessingResult,
    QualityScore,
)
from legal_portal.core.document_processor import DocumentProcessor
from legal_portal.services.corpus_coverage_service import CorpusCoverageService
from legal_portal.services.document_quality_validator import DocumentQualityValidator
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer
from legal_portal.services.statute_recommendation_service import StatuteRecommendationService
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)

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
    # Build prompt with all document summaries
    summaries_json = json.dumps([s.model_dump() for s in structured_summaries], indent=2)
    legal_issue = review_data.get("legal_issue", "") if review_data else ""

    # Get jurisdiction-specific config
    juris_config = JURISDICTION_CITATION_MAP.get(jurisdiction, JURISDICTION_CITATION_MAP["Florida"])
    statute_format = juris_config["statute_citation_short_prefix"] + " XXX.XX"

    prompt = f"""You are a senior legal analyst. Based on the intake form and document summaries below, \
create a high-level case analysis for a matter in {jurisdiction}.

INTAKE INFORMATION:
{intake_content}

{f"IDENTIFIED LEGAL ISSUE: {legal_issue}" if legal_issue else ""}

DOCUMENT SUMMARIES:
{summaries_json}

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
        model = openai_client_wrapper.get_preferred_model("document_analysis", "gpt-4o")
        response = openai_client_wrapper.create_chat_completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
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
    intake_form_path: str,
    case_document_paths: List[str],
    case_info: dict,
    review_data: dict,  # NEW: For key docs and legal issue
    progress_callback: Optional[Callable] = None,
    jurisdiction: str = "Florida",  # Added jurisdiction parameter
) -> ProcessingResult:
    """Decoupled document processing workflow."""
    start_time = time.time()
    errors = []

    try:
        # 1. Initialize services
        logger.info("Initializing processing services...")
        openai_client_wrapper = OpenAIClient()
        doc_processor = DocumentProcessor()
        json_processing_service = JsonProcessingService(client=openai_client_wrapper, config={})

        logger.info(f"Processing case for jurisdiction: {jurisdiction}")

        # 2. Validate inputs
        if not intake_form_path:
            raise ValueError("An intake form is required for the analysis.")

        # Case documents are optional
        if not case_document_paths:
            logger.warning("No case documents provided. Analysis will be based on the intake form only.")

        # 3. Process intake form from its path
        logger.info(f"Processing intake form from path: {intake_form_path}")
        intake_filename = os.path.basename(intake_form_path)
        processed_intake = await doc_processor.process_documents_from_paths(
            [intake_form_path],
            intake_filenames=[intake_filename],
        )

        if not processed_intake:
            raise ValueError("Failed to process intake form.")

        intake_content = processed_intake[0].content
        logger.info(f"Intake form processed: {len(intake_content)} characters")

        # Log data context for quality assurance
        if os.getenv("LOG_LEVEL") == "DEBUG":
            logger.info(f"CONTEXT CHECK - Intake preview: {intake_content[:200]}...")

        # 4. Process case documents (if any)
        processed_case_docs = []
        if case_document_paths:
            if progress_callback:
                await progress_callback("Extracting content from documents...", [], "document_extraction", 5)

            processed_docs = await doc_processor.process_documents_from_paths(
                case_document_paths,
                intake_filenames=[os.path.basename(intake_form_path)],
                progress_callback=progress_callback,
            )
            processed_case_docs.extend(processed_docs)

            if not processed_case_docs:
                logger.warning("No case documents were successfully processed.")

            if progress_callback:
                await progress_callback(
                    f"Extracted content from {len(processed_case_docs)} documents",
                    [d.file_name for d in processed_case_docs],
                    "extraction_complete",
                    15,
                )

        # 4.3 Deduplication
        if processed_case_docs:
            logger.info(f"Checking {len(processed_case_docs)} documents for duplicates...")
            if progress_callback:
                await progress_callback("Deduplicating documents...")

            processed_case_docs = await asyncio.to_thread(_deduplicate_documents, processed_case_docs)
            logger.info(f"After deduplication: {len(processed_case_docs)} unique documents")

            await asyncio.to_thread(_detect_near_duplicates, processed_case_docs)

        # 4.5. Quality validation on processed documents
        quality_validator = DocumentQualityValidator()
        quality_results = []
        if processed_case_docs:
            logger.info("Running document quality validation...")
            if progress_callback:
                await progress_callback("Validating document quality...")

            for doc in processed_case_docs:
                res = await asyncio.to_thread(quality_validator.validate_document, doc)
                quality_results.append(res)

        # Aggregate quality results and create context string
        aggregated_quality_report = _aggregate_quality_results(quality_results)
        quality_context = _format_quality_context(aggregated_quality_report)

        # Load settings early so we can use it for statute recommendations
        settings = get_settings()

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

        if progress_callback:
            await progress_callback(
                "Analyzing extracted content...",
                [d.file_name for d in processed_case_docs],
                "document_analysis",
                15,
            )
        structured_summaries, errors = await _generate_document_summaries(
            intake_content,
            processed_case_docs,
            openai_client_wrapper,
            json_processing_service,  # Pass the instance here
            review_data,  # Pass through
            progress_callback,
            statute_context,  # NEW: Pass statute context
            jurisdiction=jurisdiction,  # NEW: Pass jurisdiction
        )

        # 5.5. AI Call #2.5: Generate case-level analysis summary
        logger.info("AI Call #2.5: Generating case-level analysis summary...")
        case_analysis_dict = await asyncio.to_thread(
            _generate_case_analysis_summary,
            intake_content,
            structured_summaries,
            openai_client_wrapper,
            review_data,
            jurisdiction=jurisdiction,
        )
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

        # Check if CLIO context is available in review_data
        clio_context_str = ""
        if review_data.get("clio_matter_context"):
            from legal_portal.services.clio_context_builder import ClioContextBuilder

            builder = ClioContextBuilder()
            clio_context_str = builder.format_clio_context_for_prompt(review_data["clio_matter_context"])
            logger.info("Using CLIO matter context for enhanced letter generation")

        # ==================================================
        # MULTI-STAGE ANALYSIS PIPELINE (FEATURE FLAG)
        # ==================================================
        multi_stage_result = None
        fact_matrix = None
        legal_issue_map = None
        letter_structure = None

        # Multi-stage analysis is REQUIRED for letter generation
        # Always run it - no feature flag
        logger.info(f"🔬 Running multi-stage analysis pipeline for {jurisdiction}")

        try:
            statute_service = StatuteRecommendationService(jurisdiction=jurisdiction)
            multi_stage_analyzer = MultiStageAnalyzer(
                openai_client=openai_client_wrapper, statute_service=statute_service
            )

            if progress_callback:
                await progress_callback("Running multi-stage legal analysis...", phase="fact_extraction")

            multi_stage_result = await multi_stage_analyzer.analyze_case(
                intake_content=intake_content,
                document_summaries=structured_summaries,
                progress_callback=progress_callback,
                case_type=case_analysis_dict.get("practice_area"),
                jurisdiction=jurisdiction,  # Pass jurisdiction
            )

            fact_matrix = multi_stage_result.fact_matrix
            legal_issue_map = multi_stage_result.issue_map
            letter_structure = multi_stage_result.letter_structure

            logger.info(
                f"Multi-stage analysis complete: {len(fact_matrix.timeline)} timeline events, "
                f"{len(legal_issue_map.primary_issues)} legal issues identified, "
                f"letter structure: {letter_structure.style}"
            )

        except Exception as e:
            logger.error(f"Multi-stage analysis failed: {e}", exc_info=True)
            multi_stage_result = None
            # Surface the error so it's visible in results
            if progress_callback:
                await progress_callback(
                    f"⚠️ Advanced analysis failed: {str(e)[:100]}. Letter generation will be unavailable.",
                    phase="multi_stage_error",
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

        # 9. Calculate processing time
        processing_time = time.time() - start_time

        logger.info(
            f"Successfully completed document processing in {processing_time:.2f}s (letters deferred)"
        )

        # Track which models were used for each operation
        models_used = {
            "document_analysis": openai_client_wrapper.get_preferred_model("document_analysis", "gpt-4o"),
            "letter_generation": openai_client_wrapper.get_preferred_model("letter_generation", "gpt-4o"),
            "case_chat": openai_client_wrapper.get_preferred_model("case_chat", "gpt-4o"),
            "multi_stage_analysis": openai_client_wrapper.get_preferred_model(
                "multi_stage_analysis", "gpt-4o"
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
            document_count=len(processed_case_docs),
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
        )
        logger.info("✅ Document processing completed (letters deferred to on-demand endpoints).")
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


def _format_documents_with_metadata(case_documents: list) -> str:
    """Format documents with quality flags for AI analysis."""
    formatted = []
    for i, doc in enumerate(case_documents, 1):
        quality_flag = ""
        if doc.extraction_quality == "low":
            quality_flag = " [⚠️ LOW QUALITY - may have extraction errors]"
        elif doc.extraction_quality == "medium":
            quality_flag = " [⚠️ MEDIUM QUALITY - verify critical facts]"

        # Add image flag for image documents
        doc_type_flag = " [📷 IMAGE FILE]" if _is_image_document(doc) else ""

        content_preview = doc.content  # Send full content, no truncation
        formatted.append(
            f"\n--- Document {i}: {doc.file_name}{quality_flag}{doc_type_flag} ---\n{content_preview}\n"
        )
    return "".join(formatted)


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
    max_docs_per_batch = 10  # Hard limit to prevent API timeouts

    for doc in documents:
        doc_tokens = _estimate_tokens(doc.content)

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


async def _generate_document_summaries(
    intake_content: str,
    case_documents: List[Any],
    openai_client_wrapper: OpenAIClient,
    json_processing_service: JsonProcessingService,  # Add this parameter
    review_data: dict,  # NEW
    progress_callback: Optional[Callable] = None,
    statute_context: str = "",  # NEW: Pass statute recommendations
    jurisdiction: str = "Florida",  # NEW: Pass jurisdiction
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
    errors = []  # Initialize the errors list here

    # Handle case with no documents - analyze intake form only
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
    else:
        # Check if we need batching (more than 8 documents or large content)
        total_estimated_tokens = sum(_estimate_tokens(doc.content) for doc in case_documents)
        needs_batching = len(case_documents) > 8 or total_estimated_tokens > 40000

        if needs_batching:
            logger.info(
                f"📊 Large document set detected: {len(case_documents)} docs, ~{total_estimated_tokens:,} tokens"  # noqa: E501
            )
            logger.info("Using intelligent batching to process all documents...")

            # Create smart batches
            batches = _create_smart_batches(case_documents)  # Uses configured max_tokens_per_batch
            logger.info(f"Created {len(batches)} batches for processing")

            # Process each batch with detailed progress
            all_summaries = []
            total_docs_in_all_batches = len(case_documents)
            docs_processed_count = 0

            for batch_num, batch in enumerate(batches, 1):
                logger.info(f"📦 Processing batch {batch_num}/{len(batches)} ({len(batch)} documents)...")

                # Update UI progress if callback available
                try:
                    import streamlit as st

                    if (
                        hasattr(st, "session_state")
                        and hasattr(st.session_state, "progress_callback")
                        and st.session_state.progress_callback
                    ):
                        progress_pct = (batch_num - 1) / len(batches)
                        st.session_state.progress_callback(
                            progress_pct,
                            f"Analyzing batch {batch_num} of {len(batches)} ({len(all_summaries)}/{len(case_documents)} documents complete)",  # noqa: E501
                        )
                except (ImportError, AttributeError):
                    pass  # Streamlit not available or progress callback not set

                batch_result, batch_errors = await _process_document_batch(
                    batch,
                    intake_content,
                    batch_num,
                    len(batches),
                    openai_client_wrapper,
                    json_processing_service,  # Pass json_processing_service
                    review_data,  # Pass review_data
                    errors,
                    statute_context,  # NEW: Pass statute context
                    jurisdiction=jurisdiction,  # NEW: Pass jurisdiction
                )

                if batch_result:
                    all_summaries.extend(batch_result)
                if batch_errors:
                    errors.extend(batch_errors)

                docs_processed_count += len(batch)

                # Update UI progress if callback available
                if progress_callback:
                    # Calculate percentage within the 15-75% range
                    progress_pct = 15 + int((docs_processed_count / total_docs_in_all_batches) * 60)
                    await progress_callback(
                        message=f"Analyzed {docs_processed_count} of {total_docs_in_all_batches} documents...",  # noqa: E501
                        docs_processed=[s.document_name for s in all_summaries],
                        phase="document_analysis",
                        percent=progress_pct,
                    )

            logger.info(
                f"✅ Batch processing complete: {len(all_summaries)} total summaries from {len(batches)} batches"  # noqa: E501
            )

            return (
                all_summaries,
                errors,
            )  # Return empty errors for now, as errors are handled by _process_document_batch

        # Original single-call path for smaller document sets
        logger.info(f"Processing {len(case_documents)} documents in single call for {jurisdiction}...")

        # Build the flexible JSON prompt for documents
        prompt = _build_summary_prompt(
            intake_content,
            case_documents,
            review_data,
            is_batch=False,
            statute_context=statute_context,
            jurisdiction=jurisdiction,
        )

    # Make the API call
    model = openai_client_wrapper.get_preferred_model("document_analysis", "gpt-4o")
    response_dict = await asyncio.to_thread(
        openai_client_wrapper.create_chat_completion,
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a precise legal document analyst. Always return valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=4000,
        temperature=0.3,
    )

    # Parse JSON response
    raw_response = response_dict["content"].strip()

    # Remove markdown code blocks if present
    if raw_response.startswith("```"):
        lines = raw_response.split("\n")
        # Remove first line (``` or ```json) and last line (```)
        raw_response = "\n".join(lines[1:-1])

    from legal_portal.core.data_models import DocumentSummaryStructured

    try:
        parsed_data = json.loads(raw_response)

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

        logger.info(f"✅ Successfully parsed {len(validated_summaries)} structured document summaries")

        # Return both structured data and raw JSON
        return validated_summaries, []  # Return empty errors for now

    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse JSON response: {e}")
        logger.error(f"Raw response: {raw_response[:500]}...")
        # Return empty result - let calling code handle fallback
        raise ValueError(f"JSON parsing failed: {e}") from e


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

    # Clean and parse the JSON response
    parsed_data = _clean_and_parse_json(response_json, batch_num)
    if not parsed_data:
        return [], errors  # Return immediately if parsing fails

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

{batch_header}DOCUMENTS TO ANALYZE:
{_format_documents_with_metadata(documents)}

Your task is to provide a comprehensive analysis of EACH document with FLEXIBILITY.
Focus on capturing ALL relevant information, not just predefined fields.
---
OUTPUT FORMAT (STRICT JSON):
{{
  "documents": [
    {{
      "document_name": "exact_filename.pdf",
      "document_type": "Contract" | "Evidence" | "Notice" | "Other",

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
- Return ONLY valid JSON, no markdown code blocks
"""
