"""Unit tests for CostCalculator."""

from __future__ import annotations

from decimal import Decimal

import pytest
from legal_portal.core.data_models import AnalyzedDocument
from legal_portal.utils.cost_calculator import CostCalculator


def test_calculate_document_analysis_costs_exact():
    """Test exact cost calculation for document analysis with known token counts."""
    calculator = CostCalculator()

    # Create analyzed document
    analyzed_doc = AnalyzedDocument(
        file_name="test_document.pdf",
        document_type="Contract",
        summary="Test summary",
        relevance_to_case="Test relevance",
    )

    # Fixed token counts: 1000 input, 2000 output
    processing_logs = {
        "test_document.pdf": {
            "token_usage": {"prompt_tokens": 1000, "completion_tokens": 2000},
            "model": "gpt-4o",
        }
    }

    # Calculate costs
    costs = calculator.calculate_document_analysis_costs(
        analyzed_documents=[analyzed_doc], processing_logs=processing_logs
    )

    # Expected: (1000 × $0.000005) + (2000 × $0.000015) = $0.005 + $0.03 = $0.035
    expected_cost = Decimal("0.005") + Decimal("0.03")  # $0.035

    assert len(costs) == 1
    assert abs(costs[0].cost - float(expected_cost)) < 0.0001  # Allow small floating point differences
    assert costs[0].service_name == "OpenAI GPT-4o"
    assert costs[0].operation_type == "document_analysis"
    assert costs[0].units_consumed == 3000  # total tokens


def test_calculate_audio_processing_costs_exact():
    """Test exact cost calculation for audio processing."""
    # Skip if TranscriptedMedia is not available
    try:
        from legal_portal.core.data_models import TranscriptedMedia  # noqa: F401
    except ImportError:
        pytest.skip("TranscriptedMedia not available")

    calculator = CostCalculator()

    # Create mock transcripted media object
    class MockTranscriptedMedia:
        def __init__(self):
            self.file_name = "audio.mp3"
            self.transcript = "Sample transcript text"
            self.duration = 300.0  # 5 minutes in seconds

    transcripted_media = [MockTranscriptedMedia()]

    # Processing logs with exact duration
    processing_logs = {"audio.mp3": {"duration_minutes": 5.0}}

    # Calculate costs
    costs = calculator.calculate_audio_processing_costs(
        transcripted_media=transcripted_media, processing_logs=processing_logs
    )

    # Expected: 5.0 × $0.006 = $0.03
    expected_cost = Decimal("5.0") * Decimal("0.006")  # $0.03

    assert len(costs) == 1
    assert abs(costs[0].cost - float(expected_cost)) < 0.0001
    assert costs[0].service_name == "OpenAI Whisper"
    assert costs[0].operation_type == "audio_transcription"
    assert costs[0].units_consumed == 5  # minutes


def test_calculate_video_processing_costs_exact():
    """Test exact cost calculation for video processing."""
    # Skip if VideoInsight is not available
    try:
        from legal_portal.core.data_models import VideoInsight  # noqa: F401
    except ImportError:
        pytest.skip("VideoInsight not available")

    calculator = CostCalculator()

    # Create mock video insight object
    class MockVideoInsight:
        def __init__(self):
            self.file_name = "video.mp4"
            self.duration = 180.0  # 3 minutes in seconds
            self.insights = "Sample video insights"
            self.labels = []
            self.objects = []

    class MockMetadata:
        def __init__(self):
            self.size = 50 * 1024 * 1024  # 50 MB

    video_insight = MockVideoInsight()
    video_insight.metadata = MockMetadata()

    # Processing logs with exact values
    processing_logs = {
        "video.mp4": {
            "duration_minutes": 3.0,
            "gemini_token_usage": {"input_tokens": 1500, "output_tokens": 3000},
        }
    }

    # Calculate costs
    costs = calculator.calculate_video_processing_costs(
        video_insights=[video_insight], processing_logs=processing_logs
    )

    # Expected costs:
    # Video processing: 3.0 × $0.10 = $0.30
    # Gemini analysis: (1500 × $0.000000075) + (3000 × $0.0000003) = $0.0001125 + $0.0009 = $0.0010125
    # Total: $0.30 + $0.0010125 = $0.3010125

    video_cost = Decimal("3.0") * Decimal("0.10")  # $0.30
    gemini_input_cost = Decimal("1500") * Decimal("0.075") / Decimal("1000000")  # $0.0001125
    gemini_output_cost = Decimal("3000") * Decimal("0.30") / Decimal("1000000")  # $0.0009
    gemini_total = gemini_input_cost + gemini_output_cost

    # Should have 2 cost entries: video processing + gemini analysis
    assert len(costs) == 2

    # Find video processing cost
    video_cost_entry = next(c for c in costs if "Video" in c.service_name)
    assert abs(video_cost_entry.cost - float(video_cost)) < 0.01

    # Find gemini cost
    gemini_cost_entry = next(c for c in costs if "Gemini" in c.service_name)
    assert abs(gemini_cost_entry.cost - float(gemini_total)) < 0.0001


def test_total_actual_costs_aggregates_all_services():
    """Test that total actual costs aggregates all service costs correctly."""
    calculator = CostCalculator()

    # Create analyzed documents
    analyzed_doc1 = AnalyzedDocument(
        file_name="doc1.pdf", document_type="Contract", summary="Summary 1", relevance_to_case="Relevance 1"
    )

    analyzed_doc2 = AnalyzedDocument(
        file_name="doc2.pdf",
        document_type="Correspondence",
        summary="Summary 2",
        relevance_to_case="Relevance 2",
    )

    # Processing logs with known token usage
    processing_logs = {
        "documents": {
            "doc1.pdf": {
                "token_usage": {"prompt_tokens": 1000, "completion_tokens": 2000},
                "model": "gpt-4o",
            },
            "doc2.pdf": {"token_usage": {"prompt_tokens": 800, "completion_tokens": 1500}, "model": "gpt-4o"},
        }
    }

    # Calculate total costs
    result = calculator.calculate_total_actual_costs(
        analyzed_documents=[analyzed_doc1, analyzed_doc2], processing_logs=processing_logs
    )

    # Assert structure
    assert hasattr(result, "total_actual_cost")
    assert hasattr(result, "service_costs")
    assert isinstance(result.total_actual_cost, float)
    assert isinstance(result.service_costs, list)
    assert len(result.service_costs) == 2

    # Assert aggregation
    calculated_total = sum(cost.cost for cost in result.service_costs)
    assert abs(result.total_actual_cost - calculated_total) < 0.0001

    # Assert each service cost has required keys
    for cost in result.service_costs:
        assert hasattr(cost, "service_name")
        assert hasattr(cost, "cost")
        assert hasattr(cost, "operation_type")
        assert cost.cost >= 0  # Non-negative costs
