# Clio Import: Complete Per-Document Progress Log

**Date:** 2026-07-02
**Status:** Approved by user

## Problem

The Clio import modal's PROGRESS list skips documents (e.g. shows doc 12, 17, 24, 29… of 69). Two lossy stages cause this:

1. **Backend**: `persist_progress` in `src/legal_portal/services/cases/clio_import_service.py` overwrites a single snapshot in `cases.import_progress`, and `ThrottledDBWriter` (3 s min interval) drops any snapshot superseded before the next write.
2. **Frontend**: `ClioImportProgressModal.svelte` accumulates whatever snapshot each poll happens to catch via `progressStore`.

Documents that download faster than the write/poll cadence never appear. The user wants every document listed, with its file size, and its outcome (per no-silent-failures priority).

## Approach (chosen: accumulate log in payload)

Alternatives considered and rejected:
- Poll the `documents` table for inserted rows — second polling loop, no "downloading" state, misses docs skipped before insert.
- Real-time SSE/Redis — conflicts with the established polling-only architecture preference.

Chosen: the import loop maintains a `doc_log` array inside the existing `progress` JSON payload. Every throttled write persists the whole accumulated list, so throttling only delays data (≤3 s), never loses it.

## Design

### Backend — `clio_import_service.py`

- In `import_clio_documents_helper`'s document loop, maintain `doc_log: list[dict]`.
- On loop entry for each doc, append:
  `{"i": idx + 1, "name": doc_name (trimmed ≤80 chars), "size_bytes": doc.get("size", 0), "outcome": "downloading"}`
- Update `outcome` in the same iteration when decided:
  `imported` | `skipped_small_image` | `duplicate` | `blacklisted` | `failed` (failed entries also get `"reason"`, trimmed ≤120 chars).
- Include `doc_log` in the `progress_data` dict passed to `persist_progress` (same dict that already carries `message`/`phase`/`percent`/`current_doc`).
- Cap: keep at most 500 entries (drop oldest; real matters are ~10–100 docs, 69 docs ≈ 6 KB JSONB).
- Final `flush()` already exists at completion (`clio_import_service.py:611`) — verify it also runs on the error path; add to a `finally` if not.

### API — no changes

`src/legal_portal/api/routes/progress.py:124` already spreads unknown `progress_data` keys into the event stream, so `doc_log` flows through the existing endpoint untouched.

### Frontend — `progressStore` + `ClioImportProgressModal.svelte`

- `progressStore`: pass `doc_log` through on the state object (same passthrough treatment as `current_doc`).
- Modal: when state has a non-empty `doc_log`, the documents-phase section renders it as a scrollable list (fixed max-height, auto-scroll pinned to newest unless the user has scrolled up). One row per document:
  `#12  Cuchillo 2 Business Search _ A  (1.8 MB)  ✓ imported`
  - Size formatted human-readable (B/KB/MB); `0`/missing size renders as `—`.
  - Outcome markers: ✓ imported, ⬇ downloading, ⤫ skipped (small image), ≡ duplicate, ⊘ blacklisted, ✗ failed (reason in tooltip/secondary text).
- Phases other than documents keep today's message list. If `doc_log` is absent (old payloads, other import phases), the modal renders exactly as today.

### Compatibility & rollout

Additive, backward-compatible payload key: old frontends ignore `doc_log`; the new frontend degrades gracefully without it. No feature flag needed. No DB schema change (JSONB column already exists).

### Error handling

- Failed downloads keep their `failed` entry with reason; import continues (existing behavior).
- Log accumulation must never break the import: wrap append/update in the same try/except pattern `persist_progress` already uses (progress failures log a warning, never raise).

### Testing

- **pytest**: unit tests for log accumulation (every doc gets exactly one entry; outcomes transition correctly for each branch: imported / small-image / duplicate / blacklisted / failed), cap behavior, and payload inclusion. Verify final flush on success and error paths.
- **vitest**: modal renders a gap-free numbered list from a `doc_log` fixture; auto-scroll behavior; graceful render when `doc_log` absent.
- Verify against known baselines: 23 pre-existing pytest failures, 4 pre-existing vitest failures (3 of which are `progressStore` — pre-existing, not from this change), 10 svelte-check errors.
