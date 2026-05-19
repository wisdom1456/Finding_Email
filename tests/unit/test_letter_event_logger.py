"""Unit tests for the letter event logger.

The logger writes to letter_generation_events. Critical property: it must
NEVER raise out into letter generation code paths — if logging fails, the
letter still ships. Tests pin both the happy path and the swallow-errors
behavior.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from legal_portal.services.observability.letter_event_logger import (
    LetterEventLogger,
    summarize_qa,
)


class _FakeQuery:
    """Mimics the supabase-py chained query interface."""

    def __init__(self, table_name: str, log: List[Dict[str, Any]]):
        self._table = table_name
        self._log = log
        self._payload: Dict[str, Any] = {}
        self._operation: str = ""
        self._filters: List[tuple[str, Any]] = []

    def insert(self, payload):
        self._operation = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._operation = "update"
        self._payload = payload
        return self

    def eq(self, key, value):
        self._filters.append((key, value))
        return self

    def execute(self):
        self._log.append({
            "table": self._table,
            "op": self._operation,
            "payload": self._payload,
            "filters": list(self._filters),
        })
        # Return the inserted row with a fake id for INSERTs
        if self._operation == "insert":
            row = {**self._payload, "id": "evt-fake-id"}
            return SimpleNamespace(data=[row])
        return SimpleNamespace(data=[])


class _FakeSupabase:
    def __init__(self):
        self.log: List[Dict[str, Any]] = []

    def table(self, table_name):
        return _FakeQuery(table_name, self.log)


class _ExplodingSupabase:
    """Raises on any DB interaction — used to prove the logger swallows errors."""

    def table(self, _table_name):
        raise RuntimeError("DB unreachable")


def test_begin_inserts_requested_row_and_returns_event_id():
    sb = _FakeSupabase()
    logger = LetterEventLogger(sb)
    event_id = logger.begin(
        user_id="user-1",
        case_id="case-1",
        analysis_id="analysis-1",
        letter_type="findings",
    )
    assert event_id == "evt-fake-id"
    assert len(sb.log) == 1
    inserted = sb.log[0]
    assert inserted["table"] == "letter_generation_events"
    assert inserted["op"] == "insert"
    assert inserted["payload"]["status"] == "requested"
    assert inserted["payload"]["user_id"] == "user-1"
    assert inserted["payload"]["letter_type"] == "findings"


def test_complete_updates_event_to_completed_with_qa_passed_true_when_clean():
    sb = _FakeSupabase()
    logger = LetterEventLogger(sb)
    logger.complete(
        "evt-1",
        qa_summary={
            "term_explainer_passed": True,
            "evidence_linkage_score": 0.9,
            "demand_specificity_passed": None,
            "unsupported_assertion_flags": [],
        },
        duration_ms=42000,
    )
    update_call = next(c for c in sb.log if c["op"] == "update")
    assert update_call["payload"]["status"] == "completed"
    assert update_call["payload"]["qa_passed"] is True
    assert update_call["payload"]["duration_ms"] == 42000
    assert update_call["filters"] == [("id", "evt-1")]


def test_complete_marks_qa_passed_false_when_term_explainer_failed():
    sb = _FakeSupabase()
    logger = LetterEventLogger(sb)
    logger.complete(
        "evt-1",
        qa_summary={
            "term_explainer_passed": False,
            "evidence_linkage_score": 0.9,
            "unsupported_assertion_flags": [],
        },
    )
    update = next(c for c in sb.log if c["op"] == "update")
    assert update["payload"]["qa_passed"] is False


def test_complete_marks_qa_passed_false_when_evidence_linkage_low():
    sb = _FakeSupabase()
    logger = LetterEventLogger(sb)
    logger.complete(
        "evt-1",
        qa_summary={
            "term_explainer_passed": True,
            "evidence_linkage_score": 0.1,
            "unsupported_assertion_flags": [],
        },
    )
    update = next(c for c in sb.log if c["op"] == "update")
    assert update["payload"]["qa_passed"] is False


def test_complete_marks_qa_passed_false_when_unsupported_assertions_present():
    sb = _FakeSupabase()
    logger = LetterEventLogger(sb)
    logger.complete(
        "evt-1",
        qa_summary={
            "term_explainer_passed": True,
            "evidence_linkage_score": 0.9,
            "unsupported_assertion_flags": ["something_failed"],
        },
    )
    update = next(c for c in sb.log if c["op"] == "update")
    assert update["payload"]["qa_passed"] is False


def test_complete_qa_passed_null_when_no_checks_ran():
    sb = _FakeSupabase()
    logger = LetterEventLogger(sb)
    logger.complete("evt-1", qa_summary=None)
    update = next(c for c in sb.log if c["op"] == "update")
    assert update["payload"]["qa_passed"] is None


def test_fail_updates_event_to_failed_with_error():
    sb = _FakeSupabase()
    logger = LetterEventLogger(sb)
    logger.fail("evt-1", error="Model returned empty", duration_ms=5000)
    update = next(c for c in sb.log if c["op"] == "update")
    assert update["payload"]["status"] == "failed"
    assert update["payload"]["error"] == "Model returned empty"
    assert update["payload"]["duration_ms"] == 5000


def test_begin_swallows_db_errors_and_returns_none():
    # Critical: logger failures must not break letter generation
    logger = LetterEventLogger(_ExplodingSupabase())
    event_id = logger.begin(
        user_id="user-1",
        case_id="case-1",
        analysis_id="analysis-1",
        letter_type="findings",
    )
    assert event_id is None  # No exception raised


def test_complete_swallows_db_errors():
    logger = LetterEventLogger(_ExplodingSupabase())
    # Must not raise, even with a fake event_id
    logger.complete("evt-1", qa_summary={})


def test_fail_swallows_db_errors():
    logger = LetterEventLogger(_ExplodingSupabase())
    logger.fail("evt-1", error="anything")


def test_complete_and_fail_no_op_when_event_id_is_none():
    """If begin() returned None (because logging was disabled or DB was
    down), complete() and fail() must do nothing — no spurious updates."""
    sb = _FakeSupabase()
    logger = LetterEventLogger(sb)
    logger.complete(None, qa_summary={})  # type: ignore[arg-type]
    logger.fail(None, error="ignored")  # type: ignore[arg-type]
    assert sb.log == []  # No DB ops attempted


def test_summarize_qa_returns_none_for_empty_input():
    assert summarize_qa(None) is None
    assert summarize_qa({}) is None


def test_summarize_qa_returns_true_when_all_checks_pass():
    assert summarize_qa({
        "term_explainer_passed": True,
        "evidence_linkage_score": 0.9,
        "unsupported_assertion_flags": [],
    }) is True


def test_summarize_qa_demand_specificity_failed_marks_false():
    assert summarize_qa({
        "term_explainer_passed": True,
        "demand_specificity_passed": False,
        "evidence_linkage_score": 0.9,
    }) is False
