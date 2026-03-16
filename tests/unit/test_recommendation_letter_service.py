"""Unit tests for recommendation letter formatting semantics."""

from unittest.mock import MagicMock

from legal_portal.core.data_models import RecommendedLetterType
from legal_portal.services.letters.recommendation_letter_service import RecommendationLetterService


def test_request_documents_render_uses_intent_specific_title() -> None:
    service = RecommendationLetterService(MagicMock())

    html = service.render_markdown_to_html(
        "Dear Client,\n\nPlease provide the requested documents.",
        letter_type=RecommendedLetterType.REQUEST_DOCUMENTS,
        client_name="Jane Doe",
    )

    assert "<title>Document Request Letter - Jane Doe</title>" in html
    assert "Findings Email" not in html


def test_proceed_render_uses_engagement_title() -> None:
    service = RecommendationLetterService(MagicMock())

    html = service.render_markdown_to_html(
        "Dear Client,\n\nWe are ready to proceed.",
        letter_type=RecommendedLetterType.PROCEED,
        client_name="Jane Doe",
    )

    assert "<title>Engagement Letter - Jane Doe</title>" in html


def test_request_documents_stream_instructions_are_plain_language() -> None:
    service = RecommendationLetterService(MagicMock())

    instructions = service._stream_instructions_for_letter_type(
        letter_type=RecommendedLetterType.REQUEST_DOCUMENTS,
        letter_display="Document Request",
    )

    assert "plain-language advisory tone" in instructions
    assert "without sounding adversarial" in instructions


def test_non_request_documents_stream_instructions_remain_formal() -> None:
    service = RecommendationLetterService(MagicMock())

    instructions = service._stream_instructions_for_letter_type(
        letter_type=RecommendedLetterType.SETTLEMENT_ADVISORY,
        letter_display="Settlement Advisory",
    )

    assert "formal legal language" in instructions
