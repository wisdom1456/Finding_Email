from __future__ import annotations

import time
from typing import Any, List

from legal_portal.core.data_models import ProcessingError, ProcessingResult
from legal_portal.core.document_processor import DocumentProcessor
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient

logger = get_module_logger(__name__)


async def process_case_documents(
    intake_form: Any,
    case_documents: List[Any],
    case_info: dict = None,
) -> ProcessingResult:
    """Decoupled document processing workflow.

    Simplified 2-call workflow:
    1. Extract intake data + summarize case documents (AI Call #1)
    2. Generate findings letter (AI Call #2)

    Args:
    ----
        intake_form: File-like object containing the intake form
        case_documents: List of file-like objects containing case documents
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
        openai_client = openai_client_wrapper.client
        doc_processor = DocumentProcessor()
        json_processing_service = JsonProcessingService(client=openai_client, config={})

        # 2. Validate inputs
        if not intake_form:
            raise ValueError("An intake form is required for the analysis.")

        # Case documents are optional - intake form alone is sufficient for preliminary analysis
        if not case_documents or len(case_documents) == 0:
            logger.info(
                "No case documents provided - will process intake form only for preliminary analysis."
            )

        # 3. Process intake form to extract data
        logger.info("Processing intake form...")
        intake_files = [intake_form]
        processed_intake = await doc_processor.process_documents_from_streamlit(
            intake_files,
            intake_filenames=[intake_form.name if hasattr(intake_form, "name") else "intake.pdf"],
        )

        if not processed_intake:
            raise ValueError("Failed to process intake form.")

        intake_content = processed_intake[0].content
        logger.info(f"Intake form processed: {len(intake_content)} characters")

        # Log data context for quality assurance
        logger.info(f"CONTEXT CHECK - Intake preview: {intake_content[:200]}...")

        # 4. Process all case documents to extract text (if any provided)
        logger.info(f"Processing {len(case_documents)} case documents...")

        if case_documents:
            processed_case_docs = await doc_processor.process_documents_from_streamlit(
                case_documents, intake_filenames=[]
            )

            if not processed_case_docs:
                logger.warning(
                    "No case documents were successfully processed, but continuing with intake only."
                )
                processed_case_docs = []
        else:
            logger.info("No case documents provided - processing intake form only.")
            processed_case_docs = []

        logger.info(f"Processed {len(processed_case_docs)} case documents")

        # 5. AI Call #1: Generate contextual document summaries
        logger.info("AI Call #1: Generating document summaries with intake context...")
        logger.info(
            f"CONTEXT CHECK - Passing {len(intake_content)} chars of intake + {len(processed_case_docs)} docs to summarization"
        )

        document_summaries = await _generate_document_summaries(
            openai_client, intake_content, processed_case_docs
        )

        logger.info(f"Document summaries generated: {len(document_summaries)} characters")
        logger.info(f"CONTEXT CHECK - Summaries preview: {document_summaries[:200]}...")

        # 6. AI Call #2: Generate findings letter
        logger.info("AI Call #2: Generating findings letter...")
        logger.info(
            f"CONTEXT CHECK - Passing {len(intake_content)} chars intake + {len(document_summaries)} chars summaries to letter generation"
        )

        findings_letter_html = json_processing_service.generate_html_letter(
            intake_data=intake_content,
            document_summaries=document_summaries,
        )

        logger.info(f"CONTEXT CHECK - Generated letter length: {len(findings_letter_html)} chars")

        # 7. Calculate processing time
        processing_time = time.time() - start_time

        # 8. Create and return the result object
        logger.info(f"Successfully completed document processing in {processing_time:.2f}s")

        return ProcessingResult(
            main_letter=findings_letter_html,
            document_summaries=document_summaries,
            case_analysis=document_summaries,  # For backward compatibility
            status="completed",
            processing_time_seconds=processing_time,
            intake_content=intake_content,
            document_count=len(processed_case_docs),
            errors=errors,
        )

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


async def _generate_document_summaries(openai_client, intake_content: str, case_documents: list) -> str:
    """AI Call #1: Generate contextual summaries of case documents.

    Args:
    ----
        openai_client: OpenAI client instance
        intake_content: Extracted text from intake form
        case_documents: List of ProcessedDocument objects (can be empty)

    Returns:
    -------
        Formatted string containing document summaries (or intake-only analysis if no documents)
    """
    # Handle case with no documents - analyze intake form only
    if not case_documents:
        prompt = f"""You are a legal document analyst. Given the client intake information below, provide a comprehensive analysis of the case based solely on the intake information provided.

INTAKE INFORMATION:
{intake_content[:3000]}  # Limit intake to ~3000 chars to save tokens

---
OUTPUT FORMAT:
Based on the intake information, provide:
1. Case Overview (parties involved, nature of the dispute)
2. Key Facts and Timeline
3. Legal Issues Identified
4. Potential Claims or Defenses
5. Information Gaps (what additional documents would be helpful)

Keep the analysis thorough but concise. Focus on legally significant information.
"""
    else:
        # Build the summarization prompt for documents
        prompt = f"""You are a legal document analyst. Given the client intake information below, summarize the following case documents. Focus on key facts, dates, parties, amounts, obligations, issues, and evidence relevant to the case.

INTAKE INFORMATION:
{intake_content[:3000]}  # Limit intake to ~3000 chars to save tokens

---
CASE DOCUMENTS TO SUMMARIZE:

"""

        for i, doc in enumerate(case_documents, 1):
            prompt += f"\n--- Document {i}: {doc.file_name} ---\n"
            # Limit each document to reasonable size
            content_preview = doc.content[:8000] if len(doc.content) > 8000 else doc.content
            prompt += f"{content_preview}\n"

        prompt += """
---
OUTPUT FORMAT:
For each document, provide:
1. Document Name
2. Document Type (contract, correspondence, disclosure, evidence, etc.)
3. Key Facts (parties, dates, amounts, obligations)
4. Issues/Problems Identified
5. Relevance to Case

Keep summaries concise but thorough. Focus on legally significant information.
"""

    # Make the API call
    response = openai_client.chat.completions.create(
        model="gpt-4o",  # Use GPT-4o for fast, reliable, high-quality summarization
        messages=[
            {"role": "system", "content": "You are a precise legal document analyst."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4000,  # GPT-4o uses standard max_tokens parameter
        temperature=0.3,  # Consistent, professional output
    )

    return response.choices[0].message.content
