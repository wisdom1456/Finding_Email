# Debug Instructions - RLS Error Investigation

## Current Status

I've added comprehensive debug logging to track the RLS authentication flow. However, I need your help to identify where the error is occurring.

## Where to Check for the Error

### 1. Frontend Browser Console

**Steps:**
1. Open http://localhost:5173 in your browser
2. Open Developer Tools (F12 or Right-click → Inspect)
3. Go to the **Console** tab
4. Try to create a case
5. **Look for any red error messages**

**What to share:**
- Screenshot or text of any errors in the console
- The full error message
- Any network request failures (check Network tab)

### 2. Frontend Network Tab

**Steps:**
1. Open Developer Tools (F12)
2. Go to the **Network** tab
3. Try to create a case
4. Look for the POST request to `/api/cases`
5. Click on it and check:
   - **Status code** (should be 201 if successful)
   - **Response** tab - what error message?
   - **Headers** tab - is Authorization header present?

**What to share:**
- Status code of the request
- Response body (the error message)
- Request headers (especially Authorization)

### 3. Backend Terminal Output

The backend should now print debug statements when you create a case. 

**Steps:**
1. Open a new terminal
2. Run: `tail -f /Users/BRFlorida/Projects/Work/Finding_Emails/backend.log`
3. In another window, try to create a case in the browser
4. Watch for debug output like:
   ```
   🔍 DEBUG get_user_supabase_client:
     - SUPABASE_URL: ...
     - User Token: ...
   
   🔍 DEBUG create_case endpoint:
     - User ID from token: ...
     - Attempting to insert case...
   ```

**What to share:**
- All debug output that appears
- Any error messages

## Quick Tests

### Test 1: API Direct Test (Bypasses Frontend)

This test worked previously. Run it again to confirm:

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 scripts/debug_create_case.py
```

**Expected:** Status: 201 (success)

If this WORKS but the frontend FAILS, the issue is in the frontend, not the backend.

### Test 2: Frontend Login Test

1. Go to http://localhost:5173/login
2. Try to login with:
   - Email: testuser123@gmail.com
   - Password: TestPassword123!
3. Does login work?
4. Can you see the dashboard?

## What I Need From You

Please run the tests above and provide:

1. **Exact error message** you're seeing
2. **Where** you're seeing it (browser console, UI alert, backend logs)
3. **When** it happens (after clicking "Create Case"? During page load?)
4. **Browser console output** (F12 → Console tab)
5. **Network request details** (F12 → Network tab → POST /api/cases)
6. **Backend debug output** (from terminal or backend.log)

## Current Debug Features

I've added debug logging to:

### `dependencies.py` → `get_user_supabase_client()`
Prints:
- SUPABASE_URL (first 40 chars)
- SUPABASE_ANON_KEY status
- User token (first 20 chars)
- Authorization header being set

### `routes/cases.py` → `create_case()`
Prints:
- User ID from token
- User email
- Case data being sent
- Authorization header in client
- Profile existence check
- Success or failure with full error details

## Example of What I'm Looking For

**Good error report:**
```
"I'm seeing this error in the browser console when I click Create Case:

POST http://localhost:8000/api/cases 500 (Internal Server Error)

Response body:
{
  "detail": "new row violates row-level security policy for table \"cases\""
}

In the backend logs I see:
🔍 DEBUG get_user_supabase_client:
  - User Token (first 20 chars): eyJhbGc... 
❌ ERROR in create_case:
  - Exception message: new row violates row-level security policy
"
```

## Possible Scenarios

### Scenario A: Error is in Frontend
- The debug script works (Status 201)
- But browser UI shows error
- **Issue:** Frontend is not sending token correctly

### Scenario B: Error is in Backend RLS
- Both frontend and script fail
- Backend logs show RLS violation
- **Issue:** Token not being applied correctly to Supabase client

### Scenario C: User/Profile Issue
- Profile doesn't exist for the user
- RLS policy requires valid user_id
- **Issue:** Profile creation trigger not working

### Scenario D: Frontend not hitting backend
- No backend logs appear
- Frontend shows error immediately
- **Issue:** CORS or network issue

## Next Steps Based on Your Report

Once you provide the information above, I can:
1. Identify the exact failure point
2. Apply the specific fix needed
3. Verify it works end-to-end

---

**Please run the tests and share the outputs!** 🙏

