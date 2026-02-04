-- Migration: Add Clio sync tracking to cases table
-- Created: 2026-02-04
-- Description: Adds columns to track last sync time and whether analysis needs update

-- Add sync tracking columns
ALTER TABLE cases ADD COLUMN IF NOT EXISTS clio_last_synced_at TIMESTAMPTZ;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS needs_reanalysis BOOLEAN DEFAULT FALSE;

-- Add index for filtering cases that need reanalysis
CREATE INDEX IF NOT EXISTS idx_cases_needs_reanalysis
    ON cases(needs_reanalysis)
    WHERE needs_reanalysis = TRUE;

-- Add comments for documentation
COMMENT ON COLUMN cases.clio_last_synced_at IS 'Timestamp of last successful Clio sync for this case';
COMMENT ON COLUMN cases.needs_reanalysis IS 'True when new documents added via sync and analysis has not been re-run';
