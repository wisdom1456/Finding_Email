# Clio OAuth Setup - Fixed! ✅

## Changes Made

### 1. Updated to use 127.0.0.1 instead of localhost
Clio prefers `127.0.0.1` over `localhost` for redirect URIs.

### 2. Fixed Authentication Flow
The `/authorize` endpoint now accepts the session token as a query parameter instead of requiring the Authorization header. This is necessary because direct browser navigation (`window.location.href`) cannot set custom headers.

### 3. Updated Environment Variables
- Root `.env`: `CLIO_REDIRECT_URI=http://127.0.0.1:8000/api/clio/callback`
- Frontend `.env`: `PUBLIC_API_URL=http://127.0.0.1:8000`

## Required: Update Clio Developer Console

**⚠️ IMPORTANT:** You must update your Clio application's redirect URI!

### Steps:

1. **Go to Clio Developer Console**
   - Visit: https://app.clio.com/settings/developer_applications
   - Log in with your Clio account

2. **Select Your Application**
   - Click on your application name in the list

3. **Update Redirect URIs**
   - Find the "Redirect URIs" section
   - **Add** (don't replace): `http://127.0.0.1:8000/api/clio/callback`
   - You can keep the localhost one too for compatibility: `http://localhost:8000/api/clio/callback`
   - Click "Save"

4. **For Production Deployment**
   - Also add: `https://your-app.vercel.app/api/clio/callback`
   - Replace `your-app` with your actual Vercel domain

## Testing the Fix

### 1. Restart Frontend Server
```bash
# In your frontend terminal, press Ctrl+C then:
cd frontend
npm run dev
```

### 2. Clear Browser Cache (Optional but Recommended)
- Press F12 (DevTools)
- Right-click the refresh button
- Select "Empty Cache and Hard Reload"

### 3. Test the Connection Flow

1. Navigate to `http://127.0.0.1:5173` (NOT localhost)
2. Log in to your app
3. Go to a case detail page
4. Scroll to "CLIO Integration" section
5. Click "Connect to CLIO"
6. You should be redirected to Clio's authorization page
7. Log in and authorize
8. You'll be redirected back to your case page
9. Status should show "Connected to CLIO"

### Expected Console Output

Open browser DevTools (F12) → Console tab. You should see:
```
Initiating Clio OAuth with token: eyJhbGciOiJIUzI1N...
```

Then you'll be redirected to Clio.

## OAuth Flow Diagram

```
1. User clicks "Connect to CLIO"
   ↓
2. Frontend: Gets session token from Supabase
   ↓
3. Frontend: Redirects to /api/clio/authorize?token=...
   ↓
4. Backend: Verifies token with Supabase
   ↓
5. Backend: Generates Clio OAuth URL with state
   ↓
6. Backend: Redirects user to Clio authorization page
   ↓
7. User: Logs in to Clio and authorizes
   ↓
8. Clio: Redirects to /api/clio/callback?code=...&state=...
   ↓
9. Backend: Exchanges code for access & refresh tokens
   ↓
10. Backend: Stores tokens in integrations_clio table
    ↓
11. Backend: Redirects back to case page
    ↓
12. Frontend: Shows "Connected to CLIO"
```

## Troubleshooting

### Still getting "Not authenticated"?
- Make sure you're accessing the app at `http://127.0.0.1:5173` (not localhost)
- Clear browser cookies and cache
- Make sure you restarted the frontend server after env changes

### "Redirect URI mismatch" error?
- Verify the redirect URI in Clio console matches exactly: `http://127.0.0.1:8000/api/clio/callback`
- No trailing slashes!
- Check for typos

### Backend still using localhost?
- Restart the backend server to pick up the new CLIO_REDIRECT_URI
- The backend auto-detects and replaces localhost with 127.0.0.1

### OAuth succeeds but no connection status?
- Check browser console for errors
- Verify the integrations_clio table has data:
  ```sql
  SELECT * FROM integrations_clio;
  ```

## Security Note

The session token is passed as a query parameter for the initial OAuth redirect only. This is necessary because:
1. Direct browser navigation can't set Authorization headers
2. The token is only used server-side to verify the user
3. The actual OAuth tokens (access/refresh) are stored securely in the database
4. All subsequent API calls use proper Authorization headers

## Success Checklist

- [ ] Updated Clio Developer Console redirect URI
- [ ] Restarted frontend dev server
- [ ] Accessing app at 127.0.0.1 (not localhost)
- [ ] Can click "Connect to CLIO" without errors
- [ ] Redirected to Clio authorization page
- [ ] After authorization, redirected back to app
- [ ] Status shows "Connected to CLIO"
- [ ] Can search Clio matters
- [ ] Can import matter data

Once all items are checked, your Clio integration is working! 🎉

