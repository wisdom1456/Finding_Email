"""Tests for CaseChatService — case-specific AI chat with context."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from legal_portal.core.data_models import ProcessingResult
from legal_portal.core.models.analysis_models import Party
from legal_portal.services.shared.case_chat_service import CaseChatService


def _make_processing_result(**overrides) -> ProcessingResult:
    """Create a minimal ProcessingResult for chat tests."""
    defaults = {
        "main_letter": "<html><body>Findings</body></html>",
        "document_summaries": "Contract.pdf: Purchase agreement between parties",
        "case_analysis": '{"case_summary": "Breach of contract case", "practice_area": "Consumer Protection"}',
        "status": "completed",
        "document_count": 2,
        "opposing_parties": [
            Party(name="Acme Corp", role="Defendant", is_opposing_party=True),
        ],
        "multi_stage_result": {
            "fact_matrix": {
                "timeline": [
                    {"date": "2024-01-15", "description": "Contract signed", "source_document": "Contract.pdf"}
                ],
                "financial_data": [
                    {"amount": 50000, "description": "Purchase price", "payment_type": "owed"}
                ],
            },
            "issue_map": {
                "primary_issues": [
                    {"issue_name": "Breach of Contract", "confidence": "high"},
                ]
            },
        },
    }
    defaults.update(overrides)
    return ProcessingResult(**defaults)


def _make_mock_client():
    """Create a mock OpenAIClient for chat tests."""
    mock = MagicMock()
    mock.get_preferred_model.return_value = "gpt-5-mini"
    mock.create_response.return_value = {
        "content": "Based on the contract, Acme Corp breached clause 5.2.",
    }
    return mock


@pytest.mark.asyncio
async def test_send_message_returns_response():
    """send_message returns a string AI response."""
    client = _make_mock_client()
    service = CaseChatService(client, jurisdiction="Florida")
    result = _make_processing_result()

    with patch.object(service, "_get_relevant_statute_context", return_value=""):
        response = await service.send_message(
            user_message="What are the key claims?",
            analysis_result=result,
            conversation_history=[],
        )

    assert isinstance(response, str)
    assert "Acme Corp" in response
    client.create_response.assert_called_once()


@pytest.mark.asyncio
async def test_send_message_includes_case_context():
    """System message assembled by _build_system_message contains case facts."""
    client = _make_mock_client()
    service = CaseChatService(client, jurisdiction="Florida")
    result = _make_processing_result()

    with patch.object(service, "_get_relevant_statute_context", return_value=""):
        system_msg = service._build_system_message(result)

    assert "Acme Corp" in system_msg
    assert "Defendant" in system_msg
    assert "Breach of Contract" in system_msg
    assert "Consumer Protection" in system_msg
    assert "Florida" in system_msg


@pytest.mark.asyncio
async def test_send_message_with_history():
    """Conversation history is passed through to the AI client."""
    client = _make_mock_client()
    service = CaseChatService(client, jurisdiction="Florida")
    result = _make_processing_result()

    history = [
        {"role": "user", "content": "What happened?"},
        {"role": "assistant", "content": "The contract was breached."},
    ]

    with patch.object(service, "_get_relevant_statute_context", return_value=""):
        await service.send_message(
            user_message="Tell me more",
            analysis_result=result,
            conversation_history=history,
        )

    call_kwargs = client.create_response.call_args
    # The conversation text should include the history
    input_text = call_kwargs.kwargs.get("input") or call_kwargs[1].get("input") or call_kwargs[0][1]
    assert "What happened?" in input_text
    assert "The contract was breached." in input_text


@pytest.mark.asyncio
async def test_stream_message_yields_tokens():
    """stream_message yields tokens from the OpenAI streaming response."""
    client = _make_mock_client()

    async def mock_stream(**kwargs):
        for token in ["Based ", "on ", "the ", "contract."]:
            yield token

    client.create_response_stream = mock_stream
    service = CaseChatService(client, jurisdiction="Florida")
    result = _make_processing_result()

    tokens = []
    with patch.object(service, "_get_relevant_statute_context", return_value=""):
        async for token in service.stream_message(
            user_message="Summarize the case",
            analysis_result=result,
            conversation_history=[],
        ):
            tokens.append(token)

    assert tokens == ["Based ", "on ", "the ", "contract."]


@pytest.mark.asyncio
async def test_build_system_message_structure():
    """System message has the expected section headings."""
    client = _make_mock_client()
    service = CaseChatService(client, jurisdiction="Florida")
    result = _make_processing_result()

    with patch.object(service, "_get_relevant_statute_context", return_value=""):
        msg = service._build_system_message(result)

    assert "## Case Summary" in msg
    assert "## Parties" in msg
    assert "## Timeline Highlights" in msg
    assert "## Financial Summary" in msg
    assert "## Primary Legal Issues" in msg


@pytest.mark.asyncio
async def test_build_system_message_empty_result():
    """Handles a minimal ProcessingResult gracefully (no multi_stage_result)."""
    client = _make_mock_client()
    service = CaseChatService(client, jurisdiction="Florida")
    result = _make_processing_result(
        multi_stage_result=None,
        opposing_parties=[],
        case_analysis="{}",
    )

    with patch.object(service, "_get_relevant_statute_context", return_value=""):
        msg = service._build_system_message(result)

    # Should not crash, and should still contain basic structure
    assert "## Parties" in msg
    assert "Florida" in msg
