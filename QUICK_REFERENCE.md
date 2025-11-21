# Quick Reference Card

## 🚀 Start Application

```bash
# Terminal 1 - Backend
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src
python3 -m uvicorn legal_portal.api.main:app --reload --port 8000

# Terminal 2 - Frontend
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

## 🌐 URLs

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:5173 | Main application |
| Backend | http://localhost:8000 | API server |
| API Docs | http://localhost:8000/docs | Interactive API documentation |
| Health Check | http://localhost:8000/health | Backend status |

## 🔑 Environment Variables

Located in: `/Users/BRFlorida/Projects/Work/Finding_Emails/.env`

```bash
SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
SUPABASE_ANON_KEY=eyJ...  # Public key
SUPABASE_SERVICE_KEY=eyJ...  # Admin key (keep secret!)
```

## 📁 Key Files

| File | Purpose |
|------|---------|
| `src/legal_portal/api/main.py` | FastAPI app entry point |
| `src/legal_portal/api/dependencies.py` | **Auth dependencies (RLS fix here!)** |
| `src/legal_portal/api/routes/cases.py` | Case CRUD endpoints |
| `frontend/src/routes/+layout.server.ts` | Root layout (auth loading) |
| `frontend/src/routes/app/+layout.svelte` | App layout (sidebar) |
| `supabase/schema.sql` | Database schema with RLS |

## 🐛 Troubleshooting

### Backend won't start
```bash
# Kill existing process
ps aux | grep uvicorn | grep -v grep | awk '{print $2}' | xargs kill

# Restart
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src
python3 -m uvicorn legal_portal.api.main:app --reload --port 8000
```

### Frontend won't start
```bash
# Kill existing process
ps aux | grep "npm run dev" | grep -v grep | awk '{print $2}' | xargs kill

# Restart
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

### RLS Policy Error
```bash
# Test the fix
python3 scripts/debug_create_case.py

# Should show: Status: 201 (success)
```

### Check Database Connection
```bash
python3 scripts/test_supabase_connection.py
```

## 🧪 Testing

```bash
# Quick health check
curl http://localhost:8000/health

# Create test case (programmatic)
python3 scripts/debug_create_case.py

# Run regression tests
pytest tests/ -v
```

## 📊 Supabase Dashboard

**Project:** Findings_Email  
**Organization:** Modible  
**URL:** https://supabase.com/dashboard/project/nqjepycmhddfekeufcle

**Useful Sections:**
- **Table Editor:** View/edit data
- **SQL Editor:** Run queries
- **Storage:** Manage uploaded files
- **Authentication:** Manage users
- **Logs:** View database activity

## 🔒 Important Security Notes

1. **Service Key** = Admin access, bypasses RLS
   - Use for: Background tasks, admin operations
   - Don't use for: User-initiated actions

2. **Anon Key** = User access, respects RLS
   - Use for: Frontend, user API calls
   - Requires: User JWT token

3. **RLS Fix:**
   - `get_user_supabase_client()` = Uses anon key + user token ✅
   - `get_supabase_client()` = Uses service key (admin only)

## 📝 Common Tasks

### Add New User (via UI)
1. Go to http://localhost:5173/register
2. Fill in email, password, name
3. Click "Sign Up"

### Create Case (via UI)
1. Login at http://localhost:5173/login
2. Navigate to "Cases" → "New Case"
3. Fill in details and submit

### Upload Document
1. Open a case detail page
2. Click "Upload Document"
3. Select file and add metadata

### View API Documentation
1. Go to http://localhost:8000/docs
2. Expand endpoints to see schemas
3. Try out endpoints with "Try it out" button

## 🎯 API Quick Reference

### Authentication
All API calls (except `/health`) require:
```
Authorization: Bearer <JWT_TOKEN>
```

Get token from login:
```bash
curl -X POST https://nqjepycmhddfekeufcle.supabase.co/auth/v1/token \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}'
```

### Create Case
```bash
curl -X POST http://localhost:8000/api/cases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Test","reference_number":"T-001","status":"pending"}'
```

### List Cases
```bash
curl http://localhost:8000/api/cases \
  -H "Authorization: Bearer $TOKEN"
```

### Upload Document
```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf" \
  -F "case_id=<uuid>" \
  -F "title=Document Title"
```

## 📚 Documentation Files

| File | Description |
|------|-------------|
| `REFACTOR_COMPLETE.md` | ⭐ Complete refactor summary |
| `RLS_FIX_SUMMARY.md` | ⭐ RLS authentication fix details |
| `TESTING_GUIDE.md` | ⭐ Comprehensive testing guide |
| `START.md` | Startup instructions |
| `SETUP_INSTRUCTIONS.md` | Initial setup guide |
| `supabase/README.md` | Database setup |

## 🆘 Emergency Commands

### Kill All Processes
```bash
# Kill backend
pkill -f uvicorn

# Kill frontend
pkill -f "npm run dev"
```

### Reset Database (CAUTION!)
```bash
# In Supabase SQL Editor, run:
# DROP SCHEMA public CASCADE;
# CREATE SCHEMA public;
# Then re-run schema.sql
```

### Clear Node Modules
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Reinstall Python Dependencies
```bash
pip install --user --force-reinstall -r requirements.txt
```

## ✅ Current Status

- ✅ Backend: Running on port 8000
- ✅ Frontend: Running on port 5173
- ✅ Database: Connected to Supabase
- ✅ RLS: Working correctly
- ✅ Tailwind: Styled properly
- ✅ Auth: Functional

## 🎉 Success Indicators

You know everything is working when:
1. `curl http://localhost:8000/health` returns `"status":"healthy"`
2. http://localhost:5173 redirects to styled login page
3. `python3 scripts/debug_create_case.py` returns status 201
4. Case creation in UI shows no errors
5. Documents can be uploaded

---

**Quick Start:** See `START.md`  
**Full Docs:** See `REFACTOR_COMPLETE.md`  
**Testing:** See `TESTING_GUIDE.md`

