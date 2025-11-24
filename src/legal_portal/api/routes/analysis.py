"""Document analysis endpoints."""

import asyncio
import json
import logging
import os
import shutil
import time
import traceback
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Dict, List, Optional

import html2text
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.core.data_models import (
    ChatMessageRequest,
    ChatMessageResponse,
    LetterType,
    ProcessingResult,
)
from legal_portal.services.case_chat_service import CaseChatService
from legal_portal.services.demand_letter_service import DemandLetterService
from legal_portal.services.json_processing_service import JsonProcessingService
from legal_portal.services.main_processor import process_case_documents
from legal_portal.services.progress_manager import ProgressManager
from legal_portal.utils.openai_client import OpenAIClient
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

router = APIRouter()
logger = logging.getLogger(__name__)


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
) -> tuple[Optional[str], List[str]]:
    """Synchronous helper to download and extract documents."""
    file_paths = []
    intake_form_path = None

    for doc in documents:
        storage_path = doc["storage_path"]
        # Sanitize filename to avoid directory traversal and invalid characters
        safe_filename = doc["file_name"].replace("/", "_").replace("\\", "_").replace(":", "_")
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
            print(f"  - ⏭️  Skipping video/audio file: {doc['file_name']}")
            continue

        # Check if document has extracted_text (Clio comms/notes or already processed)
        if doc.get("extracted_text"):
            print(f"  - Using extracted text for: {doc['file_name']}")
            # Save extracted text to temporary file
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(doc["extracted_text"])
        else:
            # Download file from Supabase Storage
            try:
                file_data = supabase.storage.from_("documents").download(storage_path)
                with open(temp_path, "wb") as f:
                    f.write(file_data)
            except Exception as e:
                print(f"  - Warning: Failed to download {doc['file_name']}: {e}")
                continue  # Skip this document if download fails

        # Check if this is a zip file - extract it
        if doc["file_name"].lower().endswith(".zip"):
            import zipfile

            print(f"  - 📦 Extracting zip file: {doc['file_name']}")

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
                            print(f"    ⏭️  Skipping video/audio: {extracted_file}")
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

                print(f"  - ✅ Extracted {extracted_count} files from {doc['file_name']}")

                # Remove the original zip file
                os.remove(temp_path)
                continue  # Skip adding the zip file itself to file_paths

            except zipfile.BadZipFile:
                print(f"  - ⚠️  Invalid zip file: {doc['file_name']}")
            except Exception as e:
                print(f"  - ⚠️  Failed to extract zip file {doc['file_name']}: {e}")

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
            # If we already have an intake form, only replace it with a better one (PDF/DOCX over communication)
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
                    print(f"  - Replaced intake form with better match: {doc['file_name']}")
                else:
                    file_paths.append(temp_path)
            else:
                intake_form_path = temp_path
                print(f"  - Identified intake form: {doc['file_name']}")
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

    return intake_form_path, file_paths


async def process_case_background(case_id: str, analysis_id: str, supabase, provider: str = "openai"):
    """Background task to process case documents.

    Args:
    ----
        case_id: Case ID
        analysis_id: Analysis record ID
        supabase: Supabase client
        provider: AI provider to use

    """
    # Initialize progress manager
    progress_manager = ProgressManager.get_instance()
    await progress_manager.create_channel(analysis_id)

    try:
        # Update status to processing
        supabase.table("analysis_results").update({"status": "processing"}).eq("id", analysis_id).execute()

        # Publish initial progress
        await progress_manager.publish_progress(
            channel_id=analysis_id, message="Starting document analysis...", phase="initialization", percent=0
        )

        # Get case details
        case_response = supabase.table("cases").select("*").eq("id", case_id).execute()
        if not case_response.data:
            raise ValueError("Case not found")

        case = case_response.data[0]

        # Get all documents for the case
        docs_response = supabase.table("documents").select("*").eq("case_id", case_id).execute()
        documents = docs_response.data

        if not documents:
            raise ValueError("No documents found for case")

        # Download documents from storage
        temp_dir = f"/tmp/case_{case_id}"
        os.makedirs(temp_dir, exist_ok=True)

        # Download and prepare files in threadpool to avoid blocking event loop
        intake_form_path, file_paths = await run_in_threadpool(
            _download_and_extract_documents, case_id, documents, supabase, temp_dir
        )

        # If still no documents, we need at least one
        if not intake_form_path:
            raise ValueError("At least one document is required for analysis")

        # Prepare case_info
        case_info = {
            "client_name": case["client_name"],
            "reference_number": case.get("reference_number", ""),
            "description": case.get("description", ""),
            "case_id": case_id,
        }

        # Prepare review_data (simplified - can be enhanced via UI later)
        review_data = {
            "key_documents": file_paths[:3] if len(file_paths) >= 3 else file_paths,  # First 3 docs as key
            "legal_issue": case.get("description", "General legal document analysis"),
        }

        print(f"  - Processing with intake form: {os.path.basename(intake_form_path)}")
        print(f"  - Additional documents: {len(file_paths)}")

        # Create progress callback that publishes to SSE
        async def progress_callback(message: str, docs_processed=None, phase="", percent=0):
            """Publish progress updates to SSE stream."""
            await progress_manager.publish_progress(
                channel_id=analysis_id,
                message=message,
                phase=phase,
                percent=percent,
                docs_processed=docs_processed or [],
                sub_step=message,  # Use message as sub-step for granularity
            )

        # Call the actual processor
        result: ProcessingResult = await process_case_documents(
            intake_form_path=intake_form_path,
            case_document_paths=file_paths,
            case_info=case_info,
            review_data=review_data,
            progress_callback=progress_callback,
        )

        print(f"  - Processing completed with status: {result.status}")

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

        # Publish completion event
        await progress_manager.publish_progress(
            channel_id=analysis_id,
            message="Analysis completed successfully!",
            phase="completed",
            percent=100,
            status="completed",
        )

    except Exception as e:
        # Log error and update status
        error_message = str(e)
        error_traceback = traceback.format_exc()

        print("\n❌ ERROR in process_case_background:")
        print(f"  - Error: {error_message}")
        print(f"  - Traceback: {error_traceback}")

        supabase.table("analysis_results").update(
            {"status": "error", "error": f"{error_message}\n\n{error_traceback}"}
        ).eq("id", analysis_id).execute()

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
        temp_dir = f"/tmp/case_{case_id}"
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                print(f"  - ✅ Cleaned up temporary directory: {temp_dir}")
            except Exception as cleanup_error:
                print(f"  - ⚠️  Failed to cleanup temp dir: {cleanup_error}")


@router.post("/start", response_model=AnalysisResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Start analysis for a case (async background task).

    Args:
    ----
        request: Analysis request
        background_tasks: FastAPI background tasks
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Analysis record (status: pending)

    """
    try:
        # Verify case ownership using user client (respects RLS)
        case_response = (
            user_supabase.table("cases")
            .select("id, status")
            .eq("id", request.case_id)
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
            .insert({"case_id": request.case_id, "status": "pending"})
            .execute()
        )

        if not analysis_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create analysis record"
            )

        analysis = analysis_response.data[0]

        # Update case status
        user_supabase.table("cases").update({"status": "processing"}).eq("id", request.case_id).execute()

        # Start background processing using SERVICE client (bypasses RLS, no token expiry)
        background_tasks.add_task(
            process_case_background, request.case_id, analysis["id"], service_supabase, request.provider
        )

        return analysis
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error starting analysis: {str(e)}"
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
        supabase: Supabase client

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

        # Get completed analysis
        response = (
            supabase.table("analysis_results")
            .select("*")
            .eq("case_id", case_id)
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No completed analysis found for this case"
            )

        analysis = response.data[0]
        result_payload = analysis.get("result") or {}
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
async def generate_letter(
    request: LetterGenerationRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Generate findings or demand letters on-demand."""
    _ensure_case_access(supabase, request.case_id, user["id"])
    analysis_record = _fetch_latest_analysis_result(supabase, request.case_id)

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
        "name": request.attorney_name or artifacts.get("attorney_name"),
        "firm": request.firm_name or artifacts.get("firm_name"),
        "phone": request.contact_phone or artifacts.get("contact_phone"),
        "email": request.contact_email or artifacts.get("contact_email"),
    }

    msr = processing_result.multi_stage_result
    letter_html: str
    target_party_name: Optional[str] = None

    if request.letter_type == LetterType.FINDINGS:
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
        )
        letter_key = "findings"
    else:
        if not request.target_party_name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="target_party_name is required for demand letters",
            )

        # Extract client_name from request, fact_matrix, or artifacts
        client_name = request.client_name
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
            target_party_name=request.target_party_name,
            demand_amount=request.demand_amount,
            demand_deadline=request.demand_deadline,
            specific_demands=request.specific_demands,
            attorney_info=attorney_info,
            client_name=client_name,
            document_summaries=document_summaries,
        )
        target_party_name = request.target_party_name
        letter_key = f"demand_{request.target_party_name.replace(' ', '_')}".lower()

    result_payload.setdefault("generated_letters", {})[letter_key] = letter_html
    supabase.table("analysis_results").update({"result": result_payload}).eq(
        "id", analysis_record["id"]
    ).execute()

    return LetterGenerationResponse(
        letter_html=letter_html,
        letter_type=request.letter_type,
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
    general_financial_items = []

    for item in financial_data:
        description = item.get("description", "").lower()
        if request.target_party_name.lower() in description:
            party_financial_items.append(item)
        else:
            general_financial_items.append(item)

    # Build AI prompt
    prompt = f"""Analyze this case data and calculate a reasonable demand amount for the opposing party: {request.target_party_name}

Financial Data:
{json.dumps(financial_data, indent=2)}

Parties Involved:
{json.dumps(parties, indent=2)}

Legal Issues:
{json.dumps(legal_issues, indent=2)}

Instructions:
1. Identify all amounts owed, damages claimed, or contract breaches related to {request.target_party_name}
2. Consider the strength of legal claims and potential recovery likelihood
3. Include reasonable attorney fees and costs if applicable
4. Provide a total demand amount that is justified by the evidence

Return a JSON object with:
- amount: float (total demand amount)
- reasoning: string (2-3 sentence explanation)
- breakdown: array of objects with {{description: string, amount: float}}

Be realistic and evidence-based. Only include amounts supported by the case data."""

    try:
        model = openai_client.get_preferred_model("demand_calculation", "gpt-4o-mini")
        response = await asyncio.to_thread(
            openai_client.create_chat_completion,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1000,
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
    chat_service = CaseChatService(openai_client)
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
