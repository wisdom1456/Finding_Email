# Self-Service Password Reset Flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give users a self-service way to recover a forgotten password. Today there is **no reset path at all** — the login page offers only "Register", and there is no `resetPasswordForEmail` call anywhere in the frontend. A user who forgets their password (e.g. Ceryn, 2026-07-24 — locked out after ~4 months of riding a persistent session) has no way back in without an admin.

**Non-goal / context:** This is a UX gap, **not** a bug fix. Auth itself is healthy: Supabase correctly returns `invalid_credentials`, the login path is unchanged since March 2026, and other users log in fine. This plan adds the missing recovery flow; it does not touch the existing sign-in path.

**Architecture:** Standard Supabase recovery, client-side, matching the existing direct browser→Supabase auth model (`createBrowserClient` + `signInWithPassword`). The existing `/auth/callback` route already does `exchangeCodeForSession`, so the recovery link lands there and produces a session before redirecting to a new "set a new password" page. No backend changes.

**Tech stack:** SvelteKit, `@supabase/ssr` browser client, Supabase Auth recovery emails. Reuses `sanitizeRedirectTarget` (`$lib/utils`) and the existing `AsyncButton` / `Input` components.

**Rollout preference (per house style):** Phased + flag-gated. The visible entry point sits behind `PUBLIC_ENABLE_PASSWORD_RESET` (default OFF). Backend/routes are additive and inert until the link is shown and the Supabase email template + redirect allowlist are configured.

---

## Flow

```
Login page ── "Forgot password?" (flag-gated) ──▶ /forgot-password
   user enters email
   supabase.auth.resetPasswordForEmail(email, {
     redirectTo: `${origin}/auth/callback?next=/account/update-password`
   })
   ── always show generic "if an account exists, we sent a link" ──

Supabase emails recovery link ──▶ /auth/callback?code=…&next=/account/update-password
   existing handler: exchangeCodeForSession(code)  → recovery session established
   redirect(303, next)  (next sanitized)

/account/update-password  (requires the recovery session)
   user enters new password (+ confirm)
   supabase.auth.updateUser({ password })
   on success → sign out other sessions (optional, Phase 2) → redirect /app
```

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| CREATE | `frontend/src/routes/forgot-password/+page.svelte` | Email input → `resetPasswordForEmail`; generic non-enumerating confirmation |
| CREATE | `frontend/src/routes/account/update-password/+page.svelte` | New-password form → `updateUser({ password })`; guarded by active session |
| CREATE | `frontend/src/routes/account/update-password/+page.ts` | Load guard: redirect to `/login` if no session (recovery link required) |
| MODIFY | `frontend/src/routes/login/+page.svelte` | Add "Forgot password?" link, gated behind `PUBLIC_ENABLE_PASSWORD_RESET` |
| MODIFY | `frontend/src/lib/config.ts` (or existing flag module) | Read `PUBLIC_ENABLE_PASSWORD_RESET` from `$env/dynamic/public` |
| MODIFY | `frontend/.env.example` | Document `PUBLIC_ENABLE_PASSWORD_RESET=false` |
| MODIFY | `frontend/ENV_SETUP.md` | Note the flag + the required Supabase dashboard config |
| CREATE | `frontend/src/routes/forgot-password/page.test.ts` | Unit: submits email, shows generic confirmation, handles error |
| CREATE | `frontend/src/routes/account/update-password/page.test.ts` | Unit: submits new password, redirects on success, blocks with no session |

*(No change to `/auth/callback/+server.ts` — it already handles the recovery `code` and sanitizes `next`. Add a test case only if coverage is missing.)*

---

## Configuration Reference

| Setting | Where | Value |
|---------|-------|-------|
| `PUBLIC_ENABLE_PASSWORD_RESET` | Vercel env (prod) + `.env` (local) | `false` until Phase 1 is verified, then `true` |
| Site URL | Supabase dashboard → Auth → URL Configuration | Production app URL (already hosted) |
| Redirect allowlist | Supabase dashboard → Auth → URL Configuration | Must include `${SITE_URL}/auth/callback` |
| "Reset Password" email template | Supabase dashboard → Auth → Email Templates | Confirm copy + `{{ .ConfirmationURL }}`; check sender/domain so it isn't flagged as spam |
| SMTP / rate limits | Supabase dashboard → Auth | Default mailer is fine for low volume but rate-limited; confirm before enabling |

---

## Phase 1 — Core reset flow (flag-gated)

- [ ] Add `PUBLIC_ENABLE_PASSWORD_RESET` to the flag module, `.env.example`, and `ENV_SETUP.md` (default OFF).
- [ ] `forgot-password/+page.svelte`: email field → `supabase.auth.resetPasswordForEmail(email, { redirectTo })`. Build `redirectTo` from `window.location.origin` so it works across preview/prod without hardcoding.
- [ ] **Non-enumeration:** on both success and "user not found", show the same message — "If an account exists for that email, we've sent a reset link." Never reveal whether the email is registered.
- [ ] `account/update-password/+page.ts`: load guard — if `getSecureSession()` returns no session, redirect to `/login` (the page is only reachable via a valid recovery link).
- [ ] `account/update-password/+page.svelte`: new password + confirm, min length check, mismatch check → `supabase.auth.updateUser({ password })`. On success redirect to `/app`; on error surface `error.message`.
- [ ] `login/+page.svelte`: add "Forgot password?" link under the form, rendered only when `PUBLIC_ENABLE_PASSWORD_RESET` is true.
- [ ] Unit tests for both new pages (submit, success redirect, error surface, no-session guard).
- [ ] `svelte-check`: 0 errors. Run frontend test suite green.

## Phase 1 — Operator steps (do NOT automate; gate enabling on these)

- [ ] Confirm Supabase **Site URL** = production app URL and redirect allowlist includes `/auth/callback`.
- [ ] Review the "Reset Password" email template + sender domain (spam-safety).
- [ ] Set `PUBLIC_ENABLE_PASSWORD_RESET=true` in Vercel prod (real env var — `$env/dynamic/public` reads it at runtime; a rebuild/redeploy is required).
- [ ] Manual end-to-end on prod: request reset for a test account → click emailed link → land on update-password → set new password → land on `/app` signed in.

## Phase 2 — Hardening (deferred; do only if asked)

- [ ] After a successful password change, sign out all other sessions (`signOut({ scope: 'global' }`-style) so a stolen/lingering session can't persist.
- [ ] Password-strength meter + shared validation with the register page.
- [ ] "Resend link" affordance + cooldown on the forgot-password confirmation screen.
- [ ] Rate-limit / abuse note: confirm Supabase's built-in recovery rate limits are acceptable; add app-level throttling only if needed.

---

## Risks & invariants

- **One writer per transition:** the recovery session is established solely by `/auth/callback` (`exchangeCodeForSession`); the update-password page only *consumes* that session via `updateUser`. No split ownership.
- **Redirect safety:** `next` continues to flow through `sanitizeRedirectTarget`; `redirectTo` is derived from `window.location.origin`, never from user input.
- **No enumeration:** the forgot-password response must be identical whether or not the email exists.
- **Additive & inert:** with the flag OFF and no dashboard config, none of this is reachable — zero risk to the current login path. This is the safe-to-merge property the house style requires.
