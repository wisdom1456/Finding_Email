-- Add denormalized columns from document registry for fast querying/filtering.
-- These columns are kept in sync with metadata.registry by the application layer.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_type_label TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_type_confidence TEXT DEFAULT 'low';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signed_status TEXT DEFAULT 'unknown';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS signature_expected BOOLEAN DEFAULT FALSE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS system_summary TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS enrichment_stage TEXT DEFAULT 'none';

CREATE INDEX IF NOT EXISTS idx_documents_document_type_label ON documents(document_type_label);
CREATE INDEX IF NOT EXISTS idx_documents_signed_status ON documents(signed_status);
CREATE INDEX IF NOT EXISTS idx_documents_enrichment_stage ON documents(enrichment_stage);

-- Backfill existing documents from metadata where available.
-- Set signed_status from signature_detection or signature_verification.
UPDATE documents
SET signed_status = COALESCE(
    metadata->'signature_verification'->>'status',
    metadata->'signature_detection'->>'status',
    'unknown'
)
WHERE signed_status IS NULL OR signed_status = 'unknown';

-- Set enrichment_stage to 'migration' for docs that had no registry yet.
UPDATE documents
SET enrichment_stage = 'migration'
WHERE enrichment_stage = 'none'
  AND extracted_text IS NOT NULL;
