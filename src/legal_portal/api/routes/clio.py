"""Clio Integration API Routes.

Handles OAuth flow, matter search, and data import from Clio.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from legal_portal.api.dependencies import get_current_user, get_supabase_client
from legal_portal.api.services.clio_auth_service import ClioAuthService
from legal_portal.api.services.clio_client import (
    ClioAPIError,
    ClioAuthError,
    ClioClient,
)
from legal_portal.api.utils.document_processor import DocumentProcessor
from pydantic import BaseModel

from supabase import Client

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


# ===== OAuth Flow =====
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

        # Use 127.0.0.1 instead of localhost (Clio preference)
        host = request.headers.get("host", "127.0.0.1:8000")
        if "localhost" in host:
            host = host.replace("localhost", "127.0.0.1")

        protocol = (
            "https" if "vercel" in host or request.headers.get("x-forwarded-proto") == "https" else "http"
        )
        redirect_uri = f"{protocol}://{host}/api/clio/callback"

        # Initialize auth service with dynamic redirect
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

        # Exchange code for tokens
        auth_service = ClioAuthService()
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

        # Determine frontend URL from request or environment
        import os

        frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")

        # Redirect to frontend with success message
        redirect_url = f"{frontend_url}/app/cases?clio_connected=true"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        # Redirect to frontend with error
        import os

        frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
        error_message = str(e)
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
        raise HTTPException(status_code=401, detail=f"Clio authentication failed: {str(e)}")
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
        raise HTTPException(status_code=401, detail=f"Clio authentication error: {str(e)}")
    except ClioAPIError as e:
        raise HTTPException(status_code=500, detail=f"Clio API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


# ===== Data Import =====
@router.post("/import", response_model=ClioImportResponse)
async def import_clio_data(
    import_request: ClioImportRequest,
    user=Depends(get_current_user),  # noqa: B008
    clio_client: ClioClient = Depends(get_clio_client),  # noqa: B008
    supabase: Client = Depends(get_supabase_client),  # noqa: B008
):
    """Import communications, notes, and documents from a Clio matter."""
    try:
        matter_id = import_request.matter_id
        case_id = import_request.case_id

        # Verify case belongs to user
        case_result = (
            supabase.table("cases").select("*").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_result.data:
            raise HTTPException(status_code=404, detail="Case not found")

        # Fetch full matter details first
        matter = clio_client.get_matter(matter_id)

        # Import communications
        communications = clio_client.get_communications(matter_id, limit=100)

        # Import notes
        notes = clio_client.get_notes(matter_id)

        # Import documents (metadata only)
        documents = clio_client.get_documents(matter_id)

        # Track compression statistics
        files_compressed = 0
        total_original_size = 0
        total_compressed_size = 0

        # Save communications as document entries
        for comm in communications:
            try:
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
                    "status": "processed",
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
            except Exception as e:
                print(f"Warning: Failed to save communication {comm.id}: {e}")

        # Save notes as document entries
        for note in notes:
            try:
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
                    "status": "processed",
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
            except Exception as e:
                print(f"Warning: Failed to save note {note.get('id', 'unknown')}: {e}")

        # Download and process document files (these will appear in the documents list)
        for doc in documents:
            try:
                doc_id = doc["id"]
                doc_name = doc.get("name", "Untitled Document")
                doc_url = doc.get("latest_document_version", {}).get("url")

                print(f"Processing Clio document: {doc_name} (ID: {doc_id})")

                # Skip if no download URL
                if not doc_url:
                    print("  - No download URL, saving metadata only")
                    doc_data = {
                        "case_id": case_id,
                        "file_name": doc_name,
                        "file_type": doc.get("content_type") or "application/octet-stream",
                        "file_size": doc.get("size", 0),
                        "storage_path": f"clio/{case_id}/doc_{doc_id}",
                        "status": "uploaded",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_filename": doc_name,
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

                # Download and extract text from document (with automatic compression)
                print("  - Downloading from Clio...")
                (
                    file_content,
                    content_type,
                    extracted_text,
                    compression_meta,
                ) = DocumentProcessor.download_and_extract(doc_url, access_token, doc_name, compress=True)

                file_size = len(file_content)
                original_size = compression_meta.get("original_size", file_size)
                was_compressed = compression_meta.get("compressed", False)

                # Track compression statistics
                if was_compressed:
                    files_compressed += 1
                    total_original_size += original_size
                    total_compressed_size += file_size

                print(f"  - Downloaded: {original_size} bytes")
                if was_compressed:
                    compression_ratio = compression_meta.get("compression_ratio", 1.0)
                    reduction_pct = (1 - compression_ratio) * 100
                    print(
                        f"  - Compressed: {file_size} bytes ({reduction_pct:.1f}% reduction, "
                        f"method: {compression_meta.get('method', 'unknown')})"
                    )
                print(f"  - Content type: {content_type}")
                print(f"  - Text extracted: {bool(extracted_text)}")

                # Generate unique storage path
                file_extension = doc_name.split(".")[-1] if "." in doc_name else ""
                unique_filename = f"{uuid.uuid4()}.{file_extension}" if file_extension else str(uuid.uuid4())
                storage_path = f"{user['id']}/{case_id}/clio_{unique_filename}"

                # Upload to Supabase Storage
                print(f"  - Uploading to Supabase Storage: {storage_path}")
                supabase.storage.from_("documents").upload(
                    storage_path, file_content, {"content-type": content_type}
                )

                # Check if this is an intake form
                is_intake = "intake" in doc_name.lower()

                # Save document record with extracted text and compression metadata
                doc_data = {
                    "case_id": case_id,
                    "file_name": doc_name,
                    "file_type": content_type,
                    "file_size": file_size,
                    "storage_path": storage_path,
                    "status": "processed" if extracted_text else "uploaded",
                    "extracted_text": extracted_text,
                    "metadata": {
                        "clio_source": True,
                        "clio_type": "document",
                        "clio_id": doc_id,
                        "clio_url": doc_url,
                        "clio_filename": doc_name,
                        "is_intake_form": is_intake,
                        "compression": compression_meta,
                    },
                }
                supabase.table("documents").insert(doc_data).execute()
                print(f"  - ✅ Document saved successfully{' (INTAKE FORM)' if is_intake else ''}")

            except Exception as e:
                print(f"Warning: Failed to download/process document {doc.get('id', 'unknown')}: {e}")
                # Still save metadata even if download fails
                try:
                    doc_data = {
                        "case_id": case_id,
                        "file_name": doc.get("name", "Untitled Document"),
                        "file_type": doc.get("content_type") or "application/octet-stream",
                        "file_size": doc.get("size", 0),
                        "storage_path": f"clio/{case_id}/doc_{doc['id']}_failed",
                        "status": "error",
                        "extracted_text": None,
                        "metadata": {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc["id"],
                            "clio_url": doc.get("latest_document_version", {}).get("url"),
                            "clio_filename": doc.get("name"),
                            "error": str(e),
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
            print("\n💾 Compression Summary:")
            print(f"  - Files compressed: {files_compressed}")
            print(
                f"  - Size reduction: {total_original_size / 1024 / 1024:.1f}MB → "
                f"{total_compressed_size / 1024 / 1024:.1f}MB"
            )
            print(f"  - Space saved: {total_saved / 1024 / 1024:.1f}MB ({avg_reduction:.1f}% reduction)")

        return ClioImportResponse(
            success=True,
            message="Clio data imported successfully",
            communications_count=len(communications),
            notes_count=len(notes),
            documents_count=len(documents),
        )

    except ClioAuthError as e:
        raise HTTPException(status_code=401, detail=f"Clio authentication error: {str(e)}")
    except ClioAPIError as e:
        raise HTTPException(status_code=500, detail=f"Clio API error: {str(e)}")
    except Exception as e:
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
                print(f"Warning: Storage deletion error (continuing): {storage_error}")

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
