"""Unit tests for the durable worker's DBProgressManager.

Focus: the finalization-tail path (publish_finalizing) that fixes the
frozen-at-90% freeze — it must never raise on cancel, must bypass the write
throttle, and must guard its write on status='running'.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from worker.db_progress_manager import DBProgressManager, _PHASE_TO_STAGE


def _execute_result(data=None):
    return SimpleNamespace(data=data)


def _make(sb=None, **kw):
    return DBProgressManager(sb or MagicMock(), "j" * 36, **kw)


class TestPhaseMapping:
    def test_letter_structure_maps_to_finalizing(self):
        # Regression: unmapped 'letter_structure' was written verbatim as `stage`
        # and violated the analysis_jobs.stage CHECK constraint, silently
        # dropping the 80/90% progress writes.
        assert _PHASE_TO_STAGE["letter_structure"] == "finalizing"


class TestPublishFinalizing:
    @pytest.mark.asyncio
    async def test_write_is_guarded_on_running(self):
        sb = MagicMock()
        chain = sb.table.return_value.update.return_value.eq.return_value.eq
        chain.return_value.execute.return_value = _execute_result(data=[{"id": "x"}])

        pm = _make(sb)
        await pm.publish_finalizing("chan", "Saving analysis…", 98)

        payload = sb.table.return_value.update.call_args[0][0]
        assert payload["stage"] == "finalizing"
        assert payload["progress"]["percent"] == 98
        assert payload["progress"]["phase"] == "finalizing"
        # .eq("id", job_id).eq("status", "running")
        chain.assert_called_with("status", "running")

    @pytest.mark.asyncio
    async def test_does_not_raise_when_row_not_running(self):
        """A cancel/supersede flipped the job — write matches nothing.
        publish_finalizing must log and return, never raise."""
        sb = MagicMock()
        sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = _execute_result(data=[])

        pm = _make(sb)
        # Must not raise (AnalysisCancelledError or anything else)
        await pm.publish_finalizing("chan", "Saving…", 95)

    @pytest.mark.asyncio
    async def test_never_checks_cancellation(self):
        """Even a cancelled job must not abort finalization progress."""
        sb = MagicMock()
        pm = _make(sb)
        pm._cancelled = True  # would make publish_progress raise

        # Should complete without raising despite the cancelled flag.
        await pm.publish_finalizing("chan", "Saving…", 92)

    @pytest.mark.asyncio
    async def test_bypasses_throttle(self):
        sb = MagicMock()
        pm = _make(sb, min_write_interval=999.0)  # would throttle publish_progress

        await pm.publish_finalizing("chan", "a", 92)
        await pm.publish_finalizing("chan", "b", 95)

        # Both writes land despite the huge throttle interval.
        assert sb.table.return_value.update.call_count == 2


class TestIsCancelled:
    def test_true_when_status_cancelled(self):
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value = _execute_result(
            data=[{"status": "cancelled"}]
        )
        assert _make(sb).is_cancelled() is True

    def test_false_when_status_running(self):
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.execute.return_value = _execute_result(
            data=[{"status": "running"}]
        )
        assert _make(sb).is_cancelled() is False
