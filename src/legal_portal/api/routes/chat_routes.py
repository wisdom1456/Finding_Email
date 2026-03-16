"""Chat endpoints for case discussion with AI assistant.

Provides streaming and non-streaming chat endpoints that use
analysis results as context for AI-powered case discussion.
"""

import json
import logging
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from legal_portal.api.dependencies import get_current_user, get_user_supabase_client
from legal_portal.api.routes._analysis_helpers import (
    _ensure_case_access,
    _fetch_latest_analysis_result,
    _get_user_ai_preferences,
)
from legal_portal.core.data_models import (
    ChatMessageRequest,
    ChatMessageResponse,
    ProcessingResult,
)
from legal_portal.services.shared.case_chat_service import CaseChatService
from legal_portal.utils.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

router = APIRouter()

__all__ = [
    "router",
    "stream_chat_response",
    "case_chat",
]


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

        # 2. Verify case ownership before granting access to data
        case_id = analysis_data["case_id"]
        _ensure_case_access(supabase, case_id, user["id"])

        # 3. Get conversation history (use case_id from the analysis record, not ProcessingResult)
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
