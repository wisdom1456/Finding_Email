"""Per-document log for Clio import progress.

Accumulated inside the import progress payload so the throttled DB writer
persists the whole history — throttling delays entries (≤3 s) but never
loses them. See docs/superpowers/specs/2026-07-02-clio-import-doc-log-design.md.
"""
from __future__ import annotations

MAX_LOG_ENTRIES = 500
_NAME_MAX = 80
_REASON_MAX = 120


def append_entry(doc_log: list, index: int, name: str, size_bytes: int) -> dict:
    """Append a 'downloading' entry, enforce cap, return the entry."""
    entry = {
        "i": index,
        "name": (name or "Untitled Document")[:_NAME_MAX],
        "size_bytes": int(size_bytes or 0),
        "outcome": "downloading",
    }
    doc_log.append(entry)
    if len(doc_log) > MAX_LOG_ENTRIES:
        del doc_log[: len(doc_log) - MAX_LOG_ENTRIES]
    return entry


def set_outcome(entry: dict, outcome: str, reason: str | None = None) -> None:
    """outcome ∈ imported|skipped_small_image|duplicate|blacklisted|failed"""
    entry["outcome"] = outcome
    if outcome == "failed" and reason:
        entry["reason"] = reason[:_REASON_MAX]
