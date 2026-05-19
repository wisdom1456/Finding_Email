#!/usr/bin/env python3
"""Find cases that have docs uploaded but no analysis ever started.

Pattern this catches: a user imports a matter from Clio, docs sync as
``extraction_method='deferred'`` (status='pending'), the user never
clicks 'analyze', and the case sits idle indefinitely with the docs
stuck in pending. Invisible without this script.

Once migration 20260519000000 is applied this can also be done as:
  SELECT * FROM cases_needing_attention
   WHERE NOT has_ever_been_analyzed
     AND docs_ready > 0;
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _supabase import get_supabase, paginate  # noqa: E402


def parse_ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_age(seconds):
    seconds = int(seconds)
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def main():
    sb = get_supabase()
    now = datetime.now(timezone.utc)

    cases = paginate(lambda s, e: (
        sb.table("cases").select("id, user_id, client_name, status, updated_at")
        .order("id").range(s, e)
    ))
    case_by_id = {c["id"]: c for c in cases}

    docs = paginate(lambda s, e: (
        sb.table("documents").select("id, case_id, status")
        .order("id").range(s, e)
    ))
    docs_by_case: dict = defaultdict(list)
    for d in docs:
        docs_by_case[d["case_id"]].append(d)

    jobs = paginate(lambda s, e: (
        sb.table("analysis_jobs").select("case_id, status")
        .order("id").range(s, e)
    ))
    case_has_job = {j["case_id"] for j in jobs}

    profiles = paginate(lambda s, e: (
        sb.table("profiles").select("id, email").order("id").range(s, e)
    ))
    email_by_uid = {p["id"]: p["email"] for p in profiles}

    needs_attention = []
    for c in cases:
        cdocs = docs_by_case.get(c["id"], [])
        if not cdocs:
            continue
        ready = sum(1 for d in cdocs if d["status"] == "ready")
        pending = sum(1 for d in cdocs if d["status"] == "pending")
        has_job = c["id"] in case_has_job
        if not has_job and ready > 0:
            needs_attention.append({
                "case": c,
                "ready": ready,
                "pending": pending,
                "total": len(cdocs),
            })

    print(f"=== Cases with docs ready but NO analysis ever ({len(needs_attention)}) ===")
    needs_attention.sort(key=lambda x: -x["ready"])
    for item in needs_attention:
        c = item["case"]
        email = email_by_uid.get(c["user_id"], "?")
        idle = (now - parse_ts(c["updated_at"])).total_seconds()
        print(f"  case={c['id'][:8]}  user={email:<30}  "
              f"client={(c.get('client_name') or '?')[:25]:<25}  "
              f"ready={item['ready']:>3} pending={item['pending']:>3} "
              f"total={item['total']:>3}  status={c['status']:<10}  idle={fmt_age(idle)}")


if __name__ == "__main__":
    main()
