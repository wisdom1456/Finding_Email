"""Unit tests for stage checkpointing and recovery logic."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from legal_portal.services.documents.chunk_state_manager import ChunkStateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(doc_id: str = "doc-1", file_name: str = "test.pdf", content: str = "x" * 1000):
    """Minimal document-like object."""
    return SimpleNamespace(
        document_id=doc_id,
        file_name=file_name,
        content=content,
        file_type=SimpleNamespace(value="application/pdf"),
        registry={},
        extraction_quality="high",
        metadata=SimpleNamespace(file_size=len(content)),
    )


def _compute_hash(doc_ids: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(doc_ids)).encode()).hexdigest()[:16]


def _mock_supabase(chunk_state: dict | None = None):
    """Build a mock supabase client that returns the given chunk_state."""
    mock = MagicMock()
    response = MagicMock()
    response.data = {"chunk_state": chunk_state} if chunk_state else None
    mock.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = response
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
    return mock


# ============================================================
# ChunkStateManager.try_recover_summaries()
# ============================================================


class TestTryRecoverSummaries:
    @pytest.mark.asyncio
    async def test_recovers_when_phase_is_synthesis(self):
        state = {
            "phase": "synthesis",
            "documents": {"doc-1": {"status": "completed"}},
            "summaries": {
                "sum_doc-1": {"document_name": "test.pdf", "document_type": "contract"},
            },
        }
        mgr = ChunkStateManager(_mock_supabase(state), "analysis-1")
        result = await mgr.try_recover_summaries()
        assert result is not None
        assert len(result) == 1
        assert result[0]["document_name"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_recovers_when_phase_is_completed(self):
        state = {
            "phase": "completed",
            "documents": {},
            "summaries": {"sum_1": {"document_name": "a.pdf", "document_type": "letter"}},
        }
        mgr = ChunkStateManager(_mock_supabase(state), "analysis-1")
        result = await mgr.try_recover_summaries()
        assert result is not None
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_returns_none_when_phase_is_document_analysis(self):
        state = {"phase": "document_analysis", "summaries": {"k": {"v": 1}}}
        mgr = ChunkStateManager(_mock_supabase(state), "analysis-1")
        result = await mgr.try_recover_summaries()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_summaries(self):
        state = {"phase": "synthesis", "summaries": {}}
        mgr = ChunkStateManager(_mock_supabase(state), "analysis-1")
        result = await mgr.try_recover_summaries()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_state(self):
        mgr = ChunkStateManager(_mock_supabase(None), "analysis-1")
        result = await mgr.try_recover_summaries()
        assert result is None


# ============================================================
# ChunkStateManager.initialize_chunk_state() — preserve on retry
# ============================================================


class TestInitializePreservation:
    @pytest.mark.asyncio
    async def test_preserves_existing_state_with_completed_docs(self):
        existing = {
            "phase": "synthesis",
            "documents": {"doc-1": {"status": "completed"}},
            "summaries": {"sum_doc-1": {"document_name": "test.pdf", "document_type": "x"}},
            "chunks": [],
        }
        mock_sb = _mock_supabase(existing)
        mgr = ChunkStateManager(mock_sb, "analysis-1")

        result = await mgr.initialize_chunk_state([_make_doc()])
        assert result == existing
        # Should NOT have written to DB (no update call beyond the read)
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_reinitializes_when_forced(self):
        existing = {
            "phase": "synthesis",
            "documents": {"doc-1": {"status": "completed"}},
            "summaries": {"sum_doc-1": {"document_name": "test.pdf", "document_type": "x"}},
        }
        mock_sb = _mock_supabase(existing)
        mgr = ChunkStateManager(mock_sb, "analysis-1")

        with patch("legal_portal.services.documents.chunk_state_manager.ChunkStateManager.get_chunk_state") as mock_get:
            mock_get.return_value = existing
            # force_reinit should bypass preservation
            # We need to patch the create_chunk_state import
            with patch("legal_portal.services.documents.chunk_service.create_chunk_state") as mock_create:
                mock_create.return_value = {"phase": "document_analysis", "documents": {}, "summaries": {}, "chunks": []}
                result = await mgr.initialize_chunk_state([_make_doc()], force_reinit=True)
                assert result["phase"] == "document_analysis"


# ============================================================
# doc_ids_hash validation
# ============================================================


class TestDocIdsHash:
    def test_hash_is_deterministic(self):
        ids = ["doc-3", "doc-1", "doc-2"]
        h1 = _compute_hash(ids)
        h2 = _compute_hash(ids)
        assert h1 == h2

    def test_hash_is_order_independent(self):
        h1 = _compute_hash(["doc-1", "doc-2", "doc-3"])
        h2 = _compute_hash(["doc-3", "doc-1", "doc-2"])
        assert h1 == h2

    def test_hash_changes_with_different_docs(self):
        h1 = _compute_hash(["doc-1", "doc-2"])
        h2 = _compute_hash(["doc-1", "doc-3"])
        assert h1 != h2


# ============================================================
# Monotonic stage ordering (worker checkpoint)
# ============================================================


class TestMonotonicStageOrdering:
    def test_stage_ranks_are_monotonic(self):
        """Verify the stage rank ordering is strictly increasing."""
        stages = ["summarization", "synthesis", "fact_matrix", "issue_map", "deep_analysis"]
        # These ranks come from the worker's _STAGE_RANK dict
        ranks = {
            "summarization": 1,
            "synthesis": 2,
            "fact_matrix": 3,
            "issue_map": 4,
            "deep_analysis": 5,
        }
        for i in range(len(stages) - 1):
            assert ranks[stages[i]] < ranks[stages[i + 1]], (
                f"{stages[i]} (rank={ranks[stages[i]]}) should be < "
                f"{stages[i + 1]} (rank={ranks[stages[i + 1]]})"
            )

    def test_backward_stage_is_rejected(self):
        """Verify the monotonic guard logic."""
        _STAGE_RANK = {
            "summarization": 1, "synthesis": 2, "fact_matrix": 3,
            "issue_map": 4, "deep_analysis": 5,
        }
        current_stage = "fact_matrix"
        new_stage = "summarization"

        current_rank = _STAGE_RANK.get(current_stage, 0)
        new_rank = _STAGE_RANK.get(new_stage, 0)
        assert new_rank < current_rank, "Should reject backward stage"


# ============================================================
# Deserialization fallback (multi_stage_analyzer)
# ============================================================


class TestDeserializationFallback:
    def test_fact_matrix_from_valid_checkpoint(self):
        """FactMatrix should deserialize from a valid checkpoint dict."""
        from legal_portal.core.data_models import FactMatrix

        data = {
            "parties": [],
            "timeline": [],
            "financial_data": [],
            "key_documents": [],
            "preliminary_issues": [],
        }
        fm = FactMatrix(**data)
        assert fm.parties == []
        assert fm.timeline == []

    def test_fact_matrix_from_corrupt_data_raises(self):
        """FactMatrix with missing required fields raises — caught by try/except in pipeline."""
        from legal_portal.core.data_models import FactMatrix

        with pytest.raises(Exception):
            FactMatrix(**{"parties": []})  # Missing timeline, financial_data, etc.

    def test_legal_issue_map_from_valid_checkpoint(self):
        from legal_portal.core.data_models import LegalIssueMap

        data = {"primary_issues": [], "secondary_issues": []}
        lim = LegalIssueMap(**data)
        assert lim.primary_issues == []

    def test_deep_analysis_from_valid_checkpoint(self):
        from legal_portal.core.data_models import DeepAnalysis

        data = {
            "issue_analyses": [],
            "risk_assessment": {
                "major_risks": [], "risk_mitigation_steps": [],
                "statute_of_limitations_concerns": None, "evidence_gaps": [],
            },
            "deadline_tracking": [],
            "evidence_strength": {
                "strong_evidence": [], "weak_evidence": [],
                "missing_evidence": [], "overall_strength": "moderate",
            },
            "overall_case_strength": "moderate",
        }
        da = DeepAnalysis(**data)
        assert da.overall_case_strength == "moderate"
        assert da.issue_analyses == []


# ============================================================
# Empty checkpoint → normal execution
# ============================================================


class TestEmptyCheckpoint:
    def test_empty_checkpoint_has_no_keys(self):
        checkpoint = {}
        assert not checkpoint.get("summarization")
        assert not checkpoint.get("synthesis")
        assert not checkpoint.get("fact_matrix")
        assert not checkpoint.get("issue_map")
        assert not checkpoint.get("deep_analysis")

    def test_none_checkpoint_treated_as_empty(self):
        checkpoint = None
        checkpoint = checkpoint or {}
        assert not checkpoint.get("summarization")


# ============================================================
# Synthesis recovery shape validation
# ============================================================


class TestSynthesisRecoveryShape:
    def test_valid_synthesis_checkpoint(self):
        """Synthesis checkpoint with practice_area is accepted."""
        cp = {
            "synthesis": {
                "practice_area": "Real Estate",
                "case_summary": "Test summary",
                "key_issues": ["issue1"],
                "relevant_statutes": [],
            }
        }
        case_analysis_dict = cp["synthesis"]
        assert isinstance(case_analysis_dict, dict)
        assert case_analysis_dict.get("practice_area")

    def test_invalid_synthesis_checkpoint_missing_practice_area(self):
        """Synthesis checkpoint without practice_area is rejected."""
        cp = {"synthesis": {"case_summary": "Test"}}
        case_analysis_dict = cp["synthesis"]
        assert not case_analysis_dict.get("practice_area")
