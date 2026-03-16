#!/usr/bin/env python3
"""Re-run full analysis on a case from snapshot or Supabase."""
import os
import sys
import json
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set debug environment before any imports
os.environ["VERCEL"] = "1"  # Simulate Vercel mode (SSE streaming)
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["DIAGNOSTIC_MODE"] = "true"

from dotenv import load_dotenv
load_dotenv()

from legal_portal.services.analysis.main_processor import MainProcessor


async def run_analysis(snapshot_path: str):
    """Run analysis using snapshot data.
    
    Args:
        snapshot_path: Path to the case.json snapshot file
    """
    with open(snapshot_path) as f:
        data = json.load(f)
    
    case = data["case"]
    documents = data["documents"]
    
    print(f"\n{'='*60}")
    print(f"Running analysis for: {case['client_name']}")
    print(f"Case ID: {case['id']}")
    print(f"Documents: {len(documents)}")
    print(f"Environment: VERCEL={os.environ.get('VERCEL')}")
    print(f"{'='*60}\n")
    
    # Progress callback for visibility
    def progress_callback(event_type, progress, message, **kwargs):
        stage = kwargs.get("stage", {})
        stage_id = stage.get("id", "") if isinstance(stage, dict) else ""
        print(f"[{progress:3d}%] [{event_type:20s}] {message} {stage_id}")
    
    processor = MainProcessor()
    
    try:
        result = await processor.process_case(
            case_id=case["id"],
            documents=documents,
            progress_callback=progress_callback,
        )
        
        print(f"\n{'='*60}")
        print("ANALYSIS COMPLETE")
        print(f"{'='*60}")
        print(f"Status: {result.get('status')}")
        print(f"Multi-stage error: {result.get('multi_stage_error', 'None')}")
        
        if result.get('multi_stage_result'):
            msr = result['multi_stage_result']
            print(f"\nMulti-stage result:")
            print(f"  Fact matrix parties: {len(msr.get('fact_matrix', {}).get('parties', []))}")
            print(f"  Primary issues: {len(msr.get('issue_map', {}).get('primary_issues', []))}")
        
        print(f"{'='*60}")
        return result
        
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"ERROR: {type(e).__name__}: {e}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
        return None


def find_snapshot(name: str = None) -> str:
    """Find snapshot path by name or use default."""
    snapshots_dir = os.path.join(os.path.dirname(__file__), '..', 'snapshots')
    
    if name:
        # Try to find matching snapshot
        safe_name = name.lower().replace(' ', '_').replace("'", "")
        path = os.path.join(snapshots_dir, safe_name, "case.json")
        if os.path.exists(path):
            return path
        # Try direct path
        if os.path.exists(name):
            return name
    
    # Default to Mary Ann Rivera
    default_path = os.path.join(snapshots_dir, "mary_ann_rivera", "case.json")
    if os.path.exists(default_path):
        return default_path
    
    # List available snapshots
    print("Available snapshots:")
    if os.path.exists(snapshots_dir):
        for item in os.listdir(snapshots_dir):
            case_path = os.path.join(snapshots_dir, item, "case.json")
            if os.path.exists(case_path):
                print(f"  - {item}")
    
    print("\nRun 'make pull-case' first to download case data.")
    return None


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else None
    snapshot = find_snapshot(name)
    
    if snapshot:
        print(f"Using snapshot: {snapshot}")
        asyncio.run(run_analysis(snapshot))
    else:
        sys.exit(1)

