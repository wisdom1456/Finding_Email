"""Tests for analysis results endpoint returning pending instead of 404.

Verifies:
- Returns 200 with pending status when case exists but no results yet
- Returns 404 when case not found (unchanged behavior)
- Returns full results when available (unchanged behavior)
"""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import HTTPException


@pytest.fixture
def mock_user():
    return {"id": "user-123", "email": "test@example.com"}


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def mock_service_supabase():
    return MagicMock()


class TestAnalysisResultsPending:

    @pytest.mark.asyncio
    async def test_returns_pending_when_case_exists_no_results(
        self, mock_user, mock_supabase, mock_service_supabase
    ):
        """Case ownership passes, no analysis_results rows → 200 with pending status."""
        from legal_portal.api.routes.analysis import get_analysis_results

        # Case exists
        case_chain = MagicMock()
        case_chain.select.return_value = case_chain
        case_chain.eq.return_value = case_chain
        case_chain.execute.return_value = MagicMock(data=[{"id": "case-001"}])

        # No analysis results
        results_chain = MagicMock()
        results_chain.select.return_value = results_chain
        results_chain.eq.return_value = results_chain
        results_chain.order.return_value = results_chain
        results_chain.limit.return_value = results_chain
        results_chain.execute.return_value = MagicMock(data=[])

        mock_supabase.table.side_effect = lambda name: (
            case_chain if name == "cases" else results_chain
        )

        result = await get_analysis_results(
            case_id="case-001",
            user=mock_user,
            supabase=mock_supabase,
            service_supabase=mock_service_supabase,
        )

        assert result["status"] == "pending"
        assert "message" in result

    @pytest.mark.asyncio
    async def test_returns_404_when_case_not_found(
        self, mock_user, mock_supabase, mock_service_supabase
    ):
        """No case match → 404 unchanged."""
        from legal_portal.api.routes.analysis import get_analysis_results

        case_chain = MagicMock()
        case_chain.select.return_value = case_chain
        case_chain.eq.return_value = case_chain
        case_chain.execute.return_value = MagicMock(data=[])

        mock_supabase.table.return_value = case_chain

        with pytest.raises(HTTPException) as exc_info:
            await get_analysis_results(
                case_id="nonexistent",
                user=mock_user,
                supabase=mock_supabase,
                service_supabase=mock_service_supabase,
            )

        assert exc_info.value.status_code == 404
        assert "Case not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_results_when_available(
        self, mock_user, mock_supabase, mock_service_supabase
    ):
        """Both queries return data → full results returned."""
        from legal_portal.api.routes.analysis import get_analysis_results

        case_chain = MagicMock()
        case_chain.select.return_value = case_chain
        case_chain.eq.return_value = case_chain
        case_chain.execute.return_value = MagicMock(data=[{"id": "case-001"}])

        results_chain = MagicMock()
        results_chain.select.return_value = results_chain
        results_chain.eq.return_value = results_chain
        results_chain.order.return_value = results_chain
        results_chain.limit.return_value = results_chain
        results_chain.execute.return_value = MagicMock(
            data=[
                {
                    "id": "analysis-001",
                    "case_id": "case-001",
                    "status": "completed",
                    "result": {"summary": "Test analysis"},
                    "created_at": "2026-03-04T00:00:00Z",
                    "error": None,
                }
            ]
        )

        mock_supabase.table.side_effect = lambda name: (
            case_chain if name == "cases" else results_chain
        )

        result = await get_analysis_results(
            case_id="case-001",
            user=mock_user,
            supabase=mock_supabase,
            service_supabase=mock_service_supabase,
        )

        assert result["status"] == "completed"
        assert result["analysis_id"] == "analysis-001"
        assert result["summary"] == "Test analysis"
