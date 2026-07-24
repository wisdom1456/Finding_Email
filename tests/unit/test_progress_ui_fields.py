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
