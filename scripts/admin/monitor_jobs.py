#!/usr/bin/env python3
"""Operational dashboard for analysis_jobs.

Run periodically (or on demand) to surface:
  - Status breakdown for a configurable window
  - Stuck pending / running jobs
  - Heartbeat-too-old workers (likely dead)
  - Repeated retries
  - Recent failure detail
  - Daily volume + completion latency p50/p95

Read-only. No mutations. Service-role credentials required (see .env).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _supabase import get_supabase, paginate  # noqa: E402


def fmt_age(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d{(seconds % 86400) // 3600}h"


def parse_ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    parser = argparse.ArgumentParser(description="Analysis jobs operational dashboard")
    parser.add_argument("--days", type=int, default=28, help="Lookback window in days")
    args = parser.parse_args()

    sb = get_supabase()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=args.days)

    print("=" * 78)
    print(f"ANALYSIS_JOBS DASHBOARD ({window_start.date()} → {now.date()})")
    print("=" * 78)

    jobs = paginate(lambda s, e: (
        sb.table("analysis_jobs")
        .select(
            "id, case_id, status, stage, attempts, max_attempts, error, error_type, "
            "worker_id, heartbeat_at, claimed_at, started_at, "
            "created_at, updated_at, completed_at, progress, doc_count"
        )
        .gte("created_at", window_start.isoformat())
        .order("id")
        .range(s, e)
    ))
    print(f"\nTotal jobs in window: {len(jobs)}\n")
    if not jobs:
        return

    by_status = Counter(j["status"] for j in jobs)
    for st, n in by_status.most_common():
        print(f"  {st:<10} {n}")

    # Stuck pending
    stuck_pending = [j for j in jobs
                     if j["status"] == "pending"
                     and parse_ts(j["created_at"]) < now - timedelta(minutes=5)]
    if stuck_pending:
        print(f"\n[Pending > 5 min, never claimed] {len(stuck_pending)}")
        for j in stuck_pending[:20]:
            age = (now - parse_ts(j["created_at"])).total_seconds()
            print(f"  job={j['id'][:8]} case={j['case_id'][:8]} "
                  f"age={fmt_age(age)} attempts={j['attempts']}/{j['max_attempts']}")

    # Running too long
    stuck_running = [j for j in jobs
                     if j["status"] == "running" and j.get("started_at")
                     and parse_ts(j["started_at"]) < now - timedelta(minutes=30)]
    if stuck_running:
        print(f"\n[Running > 30 min] {len(stuck_running)}")
        for j in stuck_running[:20]:
            age = (now - parse_ts(j["started_at"])).total_seconds()
            hb = parse_ts(j.get("heartbeat_at"))
            hb_age = fmt_age((now - hb).total_seconds()) if hb else "—"
            progress = j.get("progress") or {}
            print(f"  job={j['id'][:8]} case={j['case_id'][:8]} "
                  f"running={fmt_age(age)} hb={hb_age} stage={j.get('stage')} "
                  f"pct={progress.get('percent')}")

    # Dead worker
    dead = [j for j in jobs
            if j["status"] == "running" and j.get("heartbeat_at")
            and parse_ts(j["heartbeat_at"]) < now - timedelta(seconds=120)]
    if dead:
        print(f"\n[Heartbeat > 120s old (likely dead worker)] {len(dead)}")
        for j in dead[:20]:
            hb = parse_ts(j["heartbeat_at"])
            print(f"  job={j['id'][:8]} case={j['case_id'][:8]} "
                  f"hb_age={fmt_age((now - hb).total_seconds())} "
                  f"worker={j.get('worker_id')}")

    # Retries
    retried = [j for j in jobs if (j.get("attempts") or 0) >= 2]
    if retried:
        print(f"\n[Attempts >= 2] {len(retried)}")
        for j in retried[:20]:
            err = (j.get("error") or "")[:120]
            print(f"  job={j['id'][:8]} status={j['status']} "
                  f"attempts={j['attempts']}/{j['max_attempts']} "
                  f"err_type={j.get('error_type')} err={err!r}")

    # Failed by error_type
    failed = [j for j in jobs if j["status"] == "failed"]
    if failed:
        print(f"\n[Failed by error_type] total={len(failed)}")
        for et, n in Counter(j.get("error_type") or "(none)" for j in failed).most_common():
            print(f"  {et:<30} {n}")

    # Latency
    completed = [j for j in jobs
                 if j["status"] == "completed"
                 and j.get("started_at") and j.get("completed_at")]
    if completed:
        durations = sorted(
            (parse_ts(j["completed_at"]) - parse_ts(j["started_at"])).total_seconds()
            for j in completed
        )
        n = len(durations)
        p50 = durations[n // 2]
        p95 = durations[min(n - 1, int(n * 0.95))]
        print(f"\n[Completion latency — {n} jobs] "
              f"p50={fmt_age(p50)} p95={fmt_age(p95)} max={fmt_age(durations[-1])}")


if __name__ == "__main__":
    main()
