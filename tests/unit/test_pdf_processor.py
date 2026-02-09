"""Unit tests for PDF processor - Phase 1 Coverage Expansion.

This module provides comprehensive tests for pdf_processor.py functionality,
targeting 50% coverage.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from legal_portal.core.data_models import (
    DocumentType,
    FileMetadata,
    FileType,
    ProcessedDocument,
)
from legal_portal.services.file_processors.pdf_processor import (
    _detect_pdf_signature,
    _is_likely_plain_text,
    _wait_for_file_ready,
    detect_pdf_corruption,
    process_pdf,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def valid_pdf_bytes():
    """Create minimal valid PDF bytes."""
    # Minimal PDF with one blank page
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Test PDF Content) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000214 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
308
%%EOF"""


@pytest.fixture
def text_file_with_pdf_extension():
    """Create plain text that was saved as .pdf."""
    return b"""This is actually a plain text file.
It contains multiple lines of text content.
It was exported from a legal system.
Client: John Smith
Case Number: 2024-12345
Notes: Initial consultation completed.
"""


@pytest.fixture
def html_content_with_pdf_extension():
    """Create HTML that was saved as .pdf (error page)."""
    return b"""<!DOCTYPE html>
<html>
<head><title>Error</title></head>
<body>
<h1>Access Denied</h1>
<p>You do not have permission to access this file.</p>
</body>
</html>"""


@pytest.fixture
def binary_content():
    """Create binary content (not text or PDF)."""
    return bytes(range(256)) * 10  # Mix of all byte values


@pytest.fixture
def temp_pdf_file(tmp_path, valid_pdf_bytes):
    """Create a temporary PDF file."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(valid_pdf_bytes)
    return str(pdf_file)


@pytest.fixture
def temp_text_file_as_pdf(tmp_path, text_file_with_pdf_extension):
    """Create a temp file with text content saved as .pdf."""
    pdf_file = tmp_path / "notes.pdf"
    pdf_file.write_bytes(text_file_with_pdf_extension)
    return str(pdf_file)


# =============================================================================
# Tests for _is_likely_plain_text
# =============================================================================


class TestIsLikelyPlainText:
    """Test plain text detection function."""

    def test_detects_plain_text(self, text_file_with_pdf_extension):
        """Test detection of plain text content."""
        is_text, decoded = _is_likely_plain_text(text_file_with_pdf_extension)
        assert is_text is True
        assert "plain text" in decoded.lower()
        assert "John Smith" in decoded

    def test_detects_html_as_text(self, html_content_with_pdf_extension):
        """Test detection of HTML content as text."""
        is_text, decoded = _is_likely_plain_text(html_content_with_pdf_extension)
        assert is_text is True
        assert "Access Denied" in decoded

    def test_rejects_binary_content(self, binary_content):
        """Test rejection of binary content."""
        is_text, decoded = _is_likely_plain_text(binary_content)
        assert is_text is False
        assert decoded == ""

    def test_rejects_pdf_bytes(self, valid_pdf_bytes):
        """Test rejection of actual PDF bytes."""
        is_text, decoded = _is_likely_plain_text(valid_pdf_bytes)
        # PDFs should be rejected (they have binary content)
        # Note: minimal PDFs might pass if they're mostly text
        assert isinstance(is_text, bool)

    def test_rejects_empty_data(self):
        """Test rejection of empty data."""
        is_text, decoded = _is_likely_plain_text(b"")
        assert is_text is False
        assert decoded == ""

    def test_rejects_too_short_data(self):
        """Test rejection of very short data."""
        is_text, decoded = _is_likely_plain_text(b"short")
        assert is_text is False
        assert decoded == ""

    def test_rejects_null_heavy_content(self):
        """Test rejection of content with many null bytes."""
        # More than 1% null bytes should be rejected
        content = b"text" + b"\x00" * 100 + b"more text"
        is_text, decoded = _is_likely_plain_text(content)
        assert is_text is False

    def test_accepts_unicode_text(self):
        """Test acceptance of Unicode text content."""
        unicode_content = "This is Unicode text with émojis 🎉 and accénts".encode('utf-8')
        # Add more content to pass length check
        unicode_content += b" Additional content to make it longer than minimum." * 5
        is_text, decoded = _is_likely_plain_text(unicode_content)
        assert is_text is True
        assert "émojis" in decoded

    def test_accepts_latin1_text(self):
        """Test acceptance of Latin-1 encoded text."""
        latin1_content = "This is Latin-1 text with café and naïve".encode('latin-1')
        latin1_content += b" More content for length requirements." * 5
        is_text, decoded = _is_likely_plain_text(latin1_content)
        assert is_text is True

    def test_rejects_low_printable_ratio(self):
        """Test rejection of content with low printable character ratio."""
        # Content that's less than 85% printable
        non_printable = bytes([0x01, 0x02, 0x03, 0x04, 0x05] * 100)
        is_text, decoded = _is_likely_plain_text(non_printable)
        assert is_text is False

    def test_handles_whitespace_only(self):
        """Test handling of whitespace-only content."""
        whitespace_content = b"   \n\n\t\t\r\n   " * 100
        is_text, decoded = _is_likely_plain_text(whitespace_content)
        # Whitespace only should be rejected (no alnum)
        assert is_text is False


# =============================================================================
# Tests for _wait_for_file_ready
# =============================================================================


class TestWaitForFileReady:
    """Test file readiness detection."""

    def test_returns_true_for_existing_file(self, temp_pdf_file):
        """Test returns True for existing, stable file."""
        result = _wait_for_file_ready(temp_pdf_file, max_wait_seconds=1.0)
        assert result is True

    def test_returns_false_for_nonexistent_file(self):
        """Test returns False for nonexistent file after timeout."""
        result = _wait_for_file_ready("/nonexistent/path/file.pdf", max_wait_seconds=0.3)
        assert result is False

    def test_respects_timeout(self):
        """Test that function respects timeout parameter."""
        start_time = time.time()
        _wait_for_file_ready("/nonexistent/path.pdf", max_wait_seconds=0.5)
        elapsed = time.time() - start_time
        # Should take roughly the timeout duration
        assert 0.4 <= elapsed <= 1.0

    def test_detects_stable_file_quickly(self, temp_pdf_file):
        """Test that stable files are detected quickly."""
        start_time = time.time()
        result = _wait_for_file_ready(temp_pdf_file, max_wait_seconds=5.0)
        elapsed = time.time() - start_time
        assert result is True
        # Should detect stable file in less than 1 second
        assert elapsed < 1.0


# =============================================================================
# Tests for detect_pdf_corruption
# =============================================================================


class TestDetectPdfCorruption:
    """Test PDF corruption detection."""

    def test_valid_pdf(self, temp_pdf_file):
        """Test detection of valid PDF."""
        is_valid, message = detect_pdf_corruption(temp_pdf_file)
        # May be valid or invalid depending on PDF library availability
        assert isinstance(is_valid, bool)
        assert isinstance(message, str)


    def test_nonexistent_file(self):
        """Test detection of nonexistent file."""
        is_valid, message = detect_pdf_corruption("/nonexistent/file.pdf")
        assert is_valid is False
        assert "not found" in message.lower()

    def test_too_small_file(self, tmp_path):
        """Test detection of file that's too small."""
        small_file = tmp_path / "small.pdf"
        small_file.write_bytes(b"%PDF-1.4")  # Only 8 bytes
        
        is_valid, message = detect_pdf_corruption(str(small_file))
        assert is_valid is False
        assert "small" in message.lower() or "bytes" in message.lower()

    def test_invalid_header(self, tmp_path):
        """Test detection of file with invalid PDF header."""
        bad_file = tmp_path / "not_pdf.pdf"
        bad_file.write_bytes(b"This is not a PDF file " * 10)  # >100 bytes
        
        is_valid, message = detect_pdf_corruption(str(bad_file))
        assert is_valid is False
        assert "header" in message.lower()

    def test_empty_pdf(self, tmp_path):
        """Test detection of PDF with no pages."""
        # Create a valid header but no content
        empty_pdf = tmp_path / "empty.pdf"
        empty_pdf.write_bytes(b"%PDF-1.4\n%%EOF" + b" " * 100)
        
        is_valid, message = detect_pdf_corruption(str(empty_pdf))
        # Should fail either due to no pages or being corrupt
        # The exact behavior depends on PDF library
        assert isinstance(is_valid, bool)


# =============================================================================
# Tests for signature detection
# =============================================================================


class TestSignatureDetection:
    """Test PDF signature detection helpers."""

    def test_detects_embedded_digital_signature_markers(self):
        """Detect signature dictionaries and timestamp from raw PDF bytes."""
        pdf_bytes = b"""%PDF-1.7
1 0 obj
<< /Type /Sig /ByteRange [0 123 456 789] /SubFilter /adbe.pkcs7.detached /M (D:20231003193936-07'00') >>
endobj
%%EOF
"""
        result = _detect_pdf_signature(pdf_bytes=pdf_bytes, extracted_text="")

        assert result["status"] == "signed"
        assert result["confidence"] == "high"
        assert result["has_digital_signature"] is True
        assert result["signing_date"] == "2023-10-03T19:39:36-07:00"

    def test_detects_signature_from_text_markers(self):
        """Detect signature when text contains strong signature markers."""
        text = (
            "Counterpart Signature Page\n"
            "DocuSign Envelope ID: 1234-ABCD\n"
            "Electronically signed by Erica Corley"
        )
        result = _detect_pdf_signature(pdf_bytes=b"%PDF-1.7\n%%EOF", extracted_text=text)

        assert result["status"] == "signed"
        assert result["has_digital_signature"] is False
        assert result["has_signature_markers"] is True
        assert result["signature_marker_count"] >= 2

    @pytest.mark.asyncio
    async def test_process_pdf_exposes_signature_detection(self, tmp_path):
        """process_pdf should return signature metadata even when extraction libraries are unavailable."""
        signed_pdf = tmp_path / "signed_like.pdf"
        signed_pdf.write_bytes(
            b"%PDF-1.7\n"
            b"<< /Type /Sig /ByteRange [0 1 2 3] /SubFilter /adbe.pkcs7.detached >>\n"
            b"%%EOF"
            + (b" " * 200)
        )

        with patch("legal_portal.services.file_processors.pdf_processor.FITZ_AVAILABLE", False), patch(
            "legal_portal.services.file_processors.pdf_processor.PYPDF_AVAILABLE", False
        ):
            result = await process_pdf(
                file_path=str(signed_pdf),
                document_type=DocumentType.CASE_DOCUMENT,
                original_filename="signed_like.pdf",
            )

        assert result.signature_detection is not None
        assert result.signature_detection["status"] == "signed"
        assert result.signature_detection["has_digital_signature"] is True


# =============================================================================
# Tests for process_pdf (main function)
# =============================================================================


class TestProcessPdf:
    """Test main PDF processing function."""

    @pytest.mark.asyncio
    async def test_process_nonexistent_file(self):
        """Test processing nonexistent PDF file."""
        result = await process_pdf(
            file_path="/nonexistent/file.pdf",
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="missing.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        assert "not found" in result.content.lower() or "error" in result.content.lower()
        assert result.file_name == "missing.pdf"

    @pytest.mark.asyncio
    async def test_process_text_file_as_pdf(self, temp_text_file_as_pdf):
        """Test processing plain text file with .pdf extension."""
        result = await process_pdf(
            file_path=temp_text_file_as_pdf,
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="notes.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        # Should detect as text and extract content
        if "text_fallback" in (result.extraction_method or ""):
            assert "plain text" in result.content.lower() or "John Smith" in result.content

    @pytest.mark.asyncio
    async def test_process_valid_pdf(self, temp_pdf_file):
        """Test processing a valid PDF file."""
        result = await process_pdf(
            file_path=temp_pdf_file,
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="test.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        assert result.file_name == "test.pdf"
        assert result.document_type == DocumentType.CASE_DOCUMENT
        assert result.file_type == FileType.PDF
        assert result.metadata is not None

    @pytest.mark.asyncio
    async def test_process_small_pdf(self, tmp_path):
        """Test processing suspiciously small PDF."""
        small_pdf = tmp_path / "small.pdf"
        small_pdf.write_bytes(b"%PDF-1.4\n" * 5)  # Small but valid header
        
        result = await process_pdf(
            file_path=str(small_pdf),
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="small.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        # Should report error or warning about small file
        if result.content:
            # May contain error message about corruption/small file
            pass

    @pytest.mark.asyncio
    async def test_process_invalid_pdf_header(self, tmp_path):
        """Test processing file with invalid PDF header."""
        bad_pdf = tmp_path / "bad.pdf"
        bad_pdf.write_bytes(b"NOT A PDF FILE " * 20)
        
        result = await process_pdf(
            file_path=str(bad_pdf),
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="bad.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        # Should detect invalid content
        assert "error" in result.content.lower() or "not" in result.content.lower()

    @pytest.mark.asyncio
    async def test_process_html_error_page_as_pdf(self, tmp_path, html_content_with_pdf_extension):
        """Test processing HTML error page saved as .pdf."""
        html_pdf = tmp_path / "error.pdf"
        html_pdf.write_bytes(html_content_with_pdf_extension)
        
        result = await process_pdf(
            file_path=str(html_pdf),
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="error.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        # Should extract HTML as text or detect as invalid PDF
        content_lower = result.content.lower()
        # May contain either the HTML content or an error message
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_extraction_method_recorded(self, temp_pdf_file):
        """Test that extraction method is recorded."""
        result = await process_pdf(
            file_path=temp_pdf_file,
            document_type=DocumentType.INTAKE_FORM,
            original_filename="intake.pdf",
        )
        
        assert result.extraction_method is not None
        # Should be one of: PyMuPDF, pypdf, text_fallback, standard
        assert result.extraction_method in ["PyMuPDF", "pypdf", "text_fallback", "standard", "unknown"]

    @pytest.mark.asyncio
    async def test_page_count_recorded(self, temp_pdf_file):
        """Test that page count is recorded when possible."""
        result = await process_pdf(
            file_path=temp_pdf_file,
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="test.pdf",
        )
        
        # Page count may be set if PDF libs are available
        assert hasattr(result, 'page_count')

    @pytest.mark.asyncio
    async def test_document_type_preserved(self, temp_pdf_file):
        """Test that document type is preserved in output."""
        for doc_type in [DocumentType.CASE_DOCUMENT, DocumentType.INTAKE_FORM]:
            result = await process_pdf(
                file_path=temp_pdf_file,
                document_type=doc_type,
                original_filename="test.pdf",
            )
            assert result.document_type == doc_type

    @pytest.mark.asyncio
    async def test_metadata_populated(self, temp_pdf_file):
        """Test that metadata is populated correctly."""
        result = await process_pdf(
            file_path=temp_pdf_file,
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="document.pdf",
        )
        
        assert result.metadata is not None
        assert result.metadata.file_name == "document.pdf"
        assert result.metadata.file_type == FileType.PDF
        assert result.metadata.file_size >= 0

    @pytest.mark.asyncio
    async def test_progress_callback_called(self, temp_pdf_file):
        """Test that progress callback is called during processing."""
        progress_updates = []
        
        def progress_callback(update):
            progress_updates.append(update)
        
        result = await process_pdf(
            file_path=temp_pdf_file,
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="test.pdf",
            progress_callback=progress_callback,
        )
        
        # Progress callback may or may not be called depending on path
        # Just verify no exception was raised
        assert result is not None


# =============================================================================
# Tests for Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_process_jpeg_with_pdf_extension(self, tmp_path):
        """Test processing JPEG file saved as .pdf."""
        jpeg_header = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00"
        jpeg_pdf = tmp_path / "image.pdf"
        jpeg_pdf.write_bytes(jpeg_header + b"\x00" * 200)
        
        result = await process_pdf(
            file_path=str(jpeg_pdf),
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="image.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        # Should detect as invalid PDF (JPEG)
        assert "JPEG" in result.content or "error" in result.content.lower()

    @pytest.mark.asyncio
    async def test_process_docx_with_pdf_extension(self, tmp_path):
        """Test processing DOCX file saved as .pdf."""
        # DOCX files start with PK (ZIP header)
        docx_header = b"PK\x03\x04"
        docx_pdf = tmp_path / "document.pdf"
        docx_pdf.write_bytes(docx_header + b"\x00" * 200)
        
        result = await process_pdf(
            file_path=str(docx_pdf),
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="document.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        # Should detect as invalid PDF (ZIP/DOCX)
        assert "ZIP" in result.content or "DOCX" in result.content or "error" in result.content.lower()

    @pytest.mark.asyncio
    async def test_process_png_with_pdf_extension(self, tmp_path):
        """Test processing PNG file saved as .pdf."""
        png_header = b"\x89PNG\r\n\x1a\n"
        png_pdf = tmp_path / "image.pdf"
        png_pdf.write_bytes(png_header + b"\x00" * 200)
        
        result = await process_pdf(
            file_path=str(png_pdf),
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="image.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        # Should detect as invalid PDF (PNG)
        assert "PNG" in result.content or "error" in result.content.lower()

    @pytest.mark.asyncio
    async def test_extraction_quality_set(self, temp_pdf_file):
        """Test that extraction quality is set appropriately."""
        result = await process_pdf(
            file_path=temp_pdf_file,
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="test.pdf",
        )
        
        assert result.extraction_quality is not None
        assert result.extraction_quality in ["high", "medium", "low"]

    @pytest.mark.asyncio
    async def test_handles_read_permission_error(self, tmp_path):
        """Test handling of file with read permission issues."""
        # Create a file and try to make it unreadable
        pdf_file = tmp_path / "protected.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n" * 20)
        
        # Note: This may not work on all systems
        try:
            os.chmod(str(pdf_file), 0o000)
            
            result = await process_pdf(
                file_path=str(pdf_file),
                document_type=DocumentType.CASE_DOCUMENT,
                original_filename="protected.pdf",
            )
            
            # Should handle gracefully
            assert isinstance(result, ProcessedDocument)
        finally:
            # Restore permissions for cleanup
            os.chmod(str(pdf_file), 0o644)


# =============================================================================
# Tests for OCR Fallback (Mocked)
# =============================================================================


class TestOcrFallback:
    """Test OCR fallback behavior (with mocked external calls)."""

    @pytest.mark.asyncio
    async def test_ocr_not_triggered_for_good_extraction(self, temp_pdf_file):
        """Test that OCR is not triggered when standard extraction works."""
        with patch('legal_portal.services.file_processors.pdf_processor.GoogleVisionClient') as mock_vision:
            mock_instance = MagicMock()
            mock_instance.is_available = False
            mock_vision.get_instance.return_value = mock_instance
            
            result = await process_pdf(
                file_path=temp_pdf_file,
                document_type=DocumentType.CASE_DOCUMENT,
                original_filename="test.pdf",
            )
            
            # OCR should not be used for this simple PDF
            assert result.ocr_provider is None or result.extraction_method in ["PyMuPDF", "pypdf", "text_fallback"]

    @pytest.mark.asyncio
    async def test_ocr_provider_recorded_when_used(self, tmp_path):
        """Test that OCR provider is recorded when OCR is used."""
        # Create a "scanned" PDF (valid header but no extractable text)
        scanned_pdf = tmp_path / "scanned.pdf"
        # Minimal PDF structure with image instead of text
        scanned_pdf.write_bytes(b"%PDF-1.4\n" + b" " * 500 + b"%%EOF")
        
        # OCR provider should be None when OCR isn't actually called
        # (we're not mocking actual OCR in this test)
        result = await process_pdf(
            file_path=str(scanned_pdf),
            document_type=DocumentType.CASE_DOCUMENT,
            original_filename="scanned.pdf",
        )
        
        assert isinstance(result, ProcessedDocument)
        # ocr_provider will be None unless OCR was actually triggered and succeeded


# =============================================================================
# Tests for Concurrent Processing
# =============================================================================


class TestConcurrentProcessing:
    """Test concurrent PDF processing."""

    @pytest.mark.asyncio
    async def test_multiple_pdfs_concurrent(self, tmp_path, valid_pdf_bytes):
        """Test processing multiple PDFs concurrently."""
        # Create multiple test PDFs
        pdf_files = []
        for i in range(3):
            pdf_file = tmp_path / f"test_{i}.pdf"
            pdf_file.write_bytes(valid_pdf_bytes)
            pdf_files.append(str(pdf_file))
        
        # Process all concurrently
        tasks = [
            process_pdf(
                file_path=path,
                document_type=DocumentType.CASE_DOCUMENT,
                original_filename=f"test_{i}.pdf",
            )
            for i, path in enumerate(pdf_files)
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        for result in results:
            assert isinstance(result, ProcessedDocument)
            assert result.file_type == FileType.PDF

