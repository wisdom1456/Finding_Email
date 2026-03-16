"""Tests for CostEstimator — pre-processing cost estimation."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from legal_portal.core.constants import SERVICE_PRICING_RATES
from legal_portal.utils.cost_estimator import CostEstimator


@pytest.fixture
def estimator():
    return CostEstimator()


class TestDocumentProcessingCosts:
    def test_small_document_uses_gpt4o(self, estimator):
        """Documents under 20k tokens use the GPT-4o model."""
        doc = MagicMock()
        doc.content = "a" * 1000  # ~250 tokens, well under 20k
        doc.file_name = "test.pdf"

        costs = estimator.estimate_document_processing_costs([doc])

        assert len(costs) == 1
        assert costs[0].service_name == "OpenAI GPT-4o"
        assert costs[0].operation_type == "document_analysis"
        assert costs[0].cost > 0

    def test_large_document_uses_gpt4o_mini(self, estimator):
        """Documents over 20k tokens use the GPT-4o-mini model."""
        doc = MagicMock()
        doc.content = "a" * 100_000  # ~25k tokens, over 20k threshold
        doc.file_name = "big.pdf"

        costs = estimator.estimate_document_processing_costs([doc])

        assert len(costs) == 1
        assert costs[0].service_name == "OpenAI GPT-4o-mini"

    def test_multiple_documents(self, estimator):
        docs = []
        for i in range(3):
            doc = MagicMock()
            doc.content = f"Document {i} content " * 50
            doc.file_name = f"doc{i}.pdf"
            docs.append(doc)

        costs = estimator.estimate_document_processing_costs(docs)
        assert len(costs) == 3

    def test_file_name_preserved(self, estimator):
        doc = MagicMock()
        doc.content = "test content"
        doc.file_name = "my_file.pdf"

        costs = estimator.estimate_document_processing_costs([doc])
        assert costs[0].file_name == "my_file.pdf"


class TestAudioProcessingCosts:
    def test_audio_cost_calculation(self, estimator):
        audio_files = [{"filename": "deposition.mp3", "size": 10 * 1024 * 1024}]  # 10 MB

        costs = estimator.estimate_audio_processing_costs(audio_files)

        assert len(costs) == 1
        assert costs[0].service_name == "OpenAI Whisper"
        assert costs[0].operation_type == "audio_transcription"
        assert costs[0].unit_type == "minutes"
        assert costs[0].cost > 0

    def test_zero_size_audio_uses_minimum(self, estimator):
        audio_files = [{"filename": "empty.mp3", "size": 0}]

        costs = estimator.estimate_audio_processing_costs(audio_files)

        # Minimum billable unit is 1 minute
        assert costs[0].units_consumed >= 1


class TestVideoProcessingCosts:
    def test_video_produces_two_cost_items(self, estimator):
        """Each video produces a video processing cost and a Gemini analysis cost."""
        video_files = [{"filename": "evidence.mp4", "size": 50 * 1024 * 1024}]  # 50 MB

        costs = estimator.estimate_video_processing_costs(video_files)

        assert len(costs) == 2
        service_names = {c.service_name for c in costs}
        assert "Google Vertex AI Video" in service_names
        assert "Google Vertex AI Gemini-2.5-flash" in service_names

    def test_video_cost_positive(self, estimator):
        video_files = [{"filename": "video.mp4", "size": 100 * 1024 * 1024}]

        costs = estimator.estimate_video_processing_costs(video_files)

        for cost in costs:
            assert cost.cost > 0


class TestGenerateCostEstimate:
    def test_returns_cost_estimate_object(self, estimator):
        from legal_portal.core.data_models import CostEstimate

        doc = MagicMock()
        doc.content = "Document content here"
        doc.file_name = "doc.pdf"

        estimate = estimator.generate_cost_estimate(documents=[doc])
        assert isinstance(estimate, CostEstimate)

    def test_empty_inputs_returns_estimate(self, estimator):
        estimate = estimator.generate_cost_estimate()
        assert estimate is not None

    def test_individual_cost_methods_return_costs(self, estimator):
        """Verify the cost breakdown methods produce valid ServiceCost lists."""
        doc = MagicMock()
        doc.content = "Some text content for analysis"
        doc.file_name = "doc.pdf"

        doc_costs = estimator.estimate_document_processing_costs([doc])
        assert len(doc_costs) == 1
        assert doc_costs[0].cost > 0

        audio_costs = estimator.estimate_audio_processing_costs(
            [{"filename": "a.mp3", "size": 5 * 1024 * 1024}]
        )
        assert len(audio_costs) == 1
        assert audio_costs[0].cost > 0


class TestConfidenceLevel:
    def test_default_confidence(self, estimator):
        assert estimator.confidence_level == 0.8

    def test_update_confidence(self, estimator):
        estimator.update_confidence_level(0.95)
        assert estimator.confidence_level == 0.95

    def test_invalid_confidence_raises(self, estimator):
        with pytest.raises(ValueError):
            estimator.update_confidence_level(1.5)

        with pytest.raises(ValueError):
            estimator.update_confidence_level(-0.1)
