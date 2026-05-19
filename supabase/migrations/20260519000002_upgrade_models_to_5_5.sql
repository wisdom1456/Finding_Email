-- =============================================================================
-- Migration: 20260519000002_upgrade_models_to_5_5.sql
--
-- Upgrade ai_preferences to current OpenAI flagships (May 2026).
--
--   gpt-5.5      — current flagship (1M context, released 2026-04-23)
--   gpt-5.4-mini — workhorse (400K context, released 2026-03-17)
--
-- Replaces both gpt-4o stragglers (which the 2026-01-22 migration missed
-- because users had partially customized fields) AND older gpt-5.x
-- values. Single sweep so every user is on a consistent set.
--
-- Custom selections — defined as anything outside the old default set —
-- are preserved. We only rewrite values in the legacy set:
--   gpt-4o, gpt-4o-mini, gpt-5, gpt-5-mini, gpt-5-nano,
--   gpt-5.2, gpt-5.4, gpt-5.4-pro
-- If a user has explicitly picked gpt-5.5 or another non-legacy value,
-- this migration leaves them alone.
-- =============================================================================


-- =============================================================================
-- Step 1: Update the column default for any future new profiles
-- =============================================================================

ALTER TABLE profiles
ALTER COLUMN ai_preferences
SET DEFAULT '{
  "document_analysis": "gpt-5.4-mini",
  "letter_generation": "gpt-5.5",
  "case_chat": "gpt-5.4-mini",
  "multi_stage_analysis": "gpt-5.5",
  "blacklisted_documents": [],
  "auto_skip_failed": false,
  "max_retry_attempts": 2,
  "chunk_max_tokens": 50000
}'::jsonb;


-- =============================================================================
-- Step 2: Sweep existing profiles. Per-key rewrite preserves any
-- non-legacy custom selections.
-- =============================================================================

UPDATE profiles
SET ai_preferences = jsonb_set(
    jsonb_set(
        jsonb_set(
            jsonb_set(
                COALESCE(ai_preferences, '{}'::jsonb),
                '{document_analysis}',
                to_jsonb(
                    CASE
                        WHEN ai_preferences->>'document_analysis' IN (
                            'gpt-4o','gpt-4o-mini','gpt-5','gpt-5-mini','gpt-5-nano',
                            'gpt-5.2','gpt-5.4','gpt-5.4-pro'
                        ) THEN 'gpt-5.4-mini'
                        ELSE COALESCE(ai_preferences->>'document_analysis', 'gpt-5.4-mini')
                    END
                )
            ),
            '{letter_generation}',
            to_jsonb(
                CASE
                    WHEN ai_preferences->>'letter_generation' IN (
                        'gpt-4o','gpt-4o-mini','gpt-5','gpt-5-mini','gpt-5-nano',
                        'gpt-5.2','gpt-5.4','gpt-5.4-pro'
                    ) THEN 'gpt-5.5'
                    ELSE COALESCE(ai_preferences->>'letter_generation', 'gpt-5.5')
                END
            )
        ),
        '{case_chat}',
        to_jsonb(
            CASE
                WHEN ai_preferences->>'case_chat' IN (
                    'gpt-4o','gpt-4o-mini','gpt-5','gpt-5-mini','gpt-5-nano',
                    'gpt-5.2','gpt-5.4','gpt-5.4-pro'
                ) THEN 'gpt-5.4-mini'
                ELSE COALESCE(ai_preferences->>'case_chat', 'gpt-5.4-mini')
            END
        )
    ),
    '{multi_stage_analysis}',
    to_jsonb(
        CASE
            WHEN ai_preferences->>'multi_stage_analysis' IN (
                'gpt-4o','gpt-4o-mini','gpt-5','gpt-5-mini','gpt-5-nano',
                'gpt-5.2','gpt-5.4','gpt-5.4-pro'
            ) THEN 'gpt-5.5'
            ELSE COALESCE(ai_preferences->>'multi_stage_analysis', 'gpt-5.5')
        END
    )
);


-- =============================================================================
-- Step 3: Sanity check via NOTICE — visible in psql output
-- =============================================================================

DO $$
DECLARE
    total_count int;
    upgraded_count int;
BEGIN
    SELECT COUNT(*) INTO total_count FROM profiles;
    SELECT COUNT(*) INTO upgraded_count FROM profiles
     WHERE ai_preferences->>'document_analysis' = 'gpt-5.4-mini'
       AND ai_preferences->>'letter_generation' = 'gpt-5.5'
       AND ai_preferences->>'case_chat' = 'gpt-5.4-mini'
       AND ai_preferences->>'multi_stage_analysis' = 'gpt-5.5';
    RAISE NOTICE 'profiles total=% upgraded=% (rows on the new default set)',
        total_count, upgraded_count;
END $$;
