from __future__ import annotations

import asyncio
import mimetypes
import os
import re
from typing import Any, Callable, List, Optional

# Import from the backend utils (to be moved to root utils later)
from legal_portal.core.data_models import DocumentType, ProcessedDocument

# Maps file content types to their respective processing functions
from legal_portal.services.file_processors import PROCESSOR_MAP
from legal_portal.utils.logging_config import get_module_logger

# Import security functions for secure file handling
from legal_portal.utils.security import (
    MAX_FILE_SIZE,
    create_secure_temp_file,
    secure_filename,
    validate_file_content,
    validate_file_size,
)

logger = get_module_logger(__name__)


class DocumentProcessingError(Exception):
    """Custom exception for document processing errors."""


class DocumentProcessor:
    """A service class for processing uploaded documents.

    It identifies file types, categorizes them, and extracts content.
    Refactored to work as a standalone Python module without FastAPI dependencies.
    """

    def __init__(self):
        pass

    def _get_document_type(
        self, filename: str, intake_filenames: List[str], original_filename: str = None
    ) -> DocumentType:
        """Determine if a file is an intake form or a general case document.

        Enhanced with case-insensitive matching and keyword detection.

        Args:
        ----
            filename: The sanitized filename (may include hash suffix)
            intake_filenames: List of original intake form filenames
            original_filename: The original filename before sanitization (optional)

        Returns:
        -------
            DocumentType.INTAKE_FORM if the file is an intake form, otherwise DocumentType.CASE_DOCUMENT

        """
        # First check: Try with original filename if provided (case-insensitive)
        if original_filename:
            for intake_name in intake_filenames:
                if original_filename.lower() == intake_name.lower():
                    result = DocumentType.INTAKE_FORM
                    logger.info(
                        "Document categorization success - matched original filename",
                        extra={
                            "module": "document_processor",
                            "hypothesis_id": "document_categorization_success",
                            "original_filename": original_filename,
                            "sanitized_filename": filename,
                            "matched_intake": intake_name,
                            "assigned_type": result.name,
                            "action": "document_type_assignment",
                        },
                    )
                    return result

        # Second check: Direct match with sanitized filename (case-insensitive)
        for intake_name in intake_filenames:
            if filename.lower() == intake_name.lower():
                result = DocumentType.INTAKE_FORM
                logger.info(
                    "Document categorization success - direct match",
                    extra={
                        "module": "document_processor",
                        "hypothesis_id": "document_categorization_success",
                        "sanitized_filename": filename,
                        "matched_intake": intake_name,
                        "assigned_type": result.name,
                        "action": "document_type_assignment",
                    },
                )
                return result

        # Third check: Pattern matching for sanitized filenames
        # Sanitized filenames have format: original_name_with_underscores_hashcode.ext
        # We need to check if the base part matches any intake filename pattern

        # Extract the base part of the sanitized filename (remove hash suffix)
        # Hash is 8 characters: _a1b2c3d4
        match = re.match(r"^(.+?)_[a-f0-9]{8}(\.[^.]+)?$", filename)
        if match:
            base_part = match.group(1).lower()
            # extension is available in match.group(2) if needed for future enhancements

            # Check each intake filename to see if it could have produced this sanitized name
            for intake_name in intake_filenames:
                # Sanitize the intake filename the same way to compare
                # Simulate what secure_filename would do (without the hash)
                intake_base = re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.splitext(intake_name)[0])
                intake_base = intake_base.lstrip(".").rstrip(". ").lower()

                if base_part == intake_base or base_part.startswith(intake_base):
                    result = DocumentType.INTAKE_FORM
                    logger.info(
                        "Document categorization success - pattern match",
                        extra={
                            "module": "document_processor",
                            "hypothesis_id": "document_categorization_success",
                            "sanitized_filename": filename,
                            "matched_intake_pattern": intake_name,
                            "base_part": base_part,
                            "intake_base": intake_base,
                            "assigned_type": result.name,
                            "action": "document_type_assignment",
                        },
                    )
                    return result

        # Fourth check: Enhanced keyword-based detection for intake forms
        # Check if filename contains intake-related keywords
        intake_keywords = [
            "intake",
            "questionnaire",
            "assessment",
            "client_form",
            "client_info",
            "initial_form",
            "consultation",
            "new_client",
            "case_intake",
            "legal_intake",
        ]

        # Check both original and sanitized filenames for keywords
        filenames_to_check = [filename.lower()]
        if original_filename:
            filenames_to_check.append(original_filename.lower())

        for file_to_check in filenames_to_check:
            for keyword in intake_keywords:
                if keyword in file_to_check:
                    result = DocumentType.INTAKE_FORM
                    logger.info(
                        "Document categorization success - keyword match",
                        extra={
                            "module": "document_processor",
                            "hypothesis_id": "document_categorization_success",
                            "filename_checked": file_to_check,
                            "matched_keyword": keyword,
                            "assigned_type": result.name,
                            "action": "document_type_assignment",
                        },
                    )
                    return result

        # Default: Not an intake form
        result = DocumentType.CASE_DOCUMENT

        # DEBUG LOG: Track document categorization failure
        logger.info(
            "Document categorization debug - defaulting to case document",
            extra={
                "module": "document_processor",
                "hypothesis_id": "document_categorization_check",
                "sanitized_filename": filename,
                "original_filename": original_filename,
                "intake_filenames_list": intake_filenames,
                "filename_found_in_list": False,
                "assigned_type": result.name,
                "action": "document_type_assignment",
            },
        )

        return result

    async def process_documents_from_streamlit(
        self,
        streamlit_files: List[Any],
        intake_filenames: Optional[List[str]] = None,
        progress_callback: Optional[Callable] = None,  # Add progress_callback
    ) -> List[ProcessedDocument]:
        """Process a list of Streamlit UploadedFile objects with optimized batch processing for images."""
        total_docs = len(streamlit_files)

        # Separate images from other files for batch processing
        image_files = []
        non_image_files = []

        for file in streamlit_files:
            filename = file.name.lower() if hasattr(file, "name") else str(file).lower()
            if filename.endswith((".jpg", ".jpeg", ".png")):
                image_files.append(file)
            else:
                non_image_files.append(file)

        logger.info(
            f"Processing {total_docs} documents: {len(image_files)} images, {len(non_image_files)} non-images"
        )

        # Group images intelligently for batch processing
        from legal_portal.utils.helpers import group_images_intelligently

        image_groups = group_images_intelligently(image_files, max_per_group=3)

        logger.info(f"Grouped {len(image_files)} images into {len(image_groups)} batches")

        # Process all documents (batched images + individual non-images) in parallel
        all_tasks = []
        processed_docs_count = [0]  # Use list for mutable counter in nested function

        # Create tasks for image batches
        for batch_idx, image_group in enumerate(image_groups, 1):
            task = self._process_image_batch_wrapper(
                image_group,
                intake_filenames,
                batch_idx,
                len(image_groups),
                progress_callback,
                processed_docs_count,
                total_docs,
            )
            all_tasks.append(task)

        # Create tasks for non-image files
        for file in non_image_files:
            task = self._process_single_file_wrapper(
                file, intake_filenames, progress_callback, processed_docs_count, total_docs
            )
            all_tasks.append(task)

        # Execute all tasks in parallel
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # Flatten results and filter out errors
        processed_docs = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Document processing error: {result}")
            elif isinstance(result, list):
                # Batch result
                processed_docs.extend(result)
            elif result:
                # Single document result
                processed_docs.append(result)

        logger.info(f"Successfully processed {len(processed_docs)} out of {total_docs} documents")
        return processed_docs

    async def _process_single_file_wrapper(
        self, file, intake_filenames, progress_callback, processed_docs_count, total_docs
    ):
        """Wrap single file processing with progress tracking."""
        try:
            doc = await self._process_single_file(file, intake_filenames)
            if doc:
                processed_docs_count[0] += 1
                if progress_callback:
                    progress_callback(
                        message=(
                            f"Extracting content from document {processed_docs_count[0]} "
                            f"of {total_docs}..."
                        ),
                        docs_processed=[doc.file_name],
                        phase="document_extraction",
                        percent=int((processed_docs_count[0] / total_docs) * 15),
                    )
                return doc
        except Exception as e:
            logger.error(f"Error processing file {file.name if hasattr(file, 'name') else 'unknown'}: {e}")
            return None

    async def _process_image_batch_wrapper(
        self,
        image_group,
        intake_filenames,
        batch_idx,
        total_batches,
        progress_callback,
        processed_docs_count,
        total_docs,
    ):
        """Wrap batch image processing with progress tracking."""
        try:
            # Prepare image files for batch processing
            from legal_portal.services.file_processors.batch_vision_processor import process_images_batch

            image_info_list = []
            temp_files = []

            for img_file in image_group:
                try:
                    # Security validation and temp file creation
                    from legal_portal.utils.security import (
                        MAX_FILE_SIZE,
                        create_secure_temp_file,
                        secure_filename,
                        validate_file_content,
                        validate_file_size,
                    )

                    file_data = img_file.getvalue()
                    validate_file_size(file_data, MAX_FILE_SIZE)

                    original_name = img_file.name
                    sanitized_name = secure_filename(original_name)

                    mime_type, _ = validate_file_content(file_data, sanitized_name)
                    temp_path = create_secure_temp_file(file_data, sanitized_name)
                    temp_files.append(temp_path)

                    doc_type = self._get_document_type(sanitized_name, intake_filenames, original_name)
                    image_info_list.append((temp_path, doc_type, original_name))

                except Exception as e:
                    img_name = img_file.name if hasattr(img_file, "name") else "unknown"
                    logger.error(f"Error preparing image {img_name}: {e}")

            if not image_info_list:
                return []

            # Process batch
            logger.info(f"Processing image batch {batch_idx}/{total_batches} ({len(image_info_list)} images)")
            batch_results = await process_images_batch(image_info_list)

            # Update progress
            processed_docs_count[0] += len(batch_results)
            if progress_callback:
                progress_callback(
                    message=(
                        f"Processed image batch {batch_idx}/{total_batches} "
                        f"({len(batch_results)} images)..."
                    ),
                    docs_processed=[doc.file_name for doc in batch_results],
                    phase="document_extraction",
                    percent=int((processed_docs_count[0] / total_docs) * 15),
                )

            # Cleanup temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")

            return batch_results

        except Exception as e:
            logger.error(f"Error processing image batch {batch_idx}: {e}", exc_info=True)
            return []

    async def _process_single_file(
        self,
        uploaded_file,
        intake_filenames: List[str],
    ) -> Optional[ProcessedDocument]:
        """Process a single uploaded file.

        Args:
        ----
            uploaded_file: Streamlit UploadedFile object
            intake_filenames: List of filenames that should be treated as intake forms

        Returns:
        -------
            ProcessedDocument object if successful, None otherwise.

        """
        temp_files = []  # Track temp files for cleanup
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

                # DEBUG LOG: Track filename sanitization for intake form detection
                logger.info(
                    "Filename sanitization debug",
                    extra={
                        "module": "document_processor",
                        "hypothesis_id": "filename_sanitization_mismatch",
                        "original_filename": original_name,
                        "sanitized_filename": sanitized_name,
                        "action": "filename_sanitization",
                        "filename_changed": original_name != sanitized_name,
                    },
                )

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
                    },
                )

            except ValueError as e:
                logger.error(
                    f"Security validation failed for file '{uploaded_file.name}'",
                    extra={
                        "error": str(e),
                        "file_name": uploaded_file.name,
                    },
                )
                raise DocumentProcessingError(
                    f"Security validation failed for '{uploaded_file.name}': {e!s}"
                ) from e

            # TODO: Add PDF compression support for large files
            # if sanitized_name.lower().endswith('.pdf'):
            #     file = await self.pdf_compressor.compress_pdf_if_needed(file)

            # Pass original filename for proper intake form detection
            doc_type = self._get_document_type(sanitized_name, intake_filenames, original_name)
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
            processed_doc = await processor(temp_path, doc_type, sanitized_name)
            return processed_doc

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
            raise DocumentProcessingError(msg) from e

    async def process_documents(self, files, intake_filenames: List[str]) -> List[ProcessedDocument]:
        """Legacy method for backward compatibility.

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
                return await self.process_documents_from_streamlit(files, intake_filenames)
            else:
                msg = f"Unsupported file object type: {type(file)}"
                raise DocumentProcessingError(msg)

            # PDF compression logic removed in consolidation

            # For legacy method, we don't have the original filename separate from sanitized
            doc_type = self._get_document_type(filename, intake_filenames, filename)
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
        self,
        file_paths: List[str],
        intake_filenames: List[str],
        progress_callback: Optional[Callable] = None,
    ) -> List[ProcessedDocument]:
        """Process documents from file paths.

        Args:
        ----
            file_paths: List of file paths to process
            intake_filenames: List of filenames that should be treated as intake forms
            progress_callback: Optional callback for progress updates

        Returns:
        -------
            List of ProcessedDocument objects

        """
        processing_tasks = []
        total_docs = len(file_paths)
        processed_docs_count = [0]

        for file_path in file_paths:
            if not os.path.exists(file_path):
                msg = f"File not found: {file_path}"
                raise DocumentProcessingError(msg)

            # Ensure we only process files, not directories
            if not os.path.isfile(file_path):
                msg = f"Path is not a file: {file_path}"
                raise DocumentProcessingError(msg)

            filename = os.path.basename(file_path)
            # For file paths, the filename is already the original
            doc_type = self._get_document_type(filename, intake_filenames, filename)
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

        # Execute all tasks and collect results
        results = await asyncio.gather(*processing_tasks, return_exceptions=True)

        # Filter out errors and update progress
        processed_docs = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Document processing error: {result}")
            elif result:
                processed_docs.append(result)
                processed_docs_count[0] += 1
                if progress_callback:
                    progress_callback(
                        message=(
                            f"Extracted content from {processed_docs_count[0]} of "
                            f"{total_docs} documents..."
                        ),
                        docs_processed=[result.file_name],
                        phase="document_extraction",
                        percent=int((processed_docs_count[0] / total_docs) * 15),
                    )

        return processed_docs
