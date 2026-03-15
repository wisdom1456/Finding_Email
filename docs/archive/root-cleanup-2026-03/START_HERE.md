# 🚀 START HERE - Legal Document Analysis Portal Setup

## ✅ What's Already Done

- [x] Backend API implemented (FastAPI)
- [x] Frontend UI implemented (SvelteKit)
- [x] Database schema designed
- [x] Root .env configured with Supabase credentials
- [x] Frontend .env configured automatically
- [x] Connection to Supabase verified

## 📋 What You Need to Do Now

### 1️⃣ Apply Database Schema (5 minutes)

**Go to:** https://app.supabase.com

1. Select your project (Modible organization)
2. Click **SQL Editor** in the left sidebar
3. Click **New query**
4. Open this file on your computer: `supabase/schema.sql`
5. Copy ALL the contents
6. Paste into the SQL Editor
7. Click **RUN** (or press Cmd+Enter)
8. You should see: "Success. No rows returned"

**Verify it worked:**
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 scripts/test_supabase_connection.py
```

Expected output: `✅ All tables exist - schema is properly applied!`

### 2️⃣ Create Storage Bucket (3 minutes)

**In Supabase Dashboard:**

1. Click **Storage** in the left sidebar
2. Click **New bucket**
3. Settings:
   - Name: `documents`
   - Public: **OFF** (unchecked)
   - File size limit: `52428800` (or leave default)
4. Click **Create bucket**

**Apply storage policies** (back in SQL Editor):

Copy this and run it in a new query:

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

### 3️⃣ Start the Backend (30 seconds)

Open a terminal:

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src
uvicorn legal_portal.api.main:app --reload --port 8000
```

**Test it:** Open http://localhost:8000/docs in your browser
- You should see the FastAPI documentation

### 4️⃣ Start the Frontend (30 seconds)

Open a **NEW** terminal (keep the backend running):

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

**Test it:** Open http://localhost:5173 in your browser
- You should see the login page

### 5️⃣ Create Your First User & Test (2 minutes)

1. **Register**: http://localhost:5173/register
   - Enter your email and password
   - Click "Create account"

2. **Login**: Should auto-redirect, or go to http://localhost:5173/login

3. **Create a case**:
   - Click "New Case"
   - Enter client name (e.g., "John Doe")
   - Add a reference number (optional)
   - Click "Create Case"

4. **Upload documents**:
   - Click on your new case
   - Click "Upload Files"
   - Select some test PDFs or documents
   - Wait for upload to complete

5. **Start analysis**:
   - Click "Start Analysis"
   - Watch the status change from "pending" → "processing" → "completed"

## 🎯 Quick Start Commands (All at Once)

If you want to copy-paste everything:

```bash
# Terminal 1: Test connection
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 scripts/test_supabase_connection.py

# After schema is applied, start backend:
cd src
uvicorn legal_portal.api.main:app --reload --port 8000

# Terminal 2: Start frontend
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

## 📚 Documentation

- **SETUP_INSTRUCTIONS.md** - Detailed setup steps
- **REFACTOR_README.md** - Full architecture documentation
- **IMPLEMENTATION_SUMMARY.md** - What was built and why
- **EXISTING_DATABASE_MIGRATION.md** - How to use existing databases

## 🔧 Troubleshooting

### Backend won't start
```bash
# Make sure you're in the right directory
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src

# Check Python version (need 3.11+)
python3 --version

# Reinstall dependencies if needed
cd ..
pip install -r requirements.txt
```

### Frontend won't start
```bash
# Reinstall node modules
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
rm -rf node_modules
npm install
npm run dev
```

### "JWT expired" errors
- Your SUPABASE_ANON_KEY might be wrong
- Check: `cat /Users/BRFlorida/Projects/Work/Finding_Emails/.env`
- Make sure it matches what's in Supabase Dashboard → Settings → API

### Can't upload files
- Check that the `documents` storage bucket exists
- Check that storage policies are applied
- Check browser console for errors

### Analysis gets stuck
- Check backend logs (Terminal 1) for errors
- Make sure OPENAI_API_KEY is set in root .env
- Check OpenAI API dashboard for rate limits

## 🎉 You're Done When...

✅ Schema applied (test script passes)
✅ Storage bucket created
✅ Backend running on port 8000
✅ Frontend running on port 5173
✅ Can register/login
✅ Can create a case
✅ Can upload documents
✅ Can start analysis

## 🚀 Next Steps After Setup

1. **Test the full workflow** with real documents
2. **Customize** the prompts in `src/legal_portal/prompts/`
3. **Deploy** to production (see REFACTOR_README.md)
4. **Add team members** via Supabase Auth

## 💡 Pro Tips

- Keep both terminals open (backend + frontend)
- Use the API docs at http://localhost:8000/docs to debug
- Check Supabase Dashboard → Logs if something goes wrong
- Use the browser DevTools Network tab to see API calls

---

## ⚡ TL;DR - Minimal Steps

1. Apply `supabase/schema.sql` in Supabase SQL Editor
2. Create `documents` storage bucket + policies
3. `cd src && uvicorn legal_portal.api.main:app --reload --port 8000`
4. `cd frontend && npm run dev`
5. Register at http://localhost:5173/register
6. Create case → Upload docs → Analyze!

**Current Setup:**
- 🗄️ Database: https://nqjepycmhddfekeufcle.supabase.co
- 🔧 API: http://localhost:8000
- 🌐 Frontend: http://localhost:5173
- 📝 Docs: http://localhost:8000/docs

