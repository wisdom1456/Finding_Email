-- Drop the existing constraint
ALTER TABLE public.documents 
DROP CONSTRAINT IF EXISTS documents_status_check;

-- Map existing legacy status values to new values
UPDATE public.documents SET status = 'ready' WHERE status = 'processed';
UPDATE public.documents SET status = 'pending' WHERE status = 'uploaded';
UPDATE public.documents SET status = 'pending' WHERE status = 'processing';
UPDATE public.documents SET status = 'extraction_failed' WHERE status = 'error';

-- Add new constraint with all valid status values
ALTER TABLE public.documents
ADD CONSTRAINT documents_status_check 
CHECK (status IN ('ready', 'needs_review', 'extraction_failed', 'download_failed', 'corrupted', 'skipped', 'pending'));

-- Update default value
ALTER TABLE public.documents ALTER COLUMN status SET DEFAULT 'pending';

