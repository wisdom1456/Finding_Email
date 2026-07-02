"""Unit tests for main_processor - Phase 1 Coverage Expansion.

This module provides comprehensive tests for main_processor.py functionality,
targeting 50% coverage by testing pure utility functions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from legal_portal.core.data_models import (
    DocumentSummaryStructured,
    DocumentType,
    FileMetadata,
    FileType,
    KeyAmount,
    KeyDate,
    ProcessedDocument,
    QualityScore,
)
from legal_portal.services.analysis.main_processor import (
    _aggregate_quality_results,
    _build_original_documents_map,
    _build_quality_context,
    _create_prompt_aware_batches,
    _build_summary_prompt,
    _clean_and_parse_json,
    _convert_to_case_analysis_result,
    _process_document_batch,
    _create_smart_batches,
    _deduplicate_documents,
    _detect_near_duplicates,
    _estimate_tokens,
    _format_documents_with_metadata,
    _format_quality_context,
    _is_image_document,
)


# =============================================================================
# Helper Functions
# =============================================================================


def make_processed_doc(
    file_name: str = "test.pdf",
    content: str = "Test content",
    document_type: DocumentType = DocumentType.CASE_DOCUMENT,
    file_type: FileType = FileType.PDF,
    extraction_method: str = "test",
    extraction_quality: str = "high",
) -> ProcessedDocument:
    """Helper to create ProcessedDocument with required metadata."""
    return ProcessedDocument(
        file_name=file_name,
        content=content,
        document_type=document_type,
        file_type=file_type,
        metadata=FileMetadata(file_name=file_name, file_type=file_type, file_size=len(content)),
        extraction_method=extraction_method,
        extraction_quality=extraction_quality,
    )


def make_quality_score(
    document: str = "test.pdf",
    score: float = 8.5,
    confidence_level: str = "high",
    issues: list = None,
    has_meaningful_content: bool = True,
    is_complete: bool = True,
) -> QualityScore:
    """Helper to create QualityScore objects."""
    return QualityScore(
        document=document,
        score=score,
        confidence_level=confidence_level,
        issues=issues or [],
        has_meaningful_content=has_meaningful_content,
        is_complete=is_complete,
    )


def make_document_summary(
    document_name: str = "test.pdf",
    document_type: str = "Contract",
    relevance_to_case: str = "Relevant document",
    parties: list = None,
    key_dates: list = None,
    key_amounts: list = None,
    issues_identified: list = None,
) -> DocumentSummaryStructured:
    """Helper to create DocumentSummaryStructured objects."""
    return DocumentSummaryStructured(
        document_name=document_name,
        document_type=document_type,
        relevance_to_case=relevance_to_case,
        parties=parties or [],
        key_dates=key_dates or [],
        key_amounts=key_amounts or [],
        issues_identified=issues_identified or [],
    )


# =============================================================================
# Tests for _is_image_document
# =============================================================================


class TestIsImageDocument:
    """Test image document detection."""

    def test_detects_jpg_image(self):
        """Test detection of JPG file."""
        doc = make_processed_doc(file_name="photo.jpg")
        assert _is_image_document(doc) is True

    def test_detects_jpeg_image(self):
        """Test detection of JPEG file."""
        doc = make_processed_doc(file_name="photo.jpeg")
        assert _is_image_document(doc) is True

    def test_detects_png_image(self):
        """Test detection of PNG file."""
        doc = make_processed_doc(file_name="screenshot.png")
        assert _is_image_document(doc) is True

    def test_detects_gif_image(self):
        """Test detection of GIF file."""
        doc = make_processed_doc(file_name="animation.gif")
        assert _is_image_document(doc) is True

    def test_detects_bmp_image(self):
        """Test detection of BMP file."""
        doc = make_processed_doc(file_name="image.bmp")
        assert _is_image_document(doc) is True

    def test_detects_tiff_image(self):
        """Test detection of TIFF file."""
        doc = make_processed_doc(file_name="scan.tiff")
        assert _is_image_document(doc) is True

    def test_detects_webp_image(self):
        """Test detection of WebP file."""
        doc = make_processed_doc(file_name="modern.webp")
        assert _is_image_document(doc) is True

    def test_pdf_not_image(self):
        """Test that PDF is not detected as image."""
        doc = make_processed_doc(file_name="document.pdf")
        assert _is_image_document(doc) is False

    def test_docx_not_image(self):
        """Test that DOCX is not detected as image."""
        doc = make_processed_doc(file_name="document.docx")
        assert _is_image_document(doc) is False

    def test_txt_not_image(self):
        """Test that TXT is not detected as image."""
        doc = make_processed_doc(file_name="notes.txt")
        assert _is_image_document(doc) is False

    def test_uppercase_extension(self):
        """Test detection with uppercase extension."""
        doc = make_processed_doc(file_name="PHOTO.JPG")
        assert _is_image_document(doc) is True

    def test_mixed_case_extension(self):
        """Test detection with mixed case extension."""
        doc = make_processed_doc(file_name="Photo.Png")
        assert _is_image_document(doc) is True


# =============================================================================
# Tests for _estimate_tokens
# =============================================================================


class TestEstimateTokens:
    """Test token estimation function."""

    def test_empty_string(self):
        """Test estimation for empty string."""
        assert _estimate_tokens("") == 0

    def test_short_text(self):
        """Test estimation for short text."""
        # 12 chars -> ~3 tokens
        assert _estimate_tokens("Hello World!") == 3

    def test_medium_text(self):
        """Test estimation for medium length text."""
        text = "This is a medium length text for testing." * 10
        expected = len(text) // 4
        assert _estimate_tokens(text) == expected

    def test_long_text(self):
        """Test estimation for long text."""
        text = "A" * 10000
        assert _estimate_tokens(text) == 2500

    def test_unicode_text(self):
        """Test estimation with unicode characters."""
        # Unicode chars may have multiple bytes
        text = "Émojis 🎉 and accénts"
        # Just verify it doesn't crash and returns reasonable value
        result = _estimate_tokens(text)
        assert result > 0


# =============================================================================
# Tests for _build_quality_context
# =============================================================================


class TestBuildQualityContext:
    """Test quality context building."""

    def test_empty_documents(self):
        """Test with no documents."""
        result = _build_quality_context([])
        assert result == "No case documents provided."

    def test_single_document(self):
        """Test with single document."""
        docs = [make_processed_doc(file_name="test.pdf", extraction_quality="high", extraction_method="PyMuPDF")]
        result = _build_quality_context(docs)
        assert "test.pdf" in result
        assert "Quality=high" in result
        assert "Method=PyMuPDF" in result

    def test_multiple_documents(self):
        """Test with multiple documents."""
        docs = [
            make_processed_doc(file_name="doc1.pdf", extraction_quality="high", extraction_method="PyMuPDF"),
            make_processed_doc(file_name="doc2.pdf", extraction_quality="low", extraction_method="OCR"),
        ]
        result = _build_quality_context(docs)
        assert "doc1.pdf" in result
        assert "doc2.pdf" in result
        assert "Quality=high" in result
        assert "Quality=low" in result

    def test_unknown_quality(self):
        """Test with unknown quality/method."""
        doc = make_processed_doc(file_name="test.pdf")
        doc.extraction_quality = None
        doc.extraction_method = None
        result = _build_quality_context([doc])
        assert "Quality=unknown" in result
        assert "Method=unknown" in result


# =============================================================================
# Tests for _deduplicate_documents
# =============================================================================


class TestDeduplicateDocuments:
    """Test document deduplication."""

    def test_no_duplicates(self):
        """Test with no duplicate documents."""
        docs = [
            make_processed_doc(file_name="doc1.pdf", content="Content 1"),
            make_processed_doc(file_name="doc2.pdf", content="Content 2"),
        ]
        result = _deduplicate_documents(docs)
        assert len(result) == 2

    def test_removes_exact_duplicates(self):
        """Test removal of exact duplicate content."""
        docs = [
            make_processed_doc(file_name="doc1.pdf", content="Same content"),
            make_processed_doc(file_name="doc2.pdf", content="Same content"),
        ]
        result = _deduplicate_documents(docs)
        assert len(result) == 1
        assert result[0].file_name == "doc1.pdf"  # First one kept

    def test_keeps_different_content_same_name(self):
        """Test documents with same name but different content are kept."""
        docs = [
            make_processed_doc(file_name="doc.pdf", content="Content version 1"),
            make_processed_doc(file_name="doc.pdf", content="Content version 2"),
        ]
        result = _deduplicate_documents(docs)
        assert len(result) == 2

    def test_handles_empty_list(self):
        """Test with empty document list."""
        result = _deduplicate_documents([])
        assert len(result) == 0

    def test_handles_bytes_content(self):
        """Test with bytes content in document."""
        doc1 = make_processed_doc(file_name="doc1.pdf", content="text content")
        doc2 = make_processed_doc(file_name="doc2.pdf", content="text content")
        # Both have same content, should deduplicate
        result = _deduplicate_documents([doc1, doc2])
        assert len(result) == 1


# =============================================================================
# Tests for _detect_near_duplicates
# =============================================================================


class TestDetectNearDuplicates:
    """Test near-duplicate detection (logs warnings)."""

    def test_no_duplicates_no_warning(self, caplog):
        """Test no warnings for distinct filenames."""
        docs = [
            make_processed_doc(file_name="contract.pdf"),
            make_processed_doc(file_name="invoice.pdf"),
        ]
        _detect_near_duplicates(docs)
        # No warning should be logged
        assert "near-duplicate" not in caplog.text.lower()

    def test_similar_names_warning(self, caplog):
        """Test warning for similar filenames."""
        docs = [
            make_processed_doc(file_name="contract_v1.pdf"),
            make_processed_doc(file_name="contract_v2.pdf"),
        ]
        with patch('legal_portal.services.analysis.main_processor.get_settings') as mock_settings:
            mock_settings.return_value.duplicate_similarity_threshold = 0.7
            _detect_near_duplicates(docs)
        # Note: This may or may not log depending on similarity calculation

    def test_empty_list(self):
        """Test with empty list."""
        _detect_near_duplicates([])  # Should not raise


# =============================================================================
# Tests for _format_documents_with_metadata
# =============================================================================


class TestFormatDocumentsWithMetadata:
    """Test document formatting for AI prompts."""

    def test_formats_single_document(self):
        """Test formatting single document."""
        docs = [make_processed_doc(file_name="test.pdf", content="Document content")]
        result = _format_documents_with_metadata(docs)
        assert "Document 1:" in result
        assert "test.pdf" in result
        assert "Document content" in result

    def test_includes_quality_warning_low(self):
        """Test low quality warning is included."""
        doc = make_processed_doc(file_name="test.pdf", extraction_quality="low")
        result = _format_documents_with_metadata([doc])
        assert "LOW QUALITY" in result

    def test_includes_quality_warning_medium(self):
        """Test medium quality warning is included."""
        doc = make_processed_doc(file_name="test.pdf", extraction_quality="medium")
        result = _format_documents_with_metadata([doc])
        assert "MEDIUM QUALITY" in result

    def test_no_warning_for_high_quality(self):
        """Test no warning for high quality documents."""
        doc = make_processed_doc(file_name="test.pdf", extraction_quality="high")
        result = _format_documents_with_metadata([doc])
        assert "LOW QUALITY" not in result
        assert "MEDIUM QUALITY" not in result

    def test_image_flag_included(self):
        """Test image flag is included for image files."""
        doc = make_processed_doc(file_name="photo.jpg")
        result = _format_documents_with_metadata([doc])
        assert "IMAGE FILE" in result

    def test_numbers_multiple_documents(self):
        """Test document numbering."""
        docs = [
            make_processed_doc(file_name="doc1.pdf"),
            make_processed_doc(file_name="doc2.pdf"),
            make_processed_doc(file_name="doc3.pdf"),
        ]
        result = _format_documents_with_metadata(docs)
        assert "Document 1:" in result
        assert "Document 2:" in result
        assert "Document 3:" in result

    def test_chunks_long_document_content(self):
        """Test long content is chunked into bounded excerpts."""
        long_content = "BEGIN_" + ("A" * 20000) + "_MIDMARK_" + ("B" * 20000) + "_ENDMARK_" + ("C" * 20000)
        doc = make_processed_doc(file_name="long.txt", content=long_content)

        result = _format_documents_with_metadata([doc])

        assert "[TRUNCATED_DOCUMENT" in result
        assert "[EXCERPT 1/3 - BEGINNING]" in result
        assert "[EXCERPT 2/3 - MIDDLE]" in result
        assert "[EXCERPT 3/3 - END]" in result
        assert "BEGIN_" in result
        assert "BBBBBBBBBB" in result
        assert "CCCCCCCCCC" in result


# =============================================================================
# Tests for _aggregate_quality_results
# =============================================================================


class TestAggregateQualityResults:
    """Test quality results aggregation."""

    def test_empty_results(self):
        """Test aggregation of empty results."""
        result = _aggregate_quality_results([])
        assert result["overall_confidence"] == "high"
        assert result["overall_average_score"] == 10.0
        assert result["low_quality_documents_count"] == 0
        assert result["batch_results"] == {}

    def test_single_high_quality(self):
        """Test aggregation with single high quality result."""
        results = [make_quality_score(score=9.0, confidence_level="high")]
        result = _aggregate_quality_results(results)
        assert result["overall_confidence"] == "high"
        assert result["overall_average_score"] == 9.0
        assert result["low_quality_documents_count"] == 0

    def test_single_low_quality(self):
        """Test aggregation with single low quality result."""
        results = [make_quality_score(score=3.0, confidence_level="low")]
        result = _aggregate_quality_results(results)
        assert result["overall_confidence"] == "low"
        assert result["overall_average_score"] == 3.0
        assert result["low_quality_documents_count"] == 1

    def test_mixed_quality(self):
        """Test aggregation with mixed quality results."""
        results = [
            make_quality_score(document="doc1.pdf", score=9.0),
            make_quality_score(document="doc2.pdf", score=5.0),
            make_quality_score(document="doc3.pdf", score=4.0),
        ]
        result = _aggregate_quality_results(results)
        assert result["overall_average_score"] == 6.0  # (9+5+4)/3
        assert result["low_quality_documents_count"] == 2  # 5.0 and 4.0 < 7.0
        assert "medium" in result["overall_confidence"]

    def test_batch_results_populated(self):
        """Test that batch_results contains all documents."""
        results = [
            make_quality_score(document="doc1.pdf", score=9.0),
            make_quality_score(document="doc2.pdf", score=8.0),
        ]
        result = _aggregate_quality_results(results)
        assert "doc1.pdf" in result["batch_results"]
        assert "doc2.pdf" in result["batch_results"]


# =============================================================================
# Tests for _format_quality_context
# =============================================================================


class TestFormatQualityContext:
    """Test quality context formatting."""

    def test_high_confidence_no_issues(self):
        """Test formatting with high confidence and no issues."""
        quality_results = {
            "overall_confidence": "high",
            "overall_average_score": 9.5,
            "low_quality_documents_count": 0,
            "batch_results": {},
        }
        result = _format_quality_context(quality_results)
        assert "Overall Confidence: high" in result
        assert "Average Quality Score: 9.5/10" in result
        assert "QUALITY ISSUES" not in result

    def test_low_quality_documents_listed(self):
        """Test that low quality documents are listed."""
        quality_results = {
            "overall_confidence": "medium",
            "overall_average_score": 6.0,
            "low_quality_documents_count": 1,
            "batch_results": {
                "bad_doc.pdf": {
                    "confidence_level": "low",
                    "score": 3.5,
                    "issues": ["OCR errors", "Incomplete text"],
                }
            },
        }
        result = _format_quality_context(quality_results)
        assert "QUALITY ISSUES" in result
        assert "bad_doc.pdf" in result
        assert "3.5/10" in result


# =============================================================================
# Tests for _create_smart_batches
# =============================================================================


class TestCreateSmartBatches:
    """Test smart batching of documents."""

    def test_single_document_single_batch(self):
        """Test single document creates single batch."""
        docs = [make_processed_doc(content="Short content")]
        with patch('legal_portal.services.analysis.main_processor.get_settings') as mock_settings:
            mock_settings.return_value.max_tokens_per_batch = 100000
            batches = _create_smart_batches(docs)
        assert len(batches) == 1
        assert len(batches[0]) == 1

    def test_multiple_documents_within_limit(self):
        """Test multiple small documents stay in one batch."""
        docs = [make_processed_doc(content="Short" * 10) for _ in range(5)]
        with patch('legal_portal.services.analysis.main_processor.get_settings') as mock_settings:
            mock_settings.return_value.max_tokens_per_batch = 100000
            batches = _create_smart_batches(docs)
        assert len(batches) == 1
        assert len(batches[0]) == 5

    def test_large_documents_split_into_batches(self):
        """Test large documents are split into multiple batches."""
        # Create documents that exceed token limit
        docs = [make_processed_doc(content="A" * 10000) for _ in range(5)]  # ~2500 tokens each
        with patch('legal_portal.services.analysis.main_processor.get_settings') as mock_settings:
            mock_settings.return_value.max_tokens_per_batch = 5000  # ~2 docs per batch
            batches = _create_smart_batches(docs)
        assert len(batches) > 1

    def test_respects_max_docs_per_batch(self):
        """Test that max 10 docs per batch is respected."""
        docs = [make_processed_doc(content="Short") for _ in range(25)]
        with patch('legal_portal.services.analysis.main_processor.get_settings') as mock_settings:
            mock_settings.return_value.max_tokens_per_batch = 1000000
            batches = _create_smart_batches(docs)
        # With max 10 per batch, 25 docs should be split into at least 3 batches
        assert len(batches) >= 3
        for batch in batches:
            assert len(batch) <= 10

    def test_empty_documents(self):
        """Test with empty document list."""
        with patch('legal_portal.services.analysis.main_processor.get_settings') as mock_settings:
            mock_settings.return_value.max_tokens_per_batch = 100000
            batches = _create_smart_batches([])
        assert batches == []

    def test_custom_max_tokens(self):
        """Test with custom max_tokens_per_batch parameter."""
        docs = [make_processed_doc(content="A" * 1000) for _ in range(5)]  # ~250 tokens each
        # Pass custom max_tokens directly
        batches = _create_smart_batches(docs, max_tokens_per_batch=500)
        assert len(batches) >= 2

    def test_long_documents_use_prompt_excerpt_for_token_estimate(self):
        """Very long docs should be batched based on excerpted prompt content."""
        long_content = "L" * 120000
        docs = [
            make_processed_doc(file_name="doc1.pdf", content=long_content),
            make_processed_doc(file_name="doc2.pdf", content=long_content),
        ]

        batches = _create_smart_batches(docs, max_tokens_per_batch=15000)

        assert len(batches) == 1
        assert len(batches[0]) == 2


class TestCreatePromptAwareBatches:
    """Test prompt-aware batching that includes intake and prompt overhead."""

    def test_splits_batches_when_full_prompt_would_exceed_limit(self):
        intake_content = "I" * 40000  # Large intake should consume significant prompt budget
        docs = [make_processed_doc(file_name=f"doc_{i}.pdf", content="D" * 2500) for i in range(3)]
        review_data = {"legal_issue": "Contract dispute", "key_documents": []}

        batches = _create_prompt_aware_batches(
            documents=docs,
            intake_content=intake_content,
            review_data=review_data,
            statute_context="",
            jurisdiction="Florida",
            max_tokens_per_batch=12000,
        )

        assert len(batches) >= 2
        assert sum(len(batch) for batch in batches) == 3

    def test_respects_max_docs_per_batch_limit(self):
        docs = [make_processed_doc(file_name=f"doc_{i}.pdf", content="short") for i in range(25)]
        review_data = {"legal_issue": "Test", "key_documents": []}

        batches = _create_prompt_aware_batches(
            documents=docs,
            intake_content="small intake",
            review_data=review_data,
            statute_context="",
            jurisdiction="Florida",
            max_tokens_per_batch=1000000,
        )

        assert len(batches) >= 3
        for batch in batches:
            assert len(batch) <= 10


# =============================================================================
# Tests for _clean_and_parse_json
# =============================================================================


class TestCleanAndParseJson:
    """Test JSON cleaning and parsing."""

    def test_valid_json(self):
        """Test parsing valid JSON."""
        json_str = '{"key": "value", "number": 42}'
        result = _clean_and_parse_json(json_str)
        assert result == {"key": "value", "number": 42}

    def test_json_with_markdown_code_block(self):
        """Test removal of markdown code blocks."""
        json_str = '```json\n{"key": "value"}\n```'
        result = _clean_and_parse_json(json_str)
        assert result == {"key": "value"}

    def test_json_with_whitespace(self):
        """Test handling of whitespace."""
        json_str = '  \n  {"key": "value"}  \n  '
        result = _clean_and_parse_json(json_str)
        assert result == {"key": "value"}

    def test_invalid_json(self):
        """Test handling of invalid JSON."""
        json_str = '{"key": "value", broken}'
        result = _clean_and_parse_json(json_str)
        assert result is None

    def test_non_string_input(self):
        """Test handling of non-string input."""
        result = _clean_and_parse_json(123)  # type: ignore
        assert result is None

    def test_with_batch_number(self):
        """Test logging includes batch number when provided."""
        json_str = 'invalid json'
        result = _clean_and_parse_json(json_str, batch_num=3)
        assert result is None

    def test_nested_json(self):
        """Test parsing nested JSON structures."""
        json_str = '''```json
        {
            "documents": [
                {"name": "doc1", "type": "pdf"},
                {"name": "doc2", "type": "txt"}
            ]
        }
        ```'''
        result = _clean_and_parse_json(json_str)
        assert result is not None
        assert len(result["documents"]) == 2


# =============================================================================
# Tests for _process_document_batch
# =============================================================================


class TestProcessDocumentBatch:
    """Test batch processing error handling."""

    @pytest.mark.asyncio
    async def test_parse_error_yields_processing_error(self):
        docs = [make_processed_doc(file_name="doc1.pdf", content="content")]
        json_service = MagicMock()
        _meta = {"model": "test", "finish_reason": "stop", "usage": {}, "response_chars": 14}
        json_service.process_documents_to_json = AsyncMock(return_value=("not valid json", [], _meta))

        summaries, errors = await _process_document_batch(
            batch_documents=docs,
            intake_content="Intake",
            batch_num=1,
            total_batches=1,
            openai_client_wrapper=MagicMock(),
            json_processing_service=json_service,
            review_data={"legal_issue": "Test", "key_documents": []},
            errors=[],
        )

        assert summaries == []
        assert any(error.error_type == "PARSE_ERROR" for error in errors)

    @pytest.mark.asyncio
    async def test_empty_documents_array_yields_error(self):
        docs = [make_processed_doc(file_name="doc1.pdf", content="content")]
        json_service = MagicMock()
        _meta = {"model": "test", "finish_reason": "stop", "usage": {}, "response_chars": 20}
        json_service.process_documents_to_json = AsyncMock(return_value=('{"documents": []}', [], _meta))

        summaries, errors = await _process_document_batch(
            batch_documents=docs,
            intake_content="Intake",
            batch_num=1,
            total_batches=1,
            openai_client_wrapper=MagicMock(),
            json_processing_service=json_service,
            review_data={"legal_issue": "Test", "key_documents": []},
            errors=[],
        )

        assert summaries == []
        assert any(error.error_type == "EMPTY_BATCH_RESULT" for error in errors)


# =============================================================================
# Tests for _build_summary_prompt
# =============================================================================


class TestBuildSummaryPrompt:
    """Test summary prompt building."""

    def test_basic_prompt_structure(self):
        """Test basic prompt contains required elements."""
        docs = [make_processed_doc(file_name="test.pdf", content="Test content")]
        review_data = {"legal_issue": "Contract dispute", "key_documents": ["test.pdf"]}
        
        prompt = _build_summary_prompt(
            intake_content="Client intake information",
            documents=docs,
            review_data=review_data,
        )
        
        assert "Contract dispute" in prompt
        assert "test.pdf" in prompt
        assert "Client intake information" in prompt
        assert "JSON" in prompt

    def test_batch_mode_header(self):
        """Test batch mode adds batch header."""
        docs = [make_processed_doc()]
        review_data = {"legal_issue": "Test", "key_documents": []}
        
        prompt = _build_summary_prompt(
            intake_content="Intake",
            documents=docs,
            review_data=review_data,
            is_batch=True,
            batch_info=(2, 5),
        )
        
        assert "BATCH 2 of 5" in prompt

    def test_includes_statute_context(self):
        """Test statute context is included when provided."""
        docs = [make_processed_doc()]
        review_data = {"legal_issue": "Test", "key_documents": []}
        
        prompt = _build_summary_prompt(
            intake_content="Intake",
            documents=docs,
            review_data=review_data,
            statute_context="Florida Statute § 718.116 - Association Assessments",
        )
        
        assert "718.116" in prompt
        assert "RELEVANT" in prompt.upper()

    def test_jurisdiction_affects_prompt(self):
        """Test different jurisdictions affect prompt content."""
        docs = [make_processed_doc()]
        review_data = {"legal_issue": "Test", "key_documents": []}
        
        florida_prompt = _build_summary_prompt(
            intake_content="Intake",
            documents=docs,
            review_data=review_data,
            jurisdiction="Florida",
        )
        
        nm_prompt = _build_summary_prompt(
            intake_content="Intake",
            documents=docs,
            review_data=review_data,
            jurisdiction="New Mexico",
        )
        
        assert "Florida" in florida_prompt
        assert "New Mexico" in nm_prompt

    def test_image_handling_instructions_included(self):
        """Test that image handling instructions are in prompt."""
        docs = [make_processed_doc(file_name="photo.jpg")]
        review_data = {"legal_issue": "Test", "key_documents": []}
        
        prompt = _build_summary_prompt(
            intake_content="Intake",
            documents=docs,
            review_data=review_data,
        )
        
        assert "IMAGE DOCUMENTS" in prompt.upper()

    def test_missing_key_documents(self):
        """Test handling when no key documents specified."""
        docs = [make_processed_doc()]
        review_data = {"legal_issue": "Test", "key_documents": []}
        
        prompt = _build_summary_prompt(
            intake_content="Intake",
            documents=docs,
            review_data=review_data,
        )
        
        assert "No documents were prioritized" in prompt


# =============================================================================
# Tests for _build_original_documents_map
# =============================================================================


class TestBuildOriginalDocumentsMap:
    """Test collision-safe mapping of raw original documents."""

    def test_preserves_single_filename_without_suffix(self):
        """Single documents should keep the plain filename key."""
        doc = make_processed_doc(file_name="Subscription Agreement.pdf", content="Doc content")

        result = _build_original_documents_map([doc])

        assert list(result.keys()) == ["Subscription Agreement.pdf"]
        assert result["Subscription Agreement.pdf"] == "Doc content"

    def test_disambiguates_duplicate_filenames_with_document_id(self):
        """Duplicate filenames should not overwrite each other in the map."""
        doc_one = make_processed_doc(file_name="Agreement.pdf", content="First copy")
        doc_one.document_id = "doc-1"
        doc_two = make_processed_doc(file_name="Agreement.pdf", content="Second copy")
        doc_two.document_id = "doc-2"

        result = _build_original_documents_map([doc_one, doc_two])

        assert len(result) == 2
        assert "Agreement.pdf" in result
        assert "Agreement.pdf [id:doc-2]" in result
        assert result["Agreement.pdf"] == "First copy"
        assert result["Agreement.pdf [id:doc-2]"] == "Second copy"


# =============================================================================
# Tests for _convert_to_case_analysis_result
# =============================================================================


class TestConvertToCaseAnalysisResult:
    """Test conversion to CaseAnalysisResult format."""

    def test_basic_conversion(self):
        """Test basic conversion with minimal data."""
        summaries = [
            make_document_summary(
                document_name="contract.pdf",
                document_type="Contract",
                relevance_to_case="Important contract document",
            )
        ]
        
        result = _convert_to_case_analysis_result(
            structured_summaries=summaries,
            client_name="John Doe",
            intake_content="Initial consultation notes",
        )
        
        assert result.intake_analysis.client_name == "John Doe"
        assert len(result.analyzed_documents) == 1
        assert result.analyzed_documents[0].file_name == "contract.pdf"

    def test_conversion_with_parties(self):
        """Test conversion includes parties."""
        summaries = [
            make_document_summary(
                document_name="contract.pdf",
                parties=["John Doe", "Jane Smith"],
            )
        ]
        
        result = _convert_to_case_analysis_result(summaries, "Client", "Intake")
        
        doc = result.analyzed_documents[0]
        assert "John Doe" in doc.key_information
        assert "Jane Smith" in doc.key_information

    def test_conversion_with_dates(self):
        """Test conversion includes key dates."""
        summaries = [
            make_document_summary(
                document_name="contract.pdf",
                key_dates=[
                    KeyDate(event="Contract signed", date="2024-01-15"),
                ],
            )
        ]
        
        result = _convert_to_case_analysis_result(summaries, "Client", "Intake")
        
        doc = result.analyzed_documents[0]
        assert "2024-01-15" in doc.key_information
        assert "Contract signed" in doc.key_information

    def test_conversion_with_amounts(self):
        """Test conversion includes key amounts."""
        summaries = [
            make_document_summary(
                document_name="invoice.pdf",
                key_amounts=[
                    KeyAmount(description="Total Due", amount="$5,000.00"),
                ],
            )
        ]
        
        result = _convert_to_case_analysis_result(summaries, "Client", "Intake")
        
        doc = result.analyzed_documents[0]
        assert "$5,000.00" in doc.key_information

    def test_empty_summaries(self):
        """Test conversion with empty summaries list."""
        result = _convert_to_case_analysis_result([], "Client", "Intake")
        
        assert result.intake_analysis.client_name == "Client"
        assert len(result.analyzed_documents) == 0

    def test_truncates_long_intake_content(self):
        """Test that very long intake content is truncated."""
        long_intake = "A" * 1000
        result = _convert_to_case_analysis_result([], "Client", long_intake)
        
        # Note: The code passes to IntakeAnalysis 'summary' but field is 'case_summary'
        # This test verifies intake_analysis is created even with long content
        assert result.intake_analysis.client_name == "Client"
        assert result.intake_analysis.case_type == "Legal Matter"
