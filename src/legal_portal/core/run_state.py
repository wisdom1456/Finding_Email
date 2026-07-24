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
        if status == "completed":
            return "completed"
        if status == "failed":
            return "failed"
        if status == "cancelled":
            return "cancelled"
        if has_result:
            return "completed"
        return "idle"
    except Exception:
        return "completed" if has_result else "idle"


def cancel_reason(error: Optional[str]) -> str:
    """One-line reason for a cancelled run."""
    if error == "Superseded by re-run":
        return "Replaced by a newer run."
    if not error:
        return "Cancelled."
    return error


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
