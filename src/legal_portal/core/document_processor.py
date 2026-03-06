from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from legal_portal.config.default import settings

# Import from the backend utils (to be moved to root utils later)
from legal_portal.core.data_models import DocumentType, ProcessedDocument
from legal_portal.services.file_compression_service import get_compression_service

# Maps file content types to their respective processing functions
from legal_portal.services.file_processors import PROCESSOR_MAP
from legal_portal.utils.blacklist import is_name_blacklisted
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

    def __init__(self, message: str, error_code: str = "PROCESSING_ERROR"):
        """Initialize with error message and code.

        Args:
        ----
            message: Human-readable error message
            error_code: Machine-readable error code for categorization

        """
        super().__init__(message)
        self.error_code = error_code


class ValidationError(DocumentProcessingError):
    """Validation-specific errors with categorization."""

    def __init__(self, message: str, error_code: str, file_size_mb: Optional[float] = None):
        """Initialize validation error.

        Args:
        ----
            message: Human-readable error message
            error_code: One of FILE_TOO_LARGE, INVALID_TYPE, CONTENT_VALIDATION, SECURITY_VIOLATION, CORRUPTED
            file_size_mb: File size in MB if relevant

        """
        super().__init__(message, error_code)
        self.file_size_mb = file_size_mb


class DocumentProcessor:
    """A service class for processing uploaded documents.

    It identifies file types, categorizes them, and extracts content.
    Refactored to work as a standalone Python module without FastAPI dependencies.
    """

    def __init__(self):
        """Initialize DocumentProcessor with compression service."""
        self.compression_service = get_compression_service()

    async def process_and_upload(
        self,
        file_content: bytes,
        filename: str,
        user_id: str,
        case_id: str,
        supabase_client,
        is_intake_form: bool = False,
        content_type: Optional[str] = None,
        skip_extraction: bool = False,
        blacklist: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Unified method to validate, compress, and upload a document.

        This method provides consistent validation, compression, and storage
        across both manual uploads and Clio imports.

        Args:
        ----
            file_content: Raw file bytes
            filename: Original filename
            user_id: User ID for storage path
            case_id: Case ID for storage path
            supabase_client: Supabase client for storage operations
            is_intake_form: Whether this is an intake form
            content_type: Optional MIME type override
            skip_extraction: If True, skip text extraction (useful for bulk imports
                           where extraction can be done on-demand later)
            blacklist: Optional list of blacklisted document names (case-insensitive)

        Returns:
        -------
            Document record dictionary with metadata

        Raises:
        ------
            ValidationError: If validation fails with categorized error code
            DocumentProcessingError: If processing fails

        """
        temp_files = []

        try:
            # 0. Check blacklist before doing any work
            if is_name_blacklisted(filename, blacklist):
                logger.info(f"Document '{filename}' matches blacklist rule, marking as SKIPPED.")
                from legal_portal.core.data_models import DocumentStatus

                return {
                    "case_id": case_id,
                    "file_name": filename,
                    "file_type": content_type or "unknown",
                    "file_size": len(file_content),
                    "storage_path": None,
                    "status": DocumentStatus.SKIPPED,
                    "metadata": {
                        "is_intake_form": is_intake_form,
                        "original_filename": filename,
                        "skipped_reason": "Blacklisted by user preference",
                    },
                    "extracted_text": None,
                    "extraction_method": "skipped",
                    "extraction_quality": "none",
                    "ocr_provider": None,
                    "extraction_error": "Document name is in user's blacklist.",
                    "page_count": None,
                    "extracted_at": datetime.utcnow().isoformat(),
                }

            # 1. Validate file size
            max_size = settings.max_file_size_mb * 1024 * 1024
            try:
                validate_file_size(file_content, max_size)
            except ValueError as e:
                raise ValidationError(
                    str(e), error_code="FILE_TOO_LARGE", file_size_mb=len(file_content) / (1024 * 1024)
                ) from e

            # 2. Sanitize filename and validate content
            original_name = filename
            sanitized_name = secure_filename(filename)

            try:
                mime_type, file_ext = validate_file_content(file_content, sanitized_name)
            except ValueError as e:
                error_msg = str(e)
                if "extension" in error_msg or "not allowed" in error_msg:
                    raise ValidationError(error_msg, error_code="INVALID_TYPE") from e
                elif "content type" in error_msg or "magic" in error_msg.lower():
                    raise ValidationError(error_msg, error_code="CONTENT_VALIDATION") from e
                else:
                    raise ValidationError(error_msg, error_code="SECURITY_VIOLATION") from e

            # Use provided content_type or detected mime_type
            final_content_type = content_type or mime_type

            # 3. Check if file is empty (corruption check)
            if len(file_content) == 0:
                raise ValidationError("Empty files are not allowed", error_code="CORRUPTED")

            logger.info(
                f"File validation passed: {sanitized_name}",
                extra={
                    "original_name": original_name,
                    "sanitized_name": sanitized_name,
                    "mime_type": mime_type,
                    "file_size": len(file_content),
                },
            )

            # 4. Compress if needed
            original_size = len(file_content)
            compression_meta = {
                "compressed": False,
                "original_size": original_size,
                "compressed_size": original_size,
                "compression_ratio": 1.0,
                "method": "none",
            }

            if self.compression_service.should_compress(original_size):
                try:
                    compression_result = self.compression_service.compress_file(
                        file_content, sanitized_name, final_content_type
                    )

                    if compression_result.was_compressed:
                        file_content = compression_result.compressed_data
                        compression_meta = {
                            "compressed": True,
                            "original_size": compression_result.original_size,
                            "compressed_size": compression_result.compressed_size,
                            "compression_ratio": compression_result.compression_ratio,
                            "method": compression_result.method_used,
                        }
                        logger.info(
                            f"Compressed {sanitized_name}: "
                            f"{original_size / (1024 * 1024):.2f}MB → "
                            f"{len(file_content) / (1024 * 1024):.2f}MB"
                        )
                except Exception as e:
                    logger.warning(f"Compression failed for {sanitized_name}: {e}, using original")

            # 5. Extract text (intelligent extraction with OCR fallback)
            # Skip extraction if requested (bulk imports can do extraction on-demand later)
            extracted_text = None
            extraction_method = "none"
            extraction_quality = "low"
            ocr_provider = None
            extraction_error = None
            page_count = None
            signature_detection = None

            if skip_extraction:
                # Mark for deferred extraction - faster bulk imports
                extraction_method = "deferred"
                extraction_quality = "pending"
                logger.info(f"Skipping text extraction for {sanitized_name} (deferred mode)")
            else:
                try:
                    # Create temporary file for text extraction
                    temp_path = create_secure_temp_file(file_content, sanitized_name)
                    temp_files.append(temp_path)

                    # Get the appropriate processor from PROCESSOR_MAP
                    from legal_portal.services.file_processors import PROCESSOR_MAP

                    processor = PROCESSOR_MAP.get(final_content_type)

                    # Fallback for incorrect mimetypes using sanitized name
                    if not processor:
                        if sanitized_name.lower().endswith(".pdf"):
                            processor = PROCESSOR_MAP.get("application/pdf")
                        elif sanitized_name.lower().endswith(".docx"):
                            processor = PROCESSOR_MAP.get(
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            )
                        elif sanitized_name.lower().endswith(".doc"):
                            processor = PROCESSOR_MAP.get("application/msword")
                        elif sanitized_name.lower().endswith(".txt"):
                            processor = PROCESSOR_MAP.get("text/plain")

                    if processor:
                        # Determine doc type for extraction
                        doc_type = DocumentType.CASE_DOCUMENT
                        if is_intake_form:
                            doc_type = DocumentType.INTAKE_FORM

                        # Call processor with progress callback
                        processed_doc = await processor(temp_path, doc_type, original_name, None)
                        extracted_text = processed_doc.content
                        extraction_method = processed_doc.extraction_method or "unknown"
                        extraction_quality = processed_doc.extraction_quality or "high"
                        ocr_provider = processed_doc.ocr_provider
                        extraction_error = processed_doc.extraction_error
                        page_count = processed_doc.page_count
                        signature_detection = processed_doc.signature_detection
                    else:
                        # Legacy fallback for unsupported types
                        from legal_portal.api.utils.content_extractor import (
                            DocumentProcessor as ContentExtractor,
                        )

                        extracted_text = ContentExtractor.extract_text(
                            file_content, final_content_type, sanitized_name
                        )
                        extraction_method = "basic"

                    # Clean extracted text (remove null bytes for PostgreSQL)
                    if extracted_text:
                        extracted_text = extracted_text.replace("\x00", "").replace("\u0000", "")
                except Exception as e:
                    logger.warning(f"Text extraction failed for {sanitized_name}: {e}")
                    extraction_error = str(e)

            # 6. Upload to Supabase Storage
            file_extension = sanitized_name.split(".")[-1] if "." in sanitized_name else ""
            unique_filename = f"{uuid.uuid4()}.{file_extension}" if file_extension else str(uuid.uuid4())
            storage_path = f"{user_id}/{case_id}/{unique_filename}"

            logger.info(f"Uploading to storage: {storage_path}")
            supabase_client.storage.from_("documents").upload(
                storage_path, file_content, {"content-type": final_content_type}
            )

            # 7. Create document record
            file_size = len(file_content)
            metadata = {
                "is_intake_form": is_intake_form,
                "compression": compression_meta,
                "original_filename": original_name,
            }
            if signature_detection:
                metadata["signature_detection"] = signature_detection

            # Import DocumentStatus
            from legal_portal.core.data_models import DocumentStatus

            # Determine status based on text content quality
            status = DocumentStatus.READY
            if extraction_method == "deferred":
                # Deferred extraction - mark as ready (file is uploaded, extraction later)
                status = DocumentStatus.READY
            elif not extracted_text or len(extracted_text.strip()) == 0:
                status = DocumentStatus.EXTRACTION_FAILED
                extraction_quality = "low"
            elif len(extracted_text.strip()) < 200:
                status = DocumentStatus.NEEDS_REVIEW
                extraction_quality = "medium"
            else:
                status = DocumentStatus.READY
                extraction_quality = "high"

            doc_record = {
                "case_id": case_id,
                "file_name": original_name,
                "file_type": final_content_type,
                "file_size": file_size,
                "storage_path": storage_path,
                "status": status,
                "metadata": metadata,
                "extracted_text": extracted_text,
                "extraction_method": extraction_method,
                "extraction_quality": extraction_quality,
                "ocr_provider": ocr_provider,
                "extraction_error": extraction_error,
                "page_count": page_count,
                "extracted_at": datetime.utcnow().isoformat(),
            }

            logger.info(f"Document processed successfully: {original_name} (status: {status})")
            return doc_record

        except ValidationError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            # Wrap other errors
            logger.error(f"Error in process_and_upload for {filename}: {e}", exc_info=True)
            raise DocumentProcessingError(
                f"Failed to process document '{filename}': {str(e)}", error_code="PROCESSING_ERROR"
            ) from e
        finally:
            # Cleanup temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")

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

    async def process_uploaded_files(
        self,
        uploaded_files: List[Any],
        intake_filenames: Optional[List[str]] = None,
        progress_callback: Optional[Callable] = None,  # Add progress_callback
    ) -> List[ProcessedDocument]:
        """Process a list of uploaded file objects with optimized image batching."""
        total_docs = len(uploaded_files)

        # Separate images from other files for batch processing
        image_files = []
        non_image_files = []

        for file in uploaded_files:
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
                    await progress_callback(
                        message=(
                            f"Extracting content from document {processed_docs_count[0]} of {total_docs}..."
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
            from legal_portal.config.default import get_settings
            from legal_portal.core.data_models import FileMetadata, FileType

            _settings = get_settings()

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

            # Process images individually via OCR service or local fallback
            logger.info(f"Processing image batch {batch_idx}/{total_batches} ({len(image_info_list)} images)")
            batch_results = []
            for (temp_path, doc_type, original_name) in image_info_list:
                try:
                    with open(temp_path, "rb") as f:
                        img_bytes = f.read()
                    content_type, _ = mimetypes.guess_type(temp_path)
                    content_type = content_type or "image/png"

                    if _settings.ocr_remote_enabled:
                        from legal_portal.utils.ocr_service_client import get_ocr_client
                        ocr_client = get_ocr_client()
                        result = await ocr_client.extract_text(
                            img_bytes, original_name, content_type,
                        )
                        text_content = result["full_text"]
                        extraction_method = f"cloud_run_ocr ({result['provider']})"
                    else:
                        # Local fallback (emergency only)
                        from legal_portal.services.file_processors.image_processor import process_image
                        doc = await process_image(
                            temp_path, doc_type, original_name,
                        )
                        text_content = doc.content
                        extraction_method = "local_image_processor"

                    batch_results.append(ProcessedDocument(
                        file_name=original_name,
                        content=text_content,
                        document_type=doc_type,
                        file_type=FileType.IMAGE,
                        metadata=FileMetadata(
                            file_name=original_name,
                            file_type=FileType.IMAGE,
                            file_size=len(img_bytes),
                        ),
                        extraction_method=extraction_method,
                    ))
                except Exception as e:
                    logger.error(f"Error processing image {original_name}: {e}", exc_info=True)

            # Update progress
            processed_docs_count[0] += len(batch_results)
            if progress_callback:
                await progress_callback(
                    message=(
                        f"Processed image batch {batch_idx}/{total_batches} ({len(batch_results)} images)..."
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
        progress_callback: Optional[Callable] = None,
    ) -> Optional[ProcessedDocument]:
        """Process a single uploaded file.

        Args:
        ----
            uploaded_file: Uploaded file object
            intake_filenames: List of filenames that should be treated as intake forms
            progress_callback: Optional callback for granular progress updates

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

            # Use sanitized name for processing with optional progress callback
            processed_doc = await processor(temp_path, doc_type, sanitized_name, progress_callback)
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
                # Generic uploaded file object
                return await self.process_uploaded_files(files, intake_filenames)
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

            # Pass None for progress_callback in legacy method
            processing_tasks.append(processor(file_path, doc_type, filename, None))

        return await asyncio.gather(*processing_tasks)

    async def process_documents_from_paths(
        self,
        file_paths: List[str],
        intake_filenames: List[str],
        progress_callback: Optional[Callable] = None,
        path_to_id_map: Optional[Dict[str, str]] = None,
    ) -> List[ProcessedDocument]:
        """Process documents from file paths.

        Args:
        ----
            file_paths: List of file paths to process
            intake_filenames: List of filenames that should be treated as intake forms
            progress_callback: Optional callback for progress updates
            path_to_id_map: Optional mapping of file_path to document_id for DB updates

        Returns:
        -------
            List of ProcessedDocument objects

        """
        total_docs = len(file_paths)
        processed_docs_count = [0]

        # Create a processor-level callback wrapper that reports granular progress
        async def create_processor_callback(filename: str):
            """Create a callback wrapper for individual processor progress updates."""

            async def processor_progress(message: str, sub_step: Optional[str] = None):
                if progress_callback:
                    try:
                        await progress_callback(
                            message=message,
                            docs_processed=[filename],
                            phase="document_extraction",
                            percent=int((processed_docs_count[0] / total_docs) * 15),
                            sub_step=sub_step,
                        )
                    except TypeError:
                        # Fallback if callback doesn't support sub_step
                        await progress_callback(
                            message=message,
                            docs_processed=[filename],
                            phase="document_extraction",
                            percent=int((processed_docs_count[0] / total_docs) * 15),
                        )

            return processor_progress

        # Process documents with progress callbacks
        async def process_single_path(file_path: str):
            """Process a single file path with progress tracking."""
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

            # Create processor-level callback for granular progress
            proc_callback = await create_processor_callback(filename)

            # Call processor with progress callback
            processed_doc = await processor(file_path, doc_type, filename, proc_callback)

            # Link back to document record if ID is provided
            if path_to_id_map and file_path in path_to_id_map:
                processed_doc.document_id = path_to_id_map[file_path]

            return processed_doc

        # Execute all tasks and collect results
        processing_tasks = [process_single_path(fp) for fp in file_paths]
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
                    try:
                        msg = (
                            f"Extracted content from {processed_docs_count[0]} "
                            f"of {total_docs} documents..."
                        )
                        await progress_callback(
                            message=msg,
                            docs_processed=[result.file_name],
                            phase="document_extraction",
                            percent=int((processed_docs_count[0] / total_docs) * 15),
                        )
                    except Exception as e:
                        logger.warning(f"Progress callback error: {e}")

        return processed_docs
