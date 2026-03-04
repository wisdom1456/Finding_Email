-- Legal Document Analysis Portal - Database Schema
-- Supabase PostgreSQL Schema with Row Level Security (RLS)

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- PROFILES TABLE
-- =====================================================
-- User profiles extending Supabase Auth
CREATE TABLE IF NOT EXISTS profiles (
    id UUID REFERENCES auth.users(id) PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    default_jurisdiction TEXT NOT NULL DEFAULT 'Florida',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Policies for profiles
CREATE POLICY "Users can view own profile"
    ON profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON profiles FOR UPDATE
    USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile"
    ON profiles FOR INSERT
    WITH CHECK (auth.uid() = id);

-- =====================================================
-- CASES TABLE
-- =====================================================
-- Legal cases for document analysis
CREATE TABLE IF NOT EXISTS cases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
    client_name TEXT NOT NULL,
    reference_number TEXT,
    description TEXT,
    jurisdiction TEXT NOT NULL DEFAULT 'Florida',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'error', 'cancelled')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_cases_user_id ON cases(user_id);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at DESC);

-- Enable RLS
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;

-- Policies for cases
CREATE POLICY "Users can view own cases"
    ON cases FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can create own cases"
    ON cases FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own cases"
    ON cases FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own cases"
    ON cases FOR DELETE
    USING (auth.uid() = user_id);

-- =====================================================
-- DOCUMENTS TABLE
-- =====================================================
-- Documents uploaded for case analysis
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID REFERENCES cases(id) ON DELETE CASCADE NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    storage_path TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('ready', 'needs_review', 'extraction_failed', 'download_failed', 'corrupted', 'skipped', 'pending', 'duplicate', 'download_timeout')),
    extracted_text TEXT,
    extraction_method TEXT,
    extraction_quality TEXT,
    extracted_at TIMESTAMPTZ,
    page_count INTEGER,
    ocr_provider TEXT,
    extraction_error TEXT,
    manual_text TEXT,
    is_verified BOOLEAN DEFAULT FALSE,
    is_flagged_as_junk BOOLEAN DEFAULT FALSE,
    text_edited_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_documents_case_id ON documents(case_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);

-- Enable RLS
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

-- Policies for documents (access through case ownership)
CREATE POLICY "Users can view documents of own cases"
    ON documents FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = documents.case_id
            AND cases.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert documents to own cases"
    ON documents FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = documents.case_id
            AND cases.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update documents of own cases"
    ON documents FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = documents.case_id
            AND cases.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete documents of own cases"
    ON documents FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = documents.case_id
            AND cases.user_id = auth.uid()
        )
    );

-- =====================================================
-- ANALYSIS_RESULTS TABLE
-- =====================================================
-- Stores the results of document analysis
CREATE TABLE IF NOT EXISTS analysis_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID REFERENCES cases(id) ON DELETE CASCADE NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'error', 'cancelled')),
    result JSONB,
    error TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_analysis_results_case_id ON analysis_results(case_id);
CREATE INDEX IF NOT EXISTS idx_analysis_results_status ON analysis_results(status);
CREATE INDEX IF NOT EXISTS idx_analysis_results_created_at ON analysis_results(created_at DESC);

-- Enable RLS
ALTER TABLE analysis_results ENABLE ROW LEVEL SECURITY;

-- Policies for analysis_results (access through case ownership)
CREATE POLICY "Users can view analysis results of own cases"
    ON analysis_results FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = analysis_results.case_id
            AND cases.user_id = auth.uid()
        )
    );

CREATE POLICY "Service can insert analysis results"
    ON analysis_results FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = analysis_results.case_id
        )
    );

CREATE POLICY "Service can update analysis results"
    ON analysis_results FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = analysis_results.case_id
        )
    );

-- =====================================================
-- FUNCTIONS AND TRIGGERS
-- =====================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function to automatically create profile on user signup
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email)
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to create profile when user signs up
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION handle_new_user();

-- Triggers for updated_at
CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_analysis_results_updated_at
    BEFORE UPDATE ON analysis_results
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- STORAGE BUCKETS
-- =====================================================
-- Note: Execute these commands in Supabase Dashboard or via CLI

-- Create storage bucket for documents
-- INSERT INTO storage.buckets (id, name, public) VALUES ('documents', 'documents', false);

-- Storage policies for documents bucket
-- CREATE POLICY "Users can upload documents to own cases"
--     ON storage.objects FOR INSERT
--     WITH CHECK (
--         bucket_id = 'documents'
--         AND auth.uid()::text = (storage.foldername(name))[1]
--     );

-- CREATE POLICY "Users can view own documents"
--     ON storage.objects FOR SELECT
--     USING (
--         bucket_id = 'documents'
--         AND auth.uid()::text = (storage.foldername(name))[1]
--     );

-- CREATE POLICY "Users can delete own documents"
--     ON storage.objects FOR DELETE
--     USING (
--         bucket_id = 'documents'
--         AND auth.uid()::text = (storage.foldername(name))[1]
--     );

-- =====================================================
-- SEED DATA (Optional - for development)
-- =====================================================
-- Example seed data can be added here for testing

-- =====================================================
-- MIGRATIONS (Dec 2025)
-- =====================================================

-- Add jurisdiction to cases table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='cases' AND column_name='jurisdiction') THEN
        ALTER TABLE public.cases ADD COLUMN jurisdiction text DEFAULT 'Florida'::text NOT NULL;
    END IF;
END $$;

-- Add default_jurisdiction to profiles table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='profiles' AND column_name='default_jurisdiction') THEN
        ALTER TABLE public.profiles ADD COLUMN default_jurisdiction text DEFAULT 'Florida'::text NOT NULL;
    END IF;
END $$;

