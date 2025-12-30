-- Add 'duplicate' status for duplicate document handling during Clio imports
-- This allows documents to be marked as duplicates and excluded from analysis by default

-- Drop the existing constraint
ALTER TABLE public.documents 
DROP CONSTRAINT IF EXISTS documents_status_check;

-- Add new constraint with 'duplicate' status included
ALTER TABLE public.documents
ADD CONSTRAINT documents_status_check 
CHECK (status IN ('ready', 'needs_review', 'extraction_failed', 'download_failed', 'corrupted', 'skipped', 'pending', 'duplicate', 'download_timeout'));

COMMENT ON CONSTRAINT documents_status_check ON public.documents IS 
'Valid document statuses: ready (processed successfully), needs_review (low quality extraction), extraction_failed, download_failed, corrupted, skipped, pending, duplicate (detected as duplicate file), download_timeout (Clio download exceeded time limit)';

