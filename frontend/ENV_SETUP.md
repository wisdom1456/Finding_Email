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

## Feature Flags

- `PUBLIC_ENABLE_AUTO_EXTRACT` — when `true`, auto-runs bulk text extraction on
  case load and hides the Verification Hub bulk "Run OCR" button.
- `PUBLIC_ENABLE_AUTO_EXTRACT_FULL_COVERAGE` — **default off.** When `true`,
  auto-extract uses the convergent full-coverage loop that guarantees every
  document needing text is processed (or marked `extraction_failed` with a
  visible error) instead of the legacy offset-paginated loop, which could
  silently skip a window of documents. An unset flag evaluates as `false` at
  runtime. Enable in a Vercel **preview** and verify a real case before turning
  it on in **production**.
- `PUBLIC_ENABLE_TRUSTWORTHY_WAIT` — **default off.** When `true`, gates the
  Trustworthy Wait Phase 1 UI: no Start button while a run is active (Cancel
  only), an honest per-step progress line (1→6) with per-step ETA, and a
  visible cancellation reason. Backend status fields (`ui_state`, `step_*`,
  `items_*`, `eta_seconds`, `healthy`, `cancel_reason`) ship regardless of this
  flag; it only gates frontend rendering in `InlineAnalysisProgress.svelte`
  and `+page.svelte`. An unset flag evaluates as `false` at runtime.

## Supabase Auth Site URL (hosted project) — required for email links

Password recovery, new-user email confirmation, and magic links redirect the
user to the Supabase project's **Site URL**. This is set in the **hosted**
project dashboard (**Authentication → URL Configuration**), NOT via the
`PUBLIC_SUPABASE_*` vars above.

- **Site URL** must be the production app URL
  (e.g. `https://finding-emails-wisdom1456s-projects.vercel.app`).
- **Redirect URLs** allowlist must include `<prod-url>/**` so `/auth/callback`
  (and its `next` target) is permitted.

> ⚠️ **Do not point the hosted Site URL at `localhost`.** If it is localhost,
> every production recovery/confirmation email links to `localhost` and dies
> with `ERR_CONNECTION_REFUSED` for the recipient (regular password login still
> works, so the breakage is silent). This regressed once (2026-07-24).
>
> `supabase/config.toml` intentionally keeps `site_url = http://127.0.0.1:3000`
> for **local** dev. Running `supabase config push` would overwrite the hosted
> Site URL with that localhost value — so change the hosted Site URL in the
> dashboard, and avoid `config push` unless `config.toml` is set to prod first.

## Important Notes

- The `PUBLIC_` prefix makes these variables available on the client-side
- Never use the service role key with the `PUBLIC_` prefix
- The anon key is safe to use client-side as it respects Row Level Security (RLS) policies
- In Vercel, the `VERCEL_URL` environment variable is automatically provided

