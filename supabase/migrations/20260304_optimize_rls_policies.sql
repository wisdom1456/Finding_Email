-- Migration: Optimize RLS policies for query performance
-- Fixes Supabase lint: auth_rls_initplan
-- Changes auth.uid() -> (select auth.uid()) so the value is computed once per
-- query instead of re-evaluated for every row.
-- Also fixes: function_search_path_mutable for update_updated_at_column

-- =====================================================
-- PROFILES TABLE
-- =====================================================

DROP POLICY IF EXISTS "Users can view own profile" ON profiles;
CREATE POLICY "Users can view own profile"
    ON profiles FOR SELECT
    USING ((select auth.uid()) = id);

DROP POLICY IF EXISTS "Users can update own profile" ON profiles;
CREATE POLICY "Users can update own profile"
    ON profiles FOR UPDATE
    USING ((select auth.uid()) = id);

DROP POLICY IF EXISTS "Users can insert own profile" ON profiles;
CREATE POLICY "Users can insert own profile"
    ON profiles FOR INSERT
    WITH CHECK ((select auth.uid()) = id);

-- =====================================================
-- CASES TABLE (with approval check)
-- =====================================================

DROP POLICY IF EXISTS "Approved users can view own cases" ON cases;
CREATE POLICY "Approved users can view own cases"
    ON cases FOR SELECT
    USING (
        (select auth.uid()) = user_id
        AND EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = (select auth.uid())
            AND profiles.approved = true
        )
    );

DROP POLICY IF EXISTS "Approved users can create own cases" ON cases;
CREATE POLICY "Approved users can create own cases"
    ON cases FOR INSERT
    WITH CHECK (
        (select auth.uid()) = user_id
        AND EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = (select auth.uid())
            AND profiles.approved = true
        )
    );

DROP POLICY IF EXISTS "Approved users can update own cases" ON cases;
CREATE POLICY "Approved users can update own cases"
    ON cases FOR UPDATE
    USING (
        (select auth.uid()) = user_id
        AND EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = (select auth.uid())
            AND profiles.approved = true
        )
    );

DROP POLICY IF EXISTS "Approved users can delete own cases" ON cases;
CREATE POLICY "Approved users can delete own cases"
    ON cases FOR DELETE
    USING (
        (select auth.uid()) = user_id
        AND EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = (select auth.uid())
            AND profiles.approved = true
        )
    );

-- =====================================================
-- DOCUMENTS TABLE (with approval check via cases join)
-- =====================================================

DROP POLICY IF EXISTS "Approved users can view documents of own cases" ON documents;
CREATE POLICY "Approved users can view documents of own cases"
    ON documents FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = documents.case_id
            AND cases.user_id = (select auth.uid())
            AND profiles.approved = true
        )
    );

DROP POLICY IF EXISTS "Approved users can insert documents to own cases" ON documents;
CREATE POLICY "Approved users can insert documents to own cases"
    ON documents FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = documents.case_id
            AND cases.user_id = (select auth.uid())
            AND profiles.approved = true
        )
    );

DROP POLICY IF EXISTS "Approved users can update documents of own cases" ON documents;
CREATE POLICY "Approved users can update documents of own cases"
    ON documents FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = documents.case_id
            AND cases.user_id = (select auth.uid())
            AND profiles.approved = true
        )
    );

DROP POLICY IF EXISTS "Approved users can delete documents of own cases" ON documents;
CREATE POLICY "Approved users can delete documents of own cases"
    ON documents FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = documents.case_id
            AND cases.user_id = (select auth.uid())
            AND profiles.approved = true
        )
    );

-- =====================================================
-- ANALYSIS_RESULTS TABLE
-- =====================================================

DROP POLICY IF EXISTS "Users can view analysis results of own cases" ON analysis_results;
CREATE POLICY "Users can view analysis results of own cases"
    ON analysis_results FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = analysis_results.case_id
            AND cases.user_id = (select auth.uid())
        )
    );

-- =====================================================
-- INTEGRATIONS_CLIO TABLE
-- =====================================================

DROP POLICY IF EXISTS "Users can view own Clio integration" ON integrations_clio;
CREATE POLICY "Users can view own Clio integration"
    ON integrations_clio FOR SELECT
    USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can insert own Clio integration" ON integrations_clio;
CREATE POLICY "Users can insert own Clio integration"
    ON integrations_clio FOR INSERT
    WITH CHECK ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can update own Clio integration" ON integrations_clio;
CREATE POLICY "Users can update own Clio integration"
    ON integrations_clio FOR UPDATE
    USING ((select auth.uid()) = user_id);

DROP POLICY IF EXISTS "Users can delete own Clio integration" ON integrations_clio;
CREATE POLICY "Users can delete own Clio integration"
    ON integrations_clio FOR DELETE
    USING ((select auth.uid()) = user_id);

-- =====================================================
-- CASE_CHAT_MESSAGES TABLE
-- =====================================================

DROP POLICY IF EXISTS "Users can view chat messages of own cases" ON case_chat_messages;
CREATE POLICY "Users can view chat messages of own cases"
    ON case_chat_messages FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = case_chat_messages.case_id
            AND cases.user_id = (select auth.uid())
        )
    );

DROP POLICY IF EXISTS "Users can insert chat messages to own cases" ON case_chat_messages;
CREATE POLICY "Users can insert chat messages to own cases"
    ON case_chat_messages FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = case_chat_messages.case_id
            AND cases.user_id = (select auth.uid())
        )
    );

-- =====================================================
-- FIX: function_search_path_mutable
-- =====================================================

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
