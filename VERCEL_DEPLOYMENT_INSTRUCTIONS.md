# Vercel Deployment Instructions

This guide will help you deploy the Legal Document Analysis Portal to Vercel.

## Changes Made for Vercel Deployment

### 1. Frontend Configuration
- ✅ Added `@sveltejs/adapter-vercel` to package.json
- ✅ Updated `svelte.config.js` to use Vercel adapter
- ✅ Created auth callback route at `frontend/src/routes/auth/callback/+server.ts`
- ✅ Created `frontend/ENV_SETUP.md` for environment variable documentation

### 2. Backend Configuration
- ✅ Updated `src/legal_portal/api/main.py` to auto-detect Vercel URL for CORS
- ✅ Updated `src/legal_portal/api/routes/clio.py` to use Vercel URL for OAuth redirects
- ✅ Clio auth service already supports Vercel URL detection

### 3. Build Configuration
- ✅ Updated `vercel.json` with correct build settings for monorepo

## Deployment Steps

### Step 1: Install Dependencies

```bash
cd frontend
npm install
```

This will install the new `@sveltejs/adapter-vercel` package.

### Step 2: Deploy to Vercel

**Option A: Using Vercel CLI (Recommended)**

```bash
# Install Vercel CLI if not already installed
npm install -g vercel

# Deploy from project root
cd /Users/BRFlorida/Projects/Work/Finding_Emails
vercel
```

Follow the prompts:
- Link to your Vercel account
- Set up as a new project or link to existing
- Accept default settings
- Deploy

**Option B: Using Vercel Dashboard**

1. Go to [vercel.com](https://vercel.com)
2. Click "Add New Project"
3. Import your Git repository
4. Vercel will auto-detect SvelteKit
5. No need to change build settings (vercel.json handles this)
6. Click "Deploy"

### Step 3: Configure Environment Variables in Vercel

After deployment, configure these environment variables in Vercel Dashboard:

**Go to: Project Settings > Environment Variables**

#### Backend Variables (for API routes)
```
SUPABASE_URL=https://your-branch-ref.supabase.co
SUPABASE_SERVICE_KEY=your-branch-service-key
SUPABASE_ANON_KEY=your-branch-anon-key
OPENAI_API_KEY=your-openai-key
CLIO_CLIENT_ID=your-clio-client-id
CLIO_CLIENT_SECRET=your-clio-client-secret
```

#### Frontend Variables (PUBLIC_ prefix)
```
PUBLIC_SUPABASE_URL=https://your-branch-ref.supabase.co
PUBLIC_SUPABASE_ANON_KEY=your-branch-anon-key
```

**Important:** Set these for all environments (Production, Preview, Development) or just Production as needed.

### Step 4: Note Your Deployment URL

After deployment completes, Vercel will provide a URL like:
```
https://your-app-abc123.vercel.app
```

**Save this URL** - you'll need it for the next steps.

### Step 5: Update Supabase Authentication URLs

You need to configure your Supabase branch to accept authentication callbacks from your Vercel deployment.

**Using Supabase Dashboard:**
1. Go to your Supabase project
2. Navigate to **Authentication** > **URL Configuration**
3. Add to **Redirect URLs**:
   ```
   https://your-app-abc123.vercel.app/auth/callback
   https://*.vercel.app/auth/callback
   ```
4. Update **Site URL**:
   ```
   https://your-app-abc123.vercel.app
   ```

**Or using Supabase CLI/API** (if you have direct access to the branch)

### Step 6: Update Clio OAuth Redirect URI

1. Go to [Clio Developer Console](https://app.clio.com/settings/developer_applications)
2. Select your application
3. Add to **Redirect URIs**:
   ```
   https://your-app-abc123.vercel.app/api/clio/callback
   ```

### Step 7: Update CORS_ORIGINS (Optional)

If you want to explicitly set CORS origins instead of relying on auto-detection:

1. Go to Vercel Project Settings > Environment Variables
2. Add or update:
   ```
   CORS_ORIGINS=https://your-app-abc123.vercel.app
   ```

### Step 8: Test Your Deployment

1. **Visit your site**: `https://your-app-abc123.vercel.app`
2. **Test authentication**: Try logging in/registering
3. **Test Clio integration**: Connect to Clio if applicable
4. **Test API endpoints**: Verify document processing works

## Automatic Environment Variables

Vercel automatically provides:
- `VERCEL_URL` - The deployment URL (used for CORS and OAuth redirects)
- `VERCEL_ENV` - Environment type (production, preview, development)
- `VERCEL_GIT_COMMIT_SHA` - Git commit hash

Your code automatically uses `VERCEL_URL` for:
- CORS origin detection
- Clio OAuth redirect URI
- Frontend URL for callbacks

## Troubleshooting

### Authentication Not Working

**Problem:** Users can't log in or see "redirect_uri_mismatch" errors

**Solution:**
1. Verify Supabase redirect URLs include your Vercel domain
2. Check that `PUBLIC_SUPABASE_URL` and `PUBLIC_SUPABASE_ANON_KEY` are set in Vercel
3. Clear browser cookies and try again

### Clio Integration Errors

**Problem:** Clio OAuth fails with redirect URI mismatch

**Solution:**
1. Verify Clio Developer Console has your Vercel URL in redirect URIs
2. Check that `CLIO_CLIENT_ID` and `CLIO_CLIENT_SECRET` are set in Vercel
3. Ensure the redirect URI format is: `https://your-domain.vercel.app/api/clio/callback`

### CORS Errors

**Problem:** API requests fail with CORS errors

**Solution:**
1. Verify your frontend deployment URL is accessible
2. Check Vercel Function Logs for CORS origin detection messages
3. Optionally, explicitly set `CORS_ORIGINS` environment variable

### Build Fails

**Problem:** Vercel build fails during deployment

**Solution:**
1. Check build logs in Vercel dashboard
2. Verify `package.json` includes `@sveltejs/adapter-vercel`
3. Run `npm install` locally and commit `package-lock.json`
4. Check that all environment variables are set

### API Routes Not Working

**Problem:** API endpoints return 404 or 500 errors

**Solution:**
1. Verify Python dependencies are installed
2. Check `vercel.json` configuration for API routes
3. Review Vercel Function Logs for Python errors
4. Ensure `SUPABASE_SERVICE_KEY` and other backend env vars are set

## Preview Deployments

Every git push to a branch will create a preview deployment with a unique URL like:
```
https://your-app-git-branch-name-abc123.vercel.app
```

Preview deployments:
- Use the same environment variables as Production (or Preview-specific if configured)
- Have their own unique `VERCEL_URL`
- Are automatically cleaned up after inactivity
- Are great for testing before merging to main

## Custom Domains (Optional)

To add a custom domain:

1. Go to Vercel Project Settings > Domains
2. Add your domain (e.g., `app.yourdomain.com`)
3. Follow DNS configuration instructions
4. After domain is verified, update:
   - Supabase redirect URLs
   - Clio OAuth redirect URIs
   - Any hardcoded URLs in your code

## Monitoring and Logs

**View Deployment Logs:**
- Go to Vercel Dashboard > Your Project > Deployments
- Click on a deployment to see build and runtime logs

**View Function Logs (API routes):**
- Go to Vercel Dashboard > Your Project > Logs
- Filter by function name or time range

**Real-time Logs:**
```bash
vercel logs --follow
```

## Cost Considerations

Vercel Hobby plan includes:
- Unlimited deployments
- 100GB bandwidth/month
- 100GB-hours serverless function execution/month
- Automatic HTTPS

For production use, consider:
- **Pro Plan** for longer serverless function timeouts (60s vs 10s)
- **Team Plan** for collaboration features
- Monitor usage in Vercel Dashboard > Project > Usage

## Next Steps

After successful deployment:

1. ✅ Test all critical user flows
2. ✅ Set up monitoring/alerts if needed
3. ✅ Configure custom domain (optional)
4. ✅ Set up preview deployment notifications
5. ✅ Document production URL for your team
6. ✅ Consider enabling Vercel Analytics

## Support

For issues:
- Check Vercel documentation: https://vercel.com/docs
- Review deployment logs in Vercel Dashboard
- Check Function logs for API errors
- Verify environment variables are set correctly

---

**Deployment Date:** November 24, 2025
**Status:** ✅ Ready for Deployment

