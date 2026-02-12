"""Case management endpoints."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.services.clio_client import ClioAPIError, ClioAuthError, ClioClient
from legal_portal.api.utils.content_extractor import DocumentProcessor as ContentExtractor
from legal_portal.config.default import get_settings
from legal_portal.core.data_models import DocumentStatus
from legal_portal.core.document_processor import DocumentProcessor, ValidationError
from legal_portal.services.progress_manager import ProgressManager, get_progress_manager

# Import classification function from documents module
from legal_portal.api.routes.documents import classify_document_type

logger = logging.getLogger(__name__)
router = APIRouter()


class CaseCreate(BaseModel):
    """Request model for creating a new case."""

    client_name: str = Field(..., min_length=1, max_length=200)
    reference_number: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    jurisdiction: str = Field(default="Florida")


class CaseUpdate(BaseModel):
    """Request model for updating a case."""

    client_name: Optional[str] = Field(None, min_length=1, max_length=200)
    reference_number: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(pending|processing|completed|error)$")
    jurisdiction: Optional[str] = None


class CaseResponse(BaseModel):
    """Response model for a case."""

    id: str
    user_id: str
    client_name: str
    reference_number: Optional[str]
    description: Optional[str]
    status: str
    jurisdiction: str
    created_at: datetime
    updated_at: datetime
    clio_matter_id: Optional[str] = None
    created_via_clio: Optional[bool] = False


class CreateFromClioRequest(BaseModel):
    """Request model for creating a case from Clio matter."""

    matter_id: int = Field(..., description="Clio matter ID")
    auto_import: bool = Field(True, description="Auto-import documents")
    jurisdiction: Optional[str] = Field(None, description="State jurisdiction")


class CreateFromClioResponse(BaseModel):
    """Response model for creating a case from Clio."""

    success: bool
    case_id: str
    case: Dict[str, Any]
    import_status: Optional[Dict[str, Any]] = None
    intake_analysis: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    case_created: bool = True
    import_failed: bool = False
    import_id: Optional[str] = None  # ID for SSE progress tracking


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    case_data: CaseCreate,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Create a new case for the authenticated user.

    Args:
    ----
        case_data: Case creation data
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Created case

    """
    try:
        logger.info(
            "Creating new case",
            extra={
                "user_id": user["id"],
                "user_email": user.get("email"),
                "client_name": case_data.client_name,
            },
        )

        # Verify profile exists
        logger.debug(f"Checking if profile exists for user {user['id']}")
        try:
            profile_check = supabase.table("profiles").select("id").eq("id", user["id"]).execute()
            logger.debug(f"Profile check result: {len(profile_check.data)} records found")
        except Exception as pe:
            logger.warning(f"Profile check failed: {pe}")

        logger.debug("Attempting to insert case into database")
        response = (
            supabase.table("cases")
            .insert(
                {
                    "user_id": user["id"],
                    "client_name": case_data.client_name,
                    "reference_number": case_data.reference_number,
                    "description": case_data.description,
                    "jurisdiction": case_data.jurisdiction,
                    "status": "pending",
                }
            )
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create case"
            )

        case_id = response.data[0]["id"]
        logger.info(f"Successfully created case with ID: {case_id}")

        return response.data[0]
    except Exception as e:
        logger.error(
            f"Error creating case: {type(e).__name__}: {str(e)}",
            exc_info=True,
            extra={
                "user_id": user.get("id"),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "error_details": getattr(e, "details", None),
                "error_code": getattr(e, "code", None),
            },
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating case: {str(e)}"
        ) from e


@router.get("", response_model=List[CaseResponse])
async def list_cases(
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
    limit: int = 50,
    offset: int = 0,
):
    """List all cases for the authenticated user.

    Args:
    ----
        user: Current authenticated user
        supabase: Supabase client
        limit: Maximum number of cases to return
        offset: Number of cases to skip

    Returns:
    -------
        List of cases

    """
    try:
        response = (
            supabase.table("cases")
            .select("*")
            .eq("user_id", user["id"])
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return response.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching cases: {str(e)}"
        ) from e


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Get a specific case by ID.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Case details

    """
    try:
        response = supabase.table("cases").select("*").eq("id", case_id).eq("user_id", user["id"]).execute()

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching case: {str(e)}"
        ) from e


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    case_data: CaseUpdate,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Update a case.

    Args:
    ----
        case_id: Case ID
        case_data: Case update data
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Updated case

    """
    try:
        # Verify ownership
        existing = supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()

        if not existing.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Update only provided fields
        update_data = case_data.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

        response = supabase.table("cases").update(update_data).eq("id", case_id).execute()

        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error updating case: {str(e)}"
        ) from e


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    user_supabase=Depends(get_user_supabase_client),  # noqa: B008
):
    """Delete a case and all associated documents from storage and database.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        user_supabase: User-scoped Supabase client

    """
    try:
        logger.debug("Deleting case", extra={"case_id": case_id, "user_id": user["id"]})

        # Verify ownership
        existing = (
            user_supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not existing.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get all documents for this case to delete from storage
        logger.debug("Fetching documents for storage cleanup", extra={"case_id": case_id})
        docs_response = (
            user_supabase.table("documents").select("storage_path").eq("case_id", case_id).execute()
        )

        # Resolve the service client lazily so missing service-role env vars
        # don't block case deletion in production.
        service_supabase = None
        try:
            service_supabase = get_supabase_client()
        except Exception as service_client_error:
            logger.warning(
                "Service-role Supabase client unavailable; skipping storage cleanup",
                extra={"case_id": case_id, "error": str(service_client_error)},
            )

        # Delete files from storage only if we have service client access.
        if docs_response.data:
            storage_paths = [doc["storage_path"] for doc in docs_response.data]
            logger.debug("Deleting files from storage", extra={"count": len(storage_paths)})
            if service_supabase:
                try:
                    service_supabase.storage.from_("documents").remove(storage_paths)
                    logger.debug("Storage files deleted successfully")
                except Exception as storage_error:
                    logger.warning("Storage deletion error (continuing)", extra={"error": str(storage_error)})

        # Delete case from database (cascade deletes documents and analysis_results)
        logger.debug("Deleting case from database (cascade delete)")
        user_supabase.table("cases").delete().eq("id", case_id).execute()

        logger.info("Case deleted successfully", extra={"case_id": case_id})
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in delete_case", extra={"case_id": case_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting case: {str(e)}"
        ) from e


# ===== Clio Integration Endpoints =====


async def get_clio_client_for_user(
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_supabase_client),  # noqa: B008
) -> ClioClient:
    """Get authenticated Clio client for user."""
    try:
        # Get user's tokens
        result = supabase.table("integrations_clio").select("*").eq("user_id", user["id"]).execute()

        if not result.data:
            raise HTTPException(status_code=401, detail="Clio not connected. Please authorize first.")

        integration = result.data[0]
        access_token = integration["access_token"]
        refresh_token = integration["refresh_token"]
        expires_at_str = integration["expires_at"]

        # Parse the datetime and ensure it's timezone-aware
        if isinstance(expires_at_str, str):
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        else:
            expires_at = expires_at_str

        # Ensure expires_at is timezone-aware (UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Check if token needs refresh
        from legal_portal.api.services.clio_auth_service import ClioAuthService

        now = datetime.now(timezone.utc)
        is_expired = now >= expires_at

        auth_service = ClioAuthService()
        if is_expired:
            # Refresh token
            new_tokens = auth_service.refresh_access_token(refresh_token)

            # Update database
            supabase.table("integrations_clio").update(
                {
                    "access_token": new_tokens["access_token"],
                    "refresh_token": new_tokens["refresh_token"],
                    "expires_at": new_tokens["expires_at"].isoformat(),
                }
            ).eq("user_id", user["id"]).execute()

            access_token = new_tokens["access_token"]

        return ClioClient(access_token)

    except ClioAuthError as e:
        raise HTTPException(status_code=401, detail=f"Clio authentication failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize Clio client: {str(e)}") from e


async def import_clio_documents_helper(
    matter_id: int,
    case_id: str,
    user: dict,
    clio_client: ClioClient,
    supabase,
    progress_manager=None,
    import_id: str = None,
) -> Dict[str, Any]:
    """Import documents from Clio matter.

    Returns import status with counts and any errors.

    Args:
    ----
        matter_id: The Clio matter ID to import from
        case_id: The case ID to import documents into
        user: Current authenticated user dict
        clio_client: Initialized Clio API client
        supabase: Supabase client instance
        progress_manager: Optional ProgressManager instance for SSE updates
        import_id: Unique ID for this import operation (for SSE tracking)

    """
    # Helper to persist progress to DB for cross-instance Vercel polling
    async def persist_progress(message: str, phase: str, percent: int, **kwargs):
        """Publish progress to in-memory manager AND persist to database."""
        if progress_manager and import_id:
            await progress_manager.publish_progress(
                channel_id=import_id,
                message=message,
                phase=phase,
                percent=percent,
                **kwargs,
            )
        # Always persist to DB if we have case_id and import_id
        if case_id and import_id:
            try:
                from datetime import datetime, timezone
                progress_data = {
                    "type": kwargs.get("status", "progress"),
                    "message": message,
                    "phase": phase,
                    "percent": percent,
                }
                import_progress = {
                    "import_id": import_id,
                    "progress": progress_data,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                supabase.table("cases").update({"import_progress": import_progress}).eq("id", case_id).execute()
            except Exception as e:
                logger.warning(f"Failed to persist progress to DB: {e}")

    try:
        # Import communications
        logger.debug("Fetching communications for matter", extra={"matter_id": matter_id})
        await persist_progress("Fetching communications from Clio...", "fetch_communications", 35)
        communications = await run_in_threadpool(clio_client.get_communications, matter_id, limit=100)
        logger.debug("Found communications", extra={"count": len(communications)})

        # Import notes
        logger.debug("Fetching notes for matter", extra={"matter_id": matter_id})
        await persist_progress("Fetching notes from Clio...", "fetch_notes", 38)
        notes = await run_in_threadpool(clio_client.get_notes, matter_id)
        logger.debug("Found notes", extra={"count": len(notes)})

        # Import documents (metadata only)
        logger.debug("Fetching documents for matter", extra={"matter_id": matter_id})
        await persist_progress("Fetching documents from Clio...", "fetch_documents", 40)
        documents = await run_in_threadpool(clio_client.get_documents, matter_id)
        logger.debug("Found documents", extra={"count": len(documents)})

        comm_success = 0
        note_success = 0
        doc_success = 0
        errors = []

        # Track compression statistics
        files_compressed = 0
        total_original_size = 0
        total_compressed_size = 0

        # Save communications as document entries
        total_comms = len(communications)
        for idx, comm in enumerate(communications):
            try:
                subject = comm.subject or "Untitled Communication"
                percent = 42 + int((idx / max(total_comms, 1)) * 5)
                # Persist every 3rd item to avoid DB spam but still show progress
                if idx % 3 == 0:
                    await persist_progress(
                        f"Processing communication {idx + 1} of {total_comms}",
                        "import_communications",
                        percent,
                        sub_step=subject[:50],
                        current_doc={"index": idx + 1, "total": total_comms, "name": subject},
                    )
                # Create a text document for each communication
                content = f"Subject: {comm.subject}\n"
                content += f"Date: {comm.date}\n"
                content += f"From: {comm.sender.name}\n"
                content += f"Type: {comm.communication_type}\n\n"
                content += comm.body

                # Check if this is an intake form
                is_intake = "intake" in comm.subject.lower() if comm.subject else False

                doc_data = {
                    "case_id": case_id,
                    "file_name": f"Clio Communication - {comm.subject[:50]}.txt",
                    "file_type": "text/plain",
                    "file_size": len(content.encode("utf-8")),
                    "storage_path": f"clio/{case_id}/comm_{comm.id}.txt",
                    "status": DocumentStatus.READY,
                    "extracted_text": content,
                    "metadata": {
                        "clio_source": True,
                        "clio_type": "communication",
                        "clio_id": comm.id,
                        "clio_subject": comm.subject,
                        "clio_date": comm.date.isoformat() if comm.date else None,
                        "is_intake_form": is_intake,
                    },
                }
                supabase.table("documents").insert(doc_data).execute()
                comm_success += 1
            except Exception as e:
                errors.append(f"Communication {comm.id}: {str(e)}")

        # Save notes as document entries
        total_notes = len(notes)
        for idx, note in enumerate(notes):
            try:
                note_subject = note.get("subject", "Untitled Note")
                percent = 47 + int((idx / max(total_notes, 1)) * 5)
                # Persist every 3rd item to avoid DB spam
                if idx % 3 == 0:
                    await persist_progress(
                        f"Processing note {idx + 1} of {total_notes}",
                        "import_notes",
                        percent,
                        sub_step=note_subject[:50],
                        current_doc={"index": idx + 1, "total": total_notes, "name": note_subject},
                    )
                note_subject = note.get("subject", "No Subject")
                note_detail = note.get("detail", "")
                note_date = note.get("date", "")

                # Check if this is an intake form
                is_intake = "intake" in note_subject.lower()

                doc_data = {
                    "case_id": case_id,
                    "file_name": f"Clio Note - {note_subject[:50]}.txt",
                    "file_type": "text/plain",
                    "file_size": len(note_detail.encode("utf-8")) if note_detail else 0,
                    "storage_path": f"clio/{case_id}/note_{note['id']}.txt",
                    "status": DocumentStatus.READY,
                    "extracted_text": note_detail,
                    "metadata": {
                        "clio_source": True,
                        "clio_type": "note",
                        "clio_id": note["id"],
                        "clio_subject": note_subject,
                        "clio_date": note_date,
                        "is_intake_form": is_intake,
                    },
                }
                supabase.table("documents").insert(doc_data).execute()
                note_success += 1
            except Exception as e:
                errors.append(f"Note {note.get('id', 'unknown')}: {str(e)}")

        # Download and process document files
        logger.info("Processing Clio documents", extra={"count": len(documents)})
        total_docs = len(documents)

        # Build duplicate detection set from existing documents in this case
        # This handles re-imports and duplicate files from Clio
        existing_docs = supabase.table("documents").select("file_name, file_size, metadata").eq("case_id", case_id).execute()
        existing_file_keys = set()  # (filename, size) tuples for quick lookup
        for existing in existing_docs.data or []:
            key = (existing["file_name"], existing.get("file_size", 0))
            existing_file_keys.add(key)
            # Also track by original filename if available
            if existing.get("metadata", {}).get("original_filename"):
                key2 = (existing["metadata"]["original_filename"], existing.get("file_size", 0))
                existing_file_keys.add(key2)

        # Track duplicates seen in THIS import batch
        import_batch_keys = set()
        duplicates_count = 0

        for idx, doc in enumerate(documents):
            try:
                doc_name = doc.get("name", "Untitled Document")
                percent = 52 + int((idx / max(total_docs, 1)) * 40)
                # Persist EVERY document progress since this is the slow part
                await persist_progress(
                    f"Downloading document {idx + 1} of {total_docs}: {doc_name[:30]}",
                    "import_documents",
                    percent,
                    sub_step=doc_name[:50],
                    current_doc={"index": idx + 1, "total": total_docs, "name": doc_name},
                )
                doc_id = doc["id"]
                doc_name = doc.get("name", "Untitled Document")
                doc_size = doc.get("size", 0)  # Size in bytes from Clio API

                logger.debug("Processing document", extra={"doc_name": doc_name, "doc_id": doc_id, "size_mb": f"{doc_size / (1024 * 1024):.2f}"})

                # Check file size limits before downloading
                # More restrictive for zips since they could contain videos
                MAX_SIZE_ZIP_MB = 50
                MAX_SIZE_OTHER_MB = 100
                
                is_zip = doc_name.lower().endswith(".zip")
                size_limit_mb = MAX_SIZE_ZIP_MB if is_zip else MAX_SIZE_OTHER_MB
                size_limit_bytes = size_limit_mb * 1024 * 1024
                
                if doc_size > size_limit_bytes:
                    file_size_mb = doc_size / (1024 * 1024)
                    logger.warning(
                        f"Skipping large file {doc_name}: "
                        f"{file_size_mb:.1f}MB exceeds {size_limit_mb}MB limit"
                    )
                    errors.append(
                        f"Document {doc_name}: File too large ({file_size_mb:.1f}MB). "
                        f"Maximum size is {size_limit_mb}MB for {'zip files' if is_zip else 'this file type'}."
                    )
                    # Save metadata-only record so user knows it was skipped
                    skip_record = {
                        "case_id": case_id,
                        "file_name": doc_name,
                        "file_type": doc.get("content_type", "application/octet-stream"),
                        "file_size": doc_size,
                        "storage_path": "",  # Empty string instead of None to satisfy NOT NULL constraint
                        "status": "skipped_too_large",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "error": f"File too large ({file_size_mb:.1f}MB). Maximum size is {size_limit_mb}MB.",
                            "error_type": "FILE_TOO_LARGE",
                            "skip_reason": f"Exceeds {size_limit_mb}MB limit for {'zip files' if is_zip else 'documents'}",
                        },
                    }
                    supabase.table("documents").insert(skip_record).execute()
                    continue  # Skip to next document

                # Clio doesn't provide download URLs in the documents list
                # We need to construct the download URL using the document ID
                # Format: /api/v4/documents/{id}/download.json
                doc_url = f"https://app.clio.com/api/v4/documents/{doc_id}/download.json"

                # Get Clio access token for download
                integration = (
                    supabase.table("integrations_clio")
                    .select("access_token")
                    .eq("user_id", user["id"])
                    .execute()
                )

                if not integration.data:
                    raise Exception("Clio integration not found")

                access_token = integration.data[0]["access_token"]

                # Download file from Clio with timeout (60s per document to prevent Vercel timeout)
                # Run blocking download in threadpool with asyncio timeout
                import asyncio
                DOC_TIMEOUT_SECONDS = 60  # Max time per document

                try:
                    file_content, content_type = await asyncio.wait_for(
                        run_in_threadpool(ContentExtractor.download_file, doc_url, access_token),
                        timeout=DOC_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Document download timed out after {DOC_TIMEOUT_SECONDS}s", extra={"doc_name": doc_name})
                    errors.append(f"Document {doc_name}: Download timed out (>60s)")
                    # Save metadata-only record so user knows it was skipped
                    skip_record = {
                        "case_id": case_id,
                        "file_name": doc_name,
                        "file_type": "application/octet-stream",
                        "file_size": 0,
                        "storage_path": "",  # Empty string instead of None to satisfy NOT NULL constraint
                        "status": "download_timeout",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_url": doc_url,
                            "error": f"Download timed out after {DOC_TIMEOUT_SECONDS}s",
                            "error_type": "TIMEOUT",
                        },
                    }
                    supabase.table("documents").insert(skip_record).execute()
                    continue  # Skip to next document

                original_size = len(file_content)
                logger.debug("Downloaded file", extra={"size_mb": f"{original_size / (1024 * 1024):.2f}"})

                # --- DUPLICATE DETECTION ---
                # Check if this file is a duplicate (by name + size)
                file_key = (doc_name, original_size)
                is_duplicate = False
                duplicate_reason = None

                if file_key in existing_file_keys:
                    is_duplicate = True
                    duplicate_reason = "exists_in_case"
                    logger.info(f"Duplicate detected (exists in case): {doc_name} ({original_size} bytes)")
                elif file_key in import_batch_keys:
                    is_duplicate = True
                    duplicate_reason = "duplicate_in_import"
                    logger.info(f"Duplicate detected (in import batch): {doc_name} ({original_size} bytes)")

                # Track this file in the import batch
                import_batch_keys.add(file_key)

                if is_duplicate:
                    duplicates_count += 1

                # Check if this is an intake form candidate
                is_intake_candidate = "intake" in doc_name.lower()

                # Use unified processor for validation, compression, and upload (also with timeout)
                # Skip text extraction during bulk import - extraction can be done on-demand
                # This prevents OCR timeouts from blocking the entire import
                processor = DocumentProcessor()

                try:
                    doc_record = await asyncio.wait_for(
                        processor.process_and_upload(
                            file_content=file_content,
                            filename=doc_name,
                            user_id=user["id"],
                            case_id=case_id,
                            supabase_client=supabase,
                            is_intake_form=is_intake_candidate,
                            content_type=content_type,
                            skip_extraction=True,  # Defer OCR to avoid Vercel timeout
                        ),
                        timeout=DOC_TIMEOUT_SECONDS,
                    )

                    # Track compression statistics if compressed
                    if doc_record.get("metadata", {}).get("compression", {}).get("compressed"):
                        files_compressed += 1
                        comp_meta = doc_record["metadata"]["compression"]
                        total_original_size += comp_meta["original_size"]
                        total_compressed_size += comp_meta["compressed_size"]
                        logger.debug(
                            "File compressed",
                            extra={
                                "original_mb": f"{comp_meta['original_size'] / (1024 * 1024):.2f}",
                                "compressed_mb": f"{comp_meta['compressed_size'] / (1024 * 1024):.2f}",
                            },
                        )

                    # Classify document type for efficient extraction
                    classification = classify_document_type(doc_name, content_type or "application/octet-stream")

                    # Add Clio-specific metadata
                    doc_record["metadata"].update(
                        {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_url": doc_url,
                            "clio_filename": doc_name,
                            "is_intake_candidate": is_intake_candidate,
                            "classification": classification,  # Add classification
                        }
                    )
                    logger.debug(f"Classified as {classification}: {doc_name}")

                    # Add duplicate info to metadata if detected
                    if is_duplicate:
                        doc_record["metadata"]["is_duplicate"] = True
                        doc_record["metadata"]["duplicate_reason"] = duplicate_reason
                        doc_record["metadata"]["excluded"] = True  # Excluded by default
                        doc_record["status"] = "duplicate"
                        logger.info(f"Marked as duplicate: {doc_name} (reason: {duplicate_reason})")

                    # Insert document record
                    supabase.table("documents").insert(doc_record).execute()
                    doc_success += 1
                    logger.debug("Successfully imported document", extra={"doc_name": doc_name, "is_duplicate": is_duplicate})

                except ValidationError as e:
                    logger.warning("Validation failed", extra={"error_code": e.error_code, "error": str(e)})
                    raise Exception(f"Validation failed: {str(e)}") from e
                except asyncio.TimeoutError:
                    logger.warning(f"Document processing timed out after {DOC_TIMEOUT_SECONDS}s", extra={"doc_name": doc_name})
                    errors.append(f"Document {doc_name}: Processing timed out (>60s)")
                    # Save metadata-only record
                    skip_record = {
                        "case_id": case_id,
                        "file_name": doc_name,
                        "file_type": content_type or "application/octet-stream",
                        "file_size": original_size,
                        "storage_path": "",  # Empty string instead of None to satisfy NOT NULL constraint
                        "status": "processing_timeout",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_url": doc_url,
                            "error": f"Processing timed out after {DOC_TIMEOUT_SECONDS}s",
                            "error_type": "TIMEOUT",
                        },
                    }
                    supabase.table("documents").insert(skip_record).execute()
                    continue  # Skip to next document

            except Exception as e:
                error_msg = f"Document {doc.get('id', 'unknown')} ({doc.get('name', 'unknown')}): {str(e)}"
                errors.append(error_msg)
                logger.warning("Error importing document", extra={"doc_id": doc.get("id"), "error": str(e)})

        result = {
            "success": len(errors) == 0,
            "communications_count": comm_success,
            "notes_count": note_success,
            "documents_count": doc_success,
            "duplicates_count": duplicates_count,
            "total_imported": comm_success + note_success + doc_success,
            "errors": errors if errors else None,
        }

        logger.info(
            "Import summary",
            extra={
                "communications": comm_success,
                "notes": note_success,
                "documents": doc_success,
                "duplicates": duplicates_count,
                "total": comm_success + note_success + doc_success,
                "errors": len(errors) if errors else 0,
            },
        )

        # Log compression statistics if any files were compressed
        if files_compressed > 0:
            total_saved = total_original_size - total_compressed_size
            avg_reduction = (total_saved / total_original_size) * 100 if total_original_size > 0 else 0
            logger.info(
                "Compression summary",
                extra={
                    "files_compressed": files_compressed,
                    "original_mb": f"{total_original_size / 1024 / 1024:.1f}",
                    "compressed_mb": f"{total_compressed_size / 1024 / 1024:.1f}",
                    "saved_mb": f"{total_saved / 1024 / 1024:.1f}",
                    "reduction_percent": f"{avg_reduction:.1f}",
                },
            )

        # Post-processing: Prioritize intake forms
        logger.debug("Prioritizing intake forms")
        intake_docs = supabase.table("documents").select("*").eq("case_id", case_id).execute()

        if intake_docs.data:
            intake_candidates = [
                doc for doc in intake_docs.data if doc.get("metadata", {}).get("is_intake_candidate") is True
            ]

            if len(intake_candidates) > 1:
                logger.debug("Found intake candidates", extra={"count": len(intake_candidates)})

                # Score each candidate
                scored = []
                for doc in intake_candidates:
                    score = analyze_intake_priority(doc)
                    scored.append((doc, score))
                    logger.debug(
                        "Scored intake candidate",
                        extra={"file_name": doc["file_name"], "score": score, "size": doc["file_size"]},
                    )

                # Sort by score (highest first)
                scored.sort(key=lambda x: x[1], reverse=True)

                # Mark the best one as is_intake_form
                best_doc, best_score = scored[0]
                logger.info(
                    "Best intake selected", extra={"file_name": best_doc["file_name"], "score": best_score}
                )

                # Update the best one
                best_doc["metadata"]["is_intake_form"] = True
                best_doc["metadata"]["is_intake_candidate"] = False
                supabase.table("documents").update({"metadata": best_doc["metadata"]}).eq(
                    "id", best_doc["id"]
                ).execute()

                # Update others to mark as alternates only
                for doc, score in scored[1:]:
                    doc["metadata"]["is_intake_candidate"] = True  # Keep as candidate
                    doc["metadata"]["is_intake_form"] = False
                    supabase.table("documents").update({"metadata": doc["metadata"]}).eq(
                        "id", doc["id"]
                    ).execute()
                    logger.debug("Marked as alternate", extra={"file_name": doc["file_name"], "score": score})

            elif len(intake_candidates) == 1:
                # Only one candidate, mark it as the intake form
                doc = intake_candidates[0]
                doc["metadata"]["is_intake_form"] = True
                doc["metadata"]["is_intake_candidate"] = False
                supabase.table("documents").update({"metadata": doc["metadata"]}).eq(
                    "id", doc["id"]
                ).execute()
                logger.info("Single intake form identified", extra={"file_name": doc["file_name"]})

        return result

    except Exception as e:
        logger.exception(
            "Exception in import_clio_documents_helper",
            extra={"error": str(e), "error_type": type(e).__name__},
        )

        return {
            "success": False,
            "error": str(e),
            "communications_count": 0,
            "notes_count": 0,
            "documents_count": 0,
            "total_imported": 0,
        }


def analyze_intake_priority(doc: Dict[str, Any]) -> int:
    """Score intake documents to prioritize filled forms over blank templates.

    Higher scores = better intake form candidates.

    Args:
    ----
        doc: Document dictionary with file_name, file_size, etc.

    Returns:
    -------
        Priority score (higher = better)

    """
    filename = doc.get("file_name", "").lower()
    file_size = doc.get("file_size", 0)

    priority_score = 0

    # Negative scores for fillable/blank indicators
    if "fillable" in filename:
        priority_score -= 100
    if "blank" in filename:
        priority_score -= 100
    if "template" in filename:
        priority_score -= 50
    if "[fillable]" in filename:
        priority_score -= 100
    if "[blank]" in filename:
        priority_score -= 100

    # Positive scores for likely filled forms
    min_content_size = get_settings().min_file_size_for_content
    if file_size > min_content_size:  # Likely has content
        priority_score += 50
    elif file_size > min_content_size * 1.4:  # Very likely filled (140% of threshold)
        priority_score += 80

    # Prefer forms with person names or specific identifiers (usually after " - ")
    if " - " in filename:
        priority_score += 30
    if "_" in filename and "[fillable]" not in filename:
        priority_score += 10

    # Boost for "completed", "filled", "final" keywords
    if "completed" in filename:
        priority_score += 50
    if "filled" in filename:
        priority_score += 50
    if "final" in filename:
        priority_score += 40

    return priority_score


def analyze_intake_documents(case_id: str, supabase) -> Dict[str, Any]:
    """Analyze documents for intake form candidates.

    Returns analysis with intake document info.
    """
    try:
        # Get all documents for the case
        docs_result = supabase.table("documents").select("*").eq("case_id", case_id).execute()

        documents = docs_result.data

        # Find intake candidates (any document with "intake" in filename)
        intake_candidates = [doc for doc in documents if "intake" in doc.get("file_name", "").lower()]

        # Find already marked intake
        marked_intake = [doc for doc in documents if doc.get("metadata", {}).get("is_intake_form") is True]

        if len(intake_candidates) == 0:
            message = "⚠️ No intake document found. First document will be used."
            return {
                "intake_candidates_count": 0,
                "marked_intake_count": len(marked_intake),
                "message": message,
                "requires_user_selection": False,
                "best_intake": None,
            }

        # Score and prioritize intake candidates
        scored_candidates = []
        for doc in intake_candidates:
            score = analyze_intake_priority(doc)
            scored_candidates.append(
                {
                    "doc": doc,
                    "score": score,
                    "doc_id": doc["id"],
                    "filename": doc.get("file_name", ""),
                    "size": doc.get("file_size", 0),
                }
            )

        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        best_intake = scored_candidates[0] if scored_candidates else None

        if len(marked_intake) == 1:
            message = f"✅ Intake document identified: {marked_intake[0]['file_name']}"
        elif len(intake_candidates) == 1:
            message = f"✅ Intake document identified: {intake_candidates[0]['file_name']}"
        elif best_intake and best_intake["score"] > 0:
            fname = best_intake["filename"]
            score = best_intake["score"]
            message = f"✅ Best intake form auto-selected: {fname} (score: {score})"
        else:
            message = f"⚠️ Multiple intake candidates found ({len(intake_candidates)}). Best match selected."

        return {
            "intake_candidates_count": len(intake_candidates),
            "marked_intake_count": len(marked_intake),
            "message": message,
            "requires_user_selection": False,  # We auto-select now
            "best_intake": best_intake,
            "scored_candidates": scored_candidates[:5],  # Top 5 for debugging
        }

    except Exception as e:
        return {"error": str(e), "message": "Failed to analyze intake documents"}


async def process_clio_import_background(
    matter_id: int,
    case_id: str,
    user: dict,
    clio_client: ClioClient,
    supabase,
    progress_manager: ProgressManager,
    import_id: str,
    case_clio_data: dict,
):
    """Background task to handle Clio import process."""
    # #region agent log
    import json as _json
    def _debug_log_bg(msg, data, hyp):
        logger.info(f"[DEBUG] {msg} | hyp={hyp} | data={_json.dumps(data)}")
    _debug_log_bg("bg_task_start", {"import_id": import_id, "case_id": case_id, "matter_id": matter_id}, "H2,H4")
    # #endregion

    # Helper to persist progress to DB (missing from this code path!)
    async def save_progress_to_db(progress_data: dict):
        # #region agent log
        _debug_log_bg("save_progress_to_db_called", {"progress_data": progress_data}, "H2")
        # #endregion
        try:
            from datetime import datetime, timezone
            import_progress = {
                "import_id": import_id,
                "progress": progress_data,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            supabase.table("cases").update({"import_progress": import_progress}).eq("id", case_id).execute()
            # #region agent log
            _debug_log_bg("save_progress_to_db_success", {"case_id": case_id}, "H2")
            # #endregion
        except Exception as e:
            # #region agent log
            _debug_log_bg("save_progress_to_db_error", {"error": str(e)}, "H1,H2")
            # #endregion
            logger.warning(f"Failed to persist import progress to DB: {e}")

    try:
        # 3. Import documents
        progress_data = {"type": "progress", "message": "Starting document import from Clio...", "phase": "import_start", "percent": 30}
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Starting document import from Clio...",
            phase="import_start",
            percent=30,
            sub_step="initialization",
        )
        await save_progress_to_db(progress_data)

        logger.debug("Starting document import (background)")
        import_result = await import_clio_documents_helper(
            matter_id, case_id, user, clio_client, supabase, progress_manager, import_id
        )
        logger.info("Import completed", extra={"total_imported": import_result.get("total_imported", 0)})

        # Update case with import counts
        # Use run_in_threadpool for supabase call just in case
        await run_in_threadpool(
            lambda: supabase.table("cases")
            .update(
                {
                    "clio_matter_data": {
                        **case_clio_data,
                        "communications_count": import_result.get("communications_count", 0),
                        "notes_count": import_result.get("notes_count", 0),
                        "documents_count": import_result.get("documents_count", 0),
                    }
                }
            )
            .eq("id", case_id)
            .execute()
        )

        # 4. Analyze intake candidates
        progress_data = {"type": "progress", "message": "Analyzing intake documents...", "phase": "analyze_intake", "percent": 90}
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Analyzing intake documents...",
            phase="analyze_intake",
            percent=90,
            sub_step="identification",
        )
        await save_progress_to_db(progress_data)
        logger.debug("Analyzing intake documents")
        # analyze_intake_documents likely sync? Let's wrap it
        intake_analysis = await run_in_threadpool(analyze_intake_documents, case_id, supabase)
        logger.debug("Intake analysis complete", extra={"message": intake_analysis.get("message", "N/A")})

        # 5. Publish completion
        progress_data = {"type": "completed", "message": "Case creation completed successfully!", "phase": "complete", "percent": 100, "status": "completed"}
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Case creation completed successfully!",
            phase="complete",
            percent=100,
            sub_step="done",
            status="completed",
            data={"import_status": import_result, "intake_analysis": intake_analysis, "success": True},
        )
        await save_progress_to_db(progress_data)
        # #region agent log
        _debug_log_bg("bg_task_complete", {"import_id": import_id, "case_id": case_id}, "H2,H4")
        # #endregion

    except Exception as e:
        logger.exception("Error in background import", extra={"error": str(e)})
        progress_data = {"type": "error", "message": f"Import failed: {str(e)}", "phase": "error", "percent": 0, "status": "error"}
        await progress_manager.publish_progress(
            channel_id=import_id,
            message=f"Import failed: {str(e)}",
            phase="error",
            percent=0,
            status="error",
            error=str(e),
        )
        await save_progress_to_db(progress_data)
        # #region agent log
        _debug_log_bg("bg_task_error", {"import_id": import_id, "error": str(e)}, "H4")
        # #endregion


@router.post("/create-from-clio", response_model=CreateFromClioResponse)
async def create_case_from_clio(
    request: CreateFromClioRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_supabase_client),  # noqa: B008
    clio_client: ClioClient = Depends(get_clio_client_for_user),
    progress_manager: ProgressManager = Depends(get_progress_manager),
):
    """Create a new case from Clio matter with optional auto-import.

    This endpoint:
    1. Fetches matter details from Clio
    2. Creates a new case with matter data
    3. Optionally imports all documents (auto_import=True)
    4. Analyzes intake document candidates
    5. Returns complete status with error handling

    Args:
    ----
        request: Matter ID and auto_import flag
        background_tasks: FastAPI background tasks handler
        user: Current authenticated user
        supabase: Supabase client
        clio_client: Authenticated Clio client
        progress_manager: ProgressManager instance for SSE progress updates

    Returns:
    -------
        Case details with import status and intake analysis

    """
    import uuid

    case_id = None
    import_id = str(uuid.uuid4())  # Generate unique ID for progress tracking

    try:
        # Initialize progress channel immediately
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Starting case creation from Clio matter...",
            phase="initialization",
            percent=5,
            sub_step="start",
        )

        logger.debug(
            "Creating case from Clio",
            extra={
                "user_id": user["id"],
                "matter_id": request.matter_id,
                "auto_import": request.auto_import,
                "import_id": import_id,
            },
        )

        # 1. Fetch matter details
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Fetching matter details from Clio...",
            phase="fetch_matter",
            percent=10,
            sub_step="details",
        )
        logger.debug("Fetching matter details from Clio")
        # Run blocking call in threadpool
        matter = await run_in_threadpool(clio_client.get_matter, request.matter_id)
        logger.debug(
            "Matter fetched",
            extra={"display_number": matter.display_number, "client_name": matter.client_name},
        )

        # 2. Create case
        await progress_manager.publish_progress(
            channel_id=import_id,
            message=f"Creating case for {matter.client_name}...",
            phase="create_case",
            percent=20,
            sub_step="database",
        )
        logger.debug("Creating case")

        # Get jurisdiction (from request or user default)
        jurisdiction = request.jurisdiction
        if not jurisdiction:
            try:
                profile_resp = (
                    supabase.table("profiles")
                    .select("default_jurisdiction")
                    .eq("id", user["id"])
                    .single()
                    .execute()
                )
                if profile_resp.data:
                    jurisdiction = profile_resp.data.get("default_jurisdiction", "Florida")
                else:
                    jurisdiction = "Florida"
            except Exception:
                jurisdiction = "Florida"

        clio_data = {
            "matter_id": request.matter_id,
            "display_number": matter.display_number,
            "client_name": matter.client_name,
            "description": matter.description,
            "practice_area": matter.practice_area,
            "status": matter.status,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "import_id": import_id,  # Store import_id for reference
        }

        case_data = {
            "user_id": user["id"],
            "client_name": matter.client_name,
            "description": matter.description or f"Case for {matter.client_name}",
            "reference_number": matter.display_number,
            "clio_matter_id": str(request.matter_id),
            "created_via_clio": True,  # Mark as created via Clio
            "jurisdiction": jurisdiction,
            "status": "pending",
            "clio_matter_data": clio_data,
        }

        # Run DB insert in threadpool
        case_result = await run_in_threadpool(lambda: supabase.table("cases").insert(case_data).execute())
        case_id = case_result.data[0]["id"]
        logger.info("Case created", extra={"case_id": case_id})

        # 3. Trigger background import if auto_import
        if request.auto_import:
            logger.debug("Scheduling background import")
            background_tasks.add_task(
                process_clio_import_background,
                matter_id=request.matter_id,
                case_id=case_id,
                user=user,
                clio_client=clio_client,
                supabase=supabase,
                progress_manager=progress_manager,
                import_id=import_id,
                case_clio_data=clio_data,
            )
        else:
            # If no auto import, verify intake manually or just finish
            # For consistency, we should probably just mark as complete
            await progress_manager.publish_progress(
                channel_id=import_id,
                message="Case created successfully (no import requested)!",
                phase="complete",
                percent=100,
                sub_step="done",
                status="completed",
                data={"success": True},
            )

        # 5. Return immediate response
        # Note: import_status and intake_analysis will be None initially
        # The frontend will receive them via SSE 'complete' event
        return CreateFromClioResponse(
            success=True,
            case_id=case_id,
            case=case_result.data[0],
            import_status=None,
            intake_analysis=None,
            case_created=True,
            import_failed=False,
            import_id=import_id,  # Return import_id for SSE tracking
        )

    except ClioAuthError as e:
        # Case not created yet
        error_msg = f"Clio authentication error: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=401, detail=error_msg) from e

    except ClioAPIError as e:
        # Case not created yet
        error_msg = f"Clio API error: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg) from e

    except Exception as e:
        error_msg = str(e)
        logger.exception("Exception in create_case_from_clio", extra={"error": error_msg})

        # Partial success handling
        if case_id:
            logger.warning("Case was created but import failed", extra={"case_id": case_id})
            return CreateFromClioResponse(
                success=False,
                case_id=case_id,
                case={"id": case_id},
                import_status={"success": False, "error": error_msg},
                intake_analysis=None,
                error=error_msg,
                case_created=True,
                import_failed=True,
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating case: {error_msg}"
        ) from e


@router.post("/{case_id}/set-intake-form")
async def set_intake_form(
    case_id: str,
    request: dict,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Set a specific document as the primary intake form for a case.

    This endpoint:
    1. Verifies case ownership
    2. Clears is_intake_form from all other documents
    3. Sets is_intake_form=true for the specified document
    4. Keeps other intake candidates marked as is_intake_candidate=true

    Args:
    ----
        case_id: Case ID
        request: Dict with 'document_id' field
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Success message

    """
    try:
        document_id = request.get("document_id")
        if not document_id:
            raise HTTPException(status_code=400, detail="document_id is required")

        logger.debug(
            "Setting intake form",
            extra={"case_id": case_id, "document_id": document_id, "user_id": user["id"]},
        )

        # 1. Verify case ownership
        case_result = (
            supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_result.data:
            raise HTTPException(status_code=404, detail="Case not found")

        # 2. Get all documents for this case
        docs_result = supabase.table("documents").select("*").eq("case_id", case_id).execute()

        if not docs_result.data:
            raise HTTPException(status_code=404, detail="No documents found")

        # 3. Find the target document
        target_doc = None
        for doc in docs_result.data:
            if doc["id"] == document_id:
                target_doc = doc
                break

        if not target_doc:
            raise HTTPException(status_code=404, detail="Document not found")

        logger.debug("Target document found", extra={"file_name": target_doc["file_name"]})

        # 4. Update all documents
        for doc in docs_result.data:
            metadata = doc.get("metadata", {})

            if doc["id"] == document_id:
                # This is the new primary intake
                metadata["is_intake_form"] = True
                metadata["is_intake_candidate"] = False
                logger.info("Set as primary intake", extra={"file_name": doc["file_name"]})
            elif "intake" in doc.get("file_name", "").lower():
                # Other intake candidates
                metadata["is_intake_form"] = False
                metadata["is_intake_candidate"] = True
                logger.debug("Set as alternate intake", extra={"file_name": doc["file_name"]})
            else:
                # Regular documents
                metadata["is_intake_form"] = False
                metadata["is_intake_candidate"] = False

            # Update document
            supabase.table("documents").update({"metadata": metadata}).eq("id", doc["id"]).execute()

        return {"success": True, "message": f"Intake form updated to: {target_doc['file_name']}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating intake form", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error updating intake form: {str(e)}"
        ) from e


@router.post("/{case_id}/change-matter")
async def change_clio_matter(
    case_id: str,
    request: CreateFromClioRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_supabase_client),  # noqa: B008
    clio_client: ClioClient = Depends(get_clio_client_for_user),
):
    """Change the linked Clio matter for a case.

    This endpoint:
    1. Verifies case ownership
    2. Deletes old Clio documents from storage and database
    3. Fetches new matter details
    4. Imports documents from new matter
    5. Updates case with new matter data

    Args:
    ----
        case_id: Case ID
        request: New matter ID
        user: Current authenticated user
        supabase: Supabase client
        clio_client: Authenticated Clio client

    Returns:
    -------
        Updated case with new import status

    """
    try:
        logger.debug(
            "Changing Clio matter",
            extra={"case_id": case_id, "new_matter_id": request.matter_id, "user_id": user["id"]},
        )

        # 1. Verify case ownership
        case_result = (
            supabase.table("cases").select("*").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_result.data:
            raise HTTPException(status_code=404, detail="Case not found")

        old_case = case_result.data[0]
        old_matter_id = old_case.get("clio_matter_id")

        logger.debug("Old matter ID", extra={"old_matter_id": old_matter_id})

        # 2. Delete old Clio documents
        if old_matter_id:
            logger.debug("Deleting old Clio documents")
            docs_result = (
                supabase.table("documents")
                .select("id, storage_path, metadata")
                .eq("case_id", case_id)
                .execute()
            )

            clio_documents = [
                doc for doc in docs_result.data if doc.get("metadata", {}).get("clio_source") is True
            ]

            logger.debug("Found Clio documents to delete", extra={"count": len(clio_documents)})

            # Delete from storage
            if clio_documents:
                storage_paths = [doc["storage_path"] for doc in clio_documents]
                try:
                    supabase.storage.from_("documents").remove(storage_paths)
                    logger.debug("Deleted from storage")
                except Exception as storage_error:
                    logger.warning("Storage deletion warning", extra={"error": str(storage_error)})

            # Delete from database
            if clio_documents:
                doc_ids = [doc["id"] for doc in clio_documents]
                for doc_id in doc_ids:
                    supabase.table("documents").delete().eq("id", doc_id).execute()
                logger.debug("Deleted from database")

        # 3. Fetch new matter details
        logger.debug("Fetching new matter details from Clio")
        matter = clio_client.get_matter(request.matter_id)
        logger.debug(
            "New matter fetched",
            extra={"display_number": matter.display_number, "client_name": matter.client_name},
        )

        # 4. Update case with new matter data (before import)
        logger.debug("Updating case with new matter data")
        update_data = {
            "client_name": matter.client_name,
            "description": matter.description or f"Case for {matter.client_name}",
            "reference_number": matter.display_number,
            "clio_matter_id": str(request.matter_id),
            "clio_matter_data": {
                "matter_id": request.matter_id,
                "display_number": matter.display_number,
                "client_name": matter.client_name,
                "description": matter.description,
                "practice_area": matter.practice_area,
                "status": matter.status,
                "imported_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        supabase.table("cases").update(update_data).eq("id", case_id).execute()
        logger.info("Case updated", extra={"case_id": case_id})

        # 5. Import documents from new matter
        logger.debug("Starting document import from new matter")
        import_result = await import_clio_documents_helper(
            request.matter_id, case_id, user, clio_client, supabase
        )
        logger.info("Import completed", extra={"total_imported": import_result.get("total_imported", 0)})

        # Update case with import counts
        supabase.table("cases").update(
            {
                "clio_matter_data": {
                    **update_data["clio_matter_data"],
                    "communications_count": import_result.get("communications_count", 0),
                    "notes_count": import_result.get("notes_count", 0),
                    "documents_count": import_result.get("documents_count", 0),
                }
            }
        ).eq("id", case_id).execute()

        # 6. Analyze intake candidates
        logger.debug("Analyzing intake documents")
        intake_analysis = analyze_intake_documents(case_id, supabase)

        # 7. Get updated case
        updated_case = supabase.table("cases").select("*").eq("id", case_id).execute()

        return {
            "success": True,
            "message": "Matter changed successfully",
            "case": updated_case.data[0],
            "import_status": import_result,
            "intake_analysis": intake_analysis,
        }

    except HTTPException:
        raise
    except ClioAuthError as e:
        raise HTTPException(status_code=401, detail=f"Clio authentication error: {str(e)}") from e
    except ClioAPIError as e:
        raise HTTPException(status_code=500, detail=f"Clio API error: {str(e)}") from e
    except Exception as e:
        logger.exception("Error changing matter", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error changing matter: {str(e)}"
        ) from e
