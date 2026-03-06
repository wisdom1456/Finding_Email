"""Tests for email thread deduplication."""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from legal_portal.core.data_models import DocumentStatus


def _make_eml_doc(
    doc_id, subject, body, file_name="email.eml", body_hash=None,
):
    """Build a mock EML document dict."""
    if body_hash is None:
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return {
        "id": doc_id,
        "case_id": "case-123",
        "file_name": file_name,
        "file_type": "text/plain",
        "extracted_text": f"Subject: {subject}\nFrom: a@b.com\nTo: c@d.com\nDate: Mon, 1 Jan 2025\n\n{body}",
        "metadata": {"body_hash": body_hash},
        "is_flagged_as_junk": False,
        "status": DocumentStatus.READY,
    }


class TestEmailThreadDedup:
    """Test _dedup_email_threads flags superseded and duplicate emails."""

    @pytest.mark.asyncio
    async def test_thread_keeps_longest_reply(self):
        """In a thread, only the longest email should survive; shorter ones are flagged."""
        from legal_portal.api.routes.analysis import _dedup_email_threads

        docs = [
            _make_eml_doc("d1", "Intake Documents", "Short initial email."),
            _make_eml_doc("d2", "Re: Intake Documents", "Short initial email.\n\nReply adding more."),
            _make_eml_doc(
                "d3", "Re: Re: Intake Documents",
                "Short initial email.\n\nReply adding more.\n\nFinal reply with even more content.",
            ),
        ]

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        flagged = await _dedup_email_threads(docs, mock_supabase)

        assert "d1" in flagged
        assert "d2" in flagged
        assert "d3" not in flagged  # longest - kept

    @pytest.mark.asyncio
    async def test_exact_duplicates_flagged(self):
        """Emails with identical body_hash should be deduped (keep first)."""
        from legal_portal.api.routes.analysis import _dedup_email_threads

        body = "Identical email body content."
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        docs = [
            _make_eml_doc("d1", "Report", body, file_name="email1.eml", body_hash=body_hash),
            _make_eml_doc("d2", "Fwd: Report", body, file_name="email2.eml", body_hash=body_hash),
            _make_eml_doc("d3", "FW: Report", body, file_name="email3.eml", body_hash=body_hash),
        ]

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        flagged = await _dedup_email_threads(docs, mock_supabase)

        # Two of the three should be flagged
        assert len(flagged) == 2
        assert "d1" not in flagged  # first one kept

    @pytest.mark.asyncio
    async def test_different_threads_not_deduped(self):
        """Emails in different threads should not affect each other."""
        from legal_portal.api.routes.analysis import _dedup_email_threads

        docs = [
            _make_eml_doc("d1", "Intake Documents", "Content about intake."),
            _make_eml_doc("d2", "Payment Discussion", "Content about payment."),
        ]

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        flagged = await _dedup_email_threads(docs, mock_supabase)

        assert len(flagged) == 0  # Different threads, nothing flagged

    @pytest.mark.asyncio
    async def test_no_eml_docs_is_noop(self):
        """Empty input should return empty result."""
        from legal_portal.api.routes.analysis import _dedup_email_threads

        mock_supabase = MagicMock()
        flagged = await _dedup_email_threads([], mock_supabase)
        assert flagged == set()
