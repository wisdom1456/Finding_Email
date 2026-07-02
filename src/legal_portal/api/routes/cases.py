"""Case management endpoints."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from legal_portal.api.services.clio_client import ClioAPIError, ClioAuthError, ClioClient
from legal_portal.services.cases.clio_import_service import (
    analyze_intake_documents,
    get_clio_client_for_user as _get_clio_client_for_user_impl,
    import_clio_documents_helper,
    process_clio_import_background,
    run_content_hash_dedup,
)
from legal_portal.services.shared.progress_manager import ProgressManager, get_progress_manager

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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating case"
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
        logger.exception("Error fetching cases")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching cases"
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
        logger.exception("Error fetching case")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching case"
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
        logger.exception("Error updating case")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating case"
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting case"
        ) from e


# ===== Clio Integration Endpoints =====


async def get_clio_client_for_user(
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_supabase_client),  # noqa: B008
) -> ClioClient:
    """Get authenticated Clio client for user (FastAPI dependency wrapper)."""
    try:
        return await _get_clio_client_for_user_impl(user, supabase)
    except ClioAuthError as e:
        logger.exception("Clio authentication failed")
        raise HTTPException(status_code=401, detail="Clio authentication failed") from e
    except Exception as e:
        logger.exception("Failed to initialize Clio client")
        raise HTTPException(status_code=500, detail="Failed to initialize Clio client") from e


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
        import os
        is_vercel = os.getenv("VERCEL") is not None

        if request.auto_import:
            if is_vercel:
                # On Vercel, BackgroundTasks get killed when the response is sent.
                # The frontend will call /run-import which uses StreamingResponse
                # to keep the function alive for the full import duration.
                logger.info("Vercel detected — skipping BackgroundTask, frontend will call /run-import")
            else:
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating case"
        ) from e


class RunImportRequest(BaseModel):
    """Request body for run-import endpoint."""
    import_id: str


@router.post("/{case_id}/run-import")
async def run_import(
    case_id: str,
    request: RunImportRequest,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_supabase_client),  # noqa: B008
    clio_client: ClioClient = Depends(get_clio_client_for_user),
    progress_manager: ProgressManager = Depends(get_progress_manager),
):
    """Run Clio document import as a StreamingResponse.

    On Vercel, BackgroundTasks get killed when the response is sent.
    This endpoint runs the import inline and streams heartbeats to keep
    the Vercel function alive for the full import duration.

    The frontend fires-and-forgets this call after create-from-clio.
    Progress is persisted to DB so the SSE endpoint can relay it.
    """
    import asyncio
    import json as _json

    # Verify case ownership
    case_response = supabase.table("cases").select(
        "id, clio_matter_data, user_id"
    ).eq("id", case_id).eq("user_id", user["id"]).execute()

    if not case_response.data:
        raise HTTPException(status_code=404, detail="Case not found")

    case_data = case_response.data[0]
    clio_matter_data = case_data.get("clio_matter_data", {})
    matter_id = clio_matter_data.get("matter_id")

    if not matter_id:
        raise HTTPException(status_code=400, detail="Case has no Clio matter_id")

    import_id = request.import_id

    async def import_stream():
        """Run the import and yield heartbeats to keep Vercel alive."""
        try:
            yield f"data: {_json.dumps({'type': 'started', 'import_id': import_id})}\n\n"

            # Run the import as an asyncio task so we can yield heartbeats
            import_task = asyncio.create_task(
                process_clio_import_background(
                    matter_id=matter_id,
                    case_id=case_id,
                    user=user,
                    clio_client=clio_client,
                    supabase=supabase,
                    progress_manager=progress_manager,
                    import_id=import_id,
                    case_clio_data=clio_matter_data,
                )
            )

            heartbeat_count = 0
            while not import_task.done():
                await asyncio.sleep(2)
                heartbeat_count += 1
                if heartbeat_count >= 5:  # Every 10 seconds
                    yield f"data: {_json.dumps({'type': 'heartbeat'})}\n\n"
                    heartbeat_count = 0

            # Re-raise any exception from the task
            import_task.result()

            yield f"data: {_json.dumps({'type': 'completed'})}\n\n"
            logger.info(f"Streaming import completed for case {case_id}")

        except asyncio.CancelledError:
            logger.warning(f"Import stream cancelled for case {case_id}")
            yield f"data: {_json.dumps({'type': 'cancelled'})}\n\n"
        except Exception as e:
            logger.error(f"Import stream error for case {case_id}: {e}", exc_info=True)
            yield f"data: {_json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        import_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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

        # 2. Get all documents for this case (only fields needed for intake update)
        docs_result = supabase.table("documents").select("id, file_name, metadata").eq("case_id", case_id).execute()

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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating intake form"
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
        logger.exception("Clio authentication error")
        raise HTTPException(status_code=401, detail="Clio authentication error") from e
    except ClioAPIError as e:
        logger.exception("Clio API error")
        raise HTTPException(status_code=500, detail="Clio API error") from e
    except Exception as e:
        logger.exception("Error changing matter", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error changing matter"
        ) from e


@router.post("/{case_id}/dedup")
async def dedup_case_documents(
    case_id: str,
    user=Depends(get_current_user),  # noqa: B008
    supabase=Depends(get_supabase_client),  # noqa: B008
):
    """Run content-hash deduplication on all documents in a case.

    Downloads each document, computes SHA-256, and flags duplicates.
    """
    # Verify case ownership
    case_result = (
        supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
    )
    if not case_result.data:
        raise HTTPException(status_code=404, detail="Case not found")

    try:
        result = await run_in_threadpool(run_content_hash_dedup, case_id, supabase)
        return {
            "success": True,
            "duplicates_found": result["duplicates_found"],
            "documents_checked": result["documents_checked"],
            "message": (
                f"Found and flagged {result['duplicates_found']} duplicate documents"
                if result["duplicates_found"] > 0
                else "No duplicate documents found"
            ),
        }
    except Exception as e:
        logger.exception("Error running dedup", extra={"case_id": case_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error running dedup",
        ) from e
