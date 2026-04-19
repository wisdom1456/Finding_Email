-- supabase/migrations/20260419000000_add_monitor_state.sql
-- Lightweight key-value store for monitor state (e.g. restart rate limiting).
-- One row per key. Only service_role writes to this table.

CREATE TABLE IF NOT EXISTS monitor_state (
    key   TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed the restart rate-limit row with a NULL value (no restarts yet)
INSERT INTO monitor_state (key, value)
VALUES ('last_restart_at', NULL)
ON CONFLICT (key) DO NOTHING;

-- No RLS: only accessed via service_role key
