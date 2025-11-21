"""Document analysis endpoints.
"""

import json
import logging
import os
import shutil
import traceback
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Dict, Optional

import html2text
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.core.data_models import ProcessingResult
from legal_portal.services.main_processor import process_case_documents
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)

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
        logger.warning("Failed to render PDF artifact: %s", exc)
        return None


def _html_to_plain_text(html: Optional[str]) -> str:
    """Convert HTML to plain text for email bodies."""
    if not html:
        return ""
    try:
        return _HTML2TEXT_CONVERTER.handle(html)
    except Exception as exc:
        logger.warning("Failed to convert HTML to plain text: %s", exc)
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
        logger.warning("Failed to generate EML artifact: %s", exc)
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
        logger.warning("Failed to upload artifact %s: %s", path, exc)
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


def _attach_signed_artifact_urls(
    service_supabase, artifacts: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Attach signed URLs to stored artifact metadata."""
    enriched: Dict[str, Dict[str, Any]] = {}
    for key, info in artifacts.items():
        path = info.get("path")
        bucket = info.get("bucket", ARTIFACT_BUCKET)
        if not path:
            continue
        try:
            signed = service_supabase.storage.from_(bucket).create_signed_url(path, SIGNED_URL_TTL)
            signed_url = signed.get("signedURL")
            enriched[key] = {**info, "signed_url": signed_url}
        except Exception as exc:
            logger.warning("Failed to create signed URL for %s: %s", path, exc)
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


async def process_case_background(case_id: str, analysis_id: str, supabase, provider: str = "openai"):
    """Background task to process case documents.

    Args:
    ----
        case_id: Case ID
        analysis_id: Analysis record ID
        supabase: Supabase client
        provider: AI provider to use
    """
    try:
        # Update status to processing
        supabase.table("analysis_results").update({"status": "processing"}).eq("id", analysis_id).execute()

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

                    # Add extracted files to processing list (filtering out video/audio)
                    extracted_count = 0
                    for root, dirs, files in os.walk(zip_extract_dir):
                        for extracted_file in files:
                            # Skip hidden files and system files
                            if extracted_file.startswith(".") or extracted_file.startswith("__MACOSX"):
                                continue

                            # Skip video/audio files
                            if any(extracted_file.lower().endswith(ext) for ext in video_audio_extensions):
                                print(f"    ⏭️  Skipping video/audio: {extracted_file}")
                                continue

                            extracted_path = os.path.join(root, extracted_file)
                            file_paths.append(extracted_path)
                            extracted_count += 1

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
                    if is_document_file or (
                        doc.get("metadata", {}).get("is_intake_form") and not current_is_doc
                    ):
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

        # Call the actual processor
        result: ProcessingResult = await process_case_documents(
            intake_form_path=intake_form_path,
            case_document_paths=file_paths,
            case_info=case_info,
            review_data=review_data,
            progress_callback=None,
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
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
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
        )


@router.get("/status/{case_id}", response_model=AnalysisResponse)
async def get_analysis_status(
    case_id: str, user=Depends(get_current_user), supabase=Depends(get_user_supabase_client)
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
        )


@router.get("/results/{case_id}")
async def get_analysis_results(
    case_id: str,
    user=Depends(get_current_user),
    supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
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
        )
