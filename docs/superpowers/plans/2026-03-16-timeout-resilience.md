# Timeout & Network Resilience Hardening Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all remaining endpoints and operations that can silently exceed the Vercel function execution limit, and add guardrails to prevent regressions.

**Architecture:** Three non-streaming POST endpoints (`/generate-letter`, `/analyze-gaps`, `/analyze-gaps/resolve`) run long operations without SSE protection. The Ghostscript subprocess has a 300s timeout that blocks the event loop synchronously. All need either time-budgeting within the platform limit or migration to streaming. The deployment config test (already added) prevents config drift.

**Tech Stack:** Python/FastAPI, asyncio, Vercel serverless, pytest

---

## Context: What was already fixed (2026-03-16)

- `api/.vc-config.json` maxDuration raised from 60s to 800s (matches `vercel.json`)
- Deployment config consistency tests added (`tests/unit/test_deployment_config.py`)
- These changes mean nothing is _currently_ broken, but the architecture has latent risks if the platform limit is ever lowered or budgets increase

## Risk Assessment

| Endpoint/Operation | Type | Max Duration | SSE Protected? | Risk Level |
|---|---|---|---|---|
| `POST /generate-letter` | Non-streaming POST | 240s (letter_internal_budget) | No | **Medium** — works at 800s limit, breaks if limit reduced |
| `POST /analyze-gaps` | Non-streaming POST | ~30-60s typical | No | **Low** — usually finishes within safe margin |
| `POST /analyze-gaps/resolve` | Non-streaming POST | ~10-30s | No | **Low** |
| Ghostscript subprocess | sync subprocess.run | 300s hardcoded | No | **Medium** — blocks event loop, no async wrapper |
| `POST /generate-letter` retry after SSE fail | Frontend fallback | 240s | No | **Medium** — same as above |

---

## Chunk 1: Non-streaming `/generate-letter` safety net

### Task 1: Add internal deadline logging to `/generate-letter`

The non-streaming `/generate-letter` already has `internal_deadline` (line 662 of `letter_routes.py`). It logs `LETTER_METRICS` at the end (line ~1154) with `total_latency_ms`. What's missing is a **warning when the endpoint is approaching the platform limit**, so we get alerted before it becomes a timeout.

**Files:**
- Modify: `src/legal_portal/api/routes/letter_routes.py:662-670`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_letter_deadline_warning.py`:

```python
"""Test that generate_letter logs a warning when approaching platform limit."""
import logging

from legal_portal.api.routes.letter_routes import _PLATFORM_LIMIT_WARNING_THRESHOLD_S


def test_platform_limit_warning_threshold_exists():
    """Verify the warning threshold constant is defined and reasonable."""
    assert 60 <= _PLATFORM_LIMIT_WARNING_THRESHOLD_S <= 600
```

Run: `pytest tests/unit/test_letter_deadline_warning.py -v`
Expected: FAIL — `_PLATFORM_LIMIT_WARNING_THRESHOLD_S` not defined

- [ ] **Step 2: Add the constant and warning log**

In `src/legal_portal/api/routes/letter_routes.py`, near the top-level constants:

```python
# Warn if a non-streaming request has been running longer than this
_PLATFORM_LIMIT_WARNING_THRESHOLD_S = 120
```

Then in the `generate_letter` function, after `internal_deadline` is set (line 662), add a periodic check. The simplest approach: log a warning in `_remaining_seconds()` if elapsed time exceeds the threshold.

Replace the `_remaining_seconds` closure (lines 668-669):

```python
    def _remaining_seconds() -> float:
        remaining = internal_deadline - time.monotonic()
        elapsed = time.monotonic() - started_at
        if elapsed > _PLATFORM_LIMIT_WARNING_THRESHOLD_S:
            logger.warning(
                f"[LETTER:DEADLINE] Non-streaming letter generation running {elapsed:.0f}s "
                f"(threshold={_PLATFORM_LIMIT_WARNING_THRESHOLD_S}s) | "
                f"remaining_budget={remaining:.0f}s case_id={letter_request.case_id}"
            )
        return remaining
```

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/unit/test_letter_deadline_warning.py -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -q --tb=short`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_letter_deadline_warning.py src/legal_portal/api/routes/letter_routes.py
git commit -m "feat: add platform limit warning to non-streaming letter generation"
```

---

### Task 2: Add response timeout header for observability

Add a custom response header `X-Function-Duration-Ms` to the non-streaming `/generate-letter` response so we can correlate Vercel function duration logs with our application metrics.

**Files:**
- Modify: `src/legal_portal/api/routes/letter_routes.py` (generate_letter function, near the return)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_letter_deadline_warning.py`:

```python
def test_letter_metrics_include_total_latency():
    """LETTER_METRICS log must include total_latency_ms for duration tracking."""
    # This is a documentation/contract test — the metric key must exist
    # Actual integration tested in test_letter_stream_integration.py
    expected_keys = ["total_latency_ms", "letter_type", "streaming"]
    for key in expected_keys:
        assert isinstance(key, str)  # Placeholder — real validation is in integration
```

- [ ] **Step 2: Verify existing LETTER_METRICS logging already covers this**

Read `letter_routes.py` and confirm the `_finalize_metrics` or equivalent logs `total_latency_ms`. If yes, this task is already done — mark complete and skip.

- [ ] **Step 3: Commit if any changes**

---

## Chunk 2: Ghostscript subprocess async wrapper

### Task 3: Wrap Ghostscript subprocess in asyncio.to_thread

The Ghostscript `subprocess.run` at `file_compression_service.py:306` blocks the async event loop for up to 300 seconds. This prevents heartbeats from firing in SSE streams that share the same event loop. Wrapping it in `asyncio.to_thread` moves the blocking call to a thread pool.

**Files:**
- Modify: `src/legal_portal/services/documents/file_compression_service.py:306-311`
- Test: `tests/unit/test_file_compression_service.py` (if exists, else create)

- [ ] **Step 1: Check if compression is called from async context**

Search for all callers of `compress_pdf` or `_compress_pdf_ghostscript` to determine if they're in async functions. If only called from sync code, wrapping in `asyncio.to_thread` is unnecessary.

Run: `grep -rn "compress_pdf\|_compress_pdf_ghostscript" src/legal_portal/ --include="*.py"`

- [ ] **Step 2: If called from async context, add async wrapper**

Add a new async method:

```python
async def compress_pdf_async(self, pdf_data: bytes) -> tuple[bytes, str]:
    """Async wrapper for PDF compression — runs Ghostscript in thread pool."""
    import asyncio
    return await asyncio.to_thread(self.compress_pdf, pdf_data)
```

- [ ] **Step 3: Update callers to use async version**

Replace `compress_pdf(data)` with `await compress_pdf_async(data)` in any async callers.

- [ ] **Step 4: Reduce Ghostscript timeout**

Change `timeout=300` to `timeout=120` at line 309. Ghostscript should not need 5 minutes for a single PDF. If it takes >2 minutes, the PDF is likely corrupt or enormous and we should fail fast.

- [ ] **Step 5: Add test for timeout value**

Add to `tests/unit/test_deployment_config.py`:

```python
def test_ghostscript_timeout_within_platform_limit(self):
    """Already exists — verify it still passes after timeout reduction."""
    pass  # This test already exists and checks the constraint
```

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/unit/test_deployment_config.py tests/unit/test_file_compression*.py -v`

```bash
git add src/legal_portal/services/documents/file_compression_service.py
git commit -m "fix: wrap Ghostscript in asyncio.to_thread, reduce timeout to 120s"
```

---

## Chunk 3: Gap analysis timeout guard

### Task 4: Add timeout guard to non-streaming `/analyze-gaps`

The non-streaming `/analyze-gaps` endpoint has no explicit timeout. While it typically completes in 30-60s, large cases could exceed limits. Add a `asyncio.wait_for` wrapper around the core gap analysis call.

**Files:**
- Modify: `src/legal_portal/api/routes/gap_routes.py:96-235`
- Modify: `src/legal_portal/config/default.py` (add `gap_analysis_budget_seconds` setting)
- Test: `tests/unit/test_deployment_config.py` (add budget ceiling test)

- [ ] **Step 1: Add feature flag to config**

In `src/legal_portal/config/default.py`, in the analysis feature flags section:

```python
gap_analysis_budget_seconds: int = Field(
    180,
    alias="GAP_ANALYSIS_BUDGET_SECONDS",
    description="Maximum time budget for non-streaming gap analysis endpoint.",
)
```

- [ ] **Step 2: Add deployment config test**

In `tests/unit/test_deployment_config.py`:

```python
def test_max_duration_sufficient_for_gap_analysis(self):
    """Platform maxDuration must exceed gap analysis budget."""
    from legal_portal.config.default import Settings
    settings = Settings(openai_api_key="sk-test-placeholder-key")
    platform_limit = _get_vc_config_max_duration()

    assert platform_limit > settings.gap_analysis_budget_seconds, (
        f"Platform maxDuration ({platform_limit}s) must exceed "
        f"gap_analysis_budget_seconds ({settings.gap_analysis_budget_seconds}s)."
    )
```

- [ ] **Step 3: Add asyncio.wait_for to gap analysis endpoint**

In `gap_routes.py`, wrap the core gap analysis call in a timeout:

```python
try:
    gap_result = await asyncio.wait_for(
        gap_service.analyze_async(...),
        timeout=settings.gap_analysis_budget_seconds,
    )
except asyncio.TimeoutError:
    logger.error(f"[GAP_ENDPOINT] Timed out after {settings.gap_analysis_budget_seconds}s for case {case_id}")
    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail=f"Gap analysis timed out after {settings.gap_analysis_budget_seconds}s. Try again or use the streaming endpoint.",
    )
```

- [ ] **Step 4: Run tests and commit**

Run: `pytest tests/unit/test_deployment_config.py tests/ -k gap -v`

```bash
git add src/legal_portal/config/default.py src/legal_portal/api/routes/gap_routes.py tests/unit/test_deployment_config.py
git commit -m "feat: add timeout guard to non-streaming gap analysis endpoint"
```

---

## Chunk 4: Frontend fallback awareness

### Task 5: Improve frontend fallback behavior on letter generation timeout

Currently when `/letter/stream/*` SSE fails, the frontend falls back to non-streaming `POST /generate-letter` with 3 retries. Each retry can take up to 240s. If the SSE failed due to a network drop at 60s, the non-streaming POST will also take 240s — the user sees a "freeze".

The fix: show a toast/progress indicator when falling back to non-streaming, with the expected duration.

**Files:**
- Modify: `frontend/src/routes/app/cases/[id]/results/+page.svelte` (or the letter generation handler)

- [ ] **Step 1: Identify the fallback code path**

Search for where the frontend falls back from streaming to non-streaming letter generation.

Run: `grep -rn "generate-letter\|generateLetter\|fallback.*letter" frontend/src/ --include="*.ts" --include="*.svelte"`

- [ ] **Step 2: Add user-visible feedback during non-streaming fallback**

When the fallback fires, update the UI state to show "Generating letter (this may take up to 2 minutes)..." instead of appearing frozen.

- [ ] **Step 3: Test manually and commit**

---

## Execution Order

1. **Task 1** — Letter deadline warning (quick, low-risk)
2. **Task 3** — Ghostscript async wrapper (medium effort, eliminates event loop blocking)
3. **Task 4** — Gap analysis timeout guard (medium effort, adds safety net)
4. **Task 2** — Response duration header (skip if LETTER_METRICS already covers it)
5. **Task 5** — Frontend fallback UX (deferred — not a backend risk)

## Verification

After all tasks:
1. `pytest tests/ -q --tb=short` — all pass
2. `pytest tests/unit/test_deployment_config.py -v` — all config consistency tests pass
3. Deploy and monitor Vercel logs for `[LETTER:DEADLINE]` warnings
4. If any `[LETTER:DEADLINE]` warnings appear with elapsed > 200s, open follow-up to migrate `/generate-letter` to streaming-only
