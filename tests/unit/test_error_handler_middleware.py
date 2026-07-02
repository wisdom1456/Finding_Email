"""Tests for the AppError error handler middleware."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from legal_portal.api.middleware.error_handler import register_app_error_handler
from legal_portal.core.exceptions import (
    AppError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
)


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the error handler registered."""
    app = FastAPI()
    register_app_error_handler(app)
    return app


class TestAppErrorHandler:
    def test_not_found_returns_404(self):
        app = _make_app()

        @app.get("/test")
        async def endpoint():
            raise NotFoundError("item missing", context={"id": "42"})

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "NotFoundError"
        assert body["message"] == "item missing"
        assert body["context"] == {"id": "42"}

    def test_validation_returns_422(self):
        app = _make_app()

        @app.get("/test")
        async def endpoint():
            raise ValidationError("bad field")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "ValidationError"

    def test_authorization_returns_403(self):
        app = _make_app()

        @app.get("/test")
        async def endpoint():
            raise AuthorizationError("denied")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test")
        assert resp.status_code == 403

    def test_base_app_error_returns_500(self):
        app = _make_app()

        @app.get("/test")
        async def endpoint():
            raise AppError("internal")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == "AppError"

    def test_context_null_when_empty(self):
        app = _make_app()

        @app.get("/test")
        async def endpoint():
            raise NotFoundError("gone")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test")
        body = resp.json()
        assert body["context"] is None

    def test_non_app_error_not_caught(self):
        """Regular exceptions should NOT be caught by our handler."""
        app = _make_app()

        @app.get("/test")
        async def endpoint():
            raise RuntimeError("unrelated")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test")
        # FastAPI's default handler returns 500 for unhandled exceptions
        assert resp.status_code == 500
