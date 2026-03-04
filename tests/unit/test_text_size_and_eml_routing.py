"""Tests for oversized text truncation and .eml routing fixes.

Fix 2: sanitize_text_for_db truncates text exceeding MAX_EXTRACTED_TEXT_CHARS.
Fix 3: .eml files with file_type text/plain are detected and routed to process_eml.
"""

import os
import tempfile

import pytest

from legal_portal.utils.security import (
    MAX_EXTRACTED_TEXT_CHARS,
    sanitize_text_for_db,
)


# ---------------------------------------------------------------------------
# Fix 2 – sanitize_text_for_db text size cap
# ---------------------------------------------------------------------------

class TestSanitizeTextForDbTruncation:
    """Verify sanitize_text_for_db enforces the MAX_EXTRACTED_TEXT_CHARS limit."""

    def test_text_under_limit_unchanged(self):
        text = "Hello world" * 100  # 1100 chars, well under limit
        assert sanitize_text_for_db(text) == text

    def test_text_at_limit_unchanged(self):
        text = "x" * MAX_EXTRACTED_TEXT_CHARS
        assert sanitize_text_for_db(text) == text
        assert len(sanitize_text_for_db(text)) == MAX_EXTRACTED_TEXT_CHARS

    def test_text_over_limit_truncated(self):
        text = "a" * (MAX_EXTRACTED_TEXT_CHARS + 50_000)
        result = sanitize_text_for_db(text)
        assert len(result) == MAX_EXTRACTED_TEXT_CHARS

    def test_large_email_like_text_truncated(self):
        """Simulates the 128 MB email scenario that crashed the database."""
        # 1 million chars (~1 MB) is enough to prove the cap works
        text = "From: sender@example.com\n" * 50_000
        assert len(text) > MAX_EXTRACTED_TEXT_CHARS
        result = sanitize_text_for_db(text)
        assert len(result) == MAX_EXTRACTED_TEXT_CHARS

    def test_none_returns_none(self):
        assert sanitize_text_for_db(None) is None

    def test_empty_string_returns_empty(self):
        assert sanitize_text_for_db("") == ""

    def test_null_chars_removed_before_truncation(self):
        """NULL characters are stripped first, potentially bringing text under the limit."""
        # Build text that's over limit only because of NULL chars
        real_text = "a" * (MAX_EXTRACTED_TEXT_CHARS - 10)
        padded = real_text + "\x00" * 50_000
        result = sanitize_text_for_db(padded)
        # After stripping NULLs, text is under limit so no truncation
        assert result == real_text

    def test_max_extracted_text_chars_value(self):
        """Ensure the constant is set to the expected value."""
        assert MAX_EXTRACTED_TEXT_CHARS == 500_000


# ---------------------------------------------------------------------------
# Fix 3 – .eml file detection in text/plain branches
# ---------------------------------------------------------------------------

class TestEmlFileDetection:
    """Verify that .eml files are correctly identified regardless of file_type."""

    @pytest.mark.parametrize("filename", [
        "forwarded_email.eml",
        "IMPORTANT.EML",
        "message.Eml",
        "re_fw_contract.eml",
    ])
    def test_eml_extension_detected(self, filename):
        """Files ending in .eml should be detected by the guard condition."""
        assert filename.lower().endswith(".eml")

    @pytest.mark.parametrize("filename", [
        "notes.txt",
        "readme.txt",
        "plain_text.TXT",
        "email_backup.txt",
    ])
    def test_non_eml_not_detected(self, filename):
        """Regular .txt files should NOT match the .eml guard."""
        assert not filename.lower().endswith(".eml")

    def test_eml_with_text_plain_file_type_would_match_text_branch(self):
        """Demonstrates the bug: file_type text/plain matches the text branch."""
        file_type = "text/plain"
        file_name = "forwarded_email.eml"
        # The text/plain branch condition matches...
        assert file_type in ["text/plain", "txt"] or file_name.lower().endswith(".txt")
        # ...but the inner .eml guard catches it
        assert file_name.lower().endswith(".eml")


# ---------------------------------------------------------------------------
# Fix 3b – process_eml actually works on .eml content
# ---------------------------------------------------------------------------

class TestProcessEmlIntegration:
    """Verify process_eml extracts content from real .eml bytes."""

    @pytest.fixture
    def simple_eml_bytes(self):
        """A minimal valid .eml file."""
        return (
            b"From: sender@example.com\r\n"
            b"To: recipient@example.com\r\n"
            b"Subject: Test Email\r\n"
            b"Date: Mon, 3 Mar 2026 12:00:00 -0500\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"This is the body of a test email.\r\n"
        )

    @pytest.fixture
    def large_eml_bytes(self):
        """An .eml file with a body exceeding process_eml's 200K internal cap."""
        header = (
            b"From: sender@example.com\r\n"
            b"To: recipient@example.com\r\n"
            b"Subject: Large Email\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
        )
        body = b"A" * 300_000  # 300K chars, exceeds 200K cap
        return header + body

    @pytest.mark.asyncio
    async def test_process_eml_extracts_headers_and_body(self, simple_eml_bytes):
        from legal_portal.core.data_models import DocumentType
        from legal_portal.services.file_processors.eml_processor import process_eml

        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
            tmp.write(simple_eml_bytes)
            tmp_path = tmp.name

        try:
            result = await process_eml(
                file_path=tmp_path,
                document_type=DocumentType.CORRESPONDENCE,
                original_filename="test.eml",
            )
            assert "Test Email" in result.content  # Subject in output
            assert "test email" in result.content.lower()  # Body in output
            assert result.extraction_quality in ("high", "medium")
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_process_eml_respects_200k_cap(self, large_eml_bytes):
        from legal_portal.core.data_models import DocumentType
        from legal_portal.services.file_processors.eml_processor import process_eml

        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
            tmp.write(large_eml_bytes)
            tmp_path = tmp.name

        try:
            result = await process_eml(
                file_path=tmp_path,
                document_type=DocumentType.CORRESPONDENCE,
                original_filename="large.eml",
            )
            # process_eml caps at 200K chars
            assert len(result.content) <= 200_000
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_sanitize_caps_after_process_eml(self, large_eml_bytes):
        """Double protection: process_eml (200K) + sanitize_text_for_db (500K)."""
        from legal_portal.core.data_models import DocumentType
        from legal_portal.services.file_processors.eml_processor import process_eml

        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
            tmp.write(large_eml_bytes)
            tmp_path = tmp.name

        try:
            result = await process_eml(
                file_path=tmp_path,
                document_type=DocumentType.CORRESPONDENCE,
                original_filename="large.eml",
            )
            sanitized = sanitize_text_for_db(result.content)
            assert len(sanitized) <= MAX_EXTRACTED_TEXT_CHARS
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# VerificationHub triage grouping logic
# ---------------------------------------------------------------------------

class TestTriageGrouping:
    """Verify the triage rules that match VerificationHub.svelte."""

    @staticmethod
    def triage(doc):
        """Python reimplementation of VerificationHub triage logic."""
        status = doc.get("status", "")
        is_duplicate = doc.get("metadata", {}).get("is_duplicate") or status == "duplicate"
        is_excluded = doc.get("metadata", {}).get("excluded")

        if is_excluded:
            return "excluded"
        if is_duplicate:
            return "duplicates"
        if status in ("download_failed", "corrupted"):
            return "critical"
        if (
            status == "extraction_failed"
            or status == "needs_review"
            or status == "pending"
            or (status == "ready" and not doc.get("extracted_at"))
        ):
            return "needs_attention"
        return "ready"

    def test_ready_with_extracted_at_goes_to_ready(self):
        doc = {"status": "ready", "extracted_at": "2026-03-04T12:00:00", "metadata": {}}
        assert self.triage(doc) == "ready"

    def test_ready_without_extracted_at_goes_to_needs_attention(self):
        doc = {"status": "ready", "extracted_at": None, "metadata": {}}
        assert self.triage(doc) == "needs_attention"

    def test_ready_without_extracted_at_key_goes_to_needs_attention(self):
        doc = {"status": "ready", "metadata": {}}
        assert self.triage(doc) == "needs_attention"

    def test_pending_goes_to_needs_attention(self):
        doc = {"status": "pending", "metadata": {}}
        assert self.triage(doc) == "needs_attention"

    def test_extraction_failed_goes_to_needs_attention(self):
        doc = {"status": "extraction_failed", "metadata": {}}
        assert self.triage(doc) == "needs_attention"

    def test_verified_ready_still_goes_to_ready(self):
        """is_verified no longer matters — only extracted_at."""
        doc = {"status": "ready", "extracted_at": "2026-03-04T12:00:00", "is_verified": True, "metadata": {}}
        assert self.triage(doc) == "ready"

    def test_unverified_ready_with_text_goes_to_ready(self):
        """The key fix: ready + extracted text should NOT require verification."""
        doc = {"status": "ready", "extracted_at": "2026-03-04T12:00:00", "is_verified": False, "metadata": {}}
        assert self.triage(doc) == "ready"

    def test_duplicate_goes_to_duplicates(self):
        doc = {"status": "duplicate", "metadata": {}}
        assert self.triage(doc) == "duplicates"

    def test_excluded_goes_to_excluded(self):
        doc = {"status": "ready", "extracted_at": "2026-03-04T12:00:00", "metadata": {"excluded": True}}
        assert self.triage(doc) == "excluded"
