# Visual Guide: Adding Environment Variables to Vercel

## The Error You're Seeing

```
500: INTERNAL_SERVER_ERROR
Code: FUNCTION_INVOCATION_FAILED
```

**What it means:** The Python backend can't start because it's missing environment variables.

---

## Step-by-Step Visual Guide

### Step 1: Open Vercel Dashboard

1. Go to: https://vercel.com/dashboard
2. Find your project: **finding-emails**
3. Click on the project name

```
┌─────────────────────────────────────────┐
│  Vercel Dashboard                       │
├─────────────────────────────────────────┤
│                                         │
│  Your Projects:                         │
│                                         │
│  ┌───────────────────────────────┐     │
│  │  finding-emails  [Click Here] │     │
│  │  Last deployed: 2m ago        │     │
│  └───────────────────────────────┘     │
│                                         │
└─────────────────────────────────────────┘
```

### Step 2: Navigate to Environment Variables

1. Click **Settings** in the top navigation bar
2. Click **Environment Variables** in the left sidebar

```
┌─────────────────────────────────────────┐
│  Overview  Deployments  [Settings] ←──  │
├─────────────────────────────────────────┤
│  General                                │
│  Domains                                │
│  Git                                    │
│  [Environment Variables] ←─────────────│
│  Serverless Functions                   │
│  Edge Network                           │
└─────────────────────────────────────────┘
```

### Step 3: Add Environment Variables

Click the **"Add New"** button (top right)

For **each** of the 3 required variables, add:

#### Variable 1: SUPABASE_URL

```
┌─────────────────────────────────────────┐
│  Add Environment Variable               │
├─────────────────────────────────────────┤
│  Key:                                   │
│  ┌───────────────────────────────────┐ │
│  │ SUPABASE_URL                      │ │
│  └───────────────────────────────────┘ │
│                                         │
│  Value:                                 │
│  ┌───────────────────────────────────┐ │
│  │ https://nqjepycmhddfekeufcle...  │ │
│  └───────────────────────────────────┘ │
│                                         │
│  Environments to Add:                   │
│  ☑ Production                           │
│  ☑ Preview                              │
│  ☑ Development                          │
│                                         │
│            [Save] ←─────────────────── │
└─────────────────────────────────────────┘
```

Click **Save**

#### Variable 2: SUPABASE_SERVICE_KEY

```
┌─────────────────────────────────────────┐
│  Add Environment Variable               │
├─────────────────────────────────────────┤
│  Key:                                   │
│  ┌───────────────────────────────────┐ │
│  │ SUPABASE_SERVICE_KEY              │ │
│  └───────────────────────────────────┘ │
│                                         │
│  Value:                                 │
│  ┌───────────────────────────────────┐ │
│  │ eyJhbGciOiJIUzI1NiIsInR5cCI6... │ │
│  └───────────────────────────────────┘ │
│                                         │
│  Environments to Add:                   │
│  ☑ Production                           │
│  ☑ Preview                              │
│  ☑ Development                          │
│                                         │
│            [Save] ←─────────────────── │
└─────────────────────────────────────────┘
```

**⚠️ Important:** This is the **service_role** key from Supabase (not anon key)

Click **Save**

#### Variable 3: SUPABASE_ANON_KEY

```
┌─────────────────────────────────────────┐
│  Add Environment Variable               │
├─────────────────────────────────────────┤
│  Key:                                   │
│  ┌───────────────────────────────────┐ │
│  │ SUPABASE_ANON_KEY                 │ │
│  └───────────────────────────────────┘ │
│                                         │
│  Value:                                 │
│  ┌───────────────────────────────────┐ │
│  │ eyJhbGciOiJIUzI1NiIsInR5cCI6... │ │
│  └───────────────────────────────────┘ │
│                                         │
│  Environments to Add:                   │
│  ☑ Production                           │
│  ☑ Preview                              │
│  ☑ Development                          │
│                                         │
│            [Save] ←─────────────────── │
└─────────────────────────────────────────┘
```

**Info:** This is the **anon/public** key from Supabase

Click **Save**

### Step 4: Verify Variables Are Saved

After adding all 3, you should see:

```
┌─────────────────────────────────────────┐
│  Environment Variables                  │
├─────────────────────────────────────────┤
│                                         │
│  SUPABASE_URL                           │
│  https://nqjepycmhddfekeufcle...       │
│  Production, Preview, Development       │
│  [Edit]                                 │
│                                         │
│  SUPABASE_SERVICE_KEY                   │
│  eyJhbGciOiJ... (hidden)                │
│  Production, Preview, Development       │
│  [Edit]                                 │
│                                         │
│  SUPABASE_ANON_KEY                      │
│  eyJhbGciOiJ... (hidden)                │
│  Production, Preview, Development       │
│  [Edit]                                 │
│                                         │
└─────────────────────────────────────────┘
```

✅ You should have **at least 3 variables** listed

### Step 5: Redeploy

1. Click **Deployments** (top navigation)
2. Find your latest deployment
3. Click the **⋯** (three dots) menu
4. Click **Redeploy**

```
┌─────────────────────────────────────────┐
│  Deployments                            │
├─────────────────────────────────────────┤
│                                         │
│  finding-emails-ohb2klnln               │
│  2 minutes ago · Production             │
│  ┌──────────┐                           │
│  │  Visit   │  [⋯] ←─────────────────  │
│  └──────────┘     │                     │
│                   ▼                     │
│          ┌─────────────────┐            │
│          │ Redeploy     ←──┤            │
│          │ View Logs       │            │
│          │ Promote         │            │
│          └─────────────────┘            │
│                                         │
└─────────────────────────────────────────┘
```

Click **Redeploy** → Confirm by clicking **Redeploy** again

### Step 6: Wait for Deployment

```
┌─────────────────────────────────────────┐
│  Deployment Status                      │
├─────────────────────────────────────────┤
│                                         │
│  🔨 Building...                         │
│  ⏳ This usually takes 1-2 minutes      │
│                                         │
│  ┌──────────────────────────────┐      │
│  │ ▓▓▓▓▓▓▓▓░░░░░░░░ 50%         │      │
│  └──────────────────────────────┘      │
│                                         │
└─────────────────────────────────────────┘
```

Wait for the status to change to **✅ Ready**

### Step 7: Test Your App

1. Click **Visit** to open your deployed app
2. Log in
3. Click the Clio button

**Expected Result:**

```
Before (with error):
❌ 500: INTERNAL_SERVER_ERROR

After (fixed):
✅ "Connect to Clio" button works
✅ No more 500 errors
✅ Backend responds correctly
```

---

## Where to Find Supabase Keys

### Open Supabase Dashboard

1. Go to: https://supabase.com/dashboard
2. Select your project
3. Click **Settings** (gear icon) → **API**

### Copy the Keys

```
┌─────────────────────────────────────────┐
│  Supabase API Settings                  │
├─────────────────────────────────────────┤
│                                         │
│  Project URL                            │
│  ┌───────────────────────────────────┐ │
│  │ https://nqjepycmhddfekeufcle...  │ │ ←─ Copy this for SUPABASE_URL
│  └───────────────────────────────────┘ │
│                                         │
│  Project API keys                       │
│                                         │
│  anon public                            │
│  ┌───────────────────────────────────┐ │
│  │ eyJhbGciOiJIUzI1NiIsInR5cCI6... │ │ ←─ Copy for SUPABASE_ANON_KEY
│  └───────────────────────────────────┘ │
│                                         │
│  service_role secret                    │
│  ┌───────────────────────────────────┐ │
│  │ [Reveal] ←───────────────────────┤ │ ←─ Click to reveal
│  └───────────────────────────────────┘ │
│  ┌───────────────────────────────────┐ │
│  │ eyJhbGciOiJIUzI1NiIsInR5cCI6... │ │ ←─ Copy for SUPABASE_SERVICE_KEY
│  └───────────────────────────────────┘ │
│                                         │
└─────────────────────────────────────────┘
```

---

## Troubleshooting

### ❌ "Environment variable already exists"

**Solution:** Edit the existing variable instead of adding a new one.

### ❌ Still getting 500 error after redeploy

**Solutions:**
1. ✅ Check all 3 checkboxes (Production, Preview, Development)
2. ✅ Click "Save" after each variable
3. ✅ Wait for deployment to fully complete (check Deployments tab)
4. ✅ Try in incognito/private window to avoid cache
5. ✅ Run the test script: `./test_vercel_env.sh`

### ❌ Can't find service_role key

**Solution:**
1. Go to Supabase Dashboard → Settings → API
2. Scroll to "Project API keys"
3. Look for **"service_role"** with label "secret"
4. Click the eye icon or "Reveal" button to see the key
5. **This is different from the anon key** - it should be much longer

---

## Quick Test

After completing the steps, run this command to verify:

```bash
./test_vercel_env.sh
```

Or visit this URL in your browser:

```
https://your-vercel-url.vercel.app/api/health
```

**Expected Response (Success):**

```json
{
  "status": "healthy",
  "service": "Legal Document Analysis API",
  "version": "1.0.0",
  "environment": {
    "required_vars_set": true,
    "missing_required": null,
    "missing_optional": ["OPENAI_API_KEY", "CLIO_CLIENT_ID"]
  }
}
```

**Expected Response (Still Missing Variables):**

```json
{
  "status": "unhealthy",
  "service": "Legal Document Analysis API",
  "version": "1.0.0",
  "environment": {
    "required_vars_set": false,
    "missing_required": ["SUPABASE_SERVICE_KEY"],
    "missing_optional": ["OPENAI_API_KEY", "CLIO_CLIENT_ID"]
  }
}
```

---

## Summary Checklist

- [ ] Added `SUPABASE_URL` to Vercel (all 3 environments checked)
- [ ] Added `SUPABASE_SERVICE_KEY` to Vercel (all 3 environments checked)
- [ ] Added `SUPABASE_ANON_KEY` to Vercel (all 3 environments checked)
- [ ] Clicked "Save" after each variable
- [ ] Redeployed the application
- [ ] Waited for deployment to complete
- [ ] Tested the app (no more 500 error)
- [ ] Clio button works correctly

---

**Need more help?** See `QUICK_FIX_STEPS.md` for detailed instructions.

