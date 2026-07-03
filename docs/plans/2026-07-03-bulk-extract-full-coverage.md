# Bulk/Auto-Extract Full-Coverage Fix — Implementation Plan (Phase 1)

**Status: IMPLEMENTED 2026-07-03** on branch `fix/bulk-extract-full-coverage` (off `main`).
Backend fix is unconditional; the user-facing loop is gated behind
`PUBLIC_ENABLE_AUTO_EXTRACT_FULL_COVERAGE` (default off) pending preview verification.

### Execution results
- Commits: `deaf74b` (backend converge + persist), `c655c29` (coverage-loop util),
  `6ee5272` (flag-gated page loop), `e53f917` (exclusion sync + flag doc).
- Backend: `tests/api/test_bulk_extract_coverage.py` 3/3 + `test_extract_guard.py` 5/5 green;
  full `tests/` suite **1242 passed, 1 skipped, 0 failed** (baseline 1238–1239 passed + 3 new).
- Frontend: `svelte-check` **0 errors**; `vitest` **651 passed, 1 skipped** (baseline 649 + 2 new).
- **Pending (gated, needs user approval):** deploy branch to a Vercel preview with the flag ON,
  verify auto-extract clears the stuck `.docx` on the live Erica Corley case, then enable in prod.

---

## Context — why this change

Live incident: case "Erica Corley" (`7d67ec29-5994-4382-9356-97909bec030e`, owner
modible@gmail.com). With `PUBLIC_ENABLE_AUTO_EXTRACT` on, auto-extract fired on case load but
left legitimate documents `pending`, forcing manual per-doc "Extract Text". Two verified defects:

1. **Pagination over a mutating result set.** `runOcrOnMissingDocs`
   (`frontend/src/routes/app/cases/[id]/+page.svelte`) advanced `offset` across calls, but
   `bulk_extract_documents` (`src/legal_portal/api/routes/documents.py`) re-runs a live query each
   call (`extracted_text IS NULL OR ''`). Batch 1 extracts docs 0–19; they gain text and leave the
   filter, shrinking 54→34. Batch 2's `offset=20` lands on the shrunken 34-item set, skipping its
   first 20 rows and jumping to the tail; `has_more = 34 < 34 = false` stops the loop — a whole
   window silently never touched. (The incident's real `.docx` stayed `pending`; the extractor
   succeeds on it in 0.02s → 26k chars, so it is not a file problem.)
2. **Silent per-doc failures.** The frontend read only `extracted_count/has_more/next_offset` and
   always showed a green toast. Backend's large-PDF skip and timeout/exception branches only bumped
   a counter — they never wrote the document row, so a skipped/failed doc kept its prior status with
   no `extraction_error`. Violates the top product rule: *no silent failures*.

## The invariant (why it converges)

**Retry-set** = docs for the case that still genuinely need a bulk attempt = empty `extracted_text`
AND `is_flagged_as_junk = false` AND `status NOT IN (skipped, duplicate, corrupted,
download_failed, extraction_failed)`.

After the handler *touches* a doc it leaves the retry-set:
- extract succeeds → `_trigger_extraction_inner` writes `status=ready` + text → leaves.
- extract returns empty → inner already writes `status=extraction_failed` → leaves.
- extract raises/times out (killed before inner's write) → **NEW** `_mark_extraction_failed` → leaves.
- large-PDF skip (>10MB) → **NEW** `_mark_extraction_failed` ("too large … extract individually") → leaves.

Because every touched doc leaves the set, `|retry-set|` strictly decreases each batch ⇒ a loop that
always queries `offset=0` of the live set converges in `ceil(N/batch_size)` batches. A frontend
safety cap (`ceil(docs/20)+3`) backstops pathological cases (`hitCap`).

## What was implemented

**Backend (`src/legal_portal/api/routes/documents.py`) — unconditional:**
- `bulk_extract_documents` query now excludes a `NON_RETRYABLE` status set + `is_flagged_as_junk`.
- New `_mark_extraction_failed(service_supabase, doc_id, message)` writes
  `status=extraction_failed`, `extraction_error`, `updated_at` via the **service-role** client
  (one writer per transition, matching `_trigger_extraction_inner`). Wired into the large-PDF skip,
  the empty-text branch (idempotent), and both `except` branches.
- `BulkExtractResponse` gains `remaining` (= `total_queued - next_offset`); `has_more`/`next_offset`
  kept for the legacy flag-off loop.

**Frontend:**
- `frontend/src/lib/utils/bulkExtractLoop.ts` — pure `runCoverageLoop(runBatch, onProgress, maxBatches)`
  returning `{ totalExtracted, totalFailed, errors, batches, hitCap }`. Never advances an offset.
- `+page.svelte` `runOcrOnMissingDocs` — flag-gated: ON → coverage loop (offset:0 each call) that
  surfaces `failed_count`/`errors` via a warning toast; OFF → legacy offset loop verbatim.
- `autoExtract.ts` — `EXCLUDED_STATUSES` gains `extraction_failed` (kept in sync with backend
  `NON_RETRYABLE`) so a marked-failed doc doesn't re-trigger the whole bulk pass on every reload.
- `frontend/ENV_SETUP.md` — documents `PUBLIC_ENABLE_AUTO_EXTRACT_FULL_COVERAGE`.

## Verification

- `venv/bin/python -m pytest tests/api/test_bulk_extract_coverage.py tests/api/test_extract_guard.py -v` → 8 pass.
- `venv/bin/python -m pytest tests/ -q` → 1242 passed, 1 skipped, 0 failed.
- `cd frontend && npm run check && npx vitest run` → svelte-check 0; vitest 651 passed, 1 skipped.
- Convergence proof: `bulkExtractLoop.test.ts` exercises the 54→34→14→0 shrink without skipping a
  window and honors the safety cap.
- **Real-case (gated):** deploy to Vercel preview with flag ON; confirm the stuck `.docx` becomes
  `ready` (`extraction_method='python-docx'`), duplicates untouched, any unextractable doc shows
  `extraction_failed` + visible error + failure toast; re-query for 0 rows with (empty text AND not
  junk AND status in retry-set). Then enable in prod. Do not promote without approval.

## Out of scope (Phase 2+)

Case-load "extraction reconciliation" sweep; extract-guard fetching full `extracted_text` just to
test emptiness; signature-capability reshape; durable-jobs migration; a cross-tab lock.
