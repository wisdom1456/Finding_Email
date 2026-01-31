"""Document analysis endpoints."""

import asyncio
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
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator

import html2text
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.rate_limiter import limiter
from legal_portal.core.data_models import (
    ChatMessageRequest,
    ChatMessageResponse,
    DocumentStatus,
    DocumentType,
    LetterType,
    ProcessedDocument,
    ProcessingResult,
    SkippedDocument,
)
from legal_portal.services.case_chat_service import CaseChatService
from legal_portal.services.demand_letter_service import DemandLetterService
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.main_processor import process_case_documents
from legal_portal.services.progress_manager import ProgressManager
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.diagnostic_logger import DiagnosticLogger
from legal_portal.utils.security import sanitize_text_for_db

router = APIRouter()
logger = logging.getLogger(__name__)

# Cache for database column existence checks
_DB_COLUMNS_CACHE = {}


class AnalysisCancelledError(Exception):
    """Raised when an in-progress analysis is cancelled by the user."""


def _analysis_is_cancelled(supabase, analysis_id: str) -> bool:
    """Check whether an analysis has been cancelled.

    We treat either status='cancelled' or status='canceled' as cancelled.
    """
    try:
        resp = supabase.table("analysis_results").select("status").eq("id", analysis_id).limit(1).execute()
        if not resp.data:
            return False
        status_val = (resp.data[0].get("status") or "").lower()
        return status_val in {"cancelled", "canceled"}
    except Exception:
        # Never break processing due to a cancellation check failure
        return False


async def _cancel_analysis(
    *,
    supabase,
    case_id: str,
    analysis_id: str,
    progress_manager: Optional[ProgressManager] = None,
):
    """Cancel an analysis by updating DB state and emitting progress."""
    # Mark analysis as cancelled
    supabase.table("analysis_results").update({"status": "cancelled"}).eq("id", analysis_id).execute()

    # Un-stick the case so a new analysis can be started
    # (we keep the case and documents; user can retry later)
    supabase.table("cases").update({"status": "pending"}).eq("id", case_id).execute()

    # Best-effort progress update so UI can stop spinning
    payload = {
        "message": "Analysis cancelled by user.",
        "phase": "cancelled",
        "percent": 0,
        "status": "cancelled",
        "timestamp": datetime.utcnow().isoformat(),
    }
    if progress_manager is not None:
        try:
            await progress_manager.publish_progress(channel_id=analysis_id, **payload)
        except Exception:
            pass
    await _update_analysis_progress(supabase, analysis_id, payload)


async def _update_analysis_progress(supabase, analysis_id: str, payload: dict):
    """Update analysis progress in DB with safety check for column existence."""
    global _DB_COLUMNS_CACHE

    if _DB_COLUMNS_CACHE.get("has_progress_column") is False:
        return

    try:
        supabase.table("analysis_results").update({"progress": payload}).eq("id", analysis_id).execute()
        _DB_COLUMNS_CACHE["has_progress_column"] = True
    except Exception as e:
        if "column analysis_results.progress does not exist" in str(e):
            logger.warning("DB column analysis_results.progress missing. Disabling DB updates.")
            _DB_COLUMNS_CACHE["has_progress_column"] = False
        else:
            logger.warning(f"Failed to persist progress to DB: {e}")


async def _get_user_ai_preferences(user_id: str, supabase) -> Optional[Dict[str, str]]:
    """Fetch user's AI model preferences from profile."""
    try:
        response = supabase.table("profiles").select("ai_preferences").eq("id", user_id).single().execute()
        if response.data and response.data.get("ai_preferences"):
            return response.data["ai_preferences"]
    except Exception as e:
        logger.warning(f"Could not fetch user AI preferences: {e}")
    return None


# Optional WeasyPrint import for PDF generation
try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    WEASYPRINT_AVAILABLE = False
    HTML = None
    logger.warning(f"WeasyPrint not available: {e}. PDF generation will be disabled.")

ARTIFACT_BUCKET = os.getenv("SUPABASE_ARTIFACT_BUCKET", "documents")
ARTIFACT_PREFIX = os.getenv("ANALYSIS_ARTIFACT_PREFIX", "analysis_artifacts")
SIGNED_URL_TTL = int(os.getenv("ANALYSIS_ARTIFACT_URL_TTL", "3600"))

_HTML2TEXT_CONVERTER = html2text.HTML2Text()
_HTML2TEXT_CONVERTER.ignore_links = False
_HTML2TEXT_CONVERTER.body_width = 0


def _html_to_pdf_bytes(html: Optional[str]) -> Optional[bytes]:
    """Render HTML content to PDF bytes using WeasyPrint."""
    if not html:
        return None
    if not WEASYPRINT_AVAILABLE:
        logger.warning("WeasyPrint not available, PDF generation skipped")
        return None
    try:
        return HTML(string=html, base_url=os.getcwd()).write_pdf()
    except Exception as exc:
        logger.warning(f"Failed to render PDF artifact: {exc}")
        return None


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
    """Create PDF/EML/appendix/citation map artifacts and store them in Supabase."""
    artifacts: Dict[str, Dict[str, Any]] = {}
    prefix = f"{ARTIFACT_PREFIX}/{case_id}/{analysis_id}"
    storage = supabase_client.storage.from_(ARTIFACT_BUCKET)

    pdf_bytes = _html_to_pdf_bytes(result.main_letter)
    if pdf_bytes:
        metadata = _store_artifact(storage, f"{prefix}/findings-email.pdf", pdf_bytes, "application/pdf")
        if metadata:
            artifacts["letter_pdf"] = metadata

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


class AnalysisRequest(BaseModel):
    """Request model for starting case analysis."""

    case_id: str
    provider: Optional[str] = Field(default="openai", pattern="^(openai|anthropic)$")


class AnalysisResponse(BaseModel):
    """Response model for analysis status."""

    id: str
    case_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class LetterGenerationRequest(BaseModel):
    """Request payload for on-demand letter generation."""

    case_id: str
    letter_type: LetterType = LetterType.FINDINGS
    target_party_name: Optional[str] = None
    demand_amount: Optional[float] = None
    demand_deadline: str = "10 business days"
    specific_demands: List[str] = Field(default_factory=list)
    attorney_name: Optional[str] = None
    firm_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    client_name: Optional[str] = None


class LetterGenerationResponse(BaseModel):
    """Response payload for generated letters."""

    letter_html: str
    letter_type: LetterType
    target_party_name: Optional[str] = None


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
    # #region agent log
    _DEBUG_LOG_PATH = "/tmp/cursor_debug.log" if __import__('os').getenv("VERCEL") else "/Users/BRFlorida/Projects/Work/Finding_Emails/.cursor/debug.log"
    def _dbg_log(hyp: str, msg: str, data: dict = None):
        try:
            import json as _j, time as _t; open(_DEBUG_LOG_PATH, "a").write(_j.dumps({"hypothesisId": hyp, "location": "analysis.py:process_case_background", "message": msg, "data": data or {}, "timestamp": _t.time(), "sessionId": "debug-session"}) + "\n")
        except: pass
    _dbg_log("H2", "BACKGROUND TASK STARTED", {"case_id": case_id, "analysis_id": analysis_id, "provider": provider})
    # #endregion agent log

    bg_start_time = time.time()
    
    logger.info(
        f"[BACKGROUND:START] [CASE:{case_id}] [ANALYSIS:{analysis_id}] "
        f"Background task started | provider={provider}"
    )
    
    # Initialize progress manager
    progress_manager = ProgressManager.get_instance()
    await progress_manager.create_channel(analysis_id)
    
    # #region agent log
    _dbg_log("H2,H4", "Channel created, publishing first progress", {"analysis_id": analysis_id})
    # #endregion agent log

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

        # Get all documents for the case
        docs_response = supabase.table("documents").select("*").eq("case_id", case_id).execute()
        documents = docs_response.data

        if not documents:
            raise ValueError("No documents found for case")

        elapsed = time.time() - bg_start_time
        logger.info(
            f"[BACKGROUND:PREP] [CASE:{case_id}] [ELAPSED:{elapsed:.1f}s] "
            f"Preparing documents | total_docs={len(documents)} jurisdiction={jurisdiction}"
        )

        # Step 1: Prepare ProcessedDocument objects directly from DB (no re-extraction)
        from legal_portal.core.data_models import FileMetadata, FileType

        processed_intake = []
        processed_case_docs = []
        skipped_documents = []

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

            # Get text from manual_text (priority) or extracted_text
            text = doc.get("manual_text") or doc.get("extracted_text")
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

            pdoc = ProcessedDocument(
                file_name=doc["file_name"],
                content=text,
                document_type=(
                    DocumentType.INTAKE_FORM
                    if doc.get("metadata", {}).get("is_intake_form")
                    else DocumentType.CASE_DOCUMENT
                ),
                file_type=FileType.PDF,
                metadata=metadata,
                extraction_quality=doc.get("extraction_quality", "high"),
                extraction_method=doc.get("extraction_method", "db"),
                page_count=doc.get("page_count"),
                ocr_provider=doc.get("ocr_provider"),
                document_id=doc["id"],
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

        # Prepare case_info
        case_info = {
            "client_name": case["client_name"],
            "reference_number": case.get("reference_number", ""),
            "description": case.get("description", ""),
            "case_id": case_id,
            "jurisdiction": jurisdiction,  # Include jurisdiction in case_info
        }

        # Prepare review_data (simplified - can be enhanced via UI later)
        review_data = {
            "legal_issue": case.get("description", "General legal document analysis"),
        }

        # Track timing and stats for the AI Command Center
        analysis_start_time = time.time()
        total_tokens_used = 0

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
                "model": "gpt-5.2",
            }

            # Cooperative cancellation
            if _analysis_is_cancelled(supabase, analysis_id):
                raise AnalysisCancelledError("Analysis cancelled by user.")

            # Publish
            await progress_manager.publish_progress(channel_id=analysis_id, **payload)
            await _update_analysis_progress(supabase, analysis_id, payload)

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
            for doc in result.processed_documents:
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

        # Convert result to dict for storage (with mode='json' to serialize datetime)
        result_dict = result.model_dump(mode="json")

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

        # #region agent log
        _DEBUG_LOG_PATH = "/tmp/cursor_debug.log" if __import__('os').getenv("VERCEL") else "/Users/BRFlorida/Projects/Work/Finding_Emails/.cursor/debug.log"
        def _dbg_log(hyp: str, msg: str, data: dict = None):
            try:
                import json as _j, time as _t; open(_DEBUG_LOG_PATH, "a").write(_j.dumps({"hypothesisId": hyp, "location": "analysis.py:process_case_background:except", "message": msg, "data": data or {}, "timestamp": _t.time(), "sessionId": "debug-session"}) + "\n")
            except: pass
        _dbg_log("H3", "BACKGROUND TASK EXCEPTION", {"case_id": case_id, "analysis_id": analysis_id, "error": error_message, "error_type": type(e).__name__, "elapsed": elapsed})
        # #endregion agent log

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


@router.get("/{analysis_id}/letter/stream")
async def stream_findings_letter(
    analysis_id: str,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Stream findings email generation token by token."""
    # Verify ownership and get analysis results
    try:
        response = supabase.table("analysis_results").select("*").eq("id", analysis_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        analysis_data = response.data[0]
        result_payload = analysis_data.get("result")
        if not result_payload:
            raise HTTPException(status_code=400, detail="Analysis result not yet available")
            
        processing_result = ProcessingResult(**result_payload)
        if not processing_result.multi_stage_result:
            raise HTTPException(status_code=400, detail="Multi-stage analysis results missing")

        async def generate():
            openai_client = OpenAIClient()
            json_service = JsonProcessingService(client=openai_client, config={})
            
            msr = processing_result.multi_stage_result
            from legal_portal.core.data_models import DeepAnalysis, FactMatrix, LetterStructure
            
            fact_matrix = FactMatrix(**msr["fact_matrix"])
            deep_analysis = DeepAnalysis(**msr["deep_analysis"])
            letter_structure = LetterStructure(**msr["letter_structure"])
            
            artifacts = processing_result.artifacts or {}
            jurisdiction = artifacts.get("jurisdiction", "Florida")
            
            async for token in json_service.stream_findings_letter_adaptive(
                intake_content=processing_result.intake_content or "",
                fact_matrix=fact_matrix,
                legal_analysis=deep_analysis,
                structure_guidance=letter_structure,
                verified_statutes=msr.get("verified_statutes", []),
                attorney_name=artifacts.get("attorney_name"),
                firm_name=artifacts.get("firm_name"),
                contact_phone=artifacts.get("contact_phone"),
                contact_email=artifacts.get("contact_email"),
                jurisdiction=jurisdiction,
            ):
                yield f"data: {json.dumps({'token': token})}\n\n"
            
            yield f"data: {json.dumps({'done': True})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    except Exception as e:
        logger.error(f"Error in stream_findings_letter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{analysis_id}/chat/stream")
async def stream_chat_response(
    analysis_id: str,
    request: ChatMessageRequest,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
):
    """Stream chat response token by token."""
    try:
        # 1. Get analysis context
        response = supabase.table("analysis_results").select("*").eq("id", analysis_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Analysis result not found")
        
        analysis_data = response.data[0]
        result_payload = analysis_data["result"]
        processing_result = ProcessingResult(**result_payload)
        
        # 2. Get conversation history (use case_id from the analysis record, not ProcessingResult)
        case_id = analysis_data["case_id"]
        history_response = (
            supabase.table("case_chat_messages")
            .select("user_message, ai_response")
            .eq("case_id", case_id)
            .order("created_at", desc=False)
            .limit(10)
            .execute()
        )
        conversation_history = []
        if history_response.data:
            for row in history_response.data:
                conversation_history.append({"role": "user", "content": row["user_message"]})
                conversation_history.append({"role": "assistant", "content": row["ai_response"]})

        async def generate():
            openai_client = OpenAIClient()
            artifacts = processing_result.artifacts or {}
            jurisdiction = artifacts.get("jurisdiction", "Florida")
            chat_service = CaseChatService(openai_client, jurisdiction=jurisdiction)
            
            full_response = ""
            async for token in chat_service.stream_message(
                user_message=request.message,
                analysis_result=processing_result,
                conversation_history=conversation_history,
            ):
                full_response += token
                yield f"data: {json.dumps({'token': token})}\n\n"
            
            # 3. Save to database after streaming completes
            try:
                supabase.table("case_chat_messages").insert(
                    {
                        "case_id": case_id,
                        "user_message": request.message,
                        "ai_response": full_response,
                        "context_used": processing_result.multi_stage_result or {},
                    }
                ).execute()
            except Exception as db_err:
                logger.error(f"Failed to save chat message to DB: {db_err}")
                
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    except Exception as e:
        logger.error(f"Error in stream_chat_response: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    
    # #region agent log
    _DEBUG_LOG_PATH = "/tmp/cursor_debug.log" if is_vercel else "/Users/BRFlorida/Projects/Work/Finding_Emails/.cursor/debug.log"
    def _dbg_log(hyp: str, msg: str, data: dict = None):
        try:
            import json as _j, time as _t; open(_DEBUG_LOG_PATH, "a").write(_j.dumps({"hypothesisId": hyp, "location": "analysis.py:start_analysis", "message": msg, "data": data or {}, "timestamp": _t.time(), "sessionId": "debug-session"}) + "\n")
        except: pass
    # #endregion agent log
    
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

        _dbg_log("H6", "start_analysis called", {"case_id": analysis_request.case_id, "analysis_id": analysis["id"], "is_vercel": is_vercel})

        if is_vercel:
            # On Vercel: Return SSE stream that runs analysis inline
            # This keeps the connection alive and prevents function termination
            logger.info(f"[VERCEL] Starting SSE stream for analysis {analysis['id']}")
            _dbg_log("H6", "Starting SSE stream analysis on Vercel", {"analysis_id": analysis["id"]})
            
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
    service_supabase=Depends(get_supabase_client),  # noqa: B008
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
            supabase=service_supabase,
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
    service_supabase=Depends(get_supabase_client),  # noqa: B008
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
            supabase=service_supabase,
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No analysis found for this case"
            )

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
        docs_response = (
            service_supabase.table("documents")
            .select("*")
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
            doc_quality = doc.get("quality_score") or 0
            file_type = doc.get("file_type") or ""
            file_name = doc.get("file_name") or "Document"
            
            # Determine extraction quality based on text length and quality score
            if doc_quality >= 8 or len(extracted_text) > 500:
                extraction_quality = "high"
            elif doc_quality >= 5 or len(extracted_text) > 100:
                extraction_quality = "medium"
            else:
                extraction_quality = "low"
            
            # Determine document type
            doc_type = doc.get("document_type")
            if not doc_type and file_type:
                doc_type = file_type.split("/")[-1].upper()
            doc_type = doc_type or "Unknown"
            
            # Build document summary for Document Review tab
            doc_summary = {
                "document_name": file_name,
                "document_type": doc_type,
                "extraction_quality": extraction_quality,
                "relevance_to_case": bool(extracted_text),
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
                "score": doc_quality if doc_quality > 0 else (8 if extraction_quality == "high" else 6 if extraction_quality == "medium" else 3),
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

        # ============================================================================
        # ADD GAP ANALYSIS TO MULTI_STAGE_RESULT (NEW - 2026-01-31)
        # ============================================================================
        if multi_stage_result:
            try:
                logger.info("[STREAM] Running gap analysis on streaming result...")

                # Import gap analysis service
                from legal_portal.services.gap_analysis_service import GapAnalysisService
                from legal_portal.utils.openai_client import OpenAIClient
                from legal_portal.core.data_models import FactMatrix, LegalIssueMap, DeepAnalysis, DocumentSummaryStructured

                # Create OpenAI client and gap service
                openai_client = OpenAIClient()
                gap_service = GapAnalysisService(openai_client=openai_client)

                # Convert multi_stage_result dicts to Pydantic models for gap analysis
                fact_matrix = FactMatrix(**multi_stage_result.get("fact_matrix", {}))
                issue_map = LegalIssueMap(**multi_stage_result.get("issue_map", {}))
                deep_analysis_data = multi_stage_result.get("deep_analysis", {})

                # Deep analysis needs special handling for nested models
                deep_analysis = DeepAnalysis(**deep_analysis_data) if deep_analysis_data else None

                # Convert document summaries
                doc_summaries_list = []
                for doc_sum in doc_summaries_array:
                    try:
                        doc_summaries_list.append(DocumentSummaryStructured(**doc_sum))
                    except Exception as doc_err:
                        logger.warning(f"[STREAM] Could not convert doc summary: {doc_err}")

                # Run gap analysis
                if deep_analysis:
                    import asyncio
                    gap_result = await asyncio.to_thread(
                        lambda: asyncio.run(gap_service.analyze_gaps(
                            fact_matrix=fact_matrix,
                            issue_map=issue_map,
                            deep_analysis=deep_analysis,
                            document_summaries=doc_summaries_list,
                            intake_content=request.content[:5000],  # Use analysis content as proxy for intake
                        ))
                    )

                    # Add to multi_stage_result
                    multi_stage_result["gap_analysis"] = gap_result.model_dump(mode="json")
                    logger.info(f"[STREAM] Gap analysis complete: {gap_result.total_gaps} gaps found")
                else:
                    logger.warning("[STREAM] No deep_analysis found, skipping gap analysis")

            except Exception as gap_err:
                logger.error(f"[STREAM] Gap analysis failed: {gap_err}", exc_info=True)
                # Continue without gap analysis - don't fail the whole save
                multi_stage_result["gap_analysis"] = None

        # Create or update analysis result
        analysis_id = str(uuid.uuid4())  # Generate proper UUID for database
        
        try:
            service_supabase.table("analysis_results").upsert({
                "id": analysis_id,
                "case_id": case_id,
                "status": "completed",
                "result": streaming_result,
                "created_at": datetime.utcnow().isoformat(),
            }).execute()
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
        supabase.table("cases").update({
            "status": "completed",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", case_id).execute()
        
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
    from legal_portal.services.statute_recommendation_service import StatuteRecommendation
    from dataclasses import asdict
    
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
):
    """Stream comprehensive case analysis in real-time.
    
    Uses GPT-4.1 to generate a complete analysis in a single streaming call.
    Output is markdown format that renders progressively in the frontend.
    
    This replaces the multi-stage analysis for faster, more reliable results.
    """
    from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer
    from legal_portal.core.data_models import DocumentSummaryStructured
    
    try:
        # 1. Verify case ownership
        case_response = (
            supabase.table("cases")
            .select("*, documents(*)")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )
        
        if not case_response.data:
            raise HTTPException(status_code=404, detail="Case not found")
        
        case_data = case_response.data[0]
        documents = case_data.get("documents", [])
        
        if not documents:
            raise HTTPException(status_code=400, detail="No documents found for this case")
        
        # 2. Build document summaries from extracted text
        doc_summaries = []
        intake_content = ""
        
        for doc in documents:
            extracted_text = doc.get("extracted_text", "") or ""
            file_name = doc.get("file_name", "unknown")
            doc_type = doc.get("doc_type", "document")
            
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
                
                # Create the token generator
                token_generator = analyzer.analyze_streaming(
                    intake_content=intake_content,
                    document_summaries=doc_summaries,
                    jurisdiction=jurisdiction,
                )
                
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
                                # Signal completion
                                yield f"data: {json.dumps({'done': True, 'content': full_content})}\n\n"
                                logger.info(f"[STREAM] Completed streaming for case {case_id}")
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


@router.post("/generate-letter", response_model=LetterGenerationResponse)
@limiter.limit("10/minute")  # Rate limit letter generation
async def generate_letter(
    letter_request: LetterGenerationRequest,
    request: Request,  # Required for rate limiter (must be named 'request')
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Generate findings or demand letters on-demand."""
    _ensure_case_access(supabase, letter_request.case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, letter_request.case_id)

    result_payload = analysis_record["result"]
    processing_result = ProcessingResult(**result_payload)

    if not processing_result.multi_stage_result:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="On-demand letters require the latest analysis. Please re-run the case analysis.",
        )

    # Fetch user's AI preferences
    ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
    openai_client = OpenAIClient(user_preferences=ai_preferences)
    artifacts = processing_result.artifacts or {}
    attorney_info = {
        "name": letter_request.attorney_name or artifacts.get("attorney_name"),
        "firm": letter_request.firm_name or artifacts.get("firm_name"),
        "phone": letter_request.contact_phone or artifacts.get("contact_phone"),
        "email": letter_request.contact_email or artifacts.get("contact_email"),
    }

    msr = processing_result.multi_stage_result
    letter_html: str
    target_party_name: Optional[str] = None

    # Extract jurisdiction from artifacts
    jurisdiction = artifacts.get("jurisdiction", "Florida")
    logger.info(f"Generating {letter_request.letter_type} letter for {jurisdiction}")

    # Initialize Diagnostic Logger if enabled
    diag_logger = None
    if DiagnosticLogger.get_enabled():
        diag_logger = DiagnosticLogger(session_id=letter_request.case_id)

    if letter_request.letter_type == LetterType.FINDINGS:
        from legal_portal.core.data_models import DeepAnalysis, FactMatrix, LetterStructure

        fact_matrix = FactMatrix(**msr["fact_matrix"])
        deep_analysis = DeepAnalysis(**msr["deep_analysis"])
        letter_structure = LetterStructure(**msr["letter_structure"])
        verified_statutes = msr.get("verified_statutes", [])

        json_service = JsonProcessingService(client=openai_client, config={})
        letter_html = await json_service.generate_findings_letter_adaptive(
            intake_content=processing_result.intake_content or "",
            fact_matrix=fact_matrix,
            legal_analysis=deep_analysis,
            structure_guidance=letter_structure,
            verified_statutes=verified_statutes,
            attorney_name=attorney_info["name"],
            firm_name=attorney_info["firm"],
            confirmed_qa_pairs=artifacts.get("confirmed_qa_pairs", []),
            contact_phone=attorney_info["phone"],
            contact_email=attorney_info["email"],
            quality_context=artifacts.get("quality_context", ""),
            clio_matter_context=artifacts.get("clio_matter_context", ""),
            jurisdiction=jurisdiction,  # Pass jurisdiction
            diag_logger=diag_logger,  # Pass diagnostic logger
            original_documents=msr.get("original_documents"), # NEW: Pass raw content
        )
        letter_key = "findings"
    else:
        if not letter_request.target_party_name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="target_party_name is required for demand letters",
            )

        # Extract client_name from letter_request, fact_matrix, or artifacts
        client_name = letter_request.client_name
        if not client_name:
            # Try to get from fact_matrix parties (find client role)
            fact_matrix_data = msr.get("fact_matrix", {})
            parties = fact_matrix_data.get("parties", [])
            for party in parties:
                if party.get("role", "").lower() in ["client", "plaintiff", "claimant"]:
                    client_name = party.get("name")
                    break

        # Fall back to artifacts or "Client"
        if not client_name:
            client_name = artifacts.get("client_name") or "Client"

        # Parse document_summaries from JSON string
        document_summaries = []
        if processing_result.document_summaries:
            try:
                import json

                document_summaries = json.loads(processing_result.document_summaries)
            except Exception as e:
                logger.warning(f"Failed to parse document_summaries: {e}")

        demand_service = DemandLetterService(openai_client)
        letter_html = await demand_service.generate_demand_letter(
            fact_matrix_dict=msr["fact_matrix"],
            deep_analysis_dict=msr["deep_analysis"],
            target_party_name=letter_request.target_party_name,
            demand_amount=letter_request.demand_amount,
            demand_deadline=letter_request.demand_deadline,
            specific_demands=letter_request.specific_demands,
            attorney_info=attorney_info,
            client_name=client_name,
            document_summaries=document_summaries,
            jurisdiction=jurisdiction,  # Pass jurisdiction
        )
        target_party_name = letter_request.target_party_name
        letter_key = f"demand_{letter_request.target_party_name.replace(' ', '_')}".lower()

    result_payload.setdefault("generated_letters", {})[letter_key] = letter_html
    supabase.table("analysis_results").update({"result": result_payload}).eq(
        "id", analysis_record["id"]
    ).execute()

    return LetterGenerationResponse(
        letter_html=letter_html,
        letter_type=letter_request.letter_type,
        target_party_name=target_party_name,
    )


class CalculateDemandAmountRequest(BaseModel):
    """Request to calculate demand amount."""

    case_id: str
    target_party_name: str


class CalculateDemandAmountResponse(BaseModel):
    """Response with calculated demand amount."""

    amount: float
    reasoning: str
    breakdown: List[Dict[str, Any]]


@router.post("/calculate-demand-amount", response_model=CalculateDemandAmountResponse)
async def calculate_demand_amount(
    request: CalculateDemandAmountRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Calculate suggested demand amount based on case analysis and selected party."""
    _ensure_case_access(supabase, request.case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, request.case_id)

    result_payload = analysis_record["result"]
    processing_result = ProcessingResult(**result_payload)

    if not processing_result.multi_stage_result:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Demand calculation requires the latest analysis. Please re-run the case analysis.",
        )

    # Fetch user's AI preferences
    ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
    openai_client = OpenAIClient(user_preferences=ai_preferences)

    msr = processing_result.multi_stage_result
    fact_matrix = msr.get("fact_matrix", {})
    deep_analysis = msr.get("deep_analysis", {})

    # Build context for AI calculation
    financial_data = fact_matrix.get("financial_data", [])
    parties = fact_matrix.get("parties", [])
    legal_issues = deep_analysis.get("issue_analyses", [])

    # Filter financial items related to the target party
    party_financial_items = []
    # general_financial_items = []

    for item in financial_data:
        description = item.get("description", "").lower()
        if request.target_party_name.lower() in description:
            party_financial_items.append(item)
        # else:
        #     general_financial_items.append(item)

    # Build AI prompt
    target_party = request.target_party_name
    prompt = f"""Analyze this case data and calculate a reasonable demand amount for: {target_party}

Financial Data:
{json.dumps(financial_data, indent=2)}

Parties Involved:
{json.dumps(parties, indent=2)}

Legal Issues:
{json.dumps(legal_issues, indent=2)}

Instructions:
1. Identify all amounts owed, damages claimed, or contract breaches related to {target_party}
2. Consider the strength of legal claims and potential recovery likelihood
3. Include reasonable attorney fees and costs if applicable
4. Provide a total demand amount that is justified by the evidence

Return a JSON object with:
- amount: float (total demand amount)
- reasoning: string (2-3 sentence explanation)
- breakdown: array of objects with {{description: string, amount: float}}

Be realistic and evidence-based. Only include amounts supported by the case data."""

    try:
        model = openai_client.get_preferred_model("demand_calculation", "gpt-5-mini")
        response = await asyncio.to_thread(
            openai_client.create_response,
            model=model,
            input=prompt,
            instructions="You are a legal analyst calculating demand amounts. Return only valid JSON.",
            reasoning_effort="low",
            verbosity="medium",
            max_output_tokens=1000,
        )

        result = json.loads(response["content"])

        return CalculateDemandAmountResponse(
            amount=result.get("amount", 0.0),
            reasoning=result.get("reasoning", "Unable to calculate demand amount."),
            breakdown=result.get("breakdown", []),
        )
    except Exception as e:
        logger.error(f"Error calculating demand amount: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate demand amount: {str(e)}",
        ) from e


@router.post("/chat", response_model=ChatMessageResponse)
async def case_chat(
    request: ChatMessageRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Chat about a case with the AI assistant."""
    if not request.case_id:
        raise HTTPException(status_code=400, detail="case_id is required for this endpoint")
    _ensure_case_access(supabase, request.case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, request.case_id)

    result_payload = analysis_record["result"]
    processing_result = ProcessingResult(**result_payload)

    if not processing_result.multi_stage_result:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Case chat requires the latest analysis. Please re-run the case analysis.",
        )

    history_response = (
        supabase.table("case_chat_messages")
        .select("user_message, ai_response")
        .eq("case_id", request.case_id)
        .order("created_at", desc=False)
        .limit(10)
        .execute()
    )

    conversation_history: List[Dict[str, str]] = []
    if history_response.data:
        for row in history_response.data:
            conversation_history.append({"role": "user", "content": row["user_message"]})
            conversation_history.append({"role": "assistant", "content": row["ai_response"]})

    # Fetch user's AI preferences
    ai_preferences = await _get_user_ai_preferences(user["id"], supabase)
    openai_client = OpenAIClient(user_preferences=ai_preferences)

    # Extract jurisdiction from artifacts
    artifacts = processing_result.artifacts or {}
    jurisdiction = artifacts.get("jurisdiction", "Florida")

    chat_service = CaseChatService(openai_client, jurisdiction=jurisdiction)
    ai_response = await chat_service.send_message(
        user_message=request.message,
        analysis_result=processing_result,
        conversation_history=conversation_history,
    )

    supabase.table("case_chat_messages").insert(
        {
            "case_id": request.case_id,
            "user_message": request.message,
            "ai_response": ai_response,
            "context_used": processing_result.multi_stage_result or {},
        }
    ).execute()

    return ChatMessageResponse(response=ai_response, context_used={})


# =============================================================================
# CHUNKED PROCESSING & RECOVERY ENDPOINTS
# =============================================================================


class RetryDocumentsRequest(BaseModel):
    """Request to retry failed documents."""
    document_ids: List[str] = Field(
        default=[],
        description="List of document IDs to retry, or empty to retry all failed"
    )


class SkipDocumentsRequest(BaseModel):
    """Request to skip failed documents and continue."""
    document_ids: List[str] = Field(
        default=[],
        description="List of document IDs to skip, or empty to skip all failed"
    )


class DocumentStatusResponse(BaseModel):
    """Response with document processing status."""
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    skipped: int
    documents: Dict[str, Any] = Field(default_factory=dict)
    can_proceed: bool = False


class RecoveryActionResponse(BaseModel):
    """Response after retry/skip action."""
    success: bool
    action: str
    affected_count: int
    message: str


@router.get("/{analysis_id}/documents", response_model=DocumentStatusResponse)
async def get_document_status(
    analysis_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Get detailed status of all documents in an analysis."""
    from legal_portal.services.chunk_state_manager import ChunkStateManager
    
    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, chunk_state"
    ).eq("id", analysis_id).single().execute()
    
    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    
    analysis = response.data
    case_id = analysis.get("case_id")
    
    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])
    
    chunk_state = analysis.get("chunk_state") or {}
    documents = chunk_state.get("documents", {})
    
    # Calculate summary
    statuses = [info.get("status", "pending") for info in documents.values()]
    
    summary = {
        "total": len(documents),
        "pending": statuses.count("pending"),
        "processing": statuses.count("processing"),
        "completed": statuses.count("completed"),
        "failed": statuses.count("failed"),
        "skipped": statuses.count("skipped"),
    }
    
    can_proceed = summary["pending"] == 0 and summary["processing"] == 0 and summary["failed"] == 0
    
    return DocumentStatusResponse(
        **summary,
        documents=documents,
        can_proceed=can_proceed
    )


@router.post("/{analysis_id}/retry", response_model=RecoveryActionResponse)
async def retry_failed_documents(
    analysis_id: str,
    request: RetryDocumentsRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """
    Retry processing of failed documents.
    
    If document_ids is empty, all failed documents will be retried.
    """
    from legal_portal.services.chunk_state_manager import ChunkStateManager
    
    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, chunk_state"
    ).eq("id", analysis_id).single().execute()
    
    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    
    analysis = response.data
    case_id = analysis.get("case_id")
    
    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])
    
    chunk_state_mgr = ChunkStateManager(supabase, analysis_id)
    
    # Get failed documents
    failed_docs = await chunk_state_mgr.get_failed_documents()
    
    if not failed_docs:
        return RecoveryActionResponse(
            success=True,
            action="retry",
            affected_count=0,
            message="No failed documents to retry"
        )
    
    # Determine which docs to retry
    if request.document_ids:
        doc_ids_to_retry = [d for d in request.document_ids if d in [f["id"] for f in failed_docs]]
    else:
        doc_ids_to_retry = [f["id"] for f in failed_docs]
    
    if not doc_ids_to_retry:
        return RecoveryActionResponse(
            success=False,
            action="retry",
            affected_count=0,
            message="No matching failed documents found"
        )
    
    # Reset documents to pending
    count = await chunk_state_mgr.reset_documents_for_retry(doc_ids_to_retry)
    
    # Update analysis status to allow re-processing
    supabase.table("analysis_results").update({
        "status": "pending"
    }).eq("id", analysis_id).execute()
    
    logger.info(f"[RETRY] Reset {count} documents for retry in analysis {analysis_id}")
    
    return RecoveryActionResponse(
        success=True,
        action="retry",
        affected_count=count,
        message=f"Reset {count} documents for retry. Re-run analysis to process them."
    )


@router.post("/{analysis_id}/skip", response_model=RecoveryActionResponse)
async def skip_failed_documents(
    analysis_id: str,
    request: SkipDocumentsRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """
    Skip failed documents and continue with synthesis.
    
    If document_ids is empty, all failed documents will be skipped.
    """
    from legal_portal.services.chunk_state_manager import ChunkStateManager
    
    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, chunk_state"
    ).eq("id", analysis_id).single().execute()
    
    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    
    analysis = response.data
    case_id = analysis.get("case_id")
    
    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])
    
    chunk_state_mgr = ChunkStateManager(supabase, analysis_id)
    
    # Get failed documents
    failed_docs = await chunk_state_mgr.get_failed_documents()
    
    if not failed_docs:
        return RecoveryActionResponse(
            success=True,
            action="skip",
            affected_count=0,
            message="No failed documents to skip"
        )
    
    # Determine which docs to skip
    if request.document_ids:
        doc_ids_to_skip = [d for d in request.document_ids if d in [f["id"] for f in failed_docs]]
    else:
        doc_ids_to_skip = [f["id"] for f in failed_docs]
    
    if not doc_ids_to_skip:
        return RecoveryActionResponse(
            success=False,
            action="skip",
            affected_count=0,
            message="No matching failed documents found"
        )
    
    # Mark documents as skipped
    count = await chunk_state_mgr.mark_documents_skipped(doc_ids_to_skip)
    
    logger.info(f"[SKIP] Skipped {count} documents in analysis {analysis_id}")
    
    # Check if we can now proceed to synthesis
    can_proceed = await chunk_state_mgr.can_proceed_to_synthesis()
    
    message = f"Skipped {count} documents."
    if can_proceed:
        message += " Analysis can now proceed to synthesis."
    
    return RecoveryActionResponse(
        success=True,
        action="skip",
        affected_count=count,
        message=message
    )


@router.get("/{analysis_id}/state")
async def get_analysis_state(
    analysis_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """
    Get full analysis state for recovery/resume.
    
    Returns chunk_state with all document statuses, chunk plan, and summaries.
    """
    # Verify analysis exists and user has access
    response = supabase.table("analysis_results").select(
        "id, case_id, status, chunk_state, created_at, updated_at"
    ).eq("id", analysis_id).single().execute()
    
    if not response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    
    analysis = response.data
    case_id = analysis.get("case_id")
    
    # Verify case access
    _ensure_case_access(supabase, case_id, user["id"])
    
    chunk_state = analysis.get("chunk_state") or {}
    
    # Add computed fields
    documents = chunk_state.get("documents", {})
    statuses = [info.get("status", "pending") for info in documents.values()]
    
    return {
        "analysis_id": analysis_id,
        "status": analysis.get("status"),
        "phase": chunk_state.get("phase", "unknown"),
        "current_chunk": chunk_state.get("current_chunk", 0),
        "total_chunks": len(chunk_state.get("chunks", [])),
        "summary": {
            "total": len(documents),
            "pending": statuses.count("pending"),
            "processing": statuses.count("processing"),
            "completed": statuses.count("completed"),
            "failed": statuses.count("failed"),
            "skipped": statuses.count("skipped"),
        },
        "can_proceed": (
            statuses.count("pending") == 0 and 
            statuses.count("processing") == 0 and 
            statuses.count("failed") == 0
        ),
        "chunk_state": chunk_state,
        "created_at": analysis.get("created_at"),
        "updated_at": analysis.get("updated_at"),
    }


def _ensure_case_access(supabase_client, case_id: str, user_id: str) -> None:
    """Ensure the authenticated user owns the requested case."""
    case_response = (
        supabase_client.table("cases").select("id").eq("id", case_id).eq("user_id", user_id).execute()
    )

    if not case_response.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Case not found")


def _fetch_latest_analysis_result(supabase_client, case_id: str) -> Dict[str, Any]:
    """Fetch the latest completed analysis result for a case."""
    response = (
        supabase_client.table("analysis_results")
        .select("id, result")
        .eq("case_id", case_id)
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No completed analysis found for this case",
        )

    record = response.data[0]
    if not record.get("result"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Analysis result payload is missing",
        )

    return record
