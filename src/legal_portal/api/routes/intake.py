"""Intake Form Processing API Routes.

Handles intake form extraction and Q&A pair generation.
"""

import os
import tempfile
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from legal_portal.api.dependencies import get_current_user
from legal_portal.core.document_processor import DocumentProcessor
from legal_portal.utils.helpers import (
    build_structured_display_from_qa,
    extract_client_name_from_qa,
    identify_relevant_practice_areas_from_qa,
    parse_intake_form_qa_pairs,
)
from pydantic import BaseModel

router = APIRouter(prefix="/intake", tags=["intake"])


# ===== Request/Response Models =====
class QAPair(BaseModel):
    """Question and Answer pair from intake form."""

    question: str
    answer: str
    confidence: float = 1.0


class IntakeProcessResponse(BaseModel):
    """Response from intake processing."""

    success: bool
    client_name: str
    practice_areas: List[str]
    qa_pairs: List[QAPair]
    structured_data: Dict[str, Any]
    raw_content: str


@router.post("/process", response_model=IntakeProcessResponse)
async def process_intake_form(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Process intake form and extract Q&A pairs without saving to database.

    This endpoint is for the review workflow - it extracts data but doesn't
    commit anything to the database until the user confirms.
    """
    temp_file_path = None

    try:
        # Validate file type
        allowed_types = [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "text/plain",
        ]

        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Please upload PDF, DOCX, DOC, or TXT.",
            )

        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        # Process document with DocumentProcessor
        processor = DocumentProcessor()

        # Create a mock uploaded file object for processing
        class MockUploadedFile:
            def __init__(self, name, path):
                self.name = name
                self._path = path

            def getbuffer(self):
                with open(self._path, "rb") as f:
                    return f.read()

        mock_file = MockUploadedFile(file.filename, temp_file_path)

        # Process the document
        processed_docs = await processor.process_documents_from_streamlit(
            [mock_file], intake_filenames=["intake"]
        )

        if not processed_docs:
            raise HTTPException(status_code=400, detail="Failed to extract content from intake form")

        intake_content = processed_docs[0].content

        # Extract Q&A pairs using AI
        qa_pairs = parse_intake_form_qa_pairs(intake_content)

        if not qa_pairs:
            raise HTTPException(status_code=400, detail="Failed to extract Q&A pairs from intake form")

        # Derive metadata from Q&A pairs
        client_name = extract_client_name_from_qa(qa_pairs)
        practice_areas = identify_relevant_practice_areas_from_qa(qa_pairs)
        structured_data = build_structured_display_from_qa(qa_pairs)

        # Convert to response format
        qa_response = [
            QAPair(
                question=qa.get("question", ""),
                answer=qa.get("answer", ""),
                confidence=qa.get("confidence", 1.0),
            )
            for qa in qa_pairs
        ]

        return IntakeProcessResponse(
            success=True,
            client_name=client_name or "",
            practice_areas=practice_areas,
            qa_pairs=qa_response,
            structured_data=structured_data,
            raw_content=intake_content,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process intake form: {str(e)}")
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except:
                pass


class IntakeConfirmRequest(BaseModel):
    """Request to confirm and save intake data."""

    case_id: str
    client_name: str
    practice_areas: List[str]
    qa_pairs: List[Dict[str, str]]
    raw_content: str


@router.post("/confirm")
async def confirm_intake_data(
    request: IntakeConfirmRequest,
    user=Depends(get_current_user),
):
    """Save confirmed intake data to case and prepare for analysis.

    After user reviews and edits the extracted data, this endpoint
    saves it to the database.
    """
    try:
        from supabase import create_client

        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

        if not supabase_url or not supabase_key:
            raise HTTPException(status_code=500, detail="Database not configured")

        supabase = create_client(supabase_url, supabase_key)

        # Verify case belongs to user
        case_result = (
            supabase.table("cases").select("*").eq("id", request.case_id).eq("user_id", user["id"]).execute()
        )

        if not case_result.data:
            raise HTTPException(status_code=404, detail="Case not found")

        # Update case with intake data
        update_data = {
            "client_name": request.client_name,
            "metadata": {
                "intake_processed": True,
                "practice_areas": request.practice_areas,
                "qa_pairs": request.qa_pairs,
                "raw_intake_content": request.raw_content,
            },
        }

        supabase.table("cases").update(update_data).eq("id", request.case_id).execute()

        return {"success": True, "message": "Intake data saved successfully", "case_id": request.case_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save intake data: {str(e)}")
