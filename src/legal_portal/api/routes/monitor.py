# src/legal_portal/api/routes/monitor.py
"""Worker health monitor — called by Vercel cron every 5 minutes.

Checks:
  STUCK_JOBS      — any job pending > 15 min
  WORKER_INACTIVE — jobs in queue but no claim in > 10 min

Alerts via Slack/webhook POST. Optionally triggers Railway redeploy
with a 30-minute cooldown stored in monitor_state table.

Authentication: Vercel cron sends Authorization: Bearer <CRON_SECRET>.
Manual invocations must send the same header.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Header, HTTPException, status

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

    from legal_portal.api.dependencies import get_supabase_client
    sb = get_supabase_client()

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
    """Require valid CRON_SECRET on every request. Missing secret is a misconfiguration."""
    cron_secret = os.getenv("CRON_SECRET", "")
    if not cron_secret:
        logger.error("[MONITOR] CRON_SECRET is not set — refusing all requests")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Monitor not configured: CRON_SECRET missing")
    expected = f"Bearer {cron_secret}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid monitor secret")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minutes_ago_iso(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _oldest_job_age_minutes(stuck_jobs: list[dict]) -> float:
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
    row = sb.table("monitor_state").select("value").eq("key", "last_restart_at").maybe_single().execute()
    last_restart_raw = (row.data or {}).get("value") if row.data else None

    if last_restart_raw:
        last_restart = datetime.fromisoformat(last_restart_raw.replace("Z", "+00:00"))
        elapsed_minutes = (datetime.now(timezone.utc) - last_restart).total_seconds() / 60
        if elapsed_minutes < RESTART_COOLDOWN_MINUTES:
            logger.info(f"[RECOVERY] Skipping redeploy — cooldown active ({elapsed_minutes:.0f}min < {RESTART_COOLDOWN_MINUTES}min)")
            return False

    token = os.getenv("RAILWAY_API_TOKEN", "")
    service_id = os.getenv("RAILWAY_SERVICE_ID", "")
    environment_id = os.getenv("RAILWAY_ENVIRONMENT_ID", "")

    if not service_id or not environment_id:
        logger.error("[RECOVERY] RAILWAY_SERVICE_ID or RAILWAY_ENVIRONMENT_ID not set — skipping redeploy")
        return False

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

        now_iso = datetime.now(timezone.utc).isoformat()
        sb.table("monitor_state").upsert({"key": "last_restart_at", "value": now_iso}, on_conflict="key").execute()
        logger.warning("[RECOVERY] Railway redeploy triggered successfully")
        return True
    except Exception as e:
        logger.error(f"[RECOVERY] Redeploy request failed: {e}")
        return False
