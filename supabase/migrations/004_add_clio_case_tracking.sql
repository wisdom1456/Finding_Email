-- Migration: Add Clio case tracking
-- Created: 2025-11-20
-- Description: Add flag to track if case was created via Clio matter selection

-- Add flag to track if case was created via Clio
ALTER TABLE cases ADD COLUMN IF NOT EXISTS created_via_clio BOOLEAN DEFAULT FALSE;

-- Add index for filtering Clio-created cases
CREATE INDEX IF NOT EXISTS idx_cases_created_via_clio 
    ON cases(created_via_clio) 
    WHERE created_via_clio = TRUE;

-- Add comment for documentation
COMMENT ON COLUMN cases.created_via_clio IS 'True if case was created directly from Clio matter selection (not manually created then linked)';

