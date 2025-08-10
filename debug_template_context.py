#!/usr/bin/env python3
"""
Debug script to test the Jinja2 template context issue
"""

from __future__ import annotations

from jinja2 import DictLoader, Environment

from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")


# Test function
def test_format_function(video_data):
    return f"<p>Test formatting for video: {video_data.get('name', 'unknown')}</p>"


# Template with the current incorrect call
template_current = """
Video Analysis: {{ format_video_analysis(video)|safe }}
"""

# Template with the corrected call
template_fixed = """
Video Analysis: {{ results.format_video_analysis(video)|safe }}
"""

# Test data
video_test_data = {"name": "test_video.mp4"}
template_context = {
    "format_video_analysis": test_format_function,
    "video": video_test_data,
}

# Test Jinja2 environment
env = Environment(
    loader=DictLoader({"current": template_current, "fixed": template_fixed})
)

logger.info("=== TESTING TEMPLATE CONTEXT ACCESS ===")

# Test 1: Current broken approach
logger.info("\n1. Testing current template call (should fail):")
try:
    template = env.get_template("current")
    result = template.render(
        video=video_test_data, format_video_analysis=test_format_function
    )
    logger.info(f"SUCCESS: {result}")
except Exception as e:
    logger.error(f"FAILED: {e}")

# Test 2: Proposed fix
logger.info("\n2. Testing fixed template call (should work):")
try:
    template = env.get_template("fixed")
    result = template.render(results=template_context, video=video_test_data)
    logger.info(f"SUCCESS: {result}")
except Exception as e:
    logger.error(f"FAILED: {e}")

logger.info("\n=== DIAGNOSIS COMPLETE ===")
