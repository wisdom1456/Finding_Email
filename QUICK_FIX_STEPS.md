# Quick Fix for Vercel 500 Error

## The Problem

Your Python backend is crashing because it's missing required environment variables in Vercel. The error `FUNCTION_INVOCATION_FAILED` means the serverless function crashed on startup.

## The Solution (5 Minutes)

### Step 1: Get Your Supabase Credentials

1. Open [Supabase Dashboard](https://supabase.com/dashboard)
2. Select your project (the one with URL: `nqjepycmhddfekeufcle.supabase.co`)
3. Go to **Project Settings** (gear icon in sidebar)
4. Click **API** tab
5. Copy these values:
   - **Project URL**: `https://nqjepycmhddfekeufcle.supabase.co`
   - **anon/public key**: (labeled as `anon public`)
   - **service_role key**: (labeled as `service_role secret` - click "Reveal" to see it)

### Step 2: Add Environment Variables to Vercel

1. Open [Vercel Dashboard](https://vercel.com/dashboard)
2. Select your project: `finding-emails`
3. Click **Settings** (top navigation)
4. Click **Environment Variables** (left sidebar)
5. Add each variable below by clicking **Add New**:

**Add these 3 REQUIRED variables:**

| Variable Name | Value | Environments |
|--------------|-------|--------------|
| `SUPABASE_URL` | `https://nqjepycmhddfekeufcle.supabase.co` | ✅ Production, ✅ Preview, ✅ Development |
| `SUPABASE_SERVICE_KEY` | (paste your service_role key from Supabase) | ✅ Production, ✅ Preview, ✅ Development |
| `SUPABASE_ANON_KEY` | (paste your anon/public key from Supabase) | ✅ Production, ✅ Preview, ✅ Development |

**Add these OPTIONAL variables (for full functionality):**

| Variable Name | Value | Environments |
|--------------|-------|--------------|
| `CLIO_CLIENT_ID` | (your Clio client ID) | ✅ Production, ✅ Preview, ✅ Development |
| `CLIO_CLIENT_SECRET` | (your Clio client secret) | ✅ Production, ✅ Preview, ✅ Development |
| `OPENAI_API_KEY` | (your OpenAI API key) | ✅ Production, ✅ Preview, ✅ Development |

### Step 3: Redeploy

1. Go to **Deployments** tab (top navigation)
2. Find your latest deployment
3. Click the **⋯** (three dots) menu
4. Click **Redeploy**
5. Click **Redeploy** again to confirm

### Step 4: Test

After the redeployment finishes (1-2 minutes):

1. Open your app: `https://finding-emails-ohb2klnln-wisdom1456s-projects.vercel.app`
2. Log in
3. Click the Clio button
4. You should see:
   - ✅ No more 500 error
   - ✅ "Connect to Clio" or connection status

## Why This Happened

The Python backend needs these environment variables to:
- Connect to Supabase database
- Authenticate users
- Make API calls

Without them, the serverless function crashes immediately with a 500 error.

## Troubleshooting

### Issue: Still getting 500 error after redeploy

**Solution:**
1. Make sure you selected **all 3 environments** (Production, Preview, Development) for each variable
2. Click "Save" after adding each variable
3. Wait for the full redeployment to complete (check the Deployments tab)
4. Try in an incognito window to avoid cache

### Issue: Can't find service_role key in Supabase

**Solution:**
1. In Supabase Dashboard → Project Settings → API
2. Look for "Project API keys" section
3. The `service_role` key is marked as "secret"
4. Click the eye icon or "Reveal" to see it
5. **Important:** This is different from the `anon` key

### Issue: Vercel shows "Environment variable already exists"

**Solution:**
- Click on the existing variable to edit it
- Update the value
- Make sure all environments are checked

## Quick Verification

After adding variables and redeploying, you should see:

```
✅ SUPABASE_URL set
✅ SUPABASE_SERVICE_KEY set (starts with 'eyJ...')
✅ SUPABASE_ANON_KEY set (starts with 'eyJ...')
```

In Vercel Settings → Environment Variables.

## Next Steps

Once the 500 error is fixed:

1. **Test Clio Integration**:
   - Click "Connect to Clio"
   - Complete OAuth flow
   - Search for matters

2. **Test Document Upload**:
   - Create a case
   - Upload documents
   - Run analysis

3. **Monitor for Errors**:
   - Check Vercel Function Logs
   - Check Browser Console
   - Report any new issues

## Security Note

⚠️ **Never share** your `SUPABASE_SERVICE_KEY` or API keys publicly. These are in Vercel environment variables and are kept secure server-side.

## Need More Help?

If you're still seeing errors after following these steps:

1. **Check Vercel Function Logs**:
   - Vercel Dashboard → Deployments → Latest → Functions
   - Click on `/api/index.py` to see runtime logs
   - Look for specific error messages

2. **Check if variables are set**:
   - Vercel Dashboard → Settings → Environment Variables
   - Count should be at least 3 (SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY)

3. **Verify Supabase credentials**:
   - Try using them locally first
   - Run `python scripts/test_supabase_connection.py` from project root

