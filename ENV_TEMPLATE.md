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

### Frontend-specific (with PUBLIC_ prefix)
- PUBLIC_API_URL (set to your production API URL)
- PUBLIC_SUPABASE_URL
- PUBLIC_SUPABASE_ANON_KEY

## Notes

1. **Never commit `.env` files** - They are gitignored for security
2. **VERCEL_URL** is automatically available in Vercel deployments
3. **Service Key vs Anon Key**: Use service key only in backend, anon key in frontend
4. **Clio Redirect URI**: Must match exactly what's configured in Clio Developer Console

