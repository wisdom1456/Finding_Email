from __future__ import annotations

import hashlib
import json
import os
import re  # Added for _clean_and_parse_json
import time
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Tuple

from legal_portal.core.data_models import (
    AnalyzedDocument,
    CaseAnalysisResult,
    DocumentSummaryStructured,
    IntakeAnalysis,
    ProcessingError,
    ProcessingResult,
    QualityScore,
)
from legal_portal.core.document_processor import DocumentProcessor
from legal_portal.services.document_quality_validator import DocumentQualityValidator
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.letter_review_service import LetterReviewService
from legal_portal.services.qa_service import run_qa_heuristics  # Import the new QA function
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)

# Shared prompt instructions for image document handling
IMAGE_HANDLING_INSTRUCTIONS = """
---
**CRITICAL INSTRUCTIONS FOR IMAGE DOCUMENTS:**
Documents marked with [📷 IMAGE FILE] are images. For these:
- Base analysis ONLY on the visual description provided in the content
- DO NOT infer `parties`, `key_dates`, or `key_amounts` unless explicitly visible/readable in the image description
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


async def process_case_documents(
    intake_form_path: str,
    case_document_paths: List[str],
    case_info: dict,
    review_data: dict,  # NEW: For key docs and legal issue
    progress_callback: Optional[Callable] = None,
) -> ProcessingResult:
    """Decoupled document processing workflow.

    Simplified 2-call workflow:
    1. Extract intake data + summarize case documents (AI Call #1)
    2. Generate findings letter (AI Call #2)

    Args:
    ----
        intake_form_path: File path to the intake form
        case_document_paths: List of file paths to case documents
        case_info: Optional dictionary with case metadata (client name, attorney, etc.)

    Returns:
    -------
        ProcessingResult: Structured result containing the generated letter and analysis

    Raises:
    ------
        ValueError: If required inputs are missing or processing fails
        Exception: For unexpected errors during processing

    """
    start_time = time.time()
    errors = []

    try:
        # 1. Initialize services
        logger.info("Initializing processing services...")
        openai_client_wrapper = OpenAIClient()
        doc_processor = DocumentProcessor()
        json_processing_service = JsonProcessingService(client=openai_client_wrapper, config={})

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
                progress_callback("Extracting content from documents...", [], "document_extraction", 5)

            processed_docs = await doc_processor.process_documents_from_paths(
                case_document_paths,
                intake_filenames=[os.path.basename(intake_form_path)],
                progress_callback=progress_callback,
            )
            processed_case_docs.extend(processed_docs)

            if not processed_case_docs:
                logger.warning("No case documents were successfully processed.")

            if progress_callback:
                progress_callback(
                    f"Extracted content from {len(processed_case_docs)} documents",
                    [d.file_name for d in processed_case_docs],
                    "extraction_complete",
                    15,
                )

        # 4.3 Deduplication
        if processed_case_docs:
            logger.info(f"Checking {len(processed_case_docs)} documents for duplicates...")
            if progress_callback:
                progress_callback("Deduplicating documents...")

            processed_case_docs = _deduplicate_documents(processed_case_docs)
            logger.info(f"After deduplication: {len(processed_case_docs)} unique documents")

            _detect_near_duplicates(processed_case_docs)

        # 4.5. Quality validation on processed documents
        quality_validator = DocumentQualityValidator()
        quality_results = []
        if processed_case_docs:
            logger.info("Running document quality validation...")
            if progress_callback:
                progress_callback("Validating document quality...")

            for doc in processed_case_docs:
                quality_results.append(quality_validator.validate_document(doc))

        # Aggregate quality results and create context string
        aggregated_quality_report = _aggregate_quality_results(quality_results)
        quality_context = _format_quality_context(aggregated_quality_report)

        # Pass new context to summary generation
        if progress_callback:
            progress_callback(
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
        )

        # 6. AI Call #2: Generate findings letter from JSON
        logger.info("AI Call #2: Generating findings letter from structured data...")
        if os.getenv("LOG_LEVEL") == "DEBUG":
            logger.info(
                f"CONTEXT CHECK - Passing {len(intake_content)} chars intake + JSON summaries to letter generation"
            )

        document_summaries_json_str = json.dumps([s.model_dump() for s in structured_summaries], indent=2)

        # Extract attorney information from case_info
        attorney_name = case_info.get("attorneyName") if case_info else None
        firm_name = case_info.get("firmName") if case_info else None

        # Extract contact information from case_info
        contact_phone = case_info.get("contactPhone") if case_info else None
        contact_email = case_info.get("contactEmail") if case_info else None

        # Extract confirmed Q&A pairs from review_data
        confirmed_qa_pairs = review_data.get("confirmed_qa_pairs", []) if review_data else []

        # Pass new context to letter generation
        draft_letter = await json_processing_service.generate_findings_letter_from_json(
            intake_content=intake_content,
            document_summaries_json=document_summaries_json_str,
            quality_context=quality_context,
            attorney_name=attorney_name,
            firm_name=firm_name,
            confirmed_qa_pairs=confirmed_qa_pairs,  # NEW: Pass user-confirmed Q&A
            contact_phone=contact_phone,  # NEW: Pass contact phone
            contact_email=contact_email,  # NEW: Pass contact email
        )

        if os.getenv("LOG_LEVEL") == "DEBUG":
            logger.info(f"CONTEXT CHECK - Generated draft letter: {len(draft_letter)} chars")

        # 7. AI Call #3: Comprehensive quality review and rewrite
        logger.info("AI Call #3: Comprehensive letter review and formatting...")
        letter_review_service = LetterReviewService(client=openai_client_wrapper)

        # Extract full intake for review context (don't truncate)
        intake_summary = intake_content

        # Also pass client name from case_info for better personalization
        client_name = None
        if case_info:
            client_name = case_info.get("clientName", None)

        # Perform comprehensive review (now includes source verification and completeness checks)
        improved_letter = letter_review_service.review_and_improve_letter(
            draft_letter=draft_letter,
            intake_summary=intake_summary,
            case_type=None,
            document_summaries_json=json.dumps(
                [s.model_dump() for s in structured_summaries], indent=2
            ),  # NEW - pass for source verification
            quality_context=quality_context,  # NEW - pass for completeness checks
            client_name=client_name,
        )

        logger.info(
            f"Letter review complete: {len(draft_letter)} -> {len(improved_letter)} chars",
            extra={
                "original_length": len(draft_letter),
                "improved_length": len(improved_letter),
            },
        )

        # 8. Run lightweight QA checks
        logger.info("Running lightweight QA heuristics...")
        qa_warnings = run_qa_heuristics(
            improved_letter, json.loads(json.dumps([s.model_dump() for s in structured_summaries], indent=2))
        )
        if qa_warnings:
            for warning in qa_warnings:
                logger.warning(warning)  # Log QA warnings
            # Optionally, you could add these warnings to the ProcessingResult errors
            # For now, we just log them.

        # 8b. Create clean and cited versions
        logger.info("Creating clean and cited versions of findings letter...")
        try:
            from legal_portal.services.citation_tracking_service import CitationTrackingService

            # The AI generates letter WITH citations (per prompt instructions)
            citation_service = CitationTrackingService()

            # Clean hash suffixes from filenames in citations
            # Transform: (Source: Contract_fb5b8b11.pdf) → (Source: Contract.pdf)
            letter_with_clean_filenames = citation_service.clean_filename_hashes(improved_letter)

            # Keep the version with citations (but clean filenames) for cited letter
            letter_with_citations = letter_with_clean_filenames

            # Strip citations to create clean version
            clean_letter = citation_service.remove_citations_from_letter(letter_with_clean_filenames)

            logger.info(
                f"Successfully created both versions: "
                f"clean ({len(clean_letter)} chars) and cited ({len(letter_with_citations)} chars)"
            )

            # 8c. Apply professional formatting to both versions
            logger.info("Applying professional legal document formatting...")
            from legal_portal.services.document_formatter import DocumentFormatterService

            formatter = DocumentFormatterService()

            # Get client name for formatted header
            client_name_for_format = case_info.get("clientName", "Client") if case_info else "Client"

            # Apply formatting to both versions
            clean_letter = formatter.format_findings_letter(clean_letter, client_name_for_format)
            letter_with_citations = formatter.format_findings_letter(
                letter_with_citations, client_name_for_format
            )

            logger.info(
                f"Applied professional formatting: "
                f"clean ({len(clean_letter)} chars) and cited ({len(letter_with_citations)} chars)"
            )

            # Use clean version as main letter
            improved_letter = clean_letter

        except Exception as e:
            logger.warning(f"Failed to strip citations: {e}", exc_info=True)
            # Fallback: apply formatting to the improved letter
            try:
                from legal_portal.services.document_formatter import DocumentFormatterService

                formatter = DocumentFormatterService()
                client_name_for_format = case_info.get("clientName", "Client") if case_info else "Client"
                improved_letter = formatter.format_findings_letter(improved_letter, client_name_for_format)
                logger.info("Applied formatting to fallback letter")
            except Exception as format_error:
                logger.warning(f"Failed to format fallback letter: {format_error}")

            # Use the same formatted letter for both versions
            letter_with_citations = improved_letter
            logger.info("Using formatted letter for both versions due to citation stripping error")

        # 9. Calculate processing time
        processing_time = time.time() - start_time

        # 10. Create and return the result object
        logger.info(f"Successfully completed document processing in {processing_time:.2f}s")

        # Final result construction
        result = ProcessingResult(
            main_letter=improved_letter,
            main_letter_with_citations=letter_with_citations,  # NEW: Cited version
            document_summaries=json.dumps([s.model_dump() for s in structured_summaries], indent=2),
            case_analysis=json.dumps(
                [s.model_dump() for s in structured_summaries], indent=2
            ),  # For backward compatibility
            quality_report=[q.model_dump() for q in quality_results]
            if quality_results
            else None,  # NEW: Add quality results
            status="completed",
            processing_time_seconds=processing_time,
            intake_content=intake_content,
            document_count=len(processed_case_docs),
            errors=errors,
        )
        logger.info("✅ Full document processing workflow completed successfully.")
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
            case_analysis="",
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
            case_analysis="",
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
                f"Duplicate detected: '{doc.file_name}' is identical to '{seen_hashes[content_hash]}'. Skipping."
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

            if similarity > 0.85:  # 85% similar
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


def _create_smart_batches(documents: list, max_tokens_per_batch: int = 50000) -> list:
    """Group documents into batches based on token estimates.

    Args:
    ----
        documents: List of ProcessedDocument objects
        max_tokens_per_batch: Maximum tokens per batch (default 50,000)

    Returns:
    -------
        List of document batches

    """
    batches = []
    current_batch = []
    current_tokens = 0
    MAX_DOCS_PER_BATCH = 10  # Hard limit to prevent API timeouts

    for doc in documents:
        doc_tokens = _estimate_tokens(doc.content)

        # Start new batch if: would exceed token limit OR already have 10 docs
        if (current_tokens + doc_tokens > max_tokens_per_batch and current_batch) or len(
            current_batch
        ) >= MAX_DOCS_PER_BATCH:
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
) -> Tuple[List[Dict[str, Any]], List[ProcessingError]]:
    """AI Call #1: Generate structured JSON summaries of case documents.

    Args:
    ----
        openai_client_wrapper: An instance of the custom OpenAIClient wrapper.
        intake_content: Extracted text from intake form
        case_documents: List of ProcessedDocument objects (can be empty)

    Returns:
    -------
        Dictionary with 'summaries' (list of DocumentSummaryStructured) and 'raw_json' (string)

    """
    errors = []  # Initialize the errors list here

    # Handle case with no documents - analyze intake form only
    if not case_documents:
        prompt = f"""You are a legal document analyst. Given the client intake information below, provide a structured JSON analysis.

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
                f"📊 Large document set detected: {len(case_documents)} docs, ~{total_estimated_tokens:,} tokens"
            )
            logger.info("Using intelligent batching to process all documents...")

            # Create smart batches
            batches = _create_smart_batches(case_documents, max_tokens_per_batch=50000)
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
                            f"Analyzing batch {batch_num} of {len(batches)} ({len(all_summaries)}/{len(case_documents)} documents complete)",
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
                    progress_callback(
                        message=f"Analyzed {docs_processed_count} of {total_docs_in_all_batches} documents...",
                        docs_processed=[s.document_name for s in all_summaries],
                        phase="document_analysis",
                        percent=progress_pct,
                    )

            logger.info(
                f"✅ Batch processing complete: {len(all_summaries)} total summaries from {len(batches)} batches"
            )

            return (
                all_summaries,
                errors,
            )  # Return empty errors for now, as errors are handled by _process_document_batch

        # Original single-call path for smaller document sets
        logger.info(f"Processing {len(case_documents)} documents in single call...")

        # Build the structured JSON prompt for documents
        prompt = f"""You are a legal document analyst. Analyze each document and return structured JSON with complete facts.

INTAKE INFORMATION:
{intake_content}

DOCUMENT QUALITY NOTES:
{_build_quality_context(case_documents)}

{IMAGE_HANDLING_INSTRUCTIONS}

DOCUMENTS TO ANALYZE:
{_format_documents_with_metadata(case_documents)}

---
OUTPUT FORMAT (STRICT JSON):
{{
  "documents": [
    {{
      "document_name": "exact_filename.pdf",
      "document_type": "Contract" | "Disclosure" | "Evidence" | "Correspondence",
      "parties": ["Full Name 1", "Full Name 2"],
      "jurisdiction_inferred": "State or Court inferred from document",
      "key_dates": [
        {{
          "date": "YYYY-MM-DD or Month DD, YYYY",
          "event": "What happened",
          "source_document": "Document name, Section/Page"
        }}
      ],
      "key_amounts": [
        {{
          "amount": "$XXX,XXX.XX format",
          "description": "What this represents",
          "source_document": "Document name, Section/Page"
        }}
      ],
      "issues_identified": [
        "Specific legal problem or violation found",
        "IMPORTANT: Flag any dual roles or conflicts of interest (e.g., 'Client serves as HOA board member while also filing claim against HOA')",
        "Note any ethical considerations or recusal requirements"
      ],
      "risk_items": [
        "Lien risk present",
        "Statute of limitations proximity",
        "Insurance coverage limitations"
      ],
      "contract_clauses_referenced": [
        {{
          "clause_number": "e.g., 7.1",
          "title": "e.g., 'Default and Cure'",
          "snippet": "Brief quote from the clause"
        }}
      ],
      "procedural_requirements": [
        "e.g., 'Chapter 558 pre-suit notice required'",
        "e.g., 'Contract requires mediation before litigation'"
      ],
      "relevance_to_case": "How this document supports or weakens the claim",
      "extraction_quality": "high" | "medium" | "low",
      "extraction_notes": "Any issues with source text"
    }}
  ]
}}

CRITICAL RULES:
- Always populate source_document fields with specific references
- Use exact dates in consistent format (Month DD, YYYY preferred)
- Format amounts as $XXX,XXX.XX
- Include ALL parties mentioned (people, companies, entities)
- List specific issues, not generic statements
- **DUAL ROLES & CONFLICTS**: If the client holds multiple roles (board member + property owner, employer + employee, etc.), EXPLICITLY flag this in "issues_identified" with format: "CONFLICT: Client holds dual role as [Role 1] and [Role 2]"
- Flag any potential conflicts of interest, ethical concerns, or situations requiring recusal
- If a field has no data, use empty array [] or note "Not found in document"
- Return ONLY valid JSON, no markdown code blocks
"""

    # Make the API call
    response_dict = openai_client_wrapper.create_chat_completion(
        model="gpt-4o",
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
) -> Tuple[List[Dict[str, Any]], List[ProcessingError]]:
    """Process a single batch of documents."""
    logger.info(f"📦 Processing batch {batch_num}/{total_batches} with {len(batch_documents)} documents")

    # Build the prompt with the new context
    prompt = _build_summary_prompt(
        intake_content, batch_documents, review_data, is_batch=True, batch_info=(batch_num, total_batches)
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
    """Cleans a JSON string by removing markdown code blocks and then parses it.

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
) -> str:
    """Builds the prompt for the document summarization AI call."""
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

    if is_batch:
        batch_num, total_batches = batch_info
        batch_header = f"BATCH {batch_num} of {total_batches} - "
        main_header = "You are a legal document analyst. Analyze each document in this batch and return structured JSON with complete facts."
    else:
        batch_header = ""
        main_header = "You are a legal document analyst. Analyze each document and return structured JSON with complete facts."

    return f"""{main_header}

{user_context_section}

INTAKE INFORMATION (for context):
{intake_content}

{IMAGE_HANDLING_INSTRUCTIONS}

{batch_header}DOCUMENTS TO ANALYZE:
{_format_documents_with_metadata(documents)}

Your task is to provide a detailed, structured summary for EACH document.
---
OUTPUT FORMAT (STRICT JSON):
{{
  "documents": [
    {{
      "document_name": "exact_filename.pdf",
      "document_type": "Contract" | "Disclosure" | "Evidence" | "Correspondence",
      "parties": ["Full Name 1", "Full Name 2"],
      "jurisdiction_inferred": "State or Court inferred from document",
      "key_dates": [
        {{
          "date": "YYYY-MM-DD or Month DD, YYYY",
          "event": "What happened",
          "source_document": "Document name, Section/Page"
        }}
      ],
      "key_amounts": [
        {{
          "amount": "$XXX,XXX.XX format",
          "description": "What this represents",
          "source_document": "Document name, Section/Page"
        }}
      ],
      "issues_identified": [
        "Specific legal problem or violation found",
        "IMPORTANT: Flag any dual roles or conflicts of interest (e.g., 'Client serves as HOA board member while also filing claim against HOA')",
        "Note any ethical considerations or recusal requirements"
      ],
      "risk_items": [
        "Lien risk present",
        "Statute of limitations proximity",
        "Insurance coverage limitations"
      ],
      "contract_clauses_referenced": [
        {{
          "clause_number": "e.g., 7.1",
          "title": "e.g., 'Default and Cure'",
          "snippet": "Brief quote from the clause"
        }}
      ],
      "procedural_requirements": [
        "e.g., 'Chapter 558 pre-suit notice required'",
        "e.g., 'Contract requires mediation before litigation'"
      ],
      "relevance_to_case": "How this document supports or weakens the claim",
      "extraction_quality": "high" | "medium" | "low",
      "extraction_notes": "Any issues with source text"
    }}
  ]
}}

CRITICAL RULES:
- Always populate source_document fields with specific references
- Use exact dates in consistent format (Month DD, YYYY preferred)
- Format amounts as $XXX,XXX.XX
- Include ALL parties mentioned (people, companies, entities)
- List specific issues, not generic statements
- **DUAL ROLES & CONFLICTS**: If the client holds multiple roles (board member + property owner, employer + employee, etc.), EXPLICITLY flag this in "issues_identified" with format: "CONFLICT: Client holds dual role as [Role 1] and [Role 2]"
- Flag any potential conflicts of interest, ethical concerns, or situations requiring recusal
- If a field has no data, use empty array [] or note "Not found in document"
- Return ONLY valid JSON, no markdown code blocks
"""
