-- Migration: Harden RLS on profiles and analysis_results
--
-- Fixes two privilege gaps reachable with the public anon key + a user JWT:
--
-- 1. profiles: the UPDATE policy only checked row ownership (USING), so an
--    authenticated user could set their own `approved` / `role` columns via
--    PostgREST and bypass the approval gate that guards all `cases` access.
--    RLS WITH CHECK cannot compare against the OLD row, so the correct fix is
--    column-level privileges: authenticated users may only write the
--    user-editable profile fields. The signup trigger (handle_new_user, a
--    SECURITY DEFINER function owned by postgres) and the service-role key
--    bypass RLS/privileges and are unaffected.
--
-- 2. analysis_results: the INSERT/UPDATE policies ("Service can ...") only
--    checked that the referenced case EXISTS, not that it belongs to the
--    caller — any authenticated user could insert or overwrite analysis rows
--    for any case id. Recreated scoped to case ownership (+ approval), same
--    join shape as the documents policies in 20260304000000. The worker and
--    monitor write with the service key (bypasses RLS) and keep full access.
--    The user-JWT write path in analysis start (analysis_core.py) only writes
--    rows for the caller's own case, so it continues to work.

-- =====================================================
-- PROFILES: column-level write privileges
-- =====================================================

-- Lock writes down to the user-editable columns. Enumerated against the
-- current schema: initial schema + 20241126 (approved, role) +
-- 20251122000000 (contact/firm/AI fields) + 20251224000000 (jurisdiction).
-- Excluded on purpose: id, email, approved, role, created_at, updated_at
-- (updated_at is maintained by the BEFORE UPDATE trigger, which is exempt
-- from column privilege checks).

REVOKE INSERT, UPDATE ON public.profiles FROM authenticated, anon;

GRANT UPDATE (
    full_name,
    avatar_url,
    phone,
    firm_name,
    firm_address,
    ai_preferences,
    bar_number,
    email_signature,
    default_demand_deadline,
    default_jurisdiction
) ON public.profiles TO authenticated;

-- The API lazily creates a missing profile with the user's JWT
-- (routes/profile.py), so authenticated INSERT stays allowed — but only for
-- the same safe columns plus identity. approved/role fall back to their
-- column defaults (false / 'user').
GRANT INSERT (
    id,
    email,
    full_name,
    avatar_url,
    phone,
    firm_name,
    firm_address,
    ai_preferences,
    bar_number,
    email_signature,
    default_demand_deadline,
    default_jurisdiction
) ON public.profiles TO authenticated;

-- Recreate the UPDATE policy with an explicit WITH CHECK so a user cannot
-- re-point a row at another id (defense in depth alongside the PK).
DROP POLICY IF EXISTS "Users can update own profile" ON profiles;
CREATE POLICY "Users can update own profile"
    ON profiles FOR UPDATE
    USING ((select auth.uid()) = id)
    WITH CHECK ((select auth.uid()) = id);

-- Drop the blanket INSERT policy from 20251217000000. It was added for the
-- signup trigger, but handle_new_user() is SECURITY DEFINER and owned by
-- postgres (table owner), so it bypasses RLS entirely and never needed a
-- policy. Leaving WITH CHECK (true) lets any role insert arbitrary rows.
-- "Users can insert own profile" (auth.uid() = id) remains for the API's
-- lazy-create path.
DROP POLICY IF EXISTS "Service can create profiles" ON profiles;

-- =====================================================
-- ANALYSIS_RESULTS: ownership-scoped writes
-- =====================================================

DROP POLICY IF EXISTS "Service can insert analysis results" ON analysis_results;
CREATE POLICY "Users can insert analysis results for own cases"
    ON analysis_results FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = analysis_results.case_id
            AND cases.user_id = (select auth.uid())
            AND profiles.approved = true
        )
    );

DROP POLICY IF EXISTS "Service can update analysis results" ON analysis_results;
CREATE POLICY "Users can update analysis results of own cases"
    ON analysis_results FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = analysis_results.case_id
            AND cases.user_id = (select auth.uid())
            AND profiles.approved = true
        )
    );
