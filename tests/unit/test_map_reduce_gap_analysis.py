"""Unit tests for map-reduce gap analysis pipeline.

Tests cover:
- Batching logic (grouping, overflow splitting, small-group merge)
- Deterministic deduplication
- State hash (lightweight vs full)
- Routing (<=50 single-pass, >50 map-reduce)
- Pricing guard (gpt-5.4 cost skip)
- Parse stats tracking
- Small-group merge map chain termination
"""

import hashlib
import json

import pytest

from legal_portal.core.data_models import (
    BatchEvidence,
    BatchFinding,
    BatchGapReport,
    DocumentSummaryStructured,
    GapAnalysisResult,
)
from legal_portal.services.analysis.gap_analysis_service import (
    _deduplicate_findings,
    _normalize_title,
)


# ---------------------------------------------------------------------------
# Model instantiation
# ---------------------------------------------------------------------------


class TestBatchModels:
    """Verify BatchEvidence, BatchFinding, BatchGapReport instantiate correctly."""

    def test_batch_evidence_minimal(self):
        e = BatchEvidence(
            category="executed_contracts",
            document_ids=["id-1"],
            status="present",
            detail="Contract found.",
        )
        assert e.status == "present"
        assert e.severity is None

    def test_batch_finding_with_cross_batch(self):
        f = BatchFinding(
            category="missing_docs",
            severity="high",
            title="Missing Payment Proof",
            description="No payment receipts found.",
            document_ids=["id-2"],
            cross_batch_uncertain=True,
        )
        assert f.cross_batch_uncertain is True

    def test_batch_gap_report(self):
        r = BatchGapReport(
            batch_id="batch_1",
            batch_label="controlling_instrument",
            document_count=5,
            evidence=[],
            findings=[],
            cross_batch_flags=["CHECK_BATCH:correspondence FOR:payment_receipts"],
        )
        assert r.batch_label == "controlling_instrument"
        assert len(r.cross_batch_flags) == 1

    def test_gap_analysis_result_new_fields(self):
        r = GapAnalysisResult(
            total_gaps=3,
            critical_count=1,
            high_count=1,
            medium_count=1,
            low_count=0,
            gaps_by_category={},
            overall_completeness_score=65.0,
            attorney_summary="Test summary.",
            analysis_quality="full",
            map_reduce_metadata={"pipeline": "map_reduce"},
        )
        assert r.analysis_quality == "full"
        assert r.map_reduce_metadata["pipeline"] == "map_reduce"

    def test_gap_analysis_result_backward_compatible(self):
        """Existing results without new fields still parse."""
        r = GapAnalysisResult(
            total_gaps=0,
            overall_completeness_score=100.0,
            attorney_summary="No gaps.",
        )
        assert r.analysis_quality is None
        assert r.map_reduce_metadata is None


class TestDocumentSummaryDocumentId:
    """Verify document_id field on DocumentSummaryStructured."""

    def test_default_none(self):
        s = DocumentSummaryStructured(
            document_name="test.pdf", document_type="contract"
        )
        assert s.document_id is None

    def test_explicit_id(self):
        s = DocumentSummaryStructured(
            document_id="abc-123",
            document_name="test.pdf",
            document_type="contract",
        )
        assert s.document_id == "abc-123"

    def test_from_dict_without_id(self):
        """Existing serialized summaries without document_id still parse."""
        data = {"document_name": "test.pdf", "document_type": "contract"}
        s = DocumentSummaryStructured(**data)
        assert s.document_id is None


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplicateFindings:
    """Test deterministic deduplication logic."""

    def _make_finding(self, title="Gap", category="missing_docs", severity="high",
                      doc_ids=None):
        return BatchFinding(
            category=category,
            severity=severity,
            title=title,
            description="Description",
            document_ids=doc_ids or [],
        )

    def test_empty_list(self):
        assert _deduplicate_findings([]) == []

    def test_single_finding(self):
        f = self._make_finding()
        result = _deduplicate_findings([f])
        assert len(result) == 1

    def test_exact_duplicates_merged(self):
        """Same title + category + overlapping IDs → merge."""
        f1 = self._make_finding(doc_ids=["id-1"])
        f2 = self._make_finding(doc_ids=["id-1", "id-2"])
        result = _deduplicate_findings([f1, f2])
        assert len(result) == 1
        assert set(result[0].document_ids) == {"id-1", "id-2"}

    def test_higher_severity_wins(self):
        """When merging, keep the higher severity."""
        f1 = self._make_finding(severity="medium", doc_ids=["id-1"])
        f2 = self._make_finding(severity="critical", doc_ids=["id-1"])
        result = _deduplicate_findings([f1, f2])
        assert len(result) == 1
        assert result[0].severity == "critical"

    def test_no_overlap_keeps_both(self):
        """Same title+category but no overlapping IDs → keep both."""
        f1 = self._make_finding(doc_ids=["id-1"])
        f2 = self._make_finding(doc_ids=["id-2"])
        result = _deduplicate_findings([f1, f2])
        assert len(result) == 2

    def test_different_category_keeps_both(self):
        """Same title but different category → keep both."""
        f1 = self._make_finding(category="missing_docs", doc_ids=["id-1"])
        f2 = self._make_finding(category="contradictions", doc_ids=["id-1"])
        result = _deduplicate_findings([f1, f2])
        assert len(result) == 2

    def test_title_normalization(self):
        """Titles normalized: case, punctuation, whitespace."""
        f1 = self._make_finding(title="Missing Contract!", doc_ids=["id-1"])
        f2 = self._make_finding(title="  missing contract  ", doc_ids=["id-1"])
        result = _deduplicate_findings([f1, f2])
        assert len(result) == 1

    def test_severity_tie_more_docs_wins(self):
        """On severity tie, finding with more doc IDs wins."""
        f1 = self._make_finding(severity="high", doc_ids=["id-1"])
        f2 = self._make_finding(severity="high", doc_ids=["id-1", "id-2", "id-3"])
        result = _deduplicate_findings([f1, f2])
        assert len(result) == 1
        assert len(result[0].document_ids) == 3


class TestNormalizeTitle:
    def test_strips_punctuation_and_lowercases(self):
        assert _normalize_title("Missing Contract!") == "missing contract"

    def test_strips_whitespace(self):
        assert _normalize_title("  gap  in  docs  ") == "gap  in  docs"


# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


class TestBuildGapAnalysisBatches:
    """Test intelligent batching logic."""

    def _make_summary(self, doc_id, name="doc.pdf", doc_type="contract"):
        return DocumentSummaryStructured(
            document_id=doc_id,
            document_name=name,
            document_type=doc_type,
        )

    def _make_registry(self, doc_id, role):
        return {"document_id": doc_id, "role_in_case": role}

    def test_groups_by_role(self):
        from legal_portal.api.routes.analysis import _build_gap_analysis_batches

        summaries = [
            self._make_summary(f"id-{i}", doc_type="contract")
            for i in range(6)
        ] + [
            self._make_summary(f"id-corr-{i}", doc_type="email")
            for i in range(5)
        ]
        registry = [
            self._make_registry(f"id-{i}", "controlling_instrument")
            for i in range(6)
        ] + [
            self._make_registry(f"id-corr-{i}", "correspondence")
            for i in range(5)
        ]

        batches = _build_gap_analysis_batches(summaries, [], registry)
        labels = {b.batch_label for b in batches}
        assert "controlling_instrument" in labels
        # correspondence has 5 docs (>=3), should be its own batch
        assert "correspondence" in labels

    def test_small_groups_merge(self):
        """Groups with <3 docs merge into their target per _SMALL_GROUP_MERGE_MAP."""
        from legal_portal.api.routes.analysis import _build_gap_analysis_batches

        summaries = [
            self._make_summary("id-1"),  # intake (1 doc → merges)
            self._make_summary("id-2"),  # controlling_instrument
            self._make_summary("id-3"),
            self._make_summary("id-4"),
        ]
        registry = [
            self._make_registry("id-1", "intake"),
            self._make_registry("id-2", "controlling_instrument"),
            self._make_registry("id-3", "controlling_instrument"),
            self._make_registry("id-4", "controlling_instrument"),
        ]

        batches = _build_gap_analysis_batches(summaries, [], registry)
        # intake (1 doc) should merge → correspondence → controlling_instrument
        assert len(batches) == 1
        assert batches[0].batch_label == "controlling_instrument"
        assert len(batches[0].document_summaries) == 4

    def test_unmapped_docs_go_to_other(self):
        from legal_portal.api.routes.analysis import _build_gap_analysis_batches

        summaries = [self._make_summary(f"id-{i}") for i in range(5)]
        # No registry entries → all map to "other"
        batches = _build_gap_analysis_batches(summaries, [], [])
        # "other" has 5 docs (>=3), should be its own batch, or merge
        assert len(batches) >= 1
        total_docs = sum(len(b.document_summaries) for b in batches)
        assert total_docs == 5

    def test_signature_evidence_assigned_to_batch(self):
        from legal_portal.api.routes.analysis import _build_gap_analysis_batches

        summaries = [self._make_summary("id-1"), self._make_summary("id-2"),
                     self._make_summary("id-3")]
        registry = [self._make_registry(f"id-{i}", "controlling_instrument") for i in range(1, 4)]
        sig_evidence = [{"document_id": "id-1", "status": "signed"}]

        batches = _build_gap_analysis_batches(summaries, sig_evidence, registry)
        assert len(batches) == 1
        assert len(batches[0].signature_evidence) == 1
        assert batches[0].signature_evidence[0]["status"] == "signed"


class TestSmallGroupMergeMap:
    """Verify merge chain terminates at controlling_instrument within 3 hops."""

    def test_all_roles_terminate_at_controlling_instrument(self):
        from legal_portal.api.routes.analysis import _SMALL_GROUP_MERGE_MAP

        all_roles = [
            "intake", "official_record", "supporting_evidence",
            "other", "correspondence", "financial_evidence",
        ]
        for role in all_roles:
            target = role
            for hop in range(3):
                next_target = _SMALL_GROUP_MERGE_MAP.get(target)
                if next_target is None:
                    break
                target = next_target
            assert target == "controlling_instrument", (
                f"Role '{role}' does not terminate at 'controlling_instrument' "
                f"within 3 hops (ended at '{target}')"
            )

    def test_controlling_instrument_is_terminal(self):
        from legal_portal.api.routes.analysis import _SMALL_GROUP_MERGE_MAP

        assert "controlling_instrument" not in _SMALL_GROUP_MERGE_MAP


# ---------------------------------------------------------------------------
# Lightweight state hash
# ---------------------------------------------------------------------------


class TestLightweightStateHash:
    def test_changes_on_updated_at(self):
        from legal_portal.api.routes.analysis import _build_case_document_state_hash_lightweight

        rows_a = [{"id": "1", "updated_at": "2026-01-01", "status": "ready",
                    "file_name": "doc.pdf", "extracted_at": "2026-01-01"}]
        rows_b = [{"id": "1", "updated_at": "2026-02-01", "status": "ready",
                    "file_name": "doc.pdf", "extracted_at": "2026-01-01"}]

        hash_a = _build_case_document_state_hash_lightweight(rows_a)
        hash_b = _build_case_document_state_hash_lightweight(rows_b)
        assert hash_a != hash_b

    def test_changes_on_status(self):
        from legal_portal.api.routes.analysis import _build_case_document_state_hash_lightweight

        rows_a = [{"id": "1", "updated_at": "2026-01-01", "status": "ready",
                    "file_name": "doc.pdf", "extracted_at": "2026-01-01"}]
        rows_b = [{"id": "1", "updated_at": "2026-01-01", "status": "needs_review",
                    "file_name": "doc.pdf", "extracted_at": "2026-01-01"}]

        hash_a = _build_case_document_state_hash_lightweight(rows_a)
        hash_b = _build_case_document_state_hash_lightweight(rows_b)
        assert hash_a != hash_b

    def test_changes_on_extracted_at(self):
        from legal_portal.api.routes.analysis import _build_case_document_state_hash_lightweight

        rows_a = [{"id": "1", "updated_at": "2026-01-01", "status": "ready",
                    "file_name": "doc.pdf", "extracted_at": "2026-01-01"}]
        rows_b = [{"id": "1", "updated_at": "2026-01-01", "status": "ready",
                    "file_name": "doc.pdf", "extracted_at": "2026-02-01"}]

        hash_a = _build_case_document_state_hash_lightweight(rows_a)
        hash_b = _build_case_document_state_hash_lightweight(rows_b)
        assert hash_a != hash_b

    def test_stable_across_row_ordering(self):
        """Hash should not change if rows arrive in different order."""
        from legal_portal.api.routes.analysis import _build_case_document_state_hash_lightweight

        row1 = {"id": "1", "updated_at": "2026-01-01", "status": "ready",
                "file_name": "a.pdf", "extracted_at": "2026-01-01"}
        row2 = {"id": "2", "updated_at": "2026-01-02", "status": "ready",
                "file_name": "b.pdf", "extracted_at": "2026-01-02"}

        hash_a = _build_case_document_state_hash_lightweight([row1, row2])
        hash_b = _build_case_document_state_hash_lightweight([row2, row1])
        assert hash_a == hash_b

    def test_empty_rows(self):
        from legal_portal.api.routes.analysis import _build_case_document_state_hash_lightweight

        assert _build_case_document_state_hash_lightweight([]) == "no_case_documents"


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TestRouting:
    """Verify _run_gap_analysis routes correctly based on doc count."""

    @pytest.mark.asyncio
    async def test_routes_to_single_pass_for_small_cases(self):
        """<=50 docs should call analyze_gaps, not analyze_gaps_map_reduce."""
        from unittest.mock import AsyncMock, MagicMock

        gap_service = MagicMock()
        gap_service.analyze_gaps = AsyncMock(return_value=GapAnalysisResult(
            total_gaps=0, overall_completeness_score=100.0,
            attorney_summary="No gaps.",
        ))

        from legal_portal.api.routes.analysis import _run_gap_analysis

        summaries = [
            DocumentSummaryStructured(document_name=f"doc{i}.pdf", document_type="contract")
            for i in range(10)
        ]

        # Use MagicMock for complex models — routing doesn't inspect them
        result = await _run_gap_analysis(
            gap_service=gap_service,
            doc_summaries_list=summaries,
            fact_matrix=MagicMock(),
            issue_map=MagicMock(),
            deep_analysis=MagicMock(),
        )

        gap_service.analyze_gaps.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_to_map_reduce_for_large_cases(self):
        """  >50 docs should call analyze_gaps_map_reduce."""
        from unittest.mock import AsyncMock, MagicMock

        gap_service = MagicMock()
        gap_service.analyze_gaps_map_reduce = AsyncMock(return_value=GapAnalysisResult(
            total_gaps=5, overall_completeness_score=70.0,
            attorney_summary="Some gaps.", analysis_quality="full",
        ))

        from legal_portal.api.routes.analysis import _run_gap_analysis

        summaries = [
            DocumentSummaryStructured(
                document_id=f"id-{i}",
                document_name=f"doc{i}.pdf",
                document_type="contract",
            )
            for i in range(60)
        ]

        result = await _run_gap_analysis(
            gap_service=gap_service,
            doc_summaries_list=summaries,
            fact_matrix=MagicMock(),
            issue_map=MagicMock(),
            deep_analysis=MagicMock(),
            document_registry=[
                {"document_id": f"id-{i}", "role_in_case": "controlling_instrument"}
                for i in range(60)
            ],
        )

        gap_service.analyze_gaps_map_reduce.assert_called_once()


# ---------------------------------------------------------------------------
# Pricing guard
# ---------------------------------------------------------------------------


class TestPricingGuard:
    def test_gpt54_returns_nonzero_cost(self):
        from legal_portal.utils.openai_client import OpenAIClient

        client = OpenAIClient.__new__(OpenAIClient)
        cost = client.estimate_cost(1000, 500, "gpt-5.4")
        assert cost > 0.0

    def test_gpt41_returns_nonzero_cost(self):
        from legal_portal.utils.openai_client import OpenAIClient

        client = OpenAIClient.__new__(OpenAIClient)
        cost = client.estimate_cost(1000, 500, "gpt-5-mini")
        assert cost > 0.0


# ---------------------------------------------------------------------------
# ID stamping
# ---------------------------------------------------------------------------


class TestStampDocumentIds:
    def test_stamps_matching_ids(self):
        from legal_portal.api.routes.analysis import _stamp_document_ids

        summaries = [
            DocumentSummaryStructured(document_name="Doc A.pdf", document_type="contract"),
            DocumentSummaryStructured(document_name="Doc B.pdf", document_type="email"),
        ]
        metadata = [
            {"id": "uuid-a", "file_name": "Doc A.pdf", "updated_at": "2026-01-01"},
            {"id": "uuid-b", "file_name": "Doc B.pdf", "updated_at": "2026-01-02"},
        ]

        _stamp_document_ids(summaries, metadata)
        assert summaries[0].document_id == "uuid-a"
        assert summaries[1].document_id == "uuid-b"

    def test_collision_uses_most_recent(self):
        """When multiple metadata rows match the same name, use the first (most recent)."""
        from legal_portal.api.routes.analysis import _stamp_document_ids

        summaries = [
            DocumentSummaryStructured(document_name="doc.pdf", document_type="contract"),
        ]
        # metadata_rows are ordered by updated_at DESC, so first match wins
        metadata = [
            {"id": "uuid-new", "file_name": "doc.pdf", "updated_at": "2026-02-01"},
            {"id": "uuid-old", "file_name": "doc.pdf", "updated_at": "2026-01-01"},
        ]

        _stamp_document_ids(summaries, metadata)
        assert summaries[0].document_id == "uuid-new"

    def test_case_insensitive_matching(self):
        from legal_portal.api.routes.analysis import _stamp_document_ids

        summaries = [
            DocumentSummaryStructured(document_name="DOC A.PDF", document_type="contract"),
        ]
        metadata = [
            {"id": "uuid-a", "file_name": "doc a.pdf", "updated_at": "2026-01-01"},
        ]

        _stamp_document_ids(summaries, metadata)
        assert summaries[0].document_id == "uuid-a"

    def test_unmatched_gets_none(self):
        from legal_portal.api.routes.analysis import _stamp_document_ids

        summaries = [
            DocumentSummaryStructured(document_name="unknown.pdf", document_type="contract"),
        ]
        metadata = [
            {"id": "uuid-a", "file_name": "doc.pdf", "updated_at": "2026-01-01"},
        ]

        _stamp_document_ids(summaries, metadata)
        assert summaries[0].document_id is None

    def test_preserves_existing_id(self):
        """If document_id is already set, don't overwrite."""
        from legal_portal.api.routes.analysis import _stamp_document_ids

        summaries = [
            DocumentSummaryStructured(
                document_id="existing-id",
                document_name="doc.pdf",
                document_type="contract",
            ),
        ]
        metadata = [
            {"id": "uuid-a", "file_name": "doc.pdf", "updated_at": "2026-01-01"},
        ]

        _stamp_document_ids(summaries, metadata)
        assert summaries[0].document_id == "existing-id"


# ---------------------------------------------------------------------------
# Overflow splitting (>40 docs in a group)
# ---------------------------------------------------------------------------


class TestOverflowSplitting:
    """Test that groups with >40 docs are split by document_type."""

    def _make_summary(self, doc_id, doc_type="contract"):
        return DocumentSummaryStructured(
            document_id=doc_id,
            document_name=f"{doc_id}.pdf",
            document_type=doc_type,
        )

    def test_overflow_splits_by_document_type(self):
        """A role group >40 docs splits into sub-batches by document_type."""
        from legal_portal.api.routes.analysis import _build_gap_analysis_batches

        # 25 contracts + 20 emails = 45 total in controlling_instrument
        summaries = (
            [self._make_summary(f"id-c-{i}", "contract") for i in range(25)]
            + [self._make_summary(f"id-e-{i}", "email") for i in range(20)]
        )
        registry = [
            {"document_id": s.document_id, "role_in_case": "controlling_instrument"}
            for s in summaries
        ]

        batches = _build_gap_analysis_batches(summaries, [], registry)
        total_docs = sum(len(b.document_summaries) for b in batches)
        assert total_docs == 45
        # Should have 2+ batches since 45 > 40
        assert len(batches) >= 2
        # No batch should exceed 40 docs
        for b in batches:
            assert len(b.document_summaries) <= 40

    def test_overflow_splits_further_into_date_bands(self):
        """When a single type within a role exceeds 40, split into thirds."""
        from legal_portal.api.routes.analysis import _build_gap_analysis_batches

        # 60 contracts all in one role
        summaries = [self._make_summary(f"id-{i}", "contract") for i in range(60)]
        registry = [
            {"document_id": s.document_id, "role_in_case": "controlling_instrument"}
            for s in summaries
        ]

        batches = _build_gap_analysis_batches(summaries, [], registry)
        total_docs = sum(len(b.document_summaries) for b in batches)
        assert total_docs == 60
        # Should be split into 3 parts (chronological thirds)
        assert len(batches) == 3
        for b in batches:
            assert len(b.document_summaries) == 20

    def test_no_split_when_under_threshold(self):
        """Groups with <=40 docs stay intact."""
        from legal_portal.api.routes.analysis import _build_gap_analysis_batches

        summaries = [self._make_summary(f"id-{i}", "contract") for i in range(30)]
        registry = [
            {"document_id": s.document_id, "role_in_case": "controlling_instrument"}
            for s in summaries
        ]

        batches = _build_gap_analysis_batches(summaries, [], registry)
        assert len(batches) == 1
        assert len(batches[0].document_summaries) == 30


# ---------------------------------------------------------------------------
# Boundary conditions for routing
# ---------------------------------------------------------------------------


class TestRoutingBoundary:
    """Test exact boundary at 50 docs."""

    @pytest.mark.asyncio
    async def test_exactly_50_uses_single_pass(self):
        from unittest.mock import AsyncMock, MagicMock
        from legal_portal.api.routes.analysis import _run_gap_analysis

        gap_service = MagicMock()
        gap_service.analyze_gaps = AsyncMock(return_value=GapAnalysisResult(
            total_gaps=0, overall_completeness_score=100.0,
            attorney_summary="No gaps.",
        ))

        summaries = [
            DocumentSummaryStructured(document_name=f"doc{i}.pdf", document_type="contract")
            for i in range(50)
        ]

        await _run_gap_analysis(
            gap_service=gap_service,
            doc_summaries_list=summaries,
            fact_matrix=MagicMock(),
            issue_map=MagicMock(),
            deep_analysis=MagicMock(),
        )
        gap_service.analyze_gaps.assert_called_once()
        gap_service.analyze_gaps_map_reduce.assert_not_called()

    @pytest.mark.asyncio
    async def test_51_uses_map_reduce(self):
        from unittest.mock import AsyncMock, MagicMock
        from legal_portal.api.routes.analysis import _run_gap_analysis

        gap_service = MagicMock()
        gap_service.analyze_gaps_map_reduce = AsyncMock(return_value=GapAnalysisResult(
            total_gaps=0, overall_completeness_score=100.0,
            attorney_summary="No gaps.", analysis_quality="full",
        ))

        summaries = [
            DocumentSummaryStructured(
                document_id=f"id-{i}",
                document_name=f"doc{i}.pdf",
                document_type="contract",
            )
            for i in range(51)
        ]

        await _run_gap_analysis(
            gap_service=gap_service,
            doc_summaries_list=summaries,
            fact_matrix=MagicMock(),
            issue_map=MagicMock(),
            deep_analysis=MagicMock(),
            document_registry=[
                {"document_id": f"id-{i}", "role_in_case": "controlling_instrument"}
                for i in range(51)
            ],
        )
        gap_service.analyze_gaps_map_reduce.assert_called_once()


# ---------------------------------------------------------------------------
# Parse batch report
# ---------------------------------------------------------------------------


class TestParseBatchReport:
    """Test JSON parsing with markdown fence stripping."""

    def _make_service(self):
        from unittest.mock import MagicMock
        from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService

        svc = GapAnalysisService.__new__(GapAnalysisService)
        svc.client = MagicMock()
        return svc

    def _make_batch(self):
        from legal_portal.api.routes.analysis import GapBatch
        return GapBatch(
            batch_id="batch_1",
            batch_label="controlling_instrument",
            document_summaries=[
                DocumentSummaryStructured(
                    document_id="id-1", document_name="doc.pdf", document_type="contract",
                )
            ],
        )

    def test_parses_clean_json(self):
        svc = self._make_service()
        batch = self._make_batch()
        raw = json.dumps({
            "batch_id": "batch_1",
            "batch_label": "controlling_instrument",
            "document_count": 1,
            "evidence": [],
            "findings": [],
            "cross_batch_flags": [],
        })
        report = svc._parse_batch_report(raw, batch)
        assert report.batch_id == "batch_1"
        assert report.document_count == 1

    def test_strips_markdown_fences(self):
        svc = self._make_service()
        batch = self._make_batch()
        raw = '```json\n{"evidence": [], "findings": [], "cross_batch_flags": []}\n```'
        report = svc._parse_batch_report(raw, batch)
        assert report.batch_id == "batch_1"
        assert report.batch_label == "controlling_instrument"

    def test_raises_on_invalid_json(self):
        svc = self._make_service()
        batch = self._make_batch()
        with pytest.raises(json.JSONDecodeError):
            svc._parse_batch_report("not valid json", batch)

    def test_overrides_batch_id_and_label(self):
        """Even if LLM returns wrong batch_id/label, we override with actual values."""
        svc = self._make_service()
        batch = self._make_batch()
        raw = json.dumps({
            "batch_id": "wrong_id",
            "batch_label": "wrong_label",
            "document_count": 999,
            "evidence": [],
            "findings": [
                {"category": "missing_docs", "severity": "high",
                 "title": "Gap", "description": "Desc", "document_ids": ["id-1"]}
            ],
            "cross_batch_flags": [],
        })
        report = svc._parse_batch_report(raw, batch)
        assert report.batch_id == "batch_1"
        assert report.batch_label == "controlling_instrument"
        assert report.document_count == 1
        assert len(report.findings) == 1


# ---------------------------------------------------------------------------
# Mechanical merge fallback
# ---------------------------------------------------------------------------


class TestMechanicalMerge:
    """Test deterministic merge when reduce phase fails."""

    def _make_service(self):
        from unittest.mock import MagicMock
        from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService

        svc = GapAnalysisService.__new__(GapAnalysisService)
        svc.client = MagicMock()
        return svc

    def test_empty_reports(self):
        svc = self._make_service()
        result = svc._mechanical_merge([])
        assert result.total_gaps == 0
        assert result.overall_completeness_score == 100.0

    def test_single_report_with_findings(self):
        svc = self._make_service()
        report = BatchGapReport(
            batch_id="b1", batch_label="controlling_instrument",
            document_count=5,
            evidence=[],
            findings=[
                BatchFinding(
                    category="incomplete_info", severity="critical",
                    title="Missing Contract", description="No contract found.",
                    document_ids=["id-1"],
                ),
                BatchFinding(
                    category="incomplete_info", severity="high",
                    title="Missing Payment", description="No payment proof.",
                    document_ids=["id-2"],
                ),
            ],
            cross_batch_flags=[],
        )
        result = svc._mechanical_merge([report])
        assert result.total_gaps == 2
        assert result.critical_count == 1
        assert result.high_count == 1
        assert "Mechanical merge" in result.attorney_summary

    def test_deduplicates_across_reports(self):
        """Same finding in two reports should be deduplicated."""
        svc = self._make_service()
        finding = BatchFinding(
            category="incomplete_info", severity="high",
            title="Missing Contract", description="No contract.",
            document_ids=["id-1"],
        )
        report1 = BatchGapReport(
            batch_id="b1", batch_label="controlling_instrument",
            document_count=5, evidence=[], findings=[finding], cross_batch_flags=[],
        )
        report2 = BatchGapReport(
            batch_id="b2", batch_label="correspondence",
            document_count=3, evidence=[], findings=[finding], cross_batch_flags=[],
        )
        result = svc._mechanical_merge([report1, report2])
        # Same title, same category, overlapping doc IDs → merged
        assert result.total_gaps == 1

    def test_completeness_score_penalizes_severity(self):
        """Score decreases with higher severity gaps."""
        svc = self._make_service()
        report = BatchGapReport(
            batch_id="b1", batch_label="controlling_instrument",
            document_count=5, evidence=[],
            findings=[
                BatchFinding(
                    category="incomplete_info", severity="critical",
                    title=f"Gap {i}", description="Desc",
                    document_ids=[f"id-{i}"],
                )
                for i in range(5)
            ],
            cross_batch_flags=[],
        )
        result = svc._mechanical_merge([report])
        # 5 critical * 15 = 75 penalty → score = 25
        assert result.overall_completeness_score == 25.0

    def test_reconciliation_notes_present(self):
        svc = self._make_service()
        result = svc._mechanical_merge([])
        assert len(result.reconciliation_notes) > 0
        assert "mechanical merge" in result.reconciliation_notes[0].lower()


# ---------------------------------------------------------------------------
# Map prompt content
# ---------------------------------------------------------------------------


class TestBuildMapPrompt:
    """Test that map prompt includes correct content for each batch."""

    def _make_service(self):
        from unittest.mock import MagicMock
        from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService

        svc = GapAnalysisService.__new__(GapAnalysisService)
        svc.client = MagicMock()
        return svc

    def test_prompt_includes_batch_docs_only(self):
        from legal_portal.api.routes.analysis import GapBatch
        from unittest.mock import MagicMock

        svc = self._make_service()

        batch1_docs = [
            DocumentSummaryStructured(
                document_id="id-1", document_name="contract.pdf",
                document_type="contract",
            ),
        ]
        batch2_docs = [
            DocumentSummaryStructured(
                document_id="id-2", document_name="email.eml",
                document_type="email",
            ),
        ]

        batch1 = GapBatch(
            batch_id="batch_1", batch_label="controlling_instrument",
            document_summaries=batch1_docs,
        )
        batch2 = GapBatch(
            batch_id="batch_2", batch_label="correspondence",
            document_summaries=batch2_docs,
        )

        # Minimal mocks for fact_matrix and issue_map
        fact_matrix = MagicMock()
        fact_matrix.parties = []
        fact_matrix.timeline = []
        issue_map = MagicMock()
        issue_map.primary_issues = []

        prompt = svc._build_map_prompt(batch1, fact_matrix, issue_map, [batch1, batch2])

        # Batch 1's doc should be in the ID table
        assert "id-1" in prompt
        assert "contract.pdf" in prompt
        # Batch 2's doc should NOT be in the ID table
        assert "id-2" not in prompt
        # But batch 2's label should be mentioned as "other batch"
        assert "correspondence" in prompt

    def test_prompt_includes_id_mapping_table(self):
        from legal_portal.api.routes.analysis import GapBatch
        from unittest.mock import MagicMock

        svc = self._make_service()

        docs = [
            DocumentSummaryStructured(
                document_id=f"uuid-{i}", document_name=f"doc{i}.pdf",
                document_type="contract",
            )
            for i in range(3)
        ]
        batch = GapBatch(
            batch_id="batch_1", batch_label="test",
            document_summaries=docs,
        )

        fact_matrix = MagicMock()
        fact_matrix.parties = []
        fact_matrix.timeline = []
        issue_map = MagicMock()
        issue_map.primary_issues = []

        prompt = svc._build_map_prompt(batch, fact_matrix, issue_map, [batch])

        # All 3 doc IDs should appear in the mapping table
        for i in range(3):
            assert f"uuid-{i}" in prompt
            assert f"doc{i}.pdf" in prompt

    def test_single_batch_shows_only_batch_message(self):
        from legal_portal.api.routes.analysis import GapBatch
        from unittest.mock import MagicMock

        svc = self._make_service()

        batch = GapBatch(
            batch_id="batch_1", batch_label="test",
            document_summaries=[
                DocumentSummaryStructured(
                    document_id="id-1", document_name="doc.pdf",
                    document_type="contract",
                ),
            ],
        )

        fact_matrix = MagicMock()
        fact_matrix.parties = []
        fact_matrix.timeline = []
        issue_map = MagicMock()
        issue_map.primary_issues = []

        prompt = svc._build_map_prompt(batch, fact_matrix, issue_map, [batch])
        assert "This is the only batch." in prompt


# ---------------------------------------------------------------------------
# Reduce prompt content
# ---------------------------------------------------------------------------


class TestBuildReducePrompt:
    """Test that reduce prompt includes all batch reports and merge instructions."""

    def _make_service(self):
        from unittest.mock import MagicMock
        from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService

        svc = GapAnalysisService.__new__(GapAnalysisService)
        svc.client = MagicMock()
        return svc

    def test_includes_all_batch_reports(self):
        from unittest.mock import MagicMock

        svc = self._make_service()

        reports = [
            BatchGapReport(
                batch_id=f"batch_{i}", batch_label=f"label_{i}",
                document_count=5, evidence=[], findings=[],
                cross_batch_flags=[],
            )
            for i in range(3)
        ]

        fact_matrix = MagicMock()
        fact_matrix.parties = []
        fact_matrix.timeline = []
        issue_map = MagicMock()
        issue_map.primary_issues = []
        deep_analysis = MagicMock()
        deep_analysis.model_dump.return_value = {}

        prompt = svc._build_reduce_prompt(
            successful_reports=reports,
            failed_batches=[],
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
        )

        for i in range(3):
            assert f"batch_{i}" in prompt
            assert f"label_{i}" in prompt

    def test_includes_merge_instructions(self):
        from unittest.mock import MagicMock

        svc = self._make_service()

        report = BatchGapReport(
            batch_id="batch_1", batch_label="test",
            document_count=5, evidence=[], findings=[], cross_batch_flags=[],
        )

        fact_matrix = MagicMock()
        fact_matrix.parties = []
        fact_matrix.timeline = []
        issue_map = MagicMock()
        issue_map.primary_issues = []
        deep_analysis = MagicMock()
        deep_analysis.model_dump.return_value = {}

        prompt = svc._build_reduce_prompt(
            successful_reports=[report],
            failed_batches=[],
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
        )

        assert "Merge Instructions" in prompt
        assert "Cross-reference evidence" in prompt
        assert "Deduplicate" in prompt
        assert "overall_completeness_score" in prompt

    def test_includes_failed_batches_note(self):
        from unittest.mock import MagicMock

        svc = self._make_service()

        report = BatchGapReport(
            batch_id="batch_1", batch_label="test",
            document_count=5, evidence=[], findings=[], cross_batch_flags=[],
        )
        failed = [{"batch_label": "correspondence", "error": "Timeout"}]

        fact_matrix = MagicMock()
        fact_matrix.parties = []
        fact_matrix.timeline = []
        issue_map = MagicMock()
        issue_map.primary_issues = []
        deep_analysis = MagicMock()
        deep_analysis.model_dump.return_value = {}

        prompt = svc._build_reduce_prompt(
            successful_reports=[report],
            failed_batches=failed,
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
        )

        assert "Failed Batches" in prompt
        assert "correspondence" in prompt
        assert "Timeout" in prompt


# ---------------------------------------------------------------------------
# Analyze gaps map-reduce orchestration
# ---------------------------------------------------------------------------


class TestAnalyzeGapsMapReduce:
    """Test the full map-reduce orchestrator with mocked LLM calls."""

    def _make_service(self):
        from unittest.mock import MagicMock
        from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService

        svc = GapAnalysisService.__new__(GapAnalysisService)
        svc.client = MagicMock()
        svc.client.get_preferred_model = MagicMock(side_effect=lambda key, default: default)
        svc.client._is_gpt5_model = MagicMock(return_value=True)
        return svc

    def _make_batch(self, batch_id, label, n_docs=3):
        from legal_portal.api.routes.analysis import GapBatch
        return GapBatch(
            batch_id=batch_id,
            batch_label=label,
            document_summaries=[
                DocumentSummaryStructured(
                    document_id=f"{batch_id}-doc-{i}",
                    document_name=f"doc{i}.pdf",
                    document_type="contract",
                )
                for i in range(n_docs)
            ],
        )

    @pytest.mark.asyncio
    async def test_all_batches_fail_falls_back_to_single_pass(self):
        """When all map batches fail, falls back to single-pass."""
        from unittest.mock import AsyncMock, MagicMock, patch

        svc = self._make_service()

        # Map calls all raise exceptions
        svc.client.create_response = MagicMock(
            side_effect=Exception("LLM down")
        )

        # Single-pass fallback
        fallback_result = GapAnalysisResult(
            total_gaps=1, overall_completeness_score=50.0,
            attorney_summary="Fallback.",
        )
        svc.analyze_gaps = AsyncMock(return_value=fallback_result)
        svc._reconcile_signature_execution_gaps = MagicMock(return_value=fallback_result)
        svc._generate_recommendation = MagicMock(return_value="Review manually.")

        batches = [self._make_batch("b1", "controlling_instrument")]

        fact_matrix = MagicMock()
        fact_matrix.parties = []
        fact_matrix.timeline = []
        issue_map = MagicMock()
        issue_map.primary_issues = []
        deep_analysis = MagicMock()

        result = await svc.analyze_gaps_map_reduce(
            batches=batches,
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
        )

        assert result.analysis_quality == "fallback_single_pass"
        svc.analyze_gaps.assert_called_once()

    @pytest.mark.asyncio
    async def test_reduce_failure_uses_mechanical_merge(self):
        """When reduce fails, falls back to mechanical merge."""
        from unittest.mock import AsyncMock, MagicMock

        svc = self._make_service()

        batch_report = BatchGapReport(
            batch_id="b1", batch_label="controlling_instrument",
            document_count=3, evidence=[],
            findings=[
                BatchFinding(
                    category="incomplete_info", severity="high",
                    title="Missing Item", description="Desc",
                    document_ids=["id-1"],
                ),
            ],
            cross_batch_flags=[],
        )

        # Map succeeds
        svc._run_map_batch = AsyncMock(return_value=(
            batch_report,
            {"batch_id": "b1", "batch_label": "test", "doc_count": 3,
             "evidence_count": 0, "findings_count": 1, "duration_s": 0.1,
             "model_used": "gpt-5-mini", "retry_count": 0},
        ))

        # Reduce fails
        svc._run_reduce = AsyncMock(side_effect=Exception("Reduce crashed"))

        # Post-processing mocks
        svc._reconcile_signature_execution_gaps = MagicMock(
            side_effect=lambda r, *a, **kw: r
        )
        svc._generate_recommendation = MagicMock(return_value="Review manually.")

        batches = [self._make_batch("b1", "controlling_instrument")]

        fact_matrix = MagicMock()
        issue_map = MagicMock()
        deep_analysis = MagicMock()

        result = await svc.analyze_gaps_map_reduce(
            batches=batches,
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
        )

        assert result.analysis_quality == "degraded_merge"
        assert "Mechanical merge" in result.attorney_summary

    @pytest.mark.asyncio
    async def test_partial_batch_failure_reports_degraded(self):
        """When some (but not all) batches fail, quality is degraded_partial."""
        from unittest.mock import AsyncMock, MagicMock

        svc = self._make_service()

        good_report = BatchGapReport(
            batch_id="b1", batch_label="controlling_instrument",
            document_count=3, evidence=[], findings=[], cross_batch_flags=[],
        )

        # First batch succeeds, second raises
        async def _mock_run_map(batch, *args, **kwargs):
            if batch.batch_id == "b1":
                return (
                    good_report,
                    {"batch_id": "b1", "batch_label": "controlling_instrument",
                     "doc_count": 3, "evidence_count": 0, "findings_count": 0,
                     "duration_s": 0.1, "model_used": "gpt-5-mini", "retry_count": 0},
                )
            raise RuntimeError("Batch b2 failed")

        svc._run_map_batch = _mock_run_map

        # Reduce succeeds
        reduce_result = GapAnalysisResult(
            total_gaps=1, overall_completeness_score=70.0,
            attorney_summary="Partial analysis.",
        )
        svc._run_reduce = AsyncMock(return_value=reduce_result)
        svc._reconcile_signature_execution_gaps = MagicMock(
            side_effect=lambda r, *a, **kw: r
        )
        svc._generate_recommendation = MagicMock(return_value="Review manually.")

        batches = [
            self._make_batch("b1", "controlling_instrument"),
            self._make_batch("b2", "correspondence"),
        ]

        fact_matrix = MagicMock()
        issue_map = MagicMock()
        deep_analysis = MagicMock()

        result = await svc.analyze_gaps_map_reduce(
            batches=batches,
            fact_matrix=fact_matrix,
            issue_map=issue_map,
            deep_analysis=deep_analysis,
        )

        assert result.analysis_quality == "degraded_partial"
        assert result.map_reduce_metadata["failed_batches"]
        # Should have an INCOMPLETE_INFO gap added
        incomplete_gaps = result.gaps_by_category.get("incomplete_info", [])
        assert len(incomplete_gaps) >= 1

    @pytest.mark.asyncio
    async def test_parse_stats_tracked(self):
        """Parse stats are properly tracked and included in metadata."""
        from unittest.mock import AsyncMock, MagicMock

        svc = self._make_service()

        report = BatchGapReport(
            batch_id="b1", batch_label="controlling_instrument",
            document_count=3, evidence=[], findings=[], cross_batch_flags=[],
        )

        # Simulate: _run_map_batch increments parse_stats internally
        async def _mock_run_map(batch, fm, im, all_b, parse_stats, truncation_context=None):
            parse_stats["first_attempt_success"] += 1
            return (
                report,
                {"batch_id": "b1", "batch_label": "test", "doc_count": 3,
                 "evidence_count": 0, "findings_count": 0, "duration_s": 0.1,
                 "model_used": "gpt-5-mini", "retry_count": 0},
            )

        svc._run_map_batch = _mock_run_map

        reduce_result = GapAnalysisResult(
            total_gaps=0, overall_completeness_score=100.0,
            attorney_summary="All good.",
        )
        svc._run_reduce = AsyncMock(return_value=reduce_result)
        svc._reconcile_signature_execution_gaps = MagicMock(
            side_effect=lambda r, *a, **kw: r
        )
        svc._generate_recommendation = MagicMock(return_value="Good.")

        batches = [self._make_batch("b1", "controlling_instrument")]

        result = await svc.analyze_gaps_map_reduce(
            batches=batches,
            fact_matrix=MagicMock(),
            issue_map=MagicMock(),
            deep_analysis=MagicMock(),
        )

        meta = result.map_reduce_metadata
        assert meta["parse_stats"]["first_attempt_success"] == 1
        assert meta["parse_stats"]["parse_failure_rate_pct"] == 0.0


# ---------------------------------------------------------------------------
# Strip markdown fences
# ---------------------------------------------------------------------------


class TestStripMarkdownFences:
    def _make_service(self):
        from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService
        return GapAnalysisService.__new__(GapAnalysisService)

    def test_strips_json_fence(self):
        svc = self._make_service()
        assert svc._strip_markdown_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_bare_fence(self):
        svc = self._make_service()
        assert svc._strip_markdown_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_no_fences_unchanged(self):
        svc = self._make_service()
        assert svc._strip_markdown_fences('{"a": 1}') == '{"a": 1}'
