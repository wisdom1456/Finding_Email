from __future__ import annotations

import asyncio
import mimetypes
import os
from typing import List

# Import from the backend utils (to be moved to root utils later)
from backend.utils.data_models import DocumentType, ProcessedDocument

# Maps file content types to their respective processing functions
from backend.utils.file_processors import PROCESSOR_MAP


class DocumentProcessingError(Exception):
    """Custom exception for document processing errors."""


class DocumentProcessor:
    """
    A service class for processing uploaded documents.
    It identifies file types, categorizes them, and extracts content.

    Refactored to work as a standalone Python module without FastAPI dependencies.
    """

    def __init__(self):
        pass

    def _get_document_type(
        self, filename: str, intake_filenames: List[str]
    ) -> DocumentType:
        """Determines if a file is an intake form or a general case document."""
        if filename in intake_filenames:
            return DocumentType.INTAKE_FORM
        return DocumentType.CASE_DOCUMENT

    async def process_documents_from_streamlit(
        self, uploaded_files, intake_filenames: List[str]
    ) -> List[ProcessedDocument]:
        """
        Process documents directly from Streamlit file uploads.

        Args:
            uploaded_files: List of Streamlit UploadedFile objects
            intake_filenames: List of filenames that should be treated as intake forms

        Returns:
            List of ProcessedDocument objects
        """
        processing_tasks = []

        for uploaded_file in uploaded_files:
            temp_path = f"/tmp/{uploaded_file.name}"
            try:
                # Save uploaded file temporarily for processing
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getvalue())

                # TODO: Add PDF compression support for large files
                # if uploaded_file.name.lower().endswith('.pdf'):
                #     file = await self.pdf_compressor.compress_pdf_if_needed(file)

                doc_type = self._get_document_type(uploaded_file.name, intake_filenames)
                content_type, _ = mimetypes.guess_type(uploaded_file.name)

                processor = PROCESSOR_MAP.get(content_type)
                if not processor:
                    # Fallback for incorrect mimetypes
                    if uploaded_file.name.endswith(".pdf"):
                        processor = PROCESSOR_MAP.get("application/pdf")
                    elif uploaded_file.name.endswith(".docx"):
                        processor = PROCESSOR_MAP.get(
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    elif uploaded_file.name.endswith(".doc"):
                        processor = PROCESSOR_MAP.get("application/msword")
                    elif uploaded_file.name.endswith(".txt"):
                        processor = PROCESSOR_MAP.get("text/plain")
                    elif uploaded_file.name.endswith(".eml"):
                        processor = PROCESSOR_MAP.get("message/rfc822")

                if not processor:
                    msg = f"No processor available for file '{uploaded_file.name}' with content type '{content_type}'"
                    raise DocumentProcessingError(msg)

                processing_tasks.append(
                    processor(temp_path, doc_type, uploaded_file.name)
                )

            except Exception as e:
                # Clean up temp file on error
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                msg = f"Error processing file '{uploaded_file.name}': {e!s}"
                raise DocumentProcessingError(msg)

        try:
            return await asyncio.gather(*processing_tasks)
        finally:
            # Clean up temporary files
            for uploaded_file in uploaded_files:
                temp_path = f"/tmp/{uploaded_file.name}"
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    async def process_documents(
        self, files, intake_filenames: List[str]
    ) -> List[ProcessedDocument]:
        """
        Legacy method for backward compatibility.
        This can be used with SavedDocument objects or adapted for other file sources.
        """
        processing_tasks = []
        for file in files:
            # Handle different file object types
            if hasattr(file, "file_path"):
                # SavedDocument object
                file_path = file.file_path
                filename = file.original_filename
            elif hasattr(file, "name"):
                # Streamlit UploadedFile object
                return await self.process_documents_from_streamlit(
                    files, intake_filenames
                )
            else:
                msg = f"Unsupported file object type: {type(file)}"
                raise DocumentProcessingError(msg)

            # PDF compression logic removed in consolidation

            doc_type = self._get_document_type(filename, intake_filenames)
            content_type, _ = mimetypes.guess_type(file_path)

            processor = PROCESSOR_MAP.get(content_type)
            if not processor:
                # Fallback for incorrect mimetypes
                if filename.endswith(".pdf"):
                    processor = PROCESSOR_MAP.get("application/pdf")
                elif filename.endswith(".docx"):
                    processor = PROCESSOR_MAP.get(
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                elif filename.endswith(".doc"):
                    processor = PROCESSOR_MAP.get("application/msword")
                elif filename.endswith(".txt"):
                    processor = PROCESSOR_MAP.get("text/plain")
                elif filename.endswith(".eml"):
                    processor = PROCESSOR_MAP.get("message/rfc822")

            if not processor:
                msg = f"No processor available for file '{filename}' with content type '{content_type}'"
                raise DocumentProcessingError(msg)

            processing_tasks.append(processor(file_path, doc_type, filename))

        return await asyncio.gather(*processing_tasks)

    async def process_documents_from_paths(
        self, file_paths: List[str], intake_filenames: List[str]
    ) -> List[ProcessedDocument]:
        """
        Process documents from file paths.

        Args:
            file_paths: List of file paths to process
            intake_filenames: List of filenames that should be treated as intake forms

        Returns:
            List of ProcessedDocument objects
        """
        processing_tasks = []

        for file_path in file_paths:
            if not os.path.exists(file_path):
                msg = f"File not found: {file_path}"
                raise DocumentProcessingError(msg)

            # Ensure we only process files, not directories
            if not os.path.isfile(file_path):
                msg = f"Path is not a file: {file_path}"
                raise DocumentProcessingError(msg)

            filename = os.path.basename(file_path)
            doc_type = self._get_document_type(filename, intake_filenames)
            content_type, _ = mimetypes.guess_type(file_path)

            processor = PROCESSOR_MAP.get(content_type)
            if not processor:
                # Fallback for incorrect mimetypes
                if filename.endswith(".pdf"):
                    processor = PROCESSOR_MAP.get("application/pdf")
                elif filename.endswith(".docx"):
                    processor = PROCESSOR_MAP.get(
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                elif filename.endswith(".doc"):
                    processor = PROCESSOR_MAP.get("application/msword")
                elif filename.endswith(".txt"):
                    processor = PROCESSOR_MAP.get("text/plain")
                elif filename.endswith(".eml"):
                    processor = PROCESSOR_MAP.get("message/rfc822")

            if not processor:
                msg = f"No processor available for file '{filename}' with content type '{content_type}'"
                raise DocumentProcessingError(msg)

            processing_tasks.append(processor(file_path, doc_type, filename))

        return await asyncio.gather(*processing_tasks)
