#!/usr/bin/env python3
"""
Quick diagnostic script to check if gap analysis data exists in the database.
Run with: python3 check_gap_analysis.py <case_id>
"""

import sys
import os
from supabase import create_client

def check_gap_analysis(case_id: str):
    """Check if a case has gap analysis data."""

    # Initialize Supabase client
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        print("❌ Error: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        print("Load environment variables first: source .env")
        return

    supabase = create_client(supabase_url, supabase_key)

    print(f"\n🔍 Checking gap analysis for case: {case_id}\n")

    # Get the latest analysis result for the case
    response = (
        supabase.table("analysis_results")
        .select("id, created_at, status, result")
        .eq("case_id", case_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        print(f"❌ No analysis results found for case {case_id}")
        return

    analysis = response.data[0]
    print(f"✅ Found analysis: {analysis['id']}")
    print(f"   Status: {analysis['status']}")
    print(f"   Created: {analysis['created_at']}")

    result = analysis.get("result", {})
    multi_stage_result = result.get("multi_stage_result")

    if not multi_stage_result:
        print("\n❌ No multi_stage_result found")
        print("   This analysis was run before multi-stage analysis was implemented.")
        print("   Run a new analysis to get gap analysis.")
        return

    gap_analysis = multi_stage_result.get("gap_analysis")

    if not gap_analysis:
        print("\n❌ No gap_analysis found in multi_stage_result")
        print("   This analysis was run before gap analysis was implemented (before today).")
        print("   Run a new analysis to get gap analysis.")
        return

    # Gap analysis exists!
    print("\n✅ Gap analysis found!")
    print(f"\n📊 Gap Analysis Summary:")
    print(f"   Total gaps: {gap_analysis.get('total_gaps', 0)}")
    print(f"   Critical: {gap_analysis.get('critical_count', 0)}")
    print(f"   High: {gap_analysis.get('high_count', 0)}")
    print(f"   Medium: {gap_analysis.get('medium_count', 0)}")
    print(f"   Low: {gap_analysis.get('low_count', 0)}")
    print(f"   Completeness Score: {gap_analysis.get('overall_completeness_score', 0)}/100")

    print(f"\n📝 Attorney Summary:")
    print(f"   {gap_analysis.get('attorney_summary', 'N/A')}")

    print(f"\n🎯 Gap Categories:")
    gaps_by_category = gap_analysis.get('gaps_by_category', {})
    for category, gaps in gaps_by_category.items():
        if gaps:
            print(f"   {category}: {len(gaps)} gaps")
            for gap in gaps[:2]:  # Show first 2 gaps per category
                print(f"      - {gap.get('title', 'Untitled')}")

    print(f"\n✅ Gap analysis data is present in the database.")
    print(f"   You should see a 'Gaps' tab on the results page for this case.")
    print(f"   If you don't see it, check the browser console for errors.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 check_gap_analysis.py <case_id>")
        print("\nExample: python3 check_gap_analysis.py 123e4567-e89b-12d3-a456-426614174000")
        sys.exit(1)

    check_gap_analysis(sys.argv[1])
