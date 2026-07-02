-- Migrate firm return address + canonical firm name to the new Trinity HQ.
-- Address Migration, Wave 2 (registry ref: am-w2-finding-emails).
-- Palm Harbor (2706 US-19 ALT, Suite 213, FL 34683) -> Trinity
-- (1810 Wellness Lane, Suite A, Trinity, FL 34655), effective 2026-07-01.
--
-- Why a new migration (mirrors 20260122000000_update_ai_preferences_defaults):
-- the original 20251122000000 migration already ran on the live database with
-- the OLD Palm Harbor default, so both the column DEFAULT and the existing rows
-- it seeded still hold the old address. This migration fixes both, on any
-- database where 20251122 already applied.
--
-- Idempotent: the row UPDATEs are guarded by exact-match WHERE clauses, so a
-- second run matches zero rows. Customized profiles (e.g. the New Mexico office
-- address) do NOT match the guard and are left untouched.

-- Step 1: reset the column defaults for NEW profiles.
ALTER TABLE profiles
  ALTER COLUMN firm_address SET DEFAULT '1810 Wellness Lane
Suite A
Trinity, FL 34655';

ALTER TABLE profiles
  ALTER COLUMN firm_name SET DEFAULT 'Bernhardt Riley, Attorneys at Law, PLLC';

-- Step 2: migrate existing rows still carrying the exact old Palm Harbor default.
-- Exact-match guard preserves any customized firm_address (New Mexico office, etc.).
UPDATE profiles
SET firm_address = '1810 Wellness Lane
Suite A
Trinity, FL 34655'
WHERE firm_address = '2706 US-19 ALT
Suite 213
Palm Harbor, FL 34683';

-- Step 3: canonicalize the legacy short-form firm name (independent guard).
UPDATE profiles
SET firm_name = 'Bernhardt Riley, Attorneys at Law, PLLC'
WHERE firm_name = 'Bernhardt Riley Law Firm';

-- Document the change.
COMMENT ON COLUMN profiles.firm_address IS 'Multi-line firm address. Trinity HQ (1810 Wellness Lane, Suite A, Trinity, FL 34655) as of 2026-07-01 address migration.';
COMMENT ON COLUMN profiles.firm_name IS 'Law firm name. Canonicalized to "Bernhardt Riley, Attorneys at Law, PLLC" in the 2026-07-01 address migration.';
