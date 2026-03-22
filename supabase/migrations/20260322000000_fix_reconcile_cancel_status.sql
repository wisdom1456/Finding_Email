-- =============================================================================
-- Migration: 20260322000000_fix_reconcile_cancel_status.sql
--
-- Fix: reconcile_analysis_jobs() now sets cases.status='pending' (not
-- 'cancelled') when a job is cancelled.  Only the analysis attempt is
-- cancelled; the case itself remains retryable.
-- =============================================================================

CREATE OR REPLACE FUNCTION reconcile_analysis_jobs()
RETURNS TABLE(job_id UUID, fixed_table TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    -- Phase 1: Fix analysis_results where job is terminal but result is still active
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
    RETURNING j.id AS job_id, 'analysis_results'::TEXT AS fixed_table;

    -- Phase 2: Fix cases where job is terminal but case is still processing.
    -- cancelled → 'pending' (not 'cancelled'): only the attempt is cancelled,
    -- the case remains retryable.
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
      AND NOT EXISTS (
          SELECT 1 FROM analysis_jobs j2
          WHERE j2.case_id = c.id
            AND j2.status IN ('pending', 'running')
            AND j2.id != j.id
      )
    RETURNING j.id AS job_id, 'cases'::TEXT AS fixed_table;
END;
$$;

REVOKE ALL ON FUNCTION reconcile_analysis_jobs() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reconcile_analysis_jobs() TO service_role;
