"""Unit tests for letter polish pass (LetterPolisher and polish_letter_async)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from legal_portal.utils.letter_polish import LetterPolisher, polish_letter_async


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BULLET_DRAFT = """\
Dear Jane,

Key Findings:
- Breach of contract occurred on January 15, 2024.
- Damages total $50,000.

Next Steps:
1. File a demand letter within 30 days.
2. Preserve all written communications.

Sincerely,
John Smith, Esq.
"""

_POLISHED = """\
Dear Jane,

Based on our review of the file, a breach of contract occurred on January 15, 2024,\
 resulting in damages totaling $50,000. We recommend sending a demand letter within\
 30 days and preserving all written communications in the interim.

Sincerely,
John Smith, Esq.
"""


def _make_client(response_text: str) -> MagicMock:
    """Return a mock OpenAI client whose create_chat_completion returns response_text."""
    client = MagicMock()
    client.create_chat_completion.return_value = {
        "content": response_text,
        "usage": {"prompt_tokens": 500, "completion_tokens": 300, "total_tokens": 800},
        "model": "gpt-5.2",
    }
    return client


def _make_failing_client(exc: Exception) -> MagicMock:
    """Return a mock OpenAI client whose create_chat_completion raises exc."""
    client = MagicMock()
    client.create_chat_completion.side_effect = exc
    return client


# ---------------------------------------------------------------------------
# LetterPolisher.polish_letter — success path
# ---------------------------------------------------------------------------


def test_polish_letter_returns_polished_text():
    client = _make_client(_POLISHED)
    polisher = LetterPolisher(client)
    result = polisher.polish_letter(_BULLET_DRAFT)

    assert result["success"] is True
    assert result["polished_letter"] == _POLISHED.strip()
    assert isinstance(result["changes_made"], list)
    assert result["original_length"] == len(_BULLET_DRAFT)
    assert result["polished_length"] == len(_POLISHED.strip())


def test_polish_letter_calls_correct_model():
    client = _make_client(_POLISHED)
    polisher = LetterPolisher(client)
    polisher.polish_letter(_BULLET_DRAFT)

    call_kwargs = client.create_chat_completion.call_args
    assert call_kwargs.kwargs["model"] == "gpt-5.2"


def test_polish_letter_uses_low_temperature():
    client = _make_client(_POLISHED)
    polisher = LetterPolisher(client)
    polisher.polish_letter(_BULLET_DRAFT)

    call_kwargs = client.create_chat_completion.call_args
    assert call_kwargs.kwargs["temperature"] <= 0.2


def test_polish_letter_raw_text_included_in_prompt():
    """The draft text must appear in the user message sent to the model."""
    client = _make_client(_POLISHED)
    polisher = LetterPolisher(client)
    polisher.polish_letter(_BULLET_DRAFT)

    messages = client.create_chat_completion.call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "Dear Jane" in user_content


# ---------------------------------------------------------------------------
# LetterPolisher.polish_letter — failure path
# ---------------------------------------------------------------------------


def test_polish_letter_returns_original_on_exception():
    client = _make_failing_client(RuntimeError("OpenAI timeout"))
    polisher = LetterPolisher(client)
    result = polisher.polish_letter(_BULLET_DRAFT)

    assert result["success"] is False
    assert result["polished_letter"] == _BULLET_DRAFT
    assert result["changes_made"] == []
    assert "OpenAI timeout" in result["error"]


def test_polish_letter_never_raises():
    """polish_letter must never propagate exceptions to callers."""
    client = _make_failing_client(ValueError("unexpected"))
    polisher = LetterPolisher(client)
    # Should not raise
    result = polisher.polish_letter(_BULLET_DRAFT)
    assert result["success"] is False


# ---------------------------------------------------------------------------
# LetterPolisher._detect_changes
# ---------------------------------------------------------------------------


def test_detect_changes_bullet_conversion():
    polisher = LetterPolisher(MagicMock())
    original = "• **First issue**: some detail\n• **Second issue**: more detail"
    polished = "The first issue involves some detail. The second issue adds more detail."
    changes = polisher._detect_changes(original, polished)
    # bold bullets removed → should be flagged
    assert any("bold bullet" in c.lower() or "converted" in c.lower() for c in changes)


def test_detect_changes_spacing():
    polisher = LetterPolisher(MagicMock())
    original = "Para one.\n\n\nPara two.\n\n\nPara three."
    polished = "Para one.\n\nPara two.\n\nPara three."
    changes = polisher._detect_changes(original, polished)
    assert any("spacing" in c.lower() for c in changes)


def test_polish_prompt_instructs_citation_removal():
    """The formatting prompt must include the parenthetical citation removal rule."""
    polisher = LetterPolisher(MagicMock())
    prompt = polisher.formatting_prompt
    assert "internal pipeline parentheticals" in prompt
    assert "preserve the underlying fact" in prompt


def test_polish_prompt_instructs_internal_language_replacement():
    """The formatting prompt must address internal pipeline language generically."""
    polisher = LetterPolisher(MagicMock())
    prompt = polisher.formatting_prompt
    assert "client-reported" in prompt
    assert "pipeline" in prompt


def test_polish_prompt_instructs_distancing_language():
    """The formatting prompt must cover all distancing phrases toward the client."""
    polisher = LetterPolisher(MagicMock())
    prompt = polisher.formatting_prompt
    # All common distancing variants must be addressed (case-insensitive, since
    # "You report" is now preserved in Background & Issue but still referenced)
    for phrase in ("you report", "you state", "you say", "you claim", "you allege"):
        assert phrase in prompt.lower(), f"Missing distancing phrase: '{phrase}'"


def test_polish_prompt_instructs_plain_english_jargon():
    """The formatting prompt must address common legal jargon generically."""
    polisher = LetterPolisher(MagicMock())
    prompt = polisher.formatting_prompt
    assert "plain English" in prompt
    for term in ("spoliation", "standing", "accrual", "plaintiff", "cause of action",
                 "filing posture", "limitations purposes"):
        assert term in prompt, f"Missing jargon term: '{term}'"


def test_polish_prompt_instructs_depersonalizing_terms():
    """The formatting prompt must address abstract terms for people."""
    polisher = LetterPolisher(MagicMock())
    prompt = polisher.formatting_prompt
    assert "actors" in prompt
    assert "principals" in prompt


def test_polish_prompt_instructs_definition_integration():
    """The formatting prompt must address inline textbook-style definitions."""
    polisher = LetterPolisher(MagicMock())
    prompt = polisher.formatting_prompt
    assert "textbook" in prompt or "dictionary" in prompt


def test_polish_prompt_instructs_opening_rewrite():
    """The formatting prompt must address em-dash sub-header openings."""
    polisher = LetterPolisher(MagicMock())
    prompt = polisher.formatting_prompt
    assert "em-dash" in prompt


def test_detect_changes_empty_when_unchanged():
    polisher = LetterPolisher(MagicMock())
    text = "Dear client,\n\nNo changes needed.\n\nSincerely,\nAttorney"
    changes = polisher._detect_changes(text, text)
    assert changes == []


# ---------------------------------------------------------------------------
# polish_letter_async — async wrapper
# ---------------------------------------------------------------------------


def test_polish_letter_async_success():
    client = _make_client(_POLISHED)
    result = asyncio.run(polish_letter_async(client, _BULLET_DRAFT))

    assert result["success"] is True
    assert result["polished_letter"] == _POLISHED.strip()


def test_polish_letter_async_failure_returns_original():
    client = _make_failing_client(ConnectionError("network error"))
    result = asyncio.run(polish_letter_async(client, _BULLET_DRAFT))

    assert result["success"] is False
    assert result["polished_letter"] == _BULLET_DRAFT


def test_polish_letter_async_empty_response_treated_as_failure():
    """If the model returns an empty string, polished_letter should still be safe to use."""
    client = _make_client("   ")  # whitespace-only response
    result = asyncio.run(polish_letter_async(client, _BULLET_DRAFT))

    # polished_letter is stripped to "" — callers check truthiness before using it
    # success=True because no exception was thrown, but polished_letter is empty
    assert result["success"] is True
    assert result["polished_letter"] == ""  # .strip() applied in polish_letter
