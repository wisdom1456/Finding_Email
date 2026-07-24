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
