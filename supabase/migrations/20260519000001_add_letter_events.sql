-- =============================================================================
-- Migration: 20260519000001_add_letter_events.sql
--
-- One row per letter-generation REQUEST (not per analysis). Captures
-- attempts that didn't make it into analysis_results.generated_letters
-- (failed mid-stream, regenerated, etc.) so operators can answer
-- "did the user actually get a letter?" — a question
-- analysis_results.generated_letters alone can't answer because it's
-- overwritten on each regeneration and never records failed attempts.
--
-- Dependencies: profiles, cases, analysis_results.
-- =============================================================================


CREATE TABLE IF NOT EXISTS letter_generation_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    case_id UUID REFERENCES cases(id) ON DELETE CASCADE NOT NULL,
    analysis_id UUID REFERENCES analysis_results(id) ON DELETE SET NULL,

    letter_type TEXT NOT NULL
        CHECK (letter_type IN (
            'findings',
            'demand',
            'recommendation_proceed',
            'recommendation_decline',
            'recommendation_request_documents',
            'recommendation_settlement_advisory'
        )),

    -- For named-recipient demand letters, e.g. 'demand_michael_hero'
    letter_key TEXT,

    status TEXT NOT NULL DEFAULT 'requested'
        CHECK (status IN ('requested', 'completed', 'failed')),

    -- Whole quality_report_v2 dict for forensic; NULL when not measured
    qa_summary JSONB,
    -- Top-level pass/fail roll-up. NULL = not applicable, true = clean,
    -- false = at least one quality check failed
    qa_passed BOOLEAN,

    error TEXT,
    duration_ms INTEGER,

    requested_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);


-- =============================================================================
-- Indexes — operator queries are: by user (recent activity), by case
-- (history for one matter), or by recency (which letters just failed?)
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_letter_events_user_id
    ON letter_generation_events(user_id);

CREATE INDEX IF NOT EXISTS idx_letter_events_case_id
    ON letter_generation_events(case_id);

CREATE INDEX IF NOT EXISTS idx_letter_events_requested_at
    ON letter_generation_events(requested_at DESC);

-- Recent failures — partial index, common admin query
CREATE INDEX IF NOT EXISTS idx_letter_events_recent_failures
    ON letter_generation_events(requested_at DESC)
    WHERE status = 'failed';


-- =============================================================================
-- RLS — users can SELECT their own events; service_role bypasses for writes
-- =============================================================================

ALTER TABLE letter_generation_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own letter events" ON letter_generation_events;
CREATE POLICY "Users can view own letter events"
    ON letter_generation_events FOR SELECT
    USING (auth.uid() = user_id);


-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE letter_generation_events IS
    'One row per letter-generation request. Captures attempts that did '
    'not make it into analysis_results.generated_letters (failed, regenerated, '
    'overwritten). Written exclusively by service_role from letter_routes.py.';

COMMENT ON COLUMN letter_generation_events.qa_passed IS
    'True = all measurable QA checks passed; false = at least one failed; '
    'NULL = QA did not run (failure before QA, or wrong letter type).';

COMMENT ON COLUMN letter_generation_events.letter_key IS
    'For named-recipient demand letters, the key under generated_letters '
    '(e.g. demand_michael_hero). NULL for findings.';
