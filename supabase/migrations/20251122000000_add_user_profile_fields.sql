-- Add user profile fields for attorney/firm information and AI preferences
-- Migration: 20251122000000_add_user_profile_fields

-- Add contact and firm information fields
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT '(727) 275-9575';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS firm_name TEXT DEFAULT 'Bernhardt Riley Law Firm';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS firm_address TEXT DEFAULT '2706 US-19 ALT
Suite 213
Palm Harbor, FL 34683';

-- Add AI model preferences (JSONB for flexibility)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS ai_preferences JSONB DEFAULT '{
  "document_analysis": "gpt-4o",
  "letter_generation": "gpt-4o",
  "case_chat": "gpt-4o",
  "multi_stage_analysis": "gpt-4o"
}'::jsonb;

-- Add optional professional fields for future use
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bar_number TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_signature TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS default_demand_deadline TEXT DEFAULT '14 days from receipt';

-- Create index on ai_preferences for faster queries
CREATE INDEX IF NOT EXISTS idx_profiles_ai_preferences ON profiles USING GIN (ai_preferences);

-- Add comment to document the schema
COMMENT ON COLUMN profiles.phone IS 'Attorney phone number';
COMMENT ON COLUMN profiles.firm_name IS 'Law firm name';
COMMENT ON COLUMN profiles.firm_address IS 'Multi-line firm address';
COMMENT ON COLUMN profiles.ai_preferences IS 'User preferences for AI model selection per operation type';
COMMENT ON COLUMN profiles.bar_number IS 'State bar number (optional)';
COMMENT ON COLUMN profiles.email_signature IS 'Custom email/letter signature (optional)';
COMMENT ON COLUMN profiles.default_demand_deadline IS 'Default deadline text for demand letters';

