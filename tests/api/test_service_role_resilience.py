"""Regression tests for endpoints that should not hard-fail without service-role env."""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class _FakeAuth:
    def get_user(self, _token: str):
        user = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000001",
            email="test@example.com",
            user_metadata={},
            app_metadata={},
        )
        return SimpleNamespace(user=user)


class _FakeQuery:
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.action = "select"

    def select(self, *_args, **_kwargs):
        self.action = "select"
        return self

    def delete(self):
        self.action = "delete"
        return self

    def update(self, *_args, **_kwargs):
        self.action = "update"
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self.table_name == "integrations_clio" and self.action == "select":
            return SimpleNamespace(data=[], error=None)
        if self.table_name == "integrations_clio" and self.action == "delete":
            return SimpleNamespace(data=[], error=None)
        if self.table_name == "cases" and self.action == "select":
            return SimpleNamespace(data=[{"id": "case-001"}], error=None)
        if self.table_name == "documents" and self.action == "select":
            return SimpleNamespace(data=[{"storage_path": "documents/test/doc.pdf"}], error=None)
        if self.table_name == "cases" and self.action == "delete":
            return SimpleNamespace(data=[], error=None)
        if self.table_name == "analysis_results" and self.action == "select":
            return SimpleNamespace(data=[{"id": "analysis-001", "case_id": "case-001", "status": "processing"}], error=None)
        if self.table_name == "analysis_results" and self.action == "update":
            return SimpleNamespace(data=[], error=None)
        if self.table_name == "cases" and self.action == "update":
            return SimpleNamespace(data=[], error=None)
        return SimpleNamespace(data=[], error=None)


class _FakeUserSupabase:
    def __init__(self):
        self.auth = _FakeAuth()

    def table(self, table_name: str):
        return _FakeQuery(table_name)


@pytest_asyncio.fixture
async def resilience_client(monkeypatch):
    from legal_portal.api.dependencies import get_supabase_client, get_user_supabase_client
    from legal_portal.api.main import app

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    get_supabase_client.cache_clear()

    fake_user_supabase = _FakeUserSupabase()

    async def override_get_user_supabase():
        return fake_user_supabase

    app.dependency_overrides[get_user_supabase_client] = override_get_user_supabase

    # Ensure app.state.progress_manager exists (lifespan doesn't run with ASGITransport)
    if not hasattr(app.state, "progress_manager"):
        from legal_portal.services.shared.progress_manager import ProgressManager
        app.state.progress_manager = ProgressManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    get_supabase_client.cache_clear()


@pytest.mark.asyncio
async def test_clio_status_succeeds_without_service_role_key(resilience_client: AsyncClient):
    response = await resilience_client.get("/api/clio/status", headers={"Authorization": "Bearer mock_token"})

    assert response.status_code == 200
    assert response.json() == {"connected": False, "clio_user_id": None, "expires_at": None}


@pytest.mark.asyncio
async def test_delete_case_succeeds_without_service_role_key(resilience_client: AsyncClient):
    response = await resilience_client.delete("/api/cases/case-001", headers={"Authorization": "Bearer mock_token"})

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_clio_disconnect_succeeds_without_service_role_key(resilience_client: AsyncClient):
    response = await resilience_client.delete("/api/clio/disconnect", headers={"Authorization": "Bearer mock_token"})

    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_cancel_case_requires_service_role_key(resilience_client: AsyncClient):
    """cancel-case intentionally depends on the service-role client.

    Durable-job cancellation reads/writes ``analysis_jobs``, which RLS-scoped
    user clients cannot touch, so the endpoint requires ``SUPABASE_SERVICE_KEY``.
    Product decision (2026-07-02): keep the app strict — without the key the
    service-client dependency fails fast rather than silently falling back to
    the user client. (``delete_case`` / ``clio_disconnect`` above deliberately
    operate on the user client and do *not* need the key.)
    """
    with pytest.raises(ValueError, match="SUPABASE_SERVICE_KEY"):
        await resilience_client.post(
            "/api/analysis/cancel-case/case-001",
            headers={"Authorization": "Bearer mock_token"},
        )
