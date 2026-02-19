"""Centralized type-safety utilities for handling untyped data from JSONB, LLM responses, and APIs.

The application ingests data from several schemaless sources:
  - Supabase JSONB columns (cases.metadata, cases.clio_matter_data, analysis_results.result)
  - LLM/OpenAI JSON responses (document summaries, strategies, analyses)
  - Frontend API request bodies

All of these can contain boolean values in fields expected to be strings.
Boolean True is truthy, so the common pattern `(dict.get("key") or "default")` fails:
  - `True or "default"` evaluates to `True`
  - `True.strip()` -> AttributeError: 'bool' object has no attribute 'strip'

These utilities provide a single, centralized fix applied at data boundaries.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def safe_str(value: Any, default: Optional[str] = None) -> Optional[str]:
    """Extract a string value from untyped data, rejecting booleans.

    Use this whenever extracting a value from a dict that originates from
    JSONB, LLM output, or an API request body.

    Args:
        value: The raw value (could be str, bool, int, None, etc.)
        default: Fallback if value is None, boolean, or empty string.

    Returns:
        A stripped string, or the default if value is not a usable string.

    Examples:
        >>> safe_str("hello")
        'hello'
        >>> safe_str(True)
        None
        >>> safe_str(True, "fallback")
        'fallback'
        >>> safe_str(None, "fallback")
        'fallback'
        >>> safe_str("")
        None
        >>> safe_str(123)
        '123'
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else default
    # Numeric or other types: convert to string
    text = str(value).strip()
    return text if text else default


def safe_str_required(value: Any, default: str) -> str:
    """Same as safe_str but always returns a non-None string.

    Args:
        value: The raw value.
        default: Fallback (must not be None).

    Returns:
        A stripped string, guaranteed non-None.
    """
    result = safe_str(value, default)
    return result if result is not None else default


def sanitize_dict_strings(data: Dict[str, Any], string_keys: list[str]) -> Dict[str, Any]:
    """Sanitize specific keys in a dict, converting booleans to None for string fields.

    Modifies the dict in-place and returns it for convenience.

    Args:
        data: Dictionary to sanitize (modified in-place).
        string_keys: List of keys that should be strings.

    Returns:
        The same dict with boolean values in string_keys replaced with None.
    """
    for key in string_keys:
        if key in data and isinstance(data[key], bool):
            data[key] = None
    return data


def sanitize_nested_dict(data: Any) -> Any:
    """Recursively sanitize a dict/list structure from JSONB, converting
    top-level boolean values in dicts to None when they appear alongside
    string values (heuristic: if key name doesn't start with 'is_', 'has_',
    'should_', 'can_', or end with '_enabled', '_active', '_flag').

    This is a best-effort heuristic for cleaning LLM output stored in JSONB.
    """
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            if isinstance(value, bool) and not _is_boolean_field_name(key):
                cleaned[key] = None
            elif isinstance(value, dict):
                cleaned[key] = sanitize_nested_dict(value)
            elif isinstance(value, list):
                cleaned[key] = sanitize_nested_dict(value)
            else:
                cleaned[key] = value
        return cleaned
    elif isinstance(data, list):
        return [sanitize_nested_dict(item) for item in data]
    return data


def _is_boolean_field_name(name: str) -> bool:
    """Check if a field name conventionally represents a boolean value."""
    lower = name.lower()
    boolean_prefixes = ("is_", "has_", "should_", "can_", "was_", "will_", "needs_", "force_", "allow_")
    boolean_suffixes = ("_enabled", "_active", "_flag", "_required", "_expected", "_recommended")
    if any(lower.startswith(p) for p in boolean_prefixes):
        return True
    if any(lower.endswith(s) for s in boolean_suffixes):
        return True
    # Also check camelCase equivalents
    camel_prefixes = ("is", "has", "should", "can", "was", "will", "needs", "force", "allow")
    if any(lower.startswith(p) and len(lower) > len(p) and lower[len(p)].isupper() for p in camel_prefixes):
        return True
    return False
