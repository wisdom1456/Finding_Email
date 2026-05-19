#!/usr/bin/env python3
"""Per-letter QA audit for completed analyses.

Reads quality_report_v2 signals from analysis_results.result.generated_letters
and reports per-user pass/fail rates plus the worst-performing recent letters.

Once migration 20260519000000 is applied this can also be done as:
  SELECT * FROM letter_quality_signals WHERE NOT qa_term_explainer_passed;

This script is the manual fallback when SQL Editor access isn't available.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _supabase import get_supabase, paginate  # noqa: E402


def dig(obj, *path, default=None):
    cur = obj
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def main():
    parser = argparse.ArgumentParser(description="Letter quality audit")
    parser.add_argument("--days", type=int, default=28, help="Lookback window")
    args = parser.parse_args()

    sb = get_supabase()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=args.days)

    # Pull completed jobs in window
    jobs = paginate(lambda s, e: (
        sb.table("analysis_jobs")
        .select("id, case_id, analysis_id, completed_at, doc_count")
        .eq("status", "completed")
        .gte("created_at", window_start.isoformat())
        .order("id")
        .range(s, e)
    ))
    if not jobs:
        print("No completed jobs in window.")
        return

    analysis_ids = [j["analysis_id"] for j in jobs if j.get("analysis_id")]
    results = paginate(lambda s, e: (
        sb.table("analysis_results")
        .select("id, case_id, result")
        .in_("id", analysis_ids)
        .order("id")
        .range(s, e)
    ))
    res_by_id = {r["id"]: r for r in results}

    case_ids = list({j["case_id"] for j in jobs})
    cases = paginate(lambda s, e: (
        sb.table("cases").select("id, user_id, client_name, jurisdiction")
        .in_("id", case_ids).order("id").range(s, e)
    ))
    case_by_id = {c["id"]: c for c in cases}
    user_ids = list({c["user_id"] for c in cases})
    profs = paginate(lambda s, e: (
        sb.table("profiles").select("id, email")
        .in_("id", user_ids).order("id").range(s, e)
    ))
    email_by_uid = {p["id"]: p["email"] for p in profs}

    print(f"{'completed':<20} {'user':<24} {'client':<22} {'jur':<3} "
          f"{'has_letter':<10} {'qa_term':<8} {'qa_evid':<8} {'qa_demand':<10}")
    print("-" * 120)

    agg = Counter()
    by_user: Dict[str, Counter] = defaultdict(Counter)

    for j in jobs:
        case = case_by_id.get(j["case_id"], {})
        user = email_by_uid.get(case.get("user_id"), "?")
        client = (case.get("client_name") or "?")[:20]
        jurisdiction = (case.get("jurisdiction") or "?")[:2]
        r = res_by_id.get(j.get("analysis_id"), {})
        payload = r.get("result") or {}
        gl = payload.get("generated_letters") or {}
        qa = dig(gl, "findings_meta", "quality_report",
                 "quality_report_v2", default={}) or {}

        has_findings = "findings" in gl
        term_explainer = qa.get("term_explainer_passed")
        evid = qa.get("evidence_linkage_score")
        demand_spec = qa.get("demand_specificity_passed")

        agg["total"] += 1
        if not has_findings:
            agg["no_letter"] += 1
        if term_explainer is False:
            agg["term_explainer_failed"] += 1
        if isinstance(evid, (int, float)) and evid < 0.5:
            agg["evid_low"] += 1

        bu = by_user[user]
        bu["jobs"] += 1
        if has_findings and term_explainer is not False:
            bu["clean"] += 1
        elif term_explainer is False:
            bu["term_failed"] += 1

        completed = (j.get("completed_at") or "")[:19]
        print(f"{completed:<20} {user[:22]:<24} {client:<22} {jurisdiction:<3} "
              f"{str(has_findings):<10} {str(term_explainer):<8} "
              f"{evid if evid is not None else '-':<8} "
              f"{str(demand_spec):<10}")

    print("\n=== AGGREGATE ===")
    for k, v in agg.most_common():
        print(f"  {k:<28} {v}")

    print("\n=== PER USER ===")
    for user, ctr in sorted(by_user.items(), key=lambda x: -x[1]["jobs"]):
        print(f"  {user:<30} jobs={ctr['jobs']} clean={ctr['clean']} "
              f"term_failed={ctr['term_failed']}")


if __name__ == "__main__":
    main()
