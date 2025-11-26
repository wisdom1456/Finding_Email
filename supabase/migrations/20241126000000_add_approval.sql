-- Add approval system to profiles table
-- This migration adds account approval functionality

-- Add approved column to profiles (default false)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS approved BOOLEAN DEFAULT false;

-- Add role column to profiles with check constraint
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user' CHECK (role IN ('user', 'admin'));

-- Update existing profiles to be approved (for backwards compatibility)
UPDATE profiles SET approved = true WHERE approved IS NULL;

-- Update the handle_new_user function to set defaults for new users
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, approved, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email),
        false,  -- New users need approval
        'user'  -- Default role
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add RLS policies to restrict access for non-approved users
-- Drop existing policies first if they need to be updated
DROP POLICY IF EXISTS "Users can create own cases" ON cases;
DROP POLICY IF EXISTS "Users can view own cases" ON cases;
DROP POLICY IF EXISTS "Users can update own cases" ON cases;
DROP POLICY IF EXISTS "Users can delete own cases" ON cases;

-- Recreate policies with approval check
CREATE POLICY "Approved users can view own cases"
    ON cases FOR SELECT
    USING (
        auth.uid() = user_id 
        AND EXISTS (
            SELECT 1 FROM profiles 
            WHERE profiles.id = auth.uid() 
            AND profiles.approved = true
        )
    );

CREATE POLICY "Approved users can create own cases"
    ON cases FOR INSERT
    WITH CHECK (
        auth.uid() = user_id 
        AND EXISTS (
            SELECT 1 FROM profiles 
            WHERE profiles.id = auth.uid() 
            AND profiles.approved = true
        )
    );

CREATE POLICY "Approved users can update own cases"
    ON cases FOR UPDATE
    USING (
        auth.uid() = user_id 
        AND EXISTS (
            SELECT 1 FROM profiles 
            WHERE profiles.id = auth.uid() 
            AND profiles.approved = true
        )
    );

CREATE POLICY "Approved users can delete own cases"
    ON cases FOR DELETE
    USING (
        auth.uid() = user_id 
        AND EXISTS (
            SELECT 1 FROM profiles 
            WHERE profiles.id = auth.uid() 
            AND profiles.approved = true
        )
    );

-- Update documents policies to check approval through case ownership
DROP POLICY IF EXISTS "Users can view documents of own cases" ON documents;
DROP POLICY IF EXISTS "Users can insert documents to own cases" ON documents;
DROP POLICY IF EXISTS "Users can update documents of own cases" ON documents;
DROP POLICY IF EXISTS "Users can delete documents of own cases" ON documents;

CREATE POLICY "Approved users can view documents of own cases"
    ON documents FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = documents.case_id
            AND cases.user_id = auth.uid()
            AND profiles.approved = true
        )
    );

CREATE POLICY "Approved users can insert documents to own cases"
    ON documents FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = documents.case_id
            AND cases.user_id = auth.uid()
            AND profiles.approved = true
        )
    );

CREATE POLICY "Approved users can update documents of own cases"
    ON documents FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = documents.case_id
            AND cases.user_id = auth.uid()
            AND profiles.approved = true
        )
    );

CREATE POLICY "Approved users can delete documents of own cases"
    ON documents FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM cases
            JOIN profiles ON profiles.id = cases.user_id
            WHERE cases.id = documents.case_id
            AND cases.user_id = auth.uid()
            AND profiles.approved = true
        )
    );

-- Add index for faster approval checks
CREATE INDEX IF NOT EXISTS idx_profiles_approved ON profiles(approved);
CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles(role);

