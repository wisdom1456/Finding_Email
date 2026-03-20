-- =============================================================================
-- Migration: 20260321000000_add_analysis_jobs.sql
--
-- Durable Analysis System: Job table for Railway worker.
--
-- Design invariants:
--   analysis_jobs.progress   = lightweight UI status (frontend reads via polling)
--   analysis_jobs.checkpoint = resumable stage outputs (worker reads on retry)
--   analysis_results.result  = final completed artifact (written once by worker)
--
-- Surfaced statuses: pending, running, completed, failed, cancelled
-- worker_id, claimed_at, heartbeat_at are metadata only (not state).
--
-- Dependencies: initial_schema (uuid-ossp, update_updated_at_column, cases,
--               analysis_results)
-- =============================================================================


-- =============================================================================
-- Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    analysis_id UUID REFERENCES analysis_results(id) ON DELETE CASCADE,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),

    stage TEXT DEFAULT 'queued'
        CHECK (stage IN (
            'queued', 'preparing', 'summarization', 'synthesis',
            'fact_extraction', 'issue_mapping', 'deep_analysis',
            'gap_analysis', 'finalizing', 'completed', 'failed'
        )),

    -- Lightweight UI progress (message, percent, stage_metrics).
    -- Frontend reads this via GET /jobs/{id}/status.
    progress JSONB DEFAULT '{}',

    -- Resumable stage-complete structured outputs ONLY.
    -- Allowed keys: summarization, synthesis, fact_matrix, issue_map,
    --               last_completed_stage.
    -- Do NOT store: raw document text, raw prompts, append-only logs.
    checkpoint JSONB DEFAULT '{}',

    error TEXT,
    error_type TEXT,

    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_retry_at TIMESTAMPTZ,

    -- Worker metadata (observability only, not state)
    worker_id TEXT,
    heartbeat_at TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,

    provider TEXT DEFAULT 'openai',
    doc_count INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);


-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_pending
    ON analysis_jobs(created_at) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_heartbeat
    ON analysis_jobs(heartbeat_at) WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_case_id
    ON analysis_jobs(case_id);

-- One active job per case. UPDATE running->pending on the same row
-- changes the indexed value but not the row identity, so no conflict.
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_job_per_case
    ON analysis_jobs(case_id) WHERE status IN ('pending', 'running');


-- =============================================================================
-- Trigger
-- Safe for re-runs: DROP IF EXISTS then CREATE. The table always exists at
-- this point because CREATE TABLE IF NOT EXISTS runs first in this migration.
-- =============================================================================

DROP TRIGGER IF EXISTS update_analysis_jobs_updated_at ON analysis_jobs;
CREATE TRIGGER update_analysis_jobs_updated_at
    BEFORE UPDATE ON analysis_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- RLS
--
-- Only SELECT is granted to authenticated users (ownership-gated via cases).
-- No INSERT/UPDATE policies: only service_role writes to this table, and
-- service_role bypasses RLS entirely in Supabase.
-- =============================================================================

ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view jobs for own cases" ON analysis_jobs;
CREATE POLICY "Users can view jobs for own cases"
    ON analysis_jobs FOR SELECT
    USING (EXISTS (
        SELECT 1 FROM cases
        WHERE cases.id = analysis_jobs.case_id
          AND cases.user_id = auth.uid()
    ));


-- =============================================================================
-- RPC: claim_analysis_job
--
-- Atomically claims the next available job. Uses FOR UPDATE SKIP LOCKED
-- for safe concurrent access across multiple worker instances.
-- Transitions pending -> running in a single atomic step.
--
-- The UPDATE targets a single row by primary key (WHERE id = v_job.id),
-- so RETURNING * INTO v_job is guaranteed to return exactly one row.
--
-- Ordering rationale:
--   1. Stale recovery (prevents permanently stuck jobs)
--   2. Retries before fresh (honors work already invested)
--   3. FIFO by created_at (fair ordering -- prevents starvation of any job)
--   4. doc_count as tiebreaker only (same-timestamp tie-break; large jobs
--      cannot starve because created_at is the primary sort within each tier)
--
-- Callable only by service_role (REVOKE FROM PUBLIC below).
-- =============================================================================

CREATE OR REPLACE FUNCTION claim_analysis_job(p_worker_id TEXT)
RETURNS SETOF analysis_jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_job analysis_jobs;
BEGIN
    SELECT * INTO v_job
    FROM analysis_jobs
    WHERE
        (status = 'pending' AND (next_retry_at IS NULL OR next_retry_at <= NOW()))
        OR
        (status = 'running'
         AND heartbeat_at < NOW() - INTERVAL '120 seconds'
         AND attempts < max_attempts)
    ORDER BY
        CASE WHEN status = 'running' THEN 0 ELSE 1 END,
        CASE WHEN attempts > 0 THEN 0 ELSE 1 END,
        created_at ASC,
        COALESCE(doc_count, 0) ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED;

    IF v_job.id IS NULL THEN
        RETURN;
    END IF;

    UPDATE analysis_jobs SET
        status = 'running',
        worker_id = p_worker_id,
        heartbeat_at = NOW(),
        claimed_at = NOW(),
        started_at = COALESCE(started_at, NOW()),
        attempts = attempts + 1,
        updated_at = NOW()
    WHERE id = v_job.id
    RETURNING * INTO v_job;

    RETURN NEXT v_job;
END;
$$;

REVOKE ALL ON FUNCTION claim_analysis_job(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_analysis_job(TEXT) TO service_role;


-- =============================================================================
-- RPC: reconcile_analysis_jobs
--
-- Periodic cleanup. Fixes analysis_results and cases rows when a job reached
-- a terminal state but the worker crashed before propagating that state.
--
-- Two RETURN QUERY UPDATEs targeting different tables (analysis_results, cases).
-- Each appends rows to the combined result set (PG15 43.6.1.2: "results will
-- be concatenated"). No cross-table conflict: first UPDATE touches
-- analysis_results, second touches cases.
--
-- Status mapping: analysis_jobs.failed -> analysis_results.error (different enums)
--
-- Callable only by service_role (REVOKE FROM PUBLIC below).
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

    -- Phase 2: Fix cases where job is terminal but case is still processing
    RETURN QUERY
    UPDATE cases c
    SET status = CASE
            WHEN j.status = 'failed' THEN 'error'
            WHEN j.status = 'cancelled' THEN 'cancelled'
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


-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE analysis_jobs IS
    'Durable analysis job queue. Polled by Railway worker. Single source of truth for analysis progress.';

COMMENT ON COLUMN analysis_jobs.progress IS
    'Lightweight UI progress: message, percent, stage_metrics. Read by GET /jobs/{id}/status.';

COMMENT ON COLUMN analysis_jobs.checkpoint IS
    'Resumable stage outputs for retry. Keys: summarization, synthesis, fact_matrix, issue_map, last_completed_stage. No raw text/prompts.';
