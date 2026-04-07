# Analysis Progress Feedback — Design Spec

## Context

Users see broken feedback when analysis jobs run via the durable worker (Railway):

1. **`analysis_results.status` stays `pending` forever** — the worker never sets it to `processing`. The frontend auto-progress modal only opens for `status === 'processing'`, so it never opens on page load/refresh.
2. **No job info on page load** — `loadAnalysisStatus()` only queries `analysis_results`, never `analysis_jobs`. Even if the modal opened, it wouldn't have the `job_id` needed to poll real progress.
3. **No queue feedback** — when a job is pending (worker busy with another case), users see a static "pending" badge with no explanation.
4. **Re-runs hide completed results** — inserting a new `analysis_results` row on re-run means the pending row takes priority, hiding the completed analysis the user actually wants to see.
5. **Multiple stale rows accumulate** — ceryn's case has 6 `analysis_results` rows (2 errors, 3 completed, 1 pending).

**Affected users (incident 2026-04-07):**
- ceryn@brflorida.com: sees loading spinner, can't access her completed results because a new pending analysis hides them.
- modible@gmail.com: job actively running (deep_analysis stage), UI shows static "pending".

## Design Decisions

- **One analysis result per case.** Re-run resets the existing row, not inserts a new one. Confirmation dialog before overwriting.
- **Queue feedback shows position + reason**, not ETAs. "Your analysis is #2 in the queue. The worker is currently processing another case."
- **Single worker** is the current deployment model. Queue logic is simple FIFO by `created_at`.

## Changes

### 1. Backend: Worker sets `analysis_results.status = 'processing'`

**File:** `worker/analysis_worker.py` — `_process_job` method

After claiming the job (after `claim_analysis_job` RPC returns), before running the pipeline, add:

```python
self.supabase.table("analysis_results").update({
    "status": "processing",
}).eq("id", analysis_id).eq("status", "pending").execute()
```

The `.eq("status", "pending")` guard prevents a stale worker from reviving a cancelled/completed row.

### 2. Backend: `analysis/start` resets existing row

**File:** `src/legal_portal/api/routes/analysis_core.py` — `start_analysis` endpoint

Replace the current insert-always logic with:

```python
# 1. Cancel any active analysis_jobs for this case
service_supabase.table("analysis_jobs").update({
    "status": "cancelled",
    "error": "Superseded by re-run",
}).eq("case_id", case_id).in_("status", ["pending", "running"]).execute()

# 2. Reset or create analysis_results row
existing = user_supabase.table("analysis_results") \
    .select("id").eq("case_id", case_id).limit(1).maybeSingle().execute()

if existing.data:
    analysis_response = user_supabase.table("analysis_results").update({
        "status": "pending",
        "result": None,
        "error": None,
        "completed_at": None,
        "progress": None,
    }).eq("id", existing.data["id"]).execute()
else:
    analysis_response = user_supabase.table("analysis_results").insert({
        "case_id": case_id,
        "status": "pending",
    }).execute()

# 3. Create new job row (unchanged from current code)
```

Step 1 explicitly cancels stale jobs before the new job insert, preventing `idx_one_active_job_per_case` violations.

### 3. Backend: Queue position in job status endpoint

**File:** `src/legal_portal/api/routes/progress.py` — `get_job_status` endpoint

Add two fields to the response when job status is `pending`:

```python
queue_position = None
worker_busy = None

if j["status"] == "pending":
    ahead = supabase.table("analysis_jobs").select("id", count="exact") \
        .eq("status", "pending") \
        .lt("created_at", j["created_at"]).execute()
    queue_position = (ahead.count or 0) + 1

    running = supabase.table("analysis_jobs").select("id", count="exact") \
        .eq("status", "running").execute()
    worker_busy = (running.count or 0) > 0

# Add to response dict:
"queue_position": queue_position,
"worker_busy": worker_busy,
```

Both fields are `null` when the job is not pending.

### 4. Frontend: Simplify `loadAnalysisStatus`

**File:** `frontend/src/routes/app/cases/[id]/+page.svelte` — `loadAnalysisStatus` function

Replace the 4-step priority resolution cascade (lines 393-451) with:

```typescript
async function loadAnalysisStatus() {
    try {
        // One row per case after cleanup; order as safety net during transition
        const { data, error } = await withRetry(() =>
            supabase
                .from('analysis_results')
                .select('id, status, created_at, completed_at')
                .eq('case_id', caseId as string)
                .order('created_at', { ascending: false })
                .limit(1)
                .maybeSingle()
        );
        if (error) throw error;

        // If active, fetch job info for job_id and real status
        if (data && ['pending', 'processing'].includes(data.status)) {
            const { data: jobData } = await withRetry(() =>
                supabase
                    .from('analysis_jobs')
                    .select('id, status, stage')
                    .eq('analysis_id', data.id)
                    .in('status', ['pending', 'running'])
                    .limit(1)
                    .maybeSingle()
            );
            if (jobData) {
                currentJobId = jobData.id;
            }
        }

        analysisStatus = data;
    } catch (error: any) {
        console.error('Failed to load analysis status:', error);
        analysisStatus = null;
    }
}
```

### 5. Frontend: Auto-open progress modal for in-flight jobs

**File:** `frontend/src/routes/app/cases/[id]/+page.svelte` — `onMount` block

Change the auto-mount condition (line 240) from:

```typescript
if (analysisBackendOnly && analysisStatus?.status === 'processing')
```

To:

```typescript
if (analysisBackendOnly
    && ['pending', 'processing'].includes(analysisStatus?.status)
    && currentJobId) {
    currentAnalysisId = analysisStatus.id;
    showProgressModal = true;
}
```

### 6. Frontend: Queue feedback messages

**File:** `frontend/src/lib/stores/progressStore.ts` — `messageHandler` function

Update the pending message logic (around line 567) to use queue position:

```typescript
if (isDurable && eventStatus === 'pending') {
    if (event.queue_position && event.queue_position > 1) {
        message = `Your analysis is #${event.queue_position} in the queue. The worker is currently processing another case.`;
    } else if (event.worker_busy) {
        message = `Your analysis is next. The worker is currently finishing another case.`;
    } else if (event.attempts > 0) {
        message = `Resuming analysis from last checkpoint (attempt ${event.attempts}/${event.max_attempts})...`;
    } else {
        message = 'Analysis queued — starting shortly...';
    }
}
```

### 7. Frontend: Re-run confirmation dialog

**File:** `frontend/src/routes/app/cases/[id]/+page.svelte`

When clicking "Re-run Analysis" and a completed result exists, show a confirmation dialog before calling `runAnalysis()`:

```
"This will replace your current analysis results. Do you want to re-run the analysis?"
[Cancel] [Re-run]
```

Gate the `runAnalysis()` call behind this confirmation when `analysisStatus?.status === 'completed'`.

### 8. Data cleanup migration

**One-time script** (not a schema migration — no DDL changes needed):

```sql
-- Keep one row per case: prefer completed, then latest
DELETE FROM analysis_results
WHERE id NOT IN (
    SELECT DISTINCT ON (case_id) id
    FROM analysis_results
    ORDER BY case_id,
             CASE WHEN status = 'completed' THEN 0
                  WHEN status IN ('pending', 'processing') THEN 1
                  ELSE 2 END,
             created_at DESC
);

-- Clean up old terminal jobs (> 7 days)
DELETE FROM analysis_jobs
WHERE status IN ('failed', 'cancelled', 'completed')
AND completed_at < NOW() - INTERVAL '7 days';
```

Existing unique partial indexes already prevent future duplicates:
- `idx_one_active_analysis_per_case` on `analysis_results(case_id) WHERE status IN ('pending', 'processing')`
- `idx_one_active_job_per_case` on `analysis_jobs(case_id) WHERE status IN ('pending', 'running')`

### 9. Immediate manual fix (pre-deploy)

Cancel ceryn's stuck pending analysis and its queued job so she can see her completed results now:

```sql
-- Cancel the queued job
UPDATE analysis_jobs SET status = 'cancelled', error = 'Manual cleanup'
WHERE id = '8f21faf6-943c-4ed0-9338-43cc21646adc';

-- Cancel the pending analysis result
UPDATE analysis_results SET status = 'cancelled'
WHERE id = 'a08b0448-13fb-4fae-9441-7865aeed782d';

-- Set case back to completed (she has completed results)
UPDATE cases SET status = 'completed'
WHERE id = 'e453034e-8e3a-4f51-988a-5b00978d6036';
```

## Files Modified

| File | Change |
|------|--------|
| `worker/analysis_worker.py` | Add `analysis_results.status = 'processing'` on claim |
| `src/legal_portal/api/routes/analysis_core.py` | Reset existing row + cancel stale jobs on re-run |
| `src/legal_portal/api/routes/progress.py` | Add `queue_position` + `worker_busy` to job status |
| `frontend/src/routes/app/cases/[id]/+page.svelte` | Simplify `loadAnalysisStatus`, auto-open modal, re-run confirmation |
| `frontend/src/lib/stores/progressStore.ts` | Queue feedback messages |

## Existing Code Reused

- `idx_one_active_analysis_per_case` / `idx_one_active_job_per_case` — unique partial indexes already enforce one-active invariants
- `update_analysis_results_updated_at` trigger — auto-handles `updated_at` on all updates
- `claim_analysis_job` RPC — atomic job claiming with `FOR UPDATE SKIP LOCKED`
- `InlineAnalysisProgress` component — existing step-by-step progress UI, works correctly when given a `jobId`
- `PollingClient` — existing polling mechanism, already handles durable job responses
- `JOB_STAGE_MAP` in progressStore — already maps job stages to frontend stage IDs

## Verification

1. **Worker status transition:** Start analysis, check `analysis_results.status` transitions `pending` -> `processing` -> `completed`.
2. **Page refresh during processing:** Start analysis, refresh page, verify progress modal auto-opens with correct stage display.
3. **Queue feedback:** Start two analyses concurrently (different cases). Second one should show queue position message.
4. **Re-run confirmation:** Complete an analysis, click Re-run, verify confirmation dialog appears. Confirm, verify old result is replaced (not duplicated).
5. **Re-run cancels old job:** Start analysis, before it completes click Re-run and confirm. Verify old job is cancelled, new job is created.
6. **Cleanup migration:** Run the cleanup SQL, verify each case has exactly one `analysis_results` row.
7. **Manual fix:** Run the ceryn fix SQL, verify she can see her completed results.
