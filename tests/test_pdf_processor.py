"""Tests for PDF processor with reliability enhancements."""

import os
from pathlib import Path

import pytest
from legal_portal.core.data_models import DocumentType
from legal_portal.services.file_processors.pdf_processor import (
    detect_pdf_corruption,
    process_pdf,
)


@pytest.mark.asyncio
async def test_pdf_size_validation():
    """Test that small PDFs are rejected."""
    # Create tiny file
    tiny_pdf = Path("/tmp/tiny.pdf")
    tiny_pdf.write_bytes(b"XX")  # 2 bytes

    result = await process_pdf(str(tiny_pdf), DocumentType.CASE_DOCUMENT, "tiny.pdf")

    assert "too small" in result.content.lower()
    tiny_pdf.unlink()


@pytest.mark.asyncio
async def test_pdf_corruption_detection():
    """Test PDF corruption detection."""
    valid, reason = detect_pdf_corruption("nonexistent.pdf")
    assert not valid
    assert "not found" in reason.lower()

    # Test tiny file
    tiny_pdf = Path("/tmp/tiny2.pdf")
    tiny_pdf.write_bytes(b"X")
    valid, reason = detect_pdf_corruption(str(tiny_pdf))
    assert not valid
    assert "too small" in reason.lower()
    tiny_pdf.unlink()


@pytest.mark.asyncio
async def test_pdf_retry_logic():
    """Test retry logic works for valid PDF."""
    # Create valid small PDF (using PyMuPDF)
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Test content")
    test_pdf = "/tmp/test_retry.pdf"
    doc.save(test_pdf)
    doc.close()

    # Should succeed even with retry
    result = await process_pdf(test_pdf, DocumentType.CASE_DOCUMENT, "test.pdf")
    assert "Test content" in result.content

    os.remove(test_pdf)


@pytest.mark.asyncio
async def test_pdf_invalid_header():
    """Test that files with invalid PDF headers are rejected."""
    # Create file with wrong header (must be > 100 bytes to pass size check)
    bad_pdf = Path("/tmp/bad_header.pdf")
    bad_pdf.write_bytes(b"Not a PDF file content here" + b"X" * 100)

    valid, reason = detect_pdf_corruption(str(bad_pdf))
    assert not valid
    assert "header" in reason.lower()

    bad_pdf.unlink()


@pytest.mark.asyncio
async def test_pdf_missing_file():
    """Test handling of missing PDF files."""
    result = await process_pdf("/tmp/nonexistent_file.pdf", DocumentType.CASE_DOCUMENT, "missing.pdf")

    assert "not found" in result.content.lower()
    assert result.metadata.file_size == 0


@pytest.mark.asyncio
async def test_pdf_extraction_success():
    """Test successful PDF text extraction."""
    import fitz

    # Create a valid PDF with multiple pages
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((50, 50), "Page 1 content")
    page2 = doc.new_page()
    page2.insert_text((50, 50), "Page 2 content")

    test_pdf = "/tmp/test_multipage.pdf"
    doc.save(test_pdf)
    doc.close()

    result = await process_pdf(test_pdf, DocumentType.CASE_DOCUMENT, "multipage.pdf")

    assert "Page 1 content" in result.content
    assert "Page 2 content" in result.content
    assert not result.content.startswith("Error")
    assert result.metadata.file_size > 0

    os.remove(test_pdf)


@pytest.mark.asyncio
async def test_pdf_empty_pages():
    """Test handling of PDF with no pages (actually a page with no content)."""
    import fitz

    # Create PDF with one empty page
    doc = fitz.open()
    doc.new_page()  # Add an empty page
    test_pdf = "/tmp/test_empty.pdf"
    doc.save(test_pdf)
    doc.close()

    # Should be valid PDF but with empty content
    valid, reason = detect_pdf_corruption(test_pdf)
    assert valid  # Valid PDF structure

    # Process it - should extract empty/minimal text
    result = await process_pdf(test_pdf, DocumentType.CASE_DOCUMENT, "empty.pdf")
    assert not result.content.startswith("Error")
    assert len(result.content.strip()) == 0  # Empty content

    os.remove(test_pdf)
