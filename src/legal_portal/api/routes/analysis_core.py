"""Core analysis endpoints and background processing logic.

Contains the 8 primary analysis endpoints (start, cancel, status, results,
streaming, save) along with background processing, deferred extraction,
email dedup, and artifact generation.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
import traceback
import uuid
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Dict, List, Optional

import html2text
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.middleware.retry import retry_sync
from legal_portal.api.rate_limiter import limiter
from legal_portal.api.routes._analysis_helpers import (
    AnalysisCancelledError,
    AnalysisRequest,
    AnalysisResponse,
    StreamingAnalysisSaveRequest,
    _analysis_is_cancelled,
    _apply_signature_verification_override,
    _cancel_analysis,
    _ensure_case_access,
    _fetch_latest_analysis_result,
    _infer_signature_detection_from_text,
    _is_pdf_like_document,
    _is_signature_inference_candidate,
    _sample_text_for_state_hash,
    _update_analysis_progress,
    _update_case_with_retry,
    _upsert_with_retry,
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
from legal_portal.services.main_processor import process_case_documents
from legal_portal.services.progress_manager import ProgressManager
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.security import sanitize_text_for_db
from legal_portal.utils.throttled_db_writer import ThrottledDBWriter
from legal_portal.utils.type_safety import safe_str, safe_str_required, sanitize_nested_dict

router = APIRouter()
logger = logging.getLogger(__name__)

# Re-export for backward compatibility (tests import from analysis module)
from legal_portal.api.routes._analysis_helpers import _db_columns_cache as _DB_COLUMNS_CACHE

__all__ = [
    "router",
    # Endpoints
    "start_analysis",
    "cancel_analysis",
    "cancel_case_analysis",
    "get_analysis_status",
    "get_analysis_results",
    "save_streaming_analysis",
    "stream_case_analysis",
    "get_streaming_result",
    # Background processing
    "process_case_background",
    # Core-specific helpers
    "_extract_deferred_documents",
    "_dedup_email_threads",
    "_download_and_extract_documents",
    # Artifact helpers
    "_html_to_plain_text",
    "_generate_eml_bytes",
    "_store_artifact",
    "_generate_and_store_artifacts",
    "_attach_signed_artifact_urls",
    "ARTIFACT_BUCKET",
    "ARTIFACT_PREFIX",
    "SIGNED_URL_TTL",
    # Streaming parse helpers
    "_convert_statute_recommendations_recursive",
    "_parse_currency",
    "_extract_embedded_json",
    "_extract_section",
    "_extract_list_items",
]

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

async def _dedup_email_threads(
    eml_docs: list,
    supabase,
) -> set:
    """Deduplicate email threads by subject grouping and body hash.

    Flags superseded emails (shorter versions of the same thread) and
    exact duplicates (same body_hash) as is_flagged_as_junk=True.

    Returns set of flagged document IDs.
    """
    if not eml_docs:
        return set()

    def _normalize_subject(subject: str) -> str:
        """Strip Re:/Fwd:/FW: prefixes and normalize."""
        cleaned = re.sub(
            r"^(re:\s*|fwd?:\s*|fw:\s*)+", "", subject, flags=re.IGNORECASE,
        )
        return cleaned.strip().lower()

    def _extract_subject(doc: dict) -> str:
        """Extract subject from extracted_text header."""
        text = doc.get("extracted_text", "")
        for line in text.split("\n"):
            if line.startswith("Subject: "):
                return line[9:].strip()
        return ""

    # Group by normalized subject
    thread_groups: dict[str, list[dict]] = {}
    for doc in eml_docs:
        subject = _extract_subject(doc)
        norm = _normalize_subject(subject)
        if norm:
            thread_groups.setdefault(norm, []).append(doc)

    flagged_ids = set()

    for norm_subject, group in thread_groups.items():
        if len(group) < 2:
            continue

        # Phase 1: Exact duplicate dedup (same body_hash)
        hash_groups: dict[str, list[dict]] = {}
        for doc in group:
            bh = (doc.get("metadata") or {}).get("body_hash", "")
            if bh:
                hash_groups.setdefault(bh, []).append(doc)

        # For exact duplicates, keep the first, flag the rest
        deduped_group = []
        seen_hashes = set()
        for doc in group:
            bh = (doc.get("metadata") or {}).get("body_hash", "")
            if bh and bh in seen_hashes:
                # Exact duplicate
                flagged_ids.add(doc["id"])
                try:
                    supabase.table("documents").update({
                        "is_flagged_as_junk": True,
                        "metadata": {
                            **(doc.get("metadata") or {}),
                            "junk_reason": "exact_duplicate",
                        },
                    }).eq("id", doc["id"]).execute()
                except Exception as e:
                    logger.warning(f"Failed to flag duplicate {doc['id']}: {e}")
            else:
                if bh:
                    seen_hashes.add(bh)
                deduped_group.append(doc)

        # Phase 2: Thread supersession (longer body contains shorter)
        if len(deduped_group) < 2:
            continue

        # Sort by extracted_text length descending
        deduped_group.sort(
            key=lambda d: len(d.get("extracted_text", "")), reverse=True,
        )
        canonical = deduped_group[0]
        canonical_text = canonical.get("extracted_text", "")

        for doc in deduped_group[1:]:
            doc_body = doc.get("extracted_text", "")
            # Check if the shorter email's body is contained in the canonical
            # Strip headers for comparison (body starts after first blank line)
            canon_body = canonical_text.split("\n\n", 1)[-1] if "\n\n" in canonical_text else canonical_text
            short_body = doc_body.split("\n\n", 1)[-1] if "\n\n" in doc_body else doc_body

            if short_body.strip() and short_body.strip() in canon_body:
                flagged_ids.add(doc["id"])
                try:
                    supabase.table("documents").update({
                        "is_flagged_as_junk": True,
                        "metadata": {
                            **(doc.get("metadata") or {}),
                            "junk_reason": "superseded_by_later_reply",
                            "superseded_by": canonical["id"],
                        },
                    }).eq("id", doc["id"]).execute()
                except Exception as e:
                    logger.warning(f"Failed to flag superseded {doc['id']}: {e}")

    logger.info(f"[DEDUP] Flagged {len(flagged_ids)} emails as junk")
    return flagged_ids

ARTIFACT_BUCKET = os.getenv("SUPABASE_ARTIFACT_BUCKET", "documents")
ARTIFACT_PREFIX = os.getenv("ANALYSIS_ARTIFACT_PREFIX", "analysis_artifacts")
SIGNED_URL_TTL = int(os.getenv("ANALYSIS_ARTIFACT_URL_TTL", "3600"))

_HTML2TEXT_CONVERTER = html2text.HTML2Text()
_HTML2TEXT_CONVERTER.ignore_links = False
_HTML2TEXT_CONVERTER.body_width = 0


def _html_to_plain_text(html: Optional[str]) -> str:
    """Convert HTML to plain text for email bodies."""
    if not html:
        return ""
    try:
        return _HTML2TEXT_CONVERTER.handle(html)
    except Exception as exc:
        logger.warning(f"Failed to convert HTML to plain text: {exc}")
        return ""


def _generate_eml_bytes(html: Optional[str], subject: str) -> Optional[bytes]:
    """Generate an EML file from HTML content."""
    if not html:
        return None
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["To"] = "client@example.com"
        msg["From"] = "noreply@legal-portal.local"
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        plain_text = _html_to_plain_text(html)
        msg.set_content(plain_text or "Please see the attached findings email.")
        msg.add_alternative(html, subtype="html")
        return msg.as_bytes()
    except Exception as exc:
        logger.warning(f"Failed to generate EML artifact: {exc}")
        return None


def _store_artifact(storage, path: str, data: bytes, content_type: str) -> Optional[Dict[str, Any]]:
    """Upload artifact bytes to Supabase storage and return metadata."""
    if not data:
        return None
    try:
        # Remove existing artifact if present
        try:
            storage.remove([path])
        except Exception:
            pass
        storage.upload(path, data, {"content-type": content_type})
        return {
            "bucket": ARTIFACT_BUCKET,
            "path": path,
            "content_type": content_type,
            "filename": os.path.basename(path),
        }
    except Exception as exc:
        logger.warning(f"Failed to upload artifact {path}: {exc}")
        return None


def _generate_and_store_artifacts(
    result: ProcessingResult,
    case_id: str,
    analysis_id: str,
    supabase_client,
) -> Dict[str, Dict[str, Any]]:
    """Create EML/HTML/appendix/citation map artifacts and store them in Supabase."""
    artifacts: Dict[str, Dict[str, Any]] = {}
    prefix = f"{ARTIFACT_PREFIX}/{case_id}/{analysis_id}"
    storage = supabase_client.storage.from_(ARTIFACT_BUCKET)

    eml_bytes = _generate_eml_bytes(result.main_letter, f"Findings Email - Case {case_id}")
    if eml_bytes:
        metadata = _store_artifact(storage, f"{prefix}/findings-email.eml", eml_bytes, "message/rfc822")
        if metadata:
            artifacts["letter_eml"] = metadata

    if result.main_letter_with_citations:
        html_bytes = result.main_letter_with_citations.encode("utf-8")
        metadata = _store_artifact(
            storage,
            f"{prefix}/findings-email-cited.html",
            html_bytes,
            "text/html",
        )
        if metadata:
            artifacts["letter_cited_html"] = metadata

    if result.citation_appendix:
        appendix_bytes = result.citation_appendix.encode("utf-8")
        metadata = _store_artifact(storage, f"{prefix}/citation-appendix.html", appendix_bytes, "text/html")
        if metadata:
            artifacts["citation_appendix_html"] = metadata

    if result.citation_map:
        map_bytes = json.dumps(result.citation_map, indent=2).encode("utf-8")
        metadata = _store_artifact(storage, f"{prefix}/citation-map.json", map_bytes, "application/json")
        if metadata:
            artifacts["citation_map"] = metadata

    return {key: value for key, value in artifacts.items() if value}


def _attach_signed_artifact_urls(service_supabase, artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """Attach signed URLs to stored artifact metadata."""
    enriched: Dict[str, Any] = {}
    for key, info in artifacts.items():
        # Skip if info is not a dictionary (e.g. it's a context string)
        if not isinstance(info, dict):
            enriched[key] = info
            continue

        path = info.get("path")
        bucket = info.get("bucket", ARTIFACT_BUCKET)
        if not path:
            enriched[key] = info
            continue
        try:
            signed = service_supabase.storage.from_(bucket).create_signed_url(path, SIGNED_URL_TTL)
            signed_url = signed.get("signedURL")
            enriched[key] = {**info, "signed_url": signed_url}
        except Exception as exc:
            logger.warning(f"Failed to create signed URL for {path}: {exc}")
            enriched[key] = info
    return enriched or artifacts

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



async def process_case_background(case_id: str, analysis_id: str, supabase, provider: str = "openai"):
    """Background task to process case documents.

    Args:
    ----
        case_id: Case ID
        analysis_id: Analysis record ID
        supabase: Supabase client
        provider: AI provider to use

    """
    bg_start_time = time.time()

    logger.info(
        f"[BACKGROUND:START] [CASE:{case_id}] [ANALYSIS:{analysis_id}] "
        f"Background task started | provider={provider}"
    )

    # Initialize progress manager
    progress_manager = ProgressManager.get_instance()
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
            from legal_portal.api.routes.cases import run_content_hash_dedup
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




@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")  # Rate limit AI analysis to prevent abuse
async def start_analysis(
    analysis_request: AnalysisRequest,
    request: Request,  # Required for rate limiter (must be named 'request')
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Start analysis for a case.
    
    On Vercel serverless, BackgroundTasks don't work reliably because the function
    instance is terminated after the response is sent. On Vercel, this endpoint
    returns an SSE stream that runs the analysis inline and streams progress.

    Args:
    ----
        analysis_request: Analysis request data
        request: FastAPI request object
        background_tasks: FastAPI background tasks handler (used for local dev only)
        user: Current authenticated user
        user_supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    Returns:
    -------
        On local: JSON with analysis record (202)
        On Vercel: SSE stream with progress events

    """
    import os
    is_vercel = os.getenv("VERCEL") is not None

    try:
        # Verify case ownership using user client (respects RLS)
        case_response = (
            user_supabase.table("cases")
            .select("id, status")
            .eq("id", analysis_request.case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        case = case_response.data[0]

        # Check if case already has pending/processing analysis
        if case["status"] in ["processing"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Case is already being processed"
            )

        # Clear needs_reanalysis flag when starting new analysis
        user_supabase.table("cases").update({
            "needs_reanalysis": False
        }).eq("id", analysis_request.case_id).execute()

        # Create analysis record using user client
        analysis_response = (
            user_supabase.table("analysis_results")
            .insert({"case_id": analysis_request.case_id, "status": "pending"})
            .execute()
        )

        if not analysis_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create analysis record"
            )

        analysis = analysis_response.data[0]

        # Update case status
        user_supabase.table("cases").update({"status": "processing"}).eq(
            "id", analysis_request.case_id
        ).execute()

        if is_vercel:
            # On Vercel: Return SSE stream that runs analysis inline
            # This keeps the connection alive and prevents function termination
            logger.info(f"[VERCEL] Starting SSE stream for analysis {analysis['id']}")

            async def analysis_stream():
                """Generator that runs analysis and yields progress events with heartbeats."""
                import asyncio

                analysis_id = analysis["id"]

                # First, yield the analysis record so frontend knows the ID immediately
                yield f"data: {json.dumps({'type': 'started', 'analysis': analysis})}\n\n"

                # Create a task for the analysis so we can yield heartbeats while it runs
                analysis_task = asyncio.create_task(
                    process_case_background(
                        analysis_request.case_id,
                        analysis_id,
                        service_supabase,
                        analysis_request.provider,
                    )
                )

                last_progress = None
                heartbeat_count = 0

                try:
                    while not analysis_task.done():
                        # Check for progress updates in database
                        try:
                            result = service_supabase.table("analysis_results").select("status, progress").eq("id", analysis_id).single().execute()

                            if result.data:
                                current_status = result.data.get("status")
                                current_progress = result.data.get("progress")

                                # Yield progress if it changed
                                if current_progress and current_progress != last_progress:
                                    yield f"data: {json.dumps(current_progress)}\n\n"
                                    last_progress = current_progress
                                    heartbeat_count = 0  # Reset heartbeat counter on real progress

                                # Check if analysis completed or failed
                                if current_status in ["completed", "failed", "cancelled"]:
                                    break
                        except Exception as db_err:
                            logger.warning(f"Error checking progress: {db_err}")

                        # Send heartbeat every 10 seconds if no real progress
                        heartbeat_count += 1
                        if heartbeat_count >= 5:  # Every 5 * 2s = 10 seconds
                            yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                            heartbeat_count = 0

                        # Wait 2 seconds before checking again
                        await asyncio.sleep(2)

                    # Wait for the task to complete and get any exception
                    await analysis_task

                    # Fetch final status
                    final = service_supabase.table("analysis_results").select("status, progress").eq("id", analysis_id).single().execute()
                    final_status = final.data.get("status", "unknown") if final.data else "unknown"
                    final_progress = final.data.get("progress") if final.data else None

                    # Yield final progress if different
                    if final_progress and final_progress != last_progress:
                        yield f"data: {json.dumps(final_progress)}\n\n"

                    yield f"data: {json.dumps({'type': 'completed', 'status': final_status})}\n\n"
                    logger.info(f"[VERCEL] Analysis stream completed for {analysis_id} with status: {final_status}")

                except asyncio.CancelledError:
                    logger.warning(f"Analysis stream cancelled for {analysis_id}")
                    analysis_task.cancel()
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                except Exception as e:
                    logger.error(f"Analysis stream error for {analysis_id}: {e}", exc_info=True)
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

            return StreamingResponse(
                analysis_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-transform",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        else:
            # Local development: Use BackgroundTasks as before (returns JSON)
            logger.info(f"[LOCAL] Using BackgroundTasks for {analysis['id']}")
            background_tasks.add_task(
                process_case_background,
                analysis_request.case_id,
                analysis["id"],
                service_supabase,
                analysis_request.provider,
            )
            return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in start_analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error starting analysis: {str(e)}"
        ) from e


@router.post("/cancel/{analysis_id}", status_code=status.HTTP_200_OK)
async def cancel_analysis(
    analysis_id: str,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Cancel an in-progress analysis and un-stick the case.

    This is a cooperative cancel: we mark the analysis as cancelled and set the case back to pending.
    The background worker checks this status and stops as soon as it hits a checkpoint.
    """
    try:
        # Verify analysis belongs to the user (RLS via user_supabase)
        resp = (
            user_supabase.table("analysis_results")
            .select("id, case_id, status")
            .eq("id", analysis_id)
            .execute()
        )
        if not resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analysis not found",
            )

        analysis = resp.data[0]
        case_id = analysis["case_id"]

        progress_manager = ProgressManager.get_instance()
        await _cancel_analysis(
            supabase=user_supabase,
            case_id=case_id,
            analysis_id=analysis_id,
            progress_manager=progress_manager,
        )

        return {"status": "cancelled", "analysis_id": analysis_id, "case_id": case_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel analysis: {str(e)}",
        ) from e


@router.post("/cancel-case/{case_id}", status_code=status.HTTP_200_OK)
async def cancel_case_analysis(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    r"""Cancel the most recent in-progress analysis for a case.

    This enables "Cancel" from the cases list UI without needing an analysis_id.
    """
    try:
        # Verify ownership of the case (RLS via user_supabase)
        case_resp = (
            user_supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )
        if not case_resp.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Find the newest analysis for this case that is still pending/processing
        analysis_resp = (
            user_supabase.table("analysis_results")
            .select("id, status")
            .eq("case_id", case_id)
            .in_("status", ["pending", "processing"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not analysis_resp.data:
            return {"status": "no_active_analysis", "case_id": case_id}

        analysis_id = analysis_resp.data[0]["id"]

        progress_manager = ProgressManager.get_instance()
        await _cancel_analysis(
            supabase=user_supabase,
            case_id=case_id,
            analysis_id=analysis_id,
            progress_manager=progress_manager,
        )

        return {"status": "cancelled", "analysis_id": analysis_id, "case_id": case_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel case analysis: {str(e)}",
        ) from e


@router.get("/status/{case_id}", response_model=AnalysisResponse)
async def get_analysis_status(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Get the latest analysis status for a case.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Latest analysis result

    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get latest analysis for case
        response = (
            supabase.table("analysis_results")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found for this case"
            )

        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching analysis status: {str(e)}",
        ) from e


@router.get("/results/{case_id}")
async def get_analysis_results(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Get the full analysis results for a completed case.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    Returns:
    -------
        Analysis results (ProcessingResult)

    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get most recent analysis (regardless of status)
        response = (
            supabase.table("analysis_results")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data:
            return {"status": "pending", "message": "Analysis results not yet available"}

        analysis = response.data[0]
        # Include status in the response so frontend can handle it
        result_payload = analysis.get("result") or {}
        result_payload["status"] = analysis.get("status")
        result_payload["analysis_id"] = analysis.get("id")
        result_payload["created_at"] = analysis.get("created_at")
        result_payload["error"] = analysis.get("error")
        artifacts = result_payload.get("artifacts")
        if artifacts:
            result_payload["artifacts"] = _attach_signed_artifact_urls(service_supabase, artifacts)

        return result_payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching analysis results: {str(e)}",
        ) from e


class StreamingAnalysisSaveRequest(BaseModel):
    """Request to save streaming analysis result."""

    content: str = Field(..., description="The markdown content from streaming analysis")


@router.post("/stream/{case_id}/save")
async def save_streaming_analysis(
    case_id: str,
    request: StreamingAnalysisSaveRequest,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Save the result of a streaming analysis.
    
    Parses the markdown content and embedded JSON, then stores as an analysis result.
    The embedded JSON (in ```json block) contains structured data for letter generation.
    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases")
            .select("id, client_name, jurisdiction")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=404, detail="Case not found")

        case_data = case_response.data[0]

        # Parse embedded JSON from the markdown content
        structured_data = _extract_embedded_json(request.content)

        # Build case analysis from extracted data
        # Use clean issue names from structured JSON, not raw markdown
        key_issues_list = []
        if structured_data.get("primary_issues"):
            for issue in structured_data["primary_issues"]:
                issue_name = issue.get("name", "")
                if issue_name:
                    # Include strength and statutes for context
                    strength = issue.get("strength", "")
                    statutes = issue.get("statutes", [])
                    if statutes:
                        key_issues_list.append(f"{issue_name} ({strength}) - {', '.join(statutes)}")
                    else:
                        key_issues_list.append(f"{issue_name} ({strength})")

        # Fallback to markdown extraction if no structured data
        if not key_issues_list:
            key_issues_list = _extract_list_items(request.content, "Legal Issues Identified")

        case_analysis = {
            "case_summary": _extract_section(request.content, "Case Overview"),
            "key_issues": key_issues_list,
            "practice_area": structured_data.get("practice_area", "General Legal Matter"),
            "relevant_statutes": [],  # Extracted from structured_data below
        }

        # Add statutes from primary issues
        if structured_data.get("primary_issues"):
            for issue in structured_data["primary_issues"]:
                if issue.get("statutes"):
                    for statute in issue["statutes"]:
                        case_analysis["relevant_statutes"].append({
                            "statute": statute,
                            "relevance": issue.get("name", ""),
                        })

        # Build multi-stage compatible result for letter generation
        multi_stage_result = None
        if structured_data:
            # Build timeline with correct field names for FactMatrix model
            timeline_events = []
            for d in structured_data.get("key_dates", []):
                timeline_events.append({
                    "date": d.get("date", ""),
                    "description": d.get("event", ""),  # FactMatrix uses 'description' not 'event'
                    "source_document": "Streaming Analysis",  # Required field
                    "significance": None,
                    "supporting_evidence": [],
                })

            # Build properly structured parties list for FactMatrix/Party model compatibility
            structured_parties = []
            for p in structured_data.get("parties", []):
                party_role = (p.get("role") or "").lower()
                is_opposing = party_role not in ["client", "plaintiff", "claimant", "attorney", "counsel"]
                structured_parties.append({
                    "name": p.get("name", ""),
                    "role": p.get("role", ""),
                    "contact_info": None,
                    "first_mentioned_in": "Streaming Analysis",
                    "is_opposing_party": is_opposing,
                    "entity_type": p.get("entity_type", "unknown"),
                })

            multi_stage_result = {
                "fact_matrix": {
                    "parties": structured_parties,
                    "timeline": timeline_events,
                    "financial_data": [],  # Required field for FactMatrix
                    "key_documents": [],   # Required field for FactMatrix
                    "preliminary_issues": [i.get("name", "") for i in structured_data.get("primary_issues", [])],  # Required
                    "financial_items": [],  # Keep for backward compatibility
                },
                "issue_map": {
                    "primary_issues": [
                        {
                            "issue_name": i.get("name", ""),  # Frontend expects issue_name for demand letters
                            "category": i.get("category", ""),
                            "applicable_statutes": i.get("statutes", []),
                            "strength": i.get("strength", "Moderate"),
                        }
                        for i in structured_data.get("primary_issues", [])
                    ],
                },
                "letter_structure": {
                    "style": structured_data.get("recommended_letter_type", "numbered_findings"),
                    "intro": "Key Findings",
                    "issue_format": "numbered_sections_with_headers",
                    "reasoning": "Default structure for comprehensive legal analysis",
                },
                # Deep analysis structure needed for letter generation
                "deep_analysis": {
                    "issue_analyses": [
                        {
                            "issue_name": i.get("name", ""),
                            "legal_standard": f"Legal standard for {i.get('name', '')} - see full analysis for details",
                            "fact_application": f"Fact application for {i.get('name', '')} - see full analysis for details",
                            "statute_analysis": ", ".join(i.get("statutes", [])) if i.get("statutes") else None,
                            "case_law_support": None,
                            "remedies_available": ["See full analysis for detailed remedies"],
                            "procedural_requirements": None,
                            "confidence_level": i.get("strength", "moderate").lower(),
                            "supporting_evidence": [],
                        }
                        for i in structured_data.get("primary_issues", [])
                    ],
                    "risk_assessment": {
                        "major_risks": [],
                        "risk_mitigation_steps": [],
                        "statute_of_limitations_concerns": None,
                        "evidence_gaps": [],
                    },
                    "deadline_tracking": [],
                    "evidence_strength": {
                        "strong_evidence": [],
                        "weak_evidence": [],
                        "missing_evidence": [],
                        "overall_strength": "moderate",
                    },
                    "overall_case_strength": structured_data.get("case_strength", "Moderate"),
                    "key_strengths": [],
                    "key_challenges": [],
                    "is_viable": True,
                    "viability_reasoning": "Based on streaming analysis",
                    "recommend_demand_letter": structured_data.get("recommended_letter_type") in ["demand", "demand_with_findings"],
                },
            }

            # Add financial data if present (parse currency strings to floats)
            if structured_data.get("financial_summary"):
                fin = structured_data["financial_summary"]
                total_claimed = _parse_currency(fin.get("total_claimed"))
                documented_damages = _parse_currency(fin.get("documented_damages"))

                if total_claimed > 0:
                    # Add to financial_items (legacy field for backward compatibility)
                    multi_stage_result["fact_matrix"]["financial_items"].append({
                        "description": "Total Claimed",
                        "amount": total_claimed,
                    })
                    # Add to financial_data (correct field for FactMatrix model)
                    multi_stage_result["fact_matrix"]["financial_data"].append({
                        "amount": total_claimed,
                        "description": "Total Claimed",
                        "source_document": "Streaming Analysis",
                        "payment_type": "claimed",
                        "category": "damages_claimed",
                        "date": None,
                    })

                if documented_damages > 0:
                    multi_stage_result["fact_matrix"]["financial_items"].append({
                        "description": "Documented Damages",
                        "amount": documented_damages,
                    })
                    multi_stage_result["fact_matrix"]["financial_data"].append({
                        "amount": documented_damages,
                        "description": "Documented Damages",
                        "source_document": "Streaming Analysis",
                        "payment_type": "claimed",
                        "category": "damages_claimed",
                        "date": None,
                    })

            # Verify statutes against legal corpus for letter generation
            # Defensive check: ensure multi_stage_result exists before modifying it
            if multi_stage_result is None:
                logger.warning("[STREAM] multi_stage_result is None, skipping verified_statutes conversion")
                multi_stage_result = {}

            try:
                from legal_portal.services.statute_recommendation_service import StatuteRecommendationService
                jurisdiction = case_data.get("jurisdiction", "Florida")
                statute_service = StatuteRecommendationService(jurisdiction=jurisdiction)

                # Get legal issues from structured data
                legal_issues = [i.get("name", "") for i in structured_data.get("primary_issues", [])]

                # Get verified statutes from corpus (jurisdiction already set in constructor)
                verified_statutes = statute_service.recommend_statutes(
                    case_facts=request.content[:2000],  # First 2000 chars of analysis
                    legal_issues=legal_issues,
                )

                # Validate verified_statutes is a list
                if not isinstance(verified_statutes, list):
                    logger.warning(f"[STREAM] verified_statutes is not a list (type: {type(verified_statutes)}), converting to empty list")
                    verified_statutes = []

                # Convert StatuteRecommendation dataclass objects to dicts for JSON serialization
                from dataclasses import asdict
                converted_statutes = []
                conversion_errors = []

                for idx, statute in enumerate(verified_statutes):
                    try:
                        # Check if it's a StatuteRecommendation instance
                        from legal_portal.services.statute_recommendation_service import StatuteRecommendation
                        if isinstance(statute, StatuteRecommendation):
                            converted = asdict(statute)
                            # Validate conversion produced a dict
                            if not isinstance(converted, dict):
                                raise TypeError(f"asdict() returned {type(converted)}, expected dict")
                            converted_statutes.append(converted)
                        else:
                            # If it's already a dict, validate and use it
                            if isinstance(statute, dict):
                                converted_statutes.append(statute)
                            else:
                                logger.warning(f"[STREAM] Item {idx} in verified_statutes is unexpected type: {type(statute)}")
                                conversion_errors.append(f"Item {idx}: {type(statute)}")
                    except (TypeError, AttributeError) as conv_err:
                        logger.error(f"[STREAM] Failed to convert StatuteRecommendation at index {idx}: {conv_err}")
                        conversion_errors.append(f"Item {idx}: {str(conv_err)}")
                    except Exception as conv_err:
                        logger.error(f"[STREAM] Unexpected error converting item {idx}: {conv_err}")
                        conversion_errors.append(f"Item {idx}: {str(conv_err)}")

                multi_stage_result["verified_statutes"] = converted_statutes

                if conversion_errors:
                    logger.warning(f"[STREAM] Had {len(conversion_errors)} conversion errors: {conversion_errors}")

                logger.info(f"[STREAM] Converted {len(converted_statutes)} StatuteRecommendation objects to dicts for {jurisdiction}")

            except (ImportError, ModuleNotFoundError) as import_err:
                logger.info(f"[STREAM] StatuteRecommendationService not available: {import_err}")
                if multi_stage_result is not None:
                    multi_stage_result["verified_statutes"] = []
            except (TypeError, AttributeError) as conv_err:
                logger.warning(f"[STREAM] Conversion error getting verified statutes: {conv_err}", exc_info=True)
                if multi_stage_result is not None:
                    multi_stage_result["verified_statutes"] = []
            except Exception as e:
                logger.warning(f"[STREAM] Failed to get verified statutes from corpus: {e}", exc_info=True)
                if multi_stage_result is not None:
                    multi_stage_result["verified_statutes"] = []

        # Fetch documents for this case (they're in a separate table, not embedded in case_data)
        # Include extracted_text since it's used for summaries and quality assessment
        docs_response = (
            service_supabase.table("documents")
            .select("id, file_name, file_type, extracted_text, extraction_quality, status, metadata")
            .eq("case_id", case_id)
            .execute()
        )
        documents = docs_response.data if docs_response.data else []
        logger.info(f"[STREAM] Building summaries for {len(documents)} documents")

        # Filter out duplicate/excluded documents from summaries and quality report
        # These documents should not appear in Document Review or Quality Report tabs
        filtered_documents = []
        excluded_count = 0
        for doc in documents:
            doc_status = doc.get("status") or ""
            metadata = doc.get("metadata") or {}
            is_excluded = metadata.get("excluded", False)
            is_duplicate = doc_status == "duplicate" or metadata.get("is_duplicate", False)

            if is_excluded or is_duplicate:
                excluded_count += 1
                continue
            filtered_documents.append(doc)

        if excluded_count > 0:
            logger.info(f"[STREAM] Filtered out {excluded_count} duplicate/excluded documents")

        # Build document summaries from filtered documents as JSON array (frontend expects this format)
        doc_summaries_array = []
        quality_report = []

        for doc in filtered_documents:
            # Handle None values explicitly - dict.get() only uses default if key is missing, not if value is None
            extracted_text = doc.get("extracted_text") or ""
            extraction_quality = doc.get("extraction_quality") or "low"
            file_type = doc.get("file_type") or ""
            file_name = doc.get("file_name") or "Document"

            # Determine document type from metadata enrichment or file_type fallback
            metadata = doc.get("metadata") or {}
            enrichment = metadata.get("attorney_enrichment") or metadata.get("enrichment") or {}
            doc_type = enrichment.get("document_type_override") or enrichment.get("document_type")
            if not doc_type and file_type:
                doc_type = file_type.split("/")[-1].upper()
            doc_type = doc_type or "Unknown"

            # Build document summary for Document Review tab
            doc_summary = {
                "document_name": file_name,
                "document_type": doc_type,
                "extraction_quality": extraction_quality,
                "relevance_to_case": "Contains extracted text" if extracted_text else "No text extracted",
                "executive_summary": (extracted_text[:300] + "...") if len(extracted_text) > 300 else (extracted_text or "No summary available"),
                "key_content": extracted_text[:1000] if extracted_text else "No text extracted",
                "key_amounts": [],
            }
            doc_summaries_array.append(doc_summary)

            # Build quality report entry for Quality Report tab
            quality_issues = []
            if not extracted_text:
                quality_issues.append("No text could be extracted from this document")
            elif len(extracted_text) < 100:
                quality_issues.append("Very little text extracted - document may be an image or scan")
            if file_type.startswith("image/"):
                quality_issues.append("Image file - text extraction may be limited")

            quality_report.append({
                "document": file_name,
                "document_id": doc.get("id") or "",
                "score": 8 if extraction_quality == "high" else 6 if extraction_quality == "medium" else 3,
                "confidence_level": extraction_quality,
                "issues": quality_issues,
            })

        # Extract opposing parties from structured data for demand letter dropdown
        opposing_parties = []
        if structured_data and structured_data.get("parties"):
            for party_data in structured_data["parties"]:
                role = (party_data.get("role") or "").lower()
                name = party_data.get("name") or ""

                # Identify opposing parties (not client or attorney)
                # Common opposing party roles include: landlord, contractor, seller, defendant, respondent
                is_opposing = (
                    "opposing" in role or
                    "defendant" in role or
                    "respondent" in role or
                    "landlord" in role or
                    "contractor" in role or
                    "seller" in role or
                    "hoa" in role or
                    "association" in role or
                    "company" in role or
                    "employer" in role or
                    (role and "client" not in role and "plaintiff" not in role and
                     "claimant" not in role and "attorney" not in role and "counsel" not in role)
                )

                if is_opposing and name:
                    opposing_parties.append({
                        "name": name,
                        "role": party_data.get("role", "Party"),
                        "entity_type": party_data.get("entity_type", "unknown"),
                        "is_opposing_party": True,
                    })

        logger.info(f"[STREAM] Identified {len(opposing_parties)} opposing parties for demand letter dropdown")

        # Build the complete result - must match ProcessingResult structure
        streaming_result = {
            # Required fields for ProcessingResult compatibility
            "main_letter": "",  # Letters are generated separately via letter generation endpoint
            "document_summaries": json.dumps(doc_summaries_array),  # Frontend expects JSON array
            "case_analysis": json.dumps(case_analysis),
            "quality_report": quality_report,  # For Quality Report tab

            # Streaming-specific fields
            "streaming_analysis": request.content,
            "multi_stage_result": multi_stage_result,
            "opposing_parties": opposing_parties,  # For demand letter party dropdown
            "artifacts": {
                "analysis_type": "streaming",
                "jurisdiction": case_data.get("jurisdiction", "Florida"),
                "structured_data": structured_data,
            },
            "status": "completed",
        }

        # Apply recursive conversion to catch any nested StatuteRecommendation objects
        logger.debug("[STREAM] Applying recursive conversion to streaming_result")
        streaming_result = _convert_statute_recommendations_recursive(streaming_result)

        # Explicit JSON serialization test before database save
        # This catches any serialization errors early with detailed error messages
        try:
            test_json = json.dumps(streaming_result)
            logger.debug(f"[STREAM] JSON serialization test passed ({len(test_json)} bytes)")
        except TypeError as json_err:
            # Find the problematic field
            error_msg = str(json_err)
            logger.error(f"[STREAM] JSON serialization test FAILED: {error_msg}")

            # Try to identify the problematic field by testing each top-level key
            problematic_fields = []
            for key, value in streaming_result.items():
                try:
                    json.dumps(value)
                except TypeError as field_err:
                    problematic_fields.append(f"{key}: {field_err}")
                    logger.error(f"[STREAM] Field '{key}' is not JSON serializable: {field_err}")

            # Apply recursive conversion one more time as a last resort
            logger.warning("[STREAM] Applying recursive conversion again to fix serialization issues")
            streaming_result = _convert_statute_recommendations_recursive(streaming_result)

            # Test again
            try:
                test_json = json.dumps(streaming_result)
                logger.info("[STREAM] JSON serialization test passed after recursive conversion")
            except TypeError as retry_err:
                # Log structure keys for debugging (not full content)
                result_keys = list(streaming_result.keys())
                logger.error(
                    f"[STREAM] JSON serialization still failing after recursive conversion. "
                    f"Error: {retry_err}. Result keys: {result_keys}. "
                    f"Problematic fields: {problematic_fields}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to serialize analysis result: {retry_err}. Problematic fields: {problematic_fields}"
                )

        # Create or update analysis result
        # Note: Gap analysis is now handled on-demand via POST /analyze-gaps endpoint
        analysis_id = str(uuid.uuid4())  # Generate proper UUID for database

        try:
            # Check if case exists before saving (prevents race condition in Clio import)
            # Retry up to 3 times with 2 second delays to allow case creation to complete
            import time
            case_exists = False
            for retry in range(3):
                case_check = service_supabase.table("cases").select("id").eq("id", case_id).limit(1).execute()
                if case_check.data:
                    case_exists = True
                    break

                if retry < 2:  # Don't wait on last attempt
                    logger.warning(f"[STREAM] Case {case_id} not found, retry {retry + 1}/3 in 2s...")
                    time.sleep(2)

            if not case_exists:
                logger.error(f"[STREAM] Case {case_id} still not found after 3 retries")
                raise HTTPException(
                    status_code=404,
                    detail=f"Case {case_id} not found in database. Please ensure the case was created before starting analysis."
                )

            logger.info(f"[STREAM] Case {case_id} confirmed, saving analysis results...")
            _upsert_with_retry(
                service_supabase, "analysis_results",
                {
                    "id": analysis_id,
                    "case_id": case_id,
                    "status": "completed",
                    "result": streaming_result,
                    "created_at": datetime.utcnow().isoformat(),
                },
                case_id,
            )
        except HTTPException:
            raise
        except Exception as db_err:
            # If database save fails, log detailed error
            error_detail = str(db_err)
            logger.error(
                f"[STREAM] Database save failed for case {case_id}: {error_detail}. "
                f"Result keys: {list(streaming_result.keys())}"
            )
            # Check if it's a serialization error
            if "not JSON serializable" in error_detail or "TypeError" in error_detail:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to save analysis result due to serialization error: {error_detail}"
                )
            raise

        # Update case status - must use valid status from constraint: pending, processing, completed, error, cancelled
        _update_case_with_retry(
            supabase, case_id,
            {"status": "completed", "updated_at": datetime.utcnow().isoformat()},
        )

        logger.info(f"[STREAM] Saved streaming analysis for case {case_id} | structured_data={'yes' if structured_data else 'no'}")

        return {"success": True, "analysis_id": analysis_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving streaming analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _convert_statute_recommendations_recursive(obj: Any) -> Any:
    """Recursively convert any StatuteRecommendation dataclass objects to dicts.
    
    This function walks through the entire data structure (dicts, lists, nested structures)
    and converts any StatuteRecommendation instances to dictionaries for JSON serialization.
    
    Args:
        obj: The object to scan and convert (can be dict, list, or any other type)
    
    Returns:
        The same structure with all StatuteRecommendation objects converted to dicts

    """
    from dataclasses import asdict

    from legal_portal.services.statute_recommendation_service import StatuteRecommendation

    # If it's a StatuteRecommendation instance, convert it
    if isinstance(obj, StatuteRecommendation):
        return asdict(obj)

    # If it's a dict, recursively process values
    if isinstance(obj, dict):
        return {key: _convert_statute_recommendations_recursive(value) for key, value in obj.items()}

    # If it's a list, recursively process items
    if isinstance(obj, list):
        return [_convert_statute_recommendations_recursive(item) for item in obj]

    # If it's a tuple, convert to list, process, and convert back (or keep as list)
    if isinstance(obj, tuple):
        return tuple(_convert_statute_recommendations_recursive(item) for item in obj)

    # For any other type, return as-is
    return obj


def _parse_currency(value) -> float:
    """Parse currency string like '$1,234.56' to float.
    
    Handles various formats:
    - "$1,234.56" -> 1234.56
    - "1234.56" -> 1234.56
    - 1234.56 -> 1234.56
    - None -> 0.0
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove $, commas, and whitespace
        cleaned = value.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
    return 0.0


def _extract_embedded_json(content: str) -> dict:
    """Extract the structured JSON block from streaming analysis markdown.
    
    The JSON is embedded in a ```json code fence at the end of the markdown.
    """
    import re

    # Look for JSON code block
    json_pattern = r"```json\s*\n(.*?)\n```"
    match = re.search(json_pattern, content, re.DOTALL)

    if not match:
        logger.warning("[STREAM] No embedded JSON found in streaming analysis")
        return {}

    try:
        json_str = match.group(1).strip()
        structured_data = json.loads(json_str)
        logger.info(f"[STREAM] Extracted structured data: {list(structured_data.keys())}")
        return structured_data
    except json.JSONDecodeError as e:
        logger.error(f"[STREAM] Failed to parse embedded JSON: {e}")
        return {}


def _extract_section(content: str, section_name: str) -> str:
    """Extract a section from markdown content."""
    import re
    pattern = rf"## {section_name}\n(.*?)(?=\n## |$)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _extract_list_items(content: str, section_name: str) -> List[str]:
    """Extract list items from a section."""
    import re
    section = _extract_section(content, section_name)
    if not section:
        return []
    # Find bullet points or numbered items
    items = re.findall(r"[-*•]\s*(.+?)(?=\n[-*•]|\n\n|$)", section, re.MULTILINE)
    return [item.strip() for item in items if item.strip()]


@router.get("/stream/{case_id}")
async def stream_case_analysis(
    case_id: str,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Stream comprehensive case analysis in real-time.
    
    Uses GPT-4.1 to generate a complete analysis in a single streaming call.
    Output is markdown format that renders progressively in the frontend.
    
    This replaces the multi-stage analysis for faster, more reliable results.
    """
    from legal_portal.core.data_models import DocumentSummaryStructured
    from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer

    # Maximum characters of extracted_text to load per document.  Email
    # archives imported from Clio can contain 30+ MB of thread history — loading
    # them all in a single Supabase response causes an httpx ReadTimeout.  Only
    # the first MAX_DOC_CHARS are useful for LLM analysis anyway.
    MAX_DOC_CHARS = 200_000

    try:
        # 1. Verify case ownership — fetch case metadata and document stubs only.
        # extracted_text is intentionally excluded from the nested relation to
        # avoid a single HTTP response that could exceed 100+ MB for cases with
        # many large email documents.
        case_response = (
            supabase.table("cases")
            .select("*, documents(id,file_name,file_type,status,metadata)")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=404, detail="Case not found")

        case_data = case_response.data[0]
        doc_stubs = case_data.get("documents", [])

        if not doc_stubs:
            raise HTTPException(status_code=400, detail="No documents found for this case")

        # 1b. Fetch extracted_text for all documents in a single batch query.
        # Using .in_() avoids N+1 round trips (one per document) which was the
        # primary cause of connection count and CPU exhaustion on Supabase.
        doc_ids = [stub["id"] for stub in doc_stubs]
        text_by_id: dict = {}
        try:
            text_resp = (
                supabase.table("documents")
                .select("id, extracted_text")
                .in_("id", doc_ids)
                .execute()
            )
            for row in text_resp.data or []:
                raw = row.get("extracted_text") or ""
                text_by_id[row["id"]] = raw[:MAX_DOC_CHARS]
        except Exception as text_err:
            logger.warning(f"[STREAM] Could not batch-fetch extracted_text: {text_err}")

        documents = []
        for stub in doc_stubs:
            doc = dict(stub)
            doc["extracted_text"] = text_by_id.get(stub["id"], "")
            documents.append(doc)

        # 2. Build document summaries from extracted text
        doc_summaries = []
        intake_content = ""

        for doc in documents:
            extracted_text = doc.get("extracted_text", "") or ""
            file_name = doc.get("file_name", "unknown")
            
            # Derive doc_type from metadata or file_type since it's not a DB column
            metadata = doc.get("metadata") or {}
            doc_type = (
                metadata.get("classification")
                or metadata.get("attorney_enrichment", {}).get("document_type_override")
                or doc.get("file_type", "document")
            )

            if extracted_text:
                # Find intake form
                if "intake" in file_name.lower():
                    intake_content = extracted_text

                doc_summaries.append(DocumentSummaryStructured(
                    document_name=file_name,
                    document_type=doc_type,
                    executive_summary=extracted_text[:500],
                    key_content=extracted_text[:3000],
                ))

        if not intake_content and doc_summaries:
            # Use first document if no intake found
            intake_content = doc_summaries[0].key_content or ""

        # 3. Determine jurisdiction
        jurisdiction = case_data.get("jurisdiction", "Florida")

        logger.info(
            f"[STREAM] Starting streaming analysis for case {case_id} | "
            f"docs={len(doc_summaries)} jurisdiction={jurisdiction}"
        )

        # 4. Stream the analysis with thinking heartbeats
        async def generate():
            try:
                openai_client = OpenAIClient()
                analyzer = MultiStageAnalyzer(openai_client=openai_client)

                full_content = ""
                first_token_received = False
                start_time = time.time()
                last_heartbeat = start_time

                # Signal that we're starting (thinking phase begins)
                yield f"data: {json.dumps({'phase': 'thinking', 'elapsed': 0})}\n\n"

                # Create the token generator (now returns tuple)
                token_generator, ctx_result = await analyzer.analyze_streaming(
                    intake_content=intake_content,
                    document_summaries=doc_summaries,
                    jurisdiction=jurisdiction,
                )
                _docs_in_scope = ctx_result.docs_in_scope
                _docs_omitted = ctx_result.docs_omitted

                # Use asyncio.Queue to handle tokens with heartbeat timeout
                token_queue: asyncio.Queue = asyncio.Queue()
                done_event = asyncio.Event()

                async def collect_tokens():
                    """Collect tokens and put them in queue."""
                    try:
                        async for token in token_generator:
                            await token_queue.put(('token', token))
                        await token_queue.put(('done', None))
                    except Exception as e:
                        await token_queue.put(('error', str(e)))

                # Start token collection in background
                collector_task = asyncio.create_task(collect_tokens())

                try:
                    while True:
                        try:
                            # Wait for token with 5-second timeout for heartbeat
                            msg_type, msg_data = await asyncio.wait_for(
                                token_queue.get(),
                                timeout=5.0
                            )

                            if msg_type == 'token':
                                if not first_token_received:
                                    first_token_received = True
                                    elapsed = int(time.time() - start_time)
                                    logger.info(f"[STREAM] First token received after {elapsed}s thinking")
                                    # Signal transition from thinking to streaming
                                    yield f"data: {json.dumps({'phase': 'streaming', 'thinking_time': elapsed})}\n\n"

                                full_content += msg_data
                                yield f"data: {json.dumps({'token': msg_data})}\n\n"

                            elif msg_type == 'done':
                                # Signal completion — include scope counts for UI warning
                                yield f"data: {json.dumps({'done': True, 'content': full_content, 'docs_in_scope': ctx_result.docs_in_scope, 'docs_omitted': ctx_result.docs_omitted, 'context_tokens': ctx_result.total_tokens, 'omission_reason': ctx_result.omission_reason, 'omitted_doc_names': ctx_result.omitted_doc_names[:10]})}\n\n"
                                logger.info(
                                    f"[STREAM] Completed streaming for case {case_id} | "
                                    f"docs_in_scope={_docs_in_scope} docs_omitted={_docs_omitted}"
                                )

                                # Auto-save raw content for recovery if frontend loses connection
                                try:
                                    analysis_id = str(uuid.uuid4())
                                    service_supabase.table("analysis_results").insert({
                                        "id": analysis_id,
                                        "case_id": case_id,
                                        "status": "streaming_complete",
                                        "result": {
                                            "raw_streaming_content": full_content,
                                            "docs_in_scope": ctx_result.docs_in_scope,
                                            "docs_omitted": ctx_result.docs_omitted,
                                            "context_tokens": ctx_result.total_tokens,
                                            "omission_reason": ctx_result.omission_reason,
                                            "jurisdiction": jurisdiction,
                                            "streaming_completed_at": datetime.utcnow().isoformat(),
                                        },
                                        "created_at": datetime.utcnow().isoformat(),
                                    }).execute()
                                    logger.info(f"[STREAM] Auto-saved streaming result for case {case_id}")
                                except Exception as save_err:
                                    logger.error(f"[STREAM] Auto-save failed for case {case_id}: {save_err}")

                                break

                            elif msg_type == 'error':
                                yield f"data: {json.dumps({'error': msg_data})}\n\n"
                                break

                        except asyncio.TimeoutError:
                            # No token received in 5 seconds - send heartbeat
                            elapsed = int(time.time() - start_time)

                            if not first_token_received:
                                # Still in thinking phase - send thinking heartbeat
                                yield f"data: {json.dumps({'phase': 'thinking', 'elapsed': elapsed})}\n\n"
                                logger.debug(f"[STREAM] Thinking heartbeat: {elapsed}s")
                            else:
                                # In streaming phase but slow - send streaming heartbeat
                                yield f"data: {json.dumps({'heartbeat': elapsed})}\n\n"

                finally:
                    # Ensure collector task is cleaned up
                    if not collector_task.done():
                        collector_task.cancel()
                        try:
                            await collector_task
                        except asyncio.CancelledError:
                            pass

            except Exception as e:
                logger.error(f"[STREAM] Error during streaming: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable Vercel/nginx buffering
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in stream_case_analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream/{case_id}/result")
async def get_streaming_result(
    case_id: str,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Check if a streaming analysis has completed for this case (recovery endpoint)."""
    response = supabase.table("analysis_results") \
        .select("id, status, result, created_at") \
        .eq("case_id", case_id) \
        .in_("status", ["streaming_complete", "completed"]) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if response.data:
        row = response.data[0]
        result = row.get("result", {})
        content = result.get("raw_streaming_content") or result.get("streaming_analysis_content", "")
        if content:
            return {
                "found": True,
                "content": content,
                "docs_in_scope": result.get("docs_in_scope", 0),
                "docs_omitted": result.get("docs_omitted", 0),
                "analysis_id": row["id"],
            }

    return {"found": False}
