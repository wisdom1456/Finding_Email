"""Tests for uploading PDF attachments extracted from EMLs."""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest



class TestAttachmentUpload:
    """Test that _extract_deferred_documents uploads PDF attachments from EMLs."""

    @pytest.mark.asyncio
    async def test_pdf_attachment_uploaded_as_new_document(self):
        """After processing an EML, its PDF attachments should become new documents."""
        from legal_portal.api.routes.analysis import _extract_deferred_documents

        pdf_bytes = b"%PDF-1.4 test attachment content"
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # Build a simple EML with a PDF attachment
        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "a@b.com"
        msg["To"] = "c@d.com"
        msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"
        msg.attach(MIMEText("Email body with enough content for analysis purposes." * 3, "plain"))
        pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_part.add_header("Content-Disposition", "attachment", filename="contract.pdf")
        msg.attach(pdf_part)
        eml_bytes = msg.as_bytes()

        doc = {
            "id": "eml-doc-id",
            "case_id": "case-123",
            "user_id": "user-456",
            "file_name": "test.eml",
            "file_type": "text/plain",
            "storage_path": "user/case/test.eml",
            "extraction_method": "deferred",
            "extracted_text": None,
            "metadata": {},
        }

        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.download.return_value = eml_bytes

        # No existing documents with this content_hash
        mock_select = MagicMock()
        mock_select.eq.return_value = mock_select
        mock_select.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value = mock_select

        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new-pdf-id"}])

        # Mock storage upload for the PDF attachment
        mock_supabase.storage.from_.return_value.upload.return_value = None

        mock_progress = AsyncMock()

        results = await _extract_deferred_documents(
            [doc], mock_supabase, mock_progress, "test-analysis-id",
        )

        # The EML itself should be extracted
        assert "eml-doc-id" in results

        # A new document should have been inserted for the PDF attachment
        insert_calls = mock_supabase.table.return_value.insert.call_args_list
        assert len(insert_calls) >= 1
        inserted = insert_calls[0][0][0]  # first positional arg
        assert inserted["file_name"] == "contract.pdf"
        assert inserted["file_type"] == "application/pdf"
        assert inserted["extraction_method"] == "eml_attachment"
        assert inserted["metadata"]["parent_email_id"] == "eml-doc-id"
        assert inserted["metadata"]["content_hash"] == content_hash

    @pytest.mark.asyncio
    async def test_duplicate_attachment_skipped(self):
        """If a document with the same content_hash already exists, skip upload."""
        from legal_portal.api.routes.analysis import _extract_deferred_documents

        pdf_bytes = b"%PDF-1.4 duplicate content"
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "a@b.com"
        msg["To"] = "c@d.com"
        msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"
        msg.attach(MIMEText("Email body content." * 10, "plain"))
        pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_part.add_header("Content-Disposition", "attachment", filename="contract.pdf")
        msg.attach(pdf_part)

        doc = {
            "id": "eml-doc-id",
            "case_id": "case-123",
            "user_id": "user-456",
            "file_name": "test.eml",
            "file_type": "text/plain",
            "storage_path": "user/case/test.eml",
            "extraction_method": "deferred",
            "extracted_text": None,
            "metadata": {},
        }

        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.download.return_value = msg.as_bytes()

        # Existing document with same content_hash
        mock_select = MagicMock()
        mock_select.eq.return_value = mock_select
        mock_select.execute.return_value = MagicMock(
            data=[{"id": "existing-doc", "metadata": {"content_hash": content_hash}}]
        )
        mock_supabase.table.return_value.select.return_value = mock_select
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_progress = AsyncMock()

        results = await _extract_deferred_documents(
            [doc], mock_supabase, mock_progress, "test-analysis-id",
        )

        # No insert should have been called (attachment already exists)
        insert_calls = mock_supabase.table.return_value.insert.call_args_list
        assert len(insert_calls) == 0
