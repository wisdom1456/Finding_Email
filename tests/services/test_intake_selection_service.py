"""AI intake selection: pick the most detailed intake doc among candidates.

Mocks match the real OpenAIClient contract (src/legal_portal/utils/openai_client.py):
- create_chat_completion(...) returns a dict {"content": ..., "usage": ..., "model": ...}
  and RAISES on failure (it does not return a success=False envelope).
- parse_json_response(content) returns {"success": bool, "data": ..., "error": ...}.
"""
from unittest.mock import MagicMock

from legal_portal.services.analysis.intake_selection_service import (
    IntakeSelection,
    select_intake_document,
)


def _candidates():
    return [
        {"id": "d1", "file_name": "Intake Form - General.pdf", "file_type": "application/pdf"},
        {"id": "d2", "file_name": "intake notes.txt", "file_type": "text/plain"},
    ]


def _supabase_with_text():
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": "d1", "extracted_text": "Full client intake: name, dates, damages..."},
        {"id": "d2", "extracted_text": "brief note"},
    ]
    return sb


def _openai_returning(payload):
    client = MagicMock()
    client.get_preferred_model.return_value = "gpt-5.4-mini"
    client.create_chat_completion.return_value = {
        "content": "irrelevant-raw-content",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "model": "gpt-5.4-mini",
    }
    client.parse_json_response.return_value = {"success": True, "data": payload, "error": None}
    return client


def test_returns_choice_with_reasoning():
    payload = {
        "chosen_doc_id": "d1",
        "reasoning": "d1 contains full client details",
        "scores": [{"doc_id": "d1", "score": 90, "note": "complete"},
                   {"doc_id": "d2", "score": 20, "note": "sparse"}],
    }
    result = select_intake_document(_candidates(), _supabase_with_text(), _openai_returning(payload))
    assert isinstance(result, IntakeSelection)
    assert result.chosen_doc_id == "d1"
    assert "full client details" in result.reasoning
    assert result.scores == payload["scores"]


def test_none_when_fewer_than_two_candidates():
    result = select_intake_document(_candidates()[:1], _supabase_with_text(), _openai_returning({}))
    assert result is None


def test_none_when_llm_raises():
    client = _openai_returning({})
    client.create_chat_completion.side_effect = RuntimeError("boom")
    assert select_intake_document(_candidates(), _supabase_with_text(), client) is None


def test_none_when_chosen_id_not_a_candidate():
    payload = {"chosen_doc_id": "d999", "reasoning": "?", "scores": []}
    assert select_intake_document(_candidates(), _supabase_with_text(), _openai_returning(payload)) is None


def test_none_when_parse_json_response_reports_failure():
    client = _openai_returning({})
    client.parse_json_response.return_value = {
        "success": False,
        "data": None,
        "error": "JSON decode error",
    }
    assert select_intake_document(_candidates(), _supabase_with_text(), client) is None


def test_none_when_supabase_lookup_raises():
    client = _openai_returning({"chosen_doc_id": "d1", "reasoning": "x", "scores": []})
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.side_effect = RuntimeError("db down")
    assert select_intake_document(_candidates(), sb, client) is None


def _sent_prompt(client):
    """Extract the outgoing user prompt from the mocked create_chat_completion call."""
    kwargs = client.create_chat_completion.call_args.kwargs
    messages = kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    return messages[0]["content"]


def test_prompt_contains_each_candidate_id_and_snippet_marker():
    payload = {"chosen_doc_id": "d1", "reasoning": "ok", "scores": []}
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": "d1", "extracted_text": "UNIQUE_SNIPPET_D1 full client intake details"},
        {"id": "d2", "extracted_text": "UNIQUE_SNIPPET_D2 brief note"},
    ]
    client = _openai_returning(payload)

    result = select_intake_document(_candidates(), sb, client)

    assert result is not None
    prompt = _sent_prompt(client)
    assert "doc_id: d1" in prompt
    assert "doc_id: d2" in prompt
    assert "UNIQUE_SNIPPET_D1" in prompt
    assert "UNIQUE_SNIPPET_D2" in prompt
    assert "Intake Form - General.pdf" in prompt
    assert "intake notes.txt" in prompt


def test_snippet_truncated_to_exactly_3500_chars():
    inside_sentinel = "MARKER_INSIDE"  # ends exactly at the 3500-char boundary below
    past_sentinel = "MARKER_PAST_BOUNDARY"
    # First 3500 chars = 'A'*3400 + inside_sentinel + 'B' padding; past_sentinel starts at 3500.
    text = (
        "A" * 3400
        + inside_sentinel
        + "B" * (3500 - 3400 - len(inside_sentinel))
        + past_sentinel
    )
    assert text.index(past_sentinel) == 3500

    payload = {"chosen_doc_id": "d1", "reasoning": "ok", "scores": []}
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": "d1", "extracted_text": text},
        {"id": "d2", "extracted_text": "brief note"},
    ]
    client = _openai_returning(payload)

    result = select_intake_document(_candidates(), sb, client)

    assert result is not None
    prompt = _sent_prompt(client)
    assert inside_sentinel in prompt
    assert past_sentinel not in prompt
    # The snippet embedded in the prompt is exactly the first 3500 chars, verbatim.
    assert text[:3500] in prompt
    assert text[:3501] not in prompt


def test_reasoning_truncated_to_exactly_500_chars():
    long_reasoning = "R" * 600
    payload = {"chosen_doc_id": "d1", "reasoning": long_reasoning, "scores": []}
    result = select_intake_document(_candidates(), _supabase_with_text(), _openai_returning(payload))
    assert result is not None
    assert len(result.reasoning) == 500
    assert result.reasoning == long_reasoning[:500]
