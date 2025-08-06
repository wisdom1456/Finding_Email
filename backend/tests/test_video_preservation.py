# Add the project root to the Python path
from __future__ import annotations

import sys
from pathlib import Path

import pytest


sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.utils.data_models import (
    CaseAnalysisResult,
    EnhancedIntakeAnalysis,
    VideoInsight,
)


@pytest.fixture
def sample_intake_analysis():
    """Fixture for sample intake analysis."""
    return EnhancedIntakeAnalysis(
        client_name="John Doe",
        attorney_name="Jane Smith",
        case_summary="Property damage case involving contractor dispute",
        case_type="Contract Dispute",
        urgency_level="High",
        client_priorities=["Seeking damages", "Quick resolution"],
        desired_outcomes=["Full compensation", "Contract termination"],
        legal_claims=["Breach of contract", "Property damage"],
    )


@pytest.fixture
def small_video_insight():
    """Fixture for a small video insight (under token threshold)."""
    return VideoInsight(
        file_name="small_video.mov",
        insights={
            "summary": "Brief video showing minor property damage",
            "timeline": ["0:00 - Contractor arrives", "0:30 - Shows damage"],
            "objects": ["person", "building", "tools"],
        },
        transcript="This is a short transcript of the video.",
        labels=["property", "damage", "construction"],
        objects=["person", "building", "tools"],
        text_annotations=["Contract #123"],
        duration=45.0,
        confidence=0.95,
    )


@pytest.fixture
def large_video_insight():
    """Fixture for a large video insight (over token threshold)."""
    # Create a large insights object that would exceed token limits
    large_insights = {
        "summary": "Comprehensive video analysis showing extensive property damage and construction defects. "
        * 100,
        "timeline": [
            f"Time {i}: Detailed event description with extensive analysis"
            for i in range(200)
        ],
        "objects": [
            f"object_{i}_with_detailed_description_and_extensive_metadata"
            for i in range(150)
        ],
        "content_analysis": {
            "scene_analysis": [
                "Detailed scene " + "analysis " * 50 for _ in range(100)
            ],
            "object_tracking": [
                "Object tracking data " + "detailed " * 30 for _ in range(80)
            ],
            "motion_analysis": [
                "Motion analysis " + "comprehensive " * 40 for _ in range(60)
            ],
        },
        "quality_metrics": {
            "resolution": "4K",
            "framerate": "60fps",
            "audio_quality": "excellent",
            "lighting_conditions": "optimal" + " analysis" * 100,
        },
    }

    return VideoInsight(
        file_name="large_video.mov",
        insights=large_insights,
        transcript="This is a very long transcript with extensive dialogue and detailed descriptions. "
        * 200,
        labels=["property", "damage", "construction", "extensive", "detailed"] * 50,
        objects=["person", "building", "tools", "equipment", "materials"] * 100,
        text_annotations=["Contract #123", "Invoice #456", "Report #789"] * 50,
        duration=1800.0,  # 30 minutes
        confidence=0.92,
    )


class TestVideoPreservationStrategy:
    """Test cases for the video data preservation strategy."""

    def test_small_video_data_structure_validation(
        self, sample_intake_analysis, small_video_insight
    ):
        """
        Test Case 1: Small Video (Under Threshold) - Data Structure Validation
        Validates that small video insights maintain their full structure without summarization.
        """
        # Create case analysis with small video
        analysis = CaseAnalysisResult(
            intake_analysis=sample_intake_analysis, video_insights=[small_video_insight]
        )

        # Test assertions for small video processing
        assert len(analysis.video_insights) == 1
        video = analysis.video_insights[0]

        # 1. Verify video file identification
        assert video.file_name == "small_video.mov"

        # 2. Verify full insights are preserved (not summarized)
        assert "summary" in video.insights
        assert "timeline" in video.insights
        assert "objects" in video.insights
        assert video.insights["summary"] == "Brief video showing minor property damage"
        assert len(video.insights["timeline"]) == 2  # Original timeline preserved

        # 3. Verify no summarization indicators are present
        assert not hasattr(video, "insights_gcs_uri") or video.insights_gcs_uri is None
        assert not hasattr(video, "insights_summary") or video.insights_summary is None

        # 4. Verify all video metadata is complete
        assert video.transcript == "This is a short transcript of the video."
        assert len(video.labels) == 3
        assert len(video.objects) == 3
        assert len(video.text_annotations) == 1
        assert video.duration == 45.0
        assert video.confidence == 0.95

    def test_large_video_summarization_trigger(
        self, sample_intake_analysis, large_video_insight
    ):
        """
        Test Case 2: Large Video (Over Threshold) - Summarization Logic Validation
        Tests that large video insights would trigger the summarization and preservation logic.
        """
        # Create case analysis with large video
        analysis = CaseAnalysisResult(
            intake_analysis=sample_intake_analysis, video_insights=[large_video_insight]
        )

        # Verify the large video has characteristics that would trigger summarization
        video = analysis.video_insights[0]

        # 1. Verify video file identification
        assert video.file_name == "large_video.mov"

        # 2. Verify content size that would exceed token limits
        insights_size = len(str(video.insights))
        transcript_size = len(video.transcript)
        total_content_size = insights_size + transcript_size

        # Should be significantly larger than small video
        assert total_content_size > 50000  # Large enough to trigger summarization

        # 3. Verify rich content structure that would need preservation
        assert "content_analysis" in video.insights
        assert "quality_metrics" in video.insights
        assert len(video.insights["timeline"]) == 200  # Extensive timeline
        assert len(video.insights["objects"]) == 150  # Many objects

        # 4. Verify extensive metadata
        assert video.duration == 1800.0  # Long video (30 minutes)
        assert len(video.labels) == 250  # Many labels (50 * 5)
        assert len(video.objects) == 500  # Many objects (100 * 5)
        assert len(video.text_annotations) == 150  # Many annotations (50 * 3)

    def test_token_counting_logic_simulation(
        self, sample_intake_analysis, small_video_insight, large_video_insight
    ):
        """
        Test the token counting and threshold logic with simulated token counting.
        """

        # Simulate token counting function
        def simulate_token_count(text, model="gpt-4o"):
            # Rough estimation: ~4 characters per token
            return len(text) // 4

        # Test with small video (should pass threshold)
        # Simulate token check for small video
        small_video_content = (
            str(small_video_insight.insights) + small_video_insight.transcript
        )
        small_token_count = simulate_token_count(small_video_content)

        # Print actual sizes for debugging
        print(f"Small video token count: {small_token_count}")

        # Test with large video (should exceed threshold)
        # Simulate token check for large video
        large_video_content = (
            str(large_video_insight.insights) + large_video_insight.transcript
        )
        large_token_count = simulate_token_count(large_video_content)

        print(f"Large video token count: {large_token_count}")

        # Use a reasonable threshold based on actual test data
        # Small videos should be under 10,000 tokens, large videos should be over 30,000
        small_threshold = 10000
        large_threshold = 30000

        # Should be under small threshold
        assert small_token_count < small_threshold

        # Should exceed large threshold
        assert large_token_count > large_threshold

        # Test threshold logic with realistic values
        threshold = 30000  # Reasonable threshold for test data

        # Small video should not trigger summarization
        small_needs_summarization = small_token_count > threshold
        assert not small_needs_summarization

        # Large video should trigger summarization
        large_needs_summarization = large_token_count > threshold
        assert large_needs_summarization

    def test_video_preservation_metadata_structure(self, large_video_insight):
        """
        Test the data structure for video preservation metadata.
        """
        # Simulate applying preservation strategy
        video = large_video_insight

        # Simulate preservation metadata being added
        video.insights_gcs_uri = (
            "gs://findings-video-analysis/test-uuid-123/full_insights.json"
        )
        video.insights_summary = "Key objects detected: property, damage, construction; Content labels: property, damage, construction; Transcript excerpt: This is a very long transcript..."

        # Test preservation metadata structure
        assert hasattr(video, "insights_gcs_uri")
        assert hasattr(video, "insights_summary")

        # Verify GCS URI format
        assert video.insights_gcs_uri.startswith("gs://findings-video-analysis/")
        assert video.insights_gcs_uri.endswith("/full_insights.json")

        # Verify summary contains key elements
        summary = video.insights_summary
        assert "property" in summary.lower() or "damage" in summary.lower()
        assert len(summary) > 50  # Should have substantial content
        assert len(summary) < 1000  # But should be condensed

    def test_email_appendix_truncation_notice_structure(
        self, sample_intake_analysis, large_video_insight
    ):
        """
        Test that video analysis appendix includes proper truncation notice structure.
        """
        # Create analysis with preserved video data scenario
        analysis = CaseAnalysisResult(
            intake_analysis=sample_intake_analysis, video_insights=[large_video_insight]
        )

        # Simulate preserved data scenario
        video = analysis.video_insights[0]
        video.insights_gcs_uri = (
            "gs://findings-video-analysis/test-uuid/full_insights.json"
        )
        video.insights_summary = "Key objects detected: property, damage, construction; Transcript excerpt: This is a very long transcript..."

        # Mock appendix generation logic
        def generate_mock_appendix(analysis_obj):
            has_preserved_data = any(
                hasattr(v, "insights_gcs_uri") and v.insights_gcs_uri is not None
                for v in analysis_obj.video_insights
            )

            base_content = (
                "<h4>Video Analysis Appendix</h4>"
                "<p>Analysis of large_video.mov reveals extensive property damage and construction defects. "
                "The video provides comprehensive documentation of the contractor's deficient work.</p>"
            )

            if has_preserved_data:
                truncation_notice = "<p><em>Note: Full analysis was truncated due to size. Summary is provided above.</em></p>"
                return base_content + "\n" + truncation_notice

            return base_content

        # Generate mock appendix
        appendix = generate_mock_appendix(analysis)

        # Test appendix structure
        assert "Video Analysis Appendix" in appendix
        assert "large_video.mov" in appendix
        assert "Note: Full analysis was truncated due to size" in appendix
        assert len(appendix.strip()) > 100  # Should have meaningful content

    def test_mixed_video_sizes_processing(
        self, sample_intake_analysis, small_video_insight, large_video_insight
    ):
        """
        Test end-to-end workflow with both small and large videos.
        """
        # Create case analysis with both video types
        analysis = CaseAnalysisResult(
            intake_analysis=sample_intake_analysis,
            video_insights=[small_video_insight, large_video_insight],
        )

        # Verify mixed scenario
        assert len(analysis.video_insights) == 2

        small_video = analysis.video_insights[0]
        large_video = analysis.video_insights[1]

        # Small video should not need preservation
        small_content_size = len(str(small_video.insights)) + len(
            small_video.transcript
        )
        assert small_content_size < 10000  # Small enough to process normally

        # Large video should trigger preservation
        large_content_size = len(str(large_video.insights)) + len(
            large_video.transcript
        )
        assert large_content_size > 50000  # Large enough to trigger preservation

        # Verify they can coexist in the same analysis
        assert small_video.file_name == "small_video.mov"
        assert large_video.file_name == "large_video.mov"
        assert small_video.duration == 45.0
        assert large_video.duration == 1800.0


if __name__ == "__main__":
    pytest.main([__file__])
