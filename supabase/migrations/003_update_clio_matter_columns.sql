-- Migration: Update Clio Matter Columns in Cases Table
-- Created: 2024-11-20
-- Description: Rename clio_metadata to clio_matter_data and add index

-- Rename column for clarity
ALTER TABLE cases RENAME COLUMN clio_metadata TO clio_matter_data;

-- Add index for faster lookups by Clio matter ID
CREATE INDEX IF NOT EXISTS idx_cases_clio_matter_id 
    ON cases(clio_matter_id) 
    WHERE clio_matter_id IS NOT NULL;

-- Update comment
COMMENT ON COLUMN cases.clio_matter_data IS 'Complete Clio matter data including matter details and import summary';

