-- Update AI preferences defaults from legacy gpt-4o to modern models
-- Migration: 20260122_update_ai_preferences_defaults
--
-- This migration:
-- 1. Updates the column default for new users
-- 2. Updates existing users who still have the old gpt-4o defaults

-- Step 1: Update the column default for new profiles
-- Note: We need to drop and recreate the default since ALTER COLUMN SET DEFAULT
-- doesn't work well with JSONB defaults in all PostgreSQL versions

ALTER TABLE profiles 
ALTER COLUMN ai_preferences 
SET DEFAULT '{
  "document_analysis": "gpt-5-mini",
  "letter_generation": "gpt-5.2",
  "case_chat": "gpt-5-mini",
  "multi_stage_analysis": "gpt-5.2",
  "blacklisted_documents": [],
  "auto_skip_failed": false,
  "max_retry_attempts": 2,
  "chunk_max_tokens": 50000
}'::jsonb;

-- Step 2: Update existing profiles that have the old gpt-4o defaults
-- Only update if they haven't customized their preferences (still have all gpt-4o)
UPDATE profiles
SET ai_preferences = jsonb_build_object(
  'document_analysis', 'gpt-5-mini',
  'letter_generation', 'gpt-5.2',
  'case_chat', 'gpt-5-mini',
  'multi_stage_analysis', 'gpt-5.2',
  'blacklisted_documents', COALESCE(ai_preferences->'blacklisted_documents', '[]'::jsonb),
  'auto_skip_failed', COALESCE((ai_preferences->>'auto_skip_failed')::boolean, false),
  'max_retry_attempts', COALESCE((ai_preferences->>'max_retry_attempts')::int, 2),
  'chunk_max_tokens', COALESCE((ai_preferences->>'chunk_max_tokens')::int, 50000)
)
WHERE ai_preferences IS NOT NULL
  AND ai_preferences->>'document_analysis' = 'gpt-4o'
  AND ai_preferences->>'letter_generation' = 'gpt-4o'
  AND ai_preferences->>'case_chat' = 'gpt-4o'
  AND ai_preferences->>'multi_stage_analysis' = 'gpt-4o';

-- Step 3: For profiles with NULL ai_preferences, set the new defaults
UPDATE profiles
SET ai_preferences = '{
  "document_analysis": "gpt-5-mini",
  "letter_generation": "gpt-5.2",
  "case_chat": "gpt-5-mini",
  "multi_stage_analysis": "gpt-5.2",
  "blacklisted_documents": [],
  "auto_skip_failed": false,
  "max_retry_attempts": 2,
  "chunk_max_tokens": 50000
}'::jsonb
WHERE ai_preferences IS NULL;

-- Add comment documenting the change
COMMENT ON COLUMN profiles.ai_preferences IS 'User preferences for AI model selection. Updated 2026-01-22 to use gpt-5-mini/gpt-5.2 defaults instead of legacy gpt-4o.';
