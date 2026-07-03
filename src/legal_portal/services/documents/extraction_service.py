"""Document extraction business logic extracted from the documents route module.

Contains the core extraction orchestrator (_trigger_extraction_inner), image/vision
helpers, document classification, registry construction, and retry utilities.
These were extracted from api/routes/documents.py to separate business logic from
HTTP routing concerns.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from legal_portal.api.middleware.retry import retry_async
from legal_portal.api.utils.content_extractor import DocumentProcessor as ContentExtractor
from legal_portal.core.data_models import (
    DocumentStatus,
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.services.documents.document_registry_service import DocumentRegistryService
from legal_portal.services.file_processors.eml_processor import process_eml
from legal_portal.utils.google_vision_client import GoogleVisionClient
from legal_portal.utils.security import sanitize_text_for_db

logger = logging.getLogger(__name__)

__all__ = [
    "_build_and_persist_registry",
    "_update_document_with_retry",
    "is_photo_rejection_message",
    "is_low_quality_ocr_result",
    "classify_document_type",
    "get_case_context",
    "_detect_image_mime",
    "_ensure_vision_compatible",
    "analyze_image_with_vision",
    "_trigger_extraction_inner",
]

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
        ) from db_err


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
                model="gpt-5.5",
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
            logger.info("Forcing vision analysis (user requested)")
        elif force_method != "ocr" and classification == "IMAGE":
            use_vision_analysis = True
            logger.info("Using vision analysis based on classification (IMAGE)")

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
                ) from download_err

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
                        get_ocr_client, OCRConfigError,
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
                                model="gpt-5.5",
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
