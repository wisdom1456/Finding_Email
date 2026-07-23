-- =============================================================================
-- Migration: 20260723215844_fix_reconcile_resurrecting_stale_jobs.sql
--
-- Root cause (proven in prod 2026-07-23): analysis_results is ONE reused row
-- per case, and every job ever created for the case points at it via
-- analysis_id. reconcile_analysis_jobs() Phase 1 joined that row against ANY
-- terminal job in history, so the moment a case had a single cancelled/failed
-- job, every future run was killed: /start resets the row to 'pending', the
-- next reconcile pass (Vercel cron */5 + worker every 300s) matches an ancient
-- terminal job and flips the row back to 'cancelled', and the orchestrator's
-- _analysis_is_cancelled() check (reads analysis_results.status) aborts the
-- healthy pipeline. Empirical proof: a 'pending' row with NO job attached
-- flipped itself to 'cancelled' at the exact cron tick (21:50:40).
--
-- The non-unique join also copied an arbitrary old job's error onto the row
-- (PG UPDATE...FROM picks one match unpredictably) — the phantom
-- "Superseded by re-run" markers.
--
-- Fix: Phase 1 gains the guard Phase 2 always had — only the LATEST job for
-- the analysis row may propagate terminal state. The join is now unique, so
-- the error copy is deterministic too.
--
-- Also folds in 20260322000000 (cancelled -> cases 'pending', not
-- 'cancelled'), which was in the repo but had never been applied to prod —
-- the live function still had the 20260321 body.
-- =============================================================================

CREATE OR REPLACE FUNCTION reconcile_analysis_jobs()
RETURNS TABLE(job_id UUID, fixed_table TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    -- Phase 1: Fix analysis_results where the CURRENT (latest) job is terminal
    -- but the result row is still active. Historical terminal jobs must never
    -- touch the reused per-case row — only the run that owns it now.
    RETURN QUERY
    UPDATE analysis_results ar
    SET status = CASE
            WHEN j.status = 'failed' THEN 'error'
            WHEN j.status = 'cancelled' THEN 'cancelled'
            ELSE ar.status
        END,
        error = COALESCE(ar.error, j.error)
    FROM analysis_jobs j
    WHERE j.analysis_id = ar.id
      AND j.status IN ('failed', 'cancelled')
      AND ar.status IN ('pending', 'processing')
      AND j.id = (
          SELECT j3.id FROM analysis_jobs j3
          WHERE j3.analysis_id = ar.id
          ORDER BY j3.created_at DESC
          LIMIT 1
      )
    RETURNING j.id AS job_id, 'analysis_results'::TEXT AS fixed_table;

    -- Phase 2: Fix cases where the CURRENT (latest) job is terminal but the
    -- case is still processing. cancelled -> 'pending' (not 'cancelled'):
    -- only the attempt is cancelled, the case remains retryable.
    RETURN QUERY
    UPDATE cases c
    SET status = CASE
            WHEN j.status = 'failed' THEN 'error'
            WHEN j.status = 'cancelled' THEN 'pending'
            ELSE c.status
        END
    FROM analysis_jobs j
    WHERE j.case_id = c.id
      AND j.status IN ('failed', 'cancelled')
      AND c.status = 'processing'
      AND j.id = (
          SELECT j3.id FROM analysis_jobs j3
          WHERE j3.case_id = c.id
          ORDER BY j3.created_at DESC
          LIMIT 1
      )
      AND NOT EXISTS (
          SELECT 1 FROM analysis_jobs j2
          WHERE j2.case_id = c.id
            AND j2.status IN ('pending', 'running')
      )
    RETURNING j.id AS job_id, 'cases'::TEXT AS fixed_table;
END;
$$;

REVOKE ALL ON FUNCTION reconcile_analysis_jobs() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reconcile_analysis_jobs() TO service_role;
