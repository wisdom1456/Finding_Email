"""Unit tests for Phase 3: Summary Caching (incremental analysis)."""

from __future__ import annotations

from types import SimpleNamespace


from legal_portal.utils.cache_manager import CacheManager, DocumentCache
from legal_portal.services.analysis.main_processor import (
    _compute_summary_cache_key,
    _split_docs_by_summary_cache,
    _write_summaries_to_cache,
    _SUMMARY_CACHE_VERSION,
)
from legal_portal.core.data_models import DocumentSummaryStructured


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(doc_id: str = "doc-1", content: str = "hello world", file_name: str = "test.pdf"):
    return SimpleNamespace(document_id=doc_id, content=content, file_name=file_name)


def _make_summary(doc_id: str = "doc-1") -> DocumentSummaryStructured:
    return DocumentSummaryStructured(
        document_id=doc_id,
        document_name="test.pdf",
        document_type="evidence",
        relevance_to_case="medium",
        extraction_quality="high",
    )


def _make_doc_cache(tmp_path: str) -> DocumentCache:
    cm = CacheManager(cache_dir=tmp_path, use_redis=False)
    return DocumentCache(cache_manager=cm)


# ---------------------------------------------------------------------------
# _compute_summary_cache_key
# ---------------------------------------------------------------------------

class TestComputeSummaryCacheKey:
    def test_deterministic(self):
        doc = _make_doc()
        k1 = _compute_summary_cache_key(doc, "T1", "model-v1")
        k2 = _compute_summary_cache_key(doc, "T1", "model-v1")
        assert k1 == k2

    def test_content_change_causes_miss(self):
        doc_a = _make_doc(content="original content")
        doc_b = _make_doc(content="modified content")
        assert _compute_summary_cache_key(doc_a, "T1", "model-v1") != \
               _compute_summary_cache_key(doc_b, "T1", "model-v1")

    def test_doc_id_change_causes_miss(self):
        doc_a = _make_doc(doc_id="doc-1")
        doc_b = _make_doc(doc_id="doc-2")
        assert _compute_summary_cache_key(doc_a, "T1", "model-v1") != \
               _compute_summary_cache_key(doc_b, "T1", "model-v1")

    def test_model_version_change_causes_miss(self):
        doc = _make_doc()
        assert _compute_summary_cache_key(doc, "T1", "model-v1") != \
               _compute_summary_cache_key(doc, "T1", "model-v2")

    def test_tier_change_causes_miss(self):
        """T1 and T2 must not share cache entries even for identical content."""
        doc = _make_doc()
        assert _compute_summary_cache_key(doc, "T1", "model-v1") != \
               _compute_summary_cache_key(doc, "T2", "model-v1")


# ---------------------------------------------------------------------------
# DocumentCache — new summary methods
# ---------------------------------------------------------------------------

class TestDocumentCacheSummaryMethods:
    def test_get_returns_none_on_miss(self, tmp_path):
        dc = _make_doc_cache(str(tmp_path))
        assert dc.get_document_summary("nonexistent") is None

    def test_roundtrip(self, tmp_path):
        dc = _make_doc_cache(str(tmp_path))
        summary = _make_summary()
        dc.cache_document_summary("key-abc", summary.model_dump())
        result = dc.get_document_summary("key-abc")
        assert result is not None
        assert result["document_id"] == "doc-1"
        assert result["document_type"] == "evidence"

    def test_overwrite(self, tmp_path):
        dc = _make_doc_cache(str(tmp_path))
        dc.cache_document_summary("key-abc", {"document_id": "old"})
        dc.cache_document_summary("key-abc", {"document_id": "new"})
        assert dc.get_document_summary("key-abc")["document_id"] == "new"


# ---------------------------------------------------------------------------
# _split_docs_by_summary_cache
# ---------------------------------------------------------------------------

class TestSplitDocsBySummaryCache:
    def test_all_miss_on_empty_cache(self, tmp_path):
        docs = [_make_doc("a"), _make_doc("b"), _make_doc("c")]
        dc = _make_doc_cache(str(tmp_path))
        cached, uncached, key_map = _split_docs_by_summary_cache(docs, "T1", dc, "model-v1")
        assert cached == []
        assert len(uncached) == 3
        assert len(key_map) == 3

    def test_all_hit_after_population(self, tmp_path):
        docs = [_make_doc("a"), _make_doc("b")]
        dc = _make_doc_cache(str(tmp_path))
        model_v = "model-v1"
        for doc in docs:
            key = _compute_summary_cache_key(doc, "T1", model_v)
            dc.cache_document_summary(key, _make_summary(doc.document_id).model_dump())

        cached, uncached, key_map = _split_docs_by_summary_cache(docs, "T1", dc, model_v)
        assert len(cached) == 2
        assert uncached == []
        assert key_map == {}

    def test_mixed_hit_and_miss(self, tmp_path):
        docs = [_make_doc("hit-doc", content="same"), _make_doc("miss-doc", content="different")]
        dc = _make_doc_cache(str(tmp_path))
        model_v = "model-v1"
        hit_key = _compute_summary_cache_key(docs[0], "T1", model_v)
        dc.cache_document_summary(hit_key, _make_summary("hit-doc").model_dump())

        cached, uncached, key_map = _split_docs_by_summary_cache(docs, "T1", dc, model_v)
        assert len(cached) == 1
        assert cached[0].document_id == "hit-doc"
        assert len(uncached) == 1
        assert uncached[0].document_id == "miss-doc"
        assert "miss-doc" in key_map

    def test_corrupt_cache_treated_as_miss(self, tmp_path, caplog):
        doc = _make_doc("bad-doc")
        dc = _make_doc_cache(str(tmp_path))
        model_v = "model-v1"
        key = _compute_summary_cache_key(doc, "T1", model_v)
        # Store something that won't validate as DocumentSummaryStructured
        dc.cache_document_summary(key, {"garbage": True, "document_type": None})

        cached, uncached, _ = _split_docs_by_summary_cache([doc], "T1", dc, model_v)
        assert cached == []
        assert len(uncached) == 1

    def test_tier_isolation(self, tmp_path):
        """A T2-cached summary must not appear as a T1 cache hit."""
        doc = _make_doc("shared-doc")
        dc = _make_doc_cache(str(tmp_path))
        model_v = "model-v1"
        t2_key = _compute_summary_cache_key(doc, "T2", model_v)
        dc.cache_document_summary(t2_key, _make_summary("shared-doc").model_dump())

        # Looking up under T1 should miss
        cached, uncached, _ = _split_docs_by_summary_cache([doc], "T1", dc, model_v)
        assert cached == []
        assert len(uncached) == 1


# ---------------------------------------------------------------------------
# _write_summaries_to_cache
# ---------------------------------------------------------------------------

class TestWriteSummariesToCache:
    def test_successful_write(self, tmp_path):
        doc = _make_doc("doc-1")
        dc = _make_doc_cache(str(tmp_path))
        model_v = "model-v1"
        key = _compute_summary_cache_key(doc, "T1", model_v)
        key_by_id = {"doc-1": key}
        summary = _make_summary("doc-1")

        writes = _write_summaries_to_cache([summary], [doc], key_by_id, dc, "T1")
        assert writes == 1
        assert dc.get_document_summary(key) is not None

    def test_skips_doc_id_not_in_input_set(self, tmp_path, caplog):
        """Summary with doc_id absent from uncached_docs must not be written."""
        doc = _make_doc("doc-1")
        dc = _make_doc_cache(str(tmp_path))
        key_by_id = {"doc-1": "some-key"}
        stray_summary = _make_summary("stray-doc-99")

        writes = _write_summaries_to_cache([stray_summary], [doc], key_by_id, dc, "T1")
        assert writes == 0

    def test_skips_missing_key(self, tmp_path):
        """Summary whose doc_id has no entry in key_by_id is skipped."""
        doc = _make_doc("doc-1")
        dc = _make_doc_cache(str(tmp_path))
        key_by_id: dict = {}  # empty — no key for doc-1
        summary = _make_summary("doc-1")

        writes = _write_summaries_to_cache([summary], [doc], key_by_id, dc, "T1")
        assert writes == 0

    def test_schema_consistency_after_roundtrip(self, tmp_path):
        """Cached and re-loaded summary must round-trip through DocumentSummaryStructured."""
        doc = _make_doc("doc-42")
        dc = _make_doc_cache(str(tmp_path))
        model_v = "model-v1"
        key = _compute_summary_cache_key(doc, "T1", model_v)
        key_by_id = {"doc-42": key}
        original = _make_summary("doc-42")

        _write_summaries_to_cache([original], [doc], key_by_id, dc, "T1")
        raw = dc.get_document_summary(key)
        restored = DocumentSummaryStructured.model_validate(raw)

        assert restored.document_id == original.document_id
        assert restored.document_type == original.document_type
        assert restored.extraction_quality == original.extraction_quality


# ---------------------------------------------------------------------------
# Integration: model version bump forces full miss
# ---------------------------------------------------------------------------

class TestModelVersionBump:
    def test_version_bump_invalidates_cache(self, tmp_path):
        doc = _make_doc("doc-v")
        dc = _make_doc_cache(str(tmp_path))
        old_version = "model-v1"
        new_version = "model-v2"

        old_key = _compute_summary_cache_key(doc, "T1", old_version)
        dc.cache_document_summary(old_key, _make_summary("doc-v").model_dump())

        # With new version, lookup should miss
        cached, uncached, _ = _split_docs_by_summary_cache([doc], "T1", dc, new_version)
        assert cached == []
        assert len(uncached) == 1

    def test_summary_cache_version_constant_exists(self):
        assert isinstance(_SUMMARY_CACHE_VERSION, str)
        assert len(_SUMMARY_CACHE_VERSION) > 0
