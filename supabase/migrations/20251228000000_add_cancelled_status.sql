-- Migration: Add 'cancelled' to allowed status values for analysis_results and cases tables
-- This allows users to cancel in-progress analyses

-- Update the check constraint for analysis_results table
ALTER TABLE public.analysis_results 
DROP CONSTRAINT IF EXISTS analysis_results_status_check;

ALTER TABLE public.analysis_results
ADD CONSTRAINT analysis_results_status_check 
CHECK (status IN ('pending', 'processing', 'completed', 'error', 'cancelled'));

-- Update the check constraint for cases table  
ALTER TABLE public.cases
DROP CONSTRAINT IF EXISTS cases_status_check;

ALTER TABLE public.cases
ADD CONSTRAINT cases_status_check
CHECK (status IN ('pending', 'processing', 'completed', 'error', 'cancelled'));

-- Add comment for documentation
COMMENT ON CONSTRAINT analysis_results_status_check ON public.analysis_results IS 
'Valid statuses: pending (new), processing (in progress), completed (done), error (failed), cancelled (user cancelled)';

COMMENT ON CONSTRAINT cases_status_check ON public.cases IS 
'Valid statuses: pending (new), processing (in progress), completed (done), error (failed), cancelled (user cancelled)';

