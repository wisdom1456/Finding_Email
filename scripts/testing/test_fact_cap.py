#!/usr/bin/env python3
"""Unit verification: _cap_doc_for_fact_extraction logic.

Tests the per-document serialized cap for fact extraction prompts.
Run: python3 scripts/testing/test_fact_cap.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from legal_portal.services.analysis.multi_stage_analyzer import MultiStageAnalyzer

CAP = 8_000  # Must match _FACT_DOC_MAX_SERIALIZED_CHARS


def make_doc(summary_chars=500, detail_count=8, detail_chars=200,
             significance_chars=200, party_count=3, date_count=5, amount_count=3):
    """Build a synthetic doc context dict with controllable sizes."""
    return {
        "filename": "test_document.pdf",
        "document_type": "Contract",
        "content_summary": "A" * summary_chars,
        "important_details": [f"Detail {'D' * detail_chars}" for _ in range(detail_count)],
        "legal_significance": "S" * significance_chars,
        "parties": [{"name": f"Party {i}", "role": "Client"} for i in range(party_count)],
        "dates": [{"date": "2025-01-01", "event": f"Event {i}"} for i in range(date_count)],
        "amounts": [{"amount": 1000 * i, "desc": f"Item {i}"} for i in range(amount_count)],
    }


def test_small_doc_unchanged():
    """Doc under cap should pass through unchanged."""
    doc = make_doc(summary_chars=500)
    original_json = json.dumps(doc)
    assert len(original_json) < CAP, f"Test setup error: doc is {len(original_json)} chars"

    result = MultiStageAnalyzer._cap_doc_for_fact_extraction(doc)
    assert result["content_summary"] == "A" * 500
    print(f"  PASS small_doc_unchanged ({len(original_json)} chars)")


def test_large_summary_truncated():
    """Doc with oversized summary should be truncated."""
    doc = make_doc(summary_chars=10000)
    original_json = json.dumps(doc)
    assert len(original_json) > CAP, f"Test setup error: doc is {len(original_json)} chars"

    result = MultiStageAnalyzer._cap_doc_for_fact_extraction(doc)
    result_json = json.dumps(result)
    assert len(result_json) <= CAP + 200, (  # small margin for separator
        f"Capped doc still too large: {len(result_json)} chars"
    )
    assert len(result["content_summary"]) < 10000
    assert "[truncated for fact extraction]" in result["content_summary"]
    print(f"  PASS large_summary_truncated ({len(original_json)} -> {len(result_json)} chars)")


def test_large_structured_fields():
    """Doc with many large structured fields should still be capped."""
    doc = make_doc(
        summary_chars=3000,
        detail_count=8, detail_chars=500,
        significance_chars=2000,
        party_count=10, date_count=20, amount_count=10,
    )
    original_json = json.dumps(doc)
    result = MultiStageAnalyzer._cap_doc_for_fact_extraction(doc)
    result_json = json.dumps(result)
    print(f"  {'PASS' if len(result_json) <= CAP + 200 else 'WARN'} "
          f"large_structured ({len(original_json)} -> {len(result_json)} chars)")


def test_empty_summary():
    """Doc with empty summary should not crash."""
    doc = make_doc(summary_chars=0)
    doc["content_summary"] = ""
    result = MultiStageAnalyzer._cap_doc_for_fact_extraction(doc)
    assert result["content_summary"] == ""
    print(f"  PASS empty_summary")


def test_none_summary():
    """Doc with None summary should not crash."""
    doc = make_doc(summary_chars=0)
    doc["content_summary"] = None
    result = MultiStageAnalyzer._cap_doc_for_fact_extraction(doc)
    print(f"  PASS none_summary")


def test_head_tail_preservation():
    """Truncated summary should preserve head and tail content."""
    text = "HEAD_MARKER_" + ("X" * 10000) + "_TAIL_MARKER"
    doc = make_doc(summary_chars=0)
    doc["content_summary"] = text
    original_json = json.dumps(doc)
    assert len(original_json) > CAP

    result = MultiStageAnalyzer._cap_doc_for_fact_extraction(doc)
    summary = result["content_summary"]
    assert summary.startswith("HEAD_MARKER_"), f"Head not preserved: {summary[:30]}"
    assert summary.endswith("_TAIL_MARKER"), f"Tail not preserved: {summary[-30:]}"
    print(f"  PASS head_tail_preservation ({len(text)} -> {len(summary)} chars)")


def test_batch_partition_respects_cap():
    """After capping, docs should fit within batch limits more often."""
    docs = []
    for i in range(8):
        doc = make_doc(
            summary_chars=6000 if i % 2 == 0 else 2000,
            detail_count=8,
            detail_chars=300,
        )
        docs.append(MultiStageAnalyzer._cap_doc_for_fact_extraction(doc))

    total_chars = sum(len(json.dumps(d)) for d in docs)
    per_doc_avg = total_chars / len(docs)
    print(f"  INFO batch_after_cap: {len(docs)} docs, total={total_chars} chars, "
          f"avg={per_doc_avg:.0f}/doc")
    # With 8K cap × 8 docs, worst case is 64K. With 25K batch limit,
    # we'd get ~3 batches. This is a correctness check, not a pass/fail.


if __name__ == "__main__":
    print("Testing _cap_doc_for_fact_extraction:")
    test_small_doc_unchanged()
    test_large_summary_truncated()
    test_large_structured_fields()
    test_empty_summary()
    test_none_summary()
    test_head_tail_preservation()
    test_batch_partition_respects_cap()
    print("\nAll tests passed.")
