#!/usr/bin/env python3
"""Test script to verify video analysis formatting functionality."""

from __future__ import annotations

import os
import sys

from openai import OpenAI
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.utils.data_models import VideoInsight
from backend_logic.email_generator import EmailGenerator


def test_video_analysis_formatting():
    """Test the video analysis formatting function."""

    # Create a mock OpenAI client (we won't actually call the API)
    mock_client = OpenAI(api_key="test-key")

    # Create the email generator
    email_generator = EmailGenerator(mock_client)

    # Create a test video insight with typical Vertex AI response structure
    test_video_insight = VideoInsight(
        file_name="test_video.mov",
        insights={
            "summary": "The video shows a significant water leak on the floor of what appears to be a bedroom and connecting bathroom area. The extent of the water damage is substantial, with puddles visible across multiple rooms.",
            "timeline": [
                {
                    "timestamp": "00:00",
                    "event": "Initial view of a bedroom floor, showing a large puddle of water near the center and extending towards the bed",
                },
                {
                    "timestamp": "00:08",
                    "event": "Camera pans across the wet floor, showing the extent of the water in the bedroom area",
                },
                {
                    "timestamp": "00:13",
                    "event": "Camera moves towards a bathroom entrance, revealing more water on the floor",
                },
                {
                    "timestamp": "00:19",
                    "event": "Close-up view of the water on the floor near a cabinet/dresser, with reflections visible",
                },
                {
                    "timestamp": "00:24",
                    "event": "A person's foot in a brown sandal appears near the water, indicating the scale of the flooding",
                },
                {
                    "timestamp": "00:28",
                    "event": "View of a soaked bath mat next to the toilet, confirming the water has reached the bathroom area",
                },
                {
                    "timestamp": "00:30",
                    "event": "Audible verbal reaction: 'Oh fucking great, that's the first.'",
                },
            ],
            "objects": [
                {"object": "Wooden floor", "timestamp": "00:00 - 00:34"},
                {"object": "Water puddle/leak", "timestamp": "00:00 - 00:34"},
                {"object": "Bed", "timestamp": "00:00 - 00:09"},
                {"object": "Nightstand", "timestamp": "00:00 - 00:09"},
                {"object": "Window", "timestamp": "00:03 - 00:05"},
                {"object": "Dresser/Cabinet", "timestamp": "00:04 - 00:27"},
                {"object": "Toilet", "timestamp": "00:14 - 00:15, 00:31 - 00:34"},
                {"object": "Bath mat (wet)", "timestamp": "00:15 - 00:31"},
                {
                    "object": "Person's foot in sandal",
                    "timestamp": "00:11 - 00:13, 00:24 - 00:27",
                },
            ],
            "content_moderation": "The video contains mild language ('fucking') indicating frustration. No other sensitive content is present.",
        },
        transcript="",
        labels=["water damage", "flooding", "interior", "residential"],
        objects=["wooden floor", "water", "bed", "toilet"],
        text_annotations=[],
        duration=34.0,
        confidence=0.95,
    )

    # Test the formatting function
    formatted_output = email_generator.format_video_analysis_for_appendix(
        test_video_insight
    )

logger.info('=== VIDEO ANALYSIS FORMATTING TEST ===')
logger.info('\nOriginal insights structure:')
logger.info(f'Type: {type(test_video_insight.insights)}')
logger.info(f'Keys: {(list(test_video_insight.insights.keys()) if isinstance(test_video_insight.insights, dict) else 'N/A')}')
        f"Keys: {list(test_video_insight.insights.keys()) if isinstance(test_video_insight.insights, dict) else 'N/A'}"
    )

logger.info('\nFormatted output:')
logger.info(formatted_output)

    # Verify the output contains expected elements
    expected_elements = [
        "Summary:",
        "Timeline:",
        "Objects Detected:",
        "Content Moderation:",
        "• 00:00 -",  # Timeline bullet point
        "• Wooden floor (",  # Object with timestamp
    ]

logger.info('\n=== VALIDATION RESULTS ===')
    all_passed = True
    for element in expected_elements:
        if element in formatted_output:
logger.info(f"✅ PASS: Found '{element}'")
        else:
logger.info(f"❌ FAIL: Missing '{element}'")
            all_passed = False

    # Check that raw dictionary format is NOT present
    raw_dict_indicators = ["'summary':", "'timeline':", "'objects':"]
    for indicator in raw_dict_indicators:
        if indicator in formatted_output:
logger.debug(f"❌ FAIL: Found raw dictionary format '{indicator}'")
            all_passed = False
        else:
logger.debug(f"✅ PASS: No raw dictionary format '{indicator}'")

    if all_passed:
logger.info('\n🎉 ALL TESTS PASSED! Video analysis formatting is working correctly.')
        return True
logger.error('\n❌ SOME TESTS FAILED! Please check the formatting function.')
    return False


def test_edge_cases():
    """Test edge cases for the formatting function."""

    # Create a mock OpenAI client
    mock_client = OpenAI(api_key="test-key")
    email_generator = EmailGenerator(mock_client)

logger.info('\n=== EDGE CASE TESTS ===')

    # Test 1: Empty insights
    empty_video = VideoInsight(
        file_name="empty_video.mov",
        insights={},
        transcript="",
        labels=[],
        objects=[],
        text_annotations=[],
        duration=0.0,
        confidence=0.0,
    )

    result1 = email_generator.format_video_analysis_for_appendix(empty_video)
logger.info('Test 1 - Empty insights:')
logger.info(f'Result: {result1}')

    # Test 2: String insights (preserved/summarized case)
    string_video = VideoInsight(
        file_name="string_video.mov",
        insights="Video analysis summary not available",
        transcript="",
        labels=[],
        objects=[],
        text_annotations=[],
        duration=0.0,
        confidence=0.0,
    )

    result2 = email_generator.format_video_analysis_for_appendix(string_video)
logger.info('\nTest 2 - String insights:')
logger.info(f'Result: {result2}')

    # Test 3: Missing video insight object
    try:
        result3 = email_generator.format_video_analysis_for_appendix(None)
logger.info(f'\nTest 3 - None input: {result3}')
    except Exception as e:
logger.error(f'\nTest 3 - None input: Exception caught: {e}')

logger.info('✅ Edge case tests completed.')


if __name__ == "__main__":
logger.info('Testing video analysis formatting...')
    success = test_video_analysis_formatting()
    test_edge_cases()

    if success:
logger.info('\n✅ Video analysis formatting is ready for production!')
        sys.exit(0)
    else:
logger.info('\n❌ Video analysis formatting needs fixes.')
        sys.exit(1)
