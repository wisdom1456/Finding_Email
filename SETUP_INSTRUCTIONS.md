# Quick Setup Instructions

## Current Status

✅ **Backend .env configured** - Supabase credentials are set
✅ **Connection verified** - Can connect to your Supabase project at:
   `https://nqjepycmhddfekeufcle.supabase.co`

⚠️ **Schema not applied** - Database tables need to be created

## Step 1: Apply Database Schema

### Option A: Via Supabase Dashboard (Recommended)

1. **Open Supabase Dashboard**
   ```
   https://app.supabase.com
   ```

2. **Navigate to your project**
   - Organization: **Modible**
   - Project: Your new database

3. **Open SQL Editor**
   - Click on "SQL Editor" in the left sidebar
   - Click "New query"

4. **Copy and execute the schema**
   - Open the file: `supabase/schema.sql`
   - Copy ALL contents
   - Paste into SQL Editor
   - Click "Run" (or press Cmd/Ctrl + Enter)

5. **Verify success**
   - You should see "Success. No rows returned"
   - Check Tables section - you should see: `profiles`, `cases`, `documents`, `analysis_results`

### Option B: Via Supabase CLI

If you have Supabase CLI installed:

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails

# Link to your project
supabase link --project-ref nqjepycmhddfekeufcle

# Push the schema
supabase db push
```

## Step 2: Create Storage Bucket

1. **In Supabase Dashboard**, go to **Storage**

2. **Create new bucket**:
   - Name: `documents`
   - Public: **OFF** (unchecked)
   - Allowed MIME types: Leave empty (all types)
   - File size limit: `52428800` (50MB)

3. **Apply storage policies** (in SQL Editor):
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

## Step 3: Configure Frontend

The frontend needs its own `.env` file:

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend

# Create .env file (we'll do this automatically)
# It will use the same Supabase credentials from the root .env
```

## Step 4: Test Connection Again

After applying the schema:

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 scripts/test_supabase_connection.py
```

You should see:
```
✅ All tables exist - schema is properly applied!
```

## Step 5: Start the Application

### Terminal 1: Backend (FastAPI)
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src
uvicorn legal_portal.api.main:app --reload --port 8000
```

Visit API docs: http://localhost:8000/docs

### Terminal 2: Frontend (SvelteKit)
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

Visit app: http://localhost:5173

## Step 6: Create Your First User

1. **Go to**: http://localhost:5173/register
2. **Register** with your email and password
3. **Login** at: http://localhost:5173/login
4. **Start using** the app!

## Verification Checklist

- [ ] Schema applied (all 4 tables exist)
- [ ] Storage bucket created (`documents`)
- [ ] Storage policies applied
- [ ] Frontend .env configured
- [ ] Backend running (port 8000)
- [ ] Frontend running (port 5173)
- [ ] Can register new user
- [ ] Can create new case
- [ ] Can upload documents

## Troubleshooting

### "JWT expired" or "Invalid token"
- Make sure SUPABASE_ANON_KEY is the same in both .env files
- Check that you're using keys from the correct project

### "Permission denied for table"
- RLS policies might not be applied correctly
- Re-run the schema.sql file

### "Bucket not found"
- Create the `documents` storage bucket
- Make sure it's set to Private (not Public)

### Frontend can't connect to backend
- Check that PUBLIC_API_URL=http://localhost:8000 in frontend/.env
- Make sure backend is running on port 8000

## Next Steps

Once everything is working:

1. **Test the full workflow**:
   - Create a case
   - Upload documents
   - Start analysis
   - View results

2. **Review the documentation**:
   - `REFACTOR_README.md` - Full architecture guide
   - `IMPLEMENTATION_SUMMARY.md` - What was built

3. **Consider deployment**:
   - Backend: Vercel, Railway, or Fly.io
   - Frontend: Vercel or Netlify
   - Database: Already on Supabase (hosted)

---

**Current Project**: https://nqjepycmhddfekeufcle.supabase.co
**Organization**: Modible
**Status**: Ready for schema application

