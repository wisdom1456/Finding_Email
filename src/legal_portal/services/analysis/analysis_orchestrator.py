"""Analysis orchestration logic extracted from analysis_core route module.

Contains the background processing pipeline, deferred extraction,
document download, and main case processing. Artifact generation/storage
and email deduplication have been split into dedicated sub-modules.
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from starlette.concurrency import run_in_threadpool

from legal_portal.api.middleware.retry import retry_sync
from legal_portal.core.analysis_state import (
    AnalysisCancelledError,
    _analysis_is_cancelled,
    _cancel_analysis,
    _update_analysis_progress,
    _update_case_with_retry,
    _upsert_with_retry,
)
from legal_portal.core.signature_detection import (
    _apply_signature_verification_override,
    _infer_signature_detection_from_text,
    _is_pdf_like_document,
    _is_signature_inference_candidate,
    _sample_text_for_state_hash,
)
from legal_portal.config.default import get_settings
from legal_portal.core.data_models import (
    ClioMatterContext,
    DocumentStatus,
    DocumentType,
    ProcessedDocument,
    ProcessingResult,
    SkippedDocument,
)
from legal_portal.services.analysis.main_processor import process_case_documents
from legal_portal.services.shared.progress_manager import ProgressManager
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.security import sanitize_text_for_db
from legal_portal.utils.throttled_db_writer import ThrottledDBWriter
from legal_portal.utils.type_safety import safe_str, safe_str_required, sanitize_nested_dict

# ---------------------------------------------------------------------------
# Re-exports: symbols moved to sub-modules but still imported by
# analysis_core.py via this module.
# ---------------------------------------------------------------------------
from legal_portal.services.analysis.analysis_artifacts import (  # noqa: F401
    ARTIFACT_BUCKET,
    ARTIFACT_PREFIX,
    SIGNED_URL_TTL,
    _attach_signed_artifact_urls,
    _generate_and_store_artifacts,
    _generate_eml_bytes,
    _html_to_plain_text,
    _store_artifact,
)
from legal_portal.services.analysis.email_dedup import (  # noqa: F401
    _dedup_email_threads,
)

logger = logging.getLogger(__name__)


async def _extract_deferred_documents(
    deferred_docs: list,
    supabase,
    progress_manager,
    analysis_id: str,
) -> dict:
    """Extract text for documents that were uploaded with skip_extraction=True.

    Downloads each file from storage, runs the appropriate processor,
    and updates the DB record with extracted text.

    Returns dict mapping doc_id -> updated fields dict.
    """
    import mimetypes as _mt

    from legal_portal.services.file_processors import PROCESSOR_MAP
    from legal_portal.services.file_processors.eml_processor import process_eml
    from legal_portal.core.data_models import DocumentType

    settings = get_settings()
    results = {}

    for i, doc in enumerate(deferred_docs):
        doc_id = doc["id"]
        doc_name = doc.get("file_name", "unknown")
        file_type = doc.get("file_type", "")
        storage_path = doc.get("storage_path", "")

        logger.info(f"[DEFERRED:{i+1}/{len(deferred_docs)}] Extracting: {doc_name}")

        try:
            # Download file from Supabase storage
            file_bytes = supabase.storage.from_("documents").download(storage_path)
            if not file_bytes:
                raise ValueError(f"Empty file downloaded from {storage_path}")

            # Determine processor
            processor = PROCESSOR_MAP.get(file_type)
            lower_name = doc_name.lower()

            # Extension-based fallback routing
            if not processor or (file_type == "text/plain" and lower_name.endswith(".eml")):
                if lower_name.endswith(".eml"):
                    processor = process_eml
                elif lower_name.endswith(".pdf"):
                    processor = PROCESSOR_MAP.get("application/pdf")
                elif lower_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff")):
                    processor = PROCESSOR_MAP.get("image/png") or PROCESSOR_MAP.get("image/jpeg")

            if not processor:
                logger.warning(f"[DEFERRED] No processor for {doc_name} (type={file_type})")
                results[doc_id] = {
                    "extraction_method": "unsupported",
                    "extraction_quality": "low",
                    "extraction_error": f"No processor for type: {file_type}",
                    "status": DocumentStatus.EXTRACTION_FAILED,
                }
                supabase.table("documents").update(results[doc_id]).eq("id", doc_id).execute()
                continue

            # Write to temp file for processor
            ext = "." + doc_name.rsplit(".", 1)[-1] if "." in doc_name else ""
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            try:
                # Handle image files with remote OCR
                if file_type.startswith("image/") or lower_name.endswith(
                    (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff")
                ):
                    if settings.ocr_remote_enabled:
                        from legal_portal.utils.ocr_service_client import get_ocr_client
                        content_type, _ = _mt.guess_type(doc_name)
                        content_type = content_type or "image/png"
                        ocr_client = get_ocr_client()
                        ocr_result = await ocr_client.extract_text(
                            file_bytes, doc_name, content_type,
                        )
                        extracted_text = ocr_result["full_text"]
                        extraction_method = f"cloud_run_ocr ({ocr_result['provider']})"
                        ocr_provider = ocr_result["provider"]
                        extraction_error = None
                        page_count = ocr_result.get("page_count")
                    else:
                        # Fall through to processor (image_processor handles local OCR)
                        doc_type = DocumentType.CASE_DOCUMENT
                        processed = await processor(tmp_path, doc_type, doc_name, None)
                        extracted_text = processed.content
                        extraction_method = processed.extraction_method or "unknown"
                        ocr_provider = processed.ocr_provider
                        extraction_error = processed.extraction_error
                        page_count = processed.page_count
                else:
                    # PDF, EML, text, etc.
                    doc_type = DocumentType.CASE_DOCUMENT
                    if doc.get("metadata", {}).get("is_intake_form"):
                        doc_type = DocumentType.INTAKE_FORM

                    processed = await processor(tmp_path, doc_type, doc_name, None)
                    extracted_text = processed.content
                    extraction_method = processed.extraction_method or "unknown"
                    ocr_provider = processed.ocr_provider
                    extraction_error = processed.extraction_error
                    page_count = processed.page_count
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            # Sanitize
            if extracted_text:
                extracted_text = sanitize_text_for_db(extracted_text)

            # Determine quality
            text_len = len((extracted_text or "").strip())
            if text_len == 0:
                extraction_quality = "low"
                doc_status = DocumentStatus.EXTRACTION_FAILED
            elif text_len < 200:
                extraction_quality = "medium"
                doc_status = DocumentStatus.NEEDS_REVIEW
            else:
                extraction_quality = "high"
                doc_status = DocumentStatus.READY

            update_data = {
                "extracted_text": extracted_text if extracted_text else None,
                "extraction_method": extraction_method,
                "extraction_quality": extraction_quality,
                "ocr_provider": ocr_provider,
                "extraction_error": extraction_error,
                "page_count": page_count,
                "extracted_at": datetime.utcnow().isoformat() if extracted_text else None,
                "updated_at": datetime.utcnow().isoformat(),
                "status": doc_status,
            }
            supabase.table("documents").update(update_data).eq("id", doc_id).execute()
            results[doc_id] = update_data

            # Upload PDF attachments from EML files
            if lower_name.endswith(".eml") and 'processed' in dir():
                pdf_attachments = getattr(getattr(processed, 'metadata', None), 'attachments', None) or []
                if pdf_attachments and doc.get("case_id") and doc.get("user_id"):
                    case_id = doc["case_id"]
                    user_id = doc["user_id"]

                    # Fetch existing content hashes for this case
                    existing_docs = (
                        supabase.table("documents")
                        .select("id, metadata")
                        .eq("case_id", case_id)
                        .execute()
                    )
                    existing_hashes = set()
                    for ed in (existing_docs.data or []):
                        meta = ed.get("metadata") or {}
                        if isinstance(meta, dict) and meta.get("content_hash"):
                            existing_hashes.add(meta["content_hash"])

                    for att in pdf_attachments:
                        att_hash = att["content_hash"]
                        att_filename = att["filename"]

                        if att_hash in existing_hashes:
                            logger.info(
                                f"[DEFERRED] Skipping duplicate attachment "
                                f"{att_filename} (hash={att_hash[:12]}...)"
                            )
                            continue

                        # Upload attachment bytes to storage
                        att_storage_path = f"{user_id}/{case_id}/{att_filename}"
                        try:
                            supabase.storage.from_("documents").upload(
                                att_storage_path, att["bytes"],
                            )
                        except Exception as upload_err:
                            logger.warning(
                                f"[DEFERRED] Storage upload failed for {att_filename}: {upload_err}"
                            )
                            continue

                        # Insert new document record
                        att_record = {
                            "id": str(uuid.uuid4()),
                            "case_id": case_id,
                            "user_id": user_id,
                            "file_name": att_filename,
                            "file_type": "application/pdf",
                            "file_size": len(att["bytes"]),
                            "storage_path": att_storage_path,
                            "extraction_method": "eml_attachment",
                            "status": DocumentStatus.PENDING,
                            "metadata": {
                                "parent_email_id": doc_id,
                                "content_hash": att_hash,
                            },
                            "created_at": datetime.utcnow().isoformat(),
                            "updated_at": datetime.utcnow().isoformat(),
                        }
                        try:
                            supabase.table("documents").insert(att_record).execute()
                            existing_hashes.add(att_hash)
                            logger.info(
                                f"[DEFERRED] Created document for EML attachment: "
                                f"{att_filename} (parent={doc_name})"
                            )
                        except Exception as insert_err:
                            logger.error(
                                f"[DEFERRED] Failed to insert attachment {att_filename}: {insert_err}"
                            )

            logger.info(
                f"[DEFERRED] Extracted {doc_name}: "
                f"{text_len} chars, method={extraction_method}, quality={extraction_quality}"
            )

        except Exception as e:
            logger.error(f"[DEFERRED] Failed to extract {doc_name}: {e}", exc_info=True)
            error_update = {
                "extraction_method": "failed",
                "extraction_quality": "low",
                "extraction_error": str(e)[:500],
                "status": DocumentStatus.EXTRACTION_FAILED,
                "updated_at": datetime.utcnow().isoformat(),
            }
            try:
                supabase.table("documents").update(error_update).eq("id", doc_id).execute()
            except Exception:
                pass
            results[doc_id] = error_update

        # Progress update
        if progress_manager and analysis_id:
            pct = 3 + int((i + 1) / len(deferred_docs) * 2)  # 3-5% range
            await progress_manager.publish_progress(
                channel_id=analysis_id,
                message=f"Extracted {i+1}/{len(deferred_docs)} documents...",
                phase="deferred_extraction",
                percent=pct,
                timestamp=datetime.utcnow().isoformat(),
            )

    return results


def _download_and_extract_documents(
    case_id: str, documents: List[Dict[str, Any]], supabase, temp_dir: str
) -> tuple[Optional[str], List[str], Dict[str, str], List[SkippedDocument]]:
    """Download and extract documents synchronously."""
    file_paths = []
    intake_form_path = None
    path_to_id_map = {}
    skipped_documents = []

    for doc in documents:
        # Check status first - skip critical failures
        status = doc.get("status")
        if status in [DocumentStatus.DOWNLOAD_FAILED, DocumentStatus.CORRUPTED, DocumentStatus.SKIPPED]:
            logger.info(f"Auto-skipping document with status {status}: {doc['file_name']}")
            skipped_documents.append(
                SkippedDocument(
                    document_id=doc["id"],
                    file_name=doc["file_name"],
                    reason=f"Status is {status}",
                    error_type=status or "UNKNOWN",
                    recommendation="Re-upload or fix the document in the verification dashboard.",
                )
            )
            continue

        # Skip documents flagged as junk
        if doc.get("is_flagged_as_junk"):
            logger.info(f"Skipping junk-flagged document: {doc['file_name']}")
            continue

        storage_path = doc.get("storage_path")

        # Check if we have neither text nor a file
        text_content = doc.get("manual_text") or doc.get("extracted_text")
        if not text_content and not storage_path:
            logger.warning(f"Skipping document with no content and no storage path: {doc['file_name']}")
            skipped_documents.append(
                SkippedDocument(
                    document_id=doc["id"],
                    file_name=doc["file_name"],
                    reason="No extracted text and no storage file found.",
                    error_type="MISSING_CONTENT",
                    recommendation="Please re-upload this document.",
                )
            )
            continue
        # Robust sanitization to avoid filesystem issues with special characters (spaces, parentheses, etc)
        safe_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", doc["file_name"])
        # Ensure we don't have too many underscores and keep the extension
        safe_filename = re.sub(r"_+", "_", safe_filename)
        temp_path = os.path.join(temp_dir, safe_filename)

        # Skip video and audio files
        file_type = doc.get("file_type", "").lower()
        file_name_lower = doc["file_name"].lower()

        video_audio_types = [
            "video/",
            "audio/",  # Any video or audio MIME type
            "application/x-mpegurl",
            "application/vnd.apple.mpegurl",  # Streaming
        ]
        video_audio_extensions = [
            ".mov",
            ".mp4",
            ".avi",
            ".mkv",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",  # Video
            ".mp3",
            ".wav",
            ".aac",
            ".flac",
            ".m4a",
            ".ogg",
            ".wma",
            ".aiff",  # Audio
        ]

        is_video_audio = any(file_type.startswith(vtype) for vtype in video_audio_types) or any(
            file_name_lower.endswith(ext) for ext in video_audio_extensions
        )

        if is_video_audio:
            logger.info(f"Skipping video/audio file: {doc['file_name']}")
            continue

        # Check if document has manual_text (user-corrected) or extracted_text
        # Priority: manual_text > extracted_text > download and process
        text_content = doc.get("manual_text") or doc.get("extracted_text")
        if text_content:
            text_source = "manual_text" if doc.get("manual_text") else "extracted_text"
            logger.debug(f"Using {text_source} for: {doc['file_name']}")
            # Save text to temporary file
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(text_content)
            path_to_id_map[temp_path] = doc["id"]
        else:
            # Download file from Supabase Storage with validation and retry
            max_retries = 3
            expected_size = doc.get("file_size", 0)
            download_success = False

            # Check file size limits before downloading
            # More restrictive for zips since they could contain videos
            MAX_SIZE_ZIP_MB = 50
            MAX_SIZE_OTHER_MB = 100

            is_zip = doc["file_name"].lower().endswith(".zip")
            size_limit_mb = MAX_SIZE_ZIP_MB if is_zip else MAX_SIZE_OTHER_MB
            size_limit_bytes = size_limit_mb * 1024 * 1024

            if expected_size > size_limit_bytes:
                file_size_mb = expected_size / (1024 * 1024)
                logger.warning(
                    f"Skipping large file {doc['file_name']}: "
                    f"{file_size_mb:.1f}MB exceeds {size_limit_mb}MB limit"
                )
                skipped_documents.append(
                    SkippedDocument(
                        document_id=doc["id"],
                        file_name=doc["file_name"],
                        reason=f"File too large ({file_size_mb:.1f}MB). Maximum size is {size_limit_mb}MB for {'zip files' if is_zip else 'this file type'}.",
                        error_type="FILE_TOO_LARGE",
                        recommendation="Large files are skipped to prevent timeouts. Consider extracting key content manually or splitting into smaller files.",
                    )
                )
                continue

            for attempt in range(max_retries):
                try:
                    file_data = supabase.storage.from_("documents").download(storage_path)
                    actual_size = len(file_data)

                    # Validate download content is not just whitespace (corrupted upload indicator)
                    if actual_size > 0 and actual_size < 100 and not file_data.strip():
                        logger.warning(
                            f"Download for {doc['file_name']} appears to be only whitespace "
                            f"({actual_size} bytes). Potential corrupted upload."
                        )
                        # We don't retry whitespace errors as they are likely permanent in storage
                        break

                    # Validate download size if we know expected size
                    if expected_size > 0 and actual_size < expected_size * 0.9:
                        logger.warning(
                            f"Download may be truncated for {doc['file_name']}: "
                            f"got {actual_size} bytes, expected {expected_size} bytes "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                            continue

                    # Write file and ensure it's flushed to disk
                    with open(temp_path, "wb") as f:
                        f.write(file_data)
                        f.flush()
                        os.fsync(f.fileno())  # Force write to disk

                    # Verify file was written correctly
                    written_size = os.path.getsize(temp_path)
                    if written_size != actual_size:
                        logger.error(
                            f"File write mismatch for {doc['file_name']}: "
                            f"wrote {written_size}, expected {actual_size}"
                        )
                        if attempt < max_retries - 1:
                            continue

                    download_success = True
                    logger.debug(f"Successfully downloaded {doc['file_name']} ({actual_size} bytes)")
                    # Store mapping of path to document ID
                    path_to_id_map[temp_path] = doc["id"]
                    break

                except Exception as e:
                    logger.warning(
                        f"Download attempt {attempt + 1}/{max_retries} failed for {doc['file_name']}: {e}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))
                    continue

            if not download_success:
                logger.error(f"Failed to download {doc['file_name']} after {max_retries} attempts")
                skipped_documents.append(
                    SkippedDocument(
                        document_id=doc["id"],
                        file_name=doc["file_name"],
                        reason=f"Failed to download after {max_retries} attempts.",
                        error_type="DOWNLOAD_FAILED",
                        recommendation="Please try re-uploading this document.",
                    )
                )
                continue  # Skip this document if all download attempts fail

        # Check if this is a zip file - extract it
        if doc["file_name"].lower().endswith(".zip"):
            import zipfile

            logger.info(f"Extracting zip file: {doc['file_name']}")

            try:
                # Create subdirectory for this zip's contents
                zip_extract_dir = os.path.join(temp_dir, f"{doc['id']}_extracted")
                os.makedirs(zip_extract_dir, exist_ok=True)

                # Extract zip file
                with zipfile.ZipFile(temp_path, "r") as zip_ref:
                    zip_ref.extractall(zip_extract_dir)

                # Force filesystem sync to prevent race conditions
                # Increased delay to 500ms for more reliable extraction
                time.sleep(0.5)
                logger.debug(f"Filesystem sync delay (500ms) after extracting {doc['file_name']}")

                # Add extracted files to processing list (filtering out video/audio)
                extracted_count = 0
                for root, _dirs, files in os.walk(zip_extract_dir):
                    for extracted_file in files:
                        # Skip hidden files and system files
                        if extracted_file.startswith(".") or extracted_file.startswith("__MACOSX"):
                            continue

                        # Skip video/audio files
                        if any(extracted_file.lower().endswith(ext) for ext in video_audio_extensions):
                            logger.info(f"Skipping video/audio in zip: {extracted_file}")
                            continue

                        extracted_path = os.path.join(root, extracted_file)

                        # Verify file exists before adding to processing list
                        if os.path.isfile(extracted_path):
                            file_paths.append(extracted_path)
                            extracted_count += 1
                        else:
                            logger.warning(
                                f"Extracted file not found (filesystem sync issue?): {extracted_path}"
                            )

                logger.info(f"Extracted {extracted_count} files from {doc['file_name']}")

                # Remove the original zip file
                os.remove(temp_path)
                continue  # Skip adding the zip file itself to file_paths

            except zipfile.BadZipFile:
                logger.warning(f"Invalid zip file: {doc['file_name']}")
            except Exception as e:
                logger.warning(f"Failed to extract zip file {doc['file_name']}: {e}")

        # Check if this is an intake form
        # Prioritize: 1) metadata flag, 2) PDF/DOCX files with "intake" in name, 3) other files with "intake"
        is_intake = doc.get("metadata", {}).get("is_intake_form", False)
        is_document_file = doc.get("file_type", "").lower() in [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]

        if not is_intake and "intake" in doc["file_name"].lower():
            # Prefer actual document files (PDF/DOCX) over communications/notes
            if is_document_file:
                is_intake = True

        if is_intake:
            # If we already have an intake form, only replace it with a better one
            # (e.g., PDF/DOCX over communication)
            if intake_form_path:
                # Check if new candidate is a document file and current isn't, or if new is explicitly marked
                current_is_doc = any(
                    doc_check.get("id") == doc.get("id")
                    and doc_check.get("file_type", "").lower()
                    in [
                        "application/pdf",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ]
                    for doc_check in documents
                )
                if is_document_file or (doc.get("metadata", {}).get("is_intake_form") and not current_is_doc):
                    # Add old intake to regular files
                    file_paths.append(intake_form_path)
                    intake_form_path = temp_path
                    logger.info(f"Replaced intake form with better match: {doc['file_name']}")
                else:
                    file_paths.append(temp_path)
            else:
                intake_form_path = temp_path
                logger.info(f"Identified intake form: {doc['file_name']}")
        else:
            file_paths.append(temp_path)

    # If no intake form found, prefer first PDF/DOCX, then any document
    if not intake_form_path and file_paths:
        # Try to find a PDF or DOCX first
        pdf_docx_files = [
            f
            for f in file_paths
            if any(
                doc.get("storage_path") in f
                for doc in documents
                if doc.get("file_type", "").lower()
                in [
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ]
            )
        ]
        if pdf_docx_files:
            intake_form_path = pdf_docx_files[0]
            file_paths.remove(intake_form_path)
        else:
            intake_form_path = file_paths.pop(0)

    return intake_form_path, file_paths, path_to_id_map, skipped_documents



async def process_case_background(case_id: str, analysis_id: str, supabase, provider: str = "openai", *, progress_manager: "ProgressManager" = None):
    """Background task to process case documents.

    Args:
    ----
        case_id: Case ID
        analysis_id: Analysis record ID
        supabase: Supabase client
        provider: AI provider to use
        progress_manager: ProgressManager instance (from app.state)

    """
    bg_start_time = time.time()

    logger.info(
        f"[BACKGROUND:START] [CASE:{case_id}] [ANALYSIS:{analysis_id}] "
        f"Background task started | provider={provider}"
    )

    # Initialize progress channel
    await progress_manager.create_channel(analysis_id)

    # Create temp directory before try block so it's available in finally
    temp_dir = tempfile.mkdtemp(prefix=f"case_{case_id}_")

    try:
        # If user cancelled before we start, bail out quickly.
        if _analysis_is_cancelled(supabase, analysis_id):
            raise AnalysisCancelledError("Analysis cancelled before processing began.")

        # Update status to processing
        supabase.table("analysis_results").update({"status": "processing"}).eq("id", analysis_id).execute()

        # Publish initial progress
        initial_payload = {
            "message": "Starting document analysis...",
            "phase": "initialization",
            "percent": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await progress_manager.publish_progress(channel_id=analysis_id, **initial_payload)
        await _update_analysis_progress(supabase, analysis_id, initial_payload)

        # Get case details
        elapsed = time.time() - bg_start_time
        logger.info(f"[BACKGROUND:FETCH] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] Fetching case and documents")

        case_response = supabase.table("cases").select("*").eq("id", case_id).execute()
        if not case_response.data:
            raise ValueError("Case not found")

        case = case_response.data[0]
        jurisdiction = case.get("jurisdiction", "Florida")  # Get jurisdiction from case

        # Get all documents for the case — explicit column list prevents pulling extracted_text
        # for columns not needed here; text is capped per-doc below in the processing loop.
        _fetch_start = time.time()
        docs_response = (
            supabase.table("documents")
            .select(
                "id, file_name, file_type, storage_path, file_size, metadata, "
                "extracted_text, manual_text, status, extraction_quality, "
                "extraction_method, extracted_at, page_count, ocr_provider, "
                "is_flagged_as_junk"
            )
            .eq("case_id", case_id)
            .execute()
        )
        documents = docs_response.data
        _fetch_elapsed = time.time() - _fetch_start
        logger.info(
            f"[BACKGROUND:FETCH] [CASE:{case_id}] docs_fetch rows={len(documents or [])} "
            f"elapsed={_fetch_elapsed:.2f}s"
        )

        if not documents:
            raise ValueError("No documents found for case")

        elapsed = time.time() - bg_start_time
        logger.info(
            f"[BACKGROUND:PREP] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Preparing documents | total_docs={len(documents)} jurisdiction={jurisdiction}"
        )

        # Step 0: Extract text for deferred documents (bulk imports skip extraction)
        deferred_docs = [
            d for d in documents
            if d.get("extraction_method") == "deferred"
            and not d.get("extracted_text")
        ]
        if deferred_docs:
            logger.info(
                f"[BACKGROUND:DEFERRED] [CASE:{case_id}] "
                f"Extracting text for {len(deferred_docs)} deferred documents"
            )
            await progress_manager.publish_progress(
                channel_id=analysis_id,
                message=f"Extracting text from {len(deferred_docs)} documents...",
                phase="deferred_extraction",
                percent=3,
                timestamp=datetime.utcnow().isoformat(),
            )
            deferred_results = await _extract_deferred_documents(
                deferred_docs, supabase, progress_manager, analysis_id,
            )
            # Merge results back into documents list
            for doc_id, result in deferred_results.items():
                for doc in documents:
                    if doc["id"] == doc_id:
                        doc.update(result)
                        break

            # Step 0c: Extract any newly created attachment documents
            # Re-fetch documents to pick up any new attachment docs created during Step 0
            new_docs_resp = (
                supabase.table("documents")
                .select("*")
                .eq("case_id", case_id)
                .eq("extraction_method", "eml_attachment")
                .eq("status", DocumentStatus.PENDING)
                .execute()
            )
            new_att_docs = new_docs_resp.data or []
            if new_att_docs:
                logger.info(
                    f"[BACKGROUND:ATTACHMENTS] [CASE:{case_id}] "
                    f"Extracting {len(new_att_docs)} EML attachment PDFs"
                )
                att_results = await _extract_deferred_documents(
                    new_att_docs, supabase, progress_manager, analysis_id,
                )
                # Add extracted attachment docs to the documents list
                for att_doc in new_att_docs:
                    att_id = att_doc["id"]
                    if att_id in att_results:
                        att_doc.update(att_results[att_id])
                    documents.append(att_doc)

        # Step 0a: Content-hash dedup (if not already done)
        # Check whether any docs already have content_hash (indicates prior dedup run)
        has_hashes = any((d.get("metadata") or {}).get("content_hash") for d in documents)
        if not has_hashes:
            logger.info(
                f"[BACKGROUND:CONTENT_DEDUP] [CASE:{case_id}] "
                f"Running content-hash dedup (first time)"
            )
            from legal_portal.services.cases.content_dedup import run_content_hash_dedup
            dedup_result = await run_in_threadpool(run_content_hash_dedup, case_id, supabase)
            if dedup_result["duplicates_found"] > 0:
                # Remove flagged duplicates from documents list
                flagged = set(dedup_result.get("flagged_ids", []))
                documents = [d for d in documents if d["id"] not in flagged]
                logger.info(
                    f"[BACKGROUND:CONTENT_DEDUP] [CASE:{case_id}] "
                    f"Removed {dedup_result['duplicates_found']} content-hash duplicates"
                )

        # Step 0b: Deduplicate email threads
        eml_docs_for_dedup = [
            d for d in documents
            if d.get("file_name", "").lower().endswith(".eml")
            and d.get("extracted_text")
            and not d.get("is_flagged_as_junk")
        ]
        if eml_docs_for_dedup:
            logger.info(
                f"[BACKGROUND:DEDUP] [CASE:{case_id}] "
                f"Deduplicating {len(eml_docs_for_dedup)} email threads"
            )
            flagged_ids = await _dedup_email_threads(eml_docs_for_dedup, supabase)
            # Remove flagged docs from documents list so they're excluded from analysis
            if flagged_ids:
                documents = [d for d in documents if d["id"] not in flagged_ids]
                logger.info(
                    f"[BACKGROUND:DEDUP] [CASE:{case_id}] "
                    f"Removed {len(flagged_ids)} duplicate/superseded emails"
                )

        # Step 1: Prepare ProcessedDocument objects directly from DB (no re-extraction)
        from legal_portal.core.data_models import FileMetadata, FileType

        processed_intake = []
        processed_case_docs = []
        skipped_documents = []

        await progress_manager.publish_progress(
            channel_id=analysis_id,
            message="Checking document signatures...",
            phase="preparing",
            percent=5,
            timestamp=datetime.utcnow().isoformat(),
        )

        for doc in documents:
            doc_name = doc.get("file_name", "unknown")
            doc_status = doc.get("status")
            has_extracted = bool(doc.get("extracted_text"))
            extracted_len = len(doc.get("extracted_text") or "")
            has_manual = bool(doc.get("manual_text"))
            manual_len = len(doc.get("manual_text") or "")

            logger.info(
                f"Document '{doc_name}': status={doc_status}, "
                f"has_extracted_text={has_extracted} (len={extracted_len}), "
                f"has_manual_text={has_manual} (len={manual_len}), "
                f"is_junk={doc.get('is_flagged_as_junk')}"
            )

            # Skip docs with critical issues, skipped status, or duplicates
            status = doc.get("status")
            if status in [
                DocumentStatus.DOWNLOAD_FAILED,
                DocumentStatus.CORRUPTED,
                DocumentStatus.SKIPPED,
                DocumentStatus.DUPLICATE,
                "duplicate",  # Also check string value for backwards compatibility
            ]:
                logger.info(f"SKIPPING '{doc_name}': status={status} (excluded from analysis)")
                # Don't add duplicates to skipped list - they're expected and not errors
                if status not in [DocumentStatus.DUPLICATE, "duplicate"]:
                    skipped_documents.append(
                        SkippedDocument(
                            document_id=doc["id"],
                            file_name=doc["file_name"],
                            reason=f"Status is {status}",
                            error_type=str(status) if status else "UNKNOWN",
                            recommendation="Fix in verification hub.",
                        )
                    )
                continue

            if doc.get("is_flagged_as_junk"):
                logger.warning(f"SKIPPING '{doc_name}': flagged as junk")
                continue

            # Get text from manual_text (priority) or extracted_text, capped at 200K chars
            _MAX_DOC_CHARS = 200_000
            text = doc.get("manual_text") or doc.get("extracted_text")
            if text:
                text = text[:_MAX_DOC_CHARS]
            if not text:
                logger.warning(f"SKIPPING '{doc_name}': no text found (manual={has_manual}, extracted={has_extracted})")
                skipped_documents.append(
                    SkippedDocument(
                        document_id=doc["id"],
                        file_name=doc["file_name"],
                        reason="No extracted text found",
                        error_type="MISSING_TEXT",
                        recommendation="Run OCR in verification hub.",
                    )
                )
                continue

            logger.info(f"PROCESSING '{doc_name}': has {len(text)} chars of text")

            # Construct ProcessedDocument
            metadata = FileMetadata(
                file_name=doc["file_name"],
                file_type=FileType.PDF,  # Fallback
                file_size=doc.get("file_size", 0),
            )

            doc_metadata = doc.get("metadata", {}) or {}
            signature_detection = doc_metadata.get("signature_detection")
            if not signature_detection and _is_signature_inference_candidate(
                doc.get("file_name"), doc.get("file_type")
            ):
                signature_detection = _infer_signature_detection_from_text(text)
                if signature_detection:
                    logger.info(
                        "Inferred signature markers from extracted text for %s (doc_id=%s, confidence=%s)",
                        doc_name,
                        doc.get("id"),
                        signature_detection.get("confidence"),
                    )
            signature_detection = _apply_signature_verification_override(
                signature_detection if isinstance(signature_detection, dict) else None,
                doc_metadata,
                file_name=doc.get("file_name"),
            )

            pdoc = ProcessedDocument(
                file_name=doc["file_name"],
                content=text,
                document_type=(
                    DocumentType.INTAKE_FORM
                    if doc_metadata.get("is_intake_form")
                    else DocumentType.CASE_DOCUMENT
                ),
                file_type=FileType.PDF,
                metadata=metadata,
                extraction_quality=doc.get("extraction_quality", "high"),
                extraction_method=doc.get("extraction_method", "db"),
                page_count=doc.get("page_count"),
                ocr_provider=doc.get("ocr_provider"),
                document_id=doc["id"],
                signature_detection=signature_detection,
                attorney_enrichment=doc_metadata.get("attorney_enrichment") or None,
                registry=doc_metadata.get("registry") or None,
            )

            if pdoc.document_type == DocumentType.INTAKE_FORM:
                processed_intake.append(pdoc)
            else:
                processed_case_docs.append(pdoc)

        # Ensure we have at least an intake form
        if not processed_intake:
            # Fallback: if no doc marked as intake, use the first document
            if processed_case_docs:
                processed_intake = [processed_case_docs.pop(0)]
                processed_intake[0].document_type = DocumentType.INTAKE_FORM
            else:
                raise ValueError("No documents with text found for analysis. Please run OCR first.")

        # Cooperative cancellation checkpoint after preparing documents.
        if _analysis_is_cancelled(supabase, analysis_id):
            raise AnalysisCancelledError("Analysis cancelled after preparing documents.")

        case_metadata = case.get("metadata") or {}
        if not isinstance(case_metadata, dict):
            case_metadata = {}

        clio_matter_data = case.get("clio_matter_data") or {}
        if not isinstance(clio_matter_data, dict):
            clio_matter_data = {}

        profile_data: Dict[str, Any] = {}
        try:
            user_id = case.get("user_id")
            if user_id:
                profile_resp = (
                    supabase.table("profiles")
                    .select("full_name,phone,firm_name,email")
                    .eq("id", user_id)
                    .limit(1)
                    .execute()
                )
                if profile_resp.data:
                    profile_data = profile_resp.data[0] or {}
        except Exception as profile_err:
            logger.warning("Failed to load profile context for case %s: %s", case_id, profile_err)

        def _first_non_empty(*values: Any) -> Optional[str]:
            for value in values:
                text = safe_str(value)
                if text:
                    return text
            return None

        def _to_string_list(value: Any) -> List[str]:
            if not isinstance(value, list):
                return []
            return [str(item).strip() for item in value if str(item).strip()]

        practice_areas = _to_string_list(case_metadata.get("practice_areas"))
        legal_issues = _to_string_list(case_metadata.get("legal_issues"))
        if not legal_issues and practice_areas:
            legal_issues = practice_areas[:5]

        clio_practice_area = _first_non_empty(clio_matter_data.get("practice_area"))
        if not legal_issues and clio_practice_area:
            legal_issues = [clio_practice_area]

        key_documents = _to_string_list(case_metadata.get("key_documents"))
        if not key_documents:
            key_documents = [doc.file_name for doc in processed_case_docs[:8] if doc.file_name]

        confirmed_qa_pairs = case_metadata.get("qa_pairs")
        if not isinstance(confirmed_qa_pairs, list):
            confirmed_qa_pairs = []

        clio_context = None
        clio_context_raw = case_metadata.get("clio_matter_context") or case.get("clio_matter_context")
        if isinstance(clio_context_raw, ClioMatterContext):
            clio_context = clio_context_raw
        elif isinstance(clio_context_raw, dict):
            try:
                clio_context = ClioMatterContext(**clio_context_raw)
            except Exception:
                logger.warning("Ignoring invalid clio_matter_context payload for case %s", case_id)

        attorney_name = _first_non_empty(
            case.get("attorney_name"),
            case.get("attorneyName"),
            case_metadata.get("attorney_name"),
            case_metadata.get("attorneyName"),
            profile_data.get("full_name"),
        )
        firm_name = _first_non_empty(
            case.get("firm_name"),
            case.get("firmName"),
            case_metadata.get("firm_name"),
            case_metadata.get("firmName"),
            profile_data.get("firm_name"),
        )
        contact_phone = _first_non_empty(
            case.get("contact_phone"),
            case.get("contactPhone"),
            case_metadata.get("contact_phone"),
            case_metadata.get("contactPhone"),
            profile_data.get("phone"),
        )
        contact_email = _first_non_empty(
            case.get("contact_email"),
            case.get("contactEmail"),
            case_metadata.get("contact_email"),
            case_metadata.get("contactEmail"),
            profile_data.get("email"),
        )
        case_type = _first_non_empty(
            case.get("case_type"),
            case.get("caseType"),
            case_metadata.get("case_type"),
            case_metadata.get("caseType"),
            clio_practice_area,
            practice_areas[0] if practice_areas else None,
        )

        legal_issue = _first_non_empty(
            case_metadata.get("legal_issue"),
            case.get("description"),
            clio_matter_data.get("description"),
            "General legal document analysis",
        )

        # Prepare case_info with extended attorney/firm/contact context.
        case_info = {
            "client_name": case["client_name"],
            "clientName": case["client_name"],
            "reference_number": case.get("reference_number", ""),
            "description": case.get("description", ""),
            "case_id": case_id,
            "jurisdiction": jurisdiction,
            "caseType": case_type,
            "case_type": case_type,
            "attorneyName": attorney_name,
            "attorney_name": attorney_name,
            "firmName": firm_name,
            "firm_name": firm_name,
            "contactPhone": contact_phone,
            "contact_phone": contact_phone,
            "contactEmail": contact_email,
            "contact_email": contact_email,
        }

        # Prepare review_data with richer intake and prioritization context.
        review_data = {
            "legal_issue": legal_issue,
            "legal_issues": legal_issues,
            "key_documents": key_documents,
            "confirmed_qa_pairs": confirmed_qa_pairs,
        }
        if clio_context:
            review_data["clio_matter_context"] = clio_context

        # Track timing and stats for the AI Command Center
        analysis_start_time = time.time()
        total_tokens_used = 0
        try:
            progress_model = OpenAIClient().get_preferred_model("document_analysis", "gpt-5.2")
        except Exception:
            progress_model = "gpt-5.2"

        # Throttle DB progress writes to reduce disk I/O (SSE remains real-time)
        _progress_db_writer = ThrottledDBWriter(
            write_fn=lambda payload: _update_analysis_progress(supabase, analysis_id, payload),
            min_interval_seconds=5.0,
        )

        # Create progress callback that publishes to SSE and stores in DB
        async def progress_callback(
            message: str,
            docs_processed=None,
            phase="",
            percent=0,
            sub_step=None,
            # New parameters for enhanced progress
            stage: Optional[dict] = None,
            document: Optional[dict] = None,
            tokens_used: int = 0,
        ):
            """Publish progress updates to SSE stream and persistent storage."""
            nonlocal total_tokens_used
            total_tokens_used += tokens_used

            payload = {
                "message": message,
                "phase": phase,
                "percent": percent,
                "docs_processed": docs_processed or [],
                "sub_step": sub_step or message,
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Add structured data if provided
            if stage:
                payload["stage"] = stage
            if document:
                payload["document"] = document

            # Add stats periodically
            elapsed = time.time() - analysis_start_time
            payload["stats"] = {
                "elapsedSeconds": elapsed,
                "tokens_used": total_tokens_used,
                "model": progress_model,
            }

            # Cooperative cancellation
            if _analysis_is_cancelled(supabase, analysis_id):
                raise AnalysisCancelledError("Analysis cancelled by user.")

            # Publish SSE (always real-time) and throttled DB write
            await progress_manager.publish_progress(channel_id=analysis_id, **payload)
            await _progress_db_writer.maybe_write(payload)

        # NEW: Initial emission of all documents in pending state so they appear in UI
        for doc in processed_intake + processed_case_docs:
            await progress_callback(
                message=f"Queueing {doc.file_name}...",
                phase="initialization",
                document={"id": doc.document_id or doc.file_name, "name": doc.file_name, "status": "pending"}
            )

        # Call the actual processor (AI passes)
        elapsed = time.time() - bg_start_time
        logger.info(
            f"[BACKGROUND:PROCESSOR] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Calling main processor | intake_docs={len(processed_intake)} case_docs={len(processed_case_docs)}"
        )

        processor_start = time.time()
        result: ProcessingResult = await process_case_documents(
            processed_intake=processed_intake,
            processed_case_docs=processed_case_docs,
            case_info=case_info,
            review_data=review_data,
            progress_callback=progress_callback,
            jurisdiction=jurisdiction,  # Pass jurisdiction to main processor
            skipped_documents=skipped_documents,
            analysis_id=analysis_id,
            supabase_client=supabase,
        )
        processor_duration = time.time() - processor_start
        elapsed = time.time() - bg_start_time

        logger.info(
            f"[BACKGROUND:PROCESSOR] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Processor complete | duration={processor_duration:.1f}s status={result.status}"
        )

        # Persist document extraction results to the database
        if result.processed_documents:
            logger.info(
                f"[BACKGROUND:PERSIST] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
                f"Persisting extraction results | docs={len(result.processed_documents)}"
            )
            for _doc_idx, doc in enumerate(result.processed_documents):
                if doc.document_id:
                    try:
                        # Sanitize content to remove NULL characters that PostgreSQL can't store
                        sanitized_content = sanitize_text_for_db(doc.content)

                        # Prepare update data mapping model fields to database columns
                        update_data = {
                            "extracted_text": sanitized_content,
                            "extraction_method": doc.extraction_method,
                            "extraction_quality": doc.extraction_quality,
                            "extracted_at": doc.extracted_at.isoformat(),
                            "page_count": doc.page_count,
                            "ocr_provider": doc.ocr_provider,
                            "extraction_error": doc.extraction_error,
                            "status": (
                                DocumentStatus.READY
                                if sanitized_content and sanitized_content.strip()
                                else DocumentStatus.EXTRACTION_FAILED
                            ),
                        }
                        supabase.table("documents").update(update_data).eq("id", doc.document_id).execute()

                        # Pace writes: yield every 5 docs to avoid I/O spikes
                        if _doc_idx % 5 == 4:
                            await asyncio.sleep(0.1)
                    except Exception as db_err:
                        logger.warning(
                            f"Failed to persist extraction results for document {doc.document_id}: {db_err}"
                        )

        # Store skipped documents info in analysis_results artifacts
        if result.skipped_documents:
            logger.info(f"Adding {len(result.skipped_documents)} skipped documents to analysis artifacts")
            current_artifacts = result.artifacts or {}
            current_artifacts["skipped_documents"] = [s.model_dump() for s in result.skipped_documents]
            result.artifacts = current_artifacts

        elapsed = time.time() - bg_start_time
        logger.info(
            f"[BACKGROUND:ARTIFACTS] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Generating artifacts | status={result.status}"
        )

        artifacts_meta = _generate_and_store_artifacts(result, case_id, analysis_id, supabase)
        if artifacts_meta:
            result.artifacts = artifacts_meta

        # Strip document content before JSONB save — already persisted to documents table above.
        # Reduces analysis_results.result from ~40MB to <1MB for large cases.
        # Downstream consumers (chat, letters, gap analysis) re-fetch text from documents table.
        # Gate: set STRIP_PROCESSED_DOC_CONTENT=false in env to disable.
        if os.getenv("STRIP_PROCESSED_DOC_CONTENT", "true").lower() != "false":
            for _pdoc in result.processed_documents:
                _pdoc.content = ""

        # Convert result to dict for storage (with mode='json' to serialize datetime)
        result_dict = result.model_dump(mode="json")

        # Size instrumentation — confirms JSONB payload is bounded
        _result_size = len(__import__("json").dumps(result_dict))
        logger.info(
            f"[BACKGROUND:PERSIST] [CASE:{case_id}] result_dict size={_result_size:,} bytes "
            f"| processed_docs={len(result.processed_documents)}"
        )

        # Update analysis record with results
        supabase.table("analysis_results").update(
            {"status": "completed", "result": result_dict, "completed_at": datetime.utcnow().isoformat()}
        ).eq("id", analysis_id).execute()

        # Update case status
        supabase.table("cases").update({"status": "completed"}).eq("id", case_id).execute()

        elapsed = time.time() - bg_start_time
        logger.info(
            f"[BACKGROUND:COMPLETE] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Analysis complete | total_duration={elapsed:.1f}s"
        )

        # Flush any throttled progress before completion
        await _progress_db_writer.flush()

        # Publish completion event
        completion_payload = {
            "message": "Analysis completed successfully!",
            "phase": "completed",
            "percent": 100,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
        }
        await progress_manager.publish_progress(channel_id=analysis_id, **completion_payload)
        await _update_analysis_progress(supabase, analysis_id, completion_payload)

    except AnalysisCancelledError:
        await _cancel_analysis(
            supabase=supabase,
            case_id=case_id,
            analysis_id=analysis_id,
            progress_manager=progress_manager,
        )
        return
    except Exception as e:
        # Log error and update status
        error_message = str(e)
        error_traceback = traceback.format_exc()
        elapsed = time.time() - bg_start_time

        logger.error(
            f"[BACKGROUND:ERROR] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Analysis FAILED | error_type={type(e).__name__} error={error_message}"
        )
        logger.error(f"[BACKGROUND:ERROR] [CASE:{case_id}] Traceback:\n{error_traceback}")

        error_payload = {
            "message": f"Analysis failed: {error_message}",
            "phase": "error",
            "percent": 0,
            "status": "error",
            "error": error_message,
            "timestamp": datetime.utcnow().isoformat(),
        }

        await progress_manager.publish_progress(channel_id=analysis_id, **error_payload)

        # Flush any throttled progress before writing error state
        await _progress_db_writer.flush()

        try:
            supabase.table("analysis_results").update(
                {
                    "status": "error",
                    "error": f"{error_message}\n\n{error_traceback}",
                }
            ).eq("id", analysis_id).execute()
            await _update_analysis_progress(supabase, analysis_id, error_payload)
        except Exception as db_err:
            logger.warning(f"Failed to persist error status to DB: {db_err}")

        supabase.table("cases").update({"status": "error"}).eq("id", case_id).execute()

        # Publish error event
        await progress_manager.publish_progress(
            channel_id=analysis_id,
            message=f"Analysis failed: {error_message}",
            phase="error",
            percent=0,
            status="error",
            error=error_message,
        )

    finally:
        # Cleanup temporary files
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp dir: {cleanup_error}")
