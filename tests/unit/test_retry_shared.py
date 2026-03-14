"""Tests for shared retry utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from legal_portal.api.middleware.retry import (
    is_transient_supabase_error,
    retry_async,
    retry_sync,
)


class FakeAPIError(Exception):
    def __init__(self, message: str, code: str = ""):
        self.message = message
        self.code = code
        super().__init__(message)


class TestIsTransientSupabaseError:
    def test_502_code(self):
        assert is_transient_supabase_error(FakeAPIError("x", code="502")) is True

    def test_503_code(self):
        assert is_transient_supabase_error(FakeAPIError("x", code="503")) is True

    def test_57014_code(self):
        assert is_transient_supabase_error(FakeAPIError("x", code="57014")) is True

    def test_bad_gateway_message(self):
        assert is_transient_supabase_error(FakeAPIError("Bad Gateway")) is True

    def test_service_unavailable_message(self):
        assert is_transient_supabase_error(FakeAPIError("Service Unavailable")) is True

    def test_schema_cache_message(self):
        assert is_transient_supabase_error(FakeAPIError("schema cache rebuild")) is True

    def test_statement_timeout_message(self):
        assert is_transient_supabase_error(FakeAPIError("statement timeout")) is True

    def test_non_transient_400(self):
        assert is_transient_supabase_error(FakeAPIError("bad request", code="400")) is False

    def test_non_transient_permission(self):
        assert is_transient_supabase_error(FakeAPIError("permission denied", code="403")) is False

    def test_plain_exception_no_code_attr(self):
        assert is_transient_supabase_error(ValueError("something")) is False


class TestRetrySync:
    def test_success_no_retry(self):
        fn = MagicMock(return_value="ok")
        result = retry_sync(fn, max_attempts=3)
        assert result == "ok"
        assert fn.call_count == 1

    def test_retries_on_transient_then_succeeds(self):
        fn = MagicMock(side_effect=[
            FakeAPIError("Bad Gateway", code="502"),
            "ok",
        ])
        with patch("legal_portal.api.middleware.retry.time.sleep"):
            result = retry_sync(fn, max_attempts=3)
        assert result == "ok"
        assert fn.call_count == 2

    def test_exhausts_retries_raises(self):
        fn = MagicMock(side_effect=[
            FakeAPIError("Bad Gateway", code="502"),
            FakeAPIError("Bad Gateway", code="502"),
            FakeAPIError("Bad Gateway", code="502"),
        ])
        with patch("legal_portal.api.middleware.retry.time.sleep"):
            with pytest.raises(FakeAPIError):
                retry_sync(fn, max_attempts=3)
        assert fn.call_count == 3

    def test_non_retryable_raises_immediately(self):
        fn = MagicMock(side_effect=FakeAPIError("bad request", code="400"))
        with pytest.raises(FakeAPIError):
            retry_sync(fn, max_attempts=3)
        assert fn.call_count == 1

    def test_exponential_backoff_delays(self):
        fn = MagicMock(side_effect=[
            FakeAPIError("x", code="502"),
            FakeAPIError("x", code="502"),
            FakeAPIError("x", code="502"),
        ])
        with patch("legal_portal.api.middleware.retry.time.sleep") as mock_sleep:
            with pytest.raises(FakeAPIError):
                retry_sync(fn, max_attempts=3)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    def test_custom_is_retryable(self):
        fn = MagicMock(side_effect=[ValueError("retry me"), "ok"])
        with patch("legal_portal.api.middleware.retry.time.sleep"):
            result = retry_sync(
                fn, max_attempts=3, is_retryable=lambda e: isinstance(e, ValueError)
            )
        assert result == "ok"

    def test_context_label_in_logging(self):
        fn = MagicMock(side_effect=[FakeAPIError("x", code="502"), "ok"])
        with patch("legal_portal.api.middleware.retry.time.sleep"):
            with patch("legal_portal.api.middleware.retry.logger") as mock_logger:
                retry_sync(fn, max_attempts=3, context_label="test_op")
        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args
        assert "test_op" in str(call_args)


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        fn = MagicMock(return_value="ok")
        result = await retry_async(fn, max_attempts=3)
        assert result == "ok"
        assert fn.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_then_succeeds(self):
        fn = MagicMock(side_effect=[
            FakeAPIError("Bad Gateway", code="502"),
            "ok",
        ])
        with patch("legal_portal.api.middleware.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await retry_async(fn, max_attempts=3)
        assert result == "ok"
        assert fn.call_count == 2

    @pytest.mark.asyncio
    async def test_exhausts_retries_raises(self):
        fn = MagicMock(side_effect=[
            FakeAPIError("x", code="502"),
            FakeAPIError("x", code="502"),
            FakeAPIError("x", code="502"),
        ])
        with patch("legal_portal.api.middleware.retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(FakeAPIError):
                await retry_async(fn, max_attempts=3)
        assert fn.call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        fn = MagicMock(side_effect=FakeAPIError("bad request", code="400"))
        with pytest.raises(FakeAPIError):
            await retry_async(fn, max_attempts=3)
        assert fn.call_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        fn = MagicMock(side_effect=[
            FakeAPIError("x", code="502"),
            FakeAPIError("x", code="502"),
            FakeAPIError("x", code="502"),
        ])
        with patch("legal_portal.api.middleware.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(FakeAPIError):
                await retry_async(fn, max_attempts=3)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)
