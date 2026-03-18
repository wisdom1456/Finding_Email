-- Add stream_run_id column to analysis_results for streaming recovery isolation.
-- Each streaming run gets a unique ID so recovery never returns stale results
-- from a different run.
ALTER TABLE analysis_results ADD COLUMN stream_run_id UUID;

-- Partial unique index: only one row per stream_run_id (NULLs are ignored,
-- so existing rows without stream_run_id are unaffected).
CREATE UNIQUE INDEX idx_analysis_results_stream_run_id
  ON analysis_results (stream_run_id) WHERE stream_run_id IS NOT NULL;
