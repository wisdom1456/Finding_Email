# ✅ Clio OAuth Callback Fixed!

## What Was Wrong

After successfully authorizing on Clio, users were being redirected to:
```
http://127.0.0.1:8000/app/cases?clio_connected=true
```

This was hitting the **backend** (port 8000) instead of the **frontend** (port 5173), resulting in a 404 error.

## What I Fixed

### 1. Updated OAuth Callback Handler
**File**: `src/legal_portal/api/routes/clio.py`

Changed the callback redirect from a relative URL to an absolute frontend URL:

**Before**:
```python
frontend_url = "/app/cases?clio_connected=true"  # Relative - stays on port 8000
```

**After**:
```python
frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
redirect_url = f"{frontend_url}/app/cases?clio_connected=true"  # Absolute - goes to frontend
```

### 2. Added FRONTEND_URL Environment Variable
**File**: `.env`

```bash
FRONTEND_URL=http://127.0.0.1:5173
```

This allows the backend to know where to redirect users after OAuth completion.

### 3. Restarted Backend
Applied the changes by restarting the backend server.

## How OAuth Flow Works Now

```
1. User clicks "Connect to CLIO"
   ↓
2. Frontend redirects to: 
   http://127.0.0.1:8000/api/clio/authorize?token={session_token}
   ↓
3. Backend verifies token and redirects to Clio:
   https://app.clio.com/oauth/authorize?...
   ↓
4. User authorizes on Clio
   ↓
5. Clio redirects back to:
   http://127.0.0.1:8000/api/clio/callback?code=...&state=...
   ↓
6. Backend exchanges code for tokens
   ↓
7. Backend stores tokens in database
   ↓
8. Backend redirects to FRONTEND:
   http://127.0.0.1:5173/app/cases?clio_connected=true ✅
   ↓
9. Frontend detects success and updates UI
```

## Test It Now!

1. **Make sure both servers are running:**
   ```bash
   lsof -i:8000  # Backend should be running
   lsof -i:5173  # Frontend should be running
   ```

2. **Open the app:**
   - http://127.0.0.1:5173 or http://localhost:5173

3. **Navigate to any case**

4. **Click "Connect to CLIO"**

5. **Authorize on Clio**

6. **You should be redirected back to:**
   - ✅ `http://127.0.0.1:5173/app/cases?clio_connected=true`
   - ✅ Status shows "Connected to CLIO"
   - ✅ Search section appears

## Expected Behavior

### Success Path
1. After authorizing on Clio, browser URL changes to:
   ```
   http://127.0.0.1:5173/app/cases?clio_connected=true
   ```

2. The app detects the `clio_connected=true` query parameter

3. Shows success message or updates connection status

4. "Search & Import Matter" section becomes visible

### Error Path
If something goes wrong, you'll be redirected to:
```
http://127.0.0.1:5173/app/cases?clio_error={error_message}
```

## Troubleshooting

### Still getting 404?
**Check that FRONTEND_URL is set:**
```bash
grep FRONTEND_URL .env
# Should show: FRONTEND_URL=http://127.0.0.1:5173
```

**Restart backend if you just added it:**
```bash
./stop_local_dev.sh
./start_local_dev.sh
```

### Redirecting to wrong URL?
**Check backend logs:**
```bash
tail -f backend_live.log | grep "redirect"
```

You should see the redirect URL being constructed.

### Connection works but status doesn't update?
**Check browser console** (F12) for errors. The frontend should:
1. Detect the `clio_connected=true` query parameter
2. Show a success message
3. Reload the connection status

**Manually check status:**
```bash
# Get your session token from browser console: localStorage.getItem('supabase.auth.token')
curl http://127.0.0.1:8000/api/clio/status \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

Should return:
```json
{
  "connected": true,
  "clio_user_id": null,
  "expires_at": "2024-11-20T..."
}
```

## Environment Variables Summary

### Root `.env` (Backend)
```bash
# Supabase
SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
SUPABASE_SERVICE_KEY=your-service-key
SUPABASE_ANON_KEY=your-anon-key

# Clio
CLIO_CLIENT_ID=your-client-id
CLIO_CLIENT_SECRET=your-client-secret
CLIO_REDIRECT_URI=http://127.0.0.1:8000/api/clio/callback

# Frontend URL for OAuth redirects
FRONTEND_URL=http://127.0.0.1:5173

# OpenAI
OPENAI_API_KEY=your-openai-key
```

### Frontend `.env`
```bash
PUBLIC_API_URL=http://127.0.0.1:8000
PUBLIC_SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## Production Deployment

For production on Vercel, set these environment variables:

```bash
FRONTEND_URL=https://your-app.vercel.app
CLIO_REDIRECT_URI=https://your-app.vercel.app/api/clio/callback
```

The backend will automatically use these values when deployed.

## ✅ Status

- ✅ Backend redirects to frontend after OAuth
- ✅ Frontend URL configured in environment
- ✅ Both success and error paths handled
- ✅ Backend restarted with changes
- ✅ Ready for testing!

**Try connecting to Clio again - it should work now!** 🎉

