"""DB-backed progress manager for durable worker.

Writes progress ONLY to analysis_jobs.progress (the UI source of truth).
Does NOT write to analysis_results.progress — that table stores only the
final completed artifact, written once by the worker at finalization.

This is a drop-in replacement for ProgressManager. The worker passes it
to process_case_background, which calls publish_progress() at each stage
transition. The frontend polls GET /jobs/{id}/status to read this data.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# Phase → stage mapping for the frontend 6-stage UI
_PHASE_TO_STAGE = {
    "initialization": "preparing",
    "preparing": "preparing",
    "deferred_extraction": "preparing",
    "document_analysis": "summarization",
    "case_synthesis": "synthesis",
    "deadline_extraction": "synthesis",
    "fact_extraction": "fact_extraction",
    "legal_mapping": "issue_mapping",
    "issue_mapping": "issue_mapping",
    "deep_analysis": "deep_analysis",
    "gap_analysis": "gap_analysis",
    "finalizing": "finalizing",
    "completed": "completed",
    "error": "failed",
}


class DBProgressManager:
    """Drop-in replacement for ProgressManager that writes to analysis_jobs only.

    Invariants:
    - analysis_jobs.progress = lightweight UI payload (message, percent, stage)
    - analysis_jobs.checkpoint is NOT written here (worker handles that separately)
    - analysis_results is NOT touched (worker writes final result at completion)
    """

    def __init__(self, supabase: Any, job_id: str, *, min_write_interval: float = 3.0):
        self.supabase = supabase
        self.job_id = job_id
        self._min_interval = min_write_interval
        self._last_write: float = 0
        self._cancelled = False

    async def create_channel(self, channel_id: str) -> None:
        """No-op — no SSE channels in durable mode."""

    async def publish_progress(self, channel_id: str, **kwargs: Any) -> None:
        """Write progress to analysis_jobs. Check cancellation."""
        if self._check_cancelled():
            from legal_portal.core.analysis_state import AnalysisCancelledError
            raise AnalysisCancelledError("Job cancelled")

        now = time.monotonic()
        if now - self._last_write < self._min_interval:
            return  # Throttle

        self._last_write = now
        phase = kwargs.get("phase", "")
        stage = _PHASE_TO_STAGE.get(phase, phase)

        payload = {
            "message": kwargs.get("message", ""),
            "phase": phase,
            "percent": kwargs.get("percent", 0),
            "timestamp": datetime.utcnow().isoformat(),
        }
        if kwargs.get("stage"):
            payload["stage"] = kwargs["stage"]
        if kwargs.get("stats"):
            payload["stats"] = kwargs["stats"]

        try:
            self.supabase.table("analysis_jobs").update({
                "progress": payload,
                "stage": stage,
            }).eq("id", self.job_id).execute()
        except Exception as e:
            logger.warning(f"[WORKER] Failed to write progress for job {self.job_id[:8]}: {e}")

    async def publish_stage(self, channel_id: str, stage: dict) -> None:
        """Convenience: publish stage update."""
        await self.publish_progress(channel_id, stage=stage)

    async def publish_document(self, channel_id: str, document: dict) -> None:
        """No-op in durable mode — document-level progress not needed for polling."""

    async def publish_stats(self, channel_id: str, stats: dict) -> None:
        """Convenience: publish stats."""
        await self.publish_progress(channel_id, stats=stats)

    async def publish_token(self, channel_id: str, token: str, stream_id: str) -> None:
        """No-op — no streaming tokens in durable worker mode."""

    async def subscribe(self, channel_id: str) -> None:
        """No-op — no SSE subscriptions."""

    async def get_latest_status(self, channel_id: str) -> Optional[dict]:
        """No-op — frontend reads from analysis_jobs via polling."""
        return None

    async def cleanup_expired_channels(self, ttl_hours: float = 1.0) -> None:
        """No-op."""

    def _check_cancelled(self) -> bool:
        """Check if job was cancelled. Cached after first detection."""
        if self._cancelled:
            return True
        try:
            r = self.supabase.table("analysis_jobs").select("status").eq("id", self.job_id).execute()
            if r.data and r.data[0]["status"] == "cancelled":
                self._cancelled = True
                return True
        except Exception:
            pass  # Transient DB error — don't block pipeline
        return False
