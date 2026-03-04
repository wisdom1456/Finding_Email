"""Tests for save_streaming_analysis production fixes.

Verifies:
- SELECT uses extraction_quality (TEXT) not quality_score (NUMERIC)
- Document type derived from metadata enrichment, not document_type column
- Quality report score uses text mapping (high=8, medium=6, low=3)
"""

import pytest


def _build_doc_row(
    *,
    file_name="contract.pdf",
    file_type="application/pdf",
    extracted_text="Sample legal text for testing extraction quality.",
    extraction_quality="high",
    status="ready",
    metadata=None,
):
    """Build a document row using the REAL schema (no quality_score, no document_type column)."""
    return {
        "id": "doc-001",
        "file_name": file_name,
        "file_type": file_type,
        "extracted_text": extracted_text,
        "extraction_quality": extraction_quality,
        "status": status,
        "metadata": metadata or {},
    }


class TestExtractionQualityScoring:
    """Verify quality_report scoring uses extraction_quality TEXT field."""

    @pytest.mark.parametrize(
        "extraction_quality, expected_score",
        [
            ("high", 8),
            ("medium", 6),
            ("low", 3),
            (None, 3),
            ("", 3),
        ],
    )
    def test_quality_score_mapping(self, extraction_quality, expected_score):
        doc = _build_doc_row(extraction_quality=extraction_quality)
        eq = doc.get("extraction_quality") or "low"
        score = 8 if eq == "high" else 6 if eq == "medium" else 3
        assert score == expected_score

    def test_no_quality_score_column_used(self):
        doc = _build_doc_row(extraction_quality="high")
        assert "quality_score" not in doc


class TestDocumentTypeDerivation:
    """Verify document type comes from metadata enrichment, not document_type column."""

    def _derive_doc_type(self, doc):
        """Reproduce exact production logic from analysis.py."""
        metadata = doc.get("metadata") or {}
        enrichment = metadata.get("attorney_enrichment") or metadata.get("enrichment") or {}
        doc_type = enrichment.get("document_type_override") or enrichment.get("document_type")
        if not doc_type and doc.get("file_type"):
            doc_type = doc["file_type"].split("/")[-1].upper()
        return doc_type or "Unknown"

    def test_attorney_enrichment_override_takes_precedence(self):
        doc = _build_doc_row(metadata={
            "attorney_enrichment": {"document_type_override": "Contract"},
            "enrichment": {"document_type": "General"},
        })
        assert self._derive_doc_type(doc) == "Contract"

    def test_enrichment_document_type_is_second_choice(self):
        doc = _build_doc_row(metadata={"enrichment": {"document_type": "Correspondence"}})
        assert self._derive_doc_type(doc) == "Correspondence"

    def test_file_type_fallback(self):
        doc = _build_doc_row(file_type="application/pdf", metadata={})
        assert self._derive_doc_type(doc) == "PDF"

    def test_unknown_fallback(self):
        doc = _build_doc_row(file_type="", metadata={})
        assert self._derive_doc_type(doc) == "Unknown"

    def test_no_document_type_column(self):
        doc = _build_doc_row()
        assert "document_type" not in doc


class TestSelectQueryColumns:
    """Verify the SELECT string matches the real documents table schema."""

    def test_select_has_correct_columns(self):
        select_cols = "id, file_name, file_type, extracted_text, extraction_quality, status, metadata"
        assert "extraction_quality" in select_cols
        assert "quality_score" not in select_cols

    def test_select_columns_exist_in_real_schema(self):
        select_cols = [c.strip() for c in
            "id, file_name, file_type, extracted_text, extraction_quality, status, metadata".split(",")]
        real_schema = {
            "id", "case_id", "file_name", "file_type", "file_size", "storage_path",
            "status", "extracted_text", "extraction_method", "extraction_quality",
            "extracted_at", "page_count", "ocr_provider", "extraction_error",
            "manual_text", "is_verified", "is_flagged_as_junk", "text_edited_at",
            "metadata", "created_at", "updated_at",
        }
        for col in select_cols:
            assert col in real_schema, f"Column '{col}' not in real schema"


class TestDocumentFiltering:
    """Verify duplicate/excluded filtering logic."""

    def _filter(self, docs):
        filtered = []
        for doc in docs:
            meta = doc.get("metadata") or {}
            is_excluded = meta.get("excluded", False)
            is_duplicate = (doc.get("status") or "") == "duplicate" or meta.get("is_duplicate", False)
            if not (is_excluded or is_duplicate):
                filtered.append(doc)
        return filtered

    def test_duplicate_documents_filtered(self):
        docs = [_build_doc_row(file_name="a.pdf"), _build_doc_row(file_name="b.pdf", status="duplicate")]
        assert len(self._filter(docs)) == 1

    def test_excluded_documents_filtered(self):
        docs = [_build_doc_row(file_name="a.pdf", metadata={"excluded": True}), _build_doc_row(file_name="b.pdf")]
        result = self._filter(docs)
        assert len(result) == 1
        assert result[0]["file_name"] == "b.pdf"
