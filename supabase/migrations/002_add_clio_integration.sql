-- Migration: Add Clio Integration Support
-- Created: 2024-11-20
-- Description: Adds table for storing Clio OAuth tokens and integration settings

-- =====================================================
-- INTEGRATIONS_CLIO TABLE
-- =====================================================
-- Stores Clio OAuth tokens and connection state per user
CREATE TABLE IF NOT EXISTS integrations_clio (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    clio_user_id TEXT,
    clio_matter_id TEXT,
    token_type TEXT DEFAULT 'Bearer',
    scopes TEXT[] DEFAULT ARRAY['matters:read', 'communications:read', 'documents:read', 'notes:read', 'contacts:read'],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_integrations_clio_user_id ON integrations_clio(user_id);
CREATE INDEX IF NOT EXISTS idx_integrations_clio_expires_at ON integrations_clio(expires_at);

-- Enable RLS
ALTER TABLE integrations_clio ENABLE ROW LEVEL SECURITY;

-- Policies for integrations_clio
CREATE POLICY "Users can view own Clio integration"
    ON integrations_clio FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own Clio integration"
    ON integrations_clio FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own Clio integration"
    ON integrations_clio FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own Clio integration"
    ON integrations_clio FOR DELETE
    USING (auth.uid() = user_id);

-- Trigger for updated_at
CREATE TRIGGER update_integrations_clio_updated_at
    BEFORE UPDATE ON integrations_clio
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add optional Clio metadata to cases table
ALTER TABLE cases ADD COLUMN IF NOT EXISTS clio_matter_id TEXT;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS clio_metadata JSONB DEFAULT '{}';

-- Index for Clio matter lookups
CREATE INDEX IF NOT EXISTS idx_cases_clio_matter_id ON cases(clio_matter_id) WHERE clio_matter_id IS NOT NULL;

-- Comment for documentation
COMMENT ON TABLE integrations_clio IS 'Stores Clio OAuth credentials and integration state for each user';
COMMENT ON COLUMN integrations_clio.access_token IS 'Clio OAuth access token (should be encrypted at application layer)';
COMMENT ON COLUMN integrations_clio.refresh_token IS 'Clio OAuth refresh token (should be encrypted at application layer)';
COMMENT ON COLUMN integrations_clio.expires_at IS 'Timestamp when access token expires (typically 1 hour from creation)';
COMMENT ON COLUMN integrations_clio.clio_user_id IS 'User ID in Clio system for reference';
COMMENT ON COLUMN integrations_clio.clio_matter_id IS 'Currently selected/active Clio matter ID';

