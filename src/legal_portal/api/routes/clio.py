"""Clio Integration API Routes.

Handles OAuth flow, matter search, and data import from Clio.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from legal_portal.api.dependencies import get_current_user, get_supabase_client
from legal_portal.api.services.clio_auth_service import ClioAuthService
from legal_portal.api.services.clio_client import (
    ClioAPIError,
    ClioAuthError,
    ClioClient,
)
from legal_portal.api.utils.content_extractor import DocumentProcessor as ContentExtractor
from legal_portal.core.data_models import DocumentStatus
from legal_portal.core.document_processor import DocumentProcessor, ValidationError
from legal_portal.services.progress_manager import ProgressManager
from supabase import Client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clio", tags=["clio"])


# ===== Request/Response Models =====
class ClioAuthResponse(BaseModel):
    """Response after successful Clio authentication."""

    success: bool
    message: str
    connected: bool


class ClioConnectionStatus(BaseModel):
    """Clio connection status for current user."""

    connected: bool
    clio_user_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class ClioMatterResponse(BaseModel):
    """Clio matter search result."""

    id: int
    display_number: str
    description: Optional[str]
    client_name: str
    practice_area: Optional[str]
    status: str
    open_date: Optional[datetime]


class ClioImportRequest(BaseModel):
    """Request to import Clio data."""

    matter_id: int
    case_id: str


class ClioImportResponse(BaseModel):
    """Response after Clio data import."""

    success: bool
    message: str
    communications_count: int
    notes_count: int
    documents_count: int
    import_id: Optional[str] = None


# ===== OAuth Flow =====


def get_clio_redirect_uri(request: Request) -> str:
    """Get consistent Clio redirect URI.

    Uses CLIO_PRODUCTION_URL if set (recommended for production),
    otherwise falls back to dynamic URL detection.

    This ensures all OAuth flows use the same redirect URI that's
    registered in Clio's developer console.
    """
    import os

    # First priority: explicit production URL (recommended)
    production_url = os.getenv("CLIO_PRODUCTION_URL")
    if production_url:
        # Ensure no trailing slash and append callback path
        production_url = production_url.rstrip("/")
        return f"{production_url}/api/clio/callback"

    # Second priority: CLIO_REDIRECT_URI environment variable
    explicit_redirect = os.getenv("CLIO_REDIRECT_URI")
    if explicit_redirect:
        return explicit_redirect

    # Fallback: dynamic detection (may cause issues with preview deployments)
    host = request.headers.get("host", "127.0.0.1:8000")
    if "localhost" in host:
        host = host.replace("localhost", "127.0.0.1")

    protocol = "https" if "vercel" in host or request.headers.get("x-forwarded-proto") == "https" else "http"
    return f"{protocol}://{host}/api/clio/callback"


@router.get("/authorize")
async def authorize_clio(
    request: Request,
    token: str = Query(..., description="User session token"),
    supabase: Client = Depends(get_supabase_client),
):
    """Initiate Clio OAuth flow.

    Redirects user to Clio's authorization page.
    Note: Uses query param for auth since this is a direct browser navigation.
    """
    try:
        # Verify the token and get user
        response = supabase.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(status_code=401, detail="Invalid authentication token")

        user_id = response.user.id

        # Get consistent redirect URI
        redirect_uri = get_clio_redirect_uri(request)

        # Initialize auth service with the redirect URI
        auth_service = ClioAuthService(redirect_uri=redirect_uri)

        # Generate state with user_id for verification
        state = f"user:{user_id}"

        # Get authorization URL
        auth_url = auth_service.get_authorization_url(state=state)

        # Redirect to Clio
        return RedirectResponse(url=auth_url)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate OAuth: {str(e)}") from e


@router.get("/callback")
async def clio_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    supabase: Client = Depends(get_supabase_client),
):
    """Handle Clio OAuth callback.

    Exchanges code for access token and stores in database.
    """
    try:
        # Extract user_id from state
        if not state.startswith("user:"):
            raise HTTPException(status_code=400, detail="Invalid state parameter")

        user_id = state.split("user:")[1]

        # Get the same redirect URI used in /authorize
        # This is critical - Clio requires the redirect_uri to match exactly
        redirect_uri = get_clio_redirect_uri(request)

        # Exchange code for tokens using the same redirect URI
        auth_service = ClioAuthService(redirect_uri=redirect_uri)
        tokens = auth_service.handle_oauth_callback(code)

        # Store tokens in Supabase
        token_data = {
            "user_id": user_id,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_at": tokens["expires_at"].isoformat(),
            "token_type": tokens["token_type"],
        }

        # Upsert (insert or update)
        result = supabase.table("integrations_clio").upsert(token_data, on_conflict="user_id").execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to store tokens")

        # Determine frontend URL - use production URL for consistency
        import os
        from urllib.parse import quote

        # Priority: CLIO_PRODUCTION_URL > FRONTEND_URL > fallback
        production_url = os.getenv("CLIO_PRODUCTION_URL")
        if production_url:
            frontend_url = production_url.rstrip("/")
        else:
            frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")

        # Redirect to frontend with success message
        redirect_url = f"{frontend_url}/app/cases?clio_connected=true"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        # Redirect to frontend with error
        import os
        from urllib.parse import quote

        # Priority: CLIO_PRODUCTION_URL > FRONTEND_URL > fallback
        production_url = os.getenv("CLIO_PRODUCTION_URL")
        if production_url:
            frontend_url = production_url.rstrip("/")
        else:
            frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")

        error_message = quote(str(e))
        redirect_url = f"{frontend_url}/app/cases?clio_error={error_message}"
        return RedirectResponse(url=redirect_url)


@router.get("/status", response_model=ClioConnectionStatus)
async def get_clio_status(
    user=Depends(get_current_user),  # noqa: B008
    supabase: Client = Depends(get_supabase_client),  # noqa: B008
):
    """Get Clio connection status for current user."""
    try:
        # Query integrations table
        result = supabase.table("integrations_clio").select("*").eq("user_id", user["id"]).execute()

        if not result.data:
            return ClioConnectionStatus(connected=False)

        integration = result.data[0]
        expires_at_str = integration["expires_at"]

        # Parse the datetime and ensure it's timezone-aware
        from datetime import timezone

        if isinstance(expires_at_str, str):
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        else:
            expires_at = expires_at_str

        # Ensure expires_at is timezone-aware (UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Check if token is expired (compare with current UTC time)
        now = datetime.now(timezone.utc)
        is_expired = now >= expires_at

        return ClioConnectionStatus(
            connected=not is_expired,
            clio_user_id=integration.get("clio_user_id"),
            expires_at=expires_at,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}") from e


@router.delete("/disconnect")
async def disconnect_clio(
    user=Depends(get_current_user),  # noqa: B008
    supabase: Client = Depends(get_supabase_client),
):
    """Disconnect Clio integration for current user."""
    try:
        supabase.table("integrations_clio").delete().eq("user_id", user["id"]).execute()

        return {"success": True, "message": "Clio integration disconnected"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to disconnect: {str(e)}") from e


# ===== Matter Search =====
async def get_clio_client(
    user=Depends(get_current_user),  # noqa: B008
    supabase: Client = Depends(get_supabase_client),
) -> ClioClient:
    """Dependency to get authenticated Clio client."""
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
        from datetime import timezone

        if isinstance(expires_at_str, str):
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        else:
            expires_at = expires_at_str

        # Ensure expires_at is timezone-aware (UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Check if token needs refresh (compare with current UTC time)
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


@router.get("/search-matters", response_model=List[ClioMatterResponse])
async def search_clio_matters(
    query: str = Query(..., min_length=3),
    limit: int = Query(20, ge=1, le=50),
    clio_client: ClioClient = Depends(get_clio_client),
):
    """Search Clio matters by client name or matter number."""
    try:
        matters = clio_client.search_matters(query, limit)

        return [
            ClioMatterResponse(
                id=matter.id,
                display_number=matter.display_number,
                description=matter.description,
                client_name=matter.client_name,
                practice_area=matter.practice_area,
                status=matter.status,
                open_date=matter.open_date,
            )
            for matter in matters
        ]

    except ClioAuthError as e:
        raise HTTPException(status_code=401, detail=f"Clio authentication error: {str(e)}") from e
    except ClioAPIError as e:
        raise HTTPException(status_code=500, detail=f"Clio API error: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


# ===== Data Import =====


async def save_import_progress_to_db(
    supabase: Client,
    case_id: str,
    import_id: str,
    progress_data: dict,
) -> None:
    """Save import progress to database for cross-instance polling support on Vercel."""
    try:
        import_progress = {
            "import_id": import_id,
            "progress": progress_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        supabase.table("cases").update({"import_progress": import_progress}).eq("id", case_id).execute()
    except Exception as e:
        # Don't fail the import if progress persistence fails
        logger.warning(f"Failed to persist import progress to DB: {e}")


@router.post("/import", response_model=ClioImportResponse)
async def import_clio_data(
    import_request: ClioImportRequest,
    user=Depends(get_current_user),  # noqa: B008
    clio_client: ClioClient = Depends(get_clio_client),  # noqa: B008
    supabase: Client = Depends(get_supabase_client),  # noqa: B008
):
    """Import communications, notes, and documents from a Clio matter."""
    # Generate unique import ID for SSE streaming
    import_id = f"clio_import_{str(uuid.uuid4())}"
    progress_manager = ProgressManager.get_instance()
    await progress_manager.create_channel(import_id)

    # Store case_id for progress persistence
    case_id = import_request.case_id

    async def publish_and_persist(message: str, phase: str, percent: int, **kwargs):
        """Publish progress to in-memory manager AND persist to database."""
        progress_data = {
            "type": kwargs.get("status", "progress"),
            "message": message,
            "phase": phase,
            "percent": percent,
            **{k: v for k, v in kwargs.items() if k != "status"},
        }
        await progress_manager.publish_progress(
            channel_id=import_id, message=message, phase=phase, percent=percent, **kwargs
        )
        await save_import_progress_to_db(supabase, case_id, import_id, progress_data)

    try:
        matter_id = import_request.matter_id

        await publish_and_persist("Starting Clio import...", "initialization", 0)

        # Fetch user profile for blacklist
        profile_response = supabase.table("profiles").select("ai_preferences").eq("id", user["id"]).execute()
        blacklist = []
        if profile_response.data and profile_response.data[0].get("ai_preferences"):
            blacklist = profile_response.data[0]["ai_preferences"].get("blacklisted_documents", [])
        
        logger.info(f"Blacklist loaded for user {user['id']}: {blacklist} ({len(blacklist)} items)")

        # Verify case belongs to user
        case_result = (
            supabase.table("cases").select("*").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_result.data:
            raise HTTPException(status_code=404, detail="Case not found")

        await publish_and_persist("Fetching matter details from Clio...", "fetch_matter", 5)

        # Fetch full matter details first
        matter = clio_client.get_matter(matter_id)

        await publish_and_persist("Fetching communications...", "fetch_communications", 10)

        # Import communications
        communications = clio_client.get_communications(matter_id, limit=100)

        await publish_and_persist("Fetching notes...", "fetch_notes", 15)

        # Import notes
        notes = clio_client.get_notes(matter_id)

        await publish_and_persist("Fetching document list...", "fetch_documents", 20)

        # Import documents (metadata only)
        documents = clio_client.get_documents(matter_id)

        # Track compression statistics
        files_compressed = 0
        total_original_size = 0
        total_compressed_size = 0

        total_items = len(communications) + len(notes) + len(documents)
        items_processed = 0

        await publish_and_persist(
            f"Importing {len(communications)} communications...",
            "import_communications",
            25,
        )

        # Save communications as document entries
        for idx, comm in enumerate(communications, 1):
            try:
                # Check blacklist (prefix matching, normalized whitespace)
                if comm.subject and blacklist:
                    normalized_subject = ' '.join(comm.subject.lower().split())
                    is_blacklisted = any(
                        normalized_subject.startswith(' '.join(bl.lower().split())) 
                        for bl in blacklist
                    )
                    if is_blacklisted:
                        logger.info(f"Skipping blacklisted communication (prefix match): {comm.subject}")
                        items_processed += 1
                        continue

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
                items_processed += 1

                if idx % 5 == 0:  # Update every 5 items
                    progress_pct = 25 + int((items_processed / total_items) * 25)
                    await publish_and_persist(
                        f"Imported communication {idx}/{len(communications)}",
                        "import_communications",
                        progress_pct,
                        current_doc={
                            "name": comm.subject[:50] if comm.subject else "Untitled",
                            "index": idx,
                            "total": len(communications),
                        },
                    )
            except Exception as e:
                logger.warning("Failed to save communication", extra={"comm_id": comm.id, "error": str(e)})

        await publish_and_persist(f"Importing {len(notes)} notes...", "import_notes", 30)

        # Save notes as document entries
        for idx, note in enumerate(notes, 1):
            try:
                note_subject = note.get("subject", "No Subject")
                
                # Check blacklist (prefix matching, normalized whitespace)
                if blacklist:
                    normalized_note = ' '.join(note_subject.lower().split())
                    is_blacklisted = any(
                        normalized_note.startswith(' '.join(bl.lower().split())) 
                        for bl in blacklist
                    )
                    if is_blacklisted:
                        logger.info(f"Skipping blacklisted note (prefix match): {note_subject}")
                        items_processed += 1
                        continue

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
                items_processed += 1

                if idx % 5 == 0:  # Update every 5 items
                    progress_pct = 30 + int((items_processed / total_items) * 20)
                    await publish_and_persist(
                        f"Imported note {idx}/{len(notes)}",
                        "import_notes",
                        progress_pct,
                        current_doc={"name": note_subject[:50], "index": idx, "total": len(notes)},
                    )
            except Exception as e:
                logger.warning(
                    "Failed to save note", extra={"note_id": note.get("id", "unknown"), "error": str(e)}
                )

        await publish_and_persist(
            f"Downloading and processing {len(documents)} documents...",
            "import_documents",
            50,
        )

        # Download and process document files (these will appear in the documents list)
        for idx, doc in enumerate(documents, 1):
            try:
                doc_id = doc["id"]
                doc_name = doc.get("name", "Untitled Document")
                doc_url = doc.get("latest_document_version", {}).get("url")

                logger.debug("Processing Clio document", extra={"doc_name": doc_name, "doc_id": doc_id})

                # Check blacklist BEFORE downloading (prefix matching, case-insensitive, whitespace-normalized)
                if blacklist:
                    # Normalize whitespace: replace multiple spaces with single space, trim
                    normalized_doc_name = ' '.join(doc_name.lower().split())
                    is_blacklisted = any(
                        normalized_doc_name.startswith(' '.join(bl.lower().split())) 
                        for bl in blacklist
                    )
                    if is_blacklisted:
                        logger.info(f"SKIPPING blacklisted document (prefix match): '{doc_name}'")
                        items_processed += 1
                        continue

                progress_pct = 50 + int((idx / len(documents)) * 40)
                await publish_and_persist(
                    f"Processing document {idx}/{len(documents)}: {doc_name[:50]}",
                    "import_documents",
                    progress_pct,
                    current_doc={"name": doc_name[:50], "index": idx, "total": len(documents)},
                    sub_step="Downloading from Clio...",
                )

                # Skip if no download URL
                if not doc_url:
                    logger.debug("No download URL, saving metadata only", extra={"doc_id": doc_id})
                    doc_data = {
                        "case_id": case_id,
                        "file_name": doc_name,
                        "file_type": doc.get("content_type") or "application/octet-stream",
                        "file_size": doc.get("size", 0),
                        "storage_path": None,  # Set to None instead of fake path
                        "status": "download_failed",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_filename": doc_name,
                            "error": "No download URL provided by Clio",
                            "error_type": "CLIO_NO_URL",
                        },
                    }
                    supabase.table("documents").insert(doc_data).execute()
                    continue

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

                # Download file from Clio (just download, no processing yet)
                logger.debug("Downloading from Clio", extra={"doc_id": doc_id})
                file_content, content_type = ContentExtractor.download_file(doc_url, access_token)
                original_size = len(file_content)
                logger.debug("Downloaded file", extra={"size_mb": f"{original_size / (1024 * 1024):.2f}"})

                await publish_and_persist(
                    f"Processing document {idx}/{len(documents)}: {doc_name[:50]}",
                    "import_documents",
                    progress_pct,
                    current_doc={"name": doc_name[:50], "index": idx, "total": len(documents)},
                    sub_step="Validating and compressing...",
                )

                # Check if this is an intake form
                is_intake = "intake" in doc_name.lower()

                # Use unified processor for validation, compression, and upload
                logger.debug("Processing with unified validator", extra={"doc_name": doc_name})
                processor = DocumentProcessor()

                try:
                    doc_record = await processor.process_and_upload(
                        file_content=file_content,
                        filename=doc_name,
                        user_id=user["id"],
                        case_id=case_id,
                        supabase_client=supabase,
                        is_intake_form=is_intake,
                        content_type=content_type,
                        blacklist=blacklist,
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

                    # Add Clio-specific metadata
                    doc_record["metadata"].update(
                        {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_url": doc_url,
                            "clio_filename": doc_name,
                        }
                    )

                    # Insert document record
                    supabase.table("documents").insert(doc_record).execute()
                    logger.debug(
                        "Document saved successfully",
                        extra={"doc_name": doc_name, "is_intake": is_intake},
                    )

                    items_processed += 1

                except ValidationError as e:
                    logger.warning("Validation failed", extra={"error_code": e.error_code, "error": str(e)})
                    raise Exception(f"Validation failed: {str(e)}") from e

            except Exception as e:
                logger.warning(
                    "Failed to download/process document",
                    extra={"doc_id": doc.get("id", "unknown"), "error": str(e)},
                )
                # Still save metadata even if download fails
                try:
                    doc_data = {
                        "case_id": case_id,
                        "file_name": doc.get("name", "Untitled Document"),
                        "file_type": doc.get("content_type") or "application/octet-stream",
                        "file_size": doc.get("size", 0),
                        "storage_path": None,  # Set to None instead of fake path
                        "status": "download_failed",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc["id"],
                            "clio_url": doc.get("latest_document_version", {}).get("url"),
                            "clio_filename": doc.get("name"),
                            "error": str(e),
                            "error_type": "DOWNLOAD_FAILED",
                        },
                    }
                    supabase.table("documents").insert(doc_data).execute()
                except Exception:
                    pass  # Silently fail if we can't even save metadata

        # Prepare complete matter data for storage
        clio_matter_data = {
            "matter_id": matter_id,
            "display_number": matter.display_number,
            "client_name": matter.client_name,
            "description": matter.description,
            "practice_area": matter.practice_area,
            "status": matter.status,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "communications_count": len(communications),
            "notes_count": len(notes),
            "documents_count": len(documents),
        }

        # Store Clio matter ID and complete data in case
        supabase.table("cases").update(
            {
                "clio_matter_id": str(matter_id),
                "clio_matter_data": clio_matter_data,
            }
        ).eq("id", case_id).execute()

        # Update user's active matter
        supabase.table("integrations_clio").update({"clio_matter_id": str(matter_id)}).eq(
            "user_id", user["id"]
        ).execute()

        # Log compression summary if any files were compressed
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

        await publish_and_persist(
            "Import completed successfully!",
            "completed",
            100,
            status="completed",
        )

        return ClioImportResponse(
            success=True,
            message="Clio data imported successfully",
            communications_count=len(communications),
            notes_count=len(notes),
            documents_count=len(documents),
            import_id=import_id,
        )

    except ClioAuthError as e:
        await publish_and_persist(
            f"Authentication error: {str(e)}",
            "error",
            0,
            status="error",
            error=str(e),
        )
        raise HTTPException(status_code=401, detail=f"Clio authentication error: {str(e)}") from e
    except ClioAPIError as e:
        await publish_and_persist(
            f"API error: {str(e)}",
            "error",
            0,
            status="error",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Clio API error: {str(e)}") from e
    except Exception as e:
        await publish_and_persist(
            f"Import failed: {str(e)}",
            "error",
            0,
            status="error",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}") from e


@router.delete("/unlink/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_clio_matter(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase: Client = Depends(get_supabase_client),
):
    """Unlink Clio matter from case and delete all imported Clio documents.

    This removes the Clio matter association and deletes any documents that were
    imported from Clio (marked with clio_source=true in metadata).
    """
    try:
        # Verify case ownership
        case_result = (
            supabase.table("cases")
            .select("id, clio_matter_id")
            .eq("id", case_id)
            .eq("user_id", user["id"])
            .execute()
        )

        if not case_result.data:
            raise HTTPException(status_code=404, detail="Case not found")

        case = case_result.data[0]

        if not case.get("clio_matter_id"):
            raise HTTPException(status_code=400, detail="No Clio matter linked to this case")

        # Get all documents with clio_source metadata for this case
        docs_result = (
            supabase.table("documents").select("id, storage_path, metadata").eq("case_id", case_id).execute()
        )

        clio_documents = [
            doc for doc in docs_result.data if doc.get("metadata", {}).get("clio_source") is True
        ]

        # Delete Clio documents from storage
        if clio_documents:
            storage_paths = [doc["storage_path"] for doc in clio_documents]
            try:
                supabase.storage.from_("documents").remove(storage_paths)
            except Exception as storage_error:
                logger.warning("Storage deletion error (continuing)", extra={"error": str(storage_error)})

        # Delete Clio documents from database
        if clio_documents:
            doc_ids = [doc["id"] for doc in clio_documents]
            for doc_id in doc_ids:
                supabase.table("documents").delete().eq("id", doc_id).execute()

        # Clear Clio matter data from case
        supabase.table("cases").update({"clio_matter_id": None, "clio_matter_data": {}}).eq(
            "id", case_id
        ).execute()

        return None

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unlink Clio matter: {str(e)}") from e
