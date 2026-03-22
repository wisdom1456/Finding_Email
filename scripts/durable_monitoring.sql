-- =============================================================================
-- Durable Analysis: Production Monitoring Queries
--
-- Run against Supabase SQL editor or psql.
-- Each query is self-contained. Copy/paste the one you need.
-- =============================================================================


-- 1. PENDING TOO LONG (queued > 5 min without being claimed)
SELECT id, case_id, created_at, attempts,
       EXTRACT(EPOCH FROM (NOW() - created_at))::int AS pending_seconds
FROM analysis_jobs
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '5 minutes'
ORDER BY created_at ASC;


-- 2. RUNNING TOO LONG (active > 30 min)
SELECT id, case_id, worker_id, started_at, stage, attempts,
       EXTRACT(EPOCH FROM (NOW() - started_at))::int AS running_seconds,
       progress->>'message' AS last_message,
       progress->>'percent' AS percent
FROM analysis_jobs
WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '30 minutes'
ORDER BY started_at ASC;


-- 3. HEARTBEAT TOO OLD (running but no heartbeat > 90s — likely dead worker)
SELECT id, case_id, worker_id, heartbeat_at, stage, attempts,
       EXTRACT(EPOCH FROM (NOW() - heartbeat_at))::int AS heartbeat_age_seconds
FROM analysis_jobs
WHERE status = 'running'
  AND heartbeat_at < NOW() - INTERVAL '90 seconds'
ORDER BY heartbeat_at ASC;


-- 4. REPEATED RETRIES (jobs that have been retried 2+ times)
SELECT id, case_id, status, attempts, max_attempts,
       error_type, LEFT(error, 200) AS error_preview,
       created_at, updated_at
FROM analysis_jobs
WHERE attempts >= 2
ORDER BY updated_at DESC
LIMIT 20;


-- 5. FAILED JOBS BY CLASSIFICATION
SELECT error_type, COUNT(*) AS cnt,
       MIN(created_at) AS earliest,
       MAX(updated_at) AS latest
FROM analysis_jobs
WHERE status = 'failed'
GROUP BY error_type
ORDER BY cnt DESC;


-- 6. FAILED JOBS — RECENT DETAIL
SELECT id, case_id, error_type, attempts,
       LEFT(error, 300) AS error_preview,
       created_at, updated_at
FROM analysis_jobs
WHERE status = 'failed'
ORDER BY updated_at DESC
LIMIT 20;


-- 7. COMPLETED JOBS MISSING MSR (multi_stage_result)
--    These indicate a pipeline bug where the worker wrote 'completed'
--    but the result payload is incomplete.
SELECT aj.id AS job_id, aj.case_id, aj.completed_at,
       ar.id AS analysis_id, ar.status AS result_status,
       (ar.result IS NULL) AS result_null,
       (ar.result->>'multi_stage_result' IS NULL) AS msr_null
FROM analysis_jobs aj
JOIN analysis_results ar ON ar.id = aj.analysis_id
WHERE aj.status = 'completed'
  AND (ar.result IS NULL OR ar.result->>'multi_stage_result' IS NULL)
ORDER BY aj.completed_at DESC;


-- 8. DASHBOARD SUMMARY (one-row overview)
SELECT
    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
    COUNT(*) FILTER (WHERE status = 'running') AS running,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled,
    COUNT(*) AS total,
    MIN(created_at) FILTER (WHERE status = 'pending') AS oldest_pending,
    MAX(completed_at) FILTER (WHERE status = 'completed') AS latest_completed
FROM analysis_jobs;


-- 9. STATE CONSISTENCY CHECK
--    Finds rows where analysis_jobs and analysis_results disagree on terminal state.
SELECT aj.id AS job_id, aj.status AS job_status,
       ar.id AS analysis_id, ar.status AS result_status,
       c.id AS case_id, c.status AS case_status
FROM analysis_jobs aj
JOIN analysis_results ar ON ar.id = aj.analysis_id
JOIN cases c ON c.id = aj.case_id
WHERE aj.status IN ('completed', 'failed', 'cancelled')
  AND (
    (aj.status = 'completed' AND ar.status != 'completed')
    OR (aj.status = 'failed' AND ar.status NOT IN ('error', 'failed'))
    OR (aj.status = 'cancelled' AND ar.status != 'cancelled')
  )
ORDER BY aj.updated_at DESC;
