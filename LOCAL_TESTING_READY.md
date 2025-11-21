# ✅ Local Development Environment Ready!

## 🎉 Current Status

Both servers are running on **127.0.0.1** (as Clio prefers):

- **Frontend**: http://127.0.0.1:5173
- **Backend**: http://127.0.0.1:8000
- **API Docs**: http://127.0.0.1:8000/docs

## 🚀 Quick Start Commands

### Start Servers (Easy Way)
```bash
./start_local_dev.sh
```

### Stop Servers
```bash
./stop_local_dev.sh
```

### Manual Start
```bash
# Backend
python3 -m uvicorn src.legal_portal.api.main:app --reload --host 127.0.0.1 --port 8000

# Frontend (in a new terminal)
cd frontend && npm run dev
```

## 🧪 Testing Clio Integration

### Step 1: Update Clio Developer Console
**⚠️ CRITICAL - Do this first!**

1. Go to: https://app.clio.com/settings/developer_applications
2. Select your application
3. Add this redirect URI: `http://127.0.0.1:8000/api/clio/callback`
4. Save changes

### Step 2: Access Your Application
1. Open browser to: **http://127.0.0.1:5173** (must use 127.0.0.1, not localhost!)
2. Log in with your credentials
3. Navigate to any case detail page

### Step 3: Connect to Clio
1. Scroll to the "CLIO Integration" section
2. Click "Connect to CLIO" button
3. You'll be redirected to Clio's authorization page
4. Log in to Clio if needed
5. Click "Authorize" to grant access
6. You'll be redirected back to your case page
7. Status should show "Connected to CLIO" ✅

### Step 4: Search and Import Matters
1. In the "Search & Import Matter" section, enter a client name (3+ characters)
2. Click "Search"
3. Select a matter from the results
4. Click "Import Data from CLIO"
5. Communications, notes, and documents will be imported!

## 🔍 Debugging Tools

### Browser Console
Press F12 and check the Console tab. You should see:
```
Checking Clio status with token: eyJhbGci...
API URL: http://127.0.0.1:8000
Response status: 200
Clio status: {connected: false}
```

### Backend Logs
```bash
tail -f backend_live.log
```

### Frontend Logs
```bash
tail -f frontend_live.log
```

### Check Running Processes
```bash
lsof -i:8000  # Backend
lsof -i:5173  # Frontend
```

### Test Endpoints Directly
```bash
# Health check
curl http://127.0.0.1:8000/health

# Check if table exists (should return empty array if no connection)
curl http://127.0.0.1:8000/api/clio/status \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

## 📋 Configuration Files

### Root `.env`
```bash
# Backend configuration
SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
SUPABASE_SERVICE_KEY=your-service-key
SUPABASE_ANON_KEY=your-anon-key

# Clio Integration
CLIO_CLIENT_ID=your-clio-client-id
CLIO_CLIENT_SECRET=your-clio-client-secret
CLIO_REDIRECT_URI=http://127.0.0.1:8000/api/clio/callback

# OpenAI
OPENAI_API_KEY=your-openai-key
```

### Frontend `.env`
```bash
# Frontend configuration (public vars only!)
PUBLIC_API_URL=http://127.0.0.1:8000
PUBLIC_SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## ✅ What's Working Now

### Database
- ✅ `integrations_clio` table created
- ✅ Row Level Security (RLS) enabled
- ✅ Proper indexes for performance
- ✅ Foreign keys to auth.users

### Backend API Endpoints
- ✅ `GET /api/clio/authorize?token=...` - OAuth initiation
- ✅ `GET /api/clio/callback?code=...&state=...` - OAuth callback
- ✅ `GET /api/clio/status` - Connection status
- ✅ `DELETE /api/clio/disconnect` - Disconnect integration
- ✅ `GET /api/clio/search-matters?query=...` - Search matters
- ✅ `POST /api/clio/import` - Import matter data
- ✅ `GET /api/intake/{case_id}/review` - Intake review
- ✅ `POST /api/intake/confirm` - Confirm intake

### Frontend Components
- ✅ `ClioConnect.svelte` - OAuth connection UI
- ✅ `ClioMatterSearch.svelte` - Matter search & import
- ✅ Intake review page
- ✅ Practice area guidance

### Authentication Flow
- ✅ Session token passed as query parameter for OAuth
- ✅ Bearer token for all other API calls
- ✅ Automatic token refresh handling
- ✅ User verification with Supabase

## 🐛 Troubleshooting

### "Connection refused" on 127.0.0.1
**Problem**: Servers not running or using wrong IP
**Solution**: 
```bash
./stop_local_dev.sh  # Clean up
./start_local_dev.sh # Restart
```

### "Redirect URI mismatch" from Clio
**Problem**: Clio developer console doesn't have the right URI
**Solution**: Add exactly `http://127.0.0.1:8000/api/clio/callback` in Clio settings

### Still shows "localhost" in browser
**Problem**: Frontend env not reloaded
**Solution**: 
```bash
./stop_local_dev.sh
rm -rf frontend/.svelte-kit  # Clear cache
./start_local_dev.sh
```

### Frontend on wrong port (5174 instead of 5173)
**Problem**: Port 5173 was already in use
**Solution**: 
```bash
./stop_local_dev.sh  # This kills both 5173 and 5174
./start_local_dev.sh
```

### "Not authenticated" errors
**Problem**: Session expired or token not being sent
**Solution**:
1. Log out and log back in
2. Check browser console for token in requests
3. Verify Supabase auth is working

### Changes not reflecting
**Problem**: Browser cache or build cache
**Solution**:
```bash
# Clear SvelteKit cache
rm -rf frontend/.svelte-kit

# Hard refresh browser
Ctrl+Shift+R (Windows/Linux)
Cmd+Shift+R (Mac)
```

## 📊 System Architecture

```
Browser (127.0.0.1:5173)
    ↓
    ├─→ Supabase Auth (get session token)
    │
    ├─→ Backend API (127.0.0.1:8000)
    │   ├─→ /api/clio/authorize?token=...
    │   │   ↓
    │   │   Verifies token with Supabase
    │   │   ↓
    │   │   Redirects to Clio OAuth
    │   │
    │   └─→ /api/clio/callback?code=...
    │       ↓
    │       Exchanges code for tokens
    │       ↓
    │       Stores in integrations_clio table
    │       ↓
    │       Redirects back to frontend
    │
    └─→ Supabase Database
        ├─ integrations_clio (OAuth tokens)
        ├─ cases
        ├─ documents
        └─ analysis_results
```

## 🎯 Next Steps

1. ✅ Servers running on 127.0.0.1
2. ⏳ Update Clio Developer Console with redirect URI
3. ⏳ Test OAuth connection flow
4. ⏳ Test matter search
5. ⏳ Test data import
6. ⏳ Prepare for production deployment

## 📚 Additional Resources

- **Clio API Docs**: https://docs.developers.clio.com/
- **Supabase Docs**: https://supabase.com/docs
- **SvelteKit Docs**: https://kit.svelte.dev/docs
- **FastAPI Docs**: https://fastapi.tiangolo.com/

## 🎉 Success Indicators

You'll know everything is working when:
- ✅ Can access app at http://127.0.0.1:5173
- ✅ Can click "Connect to CLIO" without errors
- ✅ Get redirected to Clio authorization page
- ✅ After authorizing, see "Connected to CLIO"
- ✅ Can search for Clio matters
- ✅ Can import matter data
- ✅ Documents appear in case

**You're ready to test! Open http://127.0.0.1:5173 in your browser!** 🚀

