"""Extended tests for JsonProcessingService — JSON extraction and parsing."""

from __future__ import annotations

import json

from legal_portal.services.shared.json_processing_service import JsonProcessingService


def _service() -> JsonProcessingService:
    return JsonProcessingService(client=None, config={})  # type: ignore[arg-type]


def test_extract_json_from_markdown_fences():
    """Strips ```json fences and parses valid JSON."""
    service = _service()
    text = '```json\n{"key": "value", "count": 42}\n```'
    result = service._parse_json_block(text)

    assert result is not None
    assert result["key"] == "value"
    assert result["count"] == 42


def test_extract_json_handles_truncated():
    """Gracefully returns None on incomplete JSON."""
    service = _service()
    text = '{"key": "value", "nested": {'
    result = service._parse_json_block(text)

    assert result is None


def test_parse_json_block_plain_json():
    """Parses plain JSON without markdown fences."""
    service = _service()
    data = {"summary": "Test case", "issues": ["breach"]}
    text = json.dumps(data)
    result = service._parse_json_block(text)

    assert result is not None
    assert result["summary"] == "Test case"
    assert result["issues"] == ["breach"]


def test_parse_json_block_returns_none_for_non_dict():
    """Returns None when JSON parses to a non-dict type (e.g., array)."""
    service = _service()
    text = '["item1", "item2"]'
    result = service._parse_json_block(text)

    assert result is None
