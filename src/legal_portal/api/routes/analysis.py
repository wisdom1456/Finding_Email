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
        msg.set_content(plain_text or "Please see the attached findings letter.")
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
        metadata = _store_artifact(storage, f"{prefix}/findings-letter.pdf", pdf_bytes, "application/pdf")
        if metadata:
            artifacts["letter_pdf"] = metadata

    eml_bytes = _generate_eml_bytes(result.main_letter, f"Findings Letter - Case {case_id}")
    if eml_bytes:
        metadata = _store_artifact(storage, f"{prefix}/findings-letter.eml", eml_bytes, "message/rfc822")
        if metadata:
            artifacts["letter_eml"] = metadata

    if result.main_letter_with_citations:
        html_bytes = result.main_letter_with_citations.encode("utf-8")
        metadata = _store_artifact(
            storage,
            f"{prefix}/findings-letter-cited.html",
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
    """Stream findings letter generation token by token."""
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


@router.post("/start", response_model=AnalysisResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")  # Rate limit AI analysis to prevent abuse
async def start_analysis(
    analysis_request: AnalysisRequest,
    request: Request,  # Required for rate limiter (must be named 'request')
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Start analysis for a case (async background task).

    Args:
    ----
        analysis_request: Analysis request data
        request: FastAPI request object
        background_tasks: FastAPI background tasks handler
        user: Current authenticated user
        user_supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    Returns:
    -------
        Analysis record (status: pending)

    """
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

        # Start background processing using SERVICE client (bypasses RLS, no token expiry)
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
