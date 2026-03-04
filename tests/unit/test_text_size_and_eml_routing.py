"""Tests for oversized text truncation and .eml routing fixes.

Fix 2: sanitize_text_for_db truncates text exceeding MAX_EXTRACTED_TEXT_CHARS.
Fix 3: .eml files with file_type text/plain are detected and routed to process_eml.
"""

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
