from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from fastapi import HTTPException

from backend_logic.ai import AIAnalyzer
from backend.services.email_generator import EmailGenerator
from backend.utils.data_models import (
    AnalysisError,
    AnalyzedDocument,
    CaseResults,
    DocumentType,
    SavedDocument,
)


if TYPE_CHECKING:
    from openai import OpenAI

    from backend.services.document_processor import DocumentProcessor
    from backend.services.task_manager import TaskManager


async def process_documents_async(
    task_id: str,
    saved_documents: list[SavedDocument],
    client: OpenAI,
    doc_processor: DocumentProcessor,
    task_manager: TaskManager,
    temp_dir_path: str,
    intake_filename: str,
) -> None:
    """
    Asynchronously processes documents, updates task status, and stores the final result.
    """
    ai_analyzer = AIAnalyzer(client, doc_processor)
    email_generator = EmailGenerator(client)

    try:
        task_manager.update_task_progress(task_id, 10, "Processing documents")

        # Determine which document is the intake form
        intake_docs_saved = [
            doc for doc in saved_documents if doc.original_filename == intake_filename
        ]
        if not intake_docs_saved:
            raise HTTPException(
                status_code=400, detail="Intake form is required but was not found."
            )

        intake_docs_saved[0]

        [doc for doc in saved_documents if doc.original_filename != intake_filename]

        processed_docs = await doc_processor.process_documents(
            saved_documents, intake_filename
        )

        intake_doc = next(
            (
                doc
                for doc in processed_docs
                if doc.document_type == DocumentType.INTAKE_FORM
            ),
            None,
        )
        other_docs = [
            doc
            for doc in processed_docs
            if doc.document_type == DocumentType.CASE_DOCUMENT
        ]

        if not intake_doc:
            raise HTTPException(
                status_code=400, detail="Intake form is required but was not found."
            )

        task_manager.update_task_progress(task_id, 25, "Analyzing intake form")
        analysis_result = await ai_analyzer.analyze_intake(intake_doc)
        if not analysis_result.intake_analysis:
            msg = "Failed to analyze intake form."
            raise RuntimeError(msg)

        task_manager.update_task_progress(task_id, 50, "Analyzing case documents")
        case_analysis_results = await ai_analyzer.analyze_case_documents(
            other_docs, analysis_result.intake_analysis
        )
        for res in case_analysis_results:
            if isinstance(res, AnalyzedDocument):
                analysis_result.analyzed_documents.append(res)
            elif isinstance(res, AnalysisError):
                analysis_result.errors.append(res)

        task_manager.update_task_progress(task_id, 75, "Performing final assessment")
        final_analysis = await ai_analyzer.perform_final_assessment(analysis_result)

        task_manager.update_task_progress(task_id, 90, "Generating email")
        email_response = email_generator.generate_email_and_analysis_docs(
            final_analysis
        )

        final_result = CaseResults(analysis=final_analysis, email=email_response)
        task_manager.complete_task(task_id, final_result)

    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        print(error_message)
        task_manager.fail_task(task_id, error_message)
    finally:
        shutil.rmtree(temp_dir_path)
