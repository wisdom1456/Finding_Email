# Trustworthy Wait — Phase 1 Design

**Date:** 2026-07-23
**Status:** Proposed
**Scope:** Anti-restart + honest progress. Resume-in-place explicitly deferred to Phase 2.

---

## 1. Context

Attorneys wait 5–15 minutes for a case analysis. During that wait the UI gives them
two bad signals, and one dangerous button.

This spec was originally motivated by the belief that user-initiated restarts were
why analyses never finished. **That turned out to be wrong.** The dominant cause was
a database bug — `reconcile_analysis_jobs()` resurrecting stale terminal state onto
the reused per-case `analysis_results` row — fixed and merged in PR #8
(`20260723215844_fix_reconcile_resurrecting_stale_jobs`). Runs now complete on their own.

Phase 1 is therefore **not** a reliability fix. It is a UX and robustness fix for three
independently verified problems that remain:

| # | Problem | Evidence |
|---|---|---|
| P1 | **Restart-from-zero.** `/start` supersedes the running job and inserts a *fresh* job with an empty checkpoint. The completed-stage checkpoint stays stranded on the dead job, so a re-run redoes all work. | `analysis_core.py:150-153` (supersede), `:217-223` (fresh insert, no checkpoint carry) |
| P2 | **Frozen percent.** `deep_analysis` creeps 70→86 then **freezes at 86 for minutes** while only an elapsed-seconds ticker moves. Summarization/synthesis emit a *literally constant* percent. | `multi_stage_analyzer.py:688-694` (`min(80, elapsed/2)` capped → +16 max), `main_processor.py:47-92` |
| P3 | **Stage ids don't match.** DB `analysis_jobs.stage` CHECK allows 11 values; the frontend's 6 `DEFAULT_STAGES` use different ids (`doc_analysis` vs `summarization`, `legal_mapping` vs `issue_mapping`), so step display can't reliably track the backend. | `analysis_jobs_stage_check`; `progressStore.ts:89-96` |

A frozen bar plus an always-available **Start** button is an invitation to destroy
work in flight. Removing that invitation is cheap and permanent.

## 2. Goals / Non-goals

**Goals**
- G1. It is **impossible** to destroy a healthy in-flight run with a single click.
- G2. A user watching a legitimately slow stage can tell it is *working*, not *stuck*.
- G3. The frontend renders from **one server-computed state**, not re-derived client logic.

**Non-goals (explicitly deferred)**
- Resume-in-place / carrying the checkpoint across a re-run → **Phase 2**
- `analysis_results.progress->>job_id` ownership stamp → **Phase 2**
- Pipeline speed-up (batching/parallelism) → separate spec
- Fire-and-forget notifications ("we'll email you") → separate spec

## 3. Design

### 3.1 Canonical run state (server-computed)

One enum, computed server-side, is the **only** thing the UI branches on. Today the
case page derives "is a run active" from the `analysis_results` row
(`+page.svelte:73-75`), which **lags** the job — the job row is authoritative.

Conditions are evaluated **top-to-bottom; first match wins** — so the states are
mutually exclusive by construction and every input resolves to exactly one.

| `ui_state` | Condition | Controls rendered |
|---|---|---|
| `idle` | no job row exists for the case | **Start analysis** |
| `queued` | latest job `pending` | progress (queue position) + **Cancel** |
| `running` | latest job `running`, `heartbeat_age_seconds` < 180 | progress + **Cancel** — *no Start* |
| `stalled` | latest job `running`, `heartbeat_age_seconds` ≥ 180 | ⚠️ worker unresponsive + **Start over** |
| `completed` | latest job `completed`, or a persisted result exists | View results + **Re-run** |
| `failed` | latest job `failed` | error detail + **Start over** |
| `cancelled` | latest job `cancelled` | reason line + **Start analysis** |

In `cancelled`, show a one-line reason derived from `analysis_jobs.error`:
`"Superseded by re-run"` → *"Replaced by a newer run."*; a plain user cancel
(`error IS NULL`) → *"Cancelled."*; any other non-null error → that text verbatim.
This keeps a cancelled run from looking like a silent stop.

Ordering rationale: active states (`queued`/`running`/`stalled`) are checked before
terminal ones so a newly-started run is never masked by the previous run's outcome —
the exact lag that made `rerunIsActiveRun` unreliable today.

**Invariant (G1):** in `queued` and `running`, no control exists that calls
`POST /api/analysis/start`. Cancel is the only action. This is a *rendering*
guarantee, not a confirm dialog — the dialog at `+page.svelte:76-80` becomes
unreachable for active runs and its active-run branch is deleted.

> Note: `stalled` offers **Start over**, not **Resume** — resume-in-place is Phase 2.
> Until then "Start over" honestly describes what happens (fresh job, work redone).

### 3.2 Canonical 6-step mapping (fixes P3)

Single source of truth, defined server-side and mirrored in one frontend constant:

| Step | Label | DB `stage` values |
|---|---|---|
| 1 | Preparing documents | `queued`, `preparing` |
| 2 | Analyzing documents | `summarization`, `synthesis` |
| 3 | Extracting key facts | `fact_extraction` |
| 4 | Mapping legal issues | `issue_mapping` |
| 5 | Running deep analysis | `deep_analysis`, `gap_analysis` |
| 6 | Finalizing results | `finalizing` |

Terminal `completed` / `failed` are states, not steps. The DB CHECK constraint is
**unchanged** — this is a presentation mapping only.

### 3.3 Honest progress payload (fixes P2)

`GET /api/progress/jobs/{job_id}/status` (`progress.py:408-425`) gains four fields
alongside the existing `stage`/`percent`/`heartbeat_age_seconds`:

```jsonc
{
  "ui_state":    "running",
  "step_index":  3,          // 1..6
  "step_total":  6,
  "step_label":  "Extracting key facts",
  "items_done":  42,         // nullable — omitted when unknown
  "items_total": 71,         // nullable
  "eta_seconds": 380,        // nullable, always an estimate
  "healthy":     true        // heartbeat_age_seconds < 180
}
```

`GET /api/analysis/status/{case_id}` gains `ui_state` (computed from the latest **job**,
falling back to the result row) so the case page has one field to branch on.

**Display rule — the core of G2.** The UI shows *step + substance + liveness*, and the
raw percent stops being the primary signal:

```
Step 3 of 6 · Extracting key facts
42 of 71 documents · ~6 min remaining
Working normally · updated 4s ago
```

When `items_*` are unavailable (e.g. the single long `deep_analysis` call), the line
degrades honestly to:

```
Step 5 of 6 · Running deep analysis
This step takes several minutes on large cases
Working normally · updated 7s ago
```

"Working normally" is driven by `healthy` (heartbeat freshness), **not** by percent
movement. This is precisely why a frozen 86% no longer reads as broken.

**`items_done`/`items_total` source.** `DBProgressManager.publish_progress` already
accepts a `stats` kwarg and writes it into the progress JSON
(`db_progress_manager.py:87-88`). Phase 1 passes `{items_done, items_total}` through
`stats` from the per-document stages (summarization already knows
`"Batch 1 complete (12/12 docs summarized)"`). Stages without a natural item count
simply omit them — no fabricated denominators.

### 3.4 ETA — per remaining step

`eta_seconds` is the estimate to finish the whole run, but it is **built by summing
per-step estimates** rather than treating the run as one blob — so it stays accurate
as the run moves through cheap and expensive steps, and the same per-step numbers
drive the "this step takes several minutes" copy.

A constant table gives each of the 6 steps a `seconds_per_doc` (and a small fixed
floor for steps whose cost is roughly doc-independent, e.g. finalizing):

```
step_estimate(step)  = floor_seconds[step] + seconds_per_doc[step] × doc_count
eta_seconds          = max(0,
                           (step_estimate(current) − elapsed_in_current_step)   // finish current step
                         + Σ step_estimate(s) for s in steps after current)      // all later steps
```

Baselines seeded from observed runs (Nelson 33 docs = 319s total; Martinez 71 docs =
443s total), apportioned across steps using their known relative cost
(`deep_analysis` and summarization dominate; issue-mapping and finalizing are short).

Guards:
- Never render a countdown that hits 0 and sticks — once `eta_seconds` reaches 0 or
  the run is in the final step past its estimate, show **"almost done"**.
- Never render an ETA in `stalled`.
- Round to a coarse unit (`~6 min`), never `5m 43s` — false precision erodes trust.
- The current-step remainder is floored at 0 so an over-running step never makes the
  later-steps sum go backwards.

Refining the per-step baselines from historical job durations is **Phase 2**.

### 3.5 What is NOT changing

- The 180s `maxHeartbeatStaleSeconds` dead-worker detector (`pollingClient.ts:247-268`)
  and its deliberate ignoring of percent stagnation — both already correct.
- `analysis_jobs` schema and the `stage` CHECK constraint.
- Worker pipeline, checkpoint logic, cancel/supersede semantics.
- `POST /api/analysis/start` behaviour. It stays destructive-on-purpose; Phase 1
  simply stops rendering a path to it during an active run.

## 4. Files touched

| File | Change |
|---|---|
| `src/legal_portal/api/routes/progress.py` | add `ui_state`, `step_*`, `items_*`, `eta_seconds`, `healthy` to the job status response |
| `src/legal_portal/api/routes/analysis_core.py` | add `ui_state` to `GET /status/{case_id}` (derive from latest job) |
| `src/legal_portal/core/analysis_state.py` *(or new `run_state.py`)* | `STAGE_TO_STEP` map, `compute_ui_state()`, `estimate_eta()`, `cancel_reason()` — pure functions, unit-testable |
| `src/legal_portal/services/analysis/main_processor.py`, `multi_stage_analyzer.py` | pass `stats={items_done, items_total}` where a count exists |
| `frontend/src/lib/stores/progressStore.ts` | replace `DEFAULT_STAGES` ids with the canonical 6; carry new fields |
| `frontend/src/lib/utils/pollingClient.ts` | pass new fields through (stall logic unchanged) |
| `frontend/src/lib/components/InlineAnalysisProgress.svelte` | render step/items/ETA/liveness line |
| `frontend/src/routes/app/cases/[id]/+page.svelte` | render by `ui_state`; delete the active-run branch of the re-run dialog; no Start while `queued`/`running` |

## 5. Error handling

- `ui_state` computation must never throw — unknown/missing `stage` falls back to
  step 1 with the raw stage string as label, and the run is still cancellable.
- Missing/failed status fetch keeps the **last known** state and shows
  "reconnecting…"; it must not flip the UI to `idle` (which would re-expose Start).
- `eta_seconds` is best-effort; any error omits the field rather than failing the response.
- `stalled` must remain reachable — if the worker dies, the user is never trapped
  with only a Cancel button.

## 6. Testing

**Backend (pytest)**
- `compute_ui_state()` — table test over every (job status × heartbeat age × result
  presence) combination, including no-job and unknown-stage.
- `STAGE_TO_STEP` — every one of the 11 CHECK-allowed stage values maps to a step or
  an explicit terminal. *A stage value with no mapping is a test failure* (guards P3
  from regressing).
- `estimate_eta()` — never negative; the later-steps sum never grows when the current
  step over-runs (current-step remainder floored at 0); omitted when inputs missing.
- `cancel_reason()` — `"Superseded by re-run"` → replaced-copy; `NULL` → cancelled-copy;
  other → verbatim.
- Status endpoints return the new fields for a running job.

**Frontend (vitest)**
- For each `ui_state`, assert the rendered control set — **explicitly assert no Start
  button exists in `queued`/`running`** (this is G1's regression test).
- Frozen percent + fresh heartbeat renders "Working normally" (P2's regression test).
- `pollingClient` passes new fields through; existing 19 stall tests stay green.

**Manual (prod)**
- Run a case **with prior failure history** (not a fresh one — that mistake is what
  hid the reconcile bug) and confirm the step line advances 1→6 and never shows a
  Start button mid-run.

## 7. Rollout

Behind `PUBLIC_ENABLE_TRUSTWORTHY_WAIT` (default **off**). The API additions are
purely additive and ship unflagged — new fields are ignored by the current UI, so
there is no coupled deploy. Flag on in preview → verify on a history-bearing case →
flag on in prod. Rollback is a flag flip, not a revert.

## 8. Resolved decisions

- **Cancelled shows why** (§3.1): one line derived from `analysis_jobs.error` —
  superseded vs user-cancel vs other. Approved.
- **ETA is built per-step** (§3.4), summed to a whole-run number, rather than a single
  blob estimate. Approved.

## 9. Phase 2 (not this spec)

Resume-in-place (`POST /api/analysis/resume/{case_id}` reusing the existing job row so
the checkpoint survives), the `analysis_results` ownership stamp, and ETA baselines
learned from history.
