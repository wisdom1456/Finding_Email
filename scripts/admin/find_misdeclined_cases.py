#!/usr/bin/env python3
"""List cases that were declined by the old gap-analysis rule but had
legal merit per deep analysis. These are the cases that would now route
to NEEDS_DOCUMENTATION (request_documents letter) under the 2026-05-19
rule fix.

Use this to decide which cases to offer re-analysis on. Read-only.

Usage:
    python scripts/admin/find_misdeclined_cases.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _supabase import get_supabase, paginate  # noqa: E402


def main():
    sb = get_supabase()

    # Pull all completed analyses with recommendation; manual filter in
    # Python because the JSONB path is too complex for PostgREST.
    rows = paginate(lambda s, e: (
        sb.table("analysis_results")
        .select("id, case_id, result, completed_at")
        .eq("status", "completed")
        .order("id")
        .range(s, e)
    ))

    # Pull cases + profiles in bulk for joining
    case_ids = list({r["case_id"] for r in rows})
    cases = paginate(lambda s, e: (
        sb.table("cases").select("id, user_id, client_name, jurisdiction")
        .in_("id", case_ids).order("id").range(s, e)
    ))
    case_by_id = {c["id"]: c for c in cases}
    user_ids = list({c["user_id"] for c in cases})
    profiles = paginate(lambda s, e: (
        sb.table("profiles").select("id, email")
        .in_("id", user_ids).order("id").range(s, e)
    ))
    email_by_uid = {p["id"]: p["email"] for p in profiles}

    misdeclined = []
    legitimately_declined = []
    for r in rows:
        msr = (r.get("result") or {}).get("multi_stage_result") or {}
        ga = msr.get("gap_analysis") or {}
        da = msr.get("deep_analysis") or {}
        rec = (ga.get("recommendation") or {})
        if rec.get("category") != "not_viable":
            continue
        is_viable = bool(da.get("is_viable", True))
        score = ga.get("overall_completeness_score") or 0
        critical = ga.get("critical_count") or 0
        high = ga.get("high_count") or 0
        case = case_by_id.get(r["case_id"], {})
        email = email_by_uid.get(case.get("user_id"), "?")
        entry = {
            "completed": (r.get("completed_at") or "")[:10],
            "user": email,
            "client": case.get("client_name") or "?",
            "score": score,
            "critical": critical,
            "high": high,
            "is_viable": is_viable,
            "case_id": r["case_id"],
        }
        # Under the new rule, NOT_VIABLE requires either is_viable=False OR
        # score < 30. Anything else that's currently declined would now route
        # to NEEDS_DOCUMENTATION.
        if (not is_viable) or score < 30:
            legitimately_declined.append(entry)
        else:
            misdeclined.append(entry)

    print("=" * 92)
    print("MISDECLINED CASES — under the new rule, these would route to "
          "needs_documentation")
    print("=" * 92)
    print(f"{'completed':<12} {'user':<26} {'client':<28} "
          f"{'score':>5} {'crit':>4} {'high':>4}")
    print("-" * 92)
    misdeclined.sort(key=lambda x: x["user"] + x["client"])
    for m in misdeclined:
        print(f"{m['completed']:<12} {m['user'][:24]:<26} "
              f"{m['client'][:26]:<28} {int(m['score']):>5} "
              f"{m['critical']:>4} {m['high']:>4}")
    print(f"\nTotal misdeclined: {len(misdeclined)}")

    # Per-user roll-up
    from collections import Counter
    by_user = Counter(m["user"] for m in misdeclined)
    print("\nPer-user count of misdeclined cases:")
    for user, n in by_user.most_common():
        print(f"  {user:<35} {n}")

    print(f"\n(legitimately declined — not viable or score < 30: {len(legitimately_declined)})")


if __name__ == "__main__":
    main()
