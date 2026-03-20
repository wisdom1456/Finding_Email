#!/usr/bin/env python3
"""Durable analysis path verification.

Tests the complete durable worker flow:
  POST /analysis/start (durable) → job created → worker claims → pipeline runs →
  results finalized → letters generated → persistence verified

Separates failures into:
  - durable job orchestration failure
  - worker execution failure
  - provider transient failure (OpenAI timeouts)
  - data-quality / completeness failure
  - downstream letter-generation failure

Usage:
    # Scenario A: Ron Bryant durable full journey
    python3 scripts/testing/verify_durable_path.py --case "Ron Bryant"

    # Scenario B: Erik Devlin durable full journey
    python3 scripts/testing/verify_durable_path.py --case "Erik Devlin"

    # Scenario C: Cancel test
    python3 scripts/testing/verify_durable_path.py --cancel-test

    # All scenarios
    python3 scripts/testing/verify_durable_path.py --all

Environment:
    Requires ENABLE_DURABLE_WORKER=true on the API (Vercel or local).
    Requires the Railway worker to be running (or local worker).
"""
import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime
from urllib.parse import urlparse, parse_qs, quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from dotenv import load_dotenv
load_dotenv()

API_BASE = os.getenv("API_BASE", "https://finding-emails.vercel.app/api")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
USER_EMAIL = "modible@gmail.com"

CASES = {
    "Ron Bryant": {"matter_id": 1768679168, "expected_docs": 17},
    "Erik Devlin": {"matter_id": 1707029543, "expected_docs": 58},
}

# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

class FailureClass:
    ORCHESTRATION = "durable_job_orchestration_failure"
    WORKER = "worker_execution_failure"
    PROVIDER = "provider_transient_failure"
    DATA_QUALITY = "data_quality_completeness_failure"
    LETTER_GEN = "downstream_letter_generation_failure"


def classify_failure(error_msg: str, context: str = "") -> str:
    """Classify a failure into exactly one category."""
    e = (error_msg or "").lower()
    if any(p in e for p in ["timeout", "rate_limit", "429", "503", "502", "520", "cloudflare"]):
        return FailureClass.PROVIDER
    if any(p in e for p in ["job not found", "claim", "heartbeat", "stale"]):
        return FailureClass.ORCHESTRATION
    if any(p in e for p in ["msr missing", "multi_stage_result", "document_summaries"]):
        return FailureClass.DATA_QUALITY
    if "letter" in context.lower():
        return FailureClass.LETTER_GEN
    if any(p in e for p in ["pipeline", "process_case", "analysis"]):
        return FailureClass.WORKER
    return FailureClass.WORKER  # default


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_supabase():
    from supabase import create_client
    return create_client(SUPABASE_URL, SERVICE_KEY)


def get_user_token():
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
                 "Content-Type": "application/json"},
        json={"type": "magiclink", "email": USER_EMAIL},
    )
    data = resp.json()
    parsed = urlparse(data.get("action_link", ""))
    params = parse_qs(parsed.fragment or parsed.query)
    token_hash = params.get("token_hash", params.get("token", [None]))[0]
    verify = requests.post(
        f"{SUPABASE_URL}/auth/v1/verify",
        headers={"apikey": SERVICE_KEY, "Content-Type": "application/json"},
        json={"type": "magiclink", "token_hash": token_hash},
    )
    token = verify.json().get("access_token")
    if not token:
        print(f"Auth failed: {verify.text[:200]}")
        sys.exit(1)
    return token


def api(method, path, token, **kwargs):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{API_BASE}{path}"
    timeout = kwargs.pop("timeout", 60)
    return getattr(requests, method)(url, headers=headers, timeout=timeout, **kwargs)


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

class TimingCapture:
    def __init__(self):
        self.queue_wait_s = 0
        self.running_s = 0
        self.total_job_s = 0
        self.findings_letter_s = 0
        self.demand_letter_s = 0
        self.stage_metrics = {}

    def report(self):
        print(f"\n  Timing:")
        print(f"    Queue wait:       {self.queue_wait_s:.1f}s")
        print(f"    Running:          {self.running_s:.1f}s")
        print(f"    Total job:        {self.total_job_s:.1f}s")
        if self.findings_letter_s:
            print(f"    Findings letter:  {self.findings_letter_s:.1f}s")
        if self.demand_letter_s:
            print(f"    Demand letter:    {self.demand_letter_s:.1f}s")
        if self.stage_metrics:
            print(f"    Stage metrics:    {json.dumps(self.stage_metrics)}")


# ---------------------------------------------------------------------------
# SSE stream consumer (reused from run_full_journey.py)
# ---------------------------------------------------------------------------

def consume_sse_stream(response):
    full_content = ""
    final_html = None
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if data.get("event") == "final" and data.get("content", {}).get("html"):
            final_html = data["content"]["html"]
            continue
        token = data.get("token", "")
        if token:
            full_content += token
        if data.get("done") or data.get("event") == "done" or data.get("type") == "done":
            break
        if data.get("error"):
            return None, data.get("error")
    return final_html or full_content, None


# ---------------------------------------------------------------------------
# Scenario A/B: Durable full journey
# ---------------------------------------------------------------------------

def run_durable_journey(token, case_name: str):
    """Run full durable journey for a case."""
    print(f"\n{'='*60}")
    print(f"DURABLE JOURNEY: {case_name}")
    print(f"{'='*60}")

    s = get_supabase()
    timing = TimingCapture()
    results = {"case": case_name, "scenario": "durable_journey", "steps": {}}

    # Find case
    cases = s.table("cases").select("id, status").ilike("client_name", f"%{case_name}%").order("created_at", desc=True).limit(1).execute()
    if not cases.data:
        print(f"  Case not found!")
        results["status"] = "CASE_NOT_FOUND"
        return results
    case_id = cases.data[0]["id"]
    print(f"  Case: {case_id[:12]}...")

    # Clean up stale analysis state
    stale_ar = s.table("analysis_results").select("id").eq("case_id", case_id).in_("status", ["pending", "processing"]).execute()
    for r in stale_ar.data:
        s.table("analysis_results").update({"status": "error", "error": "Cleaned for durable test"}).eq("id", r["id"]).execute()
    stale_jobs = s.table("analysis_jobs").select("id").eq("case_id", case_id).in_("status", ["pending", "running"]).execute()
    for j in stale_jobs.data:
        s.table("analysis_jobs").update({"status": "failed", "error": "Cleaned for durable test"}).eq("id", j["id"]).execute()
    s.table("cases").update({"status": "pending"}).eq("id", case_id).execute()

    # --- Step 1: POST /analysis/start ---
    print(f"\n  Step 1: POST /analysis/start (durable)")
    t0 = time.time()
    r = api("post", "/analysis/start", token, json={"case_id": case_id, "provider": "openai"})

    step1 = {"http_status": r.status_code}
    if not r.ok:
        step1["error"] = r.text[:300]
        step1["failure_class"] = FailureClass.ORCHESTRATION
        results["steps"]["start"] = step1
        results["status"] = "START_FAILED"
        print(f"    FAILED: {r.status_code} {r.text[:200]}")
        return results

    data = r.json()
    analysis_id = data.get("id")
    job_id = data.get("job_id")
    mode = data.get("mode")
    step1["analysis_id"] = analysis_id
    step1["job_id"] = job_id
    step1["mode"] = mode
    step1["elapsed_s"] = round(time.time() - t0, 2)
    results["steps"]["start"] = step1

    if mode != "durable" or not job_id:
        print(f"    NOT DURABLE: mode={mode}, job_id={job_id}")
        print(f"    Is ENABLE_DURABLE_WORKER set on the API?")
        results["status"] = "NOT_DURABLE"
        return results

    print(f"    analysis_id: {analysis_id[:12]}...")
    print(f"    job_id: {job_id[:12]}...")
    print(f"    mode: {mode}")

    # --- Step 2: Verify DB state ---
    print(f"\n  Step 2: Verify initial DB state")
    ar_check = s.table("analysis_results").select("status").eq("id", analysis_id).execute()
    job_check = s.table("analysis_jobs").select("status, case_id, analysis_id, doc_count").eq("id", job_id).execute()
    case_check = s.table("cases").select("status").eq("id", case_id).execute()

    step2 = {
        "ar_status": ar_check.data[0]["status"] if ar_check.data else None,
        "job_status": job_check.data[0]["status"] if job_check.data else None,
        "job_doc_count": job_check.data[0].get("doc_count") if job_check.data else None,
        "case_status": case_check.data[0]["status"] if case_check.data else None,
    }
    results["steps"]["initial_state"] = step2

    ar_ok = step2["ar_status"] == "pending"
    job_ok = step2["job_status"] == "pending"
    case_ok = step2["case_status"] == "processing"
    doc_ok = step2["job_doc_count"] and step2["job_doc_count"] > 0

    print(f"    analysis_results.status = {step2['ar_status']} {'OK' if ar_ok else 'FAIL'}")
    print(f"    analysis_jobs.status = {step2['job_status']} {'OK' if job_ok else 'FAIL'}")
    print(f"    analysis_jobs.doc_count = {step2['job_doc_count']} {'OK' if doc_ok else 'FAIL'}")
    print(f"    cases.status = {step2['case_status']} {'OK' if case_ok else 'FAIL'}")

    if not (ar_ok and job_ok and case_ok):
        results["status"] = "INITIAL_STATE_INVALID"
        step2["failure_class"] = FailureClass.ORCHESTRATION
        return results

    # --- Step 3: Poll job status ---
    print(f"\n  Step 3: Poll GET /progress/jobs/{job_id[:8]}.../status")
    poll_start = time.time()
    last_stage = ""
    last_status = ""
    phase_log = []
    queue_end = None
    timeout_sec = 3600  # 1 hour max for large cases

    while time.time() - poll_start < timeout_sec:
        try:
            r = api("get", f"/progress/jobs/{job_id}/status", token, timeout=15)
            if r.ok:
                d = r.json()
                status = d.get("status", "")
                stage = d.get("stage", "")
                percent = d.get("percent", 0)
                message = d.get("message", "")
                hb_age = d.get("heartbeat_age_seconds")

                # Track queue→running transition
                if status == "running" and queue_end is None:
                    queue_end = time.time()
                    timing.queue_wait_s = queue_end - poll_start

                if stage != last_stage or status != last_status:
                    elapsed = time.time() - poll_start
                    entry = {"status": status, "stage": stage, "percent": percent,
                             "elapsed_s": round(elapsed, 1), "heartbeat_age": hb_age}
                    phase_log.append(entry)
                    print(f"    [{elapsed:6.0f}s] {status:10s} {stage:20s} {percent:3d}% hb={hb_age}")
                    last_stage = stage
                    last_status = status

                if status in ("completed", "failed", "cancelled"):
                    timing.running_s = round(time.time() - (queue_end or poll_start), 1)
                    timing.total_job_s = round(time.time() - poll_start, 1)
                    break
        except Exception as e:
            print(f"    Poll error: {e}")

        time.sleep(3)
    else:
        timing.total_job_s = round(time.time() - poll_start, 1)
        results["status"] = "POLL_TIMEOUT"
        results["steps"]["poll"] = {"phase_log": phase_log, "failure_class": FailureClass.WORKER}
        return results

    step3 = {"final_status": status, "phase_log": phase_log}
    results["steps"]["poll"] = step3

    if status != "completed":
        # Classify the failure
        error = d.get("error", "")
        step3["error"] = error
        step3["failure_class"] = classify_failure(error)
        results["status"] = f"JOB_{status.upper()}"
        print(f"    Job {status}: {error[:200]}")
        print(f"    Classification: {step3['failure_class']}")
        timing.report()
        return results

    print(f"    Job completed in {timing.total_job_s:.0f}s (queue={timing.queue_wait_s:.0f}s, run={timing.running_s:.0f}s)")

    # --- Step 4: Verify finalization ---
    print(f"\n  Step 4: Verify finalization")
    ar_final = s.table("analysis_results").select("status, result").eq("id", analysis_id).execute()
    case_final = s.table("cases").select("status").eq("id", case_id).execute()

    ar_status = ar_final.data[0]["status"] if ar_final.data else None
    result = ar_final.data[0].get("result") or {} if ar_final.data else {}
    msr = result.get("multi_stage_result") or {}
    case_status = case_final.data[0]["status"] if case_final.data else None

    fm = msr.get("fact_matrix") or {}
    im = msr.get("issue_map") or {}

    step4 = {
        "ar_status": ar_status,
        "case_status": case_status,
        "has_msr": bool(msr),
        "parties": len(fm.get("parties", [])),
        "timeline": len(fm.get("timeline", [])),
        "issues": len(im.get("primary_issues", [])),
    }
    results["steps"]["finalization"] = step4

    print(f"    analysis_results.status = {ar_status}")
    print(f"    cases.status = {case_status}")
    print(f"    MSR present: {bool(msr)}")
    print(f"    parties={step4['parties']} timeline={step4['timeline']} issues={step4['issues']}")

    if ar_status != "completed" or not msr:
        step4["failure_class"] = FailureClass.DATA_QUALITY
        results["status"] = "FINALIZATION_FAILED"
        timing.report()
        return results

    # --- Step 5: Findings letter ---
    print(f"\n  Step 5: Generate findings letter (production route)")
    t0 = time.time()
    try:
        r = api("get", f"/analysis/{analysis_id}/letter/stream?force_generation=true",
                token, timeout=300, stream=True)
        if r.ok:
            content, error = consume_sse_stream(r)
            timing.findings_letter_s = round(time.time() - t0, 1)
            if error:
                step5 = {"error": error, "failure_class": FailureClass.LETTER_GEN}
            elif content and len(content) >= 5000:
                step5 = {"chars": len(content), "elapsed_s": timing.findings_letter_s}
                print(f"    Findings: {len(content):,d} chars in {timing.findings_letter_s:.0f}s")
            else:
                step5 = {"chars": len(content) if content else 0,
                         "failure_class": FailureClass.LETTER_GEN,
                         "error": f"Too short: {len(content) if content else 0} chars"}
        else:
            step5 = {"http_status": r.status_code, "failure_class": FailureClass.LETTER_GEN}
    except Exception as e:
        step5 = {"error": str(e), "failure_class": classify_failure(str(e), "letter")}
    results["steps"]["findings_letter"] = step5

    # --- Step 6: Demand letter ---
    print(f"\n  Step 6: Generate demand letter (production route)")
    # Extract opposing party
    opposing = result.get("opposing_parties") or []
    if not opposing:
        all_parties = fm.get("parties", [])
        opposing = [p for p in all_parties if p.get("is_opposing_party")]
    if not opposing:
        opposing = [p for p in fm.get("parties", []) if p.get("role", "").lower() not in ("client", "attorney", "firm")]

    target_party = None
    for p in opposing:
        if isinstance(p, dict):
            target_party = p.get("name") or p.get("party_name")
        if target_party:
            break

    if target_party:
        encoded = quote(target_party)
        t0 = time.time()
        try:
            r = api("get", f"/analysis/{analysis_id}/demand-letter/stream"
                    f"?target_party_name={encoded}&demand_deadline=10%20business%20days",
                    token, timeout=300, stream=True)
            if r.ok:
                content, error = consume_sse_stream(r)
                timing.demand_letter_s = round(time.time() - t0, 1)
                if error:
                    step6 = {"error": error, "failure_class": FailureClass.LETTER_GEN}
                elif content and len(content) >= 3000:
                    step6 = {"chars": len(content), "party": target_party,
                             "elapsed_s": timing.demand_letter_s}
                    print(f"    Demand: {len(content):,d} chars in {timing.demand_letter_s:.0f}s (party: {target_party})")
                else:
                    step6 = {"chars": len(content) if content else 0,
                             "failure_class": FailureClass.LETTER_GEN}
            else:
                step6 = {"http_status": r.status_code, "failure_class": FailureClass.LETTER_GEN}
        except Exception as e:
            step6 = {"error": str(e), "failure_class": classify_failure(str(e), "letter")}
    else:
        step6 = {"skipped": True, "reason": "No opposing party found"}
        print(f"    Skipped: no opposing party")
    results["steps"]["demand_letter"] = step6

    # --- Step 7: Persistence ---
    print(f"\n  Step 7: Verify persistence")
    r = api("get", f"/analysis/results/{case_id}", token)
    if r.ok:
        d = r.json()
        letters = d.get("generated_letters") or {}
        findings_len = len(letters.get("findings", ""))
        demand_key = next((k for k in letters if k.startswith("demand_")), None)
        demand_len = len(letters.get(demand_key, "")) if demand_key else 0
        step7 = {"findings_persisted": findings_len, "demand_persisted": demand_len}
        print(f"    findings: {findings_len:,d} chars, demand: {demand_len:,d} chars")
    else:
        step7 = {"error": f"HTTP {r.status_code}"}
    results["steps"]["persistence"] = step7

    # --- Summary ---
    timing.report()

    has_failures = any(
        s.get("failure_class") for s in results["steps"].values() if isinstance(s, dict)
    )
    results["status"] = "PASS" if not has_failures else "PARTIAL"
    return results


# ---------------------------------------------------------------------------
# Scenario C: Cancel test
# ---------------------------------------------------------------------------

def run_cancel_test(token):
    """Test cancel semantics for durable jobs."""
    print(f"\n{'='*60}")
    print(f"CANCEL TEST")
    print(f"{'='*60}")

    s = get_supabase()
    case_name = "Ron Bryant"
    results = {"scenario": "cancel_test", "steps": {}}

    # Find case
    cases = s.table("cases").select("id").ilike("client_name", f"%{case_name}%").order("created_at", desc=True).limit(1).execute()
    if not cases.data:
        results["status"] = "CASE_NOT_FOUND"
        return results
    case_id = cases.data[0]["id"]

    # Clean stale state
    for r in s.table("analysis_results").select("id").eq("case_id", case_id).in_("status", ["pending", "processing"]).execute().data:
        s.table("analysis_results").update({"status": "error", "error": "Cancel test cleanup"}).eq("id", r["id"]).execute()
    for j in s.table("analysis_jobs").select("id").eq("case_id", case_id).in_("status", ["pending", "running"]).execute().data:
        s.table("analysis_jobs").update({"status": "failed", "error": "Cancel test cleanup"}).eq("id", j["id"]).execute()
    s.table("cases").update({"status": "pending"}).eq("id", case_id).execute()

    # Step 1: Start analysis
    print(f"\n  Step 1: Start durable analysis")
    r = api("post", "/analysis/start", token, json={"case_id": case_id, "provider": "openai"})
    if not r.ok or r.json().get("mode") != "durable":
        results["status"] = "START_FAILED"
        results["steps"]["start"] = {"error": r.text[:200] if not r.ok else "Not durable mode"}
        return results

    data = r.json()
    analysis_id = data["id"]
    job_id = data["job_id"]
    print(f"    analysis_id: {analysis_id[:12]}... job_id: {job_id[:12]}...")

    # Step 2: Verify job exists in pending or running
    time.sleep(2)  # Brief wait for worker to potentially claim
    job = s.table("analysis_jobs").select("status").eq("id", job_id).execute()
    job_status = job.data[0]["status"] if job.data else None
    print(f"    Job status before cancel: {job_status}")
    results["steps"]["pre_cancel"] = {"job_status": job_status}

    if job_status not in ("pending", "running"):
        print(f"    WARNING: Expected pending or running, got {job_status}")

    # Step 3: Cancel
    print(f"\n  Step 2: Cancel via POST /analysis/cancel/{analysis_id[:8]}...")
    r = api("post", f"/analysis/cancel/{analysis_id}", token)
    cancel_ok = r.ok
    print(f"    Cancel response: {r.status_code}")
    results["steps"]["cancel_response"] = {"http_status": r.status_code}

    # Step 4: Verify state
    print(f"\n  Step 3: Verify cancel state")
    time.sleep(1)
    job_post = s.table("analysis_jobs").select("status").eq("id", job_id).execute()
    ar_post = s.table("analysis_results").select("status").eq("id", analysis_id).execute()
    case_post = s.table("cases").select("status").eq("id", case_id).execute()

    j_st = job_post.data[0]["status"] if job_post.data else None
    a_st = ar_post.data[0]["status"] if ar_post.data else None
    c_st = case_post.data[0]["status"] if case_post.data else None

    step4 = {"job_status": j_st, "ar_status": a_st, "case_status": c_st}
    results["steps"]["post_cancel"] = step4

    print(f"    analysis_jobs.status = {j_st} (expected: cancelled)")
    print(f"    analysis_results.status = {a_st} (expected: cancelled)")
    print(f"    cases.status = {c_st} (expected: pending — no other active jobs)")

    job_ok = j_st == "cancelled"
    ar_ok = a_st == "cancelled"
    # Case should be 'pending' if no other active jobs, or unchanged if worker already moved it
    case_ok = c_st in ("pending", "cancelled")

    if job_ok and ar_ok and case_ok:
        results["status"] = "PASS"
        print(f"\n  CANCEL TEST: PASS")
    else:
        results["status"] = "FAIL"
        step4["failure_class"] = FailureClass.ORCHESTRATION
        print(f"\n  CANCEL TEST: FAIL")

    # Cleanup
    s.table("analysis_jobs").delete().eq("id", job_id).execute()
    s.table("analysis_results").delete().eq("id", analysis_id).execute()
    s.table("cases").update({"status": "completed"}).eq("id", case_id).execute()

    return results


# ---------------------------------------------------------------------------
# Scenario D: Stale recovery test plan
# ---------------------------------------------------------------------------

def print_stale_recovery_plan():
    """Document how to test stale recovery (manual procedure)."""
    print(f"\n{'='*60}")
    print(f"STALE RECOVERY TEST PLAN (manual)")
    print(f"{'='*60}")
    print("""
  Prerequisites:
    - Railway worker running
    - ENABLE_DURABLE_WORKER=true on API

  Steps:
    1. Start a durable analysis:
       POST /api/analysis/start with a medium case (Ron Bryant)
       Note the job_id.

    2. Wait for job to reach 'running' status:
       Poll GET /api/progress/jobs/{job_id}/status until status='running'

    3. Kill the Railway worker process:
       railway down (or kill the container)

    4. Wait 120+ seconds (heartbeat timeout)

    5. Verify job becomes claimable:
       SELECT * FROM claim_analysis_job('manual-test');
       Expected: returns the stale job with attempts incremented

    6. Restart the Railway worker:
       railway up

    7. Verify the worker re-claims and completes:
       Poll GET /api/progress/jobs/{job_id}/status
       Expected: status transitions running → completed

    8. Verify results:
       GET /api/analysis/results/{case_id}
       Expected: multi_stage_result present

  Success criteria:
    - Job survives worker death
    - Job is re-claimed within heartbeat_timeout + poll_interval (~125s)
    - Analysis completes on retry
    - No duplicate processing (unique constraint prevents)

  Failure modes to watch:
    - If attempts >= max_attempts (3), job goes to 'failed' instead of re-claim
    - If analysis state is corrupt from partial run, retry may fail differently
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Durable analysis path verification")
    parser.add_argument("--case", type=str, help="Case name for journey test")
    parser.add_argument("--cancel-test", action="store_true", help="Run cancel scenario")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--stale-plan", action="store_true", help="Print stale recovery test plan")
    args = parser.parse_args()

    print("Getting auth token...")
    token = get_user_token()
    print(f"Token: {token[:20]}...")

    all_results = []

    if args.stale_plan:
        print_stale_recovery_plan()
        return

    if args.case:
        r = run_durable_journey(token, args.case)
        all_results.append(r)

    if args.cancel_test or args.all:
        r = run_cancel_test(token)
        all_results.append(r)

    if args.all:
        for name in ["Ron Bryant", "Erik Devlin"]:
            r = run_durable_journey(token, name)
            all_results.append(r)

    # Summary
    if all_results:
        print(f"\n{'='*60}")
        print(f"SUMMARY")
        print(f"{'='*60}")
        print(f"{'Scenario':<35s} {'Status':<15s} {'Classification':<35s}")
        print(f"{'-'*35} {'-'*15} {'-'*35}")
        for r in all_results:
            scenario = f"{r.get('scenario', '?')} ({r.get('case', '')})"[:34]
            status = r.get("status", "?")
            # Find first failure classification
            fc = ""
            for step in r.get("steps", {}).values():
                if isinstance(step, dict) and step.get("failure_class"):
                    fc = step["failure_class"]
                    break
            print(f"{scenario:<35s} {status:<15s} {fc:<35s}")


if __name__ == "__main__":
    main()
