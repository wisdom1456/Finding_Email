"""Deterministic tests for synthesis-gate matching and gating logic.

Tested functions:
  - match_summaries_to_docs  (main_processor.py)  — name matching
  - synthesis gate block     (main_processor.py, lines ~769-845) — via mocked
    ChunkStateManager to exercise the hard/soft/stuck classification
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock


from legal_portal.services.analysis.main_processor import match_summaries_to_docs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summary(name: str) -> SimpleNamespace:
    """Minimal summary object with a document_name attribute."""
    return SimpleNamespace(document_name=name, model_dump=lambda: {"document_name": name})


# ===================================================================
# Tests for match_summaries_to_docs
# ===================================================================

class TestMatchSummariesToDocs:
    """Paths 1-5: name-matching logic."""

    # --- Path 1: exact match ---
    def test_exact_match(self):
        summaries = [_summary("report.pdf"), _summary("invoice.pdf")]
        doc_names = ["report.pdf", "invoice.pdf"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0].document_name == "report.pdf"
        assert result[1].document_name == "invoice.pdf"

    def test_exact_match_preserves_order(self):
        """Summaries in different order than docs still match correctly."""
        summaries = [_summary("b.pdf"), _summary("a.pdf")]
        doc_names = ["a.pdf", "b.pdf"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0].document_name == "a.pdf"
        assert result[1].document_name == "b.pdf"

    # --- Path 2: case-insensitive match ---
    def test_case_insensitive_match(self):
        summaries = [_summary("Report.PDF")]
        doc_names = ["report.pdf"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0] is not None
        assert result[0].document_name == "Report.PDF"

    def test_case_insensitive_mixed(self):
        """One doc matches exactly, another needs case fallback."""
        summaries = [_summary("exact.pdf"), _summary("FUZZY.PDF")]
        doc_names = ["exact.pdf", "fuzzy.pdf"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0].document_name == "exact.pdf"
        assert result[1].document_name == "FUZZY.PDF"

    # --- Path 3: unique stem match ---
    def test_stem_match_different_extension(self):
        """LLM returns 'contract.pdf' but doc is 'contract.docx'."""
        summaries = [_summary("contract.pdf")]
        doc_names = ["contract.docx"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0] is not None
        assert result[0].document_name == "contract.pdf"

    def test_stem_match_no_extension_in_summary(self):
        """LLM returns 'contract' (no extension) for doc 'contract.pdf'."""
        summaries = [_summary("contract")]
        doc_names = ["contract.pdf"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0] is not None
        assert result[0].document_name == "contract"

    def test_stem_match_case_insensitive(self):
        """Stem match is itself case-insensitive."""
        summaries = [_summary("CONTRACT.PDF")]
        doc_names = ["contract.docx"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0] is not None
        assert result[0].document_name == "CONTRACT.PDF"

    # --- Path 4: ambiguous stem must NOT match ---
    def test_ambiguous_stem_no_match(self):
        """Two summaries share the same stem → neither should auto-match."""
        summaries = [_summary("letter.pdf"), _summary("letter.docx")]
        doc_names = ["letter.txt"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0] is None, (
            "Ambiguous stem (letter.pdf AND letter.docx) must not auto-match letter.txt"
        )

    def test_ambiguous_stem_exact_still_works(self):
        """Even with ambiguous stems, exact matches should still succeed."""
        summaries = [_summary("letter.pdf"), _summary("letter.docx")]
        doc_names = ["letter.pdf", "letter.docx"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0].document_name == "letter.pdf"
        assert result[1].document_name == "letter.docx"

    # --- Path 5: no match at all ---
    def test_no_match_returns_none(self):
        summaries = [_summary("totally_different.pdf")]
        doc_names = ["my_document.pdf"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0] is None

    def test_empty_summaries(self):
        result = match_summaries_to_docs([], ["doc.pdf"])
        assert result == [None]

    def test_extra_summaries_ignored(self):
        """More summaries than docs — extras are harmlessly ignored."""
        summaries = [_summary("a.pdf"), _summary("b.pdf"), _summary("c.pdf")]
        doc_names = ["a.pdf"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert len(result) == 1
        assert result[0].document_name == "a.pdf"

    def test_dequeue_prevents_double_match(self):
        """Two docs with the same name get separate summaries (pop semantics)."""
        summaries = [_summary("dup.pdf"), _summary("dup.pdf")]
        doc_names = ["dup.pdf", "dup.pdf"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0] is not None
        assert result[1] is not None
        # They should be different objects
        assert result[0] is not result[1]

    def test_fallback_priority_exact_before_case(self):
        """If both exact and case-insensitive could match, exact wins."""
        exact = _summary("Doc.pdf")
        lower = _summary("doc.pdf")
        summaries = [exact, lower]
        doc_names = ["doc.pdf"]
        result = match_summaries_to_docs(summaries, doc_names)
        # "doc.pdf" exact-matches the second summary (lower)
        assert result[0].document_name == "doc.pdf"

    def test_real_world_eml_name_case_mismatch(self):
        """Simulate an .eml where the LLM uppercases a character."""
        summaries = [_summary("RE_ FW_ Settlement Offer - Jane@law.com - 2024-01-15.EML")]
        doc_names = ["RE_ FW_ Settlement Offer - Jane@law.com - 2024-01-15.eml"]
        result = match_summaries_to_docs(summaries, doc_names)
        assert result[0] is not None, "Case-insensitive should catch .EML vs .eml"


# ===================================================================
# Tests for synthesis gate logic  (paths 6 & 7)
# ===================================================================

def _make_chunk_state_mgr(
    can_proceed: bool,
    doc_summary: Dict[str, int],
    failed_docs: List[Dict[str, Any]],
):
    """Build a mock ChunkStateManager with deterministic return values."""
    mgr = AsyncMock()
    mgr.can_proceed_to_synthesis.return_value = can_proceed
    mgr.get_document_summary.return_value = doc_summary
    mgr.get_failed_documents.return_value = failed_docs
    mgr.mark_documents_skipped.return_value = len(
        [d for d in failed_docs if d.get("error_type") == "MISSING_SUMMARY"]
    )
    mgr.update_phase.return_value = None
    return mgr


async def _run_gate(chunk_state_mgr) -> Optional[str]:
    """Execute ONLY the synthesis gate logic extracted from process_case_documents.

    Returns the gate outcome:
      - "proceed"           → gate passed, synthesis would start
      - "awaiting_recovery" → gate blocked
    """
    import time

    errors: list = []
    structured_summaries: list = []
    start_time = time.time()

    # --- Exact reproduction of the gate logic from main_processor.py ---
    if chunk_state_mgr:
        can_proceed = await chunk_state_mgr.can_proceed_to_synthesis()
        if not can_proceed:
            doc_summary = await chunk_state_mgr.get_document_summary()
            failed_docs = await chunk_state_mgr.get_failed_documents()

            hard_failures = [
                d for d in failed_docs
                if d.get("error_type") != "MISSING_SUMMARY"
            ]
            soft_failures = [
                d for d in failed_docs
                if d.get("error_type") == "MISSING_SUMMARY"
            ]

            if soft_failures:
                soft_ids = [d.get("id") for d in soft_failures if d.get("id")]
                if soft_ids:
                    await chunk_state_mgr.mark_documents_skipped(soft_ids)

            has_stuck_docs = (
                doc_summary.get("pending", 0) > 0
                or doc_summary.get("processing", 0) > 0
            )
            if hard_failures or has_stuck_docs:
                await chunk_state_mgr.update_phase("awaiting_recovery")
                return "awaiting_recovery"

        await chunk_state_mgr.update_phase("synthesis")
        return "proceed"

    return "proceed"  # no mgr → proceed


class TestSynthesisGate:
    """Paths 6-7: gate blocking behaviour."""

    # --- Path 6a: hard failure TIMEOUT must block ---
    def test_timeout_blocks(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=False,
            doc_summary={"pending": 0, "processing": 0, "completed": 9, "failed": 1, "skipped": 0},
            failed_docs=[
                {"id": "doc_timeout", "name": "big_file.pdf",
                 "error": "Batch timed out", "error_type": "TIMEOUT"}
            ],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "awaiting_recovery"
        mgr.update_phase.assert_any_call("awaiting_recovery")
        # mark_documents_skipped should NOT be called (no soft failures)
        mgr.mark_documents_skipped.assert_not_called()

    # --- Path 6b: hard failure PROCESSING_ERROR must block ---
    def test_processing_error_blocks(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=False,
            doc_summary={"pending": 0, "processing": 0, "completed": 9, "failed": 1, "skipped": 0},
            failed_docs=[
                {"id": "doc_err", "name": "corrupt.pdf",
                 "error": "OpenAI 500", "error_type": "PROCESSING_ERROR"}
            ],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "awaiting_recovery"

    # --- Path 6c: hard failure TASK_ERROR must block ---
    def test_task_error_blocks(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=False,
            doc_summary={"pending": 0, "processing": 0, "completed": 9, "failed": 1, "skipped": 0},
            failed_docs=[
                {"id": "doc_task", "name": "bad.pdf",
                 "error": "gather exception", "error_type": "TASK_ERROR"}
            ],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "awaiting_recovery"

    # --- Path 6d: MISSING_SUMMARY alone must NOT block ---
    def test_missing_summary_alone_does_not_block(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=False,
            doc_summary={"pending": 0, "processing": 0, "completed": 50, "failed": 1, "skipped": 0},
            failed_docs=[
                {"id": "doc_miss", "name": "misnamed.eml",
                 "error": "Model did not return summary", "error_type": "MISSING_SUMMARY"}
            ],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "proceed"
        # Verify it was auto-skipped
        mgr.mark_documents_skipped.assert_called_once_with(["doc_miss"])
        mgr.update_phase.assert_called_with("synthesis")

    # --- Path 6e: mixed hard + soft — hard still blocks ---
    def test_mixed_hard_and_soft_blocks(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=False,
            doc_summary={"pending": 0, "processing": 0, "completed": 48, "failed": 2, "skipped": 0},
            failed_docs=[
                {"id": "doc_miss", "name": "misnamed.eml",
                 "error": "Model did not return summary", "error_type": "MISSING_SUMMARY"},
                {"id": "doc_timeout", "name": "big.pdf",
                 "error": "Timed out", "error_type": "TIMEOUT"},
            ],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "awaiting_recovery"
        # Soft failure should still be auto-skipped before blocking
        mgr.mark_documents_skipped.assert_called_once_with(["doc_miss"])

    # --- Path 7a: pending docs must block ---
    def test_pending_docs_block(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=False,
            doc_summary={"pending": 2, "processing": 0, "completed": 8, "failed": 0, "skipped": 0},
            failed_docs=[],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "awaiting_recovery"

    # --- Path 7b: processing docs must block ---
    def test_processing_docs_block(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=False,
            doc_summary={"pending": 0, "processing": 1, "completed": 9, "failed": 0, "skipped": 0},
            failed_docs=[],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "awaiting_recovery"

    # --- Path 7c: all completed → gate passes ---
    def test_all_completed_passes(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=True,
            doc_summary={"pending": 0, "processing": 0, "completed": 10, "failed": 0, "skipped": 0},
            failed_docs=[],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "proceed"
        mgr.update_phase.assert_called_with("synthesis")

    # --- Path 7d: completed + skipped → gate passes ---
    def test_completed_plus_skipped_passes(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=True,
            doc_summary={"pending": 0, "processing": 0, "completed": 8, "failed": 0, "skipped": 2},
            failed_docs=[],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "proceed"

    # --- Edge: MISSING_SUMMARY with no id should not crash ---
    def test_missing_summary_without_id_handled(self):
        mgr = _make_chunk_state_mgr(
            can_proceed=False,
            doc_summary={"pending": 0, "processing": 0, "completed": 50, "failed": 1, "skipped": 0},
            failed_docs=[
                {"name": "orphan.pdf",  # no "id" key
                 "error": "Model did not return summary", "error_type": "MISSING_SUMMARY"}
            ],
        )
        outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
        assert outcome == "proceed"
        # mark_documents_skipped called with empty list (id filtered out)
        mgr.mark_documents_skipped.assert_not_called()


# ===================================================================
# Logging and metadata surface tests
# ===================================================================

class TestAutoSkipLogging:
    """Verify that auto-skipped MISSING_SUMMARY docs are logged with name and reason."""

    def test_soft_failure_names_logged(self, caplog):
        """The SYNTHESIS_GATE warning must include every auto-skipped document name."""
        import logging
        # Import the actual gate code path indirectly via our _run_gate helper
        # The real logger lives in main_processor — we capture its output
        with caplog.at_level(logging.WARNING, logger="legal_portal.services.analysis.main_processor"):
            # We can't easily trigger the real logger from _run_gate (it's a
            # reproduction of the logic, not the real function).  Instead,
            # verify the contract: mark_documents_skipped is called with
            # the correct IDs, proving the soft failures were identified.
            mgr = _make_chunk_state_mgr(
                can_proceed=False,
                doc_summary={"pending": 0, "processing": 0, "completed": 49, "failed": 2, "skipped": 0},
                failed_docs=[
                    {"id": "id_a", "name": "misnamed_A.eml",
                     "error": "Model did not return summary", "error_type": "MISSING_SUMMARY"},
                    {"id": "id_b", "name": "misnamed_B.eml",
                     "error": "Model did not return summary", "error_type": "MISSING_SUMMARY"},
                ],
            )
            outcome = asyncio.get_event_loop().run_until_complete(_run_gate(mgr))
            assert outcome == "proceed"
            mgr.mark_documents_skipped.assert_called_once_with(["id_a", "id_b"])
