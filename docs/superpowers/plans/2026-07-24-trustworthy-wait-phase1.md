# Trustworthy Wait — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the analysis wait trustworthy — impossible to destroy a healthy in-flight run with one click, and a UI that shows a legitimately slow stage as *working* rather than *stuck*.

**Architecture:** A new pure-Python module `run_state.py` computes one canonical `ui_state` enum plus step/ETA/cancel-reason from raw job data. Two status endpoints emit those fields (purely additive). The frontend renders from that single server-computed state, gated by `PUBLIC_ENABLE_TRUSTWORTHY_WAIT`, and — in active states — renders no control that can call `POST /api/analysis/start`.

**Tech Stack:** FastAPI + Supabase (Python), SvelteKit + Svelte 5 runes + Vitest (frontend), pytest.

Design spec: `docs/superpowers/specs/2026-07-23-trustworthy-wait-phase1-design.md`.

## Global Constraints

- **Flag:** `PUBLIC_ENABLE_TRUSTWORTHY_WAIT`, default **off**. Frontend rendering changes are gated on it. Backend status fields ship **unflagged** (additive — ignored by current UI).
- **No schema changes.** `analysis_jobs.stage` CHECK (11 values: `queued, preparing, summarization, synthesis, fact_extraction, issue_mapping, deep_analysis, gap_analysis, finalizing, completed, failed`) is unchanged. The 6-step mapping is presentation-only.
- **Stall threshold is 180s** (`heartbeat_age_seconds >= 180` → `stalled`). Do not change `pollingClient.ts` stall logic.
- **`ui_state` computation must never throw.** Unknown/missing stage → step 1 with the raw stage as label; run stays cancellable.
- **ETA is always an estimate:** coarse rounding (`~6 min`, never `5m 43s`); never shown in `stalled`; "almost done" once it reaches 0.
- **Copy rules (verbatim):** cancelled reasons — `"Superseded by re-run"` → `"Replaced by a newer run."`; `NULL` error → `"Cancelled."`; other → the error text verbatim. Liveness line uses `"Working normally"` driven by heartbeat freshness, never percent movement.
- **Canonical 6 steps (id → label):** 1 Preparing documents, 2 Analyzing documents, 3 Extracting key facts, 4 Mapping legal issues, 5 Running deep analysis, 6 Finalizing results.
- **State precedence:** first-match-wins, active states (`queued`/`running`/`stalled`) checked before terminal ones.

---

### Task 1: `run_state.py` — stage→step, ui_state, cancel_reason

**Files:**
- Create: `src/legal_portal/core/run_state.py`
- Test: `tests/unit/test_run_state.py`

**Interfaces:**
- Produces:
  - `STEP_LABELS: dict[int, str]` (keys 1..6)
  - `STAGE_TO_STEP: dict[str, int]`
  - `stage_to_step(stage: str | None) -> int` (returns 1..6; unknown/None → 1)
  - `step_label(stage: str | None) -> str` (canonical label, or raw stage verbatim if unmapped)
  - `compute_ui_state(*, job: dict | None, has_result: bool, heartbeat_age_seconds: float | None, stall_threshold: int = 180) -> str` → one of `idle|queued|running|stalled|completed|failed|cancelled`
  - `cancel_reason(error: str | None) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_run_state.py
import pytest
from legal_portal.core import run_state as rs


@pytest.mark.parametrize("stage,expected", [
    ("queued", 1), ("preparing", 1),
    ("summarization", 2), ("synthesis", 2),
    ("fact_extraction", 3),
    ("issue_mapping", 4),
    ("deep_analysis", 5), ("gap_analysis", 5),
    ("finalizing", 6),
])
def test_stage_to_step_maps_all_pipeline_stages(stage, expected):
    assert rs.stage_to_step(stage) == expected


@pytest.mark.parametrize("stage", ["completed", "failed"])
def test_stage_to_step_terminal_defaults_to_step_1(stage):
    # terminal stages are states, not steps — default without raising
    assert rs.stage_to_step(stage) == 1


def test_stage_to_step_unknown_and_none_default_to_1():
    assert rs.stage_to_step("wat") == 1
    assert rs.stage_to_step(None) == 1


def test_step_label_known_and_unknown():
    assert rs.step_label("fact_extraction") == "Extracting key facts"
    assert rs.step_label("deep_analysis") == "Running deep analysis"
    # unmapped → raw stage verbatim, never a crash
    assert rs.step_label("mystery_stage") == "mystery_stage"


def test_every_check_allowed_stage_maps_or_is_terminal():
    # Guards P3: a stage the DB can emit with no step mapping is a bug.
    check_stages = {
        "queued", "preparing", "summarization", "synthesis", "fact_extraction",
        "issue_mapping", "deep_analysis", "gap_analysis", "finalizing",
        "completed", "failed",
    }
    terminal = {"completed", "failed"}
    for s in check_stages - terminal:
        assert s in rs.STAGE_TO_STEP, f"stage {s} has no step mapping"


@pytest.mark.parametrize("job,has_result,hb,expected", [
    (None, False, None, "idle"),
    ({"status": "pending", "stage": "queued"}, False, None, "queued"),
    ({"status": "running", "stage": "deep_analysis"}, False, 20, "running"),
    ({"status": "running", "stage": "deep_analysis"}, False, 200, "stalled"),
    ({"status": "running", "stage": "deep_analysis"}, False, None, "running"),  # no hb yet → treat alive
    ({"status": "completed", "stage": "completed"}, True, 300, "completed"),
    ({"status": "cancelled", "stage": "summarization"}, False, None, "cancelled"),
    ({"status": "failed", "stage": "deep_analysis"}, False, None, "failed"),
    # active beats a stale prior result: running job + old result present → running, not completed
    ({"status": "running", "stage": "preparing"}, True, 5, "running"),
])
def test_compute_ui_state(job, has_result, hb, expected):
    assert rs.compute_ui_state(job=job, has_result=has_result, heartbeat_age_seconds=hb) == expected


def test_compute_ui_state_never_raises_on_garbage():
    assert rs.compute_ui_state(job={"status": "weird"}, has_result=False, heartbeat_age_seconds=None) in {
        "idle", "queued", "running", "stalled", "completed", "failed", "cancelled",
    }


@pytest.mark.parametrize("error,expected", [
    ("Superseded by re-run", "Replaced by a newer run."),
    (None, "Cancelled."),
    ("Provider quota exceeded", "Provider quota exceeded"),
])
def test_cancel_reason(error, expected):
    assert rs.cancel_reason(error) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_run_state.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'legal_portal.core.run_state'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/legal_portal/core/run_state.py
"""Pure functions that turn raw analysis_jobs data into UI-facing run state.

No I/O, no Supabase, no exceptions escape. Unit-tested in isolation. This is the
single source of truth for the 6-step display and the ui_state enum the frontend
branches on.
"""
from __future__ import annotations

from typing import Optional

# Canonical 6-step UI (presentation only — DB stage CHECK is unchanged).
STEP_LABELS: dict[int, str] = {
    1: "Preparing documents",
    2: "Analyzing documents",
    3: "Extracting key facts",
    4: "Mapping legal issues",
    5: "Running deep analysis",
    6: "Finalizing results",
}

# DB stage value -> step. `completed`/`failed` are terminal states, not steps.
STAGE_TO_STEP: dict[str, int] = {
    "queued": 1,
    "preparing": 1,
    "summarization": 2,
    "synthesis": 2,
    "fact_extraction": 3,
    "issue_mapping": 4,
    "deep_analysis": 5,
    "gap_analysis": 5,
    "finalizing": 6,
}

STEP_TOTAL = 6


def stage_to_step(stage: Optional[str]) -> int:
    """Map a DB stage to a 1..6 step. Unknown/None/terminal → 1 (never raises)."""
    return STAGE_TO_STEP.get(stage or "", 1)


def step_label(stage: Optional[str]) -> str:
    """Human label for a stage's step; unmapped stage returned verbatim."""
    step = STAGE_TO_STEP.get(stage or "")
    if step is None:
        return stage or STEP_LABELS[1]
    return STEP_LABELS[step]


def compute_ui_state(
    *,
    job: Optional[dict],
    has_result: bool,
    heartbeat_age_seconds: Optional[float],
    stall_threshold: int = 180,
) -> str:
    """First-match-wins; active states beat terminal ones. Never raises."""
    try:
        status = (job or {}).get("status")
        if job is None or status is None:
            return "completed" if has_result else "idle"
        if status == "pending":
            return "queued"
        if status == "running":
            if heartbeat_age_seconds is not None and heartbeat_age_seconds >= stall_threshold:
                return "stalled"
            return "running"
        if status == "completed" or has_result:
            return "completed"
        if status == "failed":
            return "failed"
        if status == "cancelled":
            return "cancelled"
        return "completed" if has_result else "idle"
    except Exception:
        return "completed" if has_result else "idle"


def cancel_reason(error: Optional[str]) -> str:
    """One-line reason for a cancelled run."""
    if error == "Superseded by re-run":
        return "Replaced by a newer run."
    if not error:
        return "Cancelled."
    return error
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_run_state.py -q`
Expected: PASS (all parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/core/run_state.py tests/unit/test_run_state.py
git commit -m "feat(analysis): run_state helpers — stage→step, ui_state, cancel_reason"
```

---

### Task 2: `run_state.py` — per-step ETA

**Files:**
- Modify: `src/legal_portal/core/run_state.py`
- Test: `tests/unit/test_run_state.py` (append)

**Interfaces:**
- Consumes: `STEP_TOTAL`, `stage_to_step` (Task 1)
- Produces:
  - `step_estimate(step: int, doc_count: int) -> int` (seconds for one step)
  - `estimate_eta(*, current_step: int, doc_count: int, elapsed_in_step_seconds: float) -> int` (whole-run seconds remaining, ≥ 0)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/test_run_state.py

def test_step_estimate_scales_with_docs():
    small = rs.step_estimate(5, 10)
    big = rs.step_estimate(5, 71)
    assert big > small > 0


def test_estimate_eta_decreases_as_run_progresses():
    early = rs.estimate_eta(current_step=1, doc_count=71, elapsed_in_step_seconds=0)
    late = rs.estimate_eta(current_step=5, doc_count=71, elapsed_in_step_seconds=0)
    assert early > late


def test_estimate_eta_never_negative_when_step_overruns():
    # current step far over its estimate must not push the total negative
    eta = rs.estimate_eta(current_step=6, doc_count=1, elapsed_in_step_seconds=99999)
    assert eta == 0


def test_estimate_eta_overrun_current_step_does_not_grow_later_sum():
    # over-running the current step floors its remainder at 0; later steps unchanged
    base = rs.estimate_eta(current_step=3, doc_count=71, elapsed_in_step_seconds=0)
    overrun = rs.estimate_eta(current_step=3, doc_count=71, elapsed_in_step_seconds=100000)
    assert overrun <= base
    assert overrun >= 0


def test_estimate_eta_ballpark_matches_observed_runs():
    # seeded from prod: Martinez 71 docs finished ~443s. Whole-run estimate at start
    # should be within a sane band (not off by an order of magnitude).
    eta = rs.estimate_eta(current_step=1, doc_count=71, elapsed_in_step_seconds=0)
    assert 250 <= eta <= 900
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_run_state.py -k estimate_eta -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'estimate_eta'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/legal_portal/core/run_state.py`:

```python
# ETA baselines, seeded from observed prod runs (Nelson 33 docs≈319s,
# Martinez 71 docs≈443s → whole-run floor≈211s, ≈3.26 s/doc), apportioned across
# steps by relative cost. Refining these from history is Phase 2.
_STEP_FLOOR_SECONDS: dict[int, int] = {1: 20, 2: 40, 3: 40, 4: 20, 5: 60, 6: 31}
_STEP_SECONDS_PER_DOC: dict[int, float] = {1: 0.2, 2: 1.0, 3: 0.6, 4: 0.2, 5: 1.06, 6: 0.2}


def step_estimate(step: int, doc_count: int) -> int:
    step = max(1, min(STEP_TOTAL, step))
    docs = max(0, doc_count or 0)
    return int(round(_STEP_FLOOR_SECONDS[step] + _STEP_SECONDS_PER_DOC[step] * docs))


def estimate_eta(*, current_step: int, doc_count: int, elapsed_in_step_seconds: float) -> int:
    """Whole-run seconds remaining = remainder of current step + all later steps."""
    current_step = max(1, min(STEP_TOTAL, current_step))
    remaining_current = max(0, step_estimate(current_step, doc_count) - int(elapsed_in_step_seconds or 0))
    later = sum(step_estimate(s, doc_count) for s in range(current_step + 1, STEP_TOTAL + 1))
    return max(0, remaining_current + later)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_run_state.py -q`
Expected: PASS (Task 1 + Task 2 cases)

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/core/run_state.py tests/unit/test_run_state.py
git commit -m "feat(analysis): per-step ETA in run_state (summed to whole-run seconds)"
```

---

### Task 3: Job status endpoint emits the new fields

**Files:**
- Modify: `src/legal_portal/api/routes/progress.py` (the `return {...}` at `:408-425`, inside `get_job_status` at `:330`)
- Test: `tests/unit/test_progress_ui_fields.py` (create)

**Interfaces:**
- Consumes: `run_state.compute_ui_state`, `stage_to_step`, `step_label`, `estimate_eta`, `cancel_reason`, `STEP_TOTAL` (Tasks 1–2)
- Produces: job-status JSON gains `ui_state, step_index, step_total, step_label, items_done, items_total, eta_seconds, healthy, cancel_reason`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_progress_ui_fields.py
from legal_portal.api.routes import progress as prog


def test_build_ui_fields_running_job():
    j = {"status": "running", "stage": "deep_analysis", "error": None,
         "doc_count": 71, "started_at": None}
    progress = {"percent": 86, "stats": {"items_done": 40, "items_total": 71}}
    out = prog._build_ui_fields(j, progress, heartbeat_age=12.0, elapsed_in_step=30)
    assert out["ui_state"] == "running"
    assert out["step_index"] == 5
    assert out["step_total"] == 6
    assert out["step_label"] == "Running deep analysis"
    assert out["items_done"] == 40 and out["items_total"] == 71
    assert out["healthy"] is True
    assert out["eta_seconds"] >= 0


def test_build_ui_fields_stalled_hides_eta():
    j = {"status": "running", "stage": "deep_analysis", "error": None, "doc_count": 33}
    out = prog._build_ui_fields(j, {}, heartbeat_age=200.0, elapsed_in_step=0)
    assert out["ui_state"] == "stalled"
    assert out["healthy"] is False
    assert out["eta_seconds"] is None


def test_build_ui_fields_cancelled_reason():
    j = {"status": "cancelled", "stage": "summarization", "error": "Superseded by re-run", "doc_count": 10}
    out = prog._build_ui_fields(j, {}, heartbeat_age=None, elapsed_in_step=0)
    assert out["ui_state"] == "cancelled"
    assert out["cancel_reason"] == "Replaced by a newer run."


def test_build_ui_fields_missing_item_counts_omitted():
    j = {"status": "running", "stage": "deep_analysis", "error": None, "doc_count": 33}
    out = prog._build_ui_fields(j, {}, heartbeat_age=5.0, elapsed_in_step=0)
    assert out["items_done"] is None and out["items_total"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_progress_ui_fields.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute '_build_ui_fields'`

- [ ] **Step 3: Write minimal implementation**

Add a helper near the top of `progress.py` (after imports), and call it in `get_job_status`.

Add import at top of `progress.py`:

```python
from legal_portal.core import run_state
```

Add the helper function (module-level, above the route):

```python
def _build_ui_fields(j: dict, progress: dict, heartbeat_age, elapsed_in_step: float) -> dict:
    """Compute the Trustworthy-Wait UI fields. Pure w.r.t. its inputs; never raises."""
    stage = j.get("stage")
    doc_count = j.get("doc_count") or 0
    ui_state = run_state.compute_ui_state(
        job=j, has_result=False, heartbeat_age_seconds=heartbeat_age,
    )
    healthy = not (heartbeat_age is not None and heartbeat_age >= 180)
    step_index = run_state.stage_to_step(stage)

    stats = (progress or {}).get("stats") or {}
    items_done = stats.get("items_done")
    items_total = stats.get("items_total")

    eta_seconds = None
    if ui_state == "running":
        eta_seconds = run_state.estimate_eta(
            current_step=step_index, doc_count=doc_count,
            elapsed_in_step_seconds=elapsed_in_step or 0,
        )

    cancel_reason = run_state.cancel_reason(j.get("error")) if ui_state == "cancelled" else None

    return {
        "ui_state": ui_state,
        "step_index": step_index,
        "step_total": run_state.STEP_TOTAL,
        "step_label": run_state.step_label(stage),
        "items_done": items_done,
        "items_total": items_total,
        "eta_seconds": eta_seconds,
        "healthy": healthy,
        "cancel_reason": cancel_reason,
    }
```

Then, in `get_job_status`, compute `elapsed_in_step` and merge the fields. Immediately before the final `return {`:

```python
    # elapsed within the current step: prefer progress.timestamp; fall back to started_at
    elapsed_in_step = 0.0
    ts = (progress or {}).get("timestamp") or j.get("started_at")
    if ts:
        try:
            from dateutil.parser import parse as parse_dt
            from datetime import timezone
            t = parse_dt(ts)
            now2 = datetime.utcnow().replace(tzinfo=timezone.utc) if t.tzinfo else datetime.utcnow()
            elapsed_in_step = max(0.0, (now2 - t).total_seconds())
        except Exception:
            elapsed_in_step = 0.0

    ui_fields = _build_ui_fields(j, progress, heartbeat_age, elapsed_in_step)
```

And change the final `return {` dict to include the fields — add this line inside it (e.g. after `"heartbeat_age_seconds": heartbeat_age,`):

```python
        **ui_fields,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_progress_ui_fields.py -q && pytest tests/unit/test_run_state.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/api/routes/progress.py tests/unit/test_progress_ui_fields.py
git commit -m "feat(api): emit ui_state/step/eta/healthy on job status endpoint"
```

---

### Task 4: `GET /status/{case_id}` emits `ui_state`

**Files:**
- Modify: `src/legal_portal/api/routes/analysis_core.py` — `get_analysis_status` (`:557`), which returns an `analysis_results` row
- Test: `tests/unit/test_analysis_status_ui_state.py` (create)

**Interfaces:**
- Consumes: `run_state.compute_ui_state` (Task 1)
- Produces: the `/status/{case_id}` response object gains a `ui_state` key derived from the case's latest **job** (fallback: the result row's status)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_analysis_status_ui_state.py
from legal_portal.api.routes import analysis_core as ac


def test_ui_state_from_latest_job_running():
    job = {"status": "running", "stage": "deep_analysis"}
    assert ac._ui_state_for_case(latest_job=job, result_status="processing", heartbeat_age=10) == "running"


def test_ui_state_prefers_active_job_over_completed_result():
    job = {"status": "running", "stage": "preparing"}
    assert ac._ui_state_for_case(latest_job=job, result_status="completed", heartbeat_age=3) == "running"


def test_ui_state_completed_when_no_active_job_but_result_present():
    assert ac._ui_state_for_case(latest_job={"status": "completed", "stage": "completed"},
                                 result_status="completed", heartbeat_age=None) == "completed"


def test_ui_state_idle_when_nothing():
    assert ac._ui_state_for_case(latest_job=None, result_status=None, heartbeat_age=None) == "idle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_analysis_status_ui_state.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute '_ui_state_for_case'`

- [ ] **Step 3: Write minimal implementation**

Add import to `analysis_core.py`:

```python
from legal_portal.core import run_state
```

Add the pure helper (module level):

```python
def _ui_state_for_case(*, latest_job: dict | None, result_status: str | None, heartbeat_age) -> str:
    has_result = result_status == "completed"
    return run_state.compute_ui_state(
        job=latest_job, has_result=has_result, heartbeat_age_seconds=heartbeat_age,
    )
```

In `get_analysis_status`, after the row to return is chosen (each `return ...data[0]` branch), attach `ui_state`. Simplest: build the response once at the end. Replace the three `return <resp>.data[0]` sites so they funnel through a helper that fetches the latest job and stamps `ui_state`. Concretely, before the first active-check, load the latest job:

```python
    latest_job_resp = (
        supabase.table("analysis_jobs")
        .select("status, stage, heartbeat_at")
        .eq("case_id", case_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    latest_job = latest_job_resp.data[0] if latest_job_resp.data else None
    hb_age = None
    if latest_job and latest_job.get("heartbeat_at"):
        try:
            from dateutil.parser import parse as parse_dt
            from datetime import timezone
            t = parse_dt(latest_job["heartbeat_at"])
            now2 = datetime.utcnow().replace(tzinfo=timezone.utc) if t.tzinfo else datetime.utcnow()
            hb_age = (now2 - t).total_seconds()
        except Exception:
            hb_age = None

    def _with_ui_state(row: dict) -> dict:
        row = dict(row)
        row["ui_state"] = _ui_state_for_case(
            latest_job=latest_job, result_status=row.get("status"), heartbeat_age=hb_age,
        )
        return row
```

Then change each `return active_response.data[0]` / `completed_response.data[0]` / `response.data[0]` to `return _with_ui_state(<that>.data[0])`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_analysis_status_ui_state.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/api/routes/analysis_core.py tests/unit/test_analysis_status_ui_state.py
git commit -m "feat(api): add ui_state to /analysis/status derived from latest job"
```

---

### Task 5: Pipeline emits `items_done`/`items_total` where a count exists

**Files:**
- Modify: `src/legal_portal/services/analysis/multi_stage_analyzer.py` (fact_extraction / summarization progress calls) and/or `src/legal_portal/services/analysis/main_processor.py` (summarization heartbeat at `:47-92`)
- Test: `tests/unit/test_progress_stats_passthrough.py` (create)

**Interfaces:**
- Consumes: `DBProgressManager.publish_progress(..., stats=...)` — already writes `stats` into progress JSON (`db_progress_manager.py:87-88`)
- Produces: for per-document stages, `progress.stats = {"items_done": int, "items_total": int}`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_progress_stats_passthrough.py
import asyncio
from worker.db_progress_manager import DBProgressManager


class _FakeTable:
    def __init__(self, sink): self.sink = sink
    def update(self, payload): self.sink["payload"] = payload; return self
    def eq(self, *a, **k): return self
    def execute(self): return type("R", (), {"data": [{}]})()


class _FakeSB:
    def __init__(self, sink): self.sink = sink
    def table(self, _): return _FakeTable(self.sink)


def test_publish_progress_forwards_item_stats():
    sink = {}
    pm = DBProgressManager(_FakeSB(sink), "job-1", min_write_interval=0)
    # _check_cancelled reads status; fake returns {} → not cancelled
    asyncio.run(pm.publish_progress(
        "chan", message="Batch 1 complete (12/12 docs summarized)",
        phase="document_analysis", percent=40,
        stats={"items_done": 12, "items_total": 71},
    ))
    assert sink["payload"]["progress"]["stats"] == {"items_done": 12, "items_total": 71}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_progress_stats_passthrough.py -q`
Expected: This should FAIL only if `_check_cancelled` in the fake raises or stats aren't forwarded. If `publish_progress` already forwards `stats` (it does per `db_progress_manager.py:87-88`), the passthrough test PASSES immediately — in that case the failing part is the *producer* not sending stats. Proceed to Step 3 to wire the producer; keep this test as a regression guard for the manager contract.

- [ ] **Step 3: Wire the producer**

In `src/legal_portal/services/analysis/multi_stage_analyzer.py`, locate the per-document stages that already know their counts (summarization emits `"Batch N complete (X/Y docs summarized)"`; fact_extraction batches). At each such `progress_callback(...)` / `publish_progress(...)` call, pass `stats={"items_done": done, "items_total": total}` using the loop's existing counters. Example shape (adapt to the actual local variable names in that function):

```python
await progress_callback(
    f"Batch {batch_idx} complete ({done}/{total} docs summarized)",
    [], stage_id, percent,
    stats={"items_done": done, "items_total": total},
)
```

For stages with no natural item count (e.g. the single `deep_analysis` LLM call), pass **no** `stats` — the endpoint omits `items_*` (Task 3 handles the None case).

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_progress_stats_passthrough.py tests/unit/test_db_progress_manager.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/legal_portal/services/analysis/multi_stage_analyzer.py tests/unit/test_progress_stats_passthrough.py
git commit -m "feat(analysis): emit items_done/items_total on per-document stages"
```

---

### Task 6: Frontend — canonical stages + carry new fields

**Files:**
- Modify: `frontend/src/lib/stores/progressStore.ts` (`DEFAULT_STAGES` at `:89-96`; the polling status handler that maps job payload → state)
- Modify: `frontend/src/lib/utils/pollingClient.ts` (pass new fields through; **do not** touch stall logic at `:247-268`)
- Test: `frontend/src/lib/stores/progressStore.uiState.test.ts` (create)

**Interfaces:**
- Consumes: job-status payload fields from Task 3 (`ui_state, step_index, step_total, step_label, items_done, items_total, eta_seconds, healthy, cancel_reason`)
- Produces: `EnhancedProgressState` gains `uiState, stepIndex, stepTotal, stepLabel, itemsDone, itemsTotal, etaSeconds, healthy, cancelReason` (camelCase)

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/lib/stores/progressStore.uiState.test.ts
import { describe, it, expect } from 'vitest';
import { mapJobStatusToUi } from './progressStore';

describe('mapJobStatusToUi', () => {
  it('carries the trustworthy-wait fields from the job payload', () => {
    const out = mapJobStatusToUi({
      ui_state: 'running', step_index: 5, step_total: 6, step_label: 'Running deep analysis',
      items_done: 40, items_total: 71, eta_seconds: 380, healthy: true, cancel_reason: null,
    });
    expect(out.uiState).toBe('running');
    expect(out.stepIndex).toBe(5);
    expect(out.stepLabel).toBe('Running deep analysis');
    expect(out.itemsDone).toBe(40);
    expect(out.etaSeconds).toBe(380);
    expect(out.healthy).toBe(true);
  });

  it('tolerates a legacy payload without the new fields', () => {
    const out = mapJobStatusToUi({ status: 'running', stage: 'deep_analysis', percent: 86 });
    expect(out.uiState).toBeUndefined();
    expect(out.stepTotal).toBe(6); // sensible default
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/stores/progressStore.uiState.test.ts`
Expected: FAIL — `mapJobStatusToUi` is not exported.

- [ ] **Step 3: Implement**

In `progressStore.ts`, replace `DEFAULT_STAGES` (`:89-96`) with the canonical 6 (ids matching the backend step order):

```ts
const DEFAULT_STAGES: StageState[] = [
	{ id: 'preparing', name: 'Preparing documents', status: 'pending', progress: 0 },
	{ id: 'analyzing', name: 'Analyzing documents', status: 'pending', progress: 0 },
	{ id: 'fact_extraction', name: 'Extracting key facts', status: 'pending', progress: 0 },
	{ id: 'issue_mapping', name: 'Mapping legal issues', status: 'pending', progress: 0 },
	{ id: 'deep_analysis', name: 'Running deep analysis', status: 'pending', progress: 0 },
	{ id: 'finalizing', name: 'Finalizing results', status: 'pending', progress: 0 },
];
```

Add the exported pure mapper:

```ts
export interface UiRunFields {
	uiState?: string;
	stepIndex?: number;
	stepTotal: number;
	stepLabel?: string;
	itemsDone?: number | null;
	itemsTotal?: number | null;
	etaSeconds?: number | null;
	healthy?: boolean;
	cancelReason?: string | null;
}

export function mapJobStatusToUi(p: Record<string, any>): UiRunFields {
	return {
		uiState: p.ui_state,
		stepIndex: p.step_index,
		stepTotal: p.step_total ?? 6,
		stepLabel: p.step_label,
		itemsDone: p.items_done ?? null,
		itemsTotal: p.items_total ?? null,
		etaSeconds: p.eta_seconds ?? null,
		healthy: p.healthy,
		cancelReason: p.cancel_reason ?? null,
	};
}
```

Extend the `EnhancedProgressState` interface with the same optional fields, and in the durable-poll status handler merge `mapJobStatusToUi(data)` into the emitted state. In `pollingClient.ts`, ensure the raw `data` (including the new fields) is forwarded to that handler — no stall-logic change.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/stores/progressStore.uiState.test.ts src/lib/utils/pollingClient.test.ts`
Expected: PASS (new test + the existing 19 pollingClient tests still green)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/stores/progressStore.ts frontend/src/lib/utils/pollingClient.ts frontend/src/lib/stores/progressStore.uiState.test.ts
git commit -m "feat(fe): canonical 6 stages + carry trustworthy-wait fields"
```

---

### Task 7: Frontend — render step / items / ETA / liveness

**Files:**
- Modify: `frontend/src/lib/components/InlineAnalysisProgress.svelte`
- Create: `frontend/src/lib/utils/waitDisplay.ts` (pure formatters)
- Test: `frontend/src/lib/utils/waitDisplay.test.ts`

**Interfaces:**
- Consumes: `EnhancedProgressState` UI fields (Task 6)
- Produces: `formatEta(sec: number | null): string`, `livenessLine(healthy: boolean | undefined, heartbeatAgeSec: number | null): string`, `substanceLine(itemsDone, itemsTotal, stepIndex): string`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/lib/utils/waitDisplay.test.ts
import { describe, it, expect } from 'vitest';
import { formatEta, livenessLine, substanceLine } from './waitDisplay';

describe('waitDisplay', () => {
  it('rounds eta coarsely and says almost done at 0', () => {
    expect(formatEta(380)).toBe('~6 min remaining');
    expect(formatEta(35)).toBe('~1 min remaining');
    expect(formatEta(0)).toBe('almost done');
    expect(formatEta(null)).toBe('');
  });

  it('liveness from heartbeat, not percent', () => {
    expect(livenessLine(true, 4)).toContain('Working normally');
    expect(livenessLine(false, 200)).toContain('unresponsive');
  });

  it('substance line uses item counts when present, degrades otherwise', () => {
    expect(substanceLine(42, 71, 3)).toBe('42 of 71 documents');
    expect(substanceLine(null, null, 5)).toBe('This step takes several minutes on large cases');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/utils/waitDisplay.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement formatters + wire into component**

Create `frontend/src/lib/utils/waitDisplay.ts`:

```ts
export function formatEta(sec: number | null): string {
	if (sec === null || sec === undefined) return '';
	if (sec <= 0) return 'almost done';
	const mins = Math.max(1, Math.round(sec / 60));
	return `~${mins} min remaining`;
}

export function livenessLine(healthy: boolean | undefined, heartbeatAgeSec: number | null): string {
	if (healthy === false) return 'Worker unresponsive — this may have stalled';
	const age = heartbeatAgeSec == null ? 0 : Math.round(heartbeatAgeSec);
	return `Working normally · updated ${age}s ago`;
}

export function substanceLine(
	itemsDone: number | null | undefined,
	itemsTotal: number | null | undefined,
	_stepIndex: number | undefined,
): string {
	if (typeof itemsDone === 'number' && typeof itemsTotal === 'number' && itemsTotal > 0) {
		return `${itemsDone} of ${itemsTotal} documents`;
	}
	return 'This step takes several minutes on large cases';
}
```

In `InlineAnalysisProgress.svelte`, when the trustworthy-wait flag is on and the run is active, render three lines using `state`:

```svelte
{#if trustworthyWait && (state.uiState === 'running' || state.uiState === 'queued')}
	<p class="tw-step">Step {state.stepIndex} of {state.stepTotal} · {state.stepLabel}</p>
	<p class="tw-substance">
		{substanceLine(state.itemsDone, state.itemsTotal, state.stepIndex)}
		{#if formatEta(state.etaSeconds)} · {formatEta(state.etaSeconds)}{/if}
	</p>
	<p class="tw-liveness">{livenessLine(state.healthy, heartbeatAgeSeconds)}</p>
{/if}
```

Read the flag: `const trustworthyWait = import.meta.env.PUBLIC_ENABLE_TRUSTWORTHY_WAIT === 'true';` (or the project's existing env accessor — grep `PUBLIC_` usage in the file's neighbors and match it).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/utils/waitDisplay.test.ts && npx svelte-check --no-tsconfig --fail-on-warnings 2>/dev/null || npx svelte-check`
Expected: waitDisplay tests PASS; svelte-check clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/utils/waitDisplay.ts frontend/src/lib/utils/waitDisplay.test.ts frontend/src/lib/components/InlineAnalysisProgress.svelte
git commit -m "feat(fe): honest step/items/eta/liveness line during active runs"
```

---

### Task 8: Frontend — render by `ui_state`, remove Start during active run

**Files:**
- Modify: `frontend/src/routes/app/cases/[id]/+page.svelte` (`rerunIsActiveRun` at `:73-75`; re-run dialog `:76-80`; `runAnalysis` `:1051`; button rendering)
- Test: `frontend/src/routes/app/cases/[id]/caseControls.test.ts` (create — pure control-set function extracted from the page)

**Interfaces:**
- Consumes: `ui_state` from `/analysis/status` (Task 4) and the polled job status (Task 3)
- Produces: `controlsFor(uiState: string): { start: boolean; cancel: boolean; startOver: boolean; rerun: boolean; viewResults: boolean }`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/routes/app/cases/[id]/caseControls.test.ts
import { describe, it, expect } from 'vitest';
import { controlsFor } from './caseControls';

describe('controlsFor — G1: no Start while active', () => {
  it('running shows only cancel — NO start', () => {
    const c = controlsFor('running');
    expect(c.start).toBe(false);
    expect(c.startOver).toBe(false);
    expect(c.cancel).toBe(true);
  });
  it('queued shows only cancel — NO start', () => {
    const c = controlsFor('queued');
    expect(c.start).toBe(false);
    expect(c.cancel).toBe(true);
  });
  it('stalled offers start over (not resume — phase 2)', () => {
    const c = controlsFor('stalled');
    expect(c.startOver).toBe(true);
    expect(c.start).toBe(false);
  });
  it('idle / cancelled offer start', () => {
    expect(controlsFor('idle').start).toBe(true);
    expect(controlsFor('cancelled').start).toBe(true);
  });
  it('completed offers view + rerun', () => {
    const c = controlsFor('completed');
    expect(c.viewResults).toBe(true);
    expect(c.rerun).toBe(true);
    expect(c.start).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/routes/app/cases/[id]/caseControls.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `frontend/src/routes/app/cases/[id]/caseControls.ts`:

```ts
export interface Controls {
	start: boolean; cancel: boolean; startOver: boolean; rerun: boolean; viewResults: boolean;
}

export function controlsFor(uiState: string): Controls {
	switch (uiState) {
		case 'queued':
		case 'running':
			return { start: false, cancel: true, startOver: false, rerun: false, viewResults: false };
		case 'stalled':
			return { start: false, cancel: false, startOver: true, rerun: false, viewResults: false };
		case 'completed':
			return { start: false, cancel: false, startOver: false, rerun: true, viewResults: true };
		case 'failed':
			return { start: false, cancel: false, startOver: true, rerun: false, viewResults: false };
		case 'idle':
		case 'cancelled':
		default:
			return { start: true, cancel: false, startOver: false, rerun: false, viewResults: false };
	}
}
```

In `+page.svelte`, when `trustworthyWait` is on: derive `const controls = $derived(controlsFor(analysisStatus?.ui_state ?? 'idle'))` and render buttons from `controls`. Gate the Start/Re-run button on `controls.start || controls.rerun`, Cancel on `controls.cancel`, Start-over on `controls.startOver`. Delete the active-run branch of the re-run confirm (`:76-80` / the `rerunIsActiveRun` path in `runAnalysis` `:1051`) — with `controls.start` false during active runs, that path is unreachable; keep the confirm only for the `completed → rerun` case. When `ui_state === 'cancelled'`, show `analysisStatus?.cancel_reason` as a one-line note.

Keep the legacy (flag-off) rendering intact alongside, so flag-off behavior is byte-for-byte unchanged.

- [ ] **Step 4: Run test + typecheck**

Run: `cd frontend && npx vitest run src/routes/app/cases/[id]/caseControls.test.ts && npx svelte-check`
Expected: PASS; svelte-check clean.

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/routes/app/cases/[id]/caseControls.ts" "frontend/src/routes/app/cases/[id]/caseControls.test.ts" "frontend/src/routes/app/cases/[id]/+page.svelte"
git commit -m "feat(fe): render case controls by ui_state; no Start during active run (G1)"
```

---

### Task 9: Flag config + full-suite green + manual verification

**Files:**
- Modify: `frontend/.env.example` (document the flag), any env-typing file (`frontend/src/env.d.ts` if present)
- No new tests; this task gates the whole feature.

- [ ] **Step 1: Document the flag**

Add to `frontend/.env.example`:

```
# Trustworthy Wait Phase 1 UI (no Start during active run, honest progress).
# Backend status fields ship regardless; this only gates the frontend rendering.
PUBLIC_ENABLE_TRUSTWORTHY_WAIT=false
```

- [ ] **Step 2: Run the full backend suite**

Run: `pytest tests/unit/test_run_state.py tests/unit/test_progress_ui_fields.py tests/unit/test_analysis_status_ui_state.py tests/unit/test_progress_stats_passthrough.py tests/unit/test_db_progress_manager.py -q`
Expected: PASS

- [ ] **Step 3: Run the full frontend suite + typecheck**

Run: `cd frontend && npx vitest run && npx svelte-check`
Expected: all green, svelte-check 0 errors.

- [ ] **Step 4: Manual prod-preview check (flag ON) — history-bearing case**

Deploy preview with `PUBLIC_ENABLE_TRUSTWORTHY_WAIT=true`. Open a case that has prior failed/cancelled runs (NOT a fresh case — a fresh case hid the reconcile bug). Confirm:
- While running: **no Start button**, only Cancel; step line advances 1→6; a frozen `deep_analysis` shows "Working normally", not stuck.
- Cancel → reason line renders; Start reappears.
- Kill the worker (or simulate ≥180s heartbeat) → `stalled` with Start over.

- [ ] **Step 5: Commit**

```bash
git add frontend/.env.example
git commit -m "chore: document PUBLIC_ENABLE_TRUSTWORTHY_WAIT flag"
```

---

## Self-Review

**Spec coverage:**
- §3.1 canonical state → Tasks 1, 4, 8. G1 (no Start active) → Task 8 test. ✓
- §3.2 6-step mapping → Task 1 (`test_every_check_allowed_stage_maps_or_is_terminal` guards P3). ✓
- §3.3 honest payload (`ui_state, step_*, items_*, eta_seconds, healthy`) → Task 3; render → Task 7. ✓
- §3.1 cancelled reason → Tasks 1 (`cancel_reason`), 3, 8. ✓
- §3.4 per-step ETA → Task 2; format/guards → Task 7 (`formatEta`). ✓
- §3.3 items source via `stats` → Task 5. ✓
- §3.5 unchanged (stall detector, schema, /start) → respected; Task 6 explicitly leaves stall logic alone. ✓
- §5 error handling (never throw, keep-last-state) → Task 1 `compute_ui_state` try/except; endpoint guards. ✓
- §7 flag rollout → Tasks 7/8 gating, Task 9 config. ✓

**Placeholder scan:** none — every code step has concrete code. Task 5 Step 3 adapts to real local variable names (flagged explicitly, not a hidden TODO). ✓

**Type consistency:** `ui_state` string enum identical across Python (`compute_ui_state`) and TS (`controlsFor`, `mapJobStatusToUi`). Field names snake_case on the wire, camelCase in `EnhancedProgressState`/`UiRunFields`. `STEP_TOTAL`=6 consistent. `estimate_eta`/`step_estimate` signatures match between Tasks 2 and 3. ✓
