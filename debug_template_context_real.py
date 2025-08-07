#!/usr/bin/env python3
"""
Debug script to test the exact Jinja2 template context issue as it occurs in the real application
"""

from __future__ import annotations

from jinja2 import DictLoader, Environment


# Test function mimicking the real format_video_analysis_for_appendix method
def test_format_function(video_data):
    return f"<p>Real app test formatting for video: {video_data.get('file_name', 'unknown')}</p>"


# Template exactly as it appears in document_appendix.jinja2
template_real = """
{% if results.analysis and results.analysis.video_insights %}
    {% for video in results.analysis.video_insights %}
        <div>Video: {{ video.file_name }}</div>
        <div>Analysis: {{ format_video_analysis(video)|safe }}</div>
    {% endfor %}
{% endif %}
"""

# Template with the corrected call
template_fixed = """
{% if results.analysis and results.analysis.video_insights %}
    {% for video in results.analysis.video_insights %}
        <div>Video: {{ video.file_name }}</div>
        <div>Analysis: {{ results.format_video_analysis(video)|safe }}</div>
    {% endfor %}
{% endif %}
"""

# Mock data structure matching the real application
video_test_data = {
    "file_name": "test_video.mp4",
    "insights": {"summary": "Test analysis"},
}
analysis_data = {"video_insights": [video_test_data]}

# Template context exactly as passed in email_generator.py
template_context = {
    "analysis": analysis_data,
    "generated_letter": {},
    "current_date": "2025-08-05",
    "format_video_analysis": test_format_function,
}

# Test Jinja2 environment
env = Environment(loader=DictLoader({"real": template_real, "fixed": template_fixed}))

print("=== TESTING REAL APPLICATION TEMPLATE CONTEXT ===")

# Test 1: Current broken approach (as it is in document_appendix.jinja2)
print("\n1. Testing current real template call (should fail):")
try:
    template = env.get_template("real")
    # Render exactly as in email_generator.py line 272
    result = template.render(
        results=template_context, current_date=template_context["current_date"]
    )
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"FAILED: {e}")

# Test 2: Proposed fix
print("\n2. Testing fixed template call (should work):")
try:
    template = env.get_template("fixed")
    # Render exactly as in email_generator.py line 272
    result = template.render(
        results=template_context, current_date=template_context["current_date"]
    )
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== REAL APPLICATION DIAGNOSIS COMPLETE ===")
