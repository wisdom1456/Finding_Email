# Frontend Environment Variables Setup

## Required Environment Variables

The SvelteKit frontend requires the following environment variables to connect to Supabase:

```bash
# Supabase Configuration (Public - for client-side use)
PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
PUBLIC_SUPABASE_ANON_KEY=your-anon-key-here
```

## Local Development Setup

1. Create a `.env` file in the `frontend/` directory
2. Add the environment variables above with your actual Supabase credentials
3. The `.env` file is gitignored and will not be committed

## Vercel Production Setup

Configure these environment variables in the Vercel Dashboard:

1. Go to your project settings in Vercel
2. Navigate to **Environment Variables**
3. Add the following variables:
   - `PUBLIC_SUPABASE_URL` - Your Supabase project URL
   - `PUBLIC_SUPABASE_ANON_KEY` - Your Supabase anon/public key

## Getting Your Supabase Credentials

1. Open your Supabase project dashboard
2. Go to **Project Settings** > **API**
3. Copy the **Project URL** (for `PUBLIC_SUPABASE_URL`)
4. Copy the **anon/public key** (for `PUBLIC_SUPABASE_ANON_KEY`)

## Important Notes

- The `PUBLIC_` prefix makes these variables available on the client-side
- Never use the service role key with the `PUBLIC_` prefix
- The anon key is safe to use client-side as it respects Row Level Security (RLS) policies
- In Vercel, the `VERCEL_URL` environment variable is automatically provided

