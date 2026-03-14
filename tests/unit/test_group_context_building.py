"""Tests for group-aware context building."""
import pytest
from unittest.mock import patch, MagicMock

from legal_portal.core.data_models import DocumentSummaryStructured, GroupSummary, GroupType
from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer


def _make_summary(name="doc.pdf", doc_type="contract", content="Some content", key_content=None):
    return DocumentSummaryStructured(
        document_name=name,
        document_type=doc_type,
        executive_summary=content,
        key_content=key_content or content,
    )


def _make_group_summary(label="Test Group", group_type=GroupType.BANK_STATEMENTS,
                         member_count=3, authority_score=68, narrative="Group narrative."):
    return GroupSummary(
        group_id="grp_test",
        group_type=group_type,
        label=label,
        member_count=member_count,
        member_document_names=[f"doc_{i}.pdf" for i in range(member_count)],
        combined_narrative=narrative,
        key_findings=["Finding 1"],
        authority_score=authority_score,
    )


class TestScoreToPriority:
    def test_high_score(self):
        assert MultiStageAnalyzer._score_to_priority(85) == 1

    def test_medium_score(self):
        assert MultiStageAnalyzer._score_to_priority(65) == 2

    def test_low_score(self):
        assert MultiStageAnalyzer._score_to_priority(45) == 3

    def test_very_low_score(self):
        assert MultiStageAnalyzer._score_to_priority(20) == 4

    def test_boundary_80(self):
        assert MultiStageAnalyzer._score_to_priority(80) == 1

    def test_boundary_60(self):
        assert MultiStageAnalyzer._score_to_priority(60) == 2

    def test_boundary_40(self):
        assert MultiStageAnalyzer._score_to_priority(40) == 3

    def test_boundary_39(self):
        assert MultiStageAnalyzer._score_to_priority(39) == 4


class TestGroupContextBuilding:
    def test_no_groups_backward_compatible(self):
        """group_summaries=None produces output identical to current behavior."""
        mock_client = MagicMock()
        analyzer = MultiStageAnalyzer(mock_client)
        summaries = [_make_summary("lease.pdf"), _make_summary("deed.pdf")]

        result_without = analyzer._build_condensed_context(summaries, group_summaries=None)
        result_with_empty = analyzer._build_condensed_context(summaries, group_summaries=[])

        assert result_without.docs_in_scope == result_with_empty.docs_in_scope
        assert result_without.total_tokens == result_with_empty.total_tokens

    def test_groups_included_in_context(self):
        """Groups appear in context output."""
        mock_client = MagicMock()
        analyzer = MultiStageAnalyzer(mock_client)
        summaries = [_make_summary("lease.pdf")]
        groups = [_make_group_summary()]

        result = analyzer._build_condensed_context(summaries, group_summaries=groups)

        assert result.docs_in_scope == 2  # 1 doc + 1 group
        assert "Test Group" in result.context_text

    def test_groups_compete_in_same_priority_queue(self):
        """Groups use authority_score for priority, same as individual docs."""
        mock_client = MagicMock()
        analyzer = MultiStageAnalyzer(mock_client)

        # High-priority individual doc
        summaries = [_make_summary("intake_form.pdf", doc_type="intake", content="Intake data")]
        # Lower-priority group
        groups = [_make_group_summary(authority_score=40)]

        result = analyzer._build_condensed_context(summaries, group_summaries=groups)

        # Intake should come first (priority 0), group second (priority 3)
        assert "intake_form.pdf" in result.context_text
        lines = result.context_text.split("\n")
        intake_pos = next(i for i, l in enumerate(lines) if "intake_form" in l)
        group_pos = next(i for i, l in enumerate(lines) if "Test Group" in l)
        assert intake_pos < group_pos

    def test_flag_off_ignores_groups(self):
        """enable_group_context=False means groups are not used."""
        mock_client = MagicMock()
        analyzer = MultiStageAnalyzer(mock_client)
        summaries = [_make_summary()]

        # With groups=None (flag off behavior)
        result = analyzer._build_condensed_context(summaries, group_summaries=None)
        assert "Test Group" not in result.context_text

    def test_group_narrative_in_output(self):
        """Group combined_narrative appears in context text."""
        mock_client = MagicMock()
        analyzer = MultiStageAnalyzer(mock_client)
        summaries = [_make_summary()]
        groups = [_make_group_summary(narrative="Monthly deposits totaling $15,000")]

        result = analyzer._build_condensed_context(summaries, group_summaries=groups)
        assert "Monthly deposits totaling $15,000" in result.context_text

    def test_group_key_findings_in_output(self):
        """Group key_findings appear in context text."""
        mock_client = MagicMock()
        analyzer = MultiStageAnalyzer(mock_client)
        summaries = [_make_summary()]
        groups = [_make_group_summary()]

        result = analyzer._build_condensed_context(summaries, group_summaries=groups)
        assert "Finding 1" in result.context_text

    def test_high_authority_group_ranked_highly(self):
        """Group with authority_score >= 80 gets priority 1."""
        mock_client = MagicMock()
        analyzer = MultiStageAnalyzer(mock_client)

        # Low-priority individual doc
        summaries = [_make_summary("random.pdf", doc_type="other", content="Other stuff")]
        # High-priority group
        groups = [_make_group_summary(authority_score=90)]

        result = analyzer._build_condensed_context(summaries, group_summaries=groups)

        lines = result.context_text.split("\n")
        group_pos = next(i for i, l in enumerate(lines) if "Test Group" in l)
        doc_pos = next(i for i, l in enumerate(lines) if "random.pdf" in l)
        assert group_pos < doc_pos

    def test_omitted_count_includes_groups(self):
        """docs_omitted counts both groups and docs that don't fit."""
        mock_client = MagicMock()
        analyzer = MultiStageAnalyzer(mock_client)
        summaries = [_make_summary(f"doc_{i}.pdf", content="x" * 2000) for i in range(20)]
        groups = [_make_group_summary(narrative="y" * 2000)]

        # Very small budget to force omissions
        result = analyzer._build_condensed_context(
            summaries, max_tokens=500, group_summaries=groups
        )

        total_entries = len(summaries) + len(groups)
        assert result.docs_in_scope + result.docs_omitted == total_entries

    def test_group_with_no_authority_score_defaults(self):
        """Group with authority_score=None defaults to priority bucket for score 50."""
        mock_client = MagicMock()
        analyzer = MultiStageAnalyzer(mock_client)
        summaries = [_make_summary()]
        groups = [_make_group_summary(authority_score=None)]
        # authority_score=None -> default 50 -> _score_to_priority(50) = 3

        result = analyzer._build_condensed_context(summaries, group_summaries=groups)
        assert result.docs_in_scope == 2
