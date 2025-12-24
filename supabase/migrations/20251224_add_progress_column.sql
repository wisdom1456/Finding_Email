-- Add progress column to analysis_results to support cross-instance polling on Vercel
ALTER TABLE public.analysis_results 
ADD COLUMN IF NOT EXISTS progress JSONB;

