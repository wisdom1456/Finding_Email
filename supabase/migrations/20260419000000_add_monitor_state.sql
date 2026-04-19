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

-- Auto-update updated_at on every write (consistent with all other tables)
DROP TRIGGER IF EXISTS update_monitor_state_updated_at ON monitor_state;
CREATE TRIGGER update_monitor_state_updated_at
    BEFORE UPDATE ON monitor_state
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- No RLS: only accessed via service_role key

COMMENT ON TABLE monitor_state IS
    'Key-value store for monitor daemon state. Holds restart rate-limit timestamp (last_restart_at). Written exclusively by service_role.';
