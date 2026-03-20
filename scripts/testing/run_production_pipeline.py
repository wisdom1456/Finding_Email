#!/usr/bin/env python3
"""Run full production pipeline via HTTP API: analysis + findings letter + demand letter.

Calls the same endpoints the browser app uses.

Usage:
    python3 scripts/testing/run_production_pipeline.py "Ron Bryant" --letters-only
    python3 scripts/testing/run_production_pipeline.py "all"  # Run all 5 cases
"""
import os
import sys
import json
import time
import argparse
import requests
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from dotenv import load_dotenv
load_dotenv()

API_BASE = "https://finding-emails.vercel.app/api"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Cases to test
ALL_CASES = [
    "Migdalia Escribano",
    "Balaji Badam",
    "Miguel Velasco",
    "Clifton Price",
    "Erik Devlin",
]


def get_user_token():
    """Get a valid user JWT via Supabase admin API."""
    # Find the user who owns the cases
    from supabase import create_client
    s = create_client(SUPABASE_URL, SERVICE_KEY)
    r = s.table("cases").select("user_id").limit(1).execute()
    user_id = r.data[0]["user_id"]
    u = s.auth.admin.get_user_by_id(user_id)
    email = u.user.email

    # Generate magic link and verify to get JWT
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}", "Content-Type": "application/json"},
        json={"type": "magiclink", "email": email},
    )
    data = resp.json()
    action_link = data.get("action_link", "")
    parsed = urlparse(action_link)
    params = parse_qs(parsed.fragment or parsed.query)
    token_hash = params.get("token_hash", params.get("token", [None]))[0]

    verify_resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/verify",
        headers={"apikey": SERVICE_KEY, "Content-Type": "application/json"},
        json={"type": "magiclink", "token_hash": token_hash},
    )
    return verify_resp.json().get("access_token")


def api(method, path, token, **kwargs):
    """Make an authenticated API call."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{API_BASE}{path}"
    timeout = kwargs.pop("timeout", 600)
    r = getattr(requests, method)(url, headers=headers, timeout=timeout, **kwargs)
    return r


def find_case(token, name):
    """Find case by client name."""
    from supabase import create_client
    s = create_client(SUPABASE_URL, SERVICE_KEY)
    r = s.table("cases").select("id, client_name, status").ilike("client_name", f"%{name}%").order("created_at", desc=True).limit(1).execute()
    if not r.data:
        return None
    return r.data[0]


def find_analysis(case_id):
    """Find latest completed analysis with multi-stage results."""
    from supabase import create_client
    s = create_client(SUPABASE_URL, SERVICE_KEY)
    r = s.table("analysis_results").select("id, status, result").eq("case_id", case_id).eq("status", "completed").order("created_at", desc=True).limit(1).execute()
    if not r.data:
        return None
    a = r.data[0]
    result = a.get("result") or {}
    has_msr = bool(result.get("multi_stage_result"))
    return {"id": a["id"], "has_msr": has_msr}


def start_analysis(token, case_id):
    """Start analysis via POST /api/analysis/start (same as browser)."""
    print(f"  Starting analysis via API...")
    start = time.time()
    r = api("post", "/analysis/start", token, json={"case_id": case_id, "provider": "openai"}, timeout=800)

    if r.status_code == 409:
        print(f"  Analysis already in progress (409)")
        return None

    if not r.ok:
        print(f"  Start failed: {r.status_code} {r.text[:200]}")
        return None

    # Response is SSE stream - read first event for analysis ID
    analysis_id = None
    for line in r.text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("type") == "started" and data.get("analysis", {}).get("id"):
                    analysis_id = data["analysis"]["id"]
                    break
                # Also handle direct JSON response (local mode)
                if data.get("id"):
                    analysis_id = data["id"]
                    break
            except json.JSONDecodeError:
                pass

    if not analysis_id:
        # Try parsing as plain JSON (local dev mode)
        try:
            data = r.json()
            analysis_id = data.get("id")
        except:
            pass

    if not analysis_id:
        print(f"  Could not extract analysis ID from response")
        return None

    print(f"  Analysis started: {analysis_id[:12]}...")
    return analysis_id


def poll_analysis(token, analysis_id, timeout_sec=800):
    """Poll analysis status until complete (same as browser polling mode)."""
    start = time.time()
    last_phase = ""
    while time.time() - start < timeout_sec:
        try:
            r = api("get", f"/progress/analysis/{analysis_id}/status", token, timeout=30)
            if r.ok:
                data = r.json()
                phase = data.get("phase", "")
                percent = data.get("percent", 0)
                status = data.get("type", data.get("status", ""))

                if phase != last_phase:
                    elapsed = time.time() - start
                    stage = data.get("stage", {})
                    stage_name = stage.get("name", phase) if isinstance(stage, dict) else phase
                    print(f"  [{elapsed:5.0f}s] {stage_name} ({percent}%)")
                    last_phase = phase

                if status in ("completed", "failed", "error"):
                    elapsed = time.time() - start
                    print(f"  Analysis {status} in {elapsed:.0f}s")
                    return status
        except Exception as e:
            print(f"  Poll error: {e}")

        time.sleep(3)

    print(f"  Analysis timed out after {timeout_sec}s")
    return "timeout"


def consume_sse_stream(response):
    """Consume an SSE stream response and return the final content."""
    full_content = ""
    for line in response.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                token = data.get("token", "")
                if token:
                    full_content += token
                if data.get("done"):
                    break
                if data.get("event") == "done" or data.get("type") == "done":
                    break
                if data.get("error"):
                    return None, data.get("error")
            except json.JSONDecodeError:
                pass
    return full_content, None


def generate_findings_letter(token, analysis_id):
    """Generate findings letter via SSE stream (same as browser)."""
    print(f"  Generating findings letter...")
    start = time.time()
    try:
        r = api("get", f"/analysis/{analysis_id}/letter/stream?force_generation=true", token, timeout=300, stream=True)
        if not r.ok:
            print(f"  Findings letter failed: {r.status_code} {r.text[:200]}")
            return None

        content, error = consume_sse_stream(r)
        elapsed = time.time() - start

        if error:
            print(f"  Findings letter error after {elapsed:.0f}s: {error}")
            return None

        print(f"  Findings letter: {len(content)} chars in {elapsed:.0f}s")
        return content
    except Exception as e:
        elapsed = time.time() - start
        print(f"  Findings letter exception after {elapsed:.0f}s: {e}")
        return None


def generate_demand_letter(token, analysis_id):
    """Generate demand letter via SSE stream (same as browser)."""
    print(f"  Generating demand letter...")
    start = time.time()
    try:
        r = api("get", f"/analysis/{analysis_id}/demand-letter/stream", token, timeout=300, stream=True)
        if not r.ok:
            error_text = r.text[:300] if not r.headers.get("content-type", "").startswith("text/event-stream") else "(SSE stream)"
            print(f"  Demand letter failed: {r.status_code} {error_text}")
            return None

        content, error = consume_sse_stream(r)
        elapsed = time.time() - start

        if error:
            print(f"  Demand letter error after {elapsed:.0f}s: {error}")
            return None

        print(f"  Demand letter: {len(content)} chars in {elapsed:.0f}s")
        return content
    except Exception as e:
        elapsed = time.time() - start
        print(f"  Demand letter exception after {elapsed:.0f}s: {e}")
        return None


def run_case(name, token, skip_analysis=False, letters_only=False):
    """Run full pipeline for a single case."""
    print(f"\n{'='*60}")
    print(f"CASE: {name}")
    print(f"{'='*60}")

    case = find_case(token, name)
    if not case:
        print(f"  Case not found!")
        return {"name": name, "status": "NOT_FOUND"}

    case_id = case["id"]
    print(f"  ID: {case_id}")
    print(f"  Status: {case['status']}")

    result = {"name": case["client_name"], "case_id": case_id}

    # Analysis
    existing = find_analysis(case_id)

    if letters_only or skip_analysis:
        if not existing or not existing["has_msr"]:
            print(f"  No completed analysis with multi-stage results!")
            result["analysis"] = "MISSING"
            return result
        analysis_id = existing["id"]
        print(f"  Using existing analysis: {analysis_id[:12]}...")
    else:
        if existing and existing["has_msr"]:
            analysis_id = existing["id"]
            print(f"  Using existing analysis: {analysis_id[:12]}... (has multi-stage)")
        else:
            analysis_id = start_analysis(token, case_id)
            if not analysis_id:
                result["analysis"] = "START_FAILED"
                return result

            status = poll_analysis(token, analysis_id)
            if status != "completed":
                result["analysis"] = status
                return result

            # Verify multi-stage
            check = find_analysis(case_id)
            if not check or not check["has_msr"]:
                print(f"  Analysis completed but multi-stage MISSING")
                result["analysis"] = "NO_MSR"
                return result
            analysis_id = check["id"]

    result["analysis_id"] = analysis_id
    result["analysis"] = "OK"

    # Letters
    findings = generate_findings_letter(token, analysis_id)
    result["findings"] = len(findings) if findings else 0

    demand = generate_demand_letter(token, analysis_id)
    result["demand"] = len(demand) if demand else 0

    # Save locally
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'output', case["client_name"].lower().replace(' ', '_'))
    os.makedirs(output_dir, exist_ok=True)

    if findings:
        path = os.path.join(output_dir, "findings_letter.html")
        with open(path, "w") as f:
            f.write(findings)
        print(f"  Saved: {path}")

    if demand:
        path = os.path.join(output_dir, "demand_letter.html")
        with open(path, "w") as f:
            f.write(demand)
        print(f"  Saved: {path}")

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="Client name or 'all' for all 5 cases")
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--letters-only", action="store_true")
    args = parser.parse_args()

    print("Getting auth token...")
    token = get_user_token()
    if not token:
        print("Failed to get auth token!")
        sys.exit(1)
    print(f"Token: {token[:20]}...")

    cases = ALL_CASES if args.name.lower() == "all" else [args.name]

    results = []
    total_start = time.time()

    for name in cases:
        r = run_case(name, token, skip_analysis=args.skip_analysis, letters_only=args.letters_only)
        results.append(r)

    total_elapsed = time.time() - total_start

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY ({total_elapsed:.0f}s total)")
    print(f"{'='*60}")
    print(f"{'Case':<25s} {'Analysis':<12s} {'Findings':<12s} {'Demand':<12s}")
    print(f"{'-'*25} {'-'*12} {'-'*12} {'-'*12}")
    for r in results:
        analysis = r.get("analysis", "?")
        findings = f"{r.get('findings', 0):,d} chars" if r.get("findings") else "FAILED"
        demand = f"{r.get('demand', 0):,d} chars" if r.get("demand") else "FAILED"
        print(f"{r['name']:<25s} {analysis:<12s} {findings:<12s} {demand:<12s}")


if __name__ == "__main__":
    main()
