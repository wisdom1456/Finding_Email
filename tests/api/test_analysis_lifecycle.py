"""Tests for analysis lifecycle edge cases — cancel, duplicate, incomplete."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from legal_portal.services.shared.progress_manager import ProgressManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _configure_supabase(mock_client, analysis_rows=None, case_rows=None):
    """Configure supabase mock for analysis lifecycle tests."""
    analysis_rows = analysis_rows or []
    case_rows = case_rows or [
        {"id": "case-001", "user_id": "00000000-0000-0000-0000-000000000001", "status": "pending"}
    ]

    def table_dispatcher(table_name):
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.upsert.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.neq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.single.return_value = mock_table

        if table_name == "analysis_results":
            mock_table.execute.return_value = MagicMock(data=analysis_rows)
        elif table_name == "cases":
            mock_table.execute.return_value = MagicMock(data=case_rows)
        elif table_name == "documents":
            mock_table.execute.return_value = MagicMock(data=[])
        elif table_name == "profiles":
            mock_table.execute.return_value = MagicMock(data=[])
        else:
            mock_table.execute.return_value = MagicMock(data=[])

        return mock_table

    mock_client.table.side_effect = table_dispatcher


# ---------------------------------------------------------------------------
# POST /cancel/{analysis_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_analysis_success(app_client: AsyncClient, mock_supabase_client):
    """200 + sets cancelled status."""
    analysis = {
        "id": "analysis-001",
        "case_id": "case-001",
        "status": "processing",
    }
    _configure_supabase(mock_supabase_client, analysis_rows=[analysis])

    # The cancel endpoint accesses request.app.state.progress_manager
    from legal_portal.api.main import app
    if not hasattr(app.state, "progress_manager"):
        app.state.progress_manager = ProgressManager()

    response = await app_client.post(
        "/api/analysis/cancel/analysis-001",
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_analysis_not_found(app_client: AsyncClient, mock_supabase_client):
    """404 for missing analysis."""
    _configure_supabase(mock_supabase_client, analysis_rows=[])

    response = await app_client.post(
        "/api/analysis/cancel/nonexistent",
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_analysis_unauthorized(app_client: AsyncClient, mock_supabase_client):
    """401/403 without auth."""
    response = await app_client.post(
        "/api/analysis/cancel/analysis-001",
    )

    assert response.status_code in [401, 403]


# ---------------------------------------------------------------------------
# GET /status/{case_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_status_success(app_client: AsyncClient, mock_supabase_client):
    """200 + analysis status for valid case."""
    analysis = {
        "id": "analysis-001",
        "case_id": "case-001",
        "status": "processing",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T01:00:00Z",
        "result": None,
        "error": None,
    }
    _configure_supabase(mock_supabase_client, analysis_rows=[analysis])

    response = await app_client.get(
        "/api/analysis/status/case-001",
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["processing", "completed", "pending", "failed"]


@pytest.mark.asyncio
async def test_get_status_not_found(app_client: AsyncClient, mock_supabase_client):
    """404 when no analysis exists for case."""
    _configure_supabase(mock_supabase_client, analysis_rows=[])

    response = await app_client.get(
        "/api/analysis/status/case-001",
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /results/{case_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_results_incomplete_analysis(app_client: AsyncClient, mock_supabase_client):
    """Appropriate response for in-progress analysis (no completed result)."""
    _configure_supabase(mock_supabase_client, analysis_rows=[])

    response = await app_client.get(
        "/api/analysis/results/case-001",
        headers={"Authorization": "Bearer mock_token"},
    )

    # No completed analysis found
    assert response.status_code in [404, 200]
