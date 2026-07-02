"""Regression tests for PR-1 bug fixes.

Tests cover:
- B2: get_optional_user returns None when no token provided
- B3: stream_chat_response rejects users who don't own the case
- B4: cache_manager uses JSON serialization (not pickle)
- B5: tracing skips file writes in serverless environments
- B7: DocumentValidationError is properly named and aliased
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestOptionalAuth:
    """B2: get_optional_user must accept unauthenticated requests."""

    def test_optional_security_has_auto_error_false(self):
        """The optional_security instance must not raise on missing tokens."""
        from legal_portal.api.dependencies import optional_security

        assert optional_security.auto_error is False

    def test_security_has_auto_error_true(self):
        """The primary security instance must still require auth."""
        from legal_portal.api.dependencies import security

        assert security.auto_error is True

    @pytest.mark.asyncio
    async def test_get_optional_user_returns_none_without_credentials(self):
        """When credentials is None, get_optional_user should return None."""
        from legal_portal.api.dependencies import get_optional_user

        result = await get_optional_user(credentials=None)
        assert result is None


class TestChatStreamAuthorization:
    """B3: stream_chat_response must verify case ownership."""

    def test_ensure_case_access_is_called_in_stream(self):
        """Verify that _ensure_case_access is referenced in stream_chat_response."""
        import inspect

        from legal_portal.api.routes.chat_routes import stream_chat_response

        source = inspect.getsource(stream_chat_response)
        assert "_ensure_case_access" in source, (
            "stream_chat_response must call _ensure_case_access for authorization"
        )

    def test_ensure_case_access_is_called_in_non_stream(self):
        """Verify the non-streaming endpoint also checks access (baseline)."""
        import inspect

        from legal_portal.api.routes.chat_routes import case_chat

        source = inspect.getsource(case_chat)
        assert "_ensure_case_access" in source


class TestCacheManagerSerialization:
    """B4: cache_manager must use JSON, not pickle."""

    def test_no_pickle_import(self):
        """The cache_manager module must not import pickle."""
        import legal_portal.utils.cache_manager as cm

        # Check that pickle is not in the module's namespace
        assert not hasattr(cm, "pickle"), "cache_manager must not use pickle"

    def test_cache_roundtrip_json(self):
        """Cache set/get must work with JSON-serializable data."""
        from legal_portal.utils.cache_manager import CacheManager

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(cache_dir=tmpdir, use_redis=False)

            test_data = {"key": "value", "nested": {"list": [1, 2, 3]}}
            cache.set("test_key", test_data)

            # Verify file is JSON, not pickle
            cache_file = Path(tmpdir) / "test_key.json"
            assert cache_file.exists(), "Cache file should use .json extension"

            with open(cache_file) as f:
                on_disk = json.load(f)
            assert on_disk == test_data

            # Verify get returns the same data
            result = cache.get("test_key")
            assert result == test_data

    def test_legacy_pkl_files_are_cleaned_up(self):
        """Legacy .pkl files should be removed on cache get."""
        from legal_portal.utils.cache_manager import CacheManager

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(cache_dir=tmpdir, use_redis=False)

            # Create a legacy .pkl file
            legacy_file = Path(tmpdir) / "old_key.pkl"
            legacy_file.write_bytes(b"fake pickle data")
            assert legacy_file.exists()

            # Calling get should clean it up
            cache.get("old_key")
            assert not legacy_file.exists(), "Legacy .pkl file should be cleaned up"


class TestTracingServerlessGuard:
    """B5: tracing must not write files in serverless environments."""

    def test_export_skips_on_vercel(self):
        """Span._export should not create files when VERCEL is set."""
        from legal_portal.utils.tracing import Span

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch.dict(os.environ, {"VERCEL": "1"}):
                    span = Span(name="test", operation="test_op")
                    span.finish()

                logs_dir = Path(tmpdir) / "logs"
                assert not logs_dir.exists(), "logs/ dir should not be created on Vercel"
            finally:
                os.chdir(old_cwd)

    def test_export_skips_on_lambda(self):
        """Span._export should not create files when AWS_LAMBDA_FUNCTION_NAME is set."""
        from legal_portal.utils.tracing import Span

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "my-func"}):
                    span = Span(name="test", operation="test_op")
                    span.finish()

                logs_dir = Path(tmpdir) / "logs"
                assert not logs_dir.exists(), "logs/ dir should not be created on Lambda"
            finally:
                os.chdir(old_cwd)

    def test_export_writes_locally(self):
        """Span._export should write files in local development."""
        from legal_portal.utils.tracing import Span

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                env_clean = {k: v for k, v in os.environ.items()
                             if k not in ("VERCEL", "AWS_LAMBDA_FUNCTION_NAME")}
                with patch.dict(os.environ, env_clean, clear=True):
                    span = Span(name="test", operation="test_op")
                    span.finish()

                traces_file = Path(tmpdir) / "logs" / "traces.json"
                assert traces_file.exists(), "traces.json should be created locally"
            finally:
                os.chdir(old_cwd)


class TestDocumentValidationError:
    """B7: ValidationError should be properly named to avoid shadowing."""

    def test_class_is_named_document_validation_error(self):
        """The class should be named DocumentValidationError."""
        from legal_portal.core.document_processor import DocumentValidationError

        assert DocumentValidationError.__name__ == "DocumentValidationError"

    def test_backward_compatible_alias_exists(self):
        """ValidationError alias should still work for existing importers."""
        from legal_portal.core.document_processor import ValidationError

        assert ValidationError.__name__ == "DocumentValidationError"
        assert issubclass(ValidationError, Exception)

    def test_does_not_shadow_pydantic(self):
        """The custom error should not be confused with pydantic.ValidationError."""
        from legal_portal.core.document_processor import ValidationError as DocValError
        from pydantic import ValidationError as PydanticValError

        assert DocValError is not PydanticValError
