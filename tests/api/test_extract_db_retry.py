"""Tests for Supabase transient error retry logic in document extraction.

Verifies:
- 502/503 errors are retried with exponential backoff
- Non-transient errors fail immediately
- Retry exhaustion raises HTTPException 500
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


class FakeAPIError(Exception):
    """Simulates a postgrest APIError with code and message."""

    def __init__(self, message: str, code: str = ""):
        self.message = message
        self.code = code
        super().__init__(message)


class TestIsTransientSupabaseError:
    """Test the _is_transient_supabase_error helper."""

    def test_502_is_transient(self):
        from legal_portal.api.routes.documents import _is_transient_supabase_error

        err = FakeAPIError("Bad gateway", code="502")
        assert _is_transient_supabase_error(err) is True

    def test_503_is_transient(self):
        from legal_portal.api.routes.documents import _is_transient_supabase_error

        err = FakeAPIError("Service Unavailable", code="503")
        assert _is_transient_supabase_error(err) is True

    def test_schema_cache_message_is_transient(self):
        from legal_portal.api.routes.documents import _is_transient_supabase_error

        err = FakeAPIError("schema cache is being rebuilt", code="500")
        assert _is_transient_supabase_error(err) is True

    def test_bad_gateway_message_is_transient(self):
        from legal_portal.api.routes.documents import _is_transient_supabase_error

        err = FakeAPIError("Bad Gateway", code="")
        assert _is_transient_supabase_error(err) is True

    def test_400_is_not_transient(self):
        from legal_portal.api.routes.documents import _is_transient_supabase_error

        err = FakeAPIError("Invalid request", code="400")
        assert _is_transient_supabase_error(err) is False

    def test_permission_denied_is_not_transient(self):
        from legal_portal.api.routes.documents import _is_transient_supabase_error

        err = FakeAPIError("permission denied", code="403")
        assert _is_transient_supabase_error(err) is False


class TestExtractionDbRetry:
    """Test retry behavior in the document extraction DB update."""

    def _make_mock_chain(self, execute_side_effect):
        """Create a mock Supabase table chain with given execute behavior."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.side_effect = execute_side_effect
        mock_supabase.table.return_value = mock_table
        return mock_supabase, mock_table

    def test_retries_on_502_and_succeeds(self):
        """Mock .execute() to raise 502 twice, then succeed. Verify update completes."""
        from legal_portal.api.routes.documents import _update_document_with_retry

        mock_supabase, mock_table = self._make_mock_chain(
            [
                FakeAPIError("Bad Gateway", code="502"),
                FakeAPIError("Bad Gateway", code="502"),
                MagicMock(data=[{"id": "doc-001"}]),
            ]
        )

        # Should succeed after 2 retries (no real sleep in test)
        with patch("legal_portal.api.routes.documents.time.sleep"):
            result = _update_document_with_retry(
                mock_supabase, "doc-001", {"status": "ready"}
            )

        assert result.data == [{"id": "doc-001"}]
        assert mock_table.execute.call_count == 3

    def test_retries_on_503_and_succeeds(self):
        """Mock .execute() to raise 503 once, then succeed."""
        from legal_portal.api.routes.documents import _update_document_with_retry

        mock_supabase, mock_table = self._make_mock_chain(
            [
                FakeAPIError("Service Unavailable", code="503"),
                MagicMock(data=[{"id": "doc-002"}]),
            ]
        )

        with patch("legal_portal.api.routes.documents.time.sleep"):
            result = _update_document_with_retry(
                mock_supabase, "doc-002", {"status": "ready"}
            )

        assert result.data == [{"id": "doc-002"}]
        assert mock_table.execute.call_count == 2

    def test_exhausts_retries_raises_500(self):
        """All 3 attempts fail with transient error → HTTPException 500."""
        from legal_portal.api.routes.documents import _update_document_with_retry

        mock_supabase, mock_table = self._make_mock_chain(
            [
                FakeAPIError("Bad Gateway", code="502"),
                FakeAPIError("Bad Gateway", code="502"),
                FakeAPIError("Bad Gateway", code="502"),
            ]
        )

        with patch("legal_portal.api.routes.documents.time.sleep"):
            with pytest.raises(HTTPException) as exc_info:
                _update_document_with_retry(
                    mock_supabase, "doc-003", {"status": "ready"}
                )

        assert exc_info.value.status_code == 500
        assert "Failed to save extraction results" in exc_info.value.detail
        assert mock_table.execute.call_count == 3

    def test_no_retry_on_non_transient_error(self):
        """Non-transient error (400) → immediate HTTPException 500, no retry."""
        from legal_portal.api.routes.documents import _update_document_with_retry

        mock_supabase, mock_table = self._make_mock_chain(
            [FakeAPIError("Invalid request body", code="400")]
        )

        with patch("legal_portal.api.routes.documents.time.sleep"):
            with pytest.raises(HTTPException) as exc_info:
                _update_document_with_retry(
                    mock_supabase, "doc-004", {"status": "ready"}
                )

        assert exc_info.value.status_code == 500
        assert mock_table.execute.call_count == 1  # No retry

    def test_backoff_delays_are_exponential(self):
        """Verify sleep is called with 1, 2, 4 second delays."""
        from legal_portal.api.routes.documents import _update_document_with_retry

        mock_supabase, _ = self._make_mock_chain(
            [
                FakeAPIError("Bad Gateway", code="502"),
                FakeAPIError("Bad Gateway", code="502"),
                FakeAPIError("Bad Gateway", code="502"),
            ]
        )

        with patch("legal_portal.api.routes.documents.time.sleep") as mock_sleep:
            with pytest.raises(HTTPException):
                _update_document_with_retry(
                    mock_supabase, "doc-005", {"status": "ready"}
                )

        # Should sleep between attempts 0→1 and 1→2 (not after last failure)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)
