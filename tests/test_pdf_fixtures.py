"""Regression tests for PDF processing edge cases.

These tests verify that the PDF processor correctly handles:
1. "Fake PDFs" - plain text files saved with .pdf extension (common from Clio exports)
2. Real PDFs - valid PDF documents that should be extracted normally

The fixtures in tests/data/problem_files/ represent real-world edge cases
that have caused production issues.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from legal_portal.core.data_models import DocumentType
from legal_portal.services.file_processors.pdf_processor import process_pdf

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "data" / "problem_files"


@pytest.fixture
def fake_pdf_path() -> str:
    """Path to a 'fake PDF' - actually plain text with .pdf extension.

    This file intentionally does NOT have a valid PDF header (%PDF-).
    It contains legal description text that was saved as .pdf.
    """
    path = FIXTURES_DIR / "Survey_Legal_Lot_Description.pdf"
    assert path.exists(), f"Test fixture not found: {path}"
    return str(path)


@pytest.fixture
def real_pdf_path() -> str:
    """Path to a real, valid PDF document.

    This is a sanitized/minimized PDF containing generic "INTAKE PACKET" content.
    No PII is included.
    """
    path = FIXTURES_DIR / "Intake_sample_sanitized.pdf"
    assert path.exists(), f"Test fixture not found: {path}"
    return str(path)


class TestFakePdfHandling:
    """Tests for handling plain text files with .pdf extension."""

    @pytest.mark.asyncio
    async def test_fake_pdf_extracts_text_successfully(self, fake_pdf_path: str):
        """Fake PDFs should be detected as text and extracted via text_fallback."""
        result = await process_pdf(
            file_path=fake_pdf_path,
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="Survey_Legal_Lot_Description.pdf",
        )

        # Should not be an error
        assert not result.content.startswith("Error:"), f"Unexpected error: {result.content}"

        # Should contain expected content
        assert "LEGAL DESCRIPTION. LOT A-2" in result.content
        assert "SANTA FE COUNTY" in result.content

        # Should use text_fallback extraction method
        assert (
            result.extraction_method == "text_fallback"
        ), f"Expected 'text_fallback' extraction method, got: {result.extraction_method}"

    @pytest.mark.asyncio
    async def test_fake_pdf_does_not_call_vision_ocr(self, fake_pdf_path: str):
        """Text content should be returned directly without calling Vision APIs."""
        result = await process_pdf(
            file_path=fake_pdf_path,
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="Survey_Legal_Lot_Description.pdf",
        )

        # Extraction method should be text_fallback, not Google Vision or GPT-4o
        assert result.extraction_method == "text_fallback"
        assert result.extraction_method not in ["Google Cloud Vision", "GPT-4o Vision"]


class TestRealPdfHandling:
    """Tests for handling valid PDF documents."""

    @pytest.mark.asyncio
    async def test_real_pdf_extracts_text_successfully(self, real_pdf_path: str):
        """Real PDFs should be extracted using standard PDF libraries."""
        result = await process_pdf(
            file_path=real_pdf_path,
            document_type=DocumentType.INTAKE_FORM,
            original_filename="Intake_sample_sanitized.pdf",
        )

        # Should not be an error
        assert not result.content.startswith("Error:"), f"Unexpected error: {result.content}"

        # Should contain expected content
        assert "INTAKE PACKET" in result.content

        # Should NOT use text_fallback (should use PyMuPDF or pypdf)
        assert (
            result.extraction_method != "text_fallback"
        ), f"Real PDF should not use text_fallback, got: {result.extraction_method}"

    @pytest.mark.asyncio
    async def test_real_pdf_uses_standard_extraction(self, real_pdf_path: str):
        """Real PDFs should use PyMuPDF or pypdf, not Vision fallback."""
        result = await process_pdf(
            file_path=real_pdf_path,
            document_type=DocumentType.INTAKE_FORM,
            original_filename="Intake_sample_sanitized.pdf",
        )

        # Should use standard PDF extraction (PyMuPDF or pypdf)
        assert result.extraction_method in [
            "PyMuPDF",
            "pypdf",
        ], f"Expected standard PDF extraction, got: {result.extraction_method}"


class TestTextDetectionHeuristic:
    """Tests for the _is_likely_plain_text heuristic function."""

    def test_plain_text_detected(self):
        """Plain text content should be detected as text."""
        from legal_portal.services.file_processors.pdf_processor import _is_likely_plain_text

        text_content = b"This is plain text content.\nIt has multiple lines.\nAnd spaces."
        is_text, decoded = _is_likely_plain_text(text_content)

        assert is_text is True
        assert "plain text content" in decoded

    def test_pdf_header_not_detected_as_text(self):
        """PDF binary content should not be detected as plain text."""
        from legal_portal.services.file_processors.pdf_processor import _is_likely_plain_text

        # Simulated PDF-like binary content with null bytes
        pdf_like_content = b"%PDF-1.7\x00\x00\x00binary\x00content\x00here"
        is_text, decoded = _is_likely_plain_text(pdf_like_content)

        # Should not be classified as text due to null bytes
        assert is_text is False

    def test_empty_content_not_detected_as_text(self):
        """Empty or very short content should not be detected as text."""
        from legal_portal.services.file_processors.pdf_processor import _is_likely_plain_text

        is_text, _ = _is_likely_plain_text(b"")
        assert is_text is False

        is_text, _ = _is_likely_plain_text(b"short")
        assert is_text is False

    def test_leading_whitespace_text_detected(self):
        """Text with leading whitespace/newlines should still be detected as text."""
        from legal_portal.services.file_processors.pdf_processor import _is_likely_plain_text

        content = b"\n\n\n   \n\t\nLEGAL DESCRIPTION LOT A-2\nSANTA FE COUNTY"
        is_text, decoded = _is_likely_plain_text(content)

        assert is_text is True
        assert "LEGAL DESCRIPTION" in decoded
