# Authentication Architecture

## Overview

The application uses **Supabase Authentication** with a Svelte frontend and FastAPI backend.

## Current Flow

1. User signs in from the frontend.
2. Frontend sends the Supabase access token on API requests.
3. Backend validates the token and resolves the current user before protected actions.

## Backend Enforcement

- Protected routes use dependency-based auth checks.
- Requests without valid auth return `401/403`.
- Authorization-sensitive actions (for example case deletion and CLIO status checks) are user-scoped.

## Environment Requirements

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY` / `PUBLIC_SUPABASE_ANON_KEY` (frontend)
- `SUPABASE_SERVICE_KEY` (backend service operations)

## Notes

- Legacy Streamlit authentication modules were removed as part of the migration cleanup.
- For enterprise SSO, integrate through Supabase Auth providers to keep a single auth surface.
