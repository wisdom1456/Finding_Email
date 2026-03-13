# Internal Deployment Summary — v2.0.0

**Commit range:** `aebffb0` (Feb 5, 2026) → `ab2f636` (March 13, 2026)
**Commits:** ~210 | **Files changed:** 309 | **Lines added:** ~52K

---

## Backend Changes

### Model Routing
- Default model changed from GPT-5.2 to **GPT-5.4** for letter generation and multi-stage analysis.
- Document analysis and case chat default to **GPT-5 Mini**.
- OCR/Vision extraction remains on **GPT-5.2 Vision**.
- Migration `20260122000000` backfilled existing user profiles from gpt-4o defaults to gpt-5-mini/gpt-5.2 defaults (note: a further update to gpt-5.4 defaults is in code but not in migration).

### Gap Analysis Pipeline
- Map-reduce pipeline for cases with 50+ documents.
- Map phase: GPT-5 Mini per-batch processing.
- Reduce phase: GPT-5.4 synthesis with 16K max_output_tokens.
- Chunk state stored as JSONB on `analysis_results` table with distributed locking functions.

### OCR Service
- Cloud Run OCR client added (`ocr_service_client.py`) with retry logic (3 attempts, exponential backoff).
- **Disabled by default** (`OCR_REMOTE_ENABLED=false`).
- Falls back to Google Cloud Vision local extraction if config is missing or remote fails.
- Env vars required only if enabled: `OCR_SERVICE_URL`, `OCR_SERVICE_TOKEN`.

### Document Processing
- HEIC/HEIF image support via `pillow-heif` (converts to JPEG before processing).
- Small image filter: images <50KB skipped during Clio import.
- Deferred extraction: documents can be extracted on-demand.
- Email attachment extraction and thread deduplication.
- Content-hash deduplication for exact-match documents.

### Findings Email V2
- Rewritten prompt with combined law+application format.
- Critic review + polish pass pipeline.
- Network auto-retry on transient failures.

---

## Frontend Changes

### New Components
- **VerificationHub** — replaces DocumentReviewPanel. Triage groups, signature review, bulk OCR.

### Removed Components
- **DocumentReviewPanel** — consolidated into VerificationHub.
- **WeasyPrint PDF generation** — fully removed (no imports remain).

### Updated
- Settings page: model list updated (GPT-5.4, Mini, Nano, 5.2).
- Help page: HEIC added to supported formats, model references current, changelog updated.
- Results workspace: persists when switching tabs, unified navigation.
- Streaming: auto-recovery and SSE progress polling for Vercel serverless.

---

## Database / Migrations

17 migration files since `aebffb0`. All changes are **additive** (new columns, tables, indexes, functions). No drops or renames.

### Key Migrations
| Migration | Change |
|---|---|
| `20251228000001` | Document extraction tracking fields (6 columns) |
| `20260103000000` | Chunk state JSONB + distributed lock functions |
| `20260122000000` | AI preferences defaults backfill (gpt-4o → gpt-5-mini/gpt-5.2) |
| `20260204000000` | Clio sync tracking (last_synced_at, needs_reanalysis) |
| `20260304000000` | RLS policy optimization |
| `20260306000000` | Document registry denormalization (6 columns + backfill) |

### Rollback Compatibility
- Old code at `aebffb0` ignores unknown columns — safe to roll back without schema revert.
- Lock functions (`acquire_analysis_lock`, `release_analysis_lock`) are only called by new code.
- No destructive migrations (no DROP, no ALTER TYPE, no column renames).

---

## Dependencies

### Added (root requirements.txt)
- `pillow-heif>=0.16.0` — HEIC image support
- `markdown2>=2.4.0` — Markdown processing

### Added (api/requirements.txt — Vercel)
- `Pillow>=10.0.0` — Image compression/conversion
- `python-docx>=1.1.0,<2.0` — DOCX extraction
- `markdown2>=2.4.0` — Markdown processing
- `httpx>=0.27.0` — Cloud Run OCR HTTP client

### Updated
- `supabase==2.16.0` (pinned to avoid pip backtracking)
- `google-cloud-vision>=3.7.0,<4.0` (tighter range)
- `openai>=1.70.0` (required for GPT-5 parameters)

### Removed
- `weasyprint` — fully removed
- `uvicorn` — not needed for Vercel serverless
- `python-jose` — auth handled differently

### Size Check
`pillow-heif` adds ~24 MB uncompressed to the Vercel function. Total estimated function size with all dependencies is ~118 MB, well within Vercel's 250 MB limit.

---

## Environment Variables

**No new environment variables required.**

Cloud Run OCR (optional, disabled by default):
- `OCR_REMOTE_ENABLED` — set `true` to enable (default: `false`)
- `OCR_REMOTE_REQUIRED` — set `false` for fallback mode (default: `true`)
- `OCR_SERVICE_URL` — Cloud Run service URL
- `OCR_SERVICE_TOKEN` — shared auth secret

Existing variables remain unchanged. `APP_VERSION` default is still `1.0.0` in config — update in Vercel if version display is desired.

---

## Known Limitations

- Vision OCR still uses GPT-5.2 (not yet migrated to 5.4).
- Map-reduce gap analysis may take 10-15+ minutes on very large cases (50+ docs).
- HEIC conversion requires `pillow-heif` (included in Vercel deps, ~24 MB).
- Cloud Run OCR is optional; local fallback is available but slower.
- Content-hash dedup catches exact matches only (near-duplicates not caught).
- Letter polish pass adds processing time but improves output quality.
- Migration `20260122000000` set defaults to gpt-5.2, but code now defaults to gpt-5.4. Existing users with gpt-5.2 preferences will keep gpt-5.2 until they reset defaults.

---

## Rollback Plan

### Production Baseline
- **Commit:** `aebffb0`
- **Date:** Feb 5, 2026
- **Action:** Tag as production baseline before deploying v2.0.0.

### Rollback Procedure
1. Redeploy commit `aebffb0` from Vercel dashboard (frontend + backend deploy together).
2. Database: no rollback needed — old code ignores new columns/functions.
3. Documentation: bundled in deploy, rolls back with code.

### If Rollback Fails
- Check if any new Supabase functions conflict (unlikely — old code doesn't call them).
- Verify `ai_preferences` column defaults don't cause issues (old defaults are compatible).
