# Fix: "Chat AI Load Failed" Error on Vercel

## Problem
When you press Enter in the Case Chat, you get "load failed" error.

## Root Cause
The chat feature requires OpenAI API access. This error typically means:
1. `OPENAI_API_KEY` is missing or invalid in Vercel
2. The API endpoint is timing out (less likely with 300s timeout)
3. The backend can't load required dependencies

## Solution Steps

### Step 1: Verify OpenAI API Key in Vercel

1. Go to https://vercel.com
2. Select your project (`finding-emails` or similar)
3. Click **Settings** → **Environment Variables**
4. Check if `OPENAI_API_KEY` exists

**If missing, add it:**
- Name: `OPENAI_API_KEY`
- Value: `sk-proj-...` (your OpenAI API key from https://platform.openai.com/api-keys)
- Environment: Select **Production**, **Preview**, and **Development**
- Click **Save**

**If it exists:**
- Click the **Edit** button (pencil icon)
- Verify the key is correct (should start with `sk-` or `sk-proj-`)
- Test it on OpenAI's platform to ensure it's valid

### Step 2: Check Required Environment Variables

Ensure ALL these are set in Vercel:

**Backend Variables (Required):**
```
OPENAI_API_KEY=sk-proj-your-key-here
SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
SUPABASE_SERVICE_KEY=eyJ... (service_role key)
SUPABASE_ANON_KEY=eyJ... (anon key)
```

**Frontend Variables (Required):**
```
PUBLIC_SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
PUBLIC_SUPABASE_ANON_KEY=eyJ... (anon key)
```

**Optional Variables:**
```
PUBLIC_API_URL=(leave empty or remove for Vercel - it will use relative paths)
```

### Step 3: Redeploy After Adding Variables

**Important:** Environment variables only take effect after redeployment!

1. Go to **Deployments** tab
2. Find your latest deployment
3. Click the **...** menu → **Redeploy**
4. ✅ Check "Use existing Build Cache" (faster)
5. Click **Redeploy**
6. Wait for deployment to complete (~2-5 minutes)

### Step 4: Test the Fix

After redeployment:

1. Open your Vercel app: `https://your-app.vercel.app`
2. Navigate to a case with analysis results
3. Click the **Case Chat** tab
4. Type a question and press Enter
5. You should see a response instead of "load failed"

## Debugging Steps

### Check Vercel Function Logs

If it still fails:

1. Go to Vercel Dashboard → **Deployments**
2. Click on your latest deployment
3. Click **Functions** tab
4. Find `/api/index.py` function
5. Click to see the logs
6. Look for errors like:
   - `"OPENAI_API_KEY is required"`
   - `"Rate limit error"`
   - `"Invalid API key"`
   - `"Module not found"`

### Check Browser Console

1. Press F12 to open Developer Tools
2. Go to **Console** tab
3. Try sending a chat message
4. Look for the error response
5. Check the **Network** tab:
   - Find the `/api/analysis/chat` request
   - Click it to see the response
   - Look at the status code and error message

### Common Error Messages and Fixes

#### Error: "OPENAI_API_KEY is required"
**Fix:** Add `OPENAI_API_KEY` to Vercel environment variables and redeploy

#### Error: "Invalid API key"
**Fix:** 
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Update `OPENAI_API_KEY` in Vercel
4. Redeploy

#### Error: "Rate limit exceeded"
**Fix:** 
- Wait a few minutes (OpenAI has rate limits)
- Or upgrade your OpenAI plan if you hit limits frequently

#### Error: "Not authenticated" or 401
**Fix:**
- Log out and log back in
- Check if `SUPABASE_SERVICE_KEY` is set correctly in Vercel

#### Error: "Case chat requires the latest analysis"
**Fix:**
- This case was analyzed with an older version
- Re-run the analysis on this case
- The chat feature requires `multi_stage_result` data

#### Error: Module import errors
**Fix:**
- Check that `api/requirements.txt` includes all dependencies
- Redeploy to rebuild Python packages

### Step 5: Verify OpenAI API Key is Valid

Test your OpenAI key locally:

```bash
# On your computer
cd /Users/BRFlorida/Projects/Work/Finding_Emails
source venv/bin/activate
python -c "import os; from openai import OpenAI; client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')); print('API Key is valid!')"
```

If this works locally but not on Vercel, the issue is definitely with Vercel environment variables.

## Quick Checklist

- [ ] `OPENAI_API_KEY` is set in Vercel environment variables
- [ ] Key is valid (test on OpenAI platform)
- [ ] All other required environment variables are set
- [ ] Environment variables are enabled for Production/Preview/Development
- [ ] Project has been redeployed after adding variables
- [ ] Waited for deployment to complete (check deployment status)
- [ ] Cleared browser cache and refreshed the page
- [ ] Checked Vercel function logs for specific errors

## Still Not Working?

### Check Timeout Issues

The chat endpoint has a 300-second (5 minute) timeout configured in `vercel.json`. If responses take longer:

1. Check Vercel function logs for timeout errors
2. Consider using a streaming approach (SSE) for long responses
3. Or increase timeout in `vercel.json` (max is 300s on Pro plan)

### Check Dependencies

Ensure `api/requirements.txt` has:
```txt
openai>=1.0.0
httpx
pydantic
fastapi
python-dotenv
```

### Check Python Path Issues

The `api/index.py` file configures the Python path. Verify it's loading correctly:

```python
# In api/index.py
import sys
print("Python path:", sys.path)  # Add this temporarily
from legal_portal.api.main import app
```

Then check Vercel function logs to see if the path is correct.

## Need More Help?

If none of these steps work, please:

1. Share the error from Vercel function logs
2. Share the error from browser console
3. Confirm which environment variables are set in Vercel
4. Confirm the deployment succeeded without build errors

## For Testing Locally (Not Vercel)

If you want to test locally to verify it works:

```bash
# Terminal 1: Start backend
cd /Users/BRFlorida/Projects/Work/Finding_Emails
source venv/bin/activate
cd src
uvicorn legal_portal.api.main:app --reload --port 8000

# Terminal 2: Start frontend
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev

# Open: http://localhost:5173
```

If it works locally but not on Vercel, the issue is definitely environment variables or deployment configuration.

