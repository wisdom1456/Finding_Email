# Vercel Environment Variables Fix

## Issue

The frontend is now correctly using relative paths (`/api/clio/status`), but the Python backend is returning a **500 Internal Server Error**. This is because the backend environment variables are not set in Vercel.

## Root Cause

When Vercel runs the Python backend (`/api/index.py`), it needs access to environment variables like:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_ANON_KEY`
- `CLIO_CLIENT_ID`
- `CLIO_CLIENT_SECRET`
- `OPENAI_API_KEY`

These variables are used by the FastAPI backend to connect to Supabase, authenticate users, and make API calls.

## Solution: Add Backend Environment Variables to Vercel

### Step 1: Open Vercel Project Settings

1. Go to [vercel.com](https://vercel.com)
2. Select your project: `finding-emails`
3. Click **Settings** (top navigation)
4. Click **Environment Variables** (left sidebar)

### Step 2: Add Required Environment Variables

Add the following environment variables. Make sure to select **Production**, **Preview**, and **Development** for each:

#### Supabase Configuration (Required for Backend)

```env
SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
```

```env
SUPABASE_SERVICE_KEY=your-service-role-key-here
```

**⚠️ Important:** This is your Supabase **Service Role** key (not the anon key). Find it in:

- Supabase Dashboard → Project Settings → API → `service_role` key (secret)

```env
SUPABASE_ANON_KEY=your-anon-key-here
```

**Info:** This is your Supabase **anon/public** key. Find it in:

- Supabase Dashboard → Project Settings → API → `anon` key (public)

#### Clio Integration (Required for Clio Features)

```env
CLIO_CLIENT_ID=your-clio-client-id
```

```env
CLIO_CLIENT_SECRET=your-clio-client-secret
```

**Info:** Get these from [Clio Developer Console](https://app.clio.com/settings/developer_applications)

#### OpenAI API (Required for AI Analysis)

```env
OPENAI_API_KEY=sk-your-openai-key-here
```

**Info:** Get this from [OpenAI Platform](https://platform.openai.com/api-keys)

### Step 3: Verify Frontend Environment Variables

The frontend also needs these variables (you may have already set them):

#### Frontend-Specific Variables

```env
PUBLIC_SUPABASE_URL=https://nqjepycmhddfekeufcle.supabase.co
```

```env
PUBLIC_SUPABASE_ANON_KEY=your-anon-key-here
```

```env
PUBLIC_API_URL=https://your-vercel-domain.vercel.app
```

**⚠️ Important:** Set this to your actual Vercel deployment URL (e.g., `https://finding-emails-63ovbt3ec-wisdom1456s-projects.vercel.app`)

**However**, based on our recent fixes, the frontend should work with an **empty string** for `PUBLIC_API_URL` when deployed on Vercel, as it will use relative paths. You can try **removing** `PUBLIC_API_URL` from Vercel environment variables entirely, or set it to an empty string.

### Step 4: Redeploy

After adding environment variables:

1. Go to **Deployments** tab in Vercel
2. Click the **...** menu on your latest deployment
3. Click **Redeploy**
4. Check **Use existing Build Cache** (optional, but faster)
5. Click **Redeploy**

### Step 5: Verify the Fix

After redeployment:

1. Open your Vercel app in the browser
2. Open Browser Console (F12)
3. Try clicking the Clio button
4. You should see:
   - ✅ `Using status endpoint: /api/clio/status` (relative path)
   - ✅ `200 OK` response (instead of 500)
   - ✅ Clio connection status displayed

## Quick Verification Checklist

- [ ] Backend environment variables added to Vercel:
  - [ ] `SUPABASE_URL`
  - [ ] `SUPABASE_SERVICE_KEY`
  - [ ] `SUPABASE_ANON_KEY`
  - [ ] `CLIO_CLIENT_ID`
  - [ ] `CLIO_CLIENT_SECRET`
  - [ ] `OPENAI_API_KEY`

- [ ] Frontend environment variables added to Vercel:
  - [ ] `PUBLIC_SUPABASE_URL`
  - [ ] `PUBLIC_SUPABASE_ANON_KEY`
  - [ ] `PUBLIC_API_URL` (optional - can be removed or set to empty string)

- [ ] Redeployed the project

- [ ] Tested Clio button in deployed app

## Common Issues

### Issue 1: Still Getting 500 Error

**Cause:** Environment variables not properly saved or not applied to the deployment.

**Fix:**
1. Double-check that all variables are saved
2. Ensure they are enabled for **Production**, **Preview**, and **Development**
3. Try a **hard redeploy** (clear cache and redeploy)

### Issue 2: CORS Error Returns

**Cause:** `PUBLIC_API_URL` is set to the Supabase URL or another domain.

**Fix:**
1. In Vercel, set `PUBLIC_API_URL` to your Vercel domain OR remove it entirely
2. The frontend will then use relative paths which Vercel rewrites to the backend

### Issue 3: 401 Unauthorized

**Cause:** The user's session token is invalid or expired.

**Fix:**
1. Log out and log back in
2. Check if Supabase Auth is working correctly

## Security Notes

- **Never commit** `.env` files with real credentials
- **Service Role Key** should only be used server-side (Python backend)
- **Anon Key** is safe to use client-side with RLS policies
- **API Keys** (OpenAI, Clio) should never be exposed to the client

## Next Steps

After environment variables are set and the app is redeployed:

1. Test all Clio features:
   - Connection status check
   - Connect to Clio (OAuth flow)
   - Search Clio matters
   - Import Clio data

2. Test other features:
   - Document upload
   - AI analysis
   - Case management

3. Monitor Vercel logs for any errors:
   - Go to **Deployments** → Select deployment → **Functions** tab
   - Check runtime logs for `/api/index.py`

## Need Help?

If you continue to see errors after following these steps:

1. Check Vercel Function Logs:
   - Deployments → Latest → Functions → `/api/index.py`
   - Look for specific error messages

2. Check Browser Console:
   - F12 → Console tab
   - Look for network errors or JavaScript errors

3. Verify Supabase credentials are correct:
   - Test them locally first
   - Ensure RLS policies are set correctly

