-- Migration: Add import_progress column to cases table
-- Created: 2025-12-30
-- Description: Stores Clio import progress for cross-instance polling on Vercel serverless

-- Add import_progress column to store progress data by import_id
ALTER TABLE public.cases 
ADD COLUMN IF NOT EXISTS import_progress JSONB;

-- Add comment for documentation
COMMENT ON COLUMN cases.import_progress IS 'JSONB storage for Clio import progress tracking, supports cross-instance polling on Vercel serverless';

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_cases_import_progress_gin 
    ON cases USING gin (import_progress);

