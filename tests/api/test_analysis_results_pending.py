"""Tests for analysis results endpoint returning pending instead of 404.

Verifies:
- Returns 200 with pending status when case exists but no results yet
- Returns 404 when case not found (unchanged behavior)
- Returns full results when available (unchanged behavior)
"""

from unittest.mock import MagicMock

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


class TestFetchGapIntakeContent:
    """Test _fetch_gap_intake_content uses result_payload instead of intakes table."""

    def test_fetch_gap_intake_uses_result_payload(self):
        """Should return intake_content from result_payload without querying Supabase."""
        from legal_portal.api.routes.analysis import _fetch_gap_intake_content

        mock_supabase = MagicMock()
        result_payload = {
            "intake_content": "Client intake details here",
            "streaming_analysis": "Streaming fallback text",
        }

        result = _fetch_gap_intake_content(mock_supabase, "case-001", result_payload)

        assert result == "Client intake details here"
        # Should NOT query Supabase at all
        mock_supabase.table.assert_not_called()

    def test_fetch_gap_intake_falls_back_to_streaming(self):
        """No intake_content key → falls back to streaming_analysis."""
        from legal_portal.api.routes.analysis import _fetch_gap_intake_content

        mock_supabase = MagicMock()
        result_payload = {
            "streaming_analysis": "Streaming summary of case analysis",
        }

        result = _fetch_gap_intake_content(mock_supabase, "case-001", result_payload)

        assert result == "Streaming summary of case analysis"
        mock_supabase.table.assert_not_called()

    def test_fetch_gap_intake_empty_payload(self):
        """Empty result_payload → returns empty string."""
        from legal_portal.api.routes.analysis import _fetch_gap_intake_content

        mock_supabase = MagicMock()
        result = _fetch_gap_intake_content(mock_supabase, "case-001", {})

        assert result == ""
        mock_supabase.table.assert_not_called()

    def test_fetch_gap_intake_truncates_streaming(self):
        """streaming_analysis should be truncated to 5000 chars."""
        from legal_portal.api.routes.analysis import _fetch_gap_intake_content

        mock_supabase = MagicMock()
        long_text = "x" * 10000
        result_payload = {"streaming_analysis": long_text}

        result = _fetch_gap_intake_content(mock_supabase, "case-001", result_payload)

        assert len(result) == 5000
