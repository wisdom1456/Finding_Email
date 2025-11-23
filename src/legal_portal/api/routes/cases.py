"""Case management endpoints."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.services.clio_client import ClioAPIError, ClioAuthError, ClioClient
from legal_portal.api.utils.document_processor import DocumentProcessor as DocProc
from legal_portal.core.document_processor import DocumentProcessor, ValidationError
from legal_portal.services.progress_manager import ProgressManager, get_progress_manager
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

router = APIRouter()


class CaseCreate(BaseModel):
    """Request model for creating a new case."""

    client_name: str = Field(..., min_length=1, max_length=200)
    reference_number: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None


class CaseUpdate(BaseModel):
    """Request model for updating a case."""

    client_name: Optional[str] = Field(None, min_length=1, max_length=200)
    reference_number: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(pending|processing|completed|error)$")


class CaseResponse(BaseModel):
    """Response model for a case."""

    id: str
    user_id: str
    client_name: str
    reference_number: Optional[str]
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    clio_matter_id: Optional[str] = None
    created_via_clio: Optional[bool] = False


class CreateFromClioRequest(BaseModel):
    """Request model for creating a case from Clio matter."""

    matter_id: int = Field(..., description="Clio matter ID")
    auto_import: bool = Field(True, description="Auto-import documents")


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
        print("\n🔍 DEBUG create_case endpoint:")
        print(f"  - User ID from token: {user['id']}")
        print(f"  - User email: {user.get('email', 'N/A')}")
        print(f"  - Case data: client_name={case_data.client_name}")

        # Check what headers are actually being sent
        auth_header = supabase.postgrest.session.headers.get("Authorization", "NOT SET")
        print(
            f"  - Authorization header in client: {auth_header[:50]}..."
            if len(str(auth_header)) > 50
            else f"  - Authorization header: {auth_header}"
        )

        # Verify profile exists
        print(f"  - Checking if profile exists for user {user['id']}...")
        try:
            profile_check = supabase.table("profiles").select("id").eq("id", user["id"]).execute()
            print(f"  - Profile check result: {profile_check.data}")
        except Exception as pe:
            print(f"  - Profile check error: {pe}")

        print("  - Attempting to insert case...")
        response = (
            supabase.table("cases")
            .insert(
                {
                    "user_id": user["id"],
                    "client_name": case_data.client_name,
                    "reference_number": case_data.reference_number,
                    "description": case_data.description,
                    "status": "pending",
                }
            )
            .execute()
        )

        print(f"  - Insert successful! Case ID: {response.data[0]['id'] if response.data else 'unknown'}")

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create case"
            )

        return response.data[0]
    except Exception as e:
        print("\n❌ ERROR in create_case:")
        print(f"  - Exception type: {type(e).__name__}")
        print(f"  - Exception message: {str(e)}")
        print(f"  - Full exception: {repr(e)}")

        # Try to extract more details from Supabase errors
        if hasattr(e, "message"):
            print(f"  - Error message attr: {e.message}")
        if hasattr(e, "details"):
            print(f"  - Error details attr: {e.details}")
        if hasattr(e, "code"):
            print(f"  - Error code attr: {e.code}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating case: {str(e)}"
        )


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
    service_supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Delete a case and all associated documents from storage and database.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        user_supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client

    """
    try:
        print("\n🔍 DEBUG delete_case:")
        print(f"  - Case ID: {case_id}")
        print(f"  - User ID: {user['id']}")

        # Verify ownership
        existing = (
            user_supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not existing.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get all documents for this case to delete from storage
        print("  - Fetching documents for storage cleanup...")
        docs_response = (
            user_supabase.table("documents").select("storage_path").eq("case_id", case_id).execute()
        )

        # Delete files from storage (use service client)
        if docs_response.data:
            storage_paths = [doc["storage_path"] for doc in docs_response.data]
            print(f"  - Deleting {len(storage_paths)} files from storage...")
            try:
                service_supabase.storage.from_("documents").remove(storage_paths)
                print("  - ✅ Storage files deleted")
            except Exception as storage_error:
                print(f"  - ⚠️  Storage deletion error (continuing): {storage_error}")

        # Delete case from database (cascade deletes documents and analysis_results)
        print("  - Deleting case from database (cascade delete)...")
        user_supabase.table("cases").delete().eq("id", case_id).execute()

        print("  - ✅ Case deleted successfully")
        return None
    except HTTPException:
        raise
    except Exception as e:
        print("\n❌ ERROR in delete_case:")
        print(f"  - Exception: {str(e)}")
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
        progress_manager: Optional ProgressManager instance for SSE updates
        import_id: Unique ID for this import operation (for SSE tracking)

    """
    try:
        # Import communications
        print(f"\n🔍 Fetching communications for matter {matter_id}...")
        if progress_manager and import_id:
            await progress_manager.publish_progress(
                channel_id=import_id,
                message="Fetching communications from Clio...",
                phase="fetch_communications",
                sub_step="fetch",
                percent=5,
            )
        communications = await run_in_threadpool(clio_client.get_communications, matter_id, limit=100)
        print(f"  - Found {len(communications)} communications")

        # Import notes
        print(f"🔍 Fetching notes for matter {matter_id}...")
        if progress_manager and import_id:
            await progress_manager.publish_progress(
                channel_id=import_id,
                message="Fetching notes from Clio...",
                phase="fetch_notes",
                sub_step="fetch",
                percent=10,
            )
        notes = await run_in_threadpool(clio_client.get_notes, matter_id)
        print(f"  - Found {len(notes)} notes")

        # Import documents (metadata only)
        print(f"🔍 Fetching documents for matter {matter_id}...")
        if progress_manager and import_id:
            await progress_manager.publish_progress(
                channel_id=import_id,
                message="Fetching documents from Clio...",
                phase="fetch_documents",
                sub_step="fetch",
                percent=15,
            )
        documents = await run_in_threadpool(clio_client.get_documents, matter_id)
        print(f"  - Found {len(documents)} documents")

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
                if progress_manager and import_id:
                    subject = comm.subject or "Untitled Communication"
                    percent = 20 + int((idx / max(total_comms, 1)) * 5)
                    await progress_manager.publish_progress(
                        channel_id=import_id,
                        message=f"Processing communication {idx + 1} of {total_comms}",
                        phase="import_communications",
                        percent=percent,
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
                comm_success += 1
            except Exception as e:
                errors.append(f"Communication {comm.id}: {str(e)}")

        # Save notes as document entries
        total_notes = len(notes)
        for idx, note in enumerate(notes):
            try:
                if progress_manager and import_id:
                    note_subject = note.get("subject", "Untitled Note")
                    percent = 25 + int((idx / max(total_notes, 1)) * 5)
                    await progress_manager.publish_progress(
                        channel_id=import_id,
                        message=f"Processing note {idx + 1} of {total_notes}",
                        phase="import_notes",
                        percent=percent,
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
                note_success += 1
            except Exception as e:
                errors.append(f"Note {note.get('id', 'unknown')}: {str(e)}")

        # Download and process document files
        print(f"\n📄 Processing {len(documents)} Clio documents...")
        total_docs = len(documents)
        for idx, doc in enumerate(documents):
            try:
                if progress_manager and import_id:
                    doc_name = doc.get("name", "Untitled Document")
                    percent = 30 + int((idx / max(total_docs, 1)) * 60)
                    await progress_manager.publish_progress(
                        channel_id=import_id,
                        message=f"Downloading and processing document {idx + 1} of {total_docs}",
                        phase="import_documents",
                        percent=percent,
                        sub_step=doc_name[:50],
                        current_doc={"index": idx + 1, "total": total_docs, "name": doc_name},
                    )
                doc_id = doc["id"]
                doc_name = doc.get("name", "Untitled Document")

                print(f"  - Document: {doc_name} (ID: {doc_id})")

                # Clio doesn't provide download URLs in the documents list
                # We need to construct the download URL using the document ID
                # Format: /api/v4/documents/{id}/download.json
                doc_url = f"https://app.clio.com/api/v4/documents/{doc_id}/download.json"
                print(f"    Download URL: {doc_url}")

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
                # Run blocking download in threadpool
                file_content, content_type = await run_in_threadpool(
                    DocProc.download_file, doc_url, access_token
                )
                original_size = len(file_content)
                print(f"    Downloaded: {original_size / (1024 * 1024):.2f}MB")

                # Check if this is an intake form candidate
                is_intake_candidate = "intake" in doc_name.lower()

                # Use unified processor for validation, compression, and upload
                processor = DocumentProcessor()

                try:
                    doc_record = await processor.process_and_upload(
                        file_content=file_content,
                        filename=doc_name,
                        user_id=user["id"],
                        case_id=case_id,
                        supabase_client=supabase,
                        is_intake_form=is_intake_candidate,
                        content_type=content_type,
                    )

                    # Track compression statistics if compressed
                    if doc_record.get("metadata", {}).get("compression", {}).get("compressed"):
                        files_compressed += 1
                        comp_meta = doc_record["metadata"]["compression"]
                        total_original_size += comp_meta["original_size"]
                        total_compressed_size += comp_meta["compressed_size"]
                        print(
                            f"    Compressed: {comp_meta['original_size'] / (1024 * 1024):.2f}MB → "
                            f"{comp_meta['compressed_size'] / (1024 * 1024):.2f}MB"
                        )

                    # Add Clio-specific metadata
                    doc_record["metadata"].update(
                        {
                            "clio_source": True,
                            "clio_type": "document",
                            "clio_id": doc_id,
                            "clio_url": doc_url,
                            "clio_filename": doc_name,
                            "is_intake_candidate": is_intake_candidate,
                        }
                    )

                    # Insert document record
                    supabase.table("documents").insert(doc_record).execute()
                    doc_success += 1
                    print("    ✅ Successfully imported!")

                except ValidationError as e:
                    print(f"    ❌ Validation failed: {e.error_code} - {str(e)}")
                    raise Exception(f"Validation failed: {str(e)}") from e

            except Exception as e:
                error_msg = f"Document {doc.get('id', 'unknown')} ({doc.get('name', 'unknown')}): {str(e)}"
                errors.append(error_msg)
                print(f"    ❌ Error: {str(e)}")

        result = {
            "success": len(errors) == 0,
            "communications_count": comm_success,
            "notes_count": note_success,
            "documents_count": doc_success,
            "total_imported": comm_success + note_success + doc_success,
            "errors": errors if errors else None,
        }

        print("\n📊 Import Summary:")
        print(f"  - Communications: {comm_success}")
        print(f"  - Notes: {note_success}")
        print(f"  - Documents: {doc_success}")
        print(f"  - Total: {comm_success + note_success + doc_success}")
        if errors:
            print(f"  - Errors: {len(errors)}")
            for error in errors[:5]:  # Show first 5 errors
                print(f"    • {error}")

        # Show compression statistics if any files were compressed
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
        print("")  # Add blank line for readability

        # Post-processing: Prioritize intake forms
        print("\n🎯 Prioritizing intake forms...")
        intake_docs = supabase.table("documents").select("*").eq("case_id", case_id).execute()

        if intake_docs.data:
            intake_candidates = [
                doc for doc in intake_docs.data if doc.get("metadata", {}).get("is_intake_candidate") is True
            ]

            if len(intake_candidates) > 1:
                print(f"  - Found {len(intake_candidates)} intake candidates, prioritizing...")

                # Score each candidate
                scored = []
                for doc in intake_candidates:
                    score = analyze_intake_priority(doc)
                    scored.append((doc, score))
                    print(f"    • {doc['file_name']}: score={score}, size={doc['file_size']}")

                # Sort by score (highest first)
                scored.sort(key=lambda x: x[1], reverse=True)

                # Mark the best one as is_intake_form
                best_doc, best_score = scored[0]
                print(f"  - ✅ Best intake: {best_doc['file_name']} (score: {best_score})")

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
                    print(f"    • Alternate: {doc['file_name']} (score: {score})")

            elif len(intake_candidates) == 1:
                # Only one candidate, mark it as the intake form
                doc = intake_candidates[0]
                doc["metadata"]["is_intake_form"] = True
                doc["metadata"]["is_intake_candidate"] = False
                supabase.table("documents").update({"metadata": doc["metadata"]}).eq(
                    "id", doc["id"]
                ).execute()
                print(f"  - ✅ Single intake form: {doc['file_name']}")

        return result

    except Exception as e:
        print("\n❌ EXCEPTION in import_clio_documents_helper:")
        print(f"  - Error: {str(e)}")
        print(f"  - Type: {type(e).__name__}")
        import traceback

        traceback.print_exc()

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
    if file_size > 500000:  # > 500KB likely has content
        priority_score += 50
    elif file_size > 700000:  # > 700KB very likely filled
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
            message = f"✅ Best intake form auto-selected: {best_intake['filename']} (score: {best_intake['score']})"
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
    try:
        # 3. Import documents
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Starting document import from Clio...",
            phase="import_start",
            percent=30,
            sub_step="initialization",
        )

        print("  - Starting document import (background)...")
        import_result = await import_clio_documents_helper(
            matter_id, case_id, user, clio_client, supabase, progress_manager, import_id
        )
        print(f"  - Import completed: {import_result.get('total_imported', 0)} items")

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
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Analyzing intake documents...",
            phase="analyze_intake",
            percent=90,
            sub_step="identification",
        )
        print("  - Analyzing intake documents...")
        # analyze_intake_documents likely sync? Let's wrap it
        intake_analysis = await run_in_threadpool(analyze_intake_documents, case_id, supabase)
        print(f"  - Intake analysis: {intake_analysis.get('message', 'N/A')}")

        # 5. Publish completion
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Case creation completed successfully!",
            phase="complete",
            percent=100,
            sub_step="done",
            status="completed",
            data={"import_status": import_result, "intake_analysis": intake_analysis, "success": True},
        )

    except Exception as e:
        print(f"❌ Error in background import: {e}")
        await progress_manager.publish_progress(
            channel_id=import_id,
            message=f"Import failed: {str(e)}",
            phase="error",
            percent=0,
            status="error",
            error=str(e),
        )


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

        print("\n🔍 DEBUG create_case_from_clio:")
        print(f"  - User ID: {user['id']}")
        print(f"  - Matter ID: {request.matter_id}")
        print(f"  - Auto Import: {request.auto_import}")
        print(f"  - Import ID: {import_id}")

        # 1. Fetch matter details
        await progress_manager.publish_progress(
            channel_id=import_id,
            message="Fetching matter details from Clio...",
            phase="fetch_matter",
            percent=10,
            sub_step="details",
        )
        print("  - Fetching matter details from Clio...")
        # Run blocking call in threadpool
        matter = await run_in_threadpool(clio_client.get_matter, request.matter_id)
        print(f"  - Matter fetched: {matter.display_number} - {matter.client_name}")

        # 2. Create case
        await progress_manager.publish_progress(
            channel_id=import_id,
            message=f"Creating case for {matter.client_name}...",
            phase="create_case",
            percent=20,
            sub_step="database",
        )
        print("  - Creating case...")

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
            "status": "pending",
            "clio_matter_data": clio_data,
        }

        # Run DB insert in threadpool
        case_result = await run_in_threadpool(lambda: supabase.table("cases").insert(case_data).execute())
        case_id = case_result.data[0]["id"]
        print(f"  - ✅ Case created: {case_id}")

        # 3. Trigger background import if auto_import
        if request.auto_import:
            print("  - Scheduling background import...")
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
        print(f"  - ❌ {error_msg}")
        raise HTTPException(status_code=401, detail=error_msg) from e

    except ClioAPIError as e:
        # Case not created yet
        error_msg = f"Clio API error: {str(e)}"
        print(f"  - ❌ {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg) from e

    except Exception as e:
        error_msg = str(e)
        print(f"  - ❌ Exception: {error_msg}")

        # Partial success handling
        if case_id:
            print("  - Case was created but import failed")
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
        )


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

        print(f"\n🎯 Setting intake form for case {case_id}:")
        print(f"  - Document ID: {document_id}")
        print(f"  - User ID: {user['id']}")

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

        print(f"  - Target document: {target_doc['file_name']}")

        # 4. Update all documents
        for doc in docs_result.data:
            metadata = doc.get("metadata", {})

            if doc["id"] == document_id:
                # This is the new primary intake
                metadata["is_intake_form"] = True
                metadata["is_intake_candidate"] = False
                print(f"  - ✅ Set as primary: {doc['file_name']}")
            elif "intake" in doc.get("file_name", "").lower():
                # Other intake candidates
                metadata["is_intake_form"] = False
                metadata["is_intake_candidate"] = True
                print(f"  - Set as alternate: {doc['file_name']}")
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
        print(f"  - ❌ Exception: {str(e)}")
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
        print("\n🔍 DEBUG change_clio_matter:")
        print(f"  - Case ID: {case_id}")
        print(f"  - New Matter ID: {request.matter_id}")
        print(f"  - User ID: {user['id']}")

        # 1. Verify case ownership
        case_result = (
            supabase.table("cases").select("*").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_result.data:
            raise HTTPException(status_code=404, detail="Case not found")

        old_case = case_result.data[0]
        old_matter_id = old_case.get("clio_matter_id")

        print(f"  - Old matter ID: {old_matter_id}")

        # 2. Delete old Clio documents
        if old_matter_id:
            print("  - Deleting old Clio documents...")
            docs_result = (
                supabase.table("documents")
                .select("id, storage_path, metadata")
                .eq("case_id", case_id)
                .execute()
            )

            clio_documents = [
                doc for doc in docs_result.data if doc.get("metadata", {}).get("clio_source") is True
            ]

            print(f"  - Found {len(clio_documents)} Clio documents to delete")

            # Delete from storage
            if clio_documents:
                storage_paths = [doc["storage_path"] for doc in clio_documents]
                try:
                    supabase.storage.from_("documents").remove(storage_paths)
                    print("  - ✅ Deleted from storage")
                except Exception as storage_error:
                    print(f"  - ⚠️  Storage deletion warning: {storage_error}")

            # Delete from database
            if clio_documents:
                doc_ids = [doc["id"] for doc in clio_documents]
                for doc_id in doc_ids:
                    supabase.table("documents").delete().eq("id", doc_id).execute()
                print("  - ✅ Deleted from database")

        # 3. Fetch new matter details
        print("  - Fetching new matter details from Clio...")
        matter = clio_client.get_matter(request.matter_id)
        print(f"  - New matter fetched: {matter.display_number} - {matter.client_name}")

        # 4. Update case with new matter data (before import)
        print("  - Updating case with new matter data...")
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
        print("  - ✅ Case updated")

        # 5. Import documents from new matter
        print("  - Starting document import from new matter...")
        import_result = await import_clio_documents_helper(
            request.matter_id, case_id, user, clio_client, supabase
        )
        print(f"  - Import completed: {import_result.get('total_imported', 0)} items")

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
        print("  - Analyzing intake documents...")
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
        print(f"  - ❌ Exception: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error changing matter: {str(e)}"
        ) from e
