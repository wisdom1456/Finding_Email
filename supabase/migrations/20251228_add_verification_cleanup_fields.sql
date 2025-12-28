-- Add verification and cleanup fields to documents table
-- Supports the "Verification & Cleanup" workflow before analysis

ALTER TABLE public.documents
ADD COLUMN IF NOT EXISTS manual_text TEXT,
ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_flagged_as_junk BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS text_edited_at TIMESTAMPTZ;

-- Index for quick filtering of verified/unverified documents
CREATE INDEX IF NOT EXISTS idx_documents_is_verified ON public.documents(is_verified);
CREATE INDEX IF NOT EXISTS idx_documents_is_flagged_as_junk ON public.documents(is_flagged_as_junk);

-- Comment for documentation
COMMENT ON COLUMN public.documents.manual_text IS 'User-provided text correction, takes priority over extracted_text during analysis';
COMMENT ON COLUMN public.documents.is_verified IS 'Whether the user has reviewed and verified the extracted text';
COMMENT ON COLUMN public.documents.is_flagged_as_junk IS 'Whether the document is flagged as junk (instructions, blank forms) and should be skipped during analysis';
COMMENT ON COLUMN public.documents.text_edited_at IS 'Timestamp of last manual text edit';

