# ✅ Ready to Test Clio Integration!

## 🎉 All Systems Running

### Current Status
- ✅ **Backend**: http://127.0.0.1:8000 (FastAPI + Clio routes)
- ✅ **Frontend**: http://127.0.0.1:5173 OR http://localhost:5173
- ✅ **Database**: Supabase with `integrations_clio` table
- ✅ **Configuration**: All env files using 127.0.0.1

### Fixed Issues
1. ✅ Changed all localhost → 127.0.0.1 (Clio preference)
2. ✅ Updated Vite config to listen on all interfaces (0.0.0.0)
3. ✅ Fixed OAuth authentication flow (token as query param)
4. ✅ Applied database migration for integrations_clio table
5. ✅ Both backend and frontend running correctly

## 🧪 Test the Clio Integration Now!

### Step 1: Update Clio Developer Console (Required!)
**⚠️ Do this before testing:**

1. Visit: https://app.clio.com/settings/developer_applications
2. Select your application
3. Add redirect URI: `http://127.0.0.1:8000/api/clio/callback`
4. Click Save

### Step 2: Open the Application
You can use either URL (both work now):
- http://127.0.0.1:5173 ✅
- http://localhost:5173 ✅

### Step 3: Log In
Use your existing credentials to log in.

### Step 4: Navigate to a Case
1. Go to "Cases" page
2. Click on any existing case, or create a new one

### Step 5: Connect to Clio
1. Scroll down to the "CLIO Integration" section
2. Click the "Connect to CLIO" button
3. Browser will redirect to Clio's authorization page
4. Log in to your Clio account (if needed)
5. Click "Authorize" to grant access
6. You'll be redirected back to your case page

### Step 6: Verify Connection
After authorization, you should see:
- ✅ "Connected to CLIO" status (green background)
- ✅ "Search & Import Matter" section appears below

### Step 7: Search for a Matter
1. In the search box, type a client name or matter number (minimum 3 characters)
2. Click "Search"
3. Results will appear showing your Clio matters

### Step 8: Import Matter Data
1. Click on a matter from the search results
2. Click "Import Data from CLIO"
3. Wait for import to complete
4. Documents, communications, and notes will be added to your case

## 🔍 Debugging

### Check Browser Console (F12)
Look for these logs:
```
Initiating Clio OAuth with token: eyJhbGci...
Checking Clio status with token: eyJhbGci...
API URL: http://127.0.0.1:8000
Response status: 200
```

### Check Backend Logs
```bash
tail -f backend_live.log
```

Look for:
- OAuth authorization requests
- Token exchange
- Database inserts into integrations_clio

### Verify Database
After connecting, check that tokens are stored:
```sql
SELECT user_id, clio_user_id, expires_at, created_at 
FROM integrations_clio;
```

## 📊 OAuth Flow

```
1. User clicks "Connect to CLIO"
   ↓
2. Frontend gets session token from Supabase
   ↓
3. Redirects to: /api/clio/authorize?token={session_token}
   ↓
4. Backend verifies token with Supabase
   ↓
5. Backend generates Clio OAuth URL with state
   ↓
6. Backend redirects to Clio: https://app.clio.com/oauth/authorize?...
   ↓
7. User logs in and authorizes on Clio
   ↓
8. Clio redirects to: /api/clio/callback?code=...&state=...
   ↓
9. Backend exchanges code for access & refresh tokens
   ↓
10. Backend stores tokens in integrations_clio table
    ↓
11. Backend redirects to: /app/cases/{case_id}
    ↓
12. Frontend detects connection and shows "Connected to CLIO"
```

## 🎯 What to Test

### Basic OAuth Flow
- [ ] Click "Connect to CLIO" button
- [ ] Redirected to Clio login page
- [ ] Can log in to Clio
- [ ] Can authorize the application
- [ ] Redirected back to case page
- [ ] Status shows "Connected to CLIO"

### Matter Search
- [ ] Search field appears when connected
- [ ] Can type in search field
- [ ] Search button is clickable
- [ ] Results appear after searching
- [ ] Can click on a result to select it

### Matter Import
- [ ] "Import Data from CLIO" button appears
- [ ] Can click import button
- [ ] Import completes without errors
- [ ] Documents appear in case
- [ ] Can view imported documents

### Disconnect
- [ ] "Disconnect" button appears when connected
- [ ] Can click disconnect
- [ ] Status changes to "Not connected"
- [ ] Search section disappears

## ⚠️ Common Issues

### "Redirect URI mismatch"
**Problem**: Clio developer console doesn't have the correct URI
**Solution**: Make sure you added `http://127.0.0.1:8000/api/clio/callback` exactly

### "Invalid authentication token"
**Problem**: Session expired or invalid
**Solution**: Log out and log back in

### "Failed to check Clio status"
**Problem**: Backend not running or database issue
**Solution**: Check `backend_live.log` for errors

### Search returns no results
**Problem**: API credentials incorrect or no matters in Clio
**Solution**: 
1. Verify CLIO_CLIENT_ID and CLIO_CLIENT_SECRET in .env
2. Check you have matters in your Clio account

### Import fails
**Problem**: Missing scopes or API error
**Solution**: Check backend logs for specific error message

## 📝 Environment Verification

### Backend .env should have:
```bash
CLIO_CLIENT_ID=your-client-id
CLIO_CLIENT_SECRET=your-client-secret
CLIO_REDIRECT_URI=http://127.0.0.1:8000/api/clio/callback
```

### Frontend .env should have:
```bash
PUBLIC_API_URL=http://127.0.0.1:8000
PUBLIC_SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## 🚀 Quick Commands

### Check if everything is running:
```bash
lsof -i:8000  # Backend should show python3
lsof -i:5173  # Frontend should show node
```

### Restart everything:
```bash
./stop_local_dev.sh
./start_local_dev.sh
```

### View logs in real-time:
```bash
tail -f backend_live.log frontend_live.log
```

## ✅ Success Indicators

You'll know it's working when:
1. ✅ "Connect to CLIO" button is visible and clickable
2. ✅ Clicking it redirects you to Clio (not an error page)
3. ✅ After authorizing on Clio, you're back at your case
4. ✅ Status shows "Connected to CLIO" with green background
5. ✅ Search box appears below the connection status
6. ✅ Searching returns results from your Clio account
7. ✅ Importing adds documents to the case

## 🎊 You're Ready!

Everything is configured and running. Just need to:
1. Update Clio Developer Console (one time)
2. Open http://127.0.0.1:5173 or http://localhost:5173
3. Start testing!

Good luck! 🚀

