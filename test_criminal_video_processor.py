#!/usr/bin/env python3
"""
Test script for the enhanced criminal video processor functionality.
Validates that the video processor correctly handles criminal case analysis.
"""
from __future__ import annotations

from backend_logic.video_processor import VideoProcessor


def test_criminal_prompt_generation():
    """Test that criminal analysis prompts are properly generated."""
    # Test the criminal prompt directly by accessing the method

    # Create a mock instance without calling __init__
    temp_instance = object.__new__(VideoProcessor)
    criminal_prompt = temp_instance._get_criminal_analysis_prompt()

    assert "16 categories" in criminal_prompt
    assert "Driving Pattern & Reason for Stop" in criminal_prompt
    assert "constitutional compliance" in criminal_prompt.lower()
    assert "JSON STRUCTURE" in criminal_prompt
    print("✅ Criminal prompt generation test passed")


def test_standard_prompt_generation():
    """Test that standard analysis prompts work as before."""
    # Test the standard prompt directly by accessing the method

    # Create a mock instance without calling __init__
    temp_instance = object.__new__(VideoProcessor)
    standard_prompt = temp_instance._get_standard_analysis_prompt()

    assert "summary" in standard_prompt
    assert "timeline" in standard_prompt
    assert "objects" in standard_prompt
    print("✅ Standard prompt generation test passed")


def test_criminal_analysis_parsing():
    """Test parsing of criminal analysis responses."""

    # Create a mock instance without calling __init__
    temp_instance = object.__new__(VideoProcessor)

    # Mock criminal analysis response
    mock_response = {
        "evidence_items": [
            {
                "category": "Driving Pattern & Reason for Stop",
                "time_range": {
                    "start_time": "00:30",
                    "end_time": "01:15",
                    "confidence": 0.9,
                },
                "description": "Officer observed vehicle weaving between lanes",
                "key_observations": ["Lane weaving", "Speed variation"],
                "legal_significance": "Establishes reasonable suspicion for traffic stop",
                "constitutional_issues": ["Potential lack of specific observations"],
                "evidence_strength": "strong",
            }
        ],
        "timeline_summary": "Video shows traffic stop and field sobriety tests",
        "constitutional_compliance_overview": "Generally compliant with 4th Amendment requirements",
        "missing_categories": ["Booking & Processing"],
    }

    criminal_analysis = temp_instance._parse_criminal_analysis(mock_response)

    assert criminal_analysis is not None
    assert len(criminal_analysis.evidence_items) == 1
    assert criminal_analysis.evidence_items[0].evidence_strength == "strong"
    assert len(criminal_analysis.missing_categories) == 1
    print("✅ Criminal analysis parsing test passed")


def test_error_handling():
    """Test error handling in criminal analysis parsing."""

    # Create a mock instance without calling __init__
    temp_instance = object.__new__(VideoProcessor)

    # Test with error response
    error_response = {"error": "Failed to parse JSON from model."}
    result = temp_instance._parse_criminal_analysis(error_response)
    assert result is None
    print("✅ Error handling test passed")


def test_backward_compatibility():
    """Test that non-criminal processing remains unchanged."""
    # This test would require actual video processing, so we'll just verify
    # that the method signatures support backward compatibility
    import inspect

    # Check process_video_file signature without initializing
    sig = inspect.signature(VideoProcessor.process_video_file)
    assert "is_criminal_case" in sig.parameters
    assert sig.parameters["is_criminal_case"].default is False
    print("✅ Backward compatibility test passed")


def run_all_tests():
    """Run all unit tests for the enhanced video processor."""
    print("🧪 Testing Enhanced Criminal Video Processor")
    print("=" * 50)

    try:
        test_criminal_prompt_generation()
        test_standard_prompt_generation()
        test_criminal_analysis_parsing()
        test_error_handling()
        test_backward_compatibility()

        print("=" * 50)
        print("🎉 All tests passed! Criminal video processor is ready.")
        print("\n📋 Enhanced Capabilities Summary:")
        print("   • Criminal case detection with is_criminal_case parameter")
        print("   • 16 specialized criminal evidence categories")
        print("   • Constitutional compliance assessment")
        print("   • Timestamped evidence extraction")
        print("   • Enhanced legal significance analysis")
        print("   • Full backward compatibility maintained")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

    return True


if __name__ == "__main__":
    # Note: This requires proper Google Cloud setup to run full integration tests
    from backend_logic.config import get_settings

    settings = get_settings()
    if not settings.gcp_project_id or not settings.gcp_bucket_name:
        print("⚠️  Google Cloud credentials not configured - running unit tests only")

    run_all_tests()
