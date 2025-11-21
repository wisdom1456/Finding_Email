"""Document management endpoints.
"""

import mimetypes
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from legal_portal.api.dependencies import get_current_user, get_supabase_client, get_user_supabase_client
from pydantic import BaseModel

router = APIRouter()


class DocumentResponse(BaseModel):
    """Response model for a document."""

    id: str
    case_id: str
    file_name: str
    file_type: str
    file_size: int
    storage_path: str
    status: str
    created_at: datetime
    updated_at: datetime


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    case_id: str = Form(...),
    file: UploadFile = File(...),
    is_intake_form: bool = Form(False),
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Upload a document for a case.

    Args:
    ----
        case_id: ID of the case this document belongs to
        file: File to upload
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Created document metadata
    """
    try:
        print("\n🔍 DEBUG upload_document:")
        print(f"  - User ID: {user["id"]}")
        print(f"  - Case ID: {case_id}")
        print(f"  - Filename: {file.filename}")
        print(f"  - Content type: {file.content_type}")

        # Verify case ownership (use user client for RLS)
        print("  - Verifying case ownership...")
        case_response = (
            user_supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )
        print(f"  - Case found: {bool(case_response.data)}")

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        print(f"  - File size: {file_size} bytes")

        # Generate unique storage path
        file_extension = file.filename.split(".")[-1] if "." in file.filename else ""
        unique_filename = f"{uuid.uuid4()}.{file_extension}" if file_extension else str(uuid.uuid4())
        storage_path = f"{user["id"]}/{case_id}/{unique_filename}"
        print(f"  - Storage path: {storage_path}")

        # Upload to Supabase Storage (use service client to bypass storage RLS)
        print("  - Uploading to Supabase Storage with service client...")
        storage_response = service_supabase.storage.from_("documents").upload(
            storage_path,
            file_content,
            {
                "content-type": file.content_type
                or mimetypes.guess_type(file.filename)[0]
                or "application/octet-stream"
            },
        )
        print("  - Storage upload complete")

        # Prepare metadata
        metadata = {"is_intake_form": is_intake_form}

        # Create document record in database (use user client for RLS)
        print("  - Creating document record in database...")
        print(f"  - Is intake form: {is_intake_form}")
        doc_response = (
            user_supabase.table("documents")
            .insert(
                {
                    "case_id": case_id,
                    "file_name": file.filename,
                    "file_type": file.content_type or "unknown",
                    "file_size": file_size,
                    "storage_path": storage_path,
                    "status": "uploaded",
                    "metadata": metadata,
                }
            )
            .execute()
        )

        if not doc_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create document record"
            )

        print(f"  - ✅ Document uploaded successfully: {doc_response.data[0]['id']}")
        return doc_response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        print("\n❌ ERROR in upload_document:")
        print(f"  - Exception type: {type(e).__name__}")
        print(f"  - Exception message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error uploading document: {str(e)}"
        )


@router.get("/case/{case_id}", response_model=List[DocumentResponse])
async def list_documents_for_case(
    case_id: str, user=Depends(get_current_user), supabase=Depends(get_user_supabase_client)
):
    """List all documents for a specific case.

    Args:
    ----
        case_id: Case ID
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        List of documents
    """
    try:
        # Verify case ownership
        case_response = (
            supabase.table("cases").select("id").eq("id", case_id).eq("user_id", user["id"]).execute()
        )

        if not case_response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Get documents
        response = (
            supabase.table("documents")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=False)
            .execute()
        )

        return response.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching documents: {str(e)}"
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str, user=Depends(get_current_user), supabase=Depends(get_user_supabase_client)
):
    """Get document metadata by ID.

    Args:
    ----
        document_id: Document ID
        user: Current authenticated user
        supabase: Supabase client

    Returns:
    -------
        Document metadata
    """
    try:
        # Get document with case join to verify ownership
        response = (
            supabase.table("documents").select("*, cases!inner(user_id)").eq("id", document_id).execute()
        )

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        document = response.data[0]

        # Verify ownership through case
        if document["cases"]["user_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Remove nested case data before returning
        document.pop("cases", None)

        return document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching document: {str(e)}"
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user=Depends(get_current_user),
    user_supabase=Depends(get_user_supabase_client),
    service_supabase=Depends(get_supabase_client),
):
    """Delete a document and its file from storage.

    Args:
    ----
        document_id: Document ID
        user: Current authenticated user
        user_supabase: User-scoped Supabase client
        service_supabase: Service-role Supabase client
    """
    try:
        print("\n🔍 DEBUG delete_document:")
        print(f"  - Document ID: {document_id}")
        print(f"  - User ID: {user["id"]}")

        # Get document with ownership verification
        response = (
            user_supabase.table("documents")
            .select("storage_path, cases!inner(user_id)")
            .eq("id", document_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        document = response.data[0]

        # Verify ownership
        if document["cases"]["user_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Delete from storage (use service client to bypass storage RLS)
        storage_path = document["storage_path"]
        print(f"  - Deleting from storage: {storage_path}")
        service_supabase.storage.from_("documents").remove([storage_path])

        # Delete database record (use user client for RLS)
        print("  - Deleting database record")
        user_supabase.table("documents").delete().eq("id", document_id).execute()

        print("  - ✅ Document deleted successfully")
        return None
    except HTTPException:
        raise
    except Exception as e:
        print("\n❌ ERROR in delete_document:")
        print(f"  - Exception: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting document: {str(e)}"
        )
