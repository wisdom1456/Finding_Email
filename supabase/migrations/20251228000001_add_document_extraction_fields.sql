-- Add detailed extraction columns to documents table to support verification and "View Text" features
ALTER TABLE public.documents
ADD COLUMN IF NOT EXISTS extraction_method TEXT,
ADD COLUMN IF NOT EXISTS extraction_quality TEXT,
ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS page_count INTEGER,
ADD COLUMN IF NOT EXISTS ocr_provider TEXT,
ADD COLUMN IF NOT EXISTS extraction_error TEXT;

-- Index for extraction quality to help with auditing
CREATE INDEX IF NOT EXISTS idx_documents_extraction_quality ON public.documents(extraction_quality);

