#!/usr/bin/env python3
"""Run full analysis pipeline against a live case via Supabase, same as production.

Usage:
    python3 scripts/testing/run_live_analysis.py "Paul Beiter"
    python3 scripts/testing/run_live_analysis.py "Ron Bryant"
"""
import os
import sys
import asyncio
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

os.environ.setdefault("LOG_LEVEL", "INFO")

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client


async def run_analysis(client_name: str):
    """Start analysis for a case by client name, using the real production pipeline."""
    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_KEY"),
    )

    # Find case
    result = supabase.table("cases").select("id, client_name, status").ilike(
        "client_name", f"%{client_name}%"
    ).order("created_at", desc=True).limit(1).execute()

    if not result.data:
        print(f"No case found for '{client_name}'")
        return

    case = result.data[0]
    case_id = case["id"]
    print(f"Case: {case['client_name']} (ID: {case_id}, status: {case['status']})")

    # Create analysis record
    ar = supabase.table("analysis_results").insert({
        "case_id": case_id,
        "status": "pending",
    }).execute()
    analysis_id = ar.data[0]["id"]
    print(f"Analysis record: {analysis_id}")

    # Update case status
    supabase.table("cases").update({"status": "processing"}).eq("id", case_id).execute()

    # Import the real pipeline
    from legal_portal.services.analysis.analysis_orchestrator import process_case_background
    from legal_portal.services.shared.progress_manager import ProgressManager

    progress_manager = ProgressManager()

    print(f"\n{'='*60}")
    print(f"Starting analysis pipeline...")
    print(f"{'='*60}\n")

    start = time.time()

    try:
        await process_case_background(
            case_id=case_id,
            analysis_id=analysis_id,
            supabase=supabase,
            provider="openai",
            progress_manager=progress_manager,
        )
        elapsed = time.time() - start
        print(f"\n{'='*60}")
        print(f"ANALYSIS COMPLETE in {elapsed:.1f}s")
        print(f"{'='*60}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n{'='*60}")
        print(f"ANALYSIS FAILED after {elapsed:.1f}s: {type(e).__name__}: {e}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()

    # Check final status
    final = supabase.table("analysis_results").select(
        "id, status, error"
    ).eq("id", analysis_id).single().execute()
    print(f"\nFinal status: {final.data['status']}")
    if final.data.get("error"):
        print(f"Error: {final.data['error']}")

    # Check if multi-stage result exists
    full = supabase.table("analysis_results").select(
        "id, status, result"
    ).eq("id", analysis_id).single().execute()
    r = full.data.get("result") or {}
    msr = r.get("multi_stage_result")
    if msr:
        fm = msr.get("fact_matrix", {})
        im = msr.get("issue_map", {})
        print(f"Multi-stage: parties={len(fm.get('parties', []))}, "
              f"timeline={len(fm.get('timeline', []))}, "
              f"primary_issues={len(im.get('primary_issues', []))}")
    else:
        print(f"Multi-stage: MISSING (error: {r.get('multi_stage_error', 'unknown')})")

    return analysis_id


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Paul Beiter"
    asyncio.run(run_analysis(name))
