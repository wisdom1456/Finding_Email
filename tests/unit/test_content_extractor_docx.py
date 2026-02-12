"""Tests for DOCX extraction fallback behavior in content_extractor."""

from io import BytesIO
from unittest.mock import patch
import zipfile

from legal_portal.api.utils.content_extractor import DocumentProcessor as ContentExtractor


def _build_minimal_docx(text: str) -> bytes:
    """Build a minimal DOCX-like ZIP payload with WordprocessingML text."""
    xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml.encode("utf-8"))
    return payload.getvalue()


def test_extract_text_from_docx_with_method_falls_back_without_python_docx():
    """When python-docx is unavailable, DOCX extraction should still work via XML fallback."""
    docx_bytes = _build_minimal_docx("Fallback extraction works")

    with patch("legal_portal.api.utils.content_extractor.DOCX_AVAILABLE", False):
        extracted_text, extraction_method = ContentExtractor.extract_text_from_docx_with_method(docx_bytes)

    assert extraction_method == "docx_xml_fallback"
    assert "Fallback extraction works" in extracted_text


def test_extract_text_docx_does_not_return_none_without_python_docx():
    """extract_text() should return fallback text for DOCX instead of None."""
    docx_bytes = _build_minimal_docx("DOCX content via fallback")

    with patch("legal_portal.api.utils.content_extractor.DOCX_AVAILABLE", False):
        extracted_text = ContentExtractor.extract_text(
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "sample.docx",
        )

    assert extracted_text is not None
    assert "DOCX content via fallback" in extracted_text
