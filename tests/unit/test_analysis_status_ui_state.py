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


def test_cancel_reason_maps_supersede_to_friendly_copy():
    job = {"status": "cancelled", "error": "Superseded by re-run"}
    assert ac._cancel_reason_for_case(latest_job=job, ui_state="cancelled") == "Replaced by a newer run."


def test_cancel_reason_none_error_falls_back_to_cancelled():
    job = {"status": "cancelled", "error": None}
    assert ac._cancel_reason_for_case(latest_job=job, ui_state="cancelled") == "Cancelled."


def test_cancel_reason_none_when_not_cancelled():
    job = {"status": "running", "error": None}
    assert ac._cancel_reason_for_case(latest_job=job, ui_state="running") is None


def test_cancel_reason_handles_missing_job():
    assert ac._cancel_reason_for_case(latest_job=None, ui_state="cancelled") == "Cancelled."
