# Legal Document Analysis Portal - Setup Guide

## 1. Prerequisites

- **Python 3.11+** -- `python3 --version`
- **Node.js 18+** -- `node --version`
- **npm** -- `npm --version`

Install dependencies:

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
pip install -r requirements.txt

cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm install
```

---

## 2. Environment Variables

### Backend (.env)

Create `/Users/BRFlorida/Projects/Work/Finding_Emails/.env`:

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key-here
SUPABASE_ANON_KEY=your-anon-key-here

# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-key-here

# Google Cloud Vision OCR (optional -- faster and cheaper than GPT-4o)
GOOGLE_APPLICATION_CREDENTIALS_JSON=base64-encoded-service-account-json

# Clio Integration (optional)
CLIO_CLIENT_ID=your-clio-client-id
CLIO_CLIENT_SECRET=your-clio-client-secret
CLIO_REDIRECT_URI=http://127.0.0.1:8000/api/clio/callback

# Frontend URL (for OAuth callback redirects)
FRONTEND_URL=http://127.0.0.1:5173

# Application Settings
LOG_LEVEL=INFO
DEBUG_MODE=false
```

### Frontend (frontend/.env.local)

Create `/Users/BRFlorida/Projects/Work/Finding_Emails/frontend/.env.local`:

```bash
PUBLIC_API_URL=http://localhost:8000
PUBLIC_SUPABASE_URL=https://your-project.supabase.co
PUBLIC_SUPABASE_ANON_KEY=your-anon-key-here
```

**Notes:** Never commit `.env` files to git. Use the service key only in the backend. The `SUPABASE_ANON_KEY` must match between backend and frontend.

---

## 3. Database Setup

### Apply the Schema

**Option A: Supabase Dashboard (recommended)**

1. Open https://app.supabase.com, select your project.
2. Go to **SQL Editor** > **New query**.
3. Paste the full contents of `supabase/schema.sql` and click **Run**.
4. Verify tables exist: `profiles`, `cases`, `documents`, `analysis_results`.

**Option B: Supabase CLI**

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
supabase link --project-ref your-project-ref
supabase db push
```

Verify with:

```bash
python3 scripts/test_supabase_connection.py
```

### Create Storage Bucket

1. In Supabase Dashboard, go to **Storage** > **New bucket**.
   - Name: `documents`, Public: OFF, File size limit: `52428800` (50MB)
2. Apply storage policies in the SQL Editor:

```sql
CREATE POLICY "Users can upload documents to own folders"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'documents' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can view own documents"
ON storage.objects FOR SELECT
USING (bucket_id = 'documents' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can delete own documents"
ON storage.objects FOR DELETE
USING (bucket_id = 'documents' AND auth.uid()::text = (storage.foldername(name))[1]);
```

---

## 4. Starting the Application

Two terminal windows are required.

### Terminal 1: Backend (FastAPI)

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src
uvicorn legal_portal.api.main:app --reload --port 8000
```

Ready when you see `Application startup complete`. Verify at http://localhost:8000/docs.

### Terminal 2: Frontend (SvelteKit)

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

Ready when you see `Local: http://localhost:5173/`. Verify at http://localhost:5173.

To stop either server, press `Ctrl + C` in its terminal.

---

## 5. First-Time User Setup

1. **Register** at http://localhost:5173/register with email and password.
2. **Login** -- auto-redirects after registration, or go to http://localhost:5173/login.
3. **Create a case** -- click "New Case", enter client name, click "Create Case".
4. **Upload documents** -- open your case, click "Upload Files", select PDF/DOCX files.
5. **Analyze** -- click "Start Analysis", wait for completion (2-5 minutes).

---

## 6. Restarting the Application

### Kill Existing Processes

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5173 | xargs kill -9 2>/dev/null
```

### Clear Python Cache

```bash
find /Users/BRFlorida/Projects/Work/Finding_Emails -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
```

### Clear Frontend Cache

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
rm -rf .svelte-kit node_modules package-lock.json
npm install
```

### Clear Browser Cache

Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows).

Then start both servers again per Section 4. If Python packages are missing, activate the virtual environment first:

```bash
source /Users/BRFlorida/Projects/Work/Finding_Emails/venv/bin/activate
```

---

## 7. Troubleshooting

### Backend Issues

| Problem | Solution |
|---------|----------|
| `command not found: uvicorn` | Use `python3 -m uvicorn legal_portal.api.main:app --reload --port 8000` from the `src` directory |
| Port 8000 in use | `lsof -ti:8000 \| xargs kill -9` |
| Import errors | Confirm you are running from the `src` directory, not the project root |
| Missing OPENAI_API_KEY | Check `.env` file: `grep OPENAI /Users/BRFlorida/Projects/Work/Finding_Emails/.env` |
| Missing dependencies | `pip install -r requirements.txt` from the project root |

### Frontend Issues

| Problem | Solution |
|---------|----------|
| Port 5173 in use | `lsof -ti:5173 \| xargs kill -9` |
| 500 error on login page | Reinstall: `rm -rf node_modules package-lock.json && npm install` -- ensure `@tailwindcss/postcss` is installed |
| "Cannot find module" | `rm -rf node_modules package-lock.json .svelte-kit && npm install` |
| Cannot connect to backend | Verify `PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local` and backend is running |

### Auth Issues

| Problem | Solution |
|---------|----------|
| "JWT expired" / "Invalid token" | Verify `SUPABASE_ANON_KEY` matches in both `.env` files and corresponds to the correct project |
| Cannot login or register | Check browser console; verify Supabase URL and keys in `frontend/.env.local` |

### Upload Issues

| Problem | Solution |
|---------|----------|
| Files will not upload | Confirm `documents` bucket exists, storage policies are applied, file is under 50MB |
| "Permission denied" | Re-run storage policy SQL from Section 3 |

### Analysis Issues

| Problem | Solution |
|---------|----------|
| Stuck on "processing" | Check backend logs, verify OPENAI_API_KEY, check rate limits at https://platform.openai.com/usage |
| "No documents found" | Verify documents uploaded successfully in the `documents` table in Supabase |

### Dependency Issues

| Problem | Solution |
|---------|----------|
| ModuleNotFoundError: html2text, python-docx, PyMuPDF | Ensure these are uncommented in `requirements.txt`, then `pip install -r requirements.txt` |
| ModuleNotFoundError: sse_starlette | `pip install sse-starlette==2.1.3` or reinstall all requirements |

---

## 8. Quick Reference

### URLs

| Resource           | URL                            |
|--------------------|--------------------------------|
| Application        | http://localhost:5173           |
| Registration       | http://localhost:5173/register  |
| Login              | http://localhost:5173/login     |
| Dashboard          | http://localhost:5173/app       |
| API Docs           | http://localhost:8000/docs      |
| Health Check       | http://localhost:8000/health    |
| Supabase Dashboard | https://app.supabase.com        |
| OpenAI Dashboard   | https://platform.openai.com    |

### Environment Variables

| Variable | Required | Location | Description |
|----------|----------|----------|-------------|
| `SUPABASE_URL` | Yes | `.env` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | `.env` | Supabase service role key |
| `SUPABASE_ANON_KEY` | Yes | `.env` | Supabase anonymous key |
| `OPENAI_API_KEY` | Yes | `.env` | OpenAI API key |
| `FRONTEND_URL` | Yes | `.env` | Frontend URL for OAuth redirects |
| `CLIO_CLIENT_ID` | No | `.env` | Clio integration client ID |
| `CLIO_CLIENT_SECRET` | No | `.env` | Clio integration client secret |
| `CLIO_REDIRECT_URI` | No | `.env` | Clio OAuth callback URI |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | No | `.env` | Base64-encoded GCP service account |
| `LOG_LEVEL` | No | `.env` | Logging level (default: INFO) |
| `DEBUG_MODE` | No | `.env` | Enable debug mode (default: false) |
| `PUBLIC_API_URL` | Yes | `frontend/.env.local` | Backend API URL |
| `PUBLIC_SUPABASE_URL` | Yes | `frontend/.env.local` | Supabase URL (public) |
| `PUBLIC_SUPABASE_ANON_KEY` | Yes | `frontend/.env.local` | Supabase anon key (public) |
