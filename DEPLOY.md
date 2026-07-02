# Deployment Topology

Current production topology (since 2026-01; Cloud Run was decommissioned — see
commit `a5e1b3f`). Three deploy targets plus a managed database:

| Component | Platform | Source | Deploy |
|---|---|---|---|
| Frontend (SvelteKit) + API (FastAPI serverless) | Vercel | `frontend/` + `api/index.py` (imports `src/legal_portal/api/main.py`) | git push → Vercel build (`scripts/vercel_build.sh`) |
| Durable analysis worker | Railway | `worker/analysis_worker.py`, built from `Dockerfile.worker` | Railway auto-deploy from git |
| OCR microservice | Cloud Run | `services/ocr/` | manual `gcloud run deploy` (see `services/ocr/`) |
| Database / auth / storage | Supabase | `supabase/migrations/` | `supabase db push` |

## Vercel

- `vercel.json`: SvelteKit framework build, `api/index.py` function with
  `maxDuration: 800`, and the worker-health cron (`*/5 * * * *` →
  `/api/monitor/worker`, authenticated with `CRON_SECRET`).
- Python deps for the serverless function are pinned in
  `api/requirements.txt` + `api/constraints.txt` (regenerate with
  `pip-compile`; verify with `bash scripts/check_constraints.sh`).
- Rollback: Vercel dashboard → instant rollback to a previous deployment.

## Railway (worker)

- Runs `python -m worker.analysis_worker` (see `Dockerfile.worker`).
- Claims jobs from `analysis_jobs` via the `claim_analysis_job()` RPC
  (`FOR UPDATE SKIP LOCKED`), heartbeats every 30s, checkpoints per stage.
- The Vercel monitor cron can auto-redeploy a dead worker when
  `RAILWAY_API_TOKEN`/`RAILWAY_SERVICE_ID`/`RAILWAY_ENVIRONMENT_ID` are set
  (30-minute cooldown via the `monitor_state` table).
- Rollback: Railway dashboard → redeploy a previous build.

## Environment variables

`.env.template` is the canonical reference. Highlights:

- Core: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`,
  `OPENAI_API_KEY`
- Monitoring: `CRON_SECRET` (required in prod — the monitor fails closed
  without it), `ALERT_WEBHOOK_URL`, `FAILED_SPIKE_THRESHOLD`, Railway ids
- Security: `OAUTH_STATE_SECRET` (Clio OAuth state signing; falls back to
  `SUPABASE_SERVICE_KEY` with a warning until provisioned)
- Observability: `SENTRY_DSN` (optional; error tracking is a no-op without it)
- AI quality flags (default off): `ENABLE_PROMPT_HARDENING`,
  `ENABLE_DETERMINISTIC_SEED`, `ENABLE_STRICT_SCHEMA_RETRY`,
  `ENABLE_CITATION_ANNOTATIONS`
- Execution mode: `ANALYSIS_BACKEND_ONLY` (durable worker + polling vs
  legacy inline SSE)

## Local development

```bash
make supabase-start   # local Supabase (Docker) + db reset with migrations
make debug            # backend in Vercel-simulation mode on :8080
make frontend         # SvelteKit dev server on :5173
make worker           # durable worker against your configured Supabase
make test             # backend pytest suite
```
