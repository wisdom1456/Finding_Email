# Migrating to Existing Findings_Email Database

## Overview

Instead of creating a new Supabase database, we can repurpose the existing **Findings_Email** database from your Modible organization. This document outlines the steps to connect and migrate.

## Step 1: Find Your Existing Project

### Option A: Via Supabase Dashboard
1. Go to https://app.supabase.com
2. Select the **Modible** organization
3. Look for the **Findings_Email** project
4. Note the project reference ID and URL

### Option B: Via Supabase CLI
```bash
# Login to Supabase
supabase login

# List all projects
supabase projects list

# Look for "Findings_Email" or similar
```

## Step 2: Inspect Existing Schema

Once you have the project details, let's see what tables already exist:

```sql
-- Run this in Supabase SQL Editor
SELECT 
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;
```

## Step 3: Compare Schemas

### What We Need (from our new design):
```
Tables:
- profiles (id, email, full_name, avatar_url, created_at, updated_at)
- cases (id, user_id, client_name, reference_number, description, status, created_at, updated_at)
- documents (id, case_id, file_name, file_type, file_size, storage_path, status, extracted_text, metadata, created_at, updated_at)
- analysis_results (id, case_id, status, result, error, completed_at, created_at, updated_at)
```

### What Might Already Exist:
The previous implementation likely has similar structures. We need to check:
1. Are there user/profile tables?
2. Are there case/matter tables?
3. Are there document tables?
4. Are there analysis/result tables?

## Step 4: Migration Strategies

### Strategy A: Clean Migration (Recommended if no important data)

If the existing database has no critical data:

```sql
-- 1. Drop existing tables (CAREFUL!)
DROP TABLE IF EXISTS [old_table_names] CASCADE;

-- 2. Run our new schema
-- (Copy contents from supabase/schema.sql and execute)
```

### Strategy B: Incremental Migration (If preserving data)

If there's data to preserve:

1. **Export existing data:**
```sql
-- Export to CSV via Supabase dashboard
-- Table by table export
```

2. **Create new tables with different names:**
```sql
-- Add prefix to our new tables
CREATE TABLE new_profiles (...);
CREATE TABLE new_cases (...);
-- etc.
```

3. **Migrate data:**
```sql
-- Transform and copy data from old to new schema
INSERT INTO new_cases (user_id, client_name, ...)
SELECT 
    old_table.user_id,
    old_table.client_name,
    ...
FROM old_cases old_table;
```

4. **Rename tables:**
```sql
-- After verification, swap names
ALTER TABLE old_cases RENAME TO old_cases_backup;
ALTER TABLE new_cases RENAME TO cases;
```

### Strategy C: Fresh Start with Backup

1. **Backup existing database:**
```bash
# Via Supabase CLI
supabase db dump -f backup.sql
```

2. **Create a new Supabase project** for safety

3. **Use the existing project** with our new schema

## Step 5: Configure Application

Once you've chosen a strategy and prepared the database:

### 1. Get Supabase Credentials

From your Findings_Email project dashboard:
- Project URL: `https://[project-ref].supabase.co`
- Anon (public) key: `eyJ...` (Settings → API)
- Service role key: `eyJ...` (Settings → API)

### 2. Update Backend .env

Create `/Users/BRFlorida/Projects/Work/Finding_Emails/.env`:

```env
# Supabase Configuration
SUPABASE_URL=https://[your-project-ref].supabase.co
SUPABASE_SERVICE_KEY=eyJhbGc...your-service-role-key
SUPABASE_ANON_KEY=eyJhbGc...your-anon-key

# OpenAI (keep existing)
OPENAI_API_KEY=sk-...your-existing-key

# Optional
ANTHROPIC_API_KEY=sk-ant-...if-you-have-it
```

### 3. Update Frontend .env

Create `/Users/BRFlorida/Projects/Work/Finding_Emails/frontend/.env`:

```env
PUBLIC_SUPABASE_URL=https://[your-project-ref].supabase.co
PUBLIC_SUPABASE_ANON_KEY=eyJhbGc...your-anon-key
PUBLIC_API_URL=http://localhost:8000
```

## Step 6: Run Migration SQL

If starting fresh or the schema is significantly different, run our schema:

```bash
# Option A: Via Supabase Dashboard
# 1. Go to SQL Editor
# 2. Copy contents of supabase/schema.sql
# 3. Execute

# Option B: Via CLI
supabase db push
```

## Step 7: Verify Storage Bucket

Check if the `documents` storage bucket exists:

1. Go to Storage in Supabase dashboard
2. Look for "documents" bucket
3. If not exists, create it:
   - Name: `documents`
   - Public: `false` (private)
   - File size limit: `52428800` (50MB) or as needed

### Storage Policies

Add these policies to the `documents` bucket:

```sql
-- Upload policy
CREATE POLICY "Users can upload documents to own folders"
ON storage.objects FOR INSERT
WITH CHECK (
    bucket_id = 'documents'
    AND auth.uid()::text = (storage.foldername(name))[1]
);

-- Download policy
CREATE POLICY "Users can view own documents"
ON storage.objects FOR SELECT
USING (
    bucket_id = 'documents'
    AND auth.uid()::text = (storage.foldername(name))[1]
);

-- Delete policy
CREATE POLICY "Users can delete own documents"
ON storage.objects FOR DELETE
USING (
    bucket_id = 'documents'
    AND auth.uid()::text = (storage.foldername(name))[1]
);
```

## Step 8: Test Connection

### Test Backend:
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
source venv/bin/activate

# Test Supabase connection
python3 << EOF
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")

print(f"Connecting to: {url}")

client = create_client(url, key)
result = client.table("profiles").select("count", count="exact").limit(0).execute()
print(f"✅ Connected! Profile count: {result.count if hasattr(result, 'count') else 'N/A'}")
EOF
```

### Test Frontend:
```bash
cd frontend
npm run dev
# Navigate to http://localhost:5173/login
# Try to register/login
```

## Step 9: Create First User

### Via Supabase Dashboard:
1. Go to Authentication → Users
2. Click "Add user"
3. Enter email and password
4. Copy the user ID

### Create Profile:
```sql
-- Run in SQL Editor
INSERT INTO profiles (id, email, full_name)
VALUES 
    ('user-id-from-above', 'your-email@example.com', 'Your Name');
```

## Troubleshooting

### Issue: "relation does not exist"
**Solution:** Tables not created. Run `supabase/schema.sql`

### Issue: "row-level security policy violated"
**Solution:** RLS policies not set. Check schema.sql policies are applied

### Issue: "JWT expired" or "Invalid JWT"
**Solution:** 
- Check that SUPABASE_ANON_KEY matches in both backend and frontend
- Check that keys are from the same project

### Issue: "permission denied for table"
**Solution:** Service role key might be incorrect. Check Settings → API

## Rollback Plan

If something goes wrong:

1. **Restore from backup:**
```bash
supabase db reset
# Then restore backup.sql if you created one
```

2. **Use Supabase Time Travel:**
- Go to Database → Backups
- Restore to a previous point in time (if on Pro plan)

## Next Steps

After successful migration:

1. ✅ Test user registration
2. ✅ Test case creation
3. ✅ Test document upload
4. ✅ Test analysis workflow
5. ✅ Monitor logs for errors
6. 🎯 Deploy to production

## Quick Start Commands

If starting completely fresh with the existing project:

```bash
# 1. Set environment variables (edit with your values)
cat > .env << 'EOF'
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-key
SUPABASE_ANON_KEY=your-anon-key
OPENAI_API_KEY=your-openai-key
EOF

# 2. Run schema migration (via Supabase dashboard SQL editor)
# Copy and execute: supabase/schema.sql

# 3. Start backend
cd src
uvicorn legal_portal.api.main:app --reload --port 8000

# 4. Start frontend (new terminal)
cd frontend
npm run dev

# 5. Test at http://localhost:5173
```

---

**Need Help?** 
- Check Supabase docs: https://supabase.com/docs
- Check logs: Supabase Dashboard → Logs
- API docs: http://localhost:8000/docs (when backend is running)

