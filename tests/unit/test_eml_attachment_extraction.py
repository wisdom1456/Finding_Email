"""Tests for EML PDF attachment extraction."""

import hashlib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from legal_portal.core.data_models import DocumentType


def _build_eml_with_pdf(
    subject="Test Email",
    body="Hello, this is the email body with enough text to be meaningful for analysis.",
    pdf_filename="attachment.pdf",
    pdf_bytes=b"%PDF-1.4 fake pdf content for testing attachment extraction",
) -> bytes:
    """Build a multipart EML with a text body and one PDF attachment."""
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"

    msg.attach(MIMEText(body, "plain"))

    pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_part.add_header(
        "Content-Disposition", "attachment", filename=pdf_filename,
    )
    msg.attach(pdf_part)

    return msg.as_bytes()


def _build_eml_with_image(
    subject="Test Email",
    body="Hello, this is the email body.",
    image_filename="logo.png",
    image_bytes=b"\x89PNG\r\n\x1a\n fake image bytes",
) -> bytes:
    """Build a multipart EML with a text body and one image attachment."""
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"

    msg.attach(MIMEText(body, "plain"))

    img_part = MIMEApplication(image_bytes, _subtype="png")
    img_part.add_header(
        "Content-Disposition", "attachment", filename=image_filename,
    )
    msg.attach(img_part)

    return msg.as_bytes()


class TestEmlAttachmentExtraction:
    """Test that process_eml extracts PDF attachments into metadata."""

    @pytest.mark.asyncio
    async def test_pdf_attachment_extracted(self, tmp_path):
        from legal_portal.services.file_processors.eml_processor import process_eml

        pdf_bytes = b"%PDF-1.4 fake pdf content for testing"
        eml_bytes = _build_eml_with_pdf(pdf_bytes=pdf_bytes)
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_bytes)

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "test.eml",
        )

        # Attachments should be in metadata
        attachments = result.metadata.attachments or []
        assert len(attachments) == 1
        att = attachments[0]
        assert att["filename"] == "attachment.pdf"
        assert att["content_type"] == "application/pdf"
        assert att["content_hash"] == hashlib.sha256(pdf_bytes).hexdigest()
        assert att["bytes"] == pdf_bytes

    @pytest.mark.asyncio
    async def test_image_attachment_hash_only(self, tmp_path):
        """Image attachments should be recorded in attachment_hashes but NOT in attachments."""
        from legal_portal.services.file_processors.eml_processor import process_eml

        image_bytes = b"\x89PNG\r\n\x1a\n fake image bytes"
        eml_bytes = _build_eml_with_image(image_bytes=image_bytes)
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_bytes)

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "test.eml",
        )

        attachments = result.metadata.attachments or []
        assert len(attachments) == 0  # No PDF attachments

        attachment_hashes = result.metadata.attachment_hashes or []
        expected_hash = hashlib.sha256(image_bytes).hexdigest()
        assert expected_hash in attachment_hashes

    @pytest.mark.asyncio
    async def test_body_hash_computed(self, tmp_path):
        """body_hash should be SHA-256 of the plain text body."""
        from legal_portal.services.file_processors.eml_processor import process_eml

        body = "This is the email body text."
        eml_bytes = _build_eml_with_pdf(body=body)
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_bytes)

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "test.eml",
        )

        expected_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert result.metadata.body_hash == expected_hash

    @pytest.mark.asyncio
    async def test_no_attachments_eml(self, tmp_path):
        """EML with no attachments should have empty attachment lists."""
        from legal_portal.services.file_processors.eml_processor import process_eml

        msg = MIMEText("Plain text email body with enough content for testing.", "plain")
        msg["Subject"] = "Simple Email"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"

        eml_file = tmp_path / "simple.eml"
        eml_file.write_bytes(msg.as_bytes())

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "simple.eml",
        )

        assert (result.metadata.attachments or []) == []
        assert (result.metadata.attachment_hashes or []) == []
        assert result.metadata.body_hash is not None

    @pytest.mark.asyncio
    async def test_multiple_pdf_attachments(self, tmp_path):
        """Multiple PDF attachments should all be extracted."""
        from legal_portal.services.file_processors.eml_processor import process_eml

        msg = MIMEMultipart()
        msg["Subject"] = "Multi-PDF"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"
        msg.attach(MIMEText("Body text.", "plain"))

        for i in range(3):
            pdf_part = MIMEApplication(f"pdf-content-{i}".encode(), _subtype="pdf")
            pdf_part.add_header(
                "Content-Disposition", "attachment", filename=f"doc{i}.pdf",
            )
            msg.attach(pdf_part)

        eml_file = tmp_path / "multi.eml"
        eml_file.write_bytes(msg.as_bytes())

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "multi.eml",
        )

        attachments = result.metadata.attachments or []
        assert len(attachments) == 3
        filenames = [a["filename"] for a in attachments]
        assert filenames == ["doc0.pdf", "doc1.pdf", "doc2.pdf"]
