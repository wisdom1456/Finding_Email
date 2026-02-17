"""Helpers for matching document names against user blacklist rules."""

from __future__ import annotations

import re
from typing import Iterable, List

_WHITESPACE_RE = re.compile(r"\s+")
_EXTENSION_RE = re.compile(r"\.[a-z0-9]{1,10}$", re.IGNORECASE)
_TRAILING_PARENS_RE = re.compile(r"\s*\([^)]*\)\s*$")


def normalize_blacklist_text(value: str) -> str:
    """Normalize user-provided text for resilient matching."""
    if not value:
        return ""

    normalized = value.lower().replace("_", " ").replace("-", " ")
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def strip_file_extension(value: str) -> str:
    """Remove a trailing file extension from a filename-like string."""
    if not value:
        return ""
    return _EXTENSION_RE.sub("", value).strip()


def to_canonical_blacklist_term(value: str) -> str:
    """Create a canonical blacklist term by removing trailing parenthetical suffixes.

    Example:
        "Attorney Representation Agreement (Client Name).pdf"
        -> "attorney representation agreement"
    """
    canonical = normalize_blacklist_text(strip_file_extension(value))
    if not canonical:
        return ""

    previous = None
    while canonical and canonical != previous:
        previous = canonical
        canonical = _TRAILING_PARENS_RE.sub("", canonical).strip()

    return canonical.strip(" -_:;,.")


def _term_variants(value: str) -> List[str]:
    variants: List[str] = []
    for candidate in (
        normalize_blacklist_text(value),
        normalize_blacklist_text(strip_file_extension(value)),
        to_canonical_blacklist_term(value),
    ):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def derive_blacklist_rule(value: str) -> str:
    """Derive a generalized rule from a concrete document name."""
    canonical = to_canonical_blacklist_term(value)
    if canonical:
        return canonical
    return normalize_blacklist_text(strip_file_extension(value))


def is_name_blacklisted(name: str, blacklist: Iterable[str] | None) -> bool:
    """Return True when ``name`` matches any rule in ``blacklist``."""
    if not name or not blacklist:
        return False

    normalized_name = normalize_blacklist_text(name)
    normalized_name_no_ext = normalize_blacklist_text(strip_file_extension(name))
    canonical_name = to_canonical_blacklist_term(name)

    for rule in blacklist:
        if not rule:
            continue

        for variant in _term_variants(rule):
            if (
                normalized_name.startswith(variant)
                or normalized_name_no_ext.startswith(variant)
                or (canonical_name and canonical_name.startswith(variant))
            ):
                return True

    return False
