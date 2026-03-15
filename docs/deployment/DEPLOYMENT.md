# Deployment Guide

## Overview

This application deploys as a Vercel monorepo consisting of:

- **Frontend**: SvelteKit application served at the root
- **Backend**: FastAPI Python functions served under `/api`

The production URL is auto-detected via the `VERCEL_URL` environment variable, which Vercel sets automatically on each deployment. This value drives CORS configuration and OAuth callback URLs.

Architecture at a glance:

```
Browser --> Vercel Edge Network
              |
              +-- SvelteKit (/, /app/*, static assets)
              |
              +-- Python Serverless Functions (/api/*)
                    |
                    +-- Supabase (database, auth, storage)
                    +-- OpenAI API (document analysis)
                    +-- Clio API (legal practice management)
                    +-- Google Vision API (OCR, optional)
```

---

## Prerequisites

- **Vercel account** -- Pro plan recommended to access 300-second function timeouts and 500 MB function size limits
- **GitHub repository** connected to the Vercel project for automated deployments
- **Supabase project** with database tables and Row Level Security configured
- **Node.js** (v18+) and **Python** (3.11+) for local development
- **Vercel CLI** installed globally: `npm i -g vercel`
- **API keys**:
  - OpenAI API key (for document analysis)
  - Clio API credentials (client ID and secret, for legal practice management integration)
- **Google Cloud credentials** (optional, for OCR via Google Vision)

---

## Environment Variables

All environment variables are configured in the Vercel dashboard under **Settings > Environment Variables**. Set variables for the appropriate environments (Production, Preview, Development) as needed.

### Backend Variables

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | Supabase service role key (full access, server-side only) |
| `SUPABASE_ANON_KEY` | Yes | Supabase anonymous key |
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT calls |
| `CLIO_CLIENT_ID` | Yes | Clio OAuth application client ID |
| `CLIO_CLIENT_SECRET` | Yes | Clio OAuth application client secret |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | No | Base64-encoded Google Cloud service account JSON (for OCR) |
| `LOG_LEVEL` | No | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Default: `INFO` |
| `ENVIRONMENT` | No | Deployment environment identifier (`production`, `preview`, `development`) |

### Frontend Variables

Frontend variables must use the `PUBLIC_` prefix to be accessible in client-side code. These are embedded at build time.

| Variable | Required | Description |
|---|---|---|
| `PUBLIC_SUPABASE_URL` | Yes | Supabase project URL (client-side) |
| `PUBLIC_SUPABASE_ANON_KEY` | Yes | Supabase anonymous key (client-side) |
| `PUBLIC_API_URL` | No | Backend API base URL; typically left unset so the frontend calls `/api` on the same origin |

### Security Notes

- Never expose `SUPABASE_SERVICE_KEY` to the frontend. It grants full database access and bypasses RLS.
- The `SUPABASE_ANON_KEY` is safe for client-side use because Supabase enforces Row Level Security on requests made with this key.
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` should be base64-encoded before storing: `base64 -i service-account.json | tr -d '\n'`

---

## Vercel Configuration

The `vercel.json` file at the repository root defines the monorepo structure:

- **SvelteKit** handles all routes except `/api`
- **Python serverless functions** handle `/api` routes, with FastAPI as the ASGI framework

### Key Settings

- **Fluid Compute**: Enable in Vercel project settings under **Functions** to allow longer function durations (up to 300s on Pro). Required for large document analysis jobs that involve multi-page PDF extraction and GPT processing.
- **Function size limits**: The Python bundle is approximately 118 MB due to dependencies like PyMuPDF (~60 MB) and Pillow (~20 MB). The limit is 250 MB on Hobby and 500 MB on Pro. Monitor this if adding new Python dependencies.
- **Build settings**: The frontend build command and output directory are configured in Vercel project settings or `vercel.json`. SvelteKit uses `@sveltejs/adapter-vercel`.
- **Root directory**: Should be set to the repository root since both frontend and backend live in the same repo.

### Route Configuration

The `vercel.json` routes ensure proper separation:

- `/api/(.*)` routes to the Python serverless functions
- All other routes are handled by the SvelteKit application
- Static assets are served from the SvelteKit build output

---

## Deploy Process

### Production Deployment

**Automatic (recommended)**: Push to the `main` branch. Vercel builds and deploys automatically.

**Manual via CLI**:

```bash
# Deploy to production
vercel --prod

# Deploy a preview (for testing)
vercel
```

### Preview Deployments

Every pull request automatically receives a preview deployment with a unique URL. This is useful for:

- Testing changes before merging to `main`
- Sharing work-in-progress with team members
- Running integration tests against a live environment

Preview URLs follow the pattern: `https://<project>-<hash>-<scope>.vercel.app`

Note: Preview deployments use the environment variables configured for the "Preview" environment in Vercel settings.

### Build Pipeline

1. Vercel detects the monorepo structure from `vercel.json`
2. Frontend: `npm install` followed by `npm run build` compiles the SvelteKit application
3. Backend: Python dependencies are installed from `requirements.txt` and functions are bundled
4. Both are deployed as a single atomic deployment
5. The previous production deployment remains available for instant rollback

### First-Time Setup

When connecting the repository to Vercel for the first time:

1. Import the GitHub repository in the Vercel dashboard
2. Set the framework preset to **SvelteKit**
3. Configure all environment variables (see above)
4. Trigger the initial deployment
5. Configure the custom domain if applicable

---

## Post-Deployment Verification

After each production deployment, verify the following:

1. **Health check**: Send a request to the health endpoint and confirm a 200 response:
   ```bash
   curl -s https://<your-domain>/api/health | jq .
   ```

2. **Clio OAuth flow**: Navigate to the application UI, initiate a Clio connection, and confirm the OAuth redirect completes successfully and returns to the application.

3. **Document upload and analysis**: Upload a test document (PDF recommended) and confirm it processes through the full analysis pipeline -- upload, text extraction, GPT analysis, and results display.

4. **Supabase connectivity**: Verify that case data loads correctly on the cases page, confirming the database connection is working.

5. **Function logs**: Check the Vercel dashboard under **Deployments > Functions** for any startup errors, cold start issues, or runtime crashes. Pay attention to:
   - Import errors (missing dependencies)
   - Environment variable access failures
   - Memory or timeout issues

---

## Clio OAuth Setup

Clio OAuth requires the redirect URI to match the deployed application URL exactly. A mismatch will cause the OAuth flow to fail silently or return an error.

### Configuration Steps

1. Log in to the [Clio Developer Console](https://app.clio.com/nc/#/developer_applications)
2. Select or create your application
3. Set the **Redirect URI** to: `https://<your-domain>/api/clio/callback`
4. Copy the **Client ID** and **Client Secret**
5. Save both values to the Vercel environment variables (`CLIO_CLIENT_ID`, `CLIO_CLIENT_SECRET`)

### Important Notes

- The redirect URI must use HTTPS
- The URI must match exactly, including trailing slashes
- Preview deployments use different URLs, so Clio OAuth only works on the production domain unless you add preview URLs to the allowed redirects in the Clio Developer Console
- If you use a custom domain, update the redirect URI to match the custom domain, not the `.vercel.app` URL
- Clio access tokens expire; the application handles token refresh automatically

---

## Troubleshooting

### 500 Errors on API Routes

Check that all required environment variables are set in the Vercel dashboard. Missing `SUPABASE_URL` or `OPENAI_API_KEY` will cause immediate failures. Steps to diagnose:

1. Open the Vercel dashboard and navigate to the failed deployment
2. Check **Functions** tab for the specific function that errored
3. Review the function logs for the stack trace
4. Verify all required environment variables are present under **Settings > Environment Variables**

### Function Timeout

The default Vercel function timeout is 10 seconds on Hobby plans. Large document analysis requires significantly more time.

- Upgrade to Vercel Pro for 300-second timeouts
- Enable **Fluid Compute** in project settings under **Functions**
- For very large documents, the application uses background processing with a polling client that checks for completion
- If timeouts persist on Pro, investigate whether the OpenAI API calls are hanging (check for rate limiting or model availability)

### Function Size Limit Exceeded

If the Python bundle exceeds the size limit during deployment:

- Review dependencies in `requirements.txt` for unnecessary packages
- The heaviest dependencies are PyMuPDF (~60 MB) and Pillow (~20 MB)
- Consider whether optional dependencies can be excluded from the production bundle
- Use `vercel inspect` to see the exact function size breakdown
- Upgrading to Pro doubles the limit from 250 MB to 500 MB

### CORS Errors

CORS is auto-configured from `VERCEL_URL`. If you see CORS errors in the browser console:

- Confirm `VERCEL_URL` is set correctly (Vercel provides this automatically)
- If using a custom domain, ensure the backend CORS configuration includes it
- Check that the frontend is calling `/api` on the same origin rather than an absolute URL to a different domain
- Clear the browser cache, as stale CORS preflight responses can persist

### Cache Issues

If a deployment behaves unexpectedly after dependency changes:

- Redeploy without cache: in the Vercel dashboard, trigger a new deployment and uncheck **Use existing Build Cache**
- CLI: `vercel --prod --force`
- This is especially relevant when Python dependencies have been added, removed, or updated

### Missing Documents from Clio

The Clio integration uses pagination to fetch all items from the Clio API. If documents appear to be missing:

- Check function logs for pagination errors or API rate limiting
- Verify the Clio API access token has not expired (the application refreshes tokens automatically, but check for refresh failures)
- Confirm the matter ID is correct and the authenticated user has access to that matter in Clio
- Large matters with many documents may require multiple paginated requests; check that all pages completed successfully

### Cold Start Latency

Python serverless functions experience cold starts when they have not been invoked recently:

- Cold starts typically take 2-5 seconds due to the size of the Python bundle
- Fluid Compute helps by keeping functions warm longer
- The health check endpoint can be used with an external monitor (e.g., UptimeRobot) to keep functions warm

---

## Rollback

If a production deployment introduces issues, roll back immediately rather than attempting a forward fix under pressure.

### Via Vercel Dashboard

1. Navigate to **Deployments** in the Vercel dashboard
2. Find the previous successful deployment (shown with a green status)
3. Click the three-dot menu and select **Promote to Production**
4. The rollback takes effect within seconds

### Via CLI

```bash
vercel rollback
```

This immediately promotes the previous production deployment. No rebuild is required and the rollback is atomic.

### Notes on Rollback

- Rollback does not revert environment variable changes. If the issue was caused by an environment variable change, revert it manually in the dashboard.
- Database migrations are not rolled back automatically. If the deployment included schema changes, you may need to address those separately.
- After rolling back, investigate the issue on a preview deployment before re-deploying to production.

---

## Google Cloud (Historical)

The application was previously deployed on Google Cloud Run as a containerized service with a Dockerfile-based build. This deployment method is no longer active. Vercel is the primary and only supported deployment target.

The migration to Vercel was driven by:

- Simplified deployment with zero Docker configuration
- Automatic preview environments for every pull request
- Native monorepo support for SvelteKit and Python functions
- Built-in CI/CD via GitHub integration

If you need to reference the historical GCP configuration for any reason, archived documentation and Dockerfiles may exist in earlier commits of this repository.
