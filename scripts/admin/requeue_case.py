"""Re-enqueue the most recent failed analysis job for a case, preserving its checkpoint.

Picks the latest failed job (best checkpoint), resets status=pending, attempts=0,
clears error/finished fields, leaves checkpoint intact so the worker resumes from
the last completed stage instead of restarting summarization.

Usage:
    python scripts/admin/requeue_case.py <case_id> [--apply]

Without --apply, prints what it would do (dry run).
"""

from __future__ import annotations

import argparse
import json
import sys

from _supabase import get_supabase


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_id")
    ap.add_argument("--apply", action="store_true", help="Actually perform the reset")
    args = ap.parse_args()

    sb = get_supabase()

    jobs = (
        sb.table("analysis_jobs")
        .select("id,status,attempts,stage,error,error_type,checkpoint,created_at")
        .eq("case_id", args.case_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
        .data
        or []
    )

    if not jobs:
        print(f"No jobs found for case {args.case_id}")
        return 1

    print(f"Most recent jobs for case {args.case_id}:")
    for j in jobs:
        cp = j.get("checkpoint") or {}
        print(
            f"  {j['id'][:12]}  status={j['status']:<10} attempts={j.get('attempts')} "
            f"stage={j.get('stage')}  last_completed_stage={cp.get('last_completed_stage')}  "
            f"created={j['created_at']}"
        )

    failed = [j for j in jobs if j["status"] in ("error", "failed")]
    if not failed:
        print("\nNo failed jobs to re-enqueue.")
        return 0

    target = max(
        failed,
        key=lambda j: (
            bool((j.get("checkpoint") or {}).get("last_completed_stage")),
            j["created_at"],
        ),
    )
    cp = target.get("checkpoint") or {}
    print(
        f"\nTarget job to re-enqueue: {target['id']}\n"
        f"  last_completed_stage={cp.get('last_completed_stage')}\n"
        f"  summarization_completed={(cp.get('summarization') or {}).get('completed')}\n"
        f"  prior error: {(target.get('error') or '')[:200]}"
    )

    if not args.apply:
        print("\n(dry run) Re-run with --apply to reset this job to pending.")
        return 0

    upd = (
        sb.table("analysis_jobs")
        .update(
            {
                "status": "pending",
                "attempts": 0,
                "error": None,
                "error_type": None,
                "worker_id": None,
                "claimed_at": None,
                "started_at": None,
                "completed_at": None,
                "heartbeat_at": None,
                "next_retry_at": None,
            }
        )
        .eq("id", target["id"])
        .execute()
    )

    if not upd.data:
        print(f"ERROR: update returned no rows for job {target['id']}", file=sys.stderr)
        return 2

    print(f"OK: job {target['id']} reset to pending. Worker will claim on next poll.")
    print(json.dumps(upd.data[0], indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
