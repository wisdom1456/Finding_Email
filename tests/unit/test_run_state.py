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
    # terminal job status must win over a stale has_result — never mask a failure/cancel as completed
    ({"status": "failed", "stage": "deep_analysis"}, True, None, "failed"),
    ({"status": "cancelled", "stage": "summarization"}, True, None, "cancelled"),
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
