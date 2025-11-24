# Supabase Database Setup

This directory contains the database schema and setup instructions for the Legal Document Analysis Portal.

## Schema Overview

The database consists of four main tables:

1. **profiles** - User profiles (extends Supabase Auth)
2. **cases** - Legal cases for document analysis
3. **documents** - Documents uploaded for each case
4. **analysis_results** - AI analysis results for each case

## Setup Instructions

### 1. Create Supabase Project

1. Go to [supabase.com](https://supabase.com)
2. Create a new project
3. Note your project URL and API keys

### 2. Run Schema Migration

#### Option A: Using Supabase Dashboard

1. Open your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Copy the contents of `schema.sql`
4. Paste and execute

#### Option B: Using Supabase CLI

```bash
# Install Supabase CLI
npm install -g supabase

# Login to Supabase
supabase login

# Link to your project
supabase link --project-ref YOUR_PROJECT_REF

# Run migration
supabase db push
```

### 3. Create Storage Bucket

1. Navigate to **Storage** in Supabase Dashboard
2. Create a new bucket named `documents`
3. Set it as **Private** (not public)
4. Apply the storage policies from `schema.sql` (commented section at bottom)

### 4. Environment Variables

Add these to your `.env` file:

```env
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key_here
SUPABASE_ANON_KEY=your_anon_key_here
```

## Row Level Security (RLS)

All tables have RLS enabled with the following policies:

- **profiles**: Users can only view/update their own profile
- **cases**: Users can only access their own cases
- **documents**: Access granted through case ownership
- **analysis_results**: Access granted through case ownership

## Storage Policies

The `documents` storage bucket uses folder-based isolation:
- Files are stored as: `{user_id}/{case_id}/{filename}`
- Users can only access files in folders matching their user ID

## Testing the Schema

After setup, verify the tables exist:

```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```

## Development Seed Data

For development/testing, you can insert sample data:

```sql
-- Insert a test profile (must match an existing auth user)
INSERT INTO profiles (id, email, full_name)
VALUES ('user-uuid-here', 'test@example.com', 'Test User');

-- Insert a test case
INSERT INTO cases (user_id, client_name, reference_number, description)
VALUES ('user-uuid-here', 'John Doe', 'CASE-2024-001', 'Test case description');
```

