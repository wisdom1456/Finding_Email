-- Phase 1: Analysis Stabilization — stale row cleanup + uniqueness constraint
--
-- 1. Expire stale processing/pending rows older than 30 minutes
-- 2. Add unique partial index to prevent concurrent analyses per case

-- Expire stale processing rows (>30 min old)
UPDATE analysis_results
SET status = 'error', error = 'Expired: stuck in processing'
WHERE status IN ('pending', 'processing')
AND created_at < NOW() - INTERVAL '30 minutes';

-- Prevent multiple active analyses per case
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_analysis_per_case
ON analysis_results (case_id)
WHERE status IN ('pending', 'processing');
