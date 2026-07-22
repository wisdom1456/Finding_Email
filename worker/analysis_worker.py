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
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Ensure src/ is on the path for legal_portal imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

os.environ.setdefault("LOG_LEVEL", "INFO")

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, ClientOptions

from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.structured_logger import set_job_context

logger = get_module_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"
POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "5"))
HEARTBEAT_INTERVAL = int(os.getenv("WORKER_HEARTBEAT_INTERVAL", "30"))
RECONCILE_INTERVAL = 300  # 5 minutes
STALE_CLEANUP_INTERVAL = 300  # 5 minutes

# Retryable error patterns. "empty response" covers gpt-5.5 reasoning-loop
# failures where the model returns finish_reason=None with no completion;
# the call-site has a model fallback chain, but a worker-level retry gives
# a fresh attempt across the whole stage in case of intermittent triggers.
RETRYABLE_PATTERNS = [
    "timeout", "rate_limit", "429", "503", "502",
    "connection reset", "econnreset", "connection refused",
    "empty response",
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
            options=ClientOptions(postgrest_client_timeout=30),
        )
        self.running = True
        self.current_job_id: Optional[str] = None
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

        # Bind job/case ids into the structured-logging context so every log
        # line from the pipeline carries them (traceable without timestamps).
        set_job_context(job_id=job_id, case_id=case_id)

        # Start heartbeat
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_id))
        job_start = time.time()

        try:
            # Import here to avoid circular imports at module level
            from worker.db_progress_manager import DBProgressManager
            from legal_portal.services.analysis.analysis_orchestrator import process_case_background

            pm = DBProgressManager(self.supabase, job_id)

            # --- Checkpoint callback (monotonic stage writes) ---
            # Stage ordering ensures last_completed_stage never moves backward,
            # even if a stale/delayed callback fires out of order.
            _STAGE_RANK = {
                "summarization": 1,
                "synthesis": 2,
                "fact_matrix": 3,
                "issue_map": 4,
                "deep_analysis": 5,
            }

            async def _save_checkpoint(stage: str, data: dict) -> None:
                """Persist checkpoint after a stage completes.

                Writes are monotonic: last_completed_stage only advances forward.
                Best-effort — failure is logged but does not block the pipeline.
                """
                try:
                    current = self.supabase.table("analysis_jobs").select(
                        "checkpoint"
                    ).eq("id", job_id).single().execute()
                    cp = (current.data or {}).get("checkpoint") or {}

                    # Monotonic guard: never let last_completed_stage go backward
                    current_rank = _STAGE_RANK.get(cp.get("last_completed_stage", ""), 0)
                    new_rank = _STAGE_RANK.get(stage, 0)
                    if new_rank < current_rank:
                        logger.warning(
                            f"[JOB:{job_id[:8]}] [CHECKPOINT:SKIP] "
                            f"stage={stage} (rank={new_rank}) < current "
                            f"{cp.get('last_completed_stage')} (rank={current_rank}) — skipping"
                        )
                        return

                    cp[stage] = data
                    cp["last_completed_stage"] = stage
                    self.supabase.table("analysis_jobs").update({
                        "checkpoint": cp,
                    }).eq("id", job_id).execute()
                    logger.info(f"[JOB:{job_id[:8]}] [CHECKPOINT:SAVE] stage={stage}")
                except Exception as e:
                    logger.warning(
                        f"[JOB:{job_id[:8]}] [CHECKPOINT:SAVE] "
                        f"Failed to write checkpoint for {stage}: {e}"
                    )

            existing_checkpoint = job.get("checkpoint") or {}
            if existing_checkpoint.get("last_completed_stage"):
                logger.info(
                    f"[JOB:{job_id[:8]}] Resuming with checkpoint | "
                    f"last_completed_stage={existing_checkpoint['last_completed_stage']}"
                )

            # Transition analysis_results pending → processing.
            # Guard: only update if still pending (prevents reviving cancelled rows).
            self.supabase.table("analysis_results").update({
                "status": "processing",
            }).eq("id", analysis_id).eq("status", "pending").execute()

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
                checkpoint=existing_checkpoint,
                checkpoint_callback=_save_checkpoint,
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
                "progress": {"message": "Analysis complete!", "percent": 100},
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", job_id).eq("status", "running").execute()

            if not claim_resp.data:
                # Job was cancelled/superseded while the pipeline ran.
                # Re-read status + error to log which one won (observability:
                # every terminal outcome must name its cause — no silent skips).
                current = self.supabase.table("analysis_jobs").select(
                    "status, error"
                ).eq("id", job_id).execute()
                row = current.data[0] if current.data else {}
                current_status = row.get("status", "unknown")
                if (row.get("error") or "") == "Superseded by re-run":
                    logger.info(
                        f"[JOB:{job_id[:8]}] [FINALIZE] superseded by newer run "
                        f"(status='{current_status}') — result discarded; new run owns the case"
                    )
                else:
                    logger.info(
                        f"[JOB:{job_id[:8]}] [FINALIZE] user-cancelled "
                        f"(status='{current_status}') — result discarded"
                    )
                return  # Cancel wins — do not write to analysis_results or cases

            # 3. Write final result to analysis_results.
            #    Guard on status='processing': a supersede that landed between
            #    the CAS above and here reset the (shared, per-case) row to
            #    'pending' for the NEW run. Writing unconditionally would
            #    clobber the new run's row with this stale result.
            res_resp = self.supabase.table("analysis_results").update({
                "status": "completed",
                "result": result_dict,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", analysis_id).eq("status", "processing").execute()
            if not res_resp.data:
                logger.warning(
                    f"[JOB:{job_id[:8]}] [FINALIZE] analysis_results was not 'processing' "
                    f"at finalization — result NOT written (a re-run reset the row). "
                    f"Job marked completed; the newer run owns the case result."
                )

            # 4. Update case status
            self.supabase.table("cases").update({
                "status": "completed",
            }).eq("id", case_id).execute()

            # 5. Clear checkpoint — only after result persistence succeeded.
            #    This prevents stale checkpoint data from being read if the
            #    same case is re-analyzed later.
            try:
                self.supabase.table("analysis_jobs").update({
                    "checkpoint": {},
                }).eq("id", job_id).execute()
            except Exception as e:
                logger.warning(f"[JOB:{job_id[:8]}] Failed to clear checkpoint: {e}")

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
            set_job_context()  # clear job/case ids from the logging context

    def _handle_cancel(self, job_id: str, analysis_id: str, case_id: str) -> None:
        """Handle job cancellation.

        Two distinct causes, handled differently:
        - Supersede (re-run): the API already reset analysis_results to 'pending'
          and inserted a NEW job that owns the case. This old worker must touch
          NOTHING on analysis_results/cases — doing so races the new run and can
          flip the *new* run's row to 'cancelled', which is the self-cancel loop
          that caused the original bug.
        - User cancel: only update analysis_results if still 'processing' (this
          job's run), and only reset the case if no other active job exists.
        """
        superseded = False
        try:
            r = self.supabase.table("analysis_jobs").select(
                "error"
            ).eq("id", job_id).execute()
            if r.data and (r.data[0].get("error") or "") == "Superseded by re-run":
                superseded = True
        except Exception:
            pass  # Transient read error — fall through to the safe user-cancel path

        self._update_job(job_id, status="cancelled")

        if superseded:
            logger.info(
                f"[JOB:{job_id[:8]}] [FINALIZE] superseded by re-run — "
                f"leaving analysis_results/cases to the new run"
            )
            return

        logger.info(f"[JOB:{job_id[:8]}] [FINALIZE] user-cancelled")
        self.supabase.table("analysis_results").update(
            {"status": "cancelled"}
        ).eq("id", analysis_id).eq("status", "processing").execute()
        # Only reset case if no other active job exists (prevents clobbering re-runs)
        other_active = self.supabase.table("analysis_jobs").select(
            "id", count="exact"
        ).eq("case_id", case_id).in_(
            "status", ["pending", "running"]
        ).neq("id", job_id).execute()
        if not other_active.count:
            self.supabase.table("cases").update(
                {"status": "pending"}
            ).eq("id", case_id).execute()

    def _handle_retry(self, job_id: str, job: dict, error: Exception) -> None:
        """Return job to pending with exponential backoff."""
        backoff = min(30 * (2 ** (job["attempts"] - 1)), 300)
        next_retry = (datetime.now(timezone.utc) + timedelta(seconds=backoff)).isoformat()
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
        # Guard on 'processing': a re-run may have reset this shared row to
        # 'pending' for a new run — don't overwrite the new run with this error.
        self.supabase.table("analysis_results").update({
            "status": "error",
            "error": f"{error_msg}\n\n{tb}",
        }).eq("id", analysis_id).eq("status", "processing").execute()
        # Only mark the case errored if no other active job exists for it
        # (a re-run that may yet succeed must not be masked by this failure).
        other_active = self.supabase.table("analysis_jobs").select(
            "id", count="exact"
        ).eq("case_id", case_id).in_(
            "status", ["pending", "running"]
        ).neq("id", job_id).execute()
        if not other_active.count:
            self.supabase.table("cases").update({
                "status": "error",
            }).eq("id", case_id).execute()

    def _update_job(self, job_id: str, **fields: Any) -> None:
        """Update analysis_jobs fields."""
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
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
                    "heartbeat_at": datetime.now(timezone.utc).isoformat(),
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
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
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
    from legal_portal.utils.error_tracking import init_error_tracking

    init_error_tracking("worker")
    worker = AnalysisWorker()
    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
