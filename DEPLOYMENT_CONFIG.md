# Deployment Configuration Guide

This guide covers the configuration needed to deploy the Legal Document Analysis Portal to Vercel with Clio integration.

## Prerequisites

- Vercel account with Pro plan (for extended serverless function timeouts)
- Supabase project with the schema deployed
- Clio Developer account with OAuth app configured
- OpenAI API key

## Environment Variables

### Required for All Environments

Add these environment variables in your Vercel Project Settings:

#### Supabase Configuration
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key
```

#### OpenAI Configuration
```bash
OPENAI_API_KEY=sk-...
```

#### Clio Integration
```bash
CLIO_CLIENT_ID=your-clio-client-id
CLIO_CLIENT_SECRET=your-clio-client-secret
# CLIO_REDIRECT_URI is auto-detected from VERCEL_URL, but can be overridden:
# CLIO_REDIRECT_URI=https://your-app.vercel.app/api/clio/callback
```

### Frontend Environment Variables

In `frontend/.env.local` (development) and Vercel Environment Variables (production):

```bash
PUBLIC_API_URL=http://localhost:8000  # Development
# PUBLIC_API_URL=https://your-api.vercel.app  # Production
```

## Clio OAuth Configuration

### Step 1: Update Clio Redirect URI

1. Log in to [Clio Developer Console](https://app.clio.com/settings/developer_applications)
2. Select your application
3. Update the **Redirect URI** to match your Vercel deployment:
   - Development: `http://localhost:8000/api/clio/callback`
   - Production: `https://your-app.vercel.app/api/clio/callback`

### Step 2: Verify OAuth Scopes

Ensure your Clio app has these scopes enabled:
- `matters:read`
- `communications:read`
- `documents:read`
- `notes:read`
- `contacts:read`

## Database Setup

### Step 1: Run Supabase Migrations

Apply the database schema:

```bash
# From the project root
cd supabase

# Apply main schema
psql $DATABASE_URL < schema.sql

# Apply Clio integration migration
psql $DATABASE_URL < migrations/002_add_clio_integration.sql
```

Or use the Supabase CLI:

```bash
supabase db push
```

### Step 2: Verify RLS Policies

Ensure Row Level Security is enabled on all tables:
- `profiles`
- `cases`
- `documents`
- `analysis_results`
- `integrations_clio`

## Vercel Deployment

### Step 1: Configure vercel.json

Ensure your `vercel.json` is configured for both frontend and backend:

```json
{
  "buildCommand": "cd frontend && npm run build",
  "devCommand": "cd frontend && npm run dev",
  "installCommand": "cd frontend && npm install && cd ../src/legal_portal/api && pip install -r ../../../requirements.txt",
  "framework": "sveltekit",
  "outputDirectory": "frontend/.svelte-kit",
  "functions": {
    "src/legal_portal/api/**/*.py": {
      "runtime": "python3.11",
      "maxDuration": 60
    }
  },
  "rewrites": [
    {
      "source": "/api/(.*)",
      "destination": "/src/legal_portal/api/main.py"
    }
  ]
}
```

### Step 2: Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Or deploy to production
vercel --prod
```

### Step 3: Configure Environment Variables in Vercel

1. Go to your Vercel project settings
2. Navigate to "Environment Variables"
3. Add all required variables listed above
4. Ensure they are set for both "Production" and "Preview" environments

## Post-Deployment Verification

### 1. Test Clio OAuth Flow

1. Navigate to `/app/cases/[id]`
2. Scroll to "Clio Integration" section
3. Click "Connect to Clio"
4. Verify redirect to Clio authorization page
5. After authorization, verify redirect back to your app
6. Check that connection status shows "Connected"

### 2. Test Intake Review Workflow

1. Create a new case
2. Navigate to `/app/cases/[id]/review`
3. Upload an intake form
4. Verify AI extraction works
5. Edit Q&A pairs
6. Confirm and verify data is saved to Supabase

### 3. Test Analysis Flow

1. Upload documents to a case
2. Click "Start Analysis"
3. Monitor analysis status (should show processing)
4. Verify completion and results display

## Troubleshooting

### Clio OAuth "Invalid Redirect URI" Error

**Cause:** Mismatch between configured redirect URI in Clio and actual callback URL.

**Solution:**
1. Check the `CLIO_REDIRECT_URI` environment variable in Vercel
2. Verify it matches the redirect URI in Clio Developer Console
3. Ensure protocol matches (http vs https)

### Serverless Function Timeout

**Cause:** Analysis takes longer than Vercel's timeout (10s default, 60s max).

**Solution:**
1. Upgrade to Vercel Pro for 60s timeout
2. Or implement async analysis with polling (future enhancement)

### Supabase RLS "Row not found" Errors

**Cause:** RLS policies are too restrictive or user ID mismatch.

**Solution:**
1. Verify user is authenticated
2. Check that `auth.uid()` matches the user_id in queries
3. Review RLS policies in Supabase Dashboard

### "Clio not connected" Error on Matter Search

**Cause:** Access token expired or not found.

**Solution:**
1. Disconnect and reconnect to Clio
2. Check that `integrations_clio` table has valid entry
3. Verify token refresh logic is working

## Migration from Google Cloud Run

If you're migrating from an existing Google Cloud Run deployment:

### Step 1: Update Clio Redirect URI

Change the redirect URI in Clio Developer Console from:
```
https://your-cloud-run-url.run.app/api/clio/callback
```

To:
```
https://your-vercel-app.vercel.app/api/clio/callback
```

### Step 2: Migrate Environment Variables

Export environment variables from Cloud Run and import to Vercel.

### Step 3: Deprecate Cloud Run

Once Vercel deployment is verified:
1. Delete the Cloud Run service
2. Remove any related Cloud Build triggers
3. Clean up any associated IAM roles

## Security Best Practices

1. **Never commit `.env` files** - Use Vercel's environment variable UI
2. **Rotate secrets regularly** - Update Clio client secret, Supabase keys
3. **Use service role key sparingly** - Only for server-side operations
4. **Enable Supabase RLS** - Ensure all tables have proper policies
5. **Monitor API usage** - Track OpenAI and Clio API consumption

## Support

For issues or questions:
- Check Vercel deployment logs
- Review Supabase logs for database errors
- Check Clio API status page
- Review OpenAI API status

## Next Steps

After successful deployment:
1. Set up monitoring and alerting (Vercel Analytics, Sentry)
2. Configure custom domain (if desired)
3. Enable HTTPS enforcement
4. Set up backup schedule for Supabase data
5. Document user workflows for team

