"""Tests for token-budget context building in MultiStageAnalyzer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from legal_portal.core.data_models import DocumentSummaryStructured
from legal_portal.services.analysis.multi_stage_analyzer import (
    ContextBuildResult,
    MultiStageAnalyzer,
    _DEFAULT_BUDGET_TOKENS,
    _MAX_ENTRY_TOKENS,
)


def _make_summary(
    name: str = "doc.pdf",
    doc_type: str = "document",
    executive_summary: str = "Short summary.",
    key_content: str | None = None,
) -> DocumentSummaryStructured:
    """Create a minimal DocumentSummaryStructured for testing."""
    return DocumentSummaryStructured(
        document_name=name,
        document_type=doc_type,
        executive_summary=executive_summary,
        key_content=key_content,
    )


@pytest.fixture
def analyzer():
    client = MagicMock()
    return MultiStageAnalyzer(openai_client=client)


# --- Test cases ---


class TestBuildCondensedContext:
    """Unit tests for _build_condensed_context."""

    def test_zero_docs(self, analyzer):
        result = analyzer._build_condensed_context([])
        assert isinstance(result, ContextBuildResult)
        assert result.docs_in_scope == 0
        assert result.docs_omitted == 0
        assert result.context_text == ""
        assert result.total_tokens == 0

    def test_single_doc(self, analyzer):
        summaries = [_make_summary(name="intake.pdf", doc_type="intake")]
        result = analyzer._build_condensed_context(summaries)
        assert result.docs_in_scope == 1
        assert result.docs_omitted == 0
        assert "intake.pdf" in result.context_text

    def test_all_docs_under_budget(self, analyzer):
        summaries = [
            _make_summary(name=f"doc_{i}.pdf", key_content=f"Content for doc {i}")
            for i in range(10)
        ]
        result = analyzer._build_condensed_context(summaries)
        assert result.docs_in_scope == 10
        assert result.docs_omitted == 0
        assert result.omission_reason == ""

    def test_over_budget_omits_lower_priority(self, analyzer):
        # Use a very small budget to force omission
        summaries = [
            _make_summary(name=f"doc_{i}.pdf", key_content="x" * 500)
            for i in range(20)
        ]
        result = analyzer._build_condensed_context(summaries, max_tokens=500)
        assert result.docs_in_scope < 20
        assert result.docs_omitted > 0
        assert result.omission_reason != ""
        assert len(result.omitted_doc_names) == result.docs_omitted

    def test_priority_ordering_intake_first(self, analyzer):
        summaries = [
            _make_summary(name="letter.pdf", doc_type="correspondence"),
            _make_summary(name="contract.pdf", doc_type="contract"),
            _make_summary(name="client_intake.pdf", doc_type="intake"),
        ]
        result = analyzer._build_condensed_context(summaries)
        lines = result.context_text
        # Intake should appear before contract, contract before correspondence
        intake_pos = lines.index("client_intake.pdf")
        contract_pos = lines.index("contract.pdf")
        letter_pos = lines.index("letter.pdf")
        assert intake_pos < contract_pos < letter_pos

    def test_stable_sort_within_same_bucket(self, analyzer):
        summaries = [
            _make_summary(name="first_letter.pdf", doc_type="correspondence"),
            _make_summary(name="second_letter.pdf", doc_type="correspondence"),
            _make_summary(name="third_letter.pdf", doc_type="correspondence"),
        ]
        result = analyzer._build_condensed_context(summaries)
        text = result.context_text
        assert text.index("first_letter") < text.index("second_letter") < text.index("third_letter")

    def test_per_doc_cap_truncates_large_content(self, analyzer):
        # Create a doc with very large key_content
        large_content = "A" * 10_000
        summaries = [_make_summary(name="big.pdf", key_content=large_content)]
        result = analyzer._build_condensed_context(summaries)
        # The content in context_text should be shorter than the original
        assert len(result.context_text) < 10_000
        assert result.docs_in_scope == 1

    def test_fallback_to_executive_summary(self, analyzer):
        summaries = [_make_summary(
            name="minimal.pdf",
            key_content=None,
            executive_summary="This is the exec summary.",
        )]
        result = analyzer._build_condensed_context(summaries)
        assert "This is the exec summary." in result.context_text

    def test_scope_counts_always_add_up(self, analyzer):
        for n in [0, 1, 5, 50]:
            summaries = [
                _make_summary(name=f"doc_{i}.pdf", key_content="content " * 50)
                for i in range(n)
            ]
            result = analyzer._build_condensed_context(summaries)
            assert result.docs_in_scope + result.docs_omitted == n


class TestGetDocPriority:
    """Tests for _get_doc_priority static method."""

    def test_intake_name_gets_priority_0(self):
        s = _make_summary(name="client_intake.pdf", doc_type="form")
        assert MultiStageAnalyzer._get_doc_priority(s) == 0

    def test_contract_type_gets_priority_2(self):
        s = _make_summary(name="agreement.pdf", doc_type="contract")
        assert MultiStageAnalyzer._get_doc_priority(s) == 2

    def test_medical_type_gets_priority_3(self):
        s = _make_summary(name="records.pdf", doc_type="medical")
        assert MultiStageAnalyzer._get_doc_priority(s) == 3

    def test_unknown_type_gets_priority_5(self):
        s = _make_summary(name="misc.pdf", doc_type="other")
        assert MultiStageAnalyzer._get_doc_priority(s) == 5
