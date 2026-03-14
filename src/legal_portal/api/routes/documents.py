"""Document management endpoints."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.utils.content_extractor import DocumentProcessor as ContentExtractor
from legal_portal.core.data_models import DocumentStatus, DocumentType, FileMetadata, FileType, ProcessedDocument
from legal_portal.core.document_processor import DocumentProcessor, ValidationError
from legal_portal.services.document_registry_service import DocumentRegistryService
from legal_portal.services.file_processors.eml_processor import process_eml
from legal_portal.utils.google_vision_client import GoogleVisionClient
from legal_portal.api.middleware.retry import is_transient_supabase_error, retry_async
from legal_portal.utils.security import sanitize_text_for_db

router = APIRouter()
logger = logging.getLogger(__name__)

# Caps concurrent Supabase load from extraction to 3 simultaneous calls regardless
# of how many tabs or users are triggering extractions at once.
EXTRACTION_SEMAPHORE = asyncio.Semaphore(3)

# Map MIME content types to FileType enum values for registry construction
_MIME_TO_FILETYPE = {
    "application/pdf": FileType.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileType.DOCX,
    "application/msword": FileType.DOC,
    "text/plain": FileType.TXT,
    "text/csv": FileType.CSV,
    "message/rfc822": FileType.EML,
    "image/jpeg": FileType.JPG,
    "image/png": FileType.PNG,
    "image/gif": FileType.GIF,
    "image/bmp": FileType.BMP,
    "image/tiff": FileType.TIFF,
}


def _build_and_persist_registry(
    *,
    document_id: str,
    file_name: str,
    file_type: str,
    extracted_text: str,
    extraction_quality: str,
    extraction_method: str,
    signature_detection: Optional[Dict[str, Any]],
    supabase_client: Any,
) -> None:
    """Build initial registry from extraction data and persist to DB.

    Called after text extraction succeeds during upload or deferred extraction.
    """
    ft = _MIME_TO_FILETYPE.get(file_type, FileType.PDF)
    pdoc = ProcessedDocument(
        file_name=file_name,
        content=extracted_text or "",
        document_type=DocumentType.CASE_DOCUMENT,
        file_type=ft,
        metadata=FileMetadata(file_name=file_name, file_type=ft, file_size=0),
        document_id=document_id,
        extraction_quality=extraction_quality,
        extraction_method=extraction_method,
        signature_detection=signature_detection,
    )
    service = DocumentRegistryService()
    registry = service.build_initial_registry(pdoc)
    service.persist_to_document(document_id, registry, supabase_client)
    logger.info(f"Registry built for {document_id}: type={registry.get('document_type')}, "
                f"sig_expected={registry.get('signature_expected')}")


async def _update_document_with_retry(
    user_supabase, document_id: str, update_data: dict, max_attempts: int = 3
):
    """Update a document row with retry on transient Supabase errors."""
    try:
        return await retry_async(
            lambda: user_supabase.table("documents").update(update_data).eq("id", document_id).execute(),
            max_attempts=max_attempts,
            context_label=f"documents update for {document_id}",
        )
    except Exception as db_err:
        logger.error(f"Database update failed for document {document_id}: {db_err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save extraction results to database. Please try again.",
        )


class BulkDeleteRequest(BaseModel):
    """Request model for bulk delete operation."""

    document_ids: List[str]


class BulkDeleteResponse(BaseModel):
    """Response model for bulk delete operation."""

    deleted_count: int
    failed_ids: List[str]
    errors: List[str]


class BulkExtractRequest(BaseModel):
    """Request model for bulk extraction operation."""

    case_id: str
    batch_size: int = 20   # Max documents to process per invocation (prevents Vercel timeout)
    offset: int = 0        # Start index for pagination across calls


class BulkExtractResponse(BaseModel):
    """Response model for bulk extraction operation."""

    extracted_count: int
    failed_count: int
    errors: List[str]
    has_more: bool = False    # True if more documents remain beyond this batch
    next_offset: int = 0      # Offset to pass in the next call when has_more is True
    total_queued: int = 0     # Total documents found before applying offset/batch_size


class VerifyDocumentRequest(BaseModel):
    """Request model for verifying/correcting document text."""

    manual_text: Optional[str] = None
    is_verified: bool = True
    is_flagged_as_junk: bool = False
    signature_verification: Optional[str] = None
    signature_verification_notes: Optional[str] = None
    signature_signing_date: Optional[str] = None
    signature_signer_names: Optional[List[str]] = None
    # Enrichment fields for attorney input
    document_type_override: Optional[str] = None
    relevance_level: Optional[str] = None  # "critical" | "supporting" | "background"
    key_facts: Optional[Dict[str, Any]] = None
    attorney_notes: Optional[str] = None
    document_relationships: Optional[List[Dict[str, str]]] = None


class DocumentResponse(BaseModel):
    """Response model for a document."""

    id: str
    case_id: str
    file_name: str
    file_type: str
    file_size: int
    storage_path: Optional[str] = None
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    is_verified: bool = False
    is_flagged_as_junk: bool = False
    extracted_text: Optional[str] = None
    manual_text: Optional[str] = None
    extraction_method: Optional[str] = None
    extraction_quality: Optional[str] = None
    extraction_error: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    case_id: str = Form(...),
    file: UploadFile = File(...),
    is_intake_form: bool = Form(False),
    extract_immediately: bool = Form(True),
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Upload a document for a case with unified validation and compression.

    Args:
    ----
        case_id: ID of the case this document belongs to
        file: File to upload
        is_intake_form: Whether this is an intake form
        extract_immediately: Whether to extract text immediately after upload (default: True)
        user: Current authenticated user
        user_supabase: User-scoped Supabase client (for RLS)
        service_supabase: Service-scoped Supabase client (bypasses RLS)

    Returns:
    -------
        Created document metadata

    Raises:
    ------
        400: Validation error (size, type, content, security)
        404: Case not found
        500: Server error

    """
    import os
    import tempfile

    from legal_portal.services.file_processors.pdf_processor import process_pdf

    try:
        logger.debug(
            f"Upload document: user={user['id']}, case={case_id}, "
            f"file={file.filename}, type={file.content_type}"
        )

        # Verify case ownership (use user client for RLS)
        logger.debug("Verifying case ownership...")
        case_response = (
            user_supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )
        logger.debug(f"Case found: {bool(case_response.data)}")

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Fetch user profile for blacklist
        profile_response = service_supabase.table("profiles").select("ai_preferences").eq("id", user["id"]).execute()
        blacklist = []
        if profile_response.data and profile_response.data[0].get("ai_preferences"):
            blacklist = profile_response.data[0]["ai_preferences"].get("blacklisted_documents", [])

        # Read file content
        file_content = await file.read()
        logger.debug(f"File size: {len(file_content)} bytes")

        # Use unified processor for validation, compression, and upload
        processor = DocumentProcessor()

        try:
            doc_record = await processor.process_and_upload(
                file_content=file_content,
                filename=file.filename,
                user_id=user["id"],
                case_id=case_id,
                supabase_client=service_supabase,
                is_intake_form=is_intake_form,
                content_type=file.content_type,
                blacklist=blacklist,
            )
        except ValidationError as e:
            # Return structured validation error
            error_response = {
                "code": e.error_code,
                "detail": str(e),
                "file_name": file.filename,
                "file_size_mb": e.file_size_mb,
            }
            logger.warning(f"Validation error: {e.error_code} - {str(e)}")
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_response)

        # Add classification to metadata
        classification = classify_document_type(file.filename, file.content_type)
        if "metadata" not in doc_record:
            doc_record["metadata"] = {}
        doc_record["metadata"]["classification"] = classification
        logger.debug(f"Classified document as {classification}: {file.filename}")

        # Create document record in database (use user client for RLS)
        logger.debug("Creating document record in database...")
        doc_response = user_supabase.table("documents").insert(doc_record).execute()

        if not doc_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create document record"
            )

        created_doc = doc_response.data[0]
        document_id = created_doc["id"]
        logger.info(f"Document uploaded successfully: {document_id}")

        # Immediate text extraction (non-blocking approach - extract in background)
        if extract_immediately:
            try:
                file_type = doc_record.get("file_type", file.content_type)
                file_name = doc_record.get("file_name", file.filename)

                extracted_text = ""
                extraction_method = ""
                extraction_quality = "high"
                ocr_provider = None
                extraction_error = None
                page_count = None
                signature_detection = None

                if file_type in ["application/pdf", "pdf"] or file_name.lower().endswith(".pdf"):
                    # Write to temp file for PDF processing
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(file_content)
                        tmp_path = tmp.name

                    try:
                        result = await process_pdf(
                            file_path=tmp_path,
                            document_type=DocumentType.CASE_DOCUMENT,
                            original_filename=file_name,
                        )
                        extracted_text = result.content
                        extraction_method = result.extraction_method or "unknown"
                        extraction_quality = result.extraction_quality or "high"
                        ocr_provider = result.ocr_provider
                        extraction_error = result.extraction_error
                        page_count = result.page_count
                        signature_detection = result.signature_detection
                    finally:
                        os.unlink(tmp_path)

                elif file_type in ["text/plain", "txt"] or file_name.lower().endswith(".txt"):
                    if file_name.lower().endswith(".eml"):
                        # Route .eml files to email parser even if file_type is text/plain
                        try:
                            import tempfile

                            with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
                                tmp.write(file_content)
                                tmp_path = tmp.name

                            try:
                                result = await process_eml(
                                    file_path=tmp_path,
                                    document_type=DocumentType.CORRESPONDENCE,
                                    original_filename=file_name,
                                )

                                extracted_text = result.content
                                extraction_method = result.extraction_method or "email_parser"
                                extraction_quality = result.extraction_quality or "high"
                                extraction_error = result.extraction_error

                                logger.info(f"Successfully extracted email content from {file_name}: {len(extracted_text)} chars")
                            finally:
                                import os
                                try:
                                    os.unlink(tmp_path)
                                except Exception:
                                    pass
                        except Exception as e:
                            extraction_error = f"Email extraction failed: {str(e)}"
                            extraction_method = "failed"
                            extraction_quality = "low"
                            logger.error(f"Email extraction error for {file_name}: {e}")
                    else:
                        # Plain text file
                        try:
                            extracted_text = file_content.decode("utf-8", errors="replace")
                            extraction_method = "direct_text"
                            extraction_quality = "high"
                        except Exception as e:
                            extraction_error = f"Failed to decode text: {e}"
                            extraction_method = "failed"
                            extraction_quality = "low"

                elif file_type in [
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/msword",
                    "docx",
                    "doc",
                ] or file_name.lower().endswith((".docx", ".doc")):
                    # Microsoft Word documents should be extracted immediately, same as PDF/TXT
                    try:
                        extracted_text, docx_backend = ContentExtractor.extract_text_from_docx_with_method(file_content)
                        extracted_text = extracted_text.strip()
                        extraction_method = docx_backend
                        extraction_quality = "high" if len(extracted_text) > 50 else "medium"
                        logger.info(f"DOCX immediate extraction ({docx_backend}): {len(extracted_text)} characters")
                    except Exception as docx_err:
                        # Try plain text fallback (legacy .doc files may be text with .doc extension)
                        logger.warning(f"DOCX extraction failed for {file_name}: {docx_err}, trying plain text")
                        try:
                            fallback_text = file_content.decode("utf-8", errors="replace").strip()
                            if fallback_text and len(fallback_text) > 10:
                                extracted_text = fallback_text
                                extraction_method = "text_fallback"
                                extraction_quality = "medium"
                            else:
                                raise ValueError("Insufficient content")
                        except Exception:
                            extraction_error = f"DOCX extraction failed: {docx_err}"
                            extraction_method = "failed"
                            extraction_quality = "low"
                            logger.error(f"DOCX extraction error for {file_name}: {docx_err}")

                elif file_type in ["image/png", "image/jpeg", "image/jpg"] or file_name.lower().endswith((".png", ".jpg", ".jpeg")):
                    # Image file - OCR extraction
                    from legal_portal.config.default import get_settings
                    _settings = get_settings()

                    if _settings.ocr_remote_enabled:
                        # Route to Cloud Run OCR service (Google Vision only)
                        try:
                            from legal_portal.utils.ocr_service_client import (
                                get_ocr_client, OCRServiceError, OCRConfigError,
                            )
                            ocr_client = get_ocr_client()
                            img_content_type = file_type if file_type in ["image/png", "image/jpeg", "image/jpg"] else "image/png"
                            result = await ocr_client.extract_text(
                                file_content, file_name, img_content_type,
                            )
                            extracted_text = result["full_text"]
                            extraction_method = f"cloud_run_ocr ({result['provider']})"
                            extraction_quality = "high"
                            ocr_provider = result["provider"]
                            logger.info(
                                f"Remote OCR completed for {file_name}",
                                extra={
                                    "trace_id": result.get("trace_id"),
                                    "provider": result["provider"],
                                    "latency_ms": result.get("latency_ms"),
                                },
                            )
                        except OCRConfigError as e:
                            # Missing OCR_SERVICE_TOKEN/URL — config error, always fall back
                            logger.warning(f"OCR remote misconfigured ({e}), falling back to local OCR for {file_name}")
                            try:
                                google_client = GoogleVisionClient.get_instance()
                                if google_client.is_available:
                                    import asyncio
                                    from starlette.concurrency import run_in_threadpool
                                    def do_google_ocr():
                                        return google_client.extract_text_from_image(file_content)
                                    vision_text = await asyncio.wait_for(
                                        run_in_threadpool(do_google_ocr), timeout=30.0,
                                    )
                                    if vision_text and vision_text.strip():
                                        extracted_text = vision_text
                                        extraction_method = "Google Cloud Vision"
                                        extraction_quality = "high"
                                        ocr_provider = "google_vision"
                                    else:
                                        raise ValueError("Google Vision returned empty text")
                                else:
                                    raise ValueError("Google Vision client not available")
                            except Exception as fallback_err:
                                extraction_error = f"Image OCR failed (remote misconfigured, local fallback failed): {str(fallback_err)}"
                                extraction_method = "failed"
                                extraction_quality = "low"
                                logger.error(f"Local OCR fallback also failed for {file_name}: {fallback_err}")
                        except Exception as e:
                            logger.error(f"Remote OCR failed for {file_name}: {e}")
                            # Always fall back to local OCR on remote failure
                            logger.warning(f"Falling back to local OCR for {file_name}")
                            try:
                                google_client = GoogleVisionClient.get_instance()
                                if google_client.is_available:
                                    import asyncio
                                    from starlette.concurrency import run_in_threadpool
                                    def do_google_ocr():
                                        return google_client.extract_text_from_image(file_content)
                                    vision_text = await asyncio.wait_for(
                                        run_in_threadpool(do_google_ocr), timeout=30.0,
                                    )
                                    if vision_text and vision_text.strip():
                                        extracted_text = vision_text
                                        extraction_method = "Google Cloud Vision"
                                        extraction_quality = "high"
                                        ocr_provider = "google_vision"
                                    else:
                                        raise ValueError("Google Vision returned empty text")
                                else:
                                    raise ValueError("Google Vision client not available")
                            except Exception as fallback_err:
                                extraction_error = f"Image OCR failed: {str(fallback_err)}"
                                extraction_method = "failed"
                                extraction_quality = "low"
                                logger.error(f"Emergency fallback OCR also failed for {file_name}: {fallback_err}")
                    else:
                        # Local OCR path (OCR_REMOTE_ENABLED=false)
                        try:
                            google_client = GoogleVisionClient.get_instance()
                            if google_client.is_available:
                                try:
                                    import asyncio
                                    from starlette.concurrency import run_in_threadpool
                                    def do_google_ocr():
                                        return google_client.extract_text_from_image(file_content)
                                    vision_text = await asyncio.wait_for(
                                        run_in_threadpool(do_google_ocr), timeout=30.0,
                                    )
                                    if vision_text and vision_text.strip():
                                        extracted_text = vision_text
                                        extraction_method = "Google Cloud Vision"
                                        extraction_quality = "high"
                                        ocr_provider = "google_vision"
                                        logger.info(f"Successfully extracted text from {file_name} using Google Vision")
                                    else:
                                        raise ValueError("Google Vision returned empty text")
                                except Exception as google_err:
                                    logger.warning(f"{file_name}: Google Vision failed ({google_err}). Falling back to GPT-4o Vision.")
                                    raise
                            else:
                                raise ValueError("Google Vision client not available")
                        except Exception:
                            try:
                                import asyncio
                                import base64
                                from starlette.concurrency import run_in_threadpool
                                from legal_portal.utils.openai_client import OpenAIClient
                                logger.info(f"Using GPT-4o Vision for {file_name}")
                                openai_client = OpenAIClient()
                                client = openai_client.client
                                if file_type in ["image/jpeg", "image/jpg"] or file_name.lower().endswith((".jpg", ".jpeg")):
                                    mime_type = "image/jpeg"
                                else:
                                    mime_type = "image/png"
                                base64_image = base64.b64encode(file_content).decode("utf-8")
                                prompt = (
                                    f"Extract ALL text from this legal document image. "
                                    f"Filename: {file_name}. "
                                    "This is a scanned document that needs OCR text extraction. "
                                    "Maintain the logical structure and layout. "
                                    "If there are tables, preserve the row/column relationship. "
                                    "Provide the text verbatim including all numbers, dates, and names. Do not summarize."
                                )
                                def gpt4o_ocr():
                                    return client.chat.completions.create(
                                        model="gpt-5.2",
                                        messages=[{
                                            "role": "user",
                                            "content": [
                                                {"type": "text", "text": prompt},
                                                {
                                                    "type": "image_url",
                                                    "image_url": {
                                                        "url": f"data:{mime_type};base64,{base64_image}",
                                                        "detail": "high"
                                                    }
                                                },
                                            ]
                                        }],
                                        max_completion_tokens=4000,
                                        reasoning_effort="none",
                                        temperature=0.0,
                                    )
                                response = await asyncio.wait_for(
                                    run_in_threadpool(gpt4o_ocr), timeout=60.0,
                                )
                                extracted_text = response.choices[0].message.content
                                extraction_method = "GPT-5.2 Vision"
                                extraction_quality = "high"
                                ocr_provider = "openai"
                                logger.info(f"Successfully extracted text from {file_name} using GPT-4o Vision")
                            except Exception as ocr_err:
                                extraction_error = f"Image OCR failed: {str(ocr_err)}"
                                extraction_method = "failed"
                                extraction_quality = "low"
                                logger.error(f"Image extraction error for {file_name}: {ocr_err}")

                elif file_type in ["message/rfc822", "eml"] or file_name.lower().endswith(".eml"):
                    # Email file (.eml)
                    try:
                        import asyncio
                        import tempfile

                        from starlette.concurrency import run_in_threadpool

                        # Write to temp file for eml processing
                        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
                            tmp.write(file_content)
                            tmp_path = tmp.name

                        try:
                            # Process eml file asynchronously
                            result = await process_eml(
                                file_path=tmp_path,
                                document_type=DocumentType.CORRESPONDENCE,
                                original_filename=file_name,
                            )

                            extracted_text = result.content
                            extraction_method = result.extraction_method or "email_parser"
                            extraction_quality = result.extraction_quality or "high"
                            extraction_error = result.extraction_error

                            logger.info(f"Successfully extracted email content from {file_name}: {len(extracted_text)} chars")
                        finally:
                            # Clean up temp file
                            import os
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass
                    except Exception as e:
                        extraction_error = f"Email extraction failed: {str(e)}"
                        extraction_method = "failed"
                        extraction_quality = "low"
                        logger.error(f"Email extraction error for {file_name}: {e}")

                else:
                    # Other file types - mark as needing extraction
                    extraction_method = "pending"
                    extraction_quality = "unknown"

                # Sanitize extracted text to remove NULL characters that PostgreSQL can't store
                extracted_text = sanitize_text_for_db(extracted_text)

                # Update document with extraction results
                update_data = {
                    "extracted_text": extracted_text if extracted_text else None,
                    "extraction_method": extraction_method,
                    "extraction_quality": extraction_quality,
                    "ocr_provider": ocr_provider,
                    "extraction_error": extraction_error,
                    "page_count": page_count,
                    "extracted_at": datetime.utcnow().isoformat() if extracted_text else None,
                    "updated_at": datetime.utcnow().isoformat(),
                    "status": DocumentStatus.READY if extracted_text else DocumentStatus.EXTRACTION_FAILED,
                }
                if signature_detection:
                    metadata = created_doc.get("metadata", {}) or {}
                    metadata["signature_detection"] = signature_detection
                    update_data["metadata"] = metadata

                user_supabase.table("documents").update(update_data).eq("id", document_id).execute()
                logger.info(
                    f"Extraction complete for {document_id}: method={extraction_method}, "
                    f"quality={extraction_quality}, chars={len(extracted_text)}"
                )

                # Build and persist initial document registry (Stage 1)
                # Always build — filename alone provides type + signature classification
                try:
                    _build_and_persist_registry(
                        document_id=document_id,
                        file_name=file_name,
                        file_type=file_type,
                        extracted_text=extracted_text or "",
                        extraction_quality=extraction_quality,
                        extraction_method=extraction_method,
                        signature_detection=signature_detection,
                        supabase_client=user_supabase,
                    )
                except Exception as reg_err:
                    logger.warning(f"Registry build failed for {document_id}: {reg_err}")

            except Exception as extract_err:
                # Log but don't fail the upload if extraction fails
                logger.warning(f"Immediate extraction failed for {document_id}: {extract_err}")
                # Update with error status
                user_supabase.table("documents").update(
                    {
                        "extraction_method": "failed",
                        "extraction_quality": "low",
                        "extraction_error": str(extract_err),
                        "status": DocumentStatus.EXTRACTION_FAILED,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ).eq("id", document_id).execute()

                # Still build registry from filename alone
                try:
                    _build_and_persist_registry(
                        document_id=document_id,
                        file_name=file_name,
                        file_type=file_type,
                        extracted_text="",
                        extraction_quality="low",
                        extraction_method="failed",
                        signature_detection=None,
                        supabase_client=user_supabase,
                    )
                except Exception:
                    pass

        return created_doc

    except HTTPException:
        raise
    except ValidationError as e:
        # Catch any validation errors that slipped through
        error_response = {
            "code": e.error_code,
            "detail": str(e),
            "file_name": file.filename,
            "file_size_mb": e.file_size_mb,
        }
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_response)
    except Exception as e:
        logger.error(f"Error in upload_document: {type(e).__name__} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error uploading document: {str(e)}"
        ) from e


@router.get("/case/{case_id}", response_model=List[DocumentResponse])
async def list_documents_for_case(
    case_id: str, user=Depends(get_current_user), supabase=Depends(get_user_supabase_client)
):
    """List all documents for a specific case.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        List of documents

    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get documents (exclude extracted_text/manual_text to avoid multi-MB payloads)
        response = (
            supabase.table("documents")
            .select(
                "id, case_id, file_name, file_type, file_size, storage_path, status, "
                "extraction_method, extraction_quality, extracted_at, page_count, "
                "ocr_provider, extraction_error, is_verified, is_flagged_as_junk, "
                "text_edited_at, metadata, created_at, updated_at"
            )
            .eq("case_id", case_id)
            .order("created_at", desc=False)
            .execute()
        )

        return response.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching documents: {str(e)}"
        ) from e


@router.post("/case/{case_id}/enrich-cross-document")
async def enrich_cross_document_for_case(
    case_id: str,
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Run cross-document enrichment for a case.

    Detects email threads, sequential photos, and contract families.
    Populates suggested_relationships in each document's registry.
    Idempotent — skips documents already at cross_doc or ai_analysis stage.

    Call this before displaying the Verification Hub so relationship
    suggestions are available immediately (no analysis run required).
    """
    try:
        # Verify case ownership
        case_response = (
            user_supabase.table("cases")
            .select("id")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )
        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Phase 1: Load document metadata WITHOUT extracted_text (fast, small payload).
        # Only fetch extracted_text per-doc when actually needed for registry building.
        docs_response = (
            service_supabase.table("documents")
            .select("id, file_name, file_type, file_size, metadata")
            .eq("case_id", case_id)
            .execute()
        )
        docs = docs_response.data or []
        if not docs:
            return {"enriched": 0, "total": 0}

        registry_service = DocumentRegistryService()
        registries: list[dict] = []
        processed_docs: list[ProcessedDocument] = []
        doc_id_by_name: dict[str, str] = {}
        needs_enrichment = False
        registries_built = 0
        # Track doc IDs that need extracted_text for cross-doc matching
        docs_needing_text: list[dict] = []

        for doc in docs:
            metadata = doc.get("metadata") or {}
            registry = metadata.get("registry")

            # Build registry on-the-fly for docs that don't have one yet
            # (e.g. Clio imports, uploads from before registry code was added)
            if not registry:
                try:
                    # Lazy-load extracted_text only for docs needing registry build
                    text_response = (
                        service_supabase.table("documents")
                        .select("extracted_text")
                        .eq("id", doc["id"])
                        .single()
                        .execute()
                    )
                    extracted_text = (text_response.data or {}).get("extracted_text") or ""

                    ft = _MIME_TO_FILETYPE.get(doc.get("file_type", ""), FileType.PDF)
                    pdoc_tmp = ProcessedDocument(
                        file_name=doc.get("file_name", ""),
                        content=extracted_text[:200_000],
                        document_type=DocumentType.CASE_DOCUMENT,
                        file_type=ft,
                        metadata=FileMetadata(
                            file_name=doc.get("file_name", ""),
                            file_type=ft,
                            file_size=doc.get("file_size", 0),
                        ),
                        document_id=doc["id"],
                        extraction_quality=doc.get("extraction_quality", "unknown"),
                    )
                    registry = registry_service.build_initial_registry(pdoc_tmp)
                    registry_service.persist_to_document(doc["id"], registry, service_supabase)
                    registries_built += 1
                    logger.info(f"Auto-built registry for {doc.get('file_name', doc['id'])}: type={registry.get('document_type')}")
                except Exception as e:
                    logger.warning(f"Failed to auto-build registry for {doc['id']}: {e}")
                    continue

            # Skip docs already enriched beyond extraction
            stage = registry.get("enrichment_stage", "none")
            if stage in ("cross_doc", "ai_analysis"):
                registries.append(registry)
                # Still include in processed_docs for cross-doc matching
                # Mark for lazy text loading below
                docs_needing_text.append(doc)
                doc_id_by_name[doc.get("file_name", "")] = doc["id"]
                continue

            needs_enrichment = True
            registries.append(registry)
            docs_needing_text.append(doc)
            doc_id_by_name[doc.get("file_name", "")] = doc["id"]

        if not needs_enrichment:
            return {"enriched": 0, "registries_built": registries_built, "total": len(docs)}

        # Phase 2: Batch-load extracted_text only for docs included in cross-doc matching.
        # Load in batches of 50 to avoid oversized Supabase responses.
        logger.info(f"Loading extracted_text for {len(docs_needing_text)} docs for cross-doc enrichment")
        text_by_id: dict[str, str] = {}
        batch_size = 50
        for i in range(0, len(docs_needing_text), batch_size):
            batch_ids = [d["id"] for d in docs_needing_text[i : i + batch_size]]
            text_resp = (
                service_supabase.table("documents")
                .select("id, extracted_text")
                .in_("id", batch_ids)
                .execute()
            )
            for row in text_resp.data or []:
                text_by_id[row["id"]] = (row.get("extracted_text") or "")[:5000]

        # Build ProcessedDocument list with loaded text
        for doc in docs_needing_text:
            pdoc = ProcessedDocument(
                file_name=doc.get("file_name", ""),
                content=text_by_id.get(doc["id"], ""),
                document_type=DocumentType.CASE_DOCUMENT,
                file_type=FileType.PDF,
                metadata=FileMetadata(
                    file_name=doc.get("file_name", ""),
                    file_type=FileType.PDF,
                    file_size=doc.get("file_size", 0),
                ),
                document_id=doc["id"],
            )
            processed_docs.append(pdoc)

        # Phase 3: Run cross-document enrichment (pure computation, no I/O)
        logger.info(f"Running cross-document enrichment: {len(registries)} registries, {len(processed_docs)} docs")
        enriched = registry_service.enrich_cross_document(registries, processed_docs)

        # Phase 4: Persist updated registries
        persisted = 0
        persist_errors = 0
        for reg in enriched:
            doc_name = reg.get("document_name", "")
            doc_id = reg.get("document_id") or doc_id_by_name.get(doc_name)
            if not doc_id:
                continue
            if reg.get("enrichment_stage") == "cross_doc":
                try:
                    registry_service.persist_to_document(doc_id, reg, service_supabase)
                    persisted += 1
                except Exception as e:
                    persist_errors += 1
                    logger.warning(f"Failed to persist registry for {doc_id}: {e}")

        return {
            "enriched": persisted,
            "registries_built": registries_built,
            "persist_errors": persist_errors,
            "total": len(docs),
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        # Print to stdout so Vercel captures the full traceback
        print(f"ERROR in enrich_cross_document_for_case: {e}\n{tb}")
        logger.error(f"Error in enrich_cross_document_for_case: {e}\n{tb}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error running cross-document enrichment: {str(e)}",
        ) from e


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str, user=Depends(get_current_user), supabase=Depends(get_user_supabase_client)
):
    """Get document metadata by ID.

    Args:
    ----
        document_id: Document ID
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Document metadata

    """
    try:
        # Get document with case join to verify ownership (exclude large text fields)
        response = (
            supabase.table("documents")
            .select(
                "id, case_id, file_name, file_type, file_size, storage_path, status, "
                "extraction_method, extraction_quality, extracted_at, page_count, "
                "ocr_provider, extraction_error, is_verified, is_flagged_as_junk, "
                "text_edited_at, metadata, created_at, updated_at, "
                "cases!inner(user_id)"
            )
            .eq("id", document_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        document = response.data[0]

        # Verify ownership through case
        if document["cases"]["user_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Remove nested case data before returning
        document.pop("cases", None)

        return document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching document: {str(e)}"
        ) from e


@router.get("/{document_id}/extracted-text")
async def get_extracted_text(
    document_id: str, user=Depends(get_current_user), supabase=Depends(get_user_supabase_client)
):
    """Get the extracted text and metadata for a specific document.

    Args:
    ----
        document_id: Document ID
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Extracted text and extraction metadata

    """
    try:
        # Get document with case join to verify ownership
        response = (
            supabase.table("documents")
            .select(
                "extracted_text, extraction_method, extraction_quality, "
                "extracted_at, page_count, ocr_provider, extraction_error, "
                "cases!inner(user_id)"
            )
            .eq("id", document_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        document = response.data[0]

        # Verify ownership through case
        if document["cases"]["user_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Remove nested case data before returning
        document.pop("cases", None)

        return document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching extracted text: {str(e)}",
        ) from e


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Delete a document and its file from storage.

    Args:
    ----
        document_id: Document ID
        user: Current authenticated user
        user_supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    """
    try:
        logger.debug(f"Delete document: doc_id={document_id}, user={user['id']}")

        # Get document with ownership verification
        response = (
            user_supabase.table("documents")
            .select("storage_path, cases!inner(user_id)")
            .eq("id", document_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        document = response.data[0]

        # Verify ownership
        if document["cases"]["user_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Delete from storage (use service client to bypass storage RLS)
        storage_path = document["storage_path"]
        logger.debug(f"Deleting from storage: {storage_path}")
        service_supabase.storage.from_("documents").remove([storage_path])

        # Delete database record (use user client for RLS)
        logger.debug("Deleting database record")
        user_supabase.table("documents").delete().eq("id", document_id).execute()

        logger.info("Document deleted successfully")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting document: {str(e)}"
        ) from e


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_documents(
    request: BulkDeleteRequest,
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Bulk delete multiple documents and their files from storage.

    Args:
    ----
        request: List of document IDs to delete
        user: Current authenticated user
        user_supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    Returns:
    -------
        Summary of deleted and failed documents

    """
    deleted_count = 0
    failed_ids = []
    errors = []

    logger.info(f"Bulk delete request: {len(request.document_ids)} documents, user={user['id']}")

    for doc_id in request.document_ids:
        try:
            # Get document with ownership verification
            response = (
                user_supabase.table("documents")
                .select("storage_path, cases!inner(user_id)")
                .eq("id", doc_id)
                .execute()
            )

            if not response.data:
                failed_ids.append(doc_id)
                errors.append(f"Document {doc_id}: not found")
                continue

            document = response.data[0]

            # Verify ownership
            if document["cases"]["user_id"] != user["id"]:
                failed_ids.append(doc_id)
                errors.append(f"Document {doc_id}: access denied")
                continue

            # Delete from storage
            storage_path = document["storage_path"]
            try:
                service_supabase.storage.from_("documents").remove([storage_path])
            except Exception as storage_err:
                logger.warning(f"Storage deletion failed for {doc_id}: {storage_err}")
                # Continue anyway - database record should still be deleted

            # Delete database record
            user_supabase.table("documents").delete().eq("id", doc_id).execute()
            deleted_count += 1

        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {str(e)}")
            failed_ids.append(doc_id)
            errors.append(f"Document {doc_id}: {str(e)}")

    logger.info(f"Bulk delete complete: {deleted_count} deleted, {len(failed_ids)} failed")

    return BulkDeleteResponse(
        deleted_count=deleted_count,
        failed_ids=failed_ids,
        errors=errors,
    )


@router.post("/bulk-extract", response_model=BulkExtractResponse)
async def bulk_extract_documents(
    request: BulkExtractRequest,
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Extract text from documents in a case that don't have text yet.

    Paginated: processes at most request.batch_size documents per call starting at
    request.offset. Returns has_more=True and next_offset when more remain, so the
    frontend can call again to process the next batch. This prevents Vercel function
    timeout on cases with many documents (200 docs × 45s would exceed 800s maxDuration).
    """
    # Timeout per document to prevent Vercel 800s maxDuration being hit in one call
    DOC_TIMEOUT = 45  # seconds per document
    # Skip PDFs larger than this (likely to timeout on OCR)
    MAX_PDF_SIZE_FOR_BULK = 10 * 1024 * 1024  # 10MB
    # Hard cap: never process more than 20 docs per invocation regardless of request
    MAX_BATCH_SIZE = 20
    batch_size = min(request.batch_size, MAX_BATCH_SIZE)
    offset = max(request.offset, 0)

    try:
        logger.info(
            f"Bulk extraction requested for case {request.case_id} by user {user['id']} "
            f"| batch_size={batch_size} offset={offset}"
        )

        # Get all documents for this case that need extraction (no extracted_text yet)
        response = (
            user_supabase.table("documents")
            .select("id, file_name, file_type, storage_path, file_size")
            .eq("case_id", request.case_id)
            .neq("status", DocumentStatus.SKIPPED)
            .or_("extracted_text.is.null,extracted_text.eq.''")
            .order("created_at", desc=False)
            .execute()
        )

        all_pending = response.data or []
        total_queued = len(all_pending)
        logger.info(f"Found {total_queued} total documents pending extraction")

        # Apply pagination window
        documents_to_process = all_pending[offset: offset + batch_size]
        next_offset = offset + len(documents_to_process)
        has_more = next_offset < total_queued

        extracted_count = 0
        failed_count = 0
        skipped_count = 0
        errors = []

        for doc in documents_to_process:
            file_name = doc.get("file_name", "unknown")
            file_type = doc.get("file_type", "")
            file_size = doc.get("file_size", 0) or 0

            # Skip large PDFs in bulk mode - they need individual processing
            is_pdf = file_type in ["application/pdf", "pdf"] or file_name.lower().endswith(".pdf")
            if is_pdf and file_size > MAX_PDF_SIZE_FOR_BULK:
                skipped_count += 1
                skip_msg = f"Skipped {file_name}: PDF too large ({file_size / (1024*1024):.1f}MB) for bulk OCR. Extract individually."
                logger.warning(skip_msg)
                errors.append(skip_msg)
                continue

            try:
                # Call inner extraction directly (semaphore already handled inside trigger_extraction)
                result = await asyncio.wait_for(
                    _trigger_extraction_inner(
                        document_id=doc["id"],
                        force_method=None,
                        user=user,
                        user_supabase=user_supabase,
                        service_supabase=service_supabase,
                    ),
                    timeout=DOC_TIMEOUT,
                )

                extracted_text = result.get("extracted_text") or ""
                if extracted_text:
                    extracted_count += 1
                    logger.info(f"Extracted {file_name}: {len(extracted_text)} chars")
                else:
                    failed_count += 1
                    error_msg = f"No text extracted from {file_name} ({result.get('extraction_error', 'unsupported format')})"
                    logger.warning(error_msg)
                    errors.append(error_msg)
            except asyncio.TimeoutError:
                failed_count += 1
                error_msg = f"Timeout extracting {file_name} (>{DOC_TIMEOUT}s). Try extracting individually."
                logger.error(error_msg)
                errors.append(error_msg)
            except Exception as e:
                failed_count += 1
                error_msg = f"Failed to extract {file_name}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

        return BulkExtractResponse(
            extracted_count=extracted_count,
            failed_count=failed_count + skipped_count,
            errors=errors,
            has_more=has_more,
            next_offset=next_offset,
            total_queued=total_queued,
        )

    except Exception as e:
        logger.error(f"Bulk extraction failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Bulk extraction failed: {str(e)}"
        ) from e


@router.patch("/{document_id}/verify")
async def verify_document(
    document_id: str,
    request: VerifyDocumentRequest,
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
):
    """Update document verification status and optionally correct extracted text.

    Args:
    ----
        document_id: Document ID
        request: Verification request with optional manual text correction
        user: Current authenticated user
        user_supabase: User-scoped Supabase client

    Returns:
    -------
        Updated document metadata

    """
    try:
        logger.debug(f"Verify document: doc_id={document_id}, user={user['id']}")

        # Get document with ownership verification
        response = (
            user_supabase.table("documents")
            .select("id, extracted_text, manual_text, metadata, cases!inner(user_id)")
            .eq("id", document_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        document = response.data[0]

        # Verify ownership
        if document["cases"]["user_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Validate that document has text if being verified as ready
        if request.is_verified and not (document.get("extracted_text") or document.get("manual_text") or request.manual_text):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot verify document without extracted text. Please run OCR first.",
            )

        # Build update payload
        update_data = {
            "is_verified": request.is_verified,
            "is_flagged_as_junk": request.is_flagged_as_junk,
            "status": DocumentStatus.SKIPPED if request.is_flagged_as_junk else (
                DocumentStatus.READY if request.is_verified else DocumentStatus.NEEDS_REVIEW
            ),
            "updated_at": datetime.utcnow().isoformat(),
        }

        if request.manual_text is not None:
            update_data["manual_text"] = request.manual_text
            update_data["text_edited_at"] = datetime.utcnow().isoformat()

        # Optional attorney override for execution/signature status.
        metadata: Dict[str, Any] = document.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        should_update_signature_meta = (
            request.signature_verification is not None
            or request.signature_verification_notes is not None
            or request.signature_signing_date is not None
            or request.signature_signer_names is not None
        )
        if should_update_signature_meta:
            raw_status = (request.signature_verification or "").strip().lower()
            status_aliases = {
                "signed": "signed",
                "not_signed": "not_signed",
                "unsigned": "not_signed",
                "not signed": "not_signed",
                "not_detected": "not_signed",
                "not detected": "not_signed",
                "unknown": "unknown",
                "unclear": "unknown",
            }
            normalized_status = None
            if request.signature_verification is not None:
                normalized_status = status_aliases.get(raw_status)
                if not normalized_status:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "signature_verification must be one of: "
                            "signed, not_signed, unknown"
                        ),
                    )

            signature_verification = metadata.get("signature_verification")
            if not isinstance(signature_verification, dict):
                signature_verification = {}

            if normalized_status is not None:
                signature_verification["status"] = normalized_status

            if request.signature_verification_notes is not None:
                notes = (request.signature_verification_notes or "").strip()
                if notes:
                    signature_verification["notes"] = notes
                else:
                    signature_verification.pop("notes", None)

            if request.signature_signing_date is not None:
                signing_date = (request.signature_signing_date or "").strip()
                if signing_date:
                    signature_verification["signing_date"] = signing_date
                else:
                    signature_verification.pop("signing_date", None)

            if request.signature_signer_names is not None:
                signer_names = [
                    str(name).strip()
                    for name in request.signature_signer_names
                    if str(name).strip()
                ][:10]
                if signer_names:
                    signature_verification["signer_names"] = signer_names
                else:
                    signature_verification.pop("signer_names", None)

            signature_verification["verified_at"] = datetime.utcnow().isoformat()
            signature_verification["verified_by_user_id"] = user["id"]
            metadata["signature_verification"] = signature_verification

            signature_detection = metadata.get("signature_detection")
            if not isinstance(signature_detection, dict):
                signature_detection = {}

            if normalized_status == "signed":
                signature_detection["status"] = "signed"
                signature_detection["confidence"] = "verified"
                signature_detection["detection_source"] = "attorney_verification"
                signature_detection["has_signature_markers"] = True
                marker_count = signature_detection.get("signature_marker_count")
                try:
                    marker_count_int = int(marker_count)
                except (TypeError, ValueError):
                    marker_count_int = 0
                signature_detection["signature_marker_count"] = max(1, marker_count_int)
            elif normalized_status == "not_signed":
                signature_detection["status"] = "not_detected"
                signature_detection["confidence"] = "verified"
                signature_detection["detection_source"] = "attorney_verification"

            if normalized_status in {"signed", "not_signed"}:
                signature_detection["verified_by_attorney"] = True
                signature_detection["verified_at"] = signature_verification["verified_at"]
                signature_detection["verified_by_user_id"] = user["id"]

                if signature_verification.get("notes"):
                    signature_detection["verification_notes"] = signature_verification["notes"]
                if signature_verification.get("signing_date"):
                    signature_detection["signing_date"] = signature_verification["signing_date"]
                if signature_verification.get("signer_names"):
                    signature_detection["signer_names"] = signature_verification["signer_names"]

                metadata["signature_detection"] = signature_detection

            update_data["metadata"] = metadata

        # --- Attorney enrichment fields ---
        if request.document_type_override is not None:
            metadata.setdefault("attorney_enrichment", {})
            metadata["attorney_enrichment"]["document_type_override"] = request.document_type_override
        if request.relevance_level is not None:
            metadata.setdefault("attorney_enrichment", {})
            metadata["attorney_enrichment"]["relevance_level"] = request.relevance_level
        if request.key_facts is not None:
            metadata.setdefault("attorney_enrichment", {})
            metadata["attorney_enrichment"]["key_facts"] = request.key_facts
        if request.attorney_notes is not None:
            metadata.setdefault("attorney_enrichment", {})
            metadata["attorney_enrichment"]["attorney_notes"] = request.attorney_notes
        if request.document_relationships is not None:
            metadata.setdefault("attorney_enrichment", {})
            metadata["attorney_enrichment"]["document_relationships"] = request.document_relationships
        if "attorney_enrichment" in metadata:
            update_data["metadata"] = metadata

        # --- Sync registry + denormalized columns ---
        # All registry-backed column writes go through resolve_denormalized_columns()
        # to maintain a single source of truth for column computation.
        # If denormalized columns don't exist yet (migration pending), the write
        # falls back to metadata-only.
        registry = metadata.get("registry") or {}
        denorm_columns: Dict[str, Any] = {}

        # Update registry dict to reflect attorney changes
        if registry:
            if request.document_type_override is not None:
                registry["document_type_override"] = request.document_type_override
            if request.attorney_notes is not None:
                registry["attorney_notes"] = request.attorney_notes
            if request.key_facts is not None:
                registry["key_facts"] = request.key_facts
            if request.relevance_level is not None:
                registry["relevance_level"] = request.relevance_level
            if request.document_relationships is not None:
                registry["document_relationships"] = request.document_relationships
            if should_update_signature_meta and normalized_status:
                # Sync execution_status in registry so columns resolve correctly
                if normalized_status == "signed":
                    registry["execution_status"] = "signed"
                elif normalized_status == "not_signed":
                    registry["execution_status"] = "not_detected"
                else:
                    registry["execution_status"] = "unknown"

            # Compute denormalized columns from updated registry
            denorm_columns = DocumentRegistryService.resolve_denormalized_columns(registry)
            metadata["registry"] = registry
            update_data["metadata"] = metadata
        else:
            # No registry yet — still sync what we can from attorney enrichment
            if request.document_type_override is not None:
                denorm_columns["document_type_label"] = request.document_type_override
            if should_update_signature_meta and normalized_status:
                if normalized_status == "signed":
                    denorm_columns["signed_status"] = "signed"
                elif normalized_status == "not_signed":
                    denorm_columns["signed_status"] = "not_detected"
                else:
                    denorm_columns["signed_status"] = "unknown"

        # Update document — try with denormalized columns, fall back to without
        # if the migration hasn't been run yet.
        full_update = {**update_data, **denorm_columns}
        try:
            update_response = user_supabase.table("documents").update(full_update).eq("id", document_id).execute()
        except Exception:
            if denorm_columns:
                logger.warning("verify_document: denormalized columns not available, writing metadata only")
                update_response = user_supabase.table("documents").update(update_data).eq("id", document_id).execute()
            else:
                raise

        if not update_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update document",
            )

        logger.info(f"Document {document_id} verified successfully")
        return update_response.data[0]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in verify_document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying document: {str(e)}",
        ) from e


class ToggleExclusionRequest(BaseModel):
    """Request model for toggling document exclusion."""

    excluded: bool


@router.patch("/{document_id}/exclusion")
async def toggle_document_exclusion(
    document_id: str,
    request: ToggleExclusionRequest,
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
):
    """Toggle document exclusion status (for duplicate management).

    Allows users to include/exclude duplicate documents from analysis.

    Args:
    ----
        document_id: Document ID
        request: Exclusion status to set
        user: Current authenticated user
        user_supabase: User-scoped Supabase client

    Returns:
    -------
        Updated document with new exclusion status

    """
    try:
        logger.debug(f"Toggle exclusion: doc_id={document_id}, excluded={request.excluded}, user={user['id']}")

        # Get document with ownership verification
        response = (
            user_supabase.table("documents")
            .select("id, metadata, cases!inner(user_id)")
            .eq("id", document_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        document = response.data[0]

        # Verify ownership
        if document["cases"]["user_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Update metadata with new exclusion status
        metadata = document.get("metadata", {}) or {}
        metadata["excluded"] = request.excluded

        # Update status based on exclusion
        new_status = "duplicate" if metadata.get("is_duplicate") and request.excluded else "ready"

        update_data = {
            "metadata": metadata,
            "status": new_status,
            "updated_at": datetime.utcnow().isoformat(),
        }

        user_supabase.table("documents").update(update_data).eq("id", document_id).execute()

        logger.info(f"Document exclusion toggled: {document_id}, excluded={request.excluded}")

        return {
            "document_id": document_id,
            "excluded": request.excluded,
            "status": new_status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling document exclusion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error toggling exclusion: {str(e)}",
        ) from e


def is_photo_rejection_message(text: str) -> bool:
    """Check if OCR result is a message indicating the image is a photo, not a text document."""
    if not text or len(text) < 20:
        return False
    
    rejection_phrases = [
        "unable to extract text",
        "unable to access",
        "unable to analyze",
        "can't access",
        "can't analyze",
        "cannot access",
        "cannot analyze",
        "not a legal document",
        "appears to be a photo",
        "this is a photo",
        "this image is",
        "does not contain",
        "no text to extract",
        "cannot extract text",
        "i can't extract",  # Fixed: lowercase
        "i'm unable to extract",  # Fixed: lowercase
        "i'm unable to access",  # Fixed: lowercase
        "i'm unable to analyze",  # Fixed: lowercase
        "i'm sorry, i can't",  # Added: catches "I'm sorry, I can't extract text"
        "how to describe an image",
        "help you understand how to describe",
        "general guide on how",
    ]
    
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in rejection_phrases)


def is_low_quality_ocr_result(text: str) -> bool:
    """
    Detect if OCR result is too minimal to be a real text document,
    indicating the image is likely a photo rather than a document.

    Examples of low-quality results:
    - Single characters: "O", "I", "."
    - Very short results: "OK", "NO"
    - Mostly punctuation/symbols with no real words
    """
    if not text or len(text.strip()) == 0:
        return True

    cleaned = text.strip()

    # Very short results (< 20 chars) are likely spurious OCR detections
    if len(cleaned) < 20:
        return True

    # Count actual words (not just whitespace/punctuation)
    words = [w for w in cleaned.split() if any(c.isalnum() for c in w)]

    # Less than 3 real words suggests this isn't a text document
    if len(words) < 3:
        return True

    # If text is mostly non-alphanumeric (>80%), it's likely noise
    alnum_chars = sum(c.isalnum() for c in cleaned)
    if len(cleaned) > 0 and (alnum_chars / len(cleaned)) < 0.2:
        return True

    return False


def classify_document_type(file_name: str, file_type: str) -> str:
    """
    Classify if document is primarily IMAGE (visual evidence) or TEXT (text document).

    This is a fast classification based on file type and name patterns.
    No API calls are made - just metadata analysis.

    Args:
        file_name: Name of the file
        file_type: MIME type of the file

    Returns:
        "IMAGE" or "TEXT"
    """
    file_name_lower = file_name.lower()

    # Photos from phones/cameras are almost always visual evidence
    if file_type in ["image/jpeg", "image/jpg", "image/png", "image/heic", "image/webp"]:
        # Common photo filename patterns
        photo_patterns = [
            "img_",      # iPhone: IMG_1234.jpg
            "photo_",    # Generic photo apps
            "dcim",      # Camera folder
            "camera",    # Camera apps
            "dsc_",      # Digital cameras
            "p_",        # Some cameras
            "wp_",       # WhatsApp images
            "screenshot" # Screenshots (though might have text)
        ]

        # Check if filename suggests it's a photo
        if any(pattern in file_name_lower for pattern in photo_patterns):
            return "IMAGE"

        # Could be a scanned document, but default to IMAGE for safety
        # (OCR will be tried if user reclassifies or if it has substantial text)
        return "IMAGE"

    # PDFs and Office documents are TEXT by default
    if file_type in [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "text/plain",
        "text/html",
        "application/rtf"
    ]:
        return "TEXT"

    # Default to TEXT for unknown types
    return "TEXT"


async def get_case_context(case_id: str, supabase_client) -> dict:
    """Get case context for image analysis."""
    try:
        response = supabase_client.table("cases").select("client_name, description").eq("id", case_id).execute()
        if response.data and len(response.data) > 0:
            case = response.data[0]
            return {
                "case_name": case.get("client_name", "Unknown Case"),
                "client_name": case.get("client_name", "Unknown Client"),
                "description": case.get("description", ""),
            }
    except Exception as e:
        logger.warning(f"Could not fetch case context for {case_id}: {e}")
    
    return {"case_name": "Legal Case", "client_name": "", "description": ""}


def _detect_image_mime(file_bytes: bytes, file_name: str) -> str:
    """Detect actual MIME type from file bytes, falling back to extension."""
    try:
        import magic
        detected = magic.from_buffer(file_bytes[:2048], mime=True)
        if detected in ("image/jpeg", "image/png", "image/gif", "image/webp", "image/heic", "image/heif"):
            return detected
    except Exception:
        pass
    # Fallback to extension
    lower = file_name.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    elif lower.endswith(".png"):
        return "image/png"
    return "image/png"


def _ensure_vision_compatible(file_bytes: bytes, mime_type: str) -> tuple:
    """Re-encode image through PIL to normalize exotic PNG/image features.

    Always re-encodes to strip APNG frames, unusual color depths, and other
    features that OpenAI's vision parser rejects.  PNGs stay PNG, JPEGs stay
    JPEG — only the raw bytes are normalized.
    """
    try:
        from PIL import Image
        from io import BytesIO

        # Register HEIF/HEIC opener if available (must happen before Image.open)
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass

        img = Image.open(BytesIO(file_bytes))

        # HEIC/HEIF → always convert to JPEG (OpenAI doesn't support HEIC)
        if mime_type in ("image/heic", "image/heif") or img.format in ("HEIF", "HEIC"):
            out_format, out_mime = "JPEG", "image/jpeg"
            if img.mode != "RGB":
                img = img.convert("RGB")
        # Keep JPEG as JPEG, everything else as PNG
        elif mime_type == "image/jpeg" or img.format == "JPEG":
            out_format, out_mime = "JPEG", "image/jpeg"
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
        else:
            out_format, out_mime = "PNG", "image/png"
            if img.mode not in ("RGB", "RGBA", "L", "LA"):
                img = img.convert("RGBA")

        buf = BytesIO()
        save_kwargs = {"optimize": True}
        if out_format == "JPEG":
            save_kwargs["quality"] = 90
        img.save(buf, format=out_format, **save_kwargs)
        return buf.getvalue(), out_mime
    except Exception:
        return file_bytes, mime_type  # best-effort fallback


async def analyze_image_with_vision(file_bytes: bytes, file_name: str, case_context: dict) -> tuple[str, str]:
    """
    Analyze an image using vision AI with case context.
    
    Returns (visual_description, extraction_method)
    """
    import asyncio
    import base64
    from starlette.concurrency import run_in_threadpool
    from legal_portal.utils.openai_client import OpenAIClient
    
    try:
        logger.info(f"Analyzing image content for {file_name} with case context")
        openai_client = OpenAIClient()
        client = openai_client.client
        
        # Determine MIME type from actual file content
        mime_type = _detect_image_mime(file_bytes, file_name)
        file_bytes, mime_type = _ensure_vision_compatible(file_bytes, mime_type)
        base64_image = base64.b64encode(file_bytes).decode("utf-8")
        
        # Build context-aware prompt
        case_info = f"Case: {case_context['case_name']}"
        if case_context.get('client_name'):
            case_info += f" (Client: {case_context['client_name']})"
        if case_context.get('description'):
            case_info += f"\nCase Description: {case_context['description']}"
        
        prompt = (
            f"You are analyzing an image as photographic evidence for a legal case.\n\n"
            f"CASE CONTEXT:\n{case_info}\n\n"
            f"IMAGE FILE: {file_name}\n\n"
            "TASK: Describe exactly what you see in this image. This is actual photographic evidence, "
            "not a document to extract text from.\n\n"
            "In your description, include:\n"
            "1. OBJECTS & SCENE: What physical objects, people, locations, or structures are visible\n"
            "2. CONDITIONS: Any damage, defects, injuries, wear, contamination, or unusual conditions\n"
            "3. VISIBLE TEXT: Any text, labels, signs, dates, numbers, or markings you can see\n"
            "4. SETTING: The environment/location context (indoor/outdoor, type of space, lighting)\n"
            "5. CASE RELEVANCE: How this visual evidence relates to the legal matter described above\n\n"
            "IMPORTANT: DO NOT provide instructions or templates. Describe the ACTUAL SPECIFIC image "
            "you are viewing right now. Start your response by describing what you see."
        )
        
        def vision_analysis():
            return client.chat.completions.create(
                model="gpt-5.2",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}",
                                "detail": "high"
                            }
                        },
                    ]
                }],
                max_completion_tokens=1500,
                reasoning_effort="none",
                temperature=0.3,
            )
        
        response = await asyncio.wait_for(
            run_in_threadpool(vision_analysis),
            timeout=60.0,
        )
        
        description = response.choices[0].message.content
        logger.info(f"Successfully analyzed image {file_name} with vision AI: {len(description)} chars")
        return description, "GPT-4o Vision (Image Analysis)"
        
    except Exception as e:
        logger.error(f"Vision analysis failed for {file_name}: {e}")
        raise


@router.post("/{document_id}/extract")
async def trigger_extraction(
    document_id: str,
    force_method: Optional[str] = None,  # NEW: "ocr", "vision", or None for auto
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Manually trigger or re-run text extraction for a single document.

    Args:
    ----
        document_id: Document ID
        force_method: Force extraction method - "ocr" for text extraction, "vision" for image analysis, None for auto
        user: Current authenticated user
        user_supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    Returns:
    -------
        Extraction result with extracted text and metadata

    """
    import os
    import tempfile

    from legal_portal.core.data_models import DocumentType
    from legal_portal.services.file_processors.pdf_processor import process_pdf

    async with EXTRACTION_SEMAPHORE:
        return await _trigger_extraction_inner(
            document_id=document_id,
            force_method=force_method,
            user=user,
            user_supabase=user_supabase,
            service_supabase=service_supabase,
        )


async def _trigger_extraction_inner(
    document_id: str,
    force_method: Optional[str],
    user,
    user_supabase,
    service_supabase,
):
    """Inner implementation of trigger_extraction, called under EXTRACTION_SEMAPHORE."""
    import os
    import tempfile

    from legal_portal.core.data_models import DocumentType
    from legal_portal.services.file_processors.pdf_processor import process_pdf

    try:
        logger.info(f"Trigger extraction: doc_id={document_id}, user={user['id']}")

        # Get document with ownership verification (include extracted_text for Clio text doc check)
        response = (
            user_supabase.table("documents")
            .select("id, file_name, file_type, storage_path, case_id, extracted_text, metadata, cases!inner(user_id)")
            .eq("id", document_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        document = response.data[0]

        # Verify ownership
        if document["cases"]["user_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Get classification from metadata
        classification = document.get("metadata", {}).get("classification", "TEXT")
        logger.debug(f"Document classification: {classification}, force_method: {force_method}")

        # Check if we should use vision analysis directly (skip OCR)
        use_vision_analysis = False
        if force_method == "vision":
            use_vision_analysis = True
            logger.info(f"Forcing vision analysis (user requested)")
        elif force_method != "ocr" and classification == "IMAGE":
            use_vision_analysis = True
            logger.info(f"Using vision analysis based on classification (IMAGE)")

        # Download file from storage, or use extracted_text for Clio import-only docs.
        # Clio import records store content in extracted_text but may not have a real
        # storage file (legacy imports pre-dating the storage upload step, or cases where
        # the upload failed). Use the existing text as file_bytes so re-extract works.
        storage_path = document["storage_path"]
        doc_metadata = document.get("metadata") or {}
        is_clio_source = bool(doc_metadata.get("clio_source"))
        is_clio_text_doc = bool(
            document.get("extracted_text") and is_clio_source
        )

        if is_clio_text_doc:
            logger.debug(f"Using extracted_text as file content for Clio document {document_id}")
            file_bytes = document["extracted_text"].encode("utf-8")
        else:
            logger.debug(f"Downloading file from storage: {storage_path}")
            try:
                file_bytes = service_supabase.storage.from_("documents").download(storage_path)
            except Exception as download_err:
                # Clio notes are plain text — if storage upload failed during import,
                # recover the content from metadata (subject line) rather than 404ing.
                if is_clio_source and doc_metadata.get("clio_type") == "note":
                    subject = doc_metadata.get("clio_subject", "")
                    clio_date = doc_metadata.get("clio_date", "")
                    recovered_text = f"Subject: {subject}"
                    if clio_date:
                        recovered_text += f"\nDate: {clio_date}"
                    logger.warning(
                        f"[EXTRACT:CLIO_RECOVER] doc_id={document_id} | "
                        f"Storage download failed, recovering Clio note from metadata"
                    )
                    file_bytes = recovered_text.encode("utf-8")
                    # Update the document with recovered text so this doesn't happen again
                    user_supabase.table("documents").update({
                        "extracted_text": recovered_text,
                        "extracted_at": datetime.utcnow().isoformat(),
                        "extraction_quality": "low",
                        "extraction_method": "clio_metadata_recovery",
                        "status": DocumentStatus.READY,
                        "extraction_error": None,
                        "updated_at": datetime.utcnow().isoformat(),
                    }).eq("id", document_id).execute()
                    logger.info(
                        f"[EXTRACT:CLIO_RECOVER] doc_id={document_id} | "
                        f"Recovered and saved. Text length={len(recovered_text)}"
                    )
                    return {
                        "document_id": document_id,
                        "extracted_text_length": len(recovered_text),
                        "extraction_method": "clio_metadata_recovery",
                        "extraction_quality": "low",
                        "message": (
                            "Clio note recovered from metadata. Original content may be "
                            "incomplete — re-import from Clio for full text."
                        ),
                    }

                err_msg = f"File not found in storage (path: {storage_path})"
                logger.error(f"Storage download failed for {document_id}: {download_err}")
                user_supabase.table("documents").update({
                    "status": DocumentStatus.DOWNLOAD_FAILED,
                    "extraction_error": err_msg,
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", document_id).execute()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document file not found in storage. The source file may need to be re-imported.",
                )

            if not file_bytes:
                # Same recovery for Clio notes when storage returns empty
                if is_clio_source and doc_metadata.get("clio_type") == "note":
                    subject = doc_metadata.get("clio_subject", "")
                    clio_date = doc_metadata.get("clio_date", "")
                    recovered_text = f"Subject: {subject}"
                    if clio_date:
                        recovered_text += f"\nDate: {clio_date}"
                    logger.warning(
                        f"[EXTRACT:CLIO_RECOVER] doc_id={document_id} | "
                        f"Storage returned empty, recovering Clio note from metadata"
                    )
                    user_supabase.table("documents").update({
                        "extracted_text": recovered_text,
                        "extracted_at": datetime.utcnow().isoformat(),
                        "extraction_quality": "low",
                        "extraction_method": "clio_metadata_recovery",
                        "status": DocumentStatus.READY,
                        "extraction_error": None,
                        "updated_at": datetime.utcnow().isoformat(),
                    }).eq("id", document_id).execute()
                    return {
                        "document_id": document_id,
                        "extracted_text_length": len(recovered_text),
                        "extraction_method": "clio_metadata_recovery",
                        "extraction_quality": "low",
                        "message": (
                            "Clio note recovered from metadata. Original content may be "
                            "incomplete — re-import from Clio for full text."
                        ),
                    }

                user_supabase.table("documents").update({
                    "status": DocumentStatus.DOWNLOAD_FAILED,
                    "extraction_error": "Storage returned empty file",
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", document_id).execute()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document file not found in storage. The source file may need to be re-imported.",
                )

        # Determine file type and process
        file_name = document["file_name"]
        file_type = document["file_type"]

        extracted_text = ""
        extraction_method = ""
        extraction_quality = "high"
        ocr_provider = None
        extraction_error = None
        page_count = None
        signature_detection = None

        # Never use vision for plain text files
        if use_vision_analysis and file_type in ["text/plain", "txt"]:
            use_vision_analysis = False

        # If we should use vision analysis, skip OCR and go straight to image analysis
        if use_vision_analysis and file_type in ["image/png", "image/jpeg", "image/jpg", "image/heic"]:
            logger.info(f"Skipping OCR, going straight to vision analysis for {file_name}")
            try:
                # Get case context
                case_id = document.get("case_id")
                if not case_id:
                    logger.error(f"No case_id found in document {document_id}")
                    raise ValueError("Document missing case_id")

                case_context = await get_case_context(case_id, user_supabase)

                # Analyze image with context
                visual_description, vision_method = await analyze_image_with_vision(
                    file_bytes, file_name, case_context
                )

                if visual_description and len(visual_description) > 50:
                    extracted_text = visual_description
                    extraction_method = vision_method
                    extraction_quality = "high"
                    ocr_provider = "openai_vision_analysis"

                    # Update metadata to mark as visual content
                    document_metadata = document.get("metadata", {}) or {}
                    document_metadata["is_visual_content"] = True
                    document_metadata["extraction_method_used"] = "vision_direct"

                    # Update classification to IMAGE if it wasn't already
                    if classification != "IMAGE":
                        document_metadata["classification"] = "IMAGE"
                        logger.info(f"Updated classification to IMAGE for {file_name}")

                    user_supabase.table("documents").update({
                        "metadata": document_metadata
                    }).eq("id", document_id).execute()

                    logger.info(f"Successfully analyzed image using vision analysis: {file_name}")
                else:
                    extraction_error = "Vision analysis returned insufficient content"
                    extraction_method = "vision_failed"
                    extraction_quality = "low"

            except Exception as vision_err:
                logger.error(f"Vision analysis failed for {file_name}: {vision_err}", exc_info=True)
                extraction_error = f"Vision analysis failed: {str(vision_err)}"
                extraction_method = "vision_failed"
                extraction_quality = "low"

        elif file_type in ["application/pdf", "pdf"]:
            # Write to temp file for PDF processing
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            try:
                result = await process_pdf(
                    file_path=tmp_path,
                    document_type=DocumentType.CASE_DOCUMENT,
                    original_filename=file_name,
                )
                extracted_text = result.content
                extraction_method = result.extraction_method or "unknown"
                extraction_quality = result.extraction_quality or "high"
                ocr_provider = result.ocr_provider
                extraction_error = result.extraction_error
                page_count = result.page_count
                signature_detection = result.signature_detection
            finally:
                os.unlink(tmp_path)

        elif file_type in ["text/plain", "txt"]:
            if file_name.lower().endswith(".eml"):
                # Route .eml files to email parser even if file_type is text/plain
                tmp_path = None
                try:
                    import tempfile

                    with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
                        tmp.write(file_bytes)
                        tmp_path = tmp.name

                    result = await process_eml(
                        file_path=tmp_path,
                        document_type=DocumentType.CORRESPONDENCE,
                        original_filename=file_name,
                    )

                    extracted_text = result.content
                    extraction_method = result.extraction_method or "email_parser"
                    extraction_quality = result.extraction_quality or "high"
                    extraction_error = result.extraction_error

                    logger.info(f"Successfully extracted email content from {file_name}: {len(extracted_text)} chars")
                except Exception as e:
                    extraction_error = f"Email extraction failed: {str(e)}"
                    extraction_method = "failed"
                    extraction_quality = "low"
                    logger.error(f"Email extraction error for {file_name}: {e}", exc_info=True)
                finally:
                    if tmp_path:
                        import os
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
            else:
                # Plain text file
                extracted_text = file_bytes.decode("utf-8", errors="replace")
                extraction_method = "direct_text"
                extraction_quality = "high"

        elif file_type in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "docx",
            "doc",
        ] or file_name.lower().endswith((".docx", ".doc")):
            # Microsoft Word document - extract text directly (no OCR needed)
            try:
                extracted_text, docx_backend = ContentExtractor.extract_text_from_docx_with_method(file_bytes)
                extracted_text = extracted_text.strip()
                extraction_method = docx_backend
                extraction_quality = "high" if len(extracted_text) > 50 else "medium"
                logger.info(f"DOCX extraction ({docx_backend}): {len(extracted_text)} characters")
            except Exception as docx_err:
                # DOCX parsing failed — try reading as plain text (legacy .doc files
                # from Clio are often just text with a .doc extension)
                logger.warning(f"DOCX extraction failed for {file_name}: {docx_err}, trying plain text fallback")
                try:
                    fallback_text = file_bytes.decode("utf-8", errors="replace").strip()
                    if fallback_text and len(fallback_text) > 10:
                        extracted_text = fallback_text
                        extraction_method = "text_fallback"
                        extraction_quality = "medium"
                        logger.info(f"Plain text fallback succeeded for {file_name}: {len(extracted_text)} chars")
                    else:
                        raise ValueError("Plain text fallback returned insufficient content")
                except Exception:
                    extraction_error = f"DOCX extraction failed: {str(docx_err)}"
                    extraction_method = "none"
                    extraction_quality = "low"
                    logger.error(f"DOCX extraction error for {file_name}: {docx_err}")

        elif file_type in ["image/png", "image/jpeg", "image/jpg"] or file_name.lower().endswith((".png", ".jpg", ".jpeg")):
            # Image file - OCR extraction
            from legal_portal.config.default import get_settings
            _settings = get_settings()

            if _settings.ocr_remote_enabled:
                # Route to Cloud Run OCR service (Google Vision only)
                try:
                    from legal_portal.utils.ocr_service_client import (
                        get_ocr_client, OCRServiceError, OCRConfigError,
                    )
                    ocr_client = get_ocr_client()
                    img_content_type = file_type if file_type in ["image/png", "image/jpeg", "image/jpg"] else "image/png"
                    result = await ocr_client.extract_text(
                        file_bytes, file_name, img_content_type,
                    )
                    extracted_text = result["full_text"]
                    extraction_method = f"cloud_run_ocr ({result['provider']})"
                    extraction_quality = "high"
                    ocr_provider = result["provider"]
                    logger.info(
                        f"Remote OCR completed for {file_name}",
                        extra={
                            "trace_id": result.get("trace_id"),
                            "provider": result["provider"],
                            "latency_ms": result.get("latency_ms"),
                        },
                    )

                    # Check if the OCR result is a photo rejection message or low-quality result
                    if is_photo_rejection_message(extracted_text) or is_low_quality_ocr_result(extracted_text):
                        reason = "rejection message" if is_photo_rejection_message(extracted_text) else "low-quality OCR result"
                        logger.info(f"OCR detected photo (non-text image) in {file_name} ({reason}), switching to visual analysis")
                        try:
                            case_id = document.get("case_id")
                            if not case_id:
                                logger.error(f"No case_id found in document {document_id}")
                                raise ValueError("Document missing case_id")
                            case_context = await get_case_context(case_id, user_supabase)
                            visual_description, vision_method = await analyze_image_with_vision(
                                file_bytes, file_name, case_context
                            )
                            if visual_description and len(visual_description) > 50:
                                extracted_text = visual_description
                                extraction_method = vision_method
                                extraction_quality = "high"
                                ocr_provider = "openai_vision_analysis"
                                document_metadata = document.get("metadata", {}) or {}
                                document_metadata["is_visual_content"] = True
                                user_supabase.table("documents").update({
                                    "metadata": document_metadata
                                }).eq("id", document_id).execute()
                                logger.info(f"Successfully analyzed photo content for {file_name}")
                            else:
                                logger.warning(f"Vision analysis returned insufficient content for {file_name}")
                        except Exception as vision_err:
                            logger.error(f"Vision analysis failed for {file_name}: {vision_err}", exc_info=True)

                except OCRConfigError as e:
                    # Missing OCR_SERVICE_TOKEN/URL — config error, always fall back to local
                    logger.warning(f"OCR remote misconfigured ({e}), falling back to local OCR for {file_name}")
                    try:
                        google_client = GoogleVisionClient.get_instance()
                        if google_client.is_available:
                            import asyncio
                            from starlette.concurrency import run_in_threadpool
                            def do_google_ocr():
                                return google_client.extract_text_from_image(file_bytes)
                            vision_text = await asyncio.wait_for(
                                run_in_threadpool(do_google_ocr), timeout=30.0,
                            )
                            if vision_text and vision_text.strip():
                                extracted_text = vision_text
                                extraction_method = "Google Cloud Vision"
                                extraction_quality = "high"
                                ocr_provider = "google_vision"
                            else:
                                raise ValueError("Google Vision returned empty text")
                        else:
                            raise ValueError("Google Vision client not available")
                    except Exception as fallback_err:
                        extraction_error = f"Image OCR failed (remote misconfigured, local fallback failed): {str(fallback_err)}"
                        extraction_method = "failed"
                        extraction_quality = "low"
                        logger.error(f"Local OCR fallback also failed for {file_name}: {fallback_err}")

                except Exception as e:
                    logger.error(f"Remote OCR failed for {file_name}: {e}")
                    # Always fall back to local OCR on remote failure
                    logger.warning(f"Falling back to local OCR for {file_name}")
                    try:
                        google_client = GoogleVisionClient.get_instance()
                        if google_client.is_available:
                            import asyncio
                            from starlette.concurrency import run_in_threadpool
                            def do_google_ocr():
                                return google_client.extract_text_from_image(file_bytes)
                            vision_text = await asyncio.wait_for(
                                run_in_threadpool(do_google_ocr), timeout=30.0,
                            )
                            if vision_text and vision_text.strip():
                                extracted_text = vision_text
                                extraction_method = "Google Cloud Vision"
                                extraction_quality = "high"
                                ocr_provider = "google_vision"
                            else:
                                raise ValueError("Google Vision returned empty text")
                        else:
                            raise ValueError("Google Vision client not available")
                    except Exception as fallback_err:
                        extraction_error = f"Image OCR failed: {str(fallback_err)}"
                        extraction_method = "failed"
                        extraction_quality = "low"
                        logger.error(f"Fallback OCR also failed for {file_name}: {fallback_err}")
            else:
                # Local OCR path (OCR_REMOTE_ENABLED=false)
                try:
                    google_client = GoogleVisionClient.get_instance()
                    if google_client.is_available:
                        try:
                            import asyncio
                            from starlette.concurrency import run_in_threadpool
                            def do_google_ocr():
                                return google_client.extract_text_from_image(file_bytes)
                            vision_text = await asyncio.wait_for(
                                run_in_threadpool(do_google_ocr), timeout=30.0,
                            )
                            if vision_text and vision_text.strip():
                                extracted_text = vision_text
                                extraction_method = "Google Cloud Vision"
                                extraction_quality = "high"
                                ocr_provider = "google_vision"
                                logger.info(f"Successfully extracted text from {file_name} using Google Vision")
                                # Check if the OCR result is a photo rejection message or low-quality result
                                if is_photo_rejection_message(extracted_text) or is_low_quality_ocr_result(extracted_text):
                                    reason = "rejection message" if is_photo_rejection_message(extracted_text) else "low-quality OCR result"
                                    logger.info(f"Google Vision detected photo (non-text image) in {file_name} ({reason}), switching to visual analysis")
                                    try:
                                        case_id = document.get("case_id")
                                        if not case_id:
                                            logger.error(f"No case_id found in document {document_id}")
                                            raise ValueError("Document missing case_id")
                                        case_context = await get_case_context(case_id, user_supabase)
                                        visual_description, vision_method = await analyze_image_with_vision(
                                            file_bytes, file_name, case_context
                                        )
                                        if visual_description and len(visual_description) > 50:
                                            extracted_text = visual_description
                                            extraction_method = vision_method
                                            extraction_quality = "high"
                                            ocr_provider = "openai_vision_analysis"
                                            document_metadata = document.get("metadata", {}) or {}
                                            document_metadata["is_visual_content"] = True
                                            user_supabase.table("documents").update({
                                                "metadata": document_metadata
                                            }).eq("id", document_id).execute()
                                            logger.info(f"Successfully analyzed photo content for {file_name}")
                                        else:
                                            logger.warning(f"Vision analysis returned insufficient content for {file_name}")
                                    except Exception as vision_err:
                                        logger.error(f"Vision analysis failed for {file_name}: {vision_err}", exc_info=True)
                            else:
                                raise ValueError("Google Vision returned empty text")
                        except Exception as google_err:
                            logger.warning(f"{file_name}: Google Vision failed ({google_err}). Falling back to GPT-4o Vision.")
                            raise
                    else:
                        raise ValueError("Google Vision client not available")
                except Exception:
                    try:
                        import asyncio
                        import base64
                        from starlette.concurrency import run_in_threadpool
                        from legal_portal.utils.openai_client import OpenAIClient
                        logger.info(f"Using GPT-4o Vision for {file_name}")
                        openai_client = OpenAIClient()
                        client = openai_client.client
                        mime_type = _detect_image_mime(file_bytes, file_name)
                        file_bytes, mime_type = _ensure_vision_compatible(file_bytes, mime_type)
                        base64_image = base64.b64encode(file_bytes).decode("utf-8")
                        prompt = (
                            f"Extract ALL text from this legal document image. "
                            f"Filename: {file_name}. "
                            "This is a scanned document that needs OCR text extraction. "
                            "Maintain the logical structure and layout. "
                            "If there are tables, preserve the row/column relationship. "
                            "Provide the text verbatim including all numbers, dates, and names. Do not summarize."
                        )
                        def gpt4o_ocr():
                            return client.chat.completions.create(
                                model="gpt-5.2",
                                messages=[{
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:{mime_type};base64,{base64_image}",
                                                "detail": "high"
                                            }
                                        },
                                    ]
                                }],
                                max_completion_tokens=4000,
                                reasoning_effort="none",
                                temperature=0.0,
                            )
                        response = await asyncio.wait_for(
                            run_in_threadpool(gpt4o_ocr), timeout=60.0,
                        )
                        extracted_text = response.choices[0].message.content
                        extraction_method = "GPT-5.2 Vision"
                        extraction_quality = "high"
                        ocr_provider = "openai"
                        logger.info(f"Successfully extracted text from {file_name} using GPT-4o Vision")
                        # Check if the OCR result is a photo rejection message or low-quality result
                        if is_photo_rejection_message(extracted_text) or is_low_quality_ocr_result(extracted_text):
                            reason = "rejection message" if is_photo_rejection_message(extracted_text) else "low-quality OCR result"
                            logger.info(f"Detected photo (non-text image) in {file_name} ({reason}), switching to visual analysis")
                            try:
                                case_id = document.get("case_id")
                                if not case_id:
                                    logger.error(f"No case_id found in document {document_id}")
                                    raise ValueError("Document missing case_id")
                                case_context = await get_case_context(case_id, user_supabase)
                                visual_description, vision_method = await analyze_image_with_vision(
                                    file_bytes, file_name, case_context
                                )
                                if visual_description and len(visual_description) > 50:
                                    extracted_text = visual_description
                                    extraction_method = vision_method
                                    extraction_quality = "high"
                                    ocr_provider = "openai_vision_analysis"
                                    document_metadata = document.get("metadata", {}) or {}
                                    document_metadata["is_visual_content"] = True
                                    user_supabase.table("documents").update({
                                        "metadata": document_metadata
                                    }).eq("id", document_id).execute()
                                    logger.info(f"Successfully analyzed photo content for {file_name}")
                                else:
                                    logger.warning(f"Vision analysis returned insufficient content for {file_name}")
                            except Exception as vision_err:
                                logger.error(f"Vision analysis failed for {file_name}: {vision_err}", exc_info=True)
                    except Exception as ocr_err:
                        extraction_error = f"Image OCR failed: {str(ocr_err)}"
                        extraction_method = "failed"
                        extraction_quality = "low"
                    logger.error(f"Image extraction error for {file_name}: {ocr_err}")

        elif file_type in ["message/rfc822", "eml"] or file_name.lower().endswith(".eml"):
            # Email file (.eml)
            tmp_path = None
            try:
                import tempfile

                # Write to temp file for eml processing
                with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name

                # Process eml file asynchronously
                result = await process_eml(
                    file_path=tmp_path,
                    document_type=DocumentType.CORRESPONDENCE,
                    original_filename=file_name,
                )

                extracted_text = result.content
                extraction_method = result.extraction_method or "email_parser"
                extraction_quality = result.extraction_quality or "high"
                extraction_error = result.extraction_error

                logger.info(f"Successfully extracted email content from {file_name}: {len(extracted_text)} chars")
            except Exception as e:
                extraction_error = f"Email extraction failed: {str(e)}"
                extraction_method = "failed"
                extraction_quality = "low"
                logger.error(f"Email extraction error for {file_name}: {e}", exc_info=True)
            finally:
                if tmp_path:
                    import os
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        else:
            # Unsupported type
            extraction_error = f"Unsupported file type for extraction: {file_type}"
            extraction_method = "none"
            extraction_quality = "low"

        # Sanitize extracted text to remove NULL characters that PostgreSQL can't store
        extracted_text = sanitize_text_for_db(extracted_text)

        # Update classification if force_method was used (and not already updated)
        if force_method and not use_vision_analysis:
            new_classification = "IMAGE" if force_method == "vision" else "TEXT"
            if new_classification != classification:
                logger.info(f"Updating classification from {classification} to {new_classification} based on force_method")
                document_metadata = document.get("metadata", {}) or {}
                document_metadata["classification"] = new_classification
                document_metadata["classification_updated_by_user"] = True
                user_supabase.table("documents").update({
                    "metadata": document_metadata
                }).eq("id", document_id).execute()
                # Keep local copy in sync so later metadata merges don't overwrite this update.
                document["metadata"] = document_metadata

        # Update document with extraction results
        update_data = {
            "extracted_text": extracted_text,
            "extraction_method": extraction_method,
            "extraction_quality": extraction_quality,
            "ocr_provider": ocr_provider,
            "extraction_error": extraction_error,
            "page_count": page_count,
            "extracted_at": datetime.utcnow().isoformat() if extracted_text else None,
            "updated_at": datetime.utcnow().isoformat(),
            "status": DocumentStatus.READY if extracted_text and extracted_text.strip() else DocumentStatus.EXTRACTION_FAILED,
        }
        if signature_detection:
            document_metadata = document.get("metadata", {}) or {}
            document_metadata["signature_detection"] = signature_detection
            update_data["metadata"] = document_metadata

        update_result = await _update_document_with_retry(user_supabase, document_id, update_data)

        logger.info(
            f"Extraction complete for {document_id}: method={extraction_method}, "
            f"quality={extraction_quality}, chars={len(extracted_text or '')}"
        )

        # Build and persist initial document registry (Stage 1) for deferred extraction
        # Always build — filename alone provides type + signature classification
        try:
            _build_and_persist_registry(
                document_id=document_id,
                file_name=file_name,
                file_type=file_type,
                extracted_text=extracted_text or "",
                extraction_quality=extraction_quality,
                extraction_method=extraction_method,
                signature_detection=signature_detection,
                supabase_client=user_supabase,
            )
        except Exception as reg_err:
            logger.warning(f"Registry build failed for {document_id}: {reg_err}")

        return {
            "document_id": document_id,
            "extracted_text": extracted_text,
            "extraction_method": extraction_method,
            "extraction_quality": extraction_quality,
            "ocr_provider": ocr_provider,
            "extraction_error": extraction_error,
            "page_count": page_count,
            "content_length": len(extracted_text),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in trigger_extraction for {document_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error extracting text: {str(e)}",
        ) from e


@router.post("/{document_id}/replace", response_model=DocumentResponse)
async def replace_document_file(
    document_id: str,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Replace the file for an existing document record.

    Useful for fixing documents with download errors or corruption.
    """
    import os
    import tempfile

    from legal_portal.services.file_processors.pdf_processor import process_pdf

    try:
        logger.info(f"Replacing file for document {document_id}")

        # Get existing document with ownership verification
        response = (
            user_supabase.table("documents")
            .select("id, case_id, cases!inner(user_id), storage_path")
            .eq("id", document_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        existing_doc = response.data[0]
        case_id = existing_doc["case_id"]

        # Verify ownership
        if existing_doc["cases"]["user_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Read new file content
        file_content = await file.read()

        # Delete old file from storage if it exists
        if existing_doc.get("storage_path"):
            try:
                service_supabase.storage.from_("documents").remove([existing_doc["storage_path"]])
            except Exception as e:
                logger.warning(f"Failed to delete old file {existing_doc['storage_path']}: {e}")

        # Use unified processor for validation and upload
        processor = DocumentProcessor()
        doc_record = await processor.process_and_upload(
            file_content=file_content,
            filename=file.filename,
            user_id=user["id"],
            case_id=case_id,
            supabase_client=service_supabase,
            is_intake_form=False,  # Can be adjusted if needed
            content_type=file.content_type,
        )

        # Extract text from the new file
        extracted_text = ""
        extraction_method = ""
        extraction_quality = "high"
        ocr_provider = None
        extraction_error = None
        page_count = None

        file_type = doc_record.get("file_type", file.content_type)
        file_name = doc_record.get("file_name", file.filename)

        if file_type in ["application/pdf", "pdf"] or file_name.lower().endswith(".pdf"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name

            try:
                result = await process_pdf(
                    file_path=tmp_path,
                    document_type=DocumentType.CASE_DOCUMENT,
                    original_filename=file_name,
                )
                extracted_text = result.content
                extraction_method = result.extraction_method or "unknown"
                extraction_quality = result.extraction_quality or "high"
                ocr_provider = result.ocr_provider
                extraction_error = result.extraction_error
                page_count = result.page_count
            finally:
                os.unlink(tmp_path)
        elif file_type in ["text/plain", "txt"] or file_name.lower().endswith(".txt"):
            if file_name.lower().endswith(".eml"):
                # Route .eml files to email parser even if file_type is text/plain
                try:
                    import tempfile

                    with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
                        tmp.write(file_content)
                        tmp_path = tmp.name

                    try:
                        result = await process_eml(
                            file_path=tmp_path,
                            document_type=DocumentType.CORRESPONDENCE,
                            original_filename=file_name,
                        )

                        extracted_text = result.content
                        extraction_method = result.extraction_method or "email_parser"
                        extraction_quality = result.extraction_quality or "high"
                        extraction_error = result.extraction_error

                        logger.info(f"Successfully extracted email content from {file_name}: {len(extracted_text)} chars")
                    finally:
                        import os
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
                except Exception as e:
                    extraction_error = f"Email extraction failed: {str(e)}"
                    extraction_method = "failed"
                    extraction_quality = "low"
                    logger.error(f"Email extraction error for {file_name}: {e}")
            else:
                try:
                    extracted_text = file_content.decode("utf-8", errors="replace")
                    extraction_method = "direct_text"
                    extraction_quality = "high"
                except Exception as e:
                    extraction_error = f"Failed to decode text: {e}"
                    extraction_method = "failed"
                    extraction_quality = "low"
        elif file_type in [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "docx",
            "doc",
        ] or file_name.lower().endswith((".docx", ".doc")):
            try:
                extracted_text, docx_backend = ContentExtractor.extract_text_from_docx_with_method(file_content)
                extracted_text = extracted_text.strip()
                extraction_method = docx_backend
                extraction_quality = "high" if len(extracted_text) > 50 else "medium"
                logger.info(f"DOCX replacement extraction ({docx_backend}): {len(extracted_text)} characters")
            except Exception as docx_err:
                extraction_error = f"DOCX extraction failed: {docx_err}"
                extraction_method = "failed"
                extraction_quality = "low"
                logger.error(f"DOCX extraction error for {file_name}: {docx_err}")

        elif file_type in ["message/rfc822", "eml"] or file_name.lower().endswith(".eml"):
            # Email file (.eml)
            try:
                import tempfile

                # Write to temp file for eml processing
                with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name

                try:
                    # Process eml file asynchronously
                    result = await process_eml(
                        file_path=tmp_path,
                        document_type=DocumentType.CORRESPONDENCE,
                        original_filename=file_name,
                    )

                    extracted_text = result.content
                    extraction_method = result.extraction_method or "email_parser"
                    extraction_quality = result.extraction_quality or "high"
                    extraction_error = result.extraction_error

                    logger.info(f"Successfully extracted email content from {file_name}: {len(extracted_text)} chars")
                finally:
                    # Clean up temp file
                    import os
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            except Exception as e:
                extraction_error = f"Email extraction failed: {str(e)}"
                extraction_method = "failed"
                extraction_quality = "low"
                logger.error(f"Email extraction error for {file_name}: {e}")

        # Sanitize extracted text to remove NULL characters that PostgreSQL can't store
        extracted_text = sanitize_text_for_db(extracted_text)

        # Update existing document record
        update_data = {
            "file_name": file_name,
            "file_type": file_type,
            "file_size": doc_record["file_size"],
            "storage_path": doc_record["storage_path"],
            "status": DocumentStatus.READY if extracted_text else DocumentStatus.EXTRACTION_FAILED,
            "extracted_text": extracted_text if extracted_text else None,
            "extraction_method": extraction_method,
            "extraction_quality": extraction_quality,
            "ocr_provider": ocr_provider,
            "extraction_error": extraction_error,
            "page_count": page_count,
            "metadata": {**existing_doc.get("metadata", {}), **doc_record["metadata"]},
            "updated_at": datetime.utcnow().isoformat(),
        }

        update_response = user_supabase.table("documents").update(update_data).eq("id", document_id).execute()

        if not update_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update document record"
            )

        return update_response.data[0]

    except HTTPException:
        raise
    except ValidationError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"code": e.error_code, "detail": str(e)},
        )
    except Exception as e:
        logger.error(f"Error in replace_document_file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error replacing document: {str(e)}"
        ) from e
