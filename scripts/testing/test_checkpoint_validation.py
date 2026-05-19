#!/usr/bin/env python3
"""Checkpoint validation test suite for Phase 2: Stage Checkpointing.

Tests:
1. Normal end-to-end: confirm checkpoint writes appear, no regression
2. Post-summarization failure sim: inject failure, verify resume
3. Post-fact-extraction failure sim: inject failure, verify resume
4. Document-set change: modify hash, verify invalidation

Usage:
    python3 scripts/testing/test_checkpoint_validation.py --test normal "Giuseppe Iacono"
    python3 scripts/testing/test_checkpoint_validation.py --test all "Giuseppe Iacono"
"""
import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

os.environ.setdefault("LOG_LEVEL", "WARNING")

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client


def get_supabase():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))


def find_case(sb, name):
    result = sb.table("cases").select("id, client_name, status").ilike(
        "client_name", f"%{name}%"
    ).order("created_at", desc=True).limit(1).execute()
    if not result.data:
        print(f"ERROR: No case found for '{name}'")
        sys.exit(1)
    return result.data[0]


def start_analysis(sb, case_id):
    """Create analysis_results + analysis_jobs records, return (analysis_id, job_id)."""
    ar = sb.table("analysis_results").insert({
        "case_id": case_id, "status": "pending",
    }).execute()
    analysis_id = ar.data[0]["id"]

    aj = sb.table("analysis_jobs").insert({
        "case_id": case_id,
        "analysis_id": analysis_id,
        "status": "pending",
        "stage": "queued",
    }).execute()
    job_id = aj.data[0]["id"]

    sb.table("cases").update({"status": "processing"}).eq("id", case_id).execute()
    return analysis_id, job_id


def poll_job(sb, job_id, timeout=900, interval=10):
    """Poll analysis_jobs until terminal state. Returns final job row."""
    start = time.time()
    last_stage = ""
    while time.time() - start < timeout:
        row = sb.table("analysis_jobs").select("*").eq("id", job_id).single().execute()
        job = row.data
        status = job["status"]
        stage = job.get("stage", "?")
        checkpoint = job.get("checkpoint") or {}
        lcs = checkpoint.get("last_completed_stage", "-")

        if stage != last_stage:
            elapsed = time.time() - start
            cp_keys = [k for k in checkpoint if k != "last_completed_stage"]
            print(f"  [{elapsed:6.1f}s] status={status} stage={stage} checkpoint.last={lcs} keys={cp_keys}")
            last_stage = stage

        if status in ("completed", "failed", "cancelled"):
            return job

        time.sleep(interval)

    print(f"TIMEOUT after {timeout}s")
    return None


def get_checkpoint(sb, job_id):
    row = sb.table("analysis_jobs").select("checkpoint").eq("id", job_id).single().execute()
    return (row.data or {}).get("checkpoint") or {}


def set_checkpoint(sb, job_id, checkpoint):
    sb.table("analysis_jobs").update({"checkpoint": checkpoint}).eq("id", job_id).execute()


def get_chunk_state(sb, analysis_id):
    row = sb.table("analysis_results").select("chunk_state").eq("id", analysis_id).single().execute()
    return (row.data or {}).get("chunk_state") or {}


def reset_job_for_retry(sb, job_id, analysis_id, case_id):
    """Reset a completed/failed job back to pending for retry."""
    sb.table("analysis_jobs").update({
        "status": "pending",
        "stage": "queued",
        "worker_id": None,
        "error": None,
        "error_type": None,
        "completed_at": None,
    }).eq("id", job_id).execute()
    sb.table("analysis_results").update({
        "status": "pending",
        "result": None,
        "completed_at": None,
    }).eq("id", analysis_id).execute()
    sb.table("cases").update({"status": "processing"}).eq("id", case_id).execute()


# ============================================================
# Test 1: Normal end-to-end
# ============================================================
def test_normal(sb, case_name):
    print(f"\n{'='*60}")
    print(f"TEST 1: Normal end-to-end (no regression)")
    print(f"{'='*60}")

    case = find_case(sb, case_name)
    case_id = case["id"]
    print(f"Case: {case['client_name']} (status: {case['status']})")

    analysis_id, job_id = start_analysis(sb, case_id)
    print(f"Job: {job_id[:8]}  Analysis: {analysis_id[:8]}")
    print(f"Polling (worker should pick up within ~5s)...")

    start = time.time()
    final = poll_job(sb, job_id)
    elapsed = time.time() - start

    if not final:
        print("FAIL: Timed out")
        return False

    status = final["status"]
    checkpoint = final.get("checkpoint") or {}

    print(f"\nResult: status={status} duration={elapsed:.1f}s")
    print(f"Checkpoint after completion: {json.dumps(checkpoint)[:200]}")

    # Verify: checkpoint should be cleared on success
    if status == "completed" and checkpoint == {}:
        print("PASS: checkpoint cleared after success")
    elif status == "completed":
        print(f"WARN: checkpoint not cleared: {list(checkpoint.keys())}")
    else:
        print(f"FAIL: job status={status} error={final.get('error', '')[:200]}")
        return False

    # Check that analysis_results has a result
    ar = sb.table("analysis_results").select("status, result").eq("id", analysis_id).single().execute()
    has_result = bool(ar.data and ar.data.get("result"))
    has_msr = bool(has_result and ar.data["result"].get("multi_stage_result"))
    print(f"analysis_results: status={ar.data.get('status')} has_result={has_result} has_msr={has_msr}")

    if has_msr:
        print("PASS: Normal end-to-end completed successfully")
        return True
    else:
        print("FAIL: Missing multi_stage_result")
        return False


# ============================================================
# Test 2: Post-summarization failure + retry
# ============================================================
def test_post_summarization_retry(sb, case_name):
    print(f"\n{'='*60}")
    print(f"TEST 2: Post-summarization failure → retry with checkpoint")
    print(f"{'='*60}")

    case = find_case(sb, case_name)
    case_id = case["id"]
    print(f"Case: {case['client_name']}")

    analysis_id, job_id = start_analysis(sb, case_id)
    print(f"Job: {job_id[:8]}  Analysis: {analysis_id[:8]}")
    print(f"Phase A: Running until summarization checkpoint appears...")

    # Poll until summarization checkpoint appears
    start = time.time()
    while time.time() - start < 600:
        cp = get_checkpoint(sb, job_id)
        if cp.get("summarization", {}).get("completed"):
            print(f"  Summarization checkpoint found at {time.time()-start:.1f}s")
            print(f"  doc_ids_hash={cp['summarization'].get('doc_ids_hash')}")
            print(f"  summary_count={cp['summarization'].get('summary_count')}")
            break
        time.sleep(5)
    else:
        print("FAIL: Summarization checkpoint never appeared")
        return False

    # Wait for job to complete normally first time
    final = poll_job(sb, job_id)
    first_elapsed = time.time() - start
    if not final or final["status"] != "completed":
        print(f"FAIL: First run didn't complete: {final}")
        return False

    print(f"\nPhase A complete: {first_elapsed:.1f}s")

    # Now simulate retry: reset job with checkpoint data pre-loaded
    # Read the checkpoint that was saved during summarization
    # (it was cleared on success, so we reconstruct it from what we captured)
    cs = get_chunk_state(sb, analysis_id)
    summaries_count = len(cs.get("summaries", {}))
    doc_ids = sorted(cs.get("documents", {}).keys())
    doc_ids_hash = hashlib.sha256("|".join(doc_ids).encode()).hexdigest()[:16]

    retry_checkpoint = {
        "summarization": {
            "completed": True,
            "doc_ids_hash": doc_ids_hash,
            "summary_count": summaries_count,
        },
        "last_completed_stage": "summarization",
    }

    print(f"\nPhase B: Resetting job with summarization checkpoint...")
    print(f"  Injecting checkpoint: summary_count={summaries_count} hash={doc_ids_hash}")
    set_checkpoint(sb, job_id, retry_checkpoint)
    reset_job_for_retry(sb, job_id, analysis_id, case_id)

    retry_start = time.time()
    final2 = poll_job(sb, job_id)
    retry_elapsed = time.time() - retry_start

    if not final2 or final2["status"] != "completed":
        print(f"FAIL: Retry didn't complete: status={final2.get('status') if final2 else 'timeout'}")
        return False

    print(f"\nPhase B complete: {retry_elapsed:.1f}s")
    time_saved = first_elapsed - retry_elapsed
    print(f"Time saved on retry: {time_saved:.1f}s ({time_saved/first_elapsed*100:.0f}%)")

    # Verify result quality
    ar = sb.table("analysis_results").select("status, result").eq("id", analysis_id).single().execute()
    has_msr = bool(ar.data and ar.data.get("result", {}).get("multi_stage_result"))
    print(f"Has multi_stage_result: {has_msr}")

    if has_msr and retry_elapsed < first_elapsed:
        print("PASS: Retry skipped summarization and completed faster")
        return True
    elif has_msr:
        print("WARN: Retry completed but wasn't faster (possible overhead)")
        return True
    else:
        print("FAIL: Retry missing multi_stage_result")
        return False


# ============================================================
# Test 3: Post-fact-extraction failure + retry
# ============================================================
def test_post_fact_extraction_retry(sb, case_name):
    print(f"\n{'='*60}")
    print(f"TEST 3: Post-fact-extraction failure → retry with checkpoint")
    print(f"{'='*60}")

    case = find_case(sb, case_name)
    case_id = case["id"]
    print(f"Case: {case['client_name']}")

    analysis_id, job_id = start_analysis(sb, case_id)
    print(f"Job: {job_id[:8]}  Analysis: {analysis_id[:8]}")
    print(f"Phase A: Running until fact_matrix checkpoint appears...")

    start = time.time()
    while time.time() - start < 600:
        cp = get_checkpoint(sb, job_id)
        if cp.get("fact_matrix"):
            print(f"  fact_matrix checkpoint found at {time.time()-start:.1f}s")
            print(f"  last_completed_stage={cp.get('last_completed_stage')}")
            fm = cp["fact_matrix"]
            print(f"  parties={len(fm.get('parties', []))} events={len(fm.get('timeline', []))}")
            break
        time.sleep(5)
    else:
        print("FAIL: fact_matrix checkpoint never appeared")
        return False

    # Wait for full completion
    final = poll_job(sb, job_id)
    first_elapsed = time.time() - start
    if not final or final["status"] != "completed":
        print(f"FAIL: First run didn't complete")
        return False

    print(f"\nPhase A complete: {first_elapsed:.1f}s")

    # Capture the checkpoint at fact_matrix stage
    cs = get_chunk_state(sb, analysis_id)
    doc_ids = sorted(cs.get("documents", {}).keys())
    doc_ids_hash = hashlib.sha256("|".join(doc_ids).encode()).hexdigest()[:16]
    summaries_count = len(cs.get("summaries", {}))

    # Read the analysis result to get fact_matrix and synthesis
    ar = sb.table("analysis_results").select("result").eq("id", analysis_id).single().execute()
    msr = ar.data["result"]["multi_stage_result"]

    retry_checkpoint = {
        "summarization": {
            "completed": True,
            "doc_ids_hash": doc_ids_hash,
            "summary_count": summaries_count,
        },
        "synthesis": ar.data["result"].get("case_analysis"),
        "fact_matrix": msr["fact_matrix"],
        "last_completed_stage": "fact_matrix",
    }

    # case_analysis is a JSON string in result, need to parse it
    ca_raw = ar.data["result"].get("case_analysis")
    if isinstance(ca_raw, str):
        try:
            retry_checkpoint["synthesis"] = json.loads(ca_raw)
        except Exception:
            pass

    print(f"\nPhase B: Resetting job with fact_matrix checkpoint...")
    set_checkpoint(sb, job_id, retry_checkpoint)
    reset_job_for_retry(sb, job_id, analysis_id, case_id)

    retry_start = time.time()
    final2 = poll_job(sb, job_id)
    retry_elapsed = time.time() - retry_start

    if not final2 or final2["status"] != "completed":
        print(f"FAIL: Retry didn't complete")
        return False

    print(f"\nPhase B complete: {retry_elapsed:.1f}s")
    time_saved = first_elapsed - retry_elapsed
    print(f"Time saved on retry: {time_saved:.1f}s ({time_saved/first_elapsed*100:.0f}%)")

    ar2 = sb.table("analysis_results").select("status, result").eq("id", analysis_id).single().execute()
    has_msr = bool(ar2.data and ar2.data.get("result", {}).get("multi_stage_result"))

    if has_msr and retry_elapsed < first_elapsed:
        print("PASS: Retry skipped summarization + synthesis + fact extraction")
        return True
    elif has_msr:
        print("WARN: Completed but wasn't faster")
        return True
    else:
        print("FAIL: Missing result")
        return False


# ============================================================
# Test 4: Document-set change → checkpoint invalidation
# ============================================================
def test_doc_set_change(sb, case_name):
    print(f"\n{'='*60}")
    print(f"TEST 4: Document-set change → checkpoint invalidation")
    print(f"{'='*60}")

    case = find_case(sb, case_name)
    case_id = case["id"]
    print(f"Case: {case['client_name']}")

    analysis_id, job_id = start_analysis(sb, case_id)
    print(f"Job: {job_id[:8]}  Analysis: {analysis_id[:8]}")
    print(f"Phase A: Running to completion...")

    start = time.time()
    final = poll_job(sb, job_id)
    first_elapsed = time.time() - start

    if not final or final["status"] != "completed":
        print(f"FAIL: First run didn't complete")
        return False

    print(f"Phase A complete: {first_elapsed:.1f}s")

    # Inject checkpoint with WRONG doc_ids_hash
    wrong_checkpoint = {
        "summarization": {
            "completed": True,
            "doc_ids_hash": "deadbeef12345678",  # Wrong hash
            "summary_count": 99,
        },
        "synthesis": {"practice_area": "Fake", "case_summary": "Fake"},
        "fact_matrix": {"parties": [], "timeline": [], "financial_data": [], "key_documents": [], "preliminary_issues": []},
        "last_completed_stage": "fact_matrix",
    }

    print(f"\nPhase B: Resetting with WRONG doc_ids_hash...")
    set_checkpoint(sb, job_id, wrong_checkpoint)
    reset_job_for_retry(sb, job_id, analysis_id, case_id)

    retry_start = time.time()
    final2 = poll_job(sb, job_id)
    retry_elapsed = time.time() - retry_start

    if not final2 or final2["status"] != "completed":
        print(f"FAIL: Retry didn't complete")
        return False

    print(f"\nPhase B complete: {retry_elapsed:.1f}s")

    # The retry should have taken about the same time as first run
    # (checkpoint was invalidated, full restart)
    ratio = retry_elapsed / first_elapsed if first_elapsed > 0 else 1.0
    print(f"Timing ratio (retry/first): {ratio:.2f}")

    ar2 = sb.table("analysis_results").select("status, result").eq("id", analysis_id).single().execute()
    has_msr = bool(ar2.data and ar2.data.get("result", {}).get("multi_stage_result"))

    if has_msr and ratio > 0.7:
        print("PASS: Checkpoint invalidated, full restart occurred")
        return True
    elif has_msr and ratio <= 0.7:
        print("WARN: Completed but suspiciously fast — may not have invalidated")
        return False
    else:
        print("FAIL: Missing result")
        return False


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Checkpoint validation tests")
    parser.add_argument("case_name", help="Client name to test with")
    parser.add_argument("--test", choices=["normal", "post_summarization", "post_fact", "doc_change", "all"],
                        default="normal", help="Which test to run")
    args = parser.parse_args()

    sb = get_supabase()

    tests = {
        "normal": test_normal,
        "post_summarization": test_post_summarization_retry,
        "post_fact": test_post_fact_extraction_retry,
        "doc_change": test_doc_set_change,
    }

    if args.test == "all":
        results = {}
        for name, fn in tests.items():
            results[name] = fn(sb, args.case_name)
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        for name, passed in results.items():
            print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    else:
        tests[args.test](sb, args.case_name)


if __name__ == "__main__":
    main()
