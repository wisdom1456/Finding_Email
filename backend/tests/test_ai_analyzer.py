# Add the project root to the Python path
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.utils.data_models import (
    CaseAnalysisResult,
    DemandLetterEvaluation,
    EnhancedIntakeAnalysis,
    LegalAssessment,
    TranscriptedMedia,
    VideoInsight,
)
from backend_logic.ai import AIAnalyzer


@pytest.fixture
def mock_openai_client():
    """Fixture for a mocked OpenAI client."""
    return MagicMock()


@pytest.fixture
def mock_doc_processor():
    """Fixture for a mocked DocumentProcessor."""
    return MagicMock()


@pytest.fixture
def ai_analyzer(mock_openai_client, mock_doc_processor):
    """Fixture for an AIAnalyzer instance with mocked dependencies."""
    return AIAnalyzer(client=mock_openai_client, doc_processor=mock_doc_processor)


class TestAIAnalyzer:
    """Unit tests for the AIAnalyzer class."""

    @pytest.mark.asyncio
    async def test_summarize_media_content(self, ai_analyzer, mock_openai_client):
        """Test the new _summarize_media_content method."""
        mock_openai_client.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(message=MagicMock(content='{"summary": "Test summary"}'))
            ]
        )
        summary = await ai_analyzer._summarize_media_content(
            "test transcript", "audio", "test.mp3"
        )
        assert summary == "Test summary"

    @pytest.mark.asyncio
    async def test_integration_of_media_insights(self, ai_analyzer, mock_openai_client):
        """Test the integration of media insights into the final case analysis."""
        ai_analyzer._make_openai_request = AsyncMock(
            side_effect=[
                {"summary": "Audio summary"},
                {"summary": "Video summary"},
                {
                    "legal_assessment": LegalAssessment(
                        claim_viability="Strong"
                    ).model_dump(),
                    "demand_letter_evaluation": DemandLetterEvaluation(
                        is_appropriate=True
                    ).model_dump(),
                },
            ]
        )

        analysis = CaseAnalysisResult(
            intake_analysis=EnhancedIntakeAnalysis(client_name="Test"),
            transcripted_media=[
                TranscriptedMedia(file_name="test.mp3", transcript="long transcript")
            ],
            video_insights=[
                VideoInsight(file_name="test.mp4", insights={"data": "video data"})
            ],
        )

        result = await ai_analyzer.perform_final_assessment(analysis)

        assert (
            "long transcript"
            not in ai_analyzer._make_openai_request.call_args_list[2][0][0]
        )
        assert (
            "Audio summary" in ai_analyzer._make_openai_request.call_args_list[2][0][0]
        )
        assert result.legal_assessment is not None

    @pytest.mark.asyncio
    async def test_handling_of_no_media_content(self, ai_analyzer):
        """Test the handling of cases with no media content."""
        ai_analyzer._make_openai_request = AsyncMock(
            return_value={
                "legal_assessment": LegalAssessment(
                    claim_viability="Strong"
                ).model_dump(),
                "demand_letter_evaluation": DemandLetterEvaluation(
                    is_appropriate=True
                ).model_dump(),
            }
        )

        analysis = CaseAnalysisResult(
            intake_analysis=EnhancedIntakeAnalysis(client_name="Test"),
            analyzed_documents=[MagicMock()],
        )

        result = await ai_analyzer.perform_final_assessment(analysis)
        assert result.legal_assessment is not None

    @pytest.mark.asyncio
    async def test_token_management_with_media(self, ai_analyzer):
        """Test token management with media content included."""
        with patch.object(
            ai_analyzer, "_truncate_content_if_needed", return_value="truncated"
        ) as mock_truncate:
            # This test is more conceptual; we ensure truncation is called for large content.
            document = MagicMock(content="a" * 40000, file_name="large.txt")
            context = EnhancedIntakeAnalysis(client_name="test")

            await ai_analyzer._analyze_single_document(document, context)

            mock_truncate.assert_called_once()
