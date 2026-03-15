"""Tests for chat routes — streaming and non-streaming case chat endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _analysis_result_row(case_id="case-001", analysis_id="analysis-001"):
    """Minimal analysis_results row with a valid ProcessingResult payload."""
    return {
        "id": analysis_id,
        "case_id": case_id,
        "status": "completed",
        "result": {
            "main_letter": "<html>Findings</html>",
            "document_summaries": "Contract.pdf: Agreement",
            "case_analysis": '{"case_summary":"Test case","practice_area":"Consumer Protection"}',
            "status": "completed",
            "document_count": 1,
            "opposing_parties": [{"name": "Acme", "role": "Defendant"}],
            "multi_stage_result": {
                "fact_matrix": {"timeline": [], "financial_data": []},
                "issue_map": {"primary_issues": []},
            },
        },
    }


def _configure_supabase_for_chat(mock_client, analysis_row, chat_history=None):
    """Configure mock supabase to return analysis + chat history."""
    chat_history = chat_history or []

    def table_dispatcher(table_name):
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.single.return_value = mock_table

        if table_name == "analysis_results":
            mock_table.execute.return_value = MagicMock(
                data=[analysis_row] if analysis_row else []
            )
        elif table_name == "case_chat_messages":
            mock_table.execute.return_value = MagicMock(data=chat_history)
        elif table_name == "cases":
            mock_table.execute.return_value = MagicMock(
                data=[{"id": "case-001", "user_id": "00000000-0000-0000-0000-000000000001"}]
            )
        elif table_name == "profiles":
            mock_table.execute.return_value = MagicMock(data=[])
        else:
            mock_table.execute.return_value = MagicMock(data=[])

        return mock_table

    mock_client.table.side_effect = table_dispatcher


# ---------------------------------------------------------------------------
# Tests: stream_chat_response (POST /{analysis_id}/chat/stream)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_chat_response_success(app_client: AsyncClient, mock_supabase_client):
    """200 + SSE stream for valid analysis."""
    row = _analysis_result_row()
    _configure_supabase_for_chat(mock_supabase_client, row)

    with patch("legal_portal.api.routes.chat_routes.OpenAIClient") as MockOAI, \
         patch("legal_portal.api.routes.chat_routes.CaseChatService") as MockChat:
        mock_service = MagicMock()

        async def mock_stream(**kwargs):
            for token in ["Hello", " world"]:
                yield token

        mock_service.stream_message = mock_stream
        MockChat.return_value = mock_service

        response = await app_client.post(
            "/api/analysis/analysis-001/chat/stream",
            json={"message": "What are the key issues?"},
            headers={"Authorization": "Bearer mock_token"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_stream_chat_response_analysis_not_found(app_client: AsyncClient, mock_supabase_client):
    """404 when analysis doesn't exist."""
    _configure_supabase_for_chat(mock_supabase_client, None)

    response = await app_client.post(
        "/api/analysis/nonexistent/chat/stream",
        json={"message": "Hello"},
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code in [404, 500]


@pytest.mark.asyncio
async def test_stream_chat_response_no_result(app_client: AsyncClient, mock_supabase_client):
    """404/500 when analysis has no result payload."""
    row = _analysis_result_row()
    row["result"] = None
    _configure_supabase_for_chat(mock_supabase_client, row)

    response = await app_client.post(
        "/api/analysis/analysis-001/chat/stream",
        json={"message": "Hello"},
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code in [404, 500]


@pytest.mark.asyncio
async def test_stream_chat_response_unauthorized(app_client: AsyncClient, mock_supabase_client):
    """401/403 without auth header."""
    response = await app_client.post(
        "/api/analysis/analysis-001/chat/stream",
        json={"message": "Hello"},
    )

    assert response.status_code in [401, 403]


# ---------------------------------------------------------------------------
# Tests: case_chat (POST /chat)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_chat_success(app_client: AsyncClient, mock_supabase_client):
    """200 + response body for non-streaming chat."""
    row = _analysis_result_row()
    _configure_supabase_for_chat(mock_supabase_client, row)

    with patch("legal_portal.api.routes.chat_routes.OpenAIClient") as MockOAI, \
         patch("legal_portal.api.routes.chat_routes.CaseChatService") as MockChat, \
         patch("legal_portal.api.routes.chat_routes._get_user_ai_preferences", new_callable=AsyncMock, return_value=None):
        mock_service = MagicMock()
        mock_service.send_message = AsyncMock(return_value="The key issue is breach of contract.")
        MockChat.return_value = mock_service

        response = await app_client.post(
            "/api/analysis/chat",
            json={"case_id": "case-001", "message": "What are the key issues?"},
            headers={"Authorization": "Bearer mock_token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "response" in data


@pytest.mark.asyncio
async def test_case_chat_empty_message(app_client: AsyncClient, mock_supabase_client):
    """422 for blank/missing message field."""
    response = await app_client.post(
        "/api/analysis/chat",
        json={"case_id": "case-001"},
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_case_chat_no_case_id(app_client: AsyncClient, mock_supabase_client):
    """400 when case_id is missing."""
    response = await app_client.post(
        "/api/analysis/chat",
        json={"message": "Hello"},
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_case_chat_unauthorized(app_client: AsyncClient, mock_supabase_client):
    """401/403 without auth header."""
    response = await app_client.post(
        "/api/analysis/chat",
        json={"case_id": "case-001", "message": "Hello"},
    )

    assert response.status_code in [401, 403]
