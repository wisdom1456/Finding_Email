"""Tests for document status and recovery endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _analysis_with_docs(analysis_id="analysis-001", case_id="case-001", docs=None):
    """Return an analysis_results row with chunk_state documents."""
    if docs is None:
        docs = {
            "doc-1": {"status": "completed"},
            "doc-2": {"status": "failed"},
            "doc-3": {"status": "pending"},
        }
    return {
        "id": analysis_id,
        "case_id": case_id,
        "status": "processing",
        "chunk_state": {"documents": docs, "phase": "extraction", "chunks": []},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T01:00:00Z",
    }


def _configure_supabase(mock_client, analysis_row):
    """Configure supabase mock for document status routes."""

    def table_dispatcher(table_name):
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.single.return_value = mock_table

        if table_name == "analysis_results":
            mock_table.execute.return_value = MagicMock(
                data=analysis_row if analysis_row else None
            )
        elif table_name == "cases":
            mock_table.execute.return_value = MagicMock(
                data=[{"id": "case-001", "user_id": "00000000-0000-0000-0000-000000000001"}]
            )
        else:
            mock_table.execute.return_value = MagicMock(data=[])

        return mock_table

    mock_client.table.side_effect = table_dispatcher


# ---------------------------------------------------------------------------
# GET /{analysis_id}/documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_document_status_success(app_client: AsyncClient, mock_supabase_client):
    """200 + document list with status summary."""
    row = _analysis_with_docs()
    _configure_supabase(mock_supabase_client, row)

    response = await app_client.get(
        "/api/analysis/analysis-001/documents",
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["completed"] == 1
    assert data["failed"] == 1
    assert data["pending"] == 1
    assert data["can_proceed"] is False


@pytest.mark.asyncio
async def test_get_document_status_not_found(app_client: AsyncClient, mock_supabase_client):
    """404 for missing analysis."""
    _configure_supabase(mock_supabase_client, None)

    response = await app_client.get(
        "/api/analysis/nonexistent/documents",
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_document_status_unauthorized(app_client: AsyncClient, mock_supabase_client):
    """401/403 without auth header."""
    response = await app_client.get(
        "/api/analysis/analysis-001/documents",
    )

    assert response.status_code in [401, 403]


# ---------------------------------------------------------------------------
# POST /{analysis_id}/retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_failed_documents_specific_ids(app_client: AsyncClient, mock_supabase_client):
    """200 + retries selected documents."""
    row = _analysis_with_docs()
    _configure_supabase(mock_supabase_client, row)

    with patch("legal_portal.services.documents.chunk_state_manager.ChunkStateManager") as MockCSM:
        mock_csm = AsyncMock()
        mock_csm.get_failed_documents.return_value = [{"id": "doc-2"}]
        mock_csm.reset_documents_for_retry.return_value = 1
        MockCSM.return_value = mock_csm

        response = await app_client.post(
            "/api/analysis/analysis-001/retry",
            json={"document_ids": ["doc-2"]},
            headers={"Authorization": "Bearer mock_token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action"] == "retry"
    assert data["affected_count"] == 1


@pytest.mark.asyncio
async def test_retry_failed_documents_all(app_client: AsyncClient, mock_supabase_client):
    """200 + retries all failed when empty document_ids list."""
    row = _analysis_with_docs()
    _configure_supabase(mock_supabase_client, row)

    with patch("legal_portal.services.documents.chunk_state_manager.ChunkStateManager") as MockCSM:
        mock_csm = AsyncMock()
        mock_csm.get_failed_documents.return_value = [{"id": "doc-2"}, {"id": "doc-3"}]
        mock_csm.reset_documents_for_retry.return_value = 2
        MockCSM.return_value = mock_csm

        response = await app_client.post(
            "/api/analysis/analysis-001/retry",
            json={"document_ids": []},
            headers={"Authorization": "Bearer mock_token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["affected_count"] == 2


@pytest.mark.asyncio
async def test_retry_failed_documents_not_found(app_client: AsyncClient, mock_supabase_client):
    """404 for missing analysis."""
    _configure_supabase(mock_supabase_client, None)

    response = await app_client.post(
        "/api/analysis/nonexistent/retry",
        json={"document_ids": []},
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /{analysis_id}/skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_failed_documents_specific_ids(app_client: AsyncClient, mock_supabase_client):
    """200 + skips selected documents."""
    row = _analysis_with_docs()
    _configure_supabase(mock_supabase_client, row)

    with patch("legal_portal.services.documents.chunk_state_manager.ChunkStateManager") as MockCSM:
        mock_csm = AsyncMock()
        mock_csm.get_failed_documents.return_value = [{"id": "doc-2"}]
        mock_csm.mark_documents_skipped.return_value = 1
        mock_csm.can_proceed_to_synthesis.return_value = False
        MockCSM.return_value = mock_csm

        response = await app_client.post(
            "/api/analysis/analysis-001/skip",
            json={"document_ids": ["doc-2"]},
            headers={"Authorization": "Bearer mock_token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action"] == "skip"
    assert data["affected_count"] == 1


@pytest.mark.asyncio
async def test_skip_failed_documents_all(app_client: AsyncClient, mock_supabase_client):
    """200 + skips all failed when empty document_ids list."""
    row = _analysis_with_docs()
    _configure_supabase(mock_supabase_client, row)

    with patch("legal_portal.services.documents.chunk_state_manager.ChunkStateManager") as MockCSM:
        mock_csm = AsyncMock()
        mock_csm.get_failed_documents.return_value = [{"id": "doc-2"}]
        mock_csm.mark_documents_skipped.return_value = 1
        mock_csm.can_proceed_to_synthesis.return_value = True
        MockCSM.return_value = mock_csm

        response = await app_client.post(
            "/api/analysis/analysis-001/skip",
            json={"document_ids": []},
            headers={"Authorization": "Bearer mock_token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "proceed" in data["message"].lower()


# ---------------------------------------------------------------------------
# GET /{analysis_id}/state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_analysis_state_success(app_client: AsyncClient, mock_supabase_client):
    """200 + chunk_state structure."""
    row = _analysis_with_docs()
    _configure_supabase(mock_supabase_client, row)

    response = await app_client.get(
        "/api/analysis/analysis-001/state",
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["analysis_id"] == "analysis-001"
    assert "summary" in data
    assert data["summary"]["total"] == 3
    assert "can_proceed" in data


@pytest.mark.asyncio
async def test_get_analysis_state_not_found(app_client: AsyncClient, mock_supabase_client):
    """404 for missing analysis."""
    _configure_supabase(mock_supabase_client, None)

    response = await app_client.get(
        "/api/analysis/nonexistent/state",
        headers={"Authorization": "Bearer mock_token"},
    )

    assert response.status_code == 404
