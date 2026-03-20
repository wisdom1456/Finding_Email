#!/usr/bin/env python3
"""Run full pipeline: analysis + findings letter + demand letter for a case.

Calls service layer directly (same code as production endpoints).

Usage:
    python3 scripts/testing/run_full_pipeline.py "Ron Bryant"
    python3 scripts/testing/run_full_pipeline.py "Ron Bryant" --skip-analysis
    python3 scripts/testing/run_full_pipeline.py "Ron Bryant" --letters-only
"""
import os
import sys
import asyncio
import json
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
os.environ.setdefault("LOG_LEVEL", "INFO")

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client


def get_supabase():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))


def find_case(supabase, name):
    r = supabase.table("cases").select("id, client_name, status").ilike(
        "client_name", f"%{name}%"
    ).order("created_at", desc=True).limit(1).execute()
    if not r.data:
        print(f"Case not found: {name}")
        sys.exit(1)
    return r.data[0]


def find_analysis(supabase, case_id):
    """Find latest completed analysis with multi-stage results."""
    r = supabase.table("analysis_results").select("id, status, result").eq(
        "case_id", case_id
    ).eq("status", "completed").order("created_at", desc=True).limit(1).execute()
    if not r.data:
        return None
    a = r.data[0]
    result = a.get("result") or {}
    if not result.get("multi_stage_result"):
        return None
    return a


async def run_analysis(case_id, supabase):
    """Run analysis pipeline."""
    from legal_portal.services.analysis.analysis_orchestrator import process_case_background
    from legal_portal.services.shared.progress_manager import ProgressManager

    ar = supabase.table("analysis_results").insert({
        "case_id": case_id, "status": "pending"
    }).execute()
    analysis_id = ar.data[0]["id"]
    supabase.table("cases").update({"status": "processing"}).eq("id", case_id).execute()

    pm = ProgressManager()
    start = time.time()
    try:
        await process_case_background(case_id, analysis_id, supabase, "openai", progress_manager=pm)
        elapsed = time.time() - start
        print(f"  Analysis completed in {elapsed:.0f}s")
    except Exception as e:
        elapsed = time.time() - start
        print(f"  Analysis FAILED after {elapsed:.0f}s: {e}")

    return analysis_id


async def generate_findings_letter(analysis_id, supabase):
    """Generate findings email using the recommendation letter service."""
    from legal_portal.services.letters.recommendation_letter_service import RecommendationLetterService
    from legal_portal.utils.openai_client import OpenAIClient
    from legal_portal.core.data_models import ProcessingResult

    # Load analysis
    ar = supabase.table("analysis_results").select("*").eq("id", analysis_id).single().execute()
    analysis = ar.data
    result_payload = analysis.get("result", {})

    if not result_payload or not result_payload.get("multi_stage_result"):
        print("  Findings: SKIP (no multi-stage result)")
        return None

    pr = ProcessingResult(**result_payload)
    msr = pr.multi_stage_result
    case_id = analysis.get("case_id")

    # Load case info
    case_r = supabase.table("cases").select("*").eq("id", case_id).single().execute()
    case_info = case_r.data

    client = OpenAIClient()
    service = RecommendationLetterService(client)

    start = time.time()
    try:
        letter_html = await service.generate_recommendation_letter(
            analysis_result=result_payload,
            case_info=case_info,
            jurisdiction=result_payload.get("jurisdiction", "Florida"),
        )
        elapsed = time.time() - start
        char_count = len(letter_html) if letter_html else 0
        print(f"  Findings letter: {char_count} chars in {elapsed:.0f}s")

        # Save to analysis result
        if letter_html:
            generated_letters = result_payload.setdefault("generated_letters", {})
            generated_letters["findings"] = letter_html
            generated_letters["findings_meta"] = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "char_count": char_count,
            }
            supabase.table("analysis_results").update({
                "result": result_payload
            }).eq("id", analysis_id).execute()
            print(f"  Findings letter: SAVED to DB")

        return letter_html
    except Exception as e:
        elapsed = time.time() - start
        print(f"  Findings letter FAILED after {elapsed:.0f}s: {e}")
        import traceback
        traceback.print_exc()
        return None


async def generate_demand_letter(analysis_id, supabase):
    """Generate demand letter."""
    from legal_portal.services.letters.demand_letter_service import DemandLetterService
    from legal_portal.utils.openai_client import OpenAIClient
    from legal_portal.core.data_models import ProcessingResult

    ar = supabase.table("analysis_results").select("*").eq("id", analysis_id).single().execute()
    analysis = ar.data
    result_payload = analysis.get("result", {})

    if not result_payload or not result_payload.get("multi_stage_result"):
        print("  Demand letter: SKIP (no multi-stage result)")
        return None

    case_id = analysis.get("case_id")
    case_r = supabase.table("cases").select("*").eq("id", case_id).single().execute()
    case_info = case_r.data

    client = OpenAIClient()
    service = DemandLetterService(client)

    start = time.time()
    try:
        letter_html = await service.generate_demand_letter(
            analysis_result=result_payload,
            case_info=case_info,
            jurisdiction=result_payload.get("jurisdiction", "Florida"),
        )
        elapsed = time.time() - start
        char_count = len(letter_html) if letter_html else 0
        print(f"  Demand letter: {char_count} chars in {elapsed:.0f}s")

        if letter_html:
            generated_letters = result_payload.setdefault("generated_letters", {})
            generated_letters["demand"] = letter_html
            generated_letters["demand_meta"] = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "char_count": char_count,
            }
            supabase.table("analysis_results").update({
                "result": result_payload
            }).eq("id", analysis_id).execute()
            print(f"  Demand letter: SAVED to DB")

        return letter_html
    except Exception as e:
        elapsed = time.time() - start
        print(f"  Demand letter FAILED after {elapsed:.0f}s: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="Client name (partial match)")
    parser.add_argument("--skip-analysis", action="store_true", help="Use existing analysis")
    parser.add_argument("--letters-only", action="store_true", help="Only generate letters")
    args = parser.parse_args()

    supabase = get_supabase()
    case = find_case(supabase, args.name)
    case_id = case["id"]
    print(f"\n{'='*60}")
    print(f"Case: {case['client_name']} ({case_id})")
    print(f"{'='*60}")

    # Check for existing analysis
    existing = find_analysis(supabase, case_id)

    if args.letters_only or args.skip_analysis:
        if not existing:
            print("No completed analysis with multi-stage results. Run analysis first.")
            sys.exit(1)
        analysis_id = existing["id"]
        print(f"Using existing analysis: {analysis_id[:8]}...")
    else:
        if existing and not args.letters_only:
            print(f"Existing analysis found: {existing['id'][:8]}... (has multi-stage)")
            print("Re-running analysis...")

        analysis_id = await run_analysis(case_id, supabase)

        # Verify
        check = supabase.table("analysis_results").select("status, result").eq(
            "id", analysis_id
        ).single().execute()
        r = check.data.get("result") or {}
        msr = r.get("multi_stage_result")
        if not msr:
            print(f"Analysis completed but multi-stage MISSING. Cannot generate letters.")
            print(f"Error: {r.get('multi_stage_error', 'unknown')}")
            sys.exit(1)

        fm = msr.get("fact_matrix", {})
        im = msr.get("issue_map", {})
        print(f"Multi-stage: parties={len(fm.get('parties', []))}, "
              f"issues={len(im.get('primary_issues', []))}")

    # Generate letters
    print(f"\n--- Generating Letters ---")
    total_start = time.time()

    findings = await generate_findings_letter(analysis_id, supabase)
    demand = await generate_demand_letter(analysis_id, supabase)

    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"COMPLETE: {case['client_name']}")
    print(f"  Analysis: {analysis_id[:8]}...")
    print(f"  Findings: {'OK' if findings else 'FAILED'} ({len(findings or '')} chars)")
    print(f"  Demand:   {'OK' if demand else 'FAILED'} ({len(demand or '')} chars)")
    print(f"  Letter gen time: {total_elapsed:.0f}s")
    print(f"{'='*60}\n")

    # Save HTML files locally for review
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'output', case['client_name'].lower().replace(' ', '_'))
    os.makedirs(output_dir, exist_ok=True)

    if findings:
        path = os.path.join(output_dir, "findings_letter.html")
        with open(path, "w") as f:
            f.write(findings)
        print(f"Saved: {path}")

    if demand:
        path = os.path.join(output_dir, "demand_letter.html")
        with open(path, "w") as f:
            f.write(demand)
        print(f"Saved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
