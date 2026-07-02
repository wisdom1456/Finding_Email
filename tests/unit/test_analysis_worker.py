"""Unit tests for the durable analysis worker's state-transition logic.

The worker is the single writer for analysis_jobs finalization; these tests
pin its claim/retry/failure/cancel behavior against a mocked Supabase client
(no live DB needed).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def worker(monkeypatch):
    """AnalysisWorker with a MagicMock Supabase client."""
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")

    import worker.analysis_worker as wmod

    mock_client = MagicMock()
    monkeypatch.setattr(wmod, "create_client", lambda *a, **k: mock_client)
    # Signal handlers can only be installed in the main thread; harmless here,
    # but avoid surprises if the test runner uses threads.
    monkeypatch.setattr(wmod.signal, "signal", lambda *a, **k: None)

    w = wmod.AnalysisWorker()
    w.supabase = mock_client
    return w


def _execute_result(data=None, count=None):
    return SimpleNamespace(data=data, count=count)


class TestClassifyError:
    def test_retryable_patterns(self):
        from worker.analysis_worker import classify_error

        for msg in ["Read timeout", "429 Too Many Requests", "connection reset by peer",
                    "Empty response from model", "HTTP 503"]:
            assert classify_error(Exception(msg)) == "retryable", msg

    def test_terminal_default(self):
        from worker.analysis_worker import classify_error

        assert classify_error(Exception("KeyError: 'parties'")) == "terminal"

    def test_pipeline_and_multistage(self):
        from worker.analysis_worker import classify_error

        assert classify_error(Exception("PIPELINE_FAILED: stage 2")) == "pipeline_failed"
        assert classify_error(Exception("[MULTI_STAGE_MISSING] absent")) == "multi_stage_failure"


class TestClaimJob:
    def test_claim_returns_job(self, worker):
        job = {"id": "a" * 36, "case_id": "b" * 36, "attempts": 1, "doc_count": 3}
        worker.supabase.rpc.return_value.execute.return_value = _execute_result(data=[job])

        assert worker._claim_job() == job
        worker.supabase.rpc.assert_called_once()
        assert worker.supabase.rpc.call_args[0][0] == "claim_analysis_job"

    def test_no_pending_returns_none(self, worker):
        worker.supabase.rpc.return_value.execute.return_value = _execute_result(data=[])
        assert worker._claim_job() is None

    def test_claim_error_returns_none(self, worker):
        worker.supabase.rpc.return_value.execute.side_effect = RuntimeError("connection refused")
        assert worker._claim_job() is None


class TestHandleRetry:
    def _fields(self, worker):
        return worker.supabase.table.return_value.update.call_args[0][0]

    def test_returns_job_to_pending_with_backoff(self, worker):
        job = {"id": "j" * 36, "attempts": 1, "max_attempts": 3}
        worker._handle_retry(job["id"], job, Exception("timeout"))

        fields = self._fields(worker)
        assert fields["status"] == "pending"
        assert fields["worker_id"] is None
        assert fields["error_type"] == "retryable"
        assert "next_retry_at" in fields

    def test_backoff_is_capped(self, worker):
        from datetime import datetime, timezone

        job = {"id": "j" * 36, "attempts": 10, "max_attempts": 12}
        before = datetime.now(timezone.utc)
        worker._handle_retry(job["id"], job, Exception("timeout"))

        fields = self._fields(worker)
        next_retry = datetime.fromisoformat(fields["next_retry_at"])
        delta = (next_retry - before).total_seconds()
        assert delta <= 305  # capped at 300s (+ small slack)


class TestHandleFailure:
    def test_marks_job_result_and_case_failed(self, worker):
        worker._handle_failure("j" * 36, "a" * 36, "c" * 36, Exception("KeyError"))

        tables = [c.args[0] for c in worker.supabase.table.call_args_list]
        assert "analysis_jobs" in tables
        assert "analysis_results" in tables
        assert "cases" in tables

        job_fields = worker.supabase.table.return_value.update.call_args_list[0][0][0]
        assert job_fields["status"] == "failed"
        assert job_fields["error_type"] == "terminal"


class TestHandleCancel:
    def test_result_update_is_status_guarded(self, worker):
        """analysis_results is only touched while still 'processing' — a re-run
        may already have reset the row, and cancel must not clobber it."""
        worker.supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.neq.return_value.execute.return_value = _execute_result(count=0)

        worker._handle_cancel("j" * 36, "a" * 36, "c" * 36)

        eq_calls = worker.supabase.table.return_value.update.return_value.eq.return_value.eq.call_args_list
        assert any(c.args == ("status", "processing") for c in eq_calls)

    def test_case_not_reset_when_other_job_active(self, worker):
        worker.supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.neq.return_value.execute.return_value = _execute_result(count=1)

        worker._handle_cancel("j" * 36, "a" * 36, "c" * 36)

        # cases table must not be updated when another pending/running job exists
        case_updates = [
            c for c in worker.supabase.table.call_args_list if c.args[0] == "cases"
        ]
        assert case_updates == []


class TestStaleCleanup:
    @pytest.mark.asyncio
    async def test_only_running_low_heartbeat_maxed_attempts(self, worker):
        worker._last_stale_cleanup = -10_000  # force interval elapsed

        await worker._maybe_cleanup_stale()

        update_fields = worker.supabase.table.return_value.update.call_args[0][0]
        assert update_fields["status"] == "failed"
        chain = worker.supabase.table.return_value.update.return_value
        chain.eq.assert_called_with("status", "running")
        chain.eq.return_value.lt.assert_called()
        chain.eq.return_value.lt.return_value.gte.assert_called_with("attempts", 3)

    @pytest.mark.asyncio
    async def test_cutoff_is_timezone_aware(self, worker):
        from datetime import datetime

        worker._last_stale_cleanup = -10_000
        await worker._maybe_cleanup_stale()

        chain = worker.supabase.table.return_value.update.return_value
        cutoff = chain.eq.return_value.lt.call_args[0][1]
        assert datetime.fromisoformat(cutoff).tzinfo is not None


class TestReconcile:
    @pytest.mark.asyncio
    async def test_reconcile_respects_interval(self, worker):
        import time as _time

        worker._last_reconcile = _time.monotonic()  # just ran
        await worker._maybe_reconcile()
        worker.supabase.rpc.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconcile_runs_when_due(self, worker):
        worker._last_reconcile = -10_000
        worker.supabase.rpc.return_value.execute.return_value = _execute_result(data=[])
        await worker._maybe_reconcile()
        worker.supabase.rpc.assert_called_once_with("reconcile_analysis_jobs")
