# Environment Variables Template

Copy these variables to your `.env` file (backend) and `frontend/.env.local` (frontend).

## Backend (.env)

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key-here
SUPABASE_ANON_KEY=your-anon-key-here

# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-key-here

# Google Cloud Vision OCR (Optional but recommended - faster and cheaper than GPT-4o)
# Option 1: Base64-encoded service account JSON (recommended for Vercel)
GOOGLE_APPLICATION_CREDENTIALS_JSON=base64-encoded-service-account-json
# Option 2: Path to service account JSON file (for local development)
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Clio Integration
CLIO_CLIENT_ID=your-clio-client-id
CLIO_CLIENT_SECRET=your-clio-client-secret
# CLIO_REDIRECT_URI is auto-detected from VERCEL_URL in production
# For local development:
CLIO_REDIRECT_URI=http://127.0.0.1:8000/api/clio/callback

# Frontend URL (for OAuth callback redirects)
FRONTEND_URL=http://127.0.0.1:5173

# Optional: Application Settings
LOG_LEVEL=INFO
DEBUG_MODE=false
```

## Frontend (frontend/.env.local)

```bash
# API URL Configuration
PUBLIC_API_URL=http://localhost:8000  # Development
# PUBLIC_API_URL=https://your-api.vercel.app  # Production

# Supabase Public Configuration
PUBLIC_SUPABASE_URL=https://your-project.supabase.co
PUBLIC_SUPABASE_ANON_KEY=your-anon-key-here
```

## Vercel Production Environment Variables

In Vercel Project Settings > Environment Variables, add:

### Production & Preview
- SUPABASE_URL
- SUPABASE_SERVICE_KEY
- SUPABASE_ANON_KEY
- OPENAI_API_KEY
- CLIO_CLIENT_ID
- CLIO_CLIENT_SECRET
- GOOGLE_APPLICATION_CREDENTIALS_JSON (base64-encoded service account JSON)

### Frontend-specific (with PUBLIC_ prefix)
- PUBLIC_API_URL (set to your production API URL)
- PUBLIC_SUPABASE_URL
- PUBLIC_SUPABASE_ANON_KEY

## Notes

1. **Never commit `.env` files** - They are gitignored for security
2. **VERCEL_URL** is automatically available in Vercel deployments
3. **Service Key vs Anon Key**: Use service key only in backend, anon key in frontend
4. **Clio Redirect URI**: Must match exactly what's configured in Clio Developer Console

## Google Cloud Vision Setup

Google Cloud Vision provides fast, accurate OCR for scanned PDFs (much faster than GPT-4o Vision).

### Setup Steps:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the **Cloud Vision API**
4. Go to **IAM & Admin > Service Accounts**
5. Create a service account with **Cloud Vision User** role
6. Create a JSON key for the service account
7. For Vercel: Base64-encode the JSON file:
   ```bash
   cat service-account.json | base64
   ```
8. Add the base64 string as `GOOGLE_APPLICATION_CREDENTIALS_JSON` in Vercel

### Pricing:
- First 1000 units/month: Free
- Units 1001-5M: $1.50 per 1000 units
- Much cheaper than GPT-4o Vision (~$15-30 per 1000 pages)

