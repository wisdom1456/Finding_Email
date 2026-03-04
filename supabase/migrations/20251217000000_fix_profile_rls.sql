-- Fix for profile creation RLS issue
-- This ensures the trigger can properly create profiles for new users
-- Run this in Supabase Dashboard → SQL Editor

-- First, drop and recreate the function with proper settings
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER 
SECURITY DEFINER
SET search_path = public
AS $$
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
EXCEPTION
    WHEN unique_violation THEN
        -- Profile already exists, ignore
        RETURN NEW;
    WHEN OTHERS THEN
        -- Log error but don't block user creation
        RAISE WARNING 'Failed to create profile for user %: %', NEW.id, SQLERRM;
        RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Ensure the function owner is postgres/supabase_admin for SECURITY DEFINER to work
ALTER FUNCTION handle_new_user() OWNER TO postgres;

-- Recreate the trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION handle_new_user();

-- Add a permissive INSERT policy for the trigger
-- This allows profile creation without requiring auth.uid() = id during signup
DROP POLICY IF EXISTS "Service can create profiles" ON profiles;
CREATE POLICY "Service can create profiles"
    ON profiles FOR INSERT
    WITH CHECK (true);

-- Verify the trigger was created
SELECT 
    trigger_name, 
    event_manipulation, 
    event_object_table,
    action_statement
FROM information_schema.triggers
WHERE trigger_name = 'on_auth_user_created';

