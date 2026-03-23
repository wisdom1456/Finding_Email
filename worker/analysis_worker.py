#!/usr/bin/env python3
"""Railway analysis worker — durable job executor.

Long-lived process that polls analysis_jobs for pending work, runs the
analysis pipeline, and writes results to analysis_results.

Design invariants:
- analysis_jobs is the single source of truth for progress
- analysis_results stores only the final completed artifact
- This worker is the sole writer of analysis_results.status/result,
  cases.status, and analysis_jobs.status in the durable path
- Pipeline code returns ProcessingResult; it does not write to shared state

Usage:
    python -m worker.analysis_worker

Environment variables:
    SUPABASE_URL          - Supabase project URL
    SUPABASE_SERVICE_KEY  - Service role key (bypasses RLS)
    OPENAI_API_KEY        - OpenAI API key
    WORKER_POLL_INTERVAL  - Seconds between job polls (default: 5)
    WORKER_HEARTBEAT_INTERVAL - Seconds between heartbeats (default: 30)
    LLM_CONCURRENCY       - Max concurrent OpenAI calls (default: 4)
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

# Ensure src/ is on the path for legal_portal imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

os.environ.setdefault("LOG_LEVEL", "INFO")

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"
POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "5"))
HEARTBEAT_INTERVAL = int(os.getenv("WORKER_HEARTBEAT_INTERVAL", "30"))
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "4"))
RECONCILE_INTERVAL = 300  # 5 minutes
STALE_CLEANUP_INTERVAL = 300  # 5 minutes

# Retryable error patterns
RETRYABLE_PATTERNS = [
    "timeout", "rate_limit", "429", "503", "502",
    "connection reset", "econnreset", "connection refused",
]


def classify_error(e: Exception) -> str:
    """Classify an error as retryable, terminal, pipeline_failed, or multi_stage_failure."""
    error_str = str(e).lower()
    if any(p in error_str for p in RETRYABLE_PATTERNS):
        return "retryable"
    if "pipeline_failed" in error_str:
        return "pipeline_failed"
    if "multi_stage_missing" in error_str or "multi_stage_failure" in error_str:
        return "multi_stage_failure"
    return "terminal"


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class AnalysisWorker:
    """Durable analysis worker.

    Polls analysis_jobs for pending work via claim_analysis_job() RPC.
    Runs the analysis pipeline and writes results.
    """

    def __init__(self):
        self.supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
        self.running = True
        self.current_job_id: Optional[str] = None
        self.llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
        self._last_reconcile = time.monotonic()
        self._last_stale_cleanup = time.monotonic()

        # Graceful shutdown
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle_signal)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        logger.info(f"[WORKER:{WORKER_ID}] Received signal {signum}, shutting down gracefully...")
        self.running = False

    async def run(self) -> None:
        """Main worker loop."""
        logger.info(f"[WORKER:{WORKER_ID}] Starting | poll={POLL_INTERVAL}s heartbeat={HEARTBEAT_INTERVAL}s")

        while self.running:
            try:
                # Periodic maintenance
                await self._maybe_reconcile()
                await self._maybe_cleanup_stale()

                # Try to claim a job
                job = self._claim_job()
                if job:
                    await self._process_job(job)
                else:
                    await asyncio.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"[WORKER:{WORKER_ID}] Loop error: {e}")
                await asyncio.sleep(POLL_INTERVAL)

        logger.info(f"[WORKER:{WORKER_ID}] Stopped")

    def _claim_job(self) -> Optional[dict]:
        """Claim a job via stored procedure (atomic)."""
        try:
            result = self.supabase.rpc(
                "claim_analysis_job",
                {"p_worker_id": WORKER_ID}
            ).execute()
            if result.data:
                job = result.data[0]
                logger.info(
                    f"[JOB:{job['id'][:8]}] Claimed | "
                    f"case={job['case_id'][:8]} attempt={job['attempts']} "
                    f"docs={job.get('doc_count', '?')}"
                )
                return job
            return None
        except Exception as e:
            logger.error(f"[WORKER:{WORKER_ID}] Claim error: {e}")
            return None

    async def _process_job(self, job: dict) -> None:
        """Execute the analysis pipeline for a claimed job.

        This method owns ALL finalization writes:
        1. Validate result
        2. Write analysis_results.status/result
        3. Update cases.status
        4. Mark analysis_jobs.status = completed (last)
        """
        job_id = job["id"]
        case_id = job["case_id"]
        analysis_id = job["analysis_id"]
        self.current_job_id = job_id

        # Start heartbeat
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_id))
        job_start = time.time()

        try:
            # Import here to avoid circular imports at module level
            from worker.db_progress_manager import DBProgressManager
            from legal_portal.services.analysis.analysis_orchestrator import process_case_background

            pm = DBProgressManager(self.supabase, job_id)

            logger.info(f"[JOB:{job_id[:8]}] Starting pipeline | case={case_id[:8]}")

            # Run pipeline in durable mode — returns ProcessingResult,
            # does NOT write to analysis_results or cases
            result = await process_case_background(
                case_id=case_id,
                analysis_id=analysis_id,
                supabase=self.supabase,
                provider=job.get("provider", "openai"),
                progress_manager=pm,
                durable_mode=True,
            )

            elapsed = time.time() - job_start

            # --- Worker owns ALL finalization ---

            # 1. Validate result
            result_dict = result.model_dump(mode="json")
            pipeline_status = result_dict.get("status", "unknown")
            pipeline_errors = result_dict.get("errors") or []

            # Check if pipeline itself reported failure
            if pipeline_status == "failed":
                error_details = "; ".join(
                    e.get("error_message") or e.get("error", "?")
                    for e in pipeline_errors if isinstance(e, dict)
                )[:1500]
                raise ValueError(
                    f"[PIPELINE_FAILED] Pipeline returned status=failed. "
                    f"Errors: {error_details or 'none captured'}"
                )

            msr = result_dict.get("multi_stage_result")
            if not msr:
                # Extract the real error from pipeline artifacts or errors list
                artifacts = result_dict.get("artifacts") or {}
                real_error = artifacts.get("multi_stage_error", "")
                msa_errors = [e for e in pipeline_errors
                              if isinstance(e, dict) and e.get("stage") == "multi_stage_analysis"]
                if msa_errors:
                    real_error = real_error or msa_errors[0].get("error", "")

                error_msg = (
                    f"[MULTI_STAGE_MISSING] Pipeline status={pipeline_status} but "
                    f"multi_stage_result is absent.\n"
                    f"Root cause: {real_error[:1500]}" if real_error
                    else f"[MULTI_STAGE_MISSING] Pipeline status={pipeline_status}, "
                         f"multi_stage_result missing, no root cause captured. "
                         f"Pipeline errors: {pipeline_errors[:3]}"
                )
                raise ValueError(error_msg)

            doc_summaries = result_dict.get("document_summaries")
            if not doc_summaries:
                logger.warning(f"[JOB:{job_id[:8]}] document_summaries empty in result")

            result_size = len(json.dumps(result_dict))
            logger.info(
                f"[JOB:{job_id[:8]}] Pipeline complete | duration={elapsed:.0f}s "
                f"result_size={result_size} bytes"
            )

            # 2. Conditional finalization: only proceed if job is still 'running'.
            #    If the API cancelled the job while the pipeline was executing,
            #    the status will be 'cancelled' and we must NOT overwrite it.
            claim_resp = self.supabase.table("analysis_jobs").update({
                "status": "completed",
                "stage": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", job_id).eq("status", "running").execute()

            if not claim_resp.data:
                # Job was cancelled (or otherwise mutated) while pipeline ran.
                # Re-read to confirm, then handle accordingly.
                current = self.supabase.table("analysis_jobs").select(
                    "status"
                ).eq("id", job_id).execute()
                current_status = current.data[0]["status"] if current.data else "unknown"
                logger.info(
                    f"[JOB:{job_id[:8]}] Finalization skipped — job status is "
                    f"'{current_status}' (expected 'running'). "
                    f"Cancel wins; result discarded."
                )
                return  # Cancel wins — do not write to analysis_results or cases

            # 3. Write final result to analysis_results (single atomic update)
            self.supabase.table("analysis_results").update({
                "status": "completed",
                "result": result_dict,
                "completed_at": datetime.utcnow().isoformat(),
            }).eq("id", analysis_id).execute()

            # 4. Update case status
            self.supabase.table("cases").update({
                "status": "completed",
            }).eq("id", case_id).execute()

            logger.info(f"[JOB:{job_id[:8]}] Completed | duration={elapsed:.0f}s")

        except Exception as e:
            if "cancelled" in str(type(e).__name__).lower() or "cancelled" in str(e).lower():
                self._handle_cancel(job_id, analysis_id, case_id)
            elif classify_error(e) == "retryable" and job["attempts"] < job["max_attempts"]:
                self._handle_retry(job_id, job, e)
            else:
                self._handle_failure(job_id, analysis_id, case_id, e)
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            self.current_job_id = None

    def _handle_cancel(self, job_id: str, analysis_id: str, case_id: str) -> None:
        """Handle job cancellation.

        Worker is the sole writer of analysis_results and cases for running jobs.
        Sets cases.status='pending' (not 'cancelled') because only the analysis
        attempt is cancelled — the case itself remains retryable.
        """
        logger.info(f"[JOB:{job_id[:8]}] Cancelled")
        self._update_job(job_id, status="cancelled")
        self.supabase.table("analysis_results").update(
            {"status": "cancelled"}
        ).eq("id", analysis_id).execute()
        # 'pending' so user can retry — only the attempt is cancelled, not the case
        self.supabase.table("cases").update(
            {"status": "pending"}
        ).eq("id", case_id).execute()

    def _handle_retry(self, job_id: str, job: dict, error: Exception) -> None:
        """Return job to pending with exponential backoff."""
        backoff = min(30 * (2 ** (job["attempts"] - 1)), 300)
        next_retry = (datetime.utcnow() + timedelta(seconds=backoff)).isoformat()
        logger.warning(
            f"[JOB:{job_id[:8]}] Retrying | attempt={job['attempts']}/{job['max_attempts']} "
            f"backoff={backoff}s error={str(error)[:200]}"
        )
        self._update_job(job_id,
            status="pending",
            worker_id=None,
            error=str(error)[:1000],
            error_type="retryable",
            next_retry_at=next_retry,
        )

    def _handle_failure(self, job_id: str, analysis_id: str, case_id: str, error: Exception) -> None:
        """Mark job as permanently failed. Update related rows."""
        error_msg = str(error)[:1000]
        tb = traceback.format_exc()
        logger.error(f"[JOB:{job_id[:8]}] Failed | error={error_msg}")

        self._update_job(job_id,
            status="failed",
            stage="failed",
            error=error_msg,
            error_type="terminal",
        )
        self.supabase.table("analysis_results").update({
            "status": "error",
            "error": f"{error_msg}\n\n{tb}",
        }).eq("id", analysis_id).execute()
        self.supabase.table("cases").update({
            "status": "error",
        }).eq("id", case_id).execute()

    def _update_job(self, job_id: str, **fields: Any) -> None:
        """Update analysis_jobs fields."""
        fields["updated_at"] = datetime.utcnow().isoformat()
        try:
            self.supabase.table("analysis_jobs").update(fields).eq("id", job_id).execute()
        except Exception as e:
            logger.error(f"[JOB:{job_id[:8]}] Failed to update job: {e}")

    async def _heartbeat_loop(self, job_id: str) -> None:
        """Update heartbeat_at every HEARTBEAT_INTERVAL seconds."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                self.supabase.table("analysis_jobs").update({
                    "heartbeat_at": datetime.utcnow().isoformat(),
                }).eq("id", job_id).execute()
            except Exception as e:
                logger.warning(f"[JOB:{job_id[:8]}] Heartbeat write failed: {e}")

    # ---------------------------------------------------------------------------
    # Periodic maintenance
    # ---------------------------------------------------------------------------

    async def _maybe_reconcile(self) -> None:
        """Run reconciliation if interval elapsed."""
        now = time.monotonic()
        if now - self._last_reconcile < RECONCILE_INTERVAL:
            return
        self._last_reconcile = now
        try:
            result = self.supabase.rpc("reconcile_analysis_jobs").execute()
            if result.data:
                logger.info(f"[RECONCILE] Fixed {len(result.data)} mismatched rows")
        except Exception as e:
            logger.warning(f"[RECONCILE] Failed: {e}")

    async def _maybe_cleanup_stale(self) -> None:
        """Mark terminally stale jobs as failed."""
        now = time.monotonic()
        if now - self._last_stale_cleanup < STALE_CLEANUP_INTERVAL:
            return
        self._last_stale_cleanup = now
        try:
            cutoff = (datetime.utcnow() - timedelta(seconds=120)).isoformat()
            self.supabase.table("analysis_jobs").update({
                "status": "failed",
                "error": "Stale: no heartbeat for 120s, max attempts exceeded",
                "error_type": "stale_timeout",
            }).eq("status", "running") \
              .lt("heartbeat_at", cutoff) \
              .gte("attempts", 3) \
              .execute()
        except Exception as e:
            logger.warning(f"[STALE_CLEANUP] Failed: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the worker."""
    worker = AnalysisWorker()
    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
