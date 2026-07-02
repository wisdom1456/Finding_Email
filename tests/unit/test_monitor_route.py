"""Unit tests for the worker health monitor route.

Pins the auth behavior, the zombie predicate (including the busy-worker veto),
the redeploy gating, and the cron-side reconcile call.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from legal_portal.api.routes import monitor

CRON_SECRET = "test-cron-secret"
AUTH = f"Bearer {CRON_SECRET}"


def _result(data=None, count=None):
    return SimpleNamespace(data=data, count=count)


class FakeQuery:
    """Chainable query stub returning a preset result on execute()."""

    def __init__(self, result):
        self._result = result

    def __getattr__(self, name):
        def chain(*args, **kwargs):
            return self

        return chain

    def execute(self):
        return self._result


class FakeSupabase:
    """Returns preset results for the monitor's queries in call order:
    1. stuck jobs, 2. pending count, 3. recent claims,
    4. fresh running heartbeat, 5. recent failed count.
    """

    def __init__(self, stuck=None, pending_count=0, recent_claims=0, fresh_running=0,
                 failed_count=0, reconcile_data=None):
        self._results = [
            _result(data=stuck or []),
            _result(count=pending_count),
            _result(count=recent_claims),
            _result(count=fresh_running),
            _result(count=failed_count),
        ]
        self._table_calls = 0
        self.reconcile_calls = 0
        self._reconcile_data = reconcile_data or []
        self.monitor_state = MagicMock()

    def table(self, name):
        if name == "monitor_state":
            return self.monitor_state
        result = self._results[min(self._table_calls, len(self._results) - 1)]
        self._table_calls += 1
        return FakeQuery(result)

    def rpc(self, name, *a, **k):
        assert name == "reconcile_analysis_jobs"
        self.reconcile_calls += 1
        return FakeQuery(_result(data=self._reconcile_data))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", CRON_SECRET)
    monkeypatch.delenv("RAILWAY_API_TOKEN", raising=False)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)


def _patch_sb(monkeypatch, sb):
    import legal_portal.api.dependencies as deps

    monkeypatch.setattr(deps, "get_supabase_client", lambda: sb)


class TestAuth:
    def test_missing_secret_fails_closed(self, monkeypatch):
        monkeypatch.delenv("CRON_SECRET", raising=False)
        with pytest.raises(HTTPException) as exc:
            monitor.check_worker_health(authorization=AUTH)
        assert exc.value.status_code == 500

    def test_wrong_bearer_rejected(self):
        with pytest.raises(HTTPException) as exc:
            monitor.check_worker_health(authorization="Bearer wrong")
        assert exc.value.status_code == 401

    def test_missing_header_rejected(self):
        with pytest.raises(HTTPException) as exc:
            monitor.check_worker_health(authorization="")
        assert exc.value.status_code == 401


class TestZombiePredicate:
    def test_healthy_no_pending(self, monkeypatch):
        sb = FakeSupabase(pending_count=0, recent_claims=0, fresh_running=0)
        _patch_sb(monkeypatch, sb)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert resp["status"] == "no_pending_jobs"
        assert resp["checks"]["worker_inactive"]["triggered"] is False

    def test_busy_worker_vetoes_zombie(self, monkeypatch):
        """Pending jobs + no recent claim, but a running job with a fresh
        heartbeat: the worker is alive grinding a long analysis. This exact
        shape used to false-positive and trigger a mid-job Railway redeploy."""
        sb = FakeSupabase(pending_count=2, recent_claims=0, fresh_running=1)
        _patch_sb(monkeypatch, sb)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert resp["checks"]["worker_inactive"]["triggered"] is False
        assert resp["checks"]["worker_inactive"]["has_fresh_running_heartbeat"] is True

    def test_true_zombie_detected(self, monkeypatch):
        sb = FakeSupabase(pending_count=2, recent_claims=0, fresh_running=0)
        _patch_sb(monkeypatch, sb)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert resp["checks"]["worker_inactive"]["triggered"] is True
        assert "WORKER_INACTIVE" in resp["alerts"]

    def test_recent_claim_not_zombie(self, monkeypatch):
        sb = FakeSupabase(pending_count=5, recent_claims=1, fresh_running=0)
        _patch_sb(monkeypatch, sb)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert resp["checks"]["worker_inactive"]["triggered"] is False


class TestRedeployGating:
    def test_stuck_jobs_alone_do_not_redeploy(self, monkeypatch):
        """STUCK_JOBS with a live worker means a deep queue, not a dead worker.
        Redeploying would kill in-flight work."""
        monkeypatch.setenv("RAILWAY_API_TOKEN", "token")
        stuck = [{"id": "1", "case_id": "c", "created_at": "2026-01-01T00:00:00+00:00"}]
        sb = FakeSupabase(stuck=stuck, pending_count=1, recent_claims=0, fresh_running=1)
        _patch_sb(monkeypatch, sb)

        redeploys = []
        monkeypatch.setattr(monitor, "_maybe_redeploy", lambda _sb: redeploys.append(1) or True)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert "STUCK_JOBS" in resp["alerts"]
        assert redeploys == []
        assert resp["recovery_triggered"] is False

    def test_zombie_triggers_redeploy(self, monkeypatch):
        monkeypatch.setenv("RAILWAY_API_TOKEN", "token")
        sb = FakeSupabase(pending_count=1, recent_claims=0, fresh_running=0)
        _patch_sb(monkeypatch, sb)

        monkeypatch.setattr(monitor, "_maybe_redeploy", lambda _sb: True)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert resp["recovery_triggered"] is True


class TestFailedSpike:
    def test_spike_triggers_alert(self, monkeypatch):
        sb = FakeSupabase(pending_count=0, failed_count=5)
        _patch_sb(monkeypatch, sb)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert resp["checks"]["failed_spike"]["triggered"] is True
        assert "FAILED_SPIKE" in resp["alerts"]
        # Failure spikes alert but never auto-redeploy
        assert resp["recovery_triggered"] is False

    def test_below_threshold_is_healthy(self, monkeypatch):
        sb = FakeSupabase(pending_count=0, failed_count=2)
        _patch_sb(monkeypatch, sb)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert resp["checks"]["failed_spike"]["triggered"] is False
        assert resp["status"] == "no_pending_jobs"


class TestReconcile:
    def test_reconcile_runs_every_invocation(self, monkeypatch):
        """Dead-worker cleanup must not depend on a live worker — the cron
        calls reconcile_analysis_jobs() itself."""
        sb = FakeSupabase(pending_count=0)
        _patch_sb(monkeypatch, sb)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert sb.reconcile_calls == 1
        assert resp["reconciled"] == 0

    def test_reconcile_failure_does_not_break_monitor(self, monkeypatch):
        sb = FakeSupabase(pending_count=0)

        def broken_rpc(name, *a, **k):
            raise RuntimeError("rpc unavailable")

        sb.rpc = broken_rpc
        _patch_sb(monkeypatch, sb)

        resp = monitor.check_worker_health(authorization=AUTH)
        assert resp["reconciled"] == -1
        assert resp["status"] == "no_pending_jobs"
