"""Unit tests for markdown cleanup helpers."""

from __future__ import annotations

from legal_portal.utils.markdown_utils import clean_markdown_response


def test_clean_markdown_response_removes_markdown_fence():
    """It should strip markdown code fences while preserving content."""
    raw = "```markdown\n## Heading\n\nBody text.\n```"
    cleaned = clean_markdown_response(raw)
    assert cleaned == "## Heading\n\nBody text."


def test_clean_markdown_response_removes_html_fence():
    """It should strip html code fences while preserving html content."""
    raw = "```html\n<p>Test</p>\n```"
    cleaned = clean_markdown_response(raw)
    assert cleaned == "<p>Test</p>"


def test_clean_markdown_response_returns_empty_for_empty_input():
    """It should return an empty string for empty input."""
    assert clean_markdown_response("") == ""
