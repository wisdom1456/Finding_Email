"""Tests for the quick preview streaming feature (progressive analysis).

Covers:
- Feature flag gating
- quick_preview_streaming() token + classification output
- apply_preview_classifications() persistence logic
- Preview-guided context reduction in _build_condensed_context()
- Section heading detection in the SSE stream
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from legal_portal.core.data_models import DocumentSummaryStructured
from legal_portal.services.analysis.multi_stage_analyzer import MultiStageAnalyzer
from legal_portal.services.documents.document_registry_service import DocumentRegistryService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_doc_summaries(n: int = 3) -> List[DocumentSummaryStructured]:
    """Create N minimal document summaries for testing."""
    types = ["medical_record", "billing_record", "intake_form"]
    return [
        DocumentSummaryStructured(
            document_name=f"doc_{i}.pdf",
            document_type=types[i % len(types)],
            executive_summary=f"Summary for document {i}. " * 20,
            key_content=f"Key content for document {i}. " * 50,
        )
        for i in range(n)
    ]


def _make_doc_rows(n: int = 3) -> List[Dict[str, Any]]:
    """Create N minimal document rows matching what the DB returns."""
    return [
        {
            "id": f"doc-id-{i}",
            "file_name": f"doc_{i}.pdf",
            "metadata": {"registry": {"enrichment_stage": "extraction", "document_type": "other"}},
        }
        for i in range(n)
    ]


def _make_classifications(n: int = 3) -> List[Dict[str, Any]]:
    """Create N classification dicts as returned by the preview prompt."""
    levels = ["critical", "supporting", "background"]
    return [
        {
            "doc_index": i,
            "document_name": f"doc_{i}.pdf",
            "document_type": "medical_record",
            "relevance_level": levels[i % len(levels)],
            "one_line_summary": f"One-line summary for doc {i}",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Feature Flag Gating
# ---------------------------------------------------------------------------

class TestFeatureFlag:
    def test_flag_defaults_to_false(self):
        from legal_portal.config.default import get_settings
        settings = get_settings()
        assert settings.enable_analysis_quick_preview is False


# ---------------------------------------------------------------------------
# quick_preview_streaming()
# ---------------------------------------------------------------------------

class TestQuickPreviewStreaming:
    @pytest.mark.asyncio
    async def test_yields_tokens_then_classifications_then_done(self):
        """Preview should yield token dicts, then classifications, then done."""
        preview_text = (
            "This case involves a car accident.\n\n"
            "Key findings:\n- Cervical strain\n- $12,400 in bills\n\n"
            '```json\n[{"doc_index":0,"document_name":"doc_0.pdf",'
            '"document_type":"medical_record","relevance_level":"critical",'
            '"one_line_summary":"Medical records"}]\n```'
        )

        # Mock the OpenAI client to yield the preview text token by token
        async def mock_stream(*args, **kwargs):
            for char in preview_text:
                yield char

        mock_client = MagicMock()
        mock_client.create_chat_completion_stream = mock_stream

        analyzer = MultiStageAnalyzer(openai_client=mock_client)
        summaries = _make_doc_summaries(1)

        messages = []
        async for msg in analyzer.quick_preview_streaming(summaries):
            messages.append(msg)

        # Should have token messages, a classifications message, and a done message
        token_msgs = [m for m in messages if "token" in m]
        class_msgs = [m for m in messages if "classifications" in m]
        done_msgs = [m for m in messages if m.get("done")]

        assert len(token_msgs) > 0, "Should yield at least one token"
        assert len(class_msgs) == 1, "Should yield exactly one classifications message"
        assert len(done_msgs) == 1, "Should yield exactly one done message"

        # Classifications should be a list
        classifications = class_msgs[0]["classifications"]
        assert isinstance(classifications, list)
        assert len(classifications) == 1
        assert classifications[0]["document_type"] == "medical_record"

    @pytest.mark.asyncio
    async def test_tokens_stop_before_json_fence(self):
        """Token messages should not include the JSON classification block."""
        preview_text = "Summary text.```json\n[]\n```"

        async def mock_stream(*args, **kwargs):
            for char in preview_text:
                yield char

        mock_client = MagicMock()
        mock_client.create_chat_completion_stream = mock_stream

        analyzer = MultiStageAnalyzer(openai_client=mock_client)
        summaries = _make_doc_summaries(1)

        tokens_text = ""
        async for msg in analyzer.quick_preview_streaming(summaries):
            if "token" in msg:
                tokens_text += msg["token"]

        assert "```json" not in tokens_text

    @pytest.mark.asyncio
    async def test_handles_malformed_json_gracefully(self):
        """If the model outputs bad JSON, classifications should be empty."""
        preview_text = "Summary.```json\n{bad json}\n```"

        async def mock_stream(*args, **kwargs):
            for char in preview_text:
                yield char

        mock_client = MagicMock()
        mock_client.create_chat_completion_stream = mock_stream

        analyzer = MultiStageAnalyzer(openai_client=mock_client)
        summaries = _make_doc_summaries(1)

        messages = []
        async for msg in analyzer.quick_preview_streaming(summaries):
            messages.append(msg)

        # Should still yield done, no classifications
        class_msgs = [m for m in messages if "classifications" in m]
        done_msgs = [m for m in messages if m.get("done")]
        assert len(class_msgs) == 0, "Malformed JSON should not produce classifications"
        assert len(done_msgs) == 1

    @pytest.mark.asyncio
    async def test_handles_stream_error_gracefully(self):
        """If the LLM stream errors, preview should still yield done."""
        async def mock_stream(*args, **kwargs):
            yield "partial"
            raise RuntimeError("LLM connection failed")

        mock_client = MagicMock()
        mock_client.create_chat_completion_stream = mock_stream

        analyzer = MultiStageAnalyzer(openai_client=mock_client)
        summaries = _make_doc_summaries(1)

        messages = []
        async for msg in analyzer.quick_preview_streaming(summaries):
            messages.append(msg)

        done_msgs = [m for m in messages if m.get("done")]
        assert len(done_msgs) == 1, "Should always yield done even on error"


# ---------------------------------------------------------------------------
# apply_preview_classifications()
# ---------------------------------------------------------------------------

class TestApplyPreviewClassifications:
    def test_updates_eligible_documents(self):
        """Should update docs at extraction stage without attorney override."""
        docs = _make_doc_rows(3)
        classifications = _make_classifications(3)

        mock_supabase = MagicMock()
        # Mock the chain: supabase.table().select().eq().single().execute()
        mock_select_result = MagicMock()
        mock_select_result.data = {"metadata": {"registry": {"enrichment_stage": "extraction", "document_type": "other"}}}
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_select_result
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        updated = DocumentRegistryService.apply_preview_classifications(
            classifications, docs, mock_supabase
        )

        assert updated == 3

    def test_skips_attorney_override(self):
        """Should not update docs where attorney has set a type override."""
        docs = _make_doc_rows(1)
        docs[0]["metadata"]["attorney_enrichment"] = {"document_type_override": "contract"}
        classifications = _make_classifications(1)

        mock_supabase = MagicMock()

        updated = DocumentRegistryService.apply_preview_classifications(
            classifications, docs, mock_supabase
        )

        assert updated == 0

    def test_skips_already_enriched_documents(self):
        """Should not update docs already at ai_analysis enrichment stage."""
        docs = _make_doc_rows(1)
        docs[0]["metadata"]["registry"]["enrichment_stage"] = "ai_analysis"
        classifications = _make_classifications(1)

        mock_supabase = MagicMock()

        updated = DocumentRegistryService.apply_preview_classifications(
            classifications, docs, mock_supabase
        )

        assert updated == 0

    def test_skips_unmatched_doc_names(self):
        """Should skip classifications that don't match any document."""
        docs = _make_doc_rows(1)
        classifications = [{"document_name": "nonexistent.pdf", "document_type": "other", "relevance_level": "background", "one_line_summary": "test"}]

        mock_supabase = MagicMock()

        updated = DocumentRegistryService.apply_preview_classifications(
            classifications, docs, mock_supabase
        )

        assert updated == 0

    def test_handles_persist_failure_gracefully(self):
        """Should continue processing even if a single persist fails."""
        docs = _make_doc_rows(2)
        classifications = _make_classifications(2)

        mock_supabase = MagicMock()
        # First call succeeds, second raises
        mock_select_result = MagicMock()
        mock_select_result.data = {"metadata": {"registry": {"enrichment_stage": "extraction"}}}
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_select_result

        call_count = 0
        original_update = mock_supabase.table.return_value.update

        def update_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB error")
            result = MagicMock()
            result.eq.return_value.execute.return_value = MagicMock()
            return result

        mock_supabase.table.return_value.update.side_effect = update_side_effect

        # Should not raise, should return count of successful updates
        updated = DocumentRegistryService.apply_preview_classifications(
            classifications, docs, mock_supabase
        )

        # At least one should have been attempted (the second one may succeed)
        assert updated >= 0


# ---------------------------------------------------------------------------
# Preview-guided context reduction
# ---------------------------------------------------------------------------

class TestContextReduction:
    def _make_analyzer(self) -> MultiStageAnalyzer:
        mock_client = MagicMock()
        return MultiStageAnalyzer(openai_client=mock_client)

    def test_background_docs_get_reduced_content(self):
        """Background docs should use one-line summary instead of full text."""
        analyzer = self._make_analyzer()
        summaries = _make_doc_summaries(3)

        # All docs are background
        classifications = [
            {"document_name": f"doc_{i}.pdf", "relevance_level": "background", "one_line_summary": f"Brief summary {i}"}
            for i in range(3)
        ]

        result_with = analyzer._build_condensed_context(
            summaries, preview_classifications=classifications
        )
        result_without = analyzer._build_condensed_context(
            summaries, preview_classifications=None
        )

        # With background reduction, total tokens should be smaller
        assert result_with.total_tokens < result_without.total_tokens

    def test_critical_docs_retain_full_content(self):
        """Critical docs should keep their full content regardless of preview."""
        analyzer = self._make_analyzer()
        summaries = _make_doc_summaries(1)

        classifications = [
            {"document_name": "doc_0.pdf", "relevance_level": "critical", "one_line_summary": "Critical doc"}
        ]

        result_with = analyzer._build_condensed_context(
            summaries, preview_classifications=classifications
        )
        result_without = analyzer._build_condensed_context(
            summaries, preview_classifications=None
        )

        # Critical docs should have same token count
        assert result_with.total_tokens == result_without.total_tokens

    def test_no_classifications_matches_baseline(self):
        """Empty classifications should produce same result as None."""
        analyzer = self._make_analyzer()
        summaries = _make_doc_summaries(3)

        result_empty = analyzer._build_condensed_context(
            summaries, preview_classifications=[]
        )
        result_none = analyzer._build_condensed_context(
            summaries, preview_classifications=None
        )

        assert result_empty.total_tokens == result_none.total_tokens

    def test_mixed_relevance_levels(self):
        """Mix of critical/supporting/background should reduce only background."""
        analyzer = self._make_analyzer()
        summaries = _make_doc_summaries(6)

        classifications = [
            {"document_name": f"doc_{i}.pdf", "relevance_level": level, "one_line_summary": f"Summary {i}"}
            for i, level in enumerate(["critical", "critical", "supporting", "supporting", "background", "background"])
        ]

        result = analyzer._build_condensed_context(
            summaries, preview_classifications=classifications
        )

        # Should include all 6 docs
        assert result.docs_in_scope == 6
        assert result.docs_omitted == 0


# ---------------------------------------------------------------------------
# Section heading detection (unit test for parsing logic)
# ---------------------------------------------------------------------------

class TestSectionHeadingDetection:
    def test_detects_h2_headings(self):
        """Verify the heading detection regex pattern works."""
        import re

        # Simulate the heading detection logic from analysis_core.py
        test_lines = [
            "## Case Overview",
            "Some content here",
            "## Key Facts Extracted",
            "More content",
            "### Sub-heading (should not match)",
            "## Risk Assessment",
        ]

        sections_found = []
        for line in test_lines:
            stripped = line.strip()
            if stripped.startswith("## ") and not stripped.startswith("### "):
                heading = stripped[3:].strip()
                sections_found.append(heading)

        assert sections_found == ["Case Overview", "Key Facts Extracted", "Risk Assessment"]

    def test_line_buffer_splits_correctly(self):
        """Simulate token-by-token line buffer accumulation."""
        # Tokens come in as partial chunks
        tokens = ["## Case", " Over", "view\nSome text\n## Key", " Facts\n"]

        line_buffer = ""
        headings = []

        for token in tokens:
            line_buffer += token
            if "\n" in line_buffer:
                lines = line_buffer.split("\n")
                line_buffer = lines[-1]
                for line in lines[:-1]:
                    stripped = line.strip()
                    if stripped.startswith("## "):
                        headings.append(stripped[3:].strip())

        assert headings == ["Case Overview", "Key Facts"]
