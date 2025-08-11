from __future__ import annotations

import asyncio
import mimetypes
import os
import tempfile
from typing import List

# Import from the backend utils (to be moved to root utils later)
from backend.utils.data_models import DocumentType, ProcessedDocument

# Maps file content types to their respective processing functions
from backend.utils.file_processors import PROCESSOR_MAP

# Import security functions for secure file handling
from backend_logic.utils.security import (
    secure_filename,
    validate_file_size,
    validate_file_content,
    create_secure_temp_file,
    MAX_FILE_SIZE
)
from backend_logic.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


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
        # H3 DEBUG: Document classification entry (OLD logic)
        import json
        logger.info(
            f"DEBUG_H3: {json.dumps({'module': 'backend_logic.document_processor', 'hypothesis_id': 'H3', 'action': 'classification_entry', 'line': 44, 'filename': filename, 'intake_filenames': intake_filenames, 'architecture': 'OLD_FastAPI'})}"
        )
        
        classification_result = DocumentType.INTAKE_FORM if filename in intake_filenames else DocumentType.CASE_DOCUMENT
        
        # H3 DEBUG: Document classification exit (OLD logic)
        logger.info(
            f"DEBUG_H3: {json.dumps({'module': 'backend_logic.document_processor', 'hypothesis_id': 'H3', 'action': 'classification_exit', 'line': 49, 'filename': filename, 'result': classification_result.name, 'match_found': filename in intake_filenames, 'architecture': 'OLD_FastAPI'})}"
        )
        
        return classification_result

    async def process_documents_from_streamlit(
        self, uploaded_files, intake_filenames: List[str]
    ) -> List[ProcessedDocument]:
        """
        Process documents directly from Streamlit file uploads with enhanced security.

        Security features:
        - Secure filename sanitization to prevent path traversal
        - File size validation and enforcement
        - Content type validation with magic number detection
        - Secure temporary file creation with restricted permissions

        Args:
            uploaded_files: List of Streamlit UploadedFile objects
            intake_filenames: List of filenames that should be treated as intake forms

        Returns:
            List of ProcessedDocument objects
        """
        processing_tasks = []
        temp_files = []  # Track temp files for cleanup

        for uploaded_file in uploaded_files:
            try:
                # Read file data
                file_data = uploaded_file.getvalue()
                
                # Apply security validations
                try:
                    # Validate file size
                    validate_file_size(file_data, MAX_FILE_SIZE)
                    
                    # Sanitize filename
                    original_name = uploaded_file.name
                    sanitized_name = secure_filename(original_name)
                    
                    # Validate content type
                    mime_type, file_ext = validate_file_content(file_data, sanitized_name)
                    
                    # Create secure temporary file
                    temp_path = create_secure_temp_file(file_data, sanitized_name)
                    temp_files.append(temp_path)
                    
                    logger.info(
                        "File passed security validation",
                        extra={
                            "original_name": original_name,
                            "sanitized_name": sanitized_name,
                            "mime_type": mime_type,
                            "file_size": len(file_data),
                        }
                    )
                    
                except ValueError as e:
                    logger.error(
                        f"Security validation failed for file '{uploaded_file.name}'",
                        extra={
                            "error": str(e),
                            "file_name": uploaded_file.name,
                        }
                    )
                    raise DocumentProcessingError(
                        f"Security validation failed for '{uploaded_file.name}': {str(e)}"
                    )

                # TODO: Add PDF compression support for large files
                # if sanitized_name.lower().endswith('.pdf'):
                #     file = await self.pdf_compressor.compress_pdf_if_needed(file)

                doc_type = self._get_document_type(sanitized_name, intake_filenames)
                content_type, _ = mimetypes.guess_type(sanitized_name)

                processor = PROCESSOR_MAP.get(content_type)
                if not processor:
                    # Fallback for incorrect mimetypes using sanitized name
                    if sanitized_name.endswith(".pdf"):
                        processor = PROCESSOR_MAP.get("application/pdf")
                    elif sanitized_name.endswith(".docx"):
                        processor = PROCESSOR_MAP.get(
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    elif sanitized_name.endswith(".doc"):
                        processor = PROCESSOR_MAP.get("application/msword")
                    elif sanitized_name.endswith(".txt"):
                        processor = PROCESSOR_MAP.get("text/plain")
                    elif sanitized_name.endswith(".eml"):
                        processor = PROCESSOR_MAP.get("message/rfc822")

                if not processor:
                    msg = f"No processor available for file '{sanitized_name}' with content type '{content_type}'"
                    raise DocumentProcessingError(msg)

                # Use sanitized name for processing
                processing_tasks.append(
                    processor(temp_path, doc_type, sanitized_name)
                )

            except Exception as e:
                # Clean up temp files on error
                for temp_file in temp_files:
                    if os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except OSError:
                            pass  # Best effort cleanup
                            
                msg = f"Error processing file '{uploaded_file.name}': {e!s}"
                logger.error(msg, extra={"error": str(e), "file_name": uploaded_file.name})
                raise DocumentProcessingError(msg)

        try:
            return await asyncio.gather(*processing_tasks)
        finally:
            # Clean up all temporary files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError as e:
                        logger.warning(
                            f"Failed to remove temporary file",
                            extra={"temp_file": temp_file, "error": str(e)}
                        )

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
