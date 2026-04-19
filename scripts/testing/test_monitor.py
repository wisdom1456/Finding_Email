#!/usr/bin/env python3
"""Manual integration tests for the worker monitor endpoint.

Tests:
  1. healthy    — normal state, monitor returns healthy/no_pending_jobs
  2. stuck_jobs — simulate a stuck pending job, verify STUCK_JOBS alert triggers
  3. zombie     — simulate pending jobs with no recent claim, verify WORKER_INACTIVE
  4. cooldown   — set recent restart time, verify redeploy is skipped

Usage:
    # Test against deployed Vercel:
    python3 scripts/testing/test_monitor.py --test healthy

    # Test against local FastAPI:
    API_BASE_URL=http://localhost:8000 python3 scripts/testing/test_monitor.py --test healthy

    # Run all tests:
    python3 scripts/testing/test_monitor.py --test all
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from dotenv import load_dotenv
load_dotenv()

import requests
from supabase import create_client

BASE = os.getenv("API_BASE_URL", "https://finding-emails.vercel.app")
CRON_SECRET = os.getenv("CRON_SECRET", "")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

HEADERS = {"Authorization": f"Bearer {CRON_SECRET}"}


def get_sb():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def call_monitor() -> dict:
    resp = requests.get(f"{BASE}/api/monitor/worker", headers=HEADERS, timeout=30)
    print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json()


def test_healthy():
    """Baseline: monitor returns healthy or no_pending_jobs."""
    print("\n[TEST 1] Healthy state")
    data = call_monitor()
    assert data["status"] in ("healthy", "alert_sent", "no_pending_jobs"), \
        f"Unexpected status: {data['status']}"
    assert "checks" in data
    print(f"  PASS: status={data['status']}")


def test_stuck_jobs():
    """Insert a 20-min-old pending job, verify STUCK_JOBS triggers."""
    print("\n[TEST 2] Stuck jobs detection")
    sb = get_sb()

    case = sb.table("cases").select("id").limit(1).execute()
    assert case.data, "No cases found — need at least one case in DB"
    case_id = case.data[0]["id"]

    ar = sb.table("analysis_results").insert({"case_id": case_id, "status": "pending"}).execute()
    ar_id = ar.data[0]["id"]

    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    job = sb.table("analysis_jobs").insert({
        "case_id": case_id,
        "analysis_id": ar_id,
        "status": "pending",
        "stage": "queued",
        "created_at": old_ts,
    }).execute()
    job_id = job.data[0]["id"]
    print(f"  Inserted fake stuck job: {job_id[:8]}... (created 20min ago)")

    try:
        data = call_monitor()
        assert data["status"] in ("alert_sent", "alert_failed"), \
            f"Expected alert, got: {data['status']}"
        assert data["checks"]["stuck_jobs"]["triggered"], "stuck_jobs check not triggered"
        print(f"  PASS: STUCK_JOBS detected, status={data['status']}")
    finally:
        try:
            sb.table("analysis_jobs").delete().eq("id", job_id).execute()
        except Exception as e:
            print(f"  WARNING: failed to delete job {job_id}: {e}")
        try:
            sb.table("analysis_results").delete().eq("id", ar_id).execute()
        except Exception as e:
            print(f"  WARNING: failed to delete result {ar_id}: {e}")
        print("  Cleanup: removed test records")


def test_zombie_worker():
    """Insert recent pending job with no claimed_at, verify WORKER_INACTIVE."""
    print("\n[TEST 3] Zombie worker detection")
    sb = get_sb()

    case = sb.table("cases").select("id").limit(1).execute()
    assert case.data, "No cases found"
    case_id = case.data[0]["id"]

    ar = sb.table("analysis_results").insert({"case_id": case_id, "status": "pending"}).execute()
    ar_id = ar.data[0]["id"]

    recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    job = sb.table("analysis_jobs").insert({
        "case_id": case_id,
        "analysis_id": ar_id,
        "status": "pending",
        "stage": "queued",
        "created_at": recent_ts,
    }).execute()
    job_id = job.data[0]["id"]
    print(f"  Inserted pending job (1min old, no claim): {job_id[:8]}...")

    try:
        data = call_monitor()
        triggered = data["checks"]["worker_inactive"]["triggered"]
        if triggered:
            print(f"  PASS: WORKER_INACTIVE detected, status={data['status']}")
        else:
            print("  INFO: Not triggered — another job was recently claimed (worker active). "
                  "Run when worker is idle for a clean zombie test.")
    finally:
        try:
            sb.table("analysis_jobs").delete().eq("id", job_id).execute()
        except Exception as e:
            print(f"  WARNING: failed to delete job {job_id}: {e}")
        try:
            sb.table("analysis_results").delete().eq("id", ar_id).execute()
        except Exception as e:
            print(f"  WARNING: failed to delete result {ar_id}: {e}")
        print("  Cleanup: removed test records")


def test_restart_cooldown():
    """Set last_restart_at to 5 min ago, verify redeploy is skipped."""
    print("\n[TEST 4] Restart cooldown")
    sb = get_sb()

    recent_restart = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    sb.table("monitor_state").update({"value": recent_restart}).eq("key", "last_restart_at").execute()
    print("  Set last_restart_at = 5 min ago")

    try:
        data = call_monitor()
        assert not data.get("recovery_triggered"), "Redeploy should be skipped within cooldown"
        print(f"  PASS: recovery_triggered={data.get('recovery_triggered')} (expected False)")
    finally:
        try:
            sb.table("monitor_state").update({"value": None}).eq("key", "last_restart_at").execute()
        except Exception as e:
            print(f"  WARNING: failed to reset monitor_state: {e} — manually set last_restart_at=NULL")
        print("  Cleanup: reset last_restart_at to NULL")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", choices=["healthy", "stuck", "zombie", "cooldown", "all"],
                        default="healthy")
    args = parser.parse_args()

    if not CRON_SECRET:
        print("WARNING: CRON_SECRET not set — auth check will be skipped by server")

    tests = {
        "healthy": test_healthy,
        "stuck": test_stuck_jobs,
        "zombie": test_zombie_worker,
        "cooldown": test_restart_cooldown,
    }

    if args.test == "all":
        for fn in tests.values():
            fn()
    else:
        tests[args.test]()

    print("\nDone.")


if __name__ == "__main__":
    main()
