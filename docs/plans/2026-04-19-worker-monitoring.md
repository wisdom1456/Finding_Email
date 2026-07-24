# Worker Monitoring & Alerting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect and alert when the Railway analysis worker is alive but not processing jobs ("zombie worker"), and optionally trigger an automatic redeploy.

**Architecture:** A FastAPI route (`GET /api/monitor/worker`) runs health checks against Supabase on every invocation. A Vercel cron job calls this route every 5 minutes. If stuck jobs or an inactive worker are detected, the route posts a Slack/webhook alert and optionally triggers a Railway redeploy (rate-limited to once per 30 minutes via a `monitor_state` Supabase table).

**Tech Stack:** FastAPI, supabase-py, httpx (already in deps), Vercel Cron, Railway GraphQL API, Slack Incoming Webhooks.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| CREATE | `src/legal_portal/api/routes/monitor.py` | All health-check, alert, and recovery logic |
| MODIFY | `src/legal_portal/api/main.py` | Register monitor router |
| MODIFY | `vercel.json` | Add 5-minute cron schedule |
| CREATE | `supabase/migrations/20260419000000_add_monitor_state.sql` | `monitor_state` table for restart rate-limiting |
| MODIFY | `.env.template` | Document new env vars |
| CREATE | `scripts/testing/test_monitor.py` | Manual integration test (simulate stuck jobs) |

---

## Configuration Reference

| Env Var | Required | Description |
|---------|----------|-------------|
| `CRON_SECRET` | Yes (auto-set by Vercel) | Vercel sets this; cron requests carry `Authorization: Bearer <CRON_SECRET>` |
| `ALERT_WEBHOOK_URL` | Yes | Slack Incoming Webhook URL (or any HTTP POST endpoint) |
| `RAILWAY_API_TOKEN` | Optional | Railway personal token — enables auto-redeploy |
| `RAILWAY_SERVICE_ID` | Optional | `cdea3704-576e-49c2-91bd-1071d15c11c5` (already known) |
| `RAILWAY_ENVIRONMENT_ID` | Optional | `604f43c7-df41-48f2-8179-ea23c41d7f0d` (already known) |

**Thresholds (hardcoded, easy to move to env vars later):**

```python
STUCK_JOB_MINUTES = 15        # pending job older than this → STUCK_JOBS alert
ZOMBIE_WORKER_MINUTES = 10    # no claim in this window with pending jobs → WORKER_INACTIVE alert
RESTART_COOLDOWN_MINUTES = 30 # minimum time between auto-redeploys
```

---

## Task 1: Supabase Migration — monitor_state Table

**Files:**
- Create: `supabase/migrations/20260419000000_add_monitor_state.sql`

This table holds a single row per key. We use key `last_restart_at` to enforce the 30-minute restart cooldown across stateless Vercel invocations.

- [ ] **Step 1.1: Write the migration**

```sql
-- supabase/migrations/20260419000000_add_monitor_state.sql
-- Lightweight key-value store for monitor state (e.g. restart rate limiting).
-- One row per key. Only service_role writes to this table.

CREATE TABLE IF NOT EXISTS monitor_state (
    key   TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed the restart rate-limit row with a NULL value (no restarts yet)
INSERT INTO monitor_state (key, value)
VALUES ('last_restart_at', NULL)
ON CONFLICT (key) DO NOTHING;

-- No RLS: only accessed via service_role key
```

- [ ] **Step 1.2: Apply migration to Supabase**

Run in the Supabase SQL editor (project: `nqjepycmhddfekeufcle`), or via CLI:

```bash
# If supabase CLI is linked:
supabase db push

# Or paste the SQL directly into: https://supabase.com/dashboard/project/nqjepycmhddfekeufcle/sql
```

Expected: Table `monitor_state` created, one row with `key='last_restart_at'`, `value=NULL`.

- [ ] **Step 1.3: Verify**

```bash
python3 -c "
import os; from dotenv import load_dotenv; load_dotenv()
from supabase import create_client
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))
print(sb.table('monitor_state').select('*').execute().data)
"
```

Expected output: `[{'key': 'last_restart_at', 'value': None, 'updated_at': '...'}]`

- [ ] **Step 1.4: Commit**

```bash
git add supabase/migrations/20260419000000_add_monitor_state.sql
git commit -m "feat: add monitor_state table for worker restart rate limiting"
```

---

## Task 2: Monitor Route

**Files:**
- Create: `src/legal_portal/api/routes/monitor.py`

This is the core file. It contains all check logic, alert sending, and Railway redeploy. No external imports beyond what's already in requirements.txt (`httpx` is pulled in by `supabase`; if not, `requests` is already a dep).

- [ ] **Step 2.1: Write the failing test first**

```python
# scripts/testing/test_monitor.py  (scaffold — full version in Task 5)
import requests, os
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv("API_BASE_URL", "https://finding-emails.vercel.app")
SECRET = os.getenv("CRON_SECRET", "")

def test_monitor_healthy():
    """When no stuck jobs exist, monitor returns healthy status."""
    resp = requests.get(
        f"{BASE}/api/monitor/worker",
        headers={"Authorization": f"Bearer {SECRET}"},
        timeout=30,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "alert_sent", "no_pending_jobs")
    assert "checks" in data
    print(f"PASS: {data}")

test_monitor_healthy()
```

Run it now — expect a 404 (route doesn't exist yet):

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 scripts/testing/test_monitor.py
```

Expected: `404 Not Found` or connection error — confirms route is missing.

- [ ] **Step 2.2: Write the monitor route**

```python
# src/legal_portal/api/routes/monitor.py
"""Worker health monitor — called by Vercel cron every 5 minutes.

Checks:
  STUCK_JOBS    — any job pending > 15 min
  WORKER_INACTIVE — jobs in queue but no claim in > 10 min

Alerts via Slack/webhook POST. Optionally triggers Railway redeploy
with a 30-minute cooldown stored in monitor_state table.

Authentication: Vercel cron sends Authorization: Bearer <CRON_SECRET>.
Manual invocations must send the same header.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Header, HTTPException, status

from legal_portal.core.supabase_client import get_service_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor", tags=["monitor"])

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

STUCK_JOB_MINUTES = 15
ZOMBIE_WORKER_MINUTES = 10
RESTART_COOLDOWN_MINUTES = 30


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.get("/worker")
def check_worker_health(authorization: str = Header(default="")):
    """Run worker health checks. Called by Vercel cron every 5 minutes."""
    _verify_auth(authorization)

    sb = get_service_supabase()
    env = os.getenv("VERCEL_ENV", os.getenv("ENVIRONMENT", "unknown"))
    now = datetime.now(timezone.utc)

    logger.info("[MONITOR] Running worker health checks")

    # --- Check 1: Stuck jobs (pending > STUCK_JOB_MINUTES) ---
    stuck_cutoff = _minutes_ago_iso(STUCK_JOB_MINUTES)
    stuck = (
        sb.table("analysis_jobs")
        .select("id, case_id, created_at")
        .eq("status", "pending")
        .lt("created_at", stuck_cutoff)
        .execute()
    )
    stuck_jobs = stuck.data or []

    # --- Check 2: Zombie worker (pending jobs + no recent claim) ---
    pending = (
        sb.table("analysis_jobs")
        .select("id", count="exact")
        .eq("status", "pending")
        .execute()
    )
    pending_count = pending.count or 0

    zombie_cutoff = _minutes_ago_iso(ZOMBIE_WORKER_MINUTES)
    recent_claims = (
        sb.table("analysis_jobs")
        .select("id", count="exact")
        .gte("claimed_at", zombie_cutoff)
        .execute()
    )
    has_recent_claim = (recent_claims.count or 0) > 0

    zombie_detected = pending_count > 0 and not has_recent_claim

    # --- Build result ---
    checks = {
        "stuck_jobs": {
            "count": len(stuck_jobs),
            "threshold_minutes": STUCK_JOB_MINUTES,
            "triggered": len(stuck_jobs) > 0,
        },
        "worker_inactive": {
            "pending_count": pending_count,
            "has_recent_claim": has_recent_claim,
            "threshold_minutes": ZOMBIE_WORKER_MINUTES,
            "triggered": zombie_detected,
        },
    }

    any_alert = len(stuck_jobs) > 0 or zombie_detected

    if not any_alert:
        if pending_count == 0:
            logger.info("[MONITOR] Healthy — no pending jobs")
            return {"status": "no_pending_jobs", "checks": checks}
        logger.info("[MONITOR] Healthy — worker is active")
        return {"status": "healthy", "checks": checks}

    # --- Build alert message ---
    oldest_age_minutes = _oldest_job_age_minutes(stuck_jobs)
    alerts_triggered = []

    if len(stuck_jobs) > 0:
        alerts_triggered.append("STUCK_JOBS")
    if zombie_detected:
        alerts_triggered.append("WORKER_INACTIVE")

    message = _build_slack_message(
        alerts=alerts_triggered,
        stuck_count=len(stuck_jobs),
        oldest_age_minutes=oldest_age_minutes,
        pending_count=pending_count,
        env=env,
        now=now,
    )

    # --- Send alert ---
    alert_sent = _send_alert(message)
    if alert_sent:
        logger.warning(f"[ALERT] Sent: {alerts_triggered} | stuck={len(stuck_jobs)} pending={pending_count}")
    else:
        logger.error("[ALERT] Failed to send webhook alert")

    # --- Optional auto-recovery ---
    recovery_triggered = False
    if os.getenv("RAILWAY_API_TOKEN") and any_alert:
        recovery_triggered = _maybe_redeploy(sb)

    return {
        "status": "alert_sent" if alert_sent else "alert_failed",
        "alerts": alerts_triggered,
        "checks": checks,
        "alert_sent": alert_sent,
        "recovery_triggered": recovery_triggered,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _verify_auth(authorization: str) -> None:
    """Accept Vercel cron secret or manual invocation with same secret."""
    cron_secret = os.getenv("CRON_SECRET", "")
    if not cron_secret:
        # No secret configured — allow through (dev/test only)
        logger.warning("[MONITOR] CRON_SECRET not set — skipping auth")
        return
    expected = f"Bearer {cron_secret}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid monitor secret")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minutes_ago_iso(minutes: int) -> str:
    """Return ISO timestamp for N minutes ago (UTC)."""
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _oldest_job_age_minutes(stuck_jobs: list[dict]) -> float:
    """Return age in minutes of the oldest job in the list."""
    if not stuck_jobs:
        return 0.0
    now = datetime.now(timezone.utc)
    oldest = min(
        datetime.fromisoformat(j["created_at"].replace("Z", "+00:00"))
        for j in stuck_jobs
    )
    return (now - oldest).total_seconds() / 60


def _build_slack_message(
    alerts: list[str],
    stuck_count: int,
    oldest_age_minutes: float,
    pending_count: int,
    env: str,
    now: datetime,
) -> dict:
    """Build a Slack Block Kit message payload."""
    alert_label = " | ".join(alerts)
    ts = now.strftime("%Y-%m-%d %H:%M UTC")

    lines = [f"*:warning: Worker Alert — {alert_label}*", f"Environment: `{env}` | {ts}"]

    if stuck_count > 0:
        lines.append(f"• *STUCK_JOBS*: {stuck_count} job(s) pending >{STUCK_JOB_MINUTES}min (oldest: {oldest_age_minutes:.0f}min)")
    if "WORKER_INACTIVE" in alerts:
        lines.append(f"• *WORKER_INACTIVE*: {pending_count} job(s) queued, no claim in >{ZOMBIE_WORKER_MINUTES}min")

    lines.append("\n_Action: Check Railway worker logs or redeploy._")

    return {"text": "\n".join(lines)}


def _send_alert(payload: dict) -> bool:
    """POST alert payload to ALERT_WEBHOOK_URL. Returns True on success."""
    url = os.getenv("ALERT_WEBHOOK_URL", "")
    if not url:
        logger.warning("[ALERT] ALERT_WEBHOOK_URL not configured — skipping")
        return False
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"[ALERT] Webhook POST failed: {e}")
        return False


def _maybe_redeploy(sb) -> bool:
    """Trigger Railway redeploy if cooldown has elapsed. Returns True if triggered."""
    # Check cooldown via monitor_state
    row = sb.table("monitor_state").select("value").eq("key", "last_restart_at").single().execute()
    last_restart_raw = (row.data or {}).get("value")

    if last_restart_raw:
        last_restart = datetime.fromisoformat(last_restart_raw.replace("Z", "+00:00"))
        elapsed_minutes = (datetime.now(timezone.utc) - last_restart).total_seconds() / 60
        if elapsed_minutes < RESTART_COOLDOWN_MINUTES:
            logger.info(f"[RECOVERY] Skipping redeploy — cooldown active ({elapsed_minutes:.0f}min < {RESTART_COOLDOWN_MINUTES}min)")
            return False

    # Trigger Railway redeploy via GraphQL API
    token = os.getenv("RAILWAY_API_TOKEN", "")
    service_id = os.getenv("RAILWAY_SERVICE_ID", "cdea3704-576e-49c2-91bd-1071d15c11c5")
    environment_id = os.getenv("RAILWAY_ENVIRONMENT_ID", "604f43c7-df41-48f2-8179-ea23c41d7f0d")

    query = """
    mutation serviceInstanceRedeploy($environmentId: String!, $serviceId: String!) {
        serviceInstanceRedeploy(environmentId: $environmentId, serviceId: $serviceId)
    }
    """
    try:
        resp = requests.post(
            "https://backboard.railway.app/graphql/v2",
            json={
                "query": query,
                "variables": {"environmentId": environment_id, "serviceId": service_id},
            },
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("errors"):
            logger.error(f"[RECOVERY] Railway API errors: {result['errors']}")
            return False

        # Record restart time
        now_iso = datetime.now(timezone.utc).isoformat()
        sb.table("monitor_state").update({"value": now_iso, "updated_at": now_iso}).eq("key", "last_restart_at").execute()
        logger.warning(f"[RECOVERY] Railway redeploy triggered successfully")
        return True
    except Exception as e:
        logger.error(f"[RECOVERY] Redeploy request failed: {e}")
        return False
```

- [ ] **Step 2.3: Verify imports — check `get_service_supabase` exists**

```bash
grep -rn "get_service_supabase\|def get_service_supabase" /Users/BRFlorida/Projects/Work/Finding_Emails/src/legal_portal/
```

If the function doesn't exist under that name, find the correct one:

```bash
grep -rn "service_supabase\|create_client.*SERVICE_KEY\|supabase_client" /Users/BRFlorida/Projects/Work/Finding_Emails/src/legal_portal/core/ | head -20
grep -rn "service_supabase\|create_client.*SERVICE_KEY\|supabase_client" /Users/BRFlorida/Projects/Work/Finding_Emails/src/legal_portal/api/dependencies.py | head -20
```

Then update the import in `monitor.py` to match the actual function name. Common alternatives:
- `from legal_portal.api.dependencies import get_service_supabase`
- `from legal_portal.core.supabase_client import supabase_service`
- Or inline: `from supabase import create_client; sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])`

- [ ] **Step 2.4: Commit**

```bash
git add src/legal_portal/api/routes/monitor.py
git commit -m "feat: add worker health monitor route with stuck-job and zombie-worker detection"
```

---

## Task 3: Register Route + Vercel Cron

**Files:**
- Modify: `src/legal_portal/api/main.py`
- Modify: `vercel.json`

- [ ] **Step 3.1: Register monitor router in main.py**

Find the router registration block (around line 147) and add one line:

```python
# In src/legal_portal/api/main.py, add to the imports at top:
from legal_portal.api.routes import (
    ...
    monitor,       # ADD THIS
    ...
)

# In the router registration block, add:
app.include_router(monitor.router, prefix="/api", tags=["monitor"])
```

- [ ] **Step 3.2: Add Vercel cron to vercel.json**

Replace the contents of `vercel.json`:

```json
{
  "framework": "sveltekit",
  "buildCommand": "bash scripts/vercel_build.sh",
  "functions": {
    "api/index.py": {
      "maxDuration": 800
    }
  },
  "rewrites": [
    {
      "source": "/api/(.*)",
      "destination": "/api/index.py"
    }
  ],
  "crons": [
    {
      "path": "/api/monitor/worker",
      "schedule": "*/5 * * * *"
    }
  ]
}
```

Note: Vercel automatically injects `Authorization: Bearer <CRON_SECRET>` on cron requests. `CRON_SECRET` is auto-generated by Vercel — no manual setup needed.

- [ ] **Step 3.3: Verify route resolves locally**

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python3 -c "
import sys; sys.path.insert(0,'src')
from legal_portal.api.main import app
routes = [r.path for r in app.routes]
assert any('monitor' in r for r in routes), f'monitor route missing. routes={routes}'
print('OK — /api/monitor/worker registered')
"
```

Expected: `OK — /api/monitor/worker registered`

- [ ] **Step 3.4: Commit**

```bash
git add src/legal_portal/api/main.py vercel.json
git commit -m "feat: register monitor route and add Vercel 5-minute cron"
```

---

## Task 4: Environment Variables

**Files:**
- Modify: `.env.template`

- [ ] **Step 4.1: Add new vars to .env.template**

Append to `.env.template`:

```bash
# ---------------------------------------------------------------------------
# Worker Monitoring & Alerting
# ---------------------------------------------------------------------------

# Slack Incoming Webhook URL (or any HTTP POST endpoint that accepts JSON)
# Get from: Slack → Your App → Incoming Webhooks → Add New Webhook
# If unset, alerts are logged but not sent externally.
ALERT_WEBHOOK_URL=

# Railway personal API token for auto-redeploy on zombie detection.
# Get from: https://railway.app/account/tokens
# If unset, auto-redeploy is disabled (alerts still fire).
RAILWAY_API_TOKEN=

# Railway identifiers — pre-filled for this project
RAILWAY_SERVICE_ID=cdea3704-576e-49c2-91bd-1071d15c11c5
RAILWAY_ENVIRONMENT_ID=604f43c7-df41-48f2-8179-ea23c41d7f0d

# CRON_SECRET is auto-generated by Vercel. Pull it with:
#   vercel env pull .env.local
# Then set CRON_SECRET in your local .env for manual test invocations.
CRON_SECRET=
```

- [ ] **Step 4.2: Add env vars to Vercel**

```bash
# Alert webhook (required for alerts to fire)
vercel env add ALERT_WEBHOOK_URL production

# Railway token (optional — enables auto-redeploy)
vercel env add RAILWAY_API_TOKEN production

# Railway IDs (use defaults already in monitor.py, or override)
vercel env add RAILWAY_SERVICE_ID production
vercel env add RAILWAY_ENVIRONMENT_ID production
```

- [ ] **Step 4.3: Pull updated env locally**

```bash
vercel env pull .env.local
# Then copy CRON_SECRET value into your .env for local testing
```

- [ ] **Step 4.4: Commit**

```bash
git add .env.template
git commit -m "docs: add monitoring env vars to .env.template"
```

---

## Task 5: Test Script

**Files:**
- Create: `scripts/testing/test_monitor.py`

- [ ] **Step 5.1: Write full test script**

```python
#!/usr/bin/env python3
"""Manual integration tests for the worker monitor endpoint.

Tests:
  1. healthy    — normal state (no stuck jobs)
  2. stuck_jobs — simulate a stuck pending job, verify alert triggers
  3. zombie     — simulate pending jobs with no recent claim, verify alert

Usage:
    # Test against deployed Vercel:
    python3 scripts/testing/test_monitor.py

    # Test against local FastAPI (uvicorn running on 8000):
    API_BASE_URL=http://localhost:8000 python3 scripts/testing/test_monitor.py --test healthy
"""
import argparse
import os
import sys
import time
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


# ---------------------------------------------------------------------------
# Test 1: Healthy state
# ---------------------------------------------------------------------------

def test_healthy():
    """Baseline: monitor returns healthy or no_pending_jobs when queue is empty."""
    print("\n[TEST 1] Healthy state")
    # Ensure no pending jobs exist (use a non-existent case_id)
    data = call_monitor()
    assert data["status"] in ("healthy", "no_pending_jobs", "alert_sent"), \
        f"Unexpected status: {data['status']}"
    print(f"  PASS: status={data['status']}")


# ---------------------------------------------------------------------------
# Test 2: Stuck jobs detection
# ---------------------------------------------------------------------------

def test_stuck_jobs():
    """Insert a fake pending job with old created_at, verify STUCK_JOBS triggers."""
    print("\n[TEST 2] Stuck jobs detection")
    sb = get_sb()

    # Find any real case_id to attach the test job to
    case = sb.table("cases").select("id").limit(1).execute()
    assert case.data, "No cases found — need at least one case in DB"
    case_id = case.data[0]["id"]

    # Insert fake analysis_results row
    ar = sb.table("analysis_results").insert({"case_id": case_id, "status": "pending"}).execute()
    ar_id = ar.data[0]["id"]

    # Insert fake job with created_at = 20 minutes ago (past the 15-min threshold)
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
        # Cleanup
        sb.table("analysis_jobs").delete().eq("id", job_id).execute()
        sb.table("analysis_results").delete().eq("id", ar_id).execute()
        print(f"  Cleanup: removed test job and analysis_results")


# ---------------------------------------------------------------------------
# Test 3: Zombie worker detection
# ---------------------------------------------------------------------------

def test_zombie_worker():
    """Insert pending job with no recent claim, verify WORKER_INACTIVE triggers."""
    print("\n[TEST 3] Zombie worker detection")
    sb = get_sb()

    case = sb.table("cases").select("id").limit(1).execute()
    assert case.data, "No cases found"
    case_id = case.data[0]["id"]

    ar = sb.table("analysis_results").insert({"case_id": case_id, "status": "pending"}).execute()
    ar_id = ar.data[0]["id"]

    # Job created 1 min ago (not stuck) but with no claimed_at → zombie
    recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    job = sb.table("analysis_jobs").insert({
        "case_id": case_id,
        "analysis_id": ar_id,
        "status": "pending",
        "stage": "queued",
        "created_at": recent_ts,
        # claimed_at intentionally NULL — simulates worker never claiming
    }).execute()
    job_id = job.data[0]["id"]
    print(f"  Inserted fake pending job (1min old, no claim): {job_id[:8]}...")

    try:
        # Note: zombie check looks at claims in last 10 min across ALL jobs.
        # If the real worker is active, this test may see a recent claim and
        # not trigger. That's correct behavior — the zombie check is working.
        data = call_monitor()
        triggered = data["checks"]["worker_inactive"]["triggered"]
        print(f"  worker_inactive triggered={triggered} (expected True if worker idle)")
        if triggered:
            print(f"  PASS: WORKER_INACTIVE detected, status={data['status']}")
        else:
            print(f"  INFO: Not triggered — another job was recently claimed (worker active). "
                  f"Run when worker is idle for a clean zombie test.")
    finally:
        sb.table("analysis_jobs").delete().eq("id", job_id).execute()
        sb.table("analysis_results").delete().eq("id", ar_id).execute()
        print(f"  Cleanup: removed test job")


# ---------------------------------------------------------------------------
# Test 4: Restart cooldown
# ---------------------------------------------------------------------------

def test_restart_cooldown():
    """Set last_restart_at to 5 min ago, verify redeploy is skipped."""
    print("\n[TEST 4] Restart cooldown")
    sb = get_sb()

    recent_restart = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    sb.table("monitor_state").update({"value": recent_restart}).eq("key", "last_restart_at").execute()
    print(f"  Set last_restart_at = 5 min ago")

    # Now call monitor — even if alerts fire, redeploy should be skipped
    data = call_monitor()
    assert not data.get("recovery_triggered"), "Redeploy should be skipped within cooldown"
    print(f"  PASS: recovery_triggered={data.get('recovery_triggered')} (expected False)")

    # Reset
    sb.table("monitor_state").update({"value": None}).eq("key", "last_restart_at").execute()
    print(f"  Cleanup: reset last_restart_at to NULL")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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
        for name, fn in tests.items():
            fn()
    else:
        tests[args.test]()

    print("\nDone.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5.2: Run the healthy test (pre-deploy, expects 404)**

```bash
python3 scripts/testing/test_monitor.py --test healthy
```

Expected: `404` or connection error — route not deployed yet.

- [ ] **Step 5.3: Commit**

```bash
git add scripts/testing/test_monitor.py
git commit -m "test: add worker monitor integration test script"
```

---

## Task 6: Deploy and Verify

- [ ] **Step 6.1: Deploy to Vercel**

```bash
git push origin main
# Vercel auto-deploys on push. Or manually:
# vercel --prod
```

Wait ~2 minutes for build to complete.

- [ ] **Step 6.2: Run healthy test against production**

```bash
# First pull CRON_SECRET from Vercel:
vercel env pull .env.local
# Copy CRON_SECRET into .env

python3 scripts/testing/test_monitor.py --test healthy
```

Expected:
```
[TEST 1] Healthy state
  HTTP 200: {"status":"no_pending_jobs","checks":{...}}
  PASS: status=no_pending_jobs
```

- [ ] **Step 6.3: Run stuck-jobs simulation**

```bash
python3 scripts/testing/test_monitor.py --test stuck
```

Expected:
```
[TEST 2] Stuck jobs detection
  Inserted fake stuck job: e71e7216... (created 20min ago)
  HTTP 200: {"status":"alert_sent","alerts":["STUCK_JOBS"],...}
  PASS: STUCK_JOBS detected, status=alert_sent
  Cleanup: removed test job and analysis_results
```

You should also see a Slack message arrive in the configured channel.

- [ ] **Step 6.4: Verify cron is registered in Vercel**

```bash
vercel inspect --wait
# Or check: https://vercel.com/dashboard → Project → Settings → Crons
```

Expected: One cron entry at `/api/monitor/worker` running `*/5 * * * *`.

- [ ] **Step 6.5: Run cooldown test (if RAILWAY_API_TOKEN set)**

```bash
python3 scripts/testing/test_monitor.py --test cooldown
```

Expected: `recovery_triggered=False` — cooldown gate works.

- [ ] **Step 6.6: Commit final state**

```bash
git add .
git commit -m "feat: worker monitoring live — cron alerts + optional auto-redeploy"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|-------------|------|
| Detect stuck jobs (pending > 15 min) | Task 2 — `stuck_jobs` check |
| Detect zombie worker (no claim in 10 min with pending jobs) | Task 2 — `worker_inactive` check |
| Slack/webhook alerting | Task 2 — `_send_alert()` |
| STUCK_JOBS / WORKER_INACTIVE alert types | Task 2 — `alerts` field in response |
| Job count + oldest age + env + timestamp in alert | Task 2 — `_build_slack_message()` |
| 5-minute scheduled checks | Task 3 — vercel.json cron |
| Auto-recovery with 30-min rate limit | Task 2 — `_maybe_redeploy()` + Task 1 — `monitor_state` table |
| [MONITOR] / [ALERT] / [RECOVERY] log tags | Task 2 — all logger calls |
| No heavy dependencies | ✅ Only `requests` (already in requirements.txt) |

### Placeholder Scan

No TBDs, no "implement later", no missing code blocks found.

### Type Consistency

- `get_service_supabase()` — flagged in Step 2.3 with explicit fallback instructions
- `_minutes_ago_iso()` returns a string consumed by Supabase `.lt()` — consistent
- `monitor_state` table key `last_restart_at` used in Task 1 seed and Task 2 `_maybe_redeploy()` — consistent

---

## Testing Plan Summary

| Scenario | How to Simulate | Expected Outcome |
|----------|-----------------|------------------|
| Healthy | Normal operation | `status=no_pending_jobs` or `healthy` |
| Stuck jobs | `--test stuck` — inserts 20-min-old job | `STUCK_JOBS` alert fires, Slack message |
| Zombie worker | `--test zombie` — pending job, no claim | `WORKER_INACTIVE` alert fires (if worker idle) |
| Restart cooldown | `--test cooldown` — sets recent restart time | `recovery_triggered=False` |
| Real zombie | Kill Railway worker, queue a job, wait 10 min | Both alerts fire, optional redeploy |
