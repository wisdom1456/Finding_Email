"""Utilities for normalizing AI-generated markdown responses."""

from __future__ import annotations

import re


def clean_markdown_response(response_text: str) -> str:
    """Clean AI response text to extract usable markdown content."""
    if not response_text:
        return ""

    cleaned = response_text.strip()

    # Remove opening code fences with optional language identifiers.
    cleaned = re.sub(r"^\s*```(?:html|markdown|md)?\s*\n?", "", cleaned, flags=re.MULTILINE)

    # Remove trailing code fences.
    cleaned = re.sub(r"\n?\s*```\s*$", "", cleaned, flags=re.MULTILINE)

    # Remove any additional stray code fences.
    cleaned = re.sub(r"```(?:html|markdown|md)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?\s*```", "", cleaned)

    return cleaned.strip()
