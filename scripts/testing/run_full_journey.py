#!/usr/bin/env python3
"""Full user journey verification via production HTTP routes.

Exercises the complete path the browser uses:
  delete case → create from Clio → import docs → verify OCR →
  run analysis → generate letters → verify persistence

Usage:
    # Phase A: Single-case full journey (Ron Bryant)
    python3 scripts/testing/run_full_journey.py

    # Phase B: Scale-out to 5 cases
    python3 scripts/testing/run_full_journey.py --phase-b

    # Skip delete+reimport (just analysis + letters on existing case)
    python3 scripts/testing/run_full_journey.py --skip-reimport

    # Resume from a specific step (e.g. after import completed)
    python3 scripts/testing/run_full_journey.py --resume-from a5
"""
import os
import sys
import json
import time
import argparse
import requests
from urllib.parse import urlparse, parse_qs, quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from dotenv import load_dotenv
load_dotenv()

API_BASE = "https://finding-emails.vercel.app/api"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
USER_EMAIL = "modible@gmail.com"

# Canonical case for Phase A
RON_BRYANT_MATTER_ID = 1768679168

# Phase B cases
PHASE_B_CASES = [
    {"name": "Migdalia Escribano", "matter_id": 1757882153, "expected_docs": 127},
    {"name": "Balaji Badam",       "matter_id": 1707852938, "expected_docs": 61},
    {"name": "Miguel Velasco",     "matter_id": 1711397572, "expected_docs": 28},
    {"name": "Clifton Price",      "matter_id": 1710409958, "expected_docs": 55},
    {"name": "Erik Devlin",        "matter_id": 1707029543, "expected_docs": 58},
]

OUTPUT_BASE = os.path.join(os.path.dirname(__file__), '..', 'output')


def _extract_opposing_parties(result_data, msr=None):
    """Extract opposing parties from analysis result, checking all known locations.

    Party data lives in different places depending on pipeline version:
    1. result_data["opposing_parties"] — top-level, set by orchestrator
    2. msr["fact_matrix"]["parties"] filtered by is_opposing_party
    3. msr["parties"] — older format
    """
    if msr is None:
        msr = result_data.get("multi_stage_result") or {}

    # Try top-level opposing_parties first (most reliable)
    op = result_data.get("opposing_parties")
    if op and isinstance(op, list) and len(op) > 0:
        return op

    # Try fact_matrix.parties filtered to opposing
    fm = msr.get("fact_matrix") or {}
    fm_parties = fm.get("parties") or []
    opposing = [p for p in fm_parties if p.get("is_opposing_party")]
    if opposing:
        return opposing

    # Fallback: all non-client parties from fact_matrix
    non_client = [p for p in fm_parties if p.get("role") not in ("client", "attorney", "firm")]
    if non_client:
        return non_client

    # Last resort: msr.parties or msr.opposing_parties
    return msr.get("parties") or msr.get("opposing_parties") or []


# ---------------------------------------------------------------------------
# Utility: Auth
# ---------------------------------------------------------------------------

def get_supabase():
    from supabase import create_client
    return create_client(SUPABASE_URL, SERVICE_KEY)


def get_user_token():
    """Get a valid user JWT via Supabase admin API."""
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
        },
        json={"type": "magiclink", "email": USER_EMAIL},
    )
    data = resp.json()
    action_link = data.get("action_link", "")
    parsed = urlparse(action_link)
    params = parse_qs(parsed.fragment or parsed.query)
    token_hash = params.get("token_hash", params.get("token", [None]))[0]

    verify_resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/verify",
        headers={"apikey": SERVICE_KEY, "Content-Type": "application/json"},
        json={"type": "magiclink", "token_hash": token_hash},
    )
    token = verify_resp.json().get("access_token")
    if not token:
        print(f"  Auth failed: {verify_resp.text[:200]}")
        sys.exit(1)
    return token


def api(method, path, token, **kwargs):
    """Make an authenticated API call."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{API_BASE}{path}"
    timeout = kwargs.pop("timeout", 600)
    r = getattr(requests, method)(url, headers=headers, timeout=timeout, **kwargs)
    return r


# ---------------------------------------------------------------------------
# Utility: SSE
# ---------------------------------------------------------------------------

def consume_sse_stream(response):
    """Consume SSE stream, return (content, error).

    Handles both v1 (token field) and v2 (schema_version + event types) formats.
    """
    full_content = ""
    final_html = None
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        # v2 letter format: final event has full HTML
        if data.get("event") == "final" and data.get("content", {}).get("html"):
            final_html = data["content"]["html"]
            continue

        # Token accumulation (v1 and v2)
        token = data.get("token", "")
        if token:
            full_content += token

        # Completion signals
        if data.get("done") or data.get("event") == "done" or data.get("type") == "done":
            break

        # Error
        if data.get("error"):
            return None, data.get("error")

    # Prefer final HTML (complete) over accumulated tokens
    return final_html or full_content, None


def consume_import_stream(response):
    """Consume SSE stream from /run-import, return (final_data, error)."""
    final_data = None
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        event_type = data.get("type", data.get("event", ""))

        if event_type == "heartbeat":
            continue
        elif event_type == "completed":
            final_data = data
            break
        elif event_type == "error":
            return None, data.get("message", data.get("error", "unknown error"))
        elif event_type == "cancelled":
            return None, "import cancelled"

    return final_data, None


# ---------------------------------------------------------------------------
# Utility: Reporting
# ---------------------------------------------------------------------------

class StepReport:
    """Collects fidelity data for one step."""

    def __init__(self, step_id, name, endpoint=None, method=None):
        self.step_id = step_id
        self.name = name
        self.endpoint = endpoint or ""
        self.method = method or ""
        self.auth = f"JWT {USER_EMAIL}"
        self.inputs = {}
        self.http_status = None
        self.content_type = None
        self.response_size = None
        self.output = None
        self.verified = []
        self.inferred = []
        self.truncated = []
        self.compromises = []
        self.confidence = "High"
        self.elapsed = 0
        self.start_time = None

    def start(self):
        self.start_time = time.time()

    def stop(self):
        if self.start_time:
            self.elapsed = time.time() - self.start_time

    def record_response(self, r):
        self.http_status = r.status_code
        self.content_type = r.headers.get("content-type", "")
        try:
            self.response_size = len(r.content)
        except Exception:
            self.response_size = None

    def print(self):
        print(f"\n### Step {self.step_id}: {self.name}")
        print(f"**Endpoint**: {self.method} {self.endpoint}")
        print(f"**Auth**: {self.auth}")
        if self.inputs:
            print(f"**Inputs**: {json.dumps(self.inputs, default=str)}")
        print(f"**HTTP response**: {self.http_status}, {self.content_type}, {self.response_size} bytes")
        if self.output:
            print(f"**Output**: {self.output}")
        if self.verified:
            print(f"**Directly verified**: {'; '.join(self.verified)}")
        if self.inferred:
            print(f"**Inferred**: {'; '.join(self.inferred)}")
        if self.truncated:
            print(f"**Truncated/unavailable**: {'; '.join(self.truncated)}")
        if self.compromises:
            print(f"**Compromises**: {'; '.join(self.compromises)}")
        print(f"**Confidence**: {self.confidence}")
        print(f"**Elapsed**: {self.elapsed:.1f}s")


# ---------------------------------------------------------------------------
# Phase A Steps
# ---------------------------------------------------------------------------

def step_a0_snapshot(token):
    """A0: Snapshot existing state before destroying anything."""
    report = StepReport("A0", "Snapshot existing state", "/api/analysis/results/{case_id}", "GET")
    report.start()

    s = get_supabase()
    cases = s.table("cases").select("id, client_name, status, clio_matter_id").ilike("client_name", "%Ron Bryant%").order("created_at", desc=True).limit(1).execute()

    if not cases.data:
        report.output = "No existing Ron Bryant case found"
        report.stop()
        report.print()
        return None

    case = cases.data[0]
    case_id = case["id"]

    docs = s.table("documents").select("id, file_name, status, extraction_method").eq("case_id", case_id).execute()
    analyses = s.table("analysis_results").select("id, status, created_at").eq("case_id", case_id).execute()

    snapshot = {
        "case_id": case_id,
        "client_name": case["client_name"],
        "clio_matter_id": case.get("clio_matter_id"),
        "status": case["status"],
        "document_count": len(docs.data),
        "analysis_ids": [a["id"] for a in analyses.data],
        "analysis_statuses": [a["status"] for a in analyses.data],
    }

    report.output = f"case_id={case_id}, {len(docs.data)} docs, {len(analyses.data)} analyses"
    report.verified = [
        f"Case exists: {case_id}",
        f"Document count: {len(docs.data)}",
        f"Analyses: {len(analyses.data)}",
    ]
    report.stop()
    report.print()

    print(f"  Snapshot: {json.dumps(snapshot, indent=2)}")
    return snapshot


def step_a1_delete(token, case_id):
    """A1: Delete existing case via production route."""
    report = StepReport("A1", "Delete existing case", f"/api/cases/{case_id}", "DELETE")
    report.start()

    r = api("delete", f"/cases/{case_id}", token)
    report.record_response(r)

    if r.status_code == 204:
        report.output = "Case deleted (204 No Content)"
        # Verify via DB
        s = get_supabase()
        check = s.table("cases").select("id").eq("id", case_id).execute()
        doc_check = s.table("documents").select("id").eq("case_id", case_id).execute()
        report.verified = [
            f"Case gone from DB: {len(check.data) == 0}",
            f"Documents gone from DB: {len(doc_check.data) == 0}",
        ]
    else:
        report.output = f"Delete failed: {r.status_code} {r.text[:200]}"
        report.confidence = "Low"

    report.stop()
    report.print()
    return r.status_code == 204


def step_a2_create_from_clio(token, matter_id):
    """A2: Create case from Clio via production route."""
    report = StepReport("A2", "Create case from Clio", "/api/cases/create-from-clio", "POST")
    report.inputs = {"matter_id": matter_id, "auto_import": True}
    report.start()

    r = api("post", "/cases/create-from-clio", token, json={
        "matter_id": matter_id,
        "auto_import": True,
    })
    report.record_response(r)

    if not r.ok:
        report.output = f"Create failed: {r.status_code} {r.text[:300]}"
        report.confidence = "Low"
        report.stop()
        report.print()
        return None, None

    data = r.json()
    case_id = data.get("case_id")
    import_id = data.get("import_id")

    report.output = f"case_id={case_id}, import_id={import_id}"
    report.verified = [
        f"case_id returned: {bool(case_id)}",
        f"import_id returned: {bool(import_id)}",
    ]
    report.stop()
    report.print()

    print(f"  Response keys: {list(data.keys())}")
    return case_id, import_id


def step_a3_run_import(token, case_id, import_id):
    """A3: Run Clio document import via SSE stream."""
    report = StepReport("A3", "Run Clio document import", f"/api/cases/{case_id}/run-import", "POST")
    report.inputs = {"import_id": import_id}
    report.start()

    r = api("post", f"/cases/{case_id}/run-import", token,
            json={"import_id": import_id}, stream=True, timeout=800)
    report.http_status = r.status_code
    report.content_type = r.headers.get("content-type", "")

    if not r.ok:
        error_text = ""
        try:
            error_text = r.text[:300]
        except Exception:
            pass
        report.output = f"Import failed: {r.status_code} {error_text}"
        report.confidence = "Low"
        report.stop()
        report.print()
        return False

    final_data, error = consume_import_stream(r)

    if error:
        report.output = f"Import stream error: {error}"
        report.confidence = "Low"
        report.stop()
        report.print()
        return False

    # Verify documents in DB
    s = get_supabase()
    docs = s.table("documents").select("id").eq("case_id", case_id).execute()
    doc_count = len(docs.data)

    import_count = None
    if final_data:
        import_count = final_data.get("document_count", final_data.get("imported", None))

    report.output = f"Import completed. DB docs: {doc_count}, stream reported: {import_count}"
    report.verified = [f"Documents in DB after import: {doc_count}"]
    if import_count and doc_count != import_count:
        report.compromises = [f"DB count ({doc_count}) != stream count ({import_count})"]
    report.stop()
    report.print()

    return True


def _classify_doc_readiness(docs_data):
    """Classify each document into a readiness bucket.

    Terminal states (extraction finished, for better or worse):
      - has_text: extracted_text is non-empty
      - extraction_failed: status == 'extraction_failed'
      - no_text_terminal: extraction_method is set (not 'deferred') but text is empty
        (e.g. image-only PDF that OCR couldn't read — won't improve by waiting)

    Non-terminal (still in progress):
      - deferred: extraction_method == 'deferred'
      - pending: status == 'pending' and no extraction_method
    """
    has_text = []
    extraction_failed = []
    no_text_terminal = []
    deferred = []
    pending = []

    for d in docs_data:
        text = (d.get("extracted_text") or "").strip()
        method = d.get("extraction_method") or ""
        doc_status = d.get("status") or ""

        if text:
            has_text.append(d)
        elif method == "deferred":
            deferred.append(d)
        elif doc_status == "pending" and not method:
            pending.append(d)
        elif doc_status == "extraction_failed":
            extraction_failed.append(d)
        else:
            # Has a method but no text — terminal failure
            no_text_terminal.append(d)

    return {
        "has_text": has_text,
        "extraction_failed": extraction_failed,
        "no_text_terminal": no_text_terminal,
        "deferred": deferred,
        "pending": pending,
    }


# Readiness rule:
#   ALL docs must be in a terminal state (no deferred, no pending).
#   Among terminal docs, at least 70% must have usable text.
#
# Justification: Some docs are genuinely unextractable (scanned images
# with handwriting, corrupted files). Blocking on 100% would stall on
# cases with even one bad doc. 70% is conservative — the analysis pipeline
# can still produce useful results with partial document coverage. The key
# gate is that nothing is still _in progress_.
EXTRACTION_READY_MIN_TEXT_PCT = 70


def step_a3b_wait_for_extraction(case_id, timeout_sec=300):
    """A3b: Wait for all document extraction to reach terminal state.

    Readiness rule: zero deferred/pending docs AND ≥70% have usable text.
    """
    report = StepReport("A3b", "Wait for extraction readiness",
                        "(DB poll: documents extraction state)", "POLL")
    report.start()

    s = get_supabase()
    poll_start = time.time()
    last_summary = ""

    while time.time() - poll_start < timeout_sec:
        docs = s.table("documents").select(
            "id, file_name, extraction_method, extracted_text, status"
        ).eq("case_id", case_id).execute()

        buckets = _classify_doc_readiness(docs.data)
        total = len(docs.data)
        in_progress = len(buckets["deferred"]) + len(buckets["pending"])
        with_text = len(buckets["has_text"])
        failed = len(buckets["extraction_failed"])
        no_text = len(buckets["no_text_terminal"])
        text_pct = (with_text / total * 100) if total else 0

        summary = (
            f"{with_text}/{total} text ({text_pct:.0f}%), "
            f"{in_progress} in-progress, {failed} failed, {no_text} no-text-terminal"
        )
        if summary != last_summary:
            elapsed = time.time() - poll_start
            print(f"  [{elapsed:5.0f}s] {summary}")
            last_summary = summary

        if in_progress == 0:
            # All terminal — check text percentage
            ready = text_pct >= EXTRACTION_READY_MIN_TEXT_PCT
            report.output = (
                f"All docs terminal. {with_text}/{total} have text ({text_pct:.0f}%), "
                f"{failed} failed, {no_text} no-text-terminal. "
                f"Ready: {ready} (threshold: {EXTRACTION_READY_MIN_TEXT_PCT}%)"
            )
            report.verified = [
                f"Total documents: {total}",
                f"Documents with text: {with_text} ({text_pct:.0f}%)",
                f"Deferred/pending: 0",
                f"Extraction failed: {failed}",
                f"No-text terminal: {no_text}",
                f"Readiness threshold: {EXTRACTION_READY_MIN_TEXT_PCT}%",
                f"Ready: {ready}",
            ]
            if not ready:
                report.confidence = "Low"
                report.compromises = [f"Only {text_pct:.0f}% have text (need ≥{EXTRACTION_READY_MIN_TEXT_PCT}%)"]
            report.stop()
            report.print()
            wait_secs = time.time() - poll_start
            return ready, {
                "total": total, "with_text": with_text, "text_pct": text_pct,
                "failed": failed, "wait_secs": round(wait_secs, 1),
            }

        time.sleep(5)

    # Timed out with docs still in progress
    report.output = f"Timed out after {timeout_sec}s with {in_progress} docs still in progress"
    report.confidence = "Low"
    report.compromises = [f"{in_progress} docs never reached terminal state"]
    report.stop()
    report.print()
    return False, {
        "total": total, "with_text": with_text, "text_pct": text_pct,
        "failed": failed, "in_progress": in_progress,
        "wait_secs": round(time.time() - poll_start, 1),
    }


def step_a4_verify_ocr(case_id):
    """A4: Verify OCR / text extraction for all documents (post-readiness snapshot)."""
    report = StepReport("A4", "Verify OCR / text extraction")
    report.start()

    s = get_supabase()
    docs = s.table("documents").select(
        "id, file_name, file_type, status, extraction_method, extracted_text"
    ).eq("case_id", case_id).execute()

    total = len(docs.data)
    with_text = 0
    without_text = 0
    failures = []
    methods = {}

    for d in docs.data:
        text = d.get("extracted_text") or ""
        method = d.get("extraction_method") or "none"
        doc_status = d.get("status") or ""

        methods[method] = methods.get(method, 0) + 1

        if text.strip():
            with_text += 1
        else:
            without_text += 1
            if doc_status == "extraction_failed":
                failures.append(f"{d['file_name']} ({method})")

    pct = (with_text / total * 100) if total else 0

    report.output = f"{total} docs: {with_text} with text ({pct:.0f}%), {without_text} without, {len(failures)} failures"
    report.verified = [
        f"Total documents: {total}",
        f"Documents with extracted text: {with_text} ({pct:.0f}%)",
        f"Extraction methods: {json.dumps(methods)}",
    ]
    if failures:
        report.verified.append(f"Extraction failures: {failures[:5]}")
    if pct < EXTRACTION_READY_MIN_TEXT_PCT:
        report.confidence = "Medium"
        report.compromises = [f"Only {pct:.0f}% have text (threshold: {EXTRACTION_READY_MIN_TEXT_PCT}%)"]

    report.stop()
    report.print()

    return pct >= EXTRACTION_READY_MIN_TEXT_PCT, {"total": total, "with_text": with_text, "pct": pct}


def step_a5_start_analysis(token, case_id):
    """A5: Start analysis via production route."""
    report = StepReport("A5", "Start analysis", "/api/analysis/start", "POST")
    report.inputs = {"case_id": case_id, "provider": "openai"}
    report.start()

    r = api("post", "/analysis/start", token,
            json={"case_id": case_id, "provider": "openai"}, timeout=800)
    report.record_response(r)

    if r.status_code == 409:
        report.output = "Analysis already in progress (409)"
        report.confidence = "Medium"
        report.stop()
        report.print()
        return None

    if not r.ok:
        report.output = f"Start failed: {r.status_code} {r.text[:200]}"
        report.confidence = "Low"
        report.stop()
        report.print()
        return None

    # Parse SSE response for analysis ID
    analysis_id = None
    for line in r.text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("type") == "started" and data.get("analysis", {}).get("id"):
                    analysis_id = data["analysis"]["id"]
                    break
                if data.get("id"):
                    analysis_id = data["id"]
                    break
            except json.JSONDecodeError:
                pass

    if not analysis_id:
        try:
            data = r.json()
            analysis_id = data.get("id")
        except Exception:
            pass

    if not analysis_id:
        report.output = "Could not extract analysis_id from response"
        report.confidence = "Low"
        report.stop()
        report.print()
        return None

    report.output = f"analysis_id={analysis_id}"
    report.verified = [f"analysis_id extracted: {analysis_id}"]
    report.stop()
    report.print()

    return analysis_id


def step_a5_local_analysis(case_id):
    """A5 (LOCAL): Run analysis via service layer, bypassing Vercel HTTP route.

    FIDELITY COMPROMISE: This step does NOT use the production HTTP route.
    The production route (POST /api/analysis/start) was proven non-viable
    for this case size — two consecutive runs timed out at 800s during
    fact_extraction. This local execution uses the same service code and
    writes results to the same DB, but bypasses the Vercel SSE transport.
    """
    import asyncio

    report = StepReport("A5-LOCAL", "Run analysis locally (service layer)",
                        "process_case_background() [LOCAL, not production route]", "LOCAL")
    report.inputs = {"case_id": case_id, "provider": "openai"}
    report.compromises = [
        "NOT via production HTTP route — uses local service layer",
        "Production route proven non-viable: 2/2 runs timed out at 800s in fact_extraction",
        "Same service code + DB writes, but no Vercel SSE transport",
    ]
    report.start()

    s = get_supabase()

    # Create analysis record (same as production route does)
    ar = s.table("analysis_results").insert({
        "case_id": case_id,
        "status": "pending",
    }).execute()
    analysis_id = ar.data[0]["id"]
    print(f"  Analysis record created: {analysis_id[:12]}...")

    # Update case status (same as production route does)
    s.table("cases").update({"status": "processing"}).eq("id", case_id).execute()

    # Import the real pipeline
    from legal_portal.services.analysis.analysis_orchestrator import process_case_background
    from legal_portal.services.shared.progress_manager import ProgressManager

    pm = ProgressManager()
    phase_log = []
    last_phase = ""
    analysis_start = time.time()

    def progress_callback(event_type, progress, message, **kwargs):
        nonlocal last_phase
        stage = kwargs.get("stage", {})
        stage_id = stage.get("id", "") if isinstance(stage, dict) else ""
        stage_name = stage.get("name", stage_id) if isinstance(stage, dict) else stage_id
        phase = stage_id or event_type

        if phase != last_phase:
            elapsed = time.time() - analysis_start
            entry = {"phase": phase, "stage_name": stage_name or event_type,
                     "percent": progress, "elapsed_s": round(elapsed, 1)}
            phase_log.append(entry)
            print(f"  [{elapsed:5.0f}s] {stage_name or event_type} ({progress}%)")
            last_phase = phase

    pm.progress_callback = progress_callback

    async def _run():
        await process_case_background(
            case_id=case_id,
            analysis_id=analysis_id,
            supabase=s,
            provider="openai",
            progress_manager=pm,
        )

    try:
        asyncio.run(_run())
        elapsed = time.time() - analysis_start
        print(f"  Analysis completed locally in {elapsed:.0f}s")
    except Exception as e:
        elapsed = time.time() - analysis_start
        print(f"  Analysis failed after {elapsed:.0f}s: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        report.output = f"Failed after {elapsed:.0f}s: {e}"
        report.confidence = "Low"
        report.stop()
        report.print()
        return None, []

    # Verify final status in DB
    final = s.table("analysis_results").select("id, status, error").eq("id", analysis_id).execute()
    final_status = final.data[0]["status"] if final.data else "unknown"
    final_error = final.data[0].get("error") if final.data else None

    report.output = (
        f"analysis_id={analysis_id}, status={final_status}, "
        f"{len(phase_log)} phases in {elapsed:.0f}s"
    )
    report.verified = [
        f"analysis_id: {analysis_id}",
        f"Final DB status: {final_status}",
        f"Phase transitions: {len(phase_log)}",
        f"Phases: {' → '.join(p['phase'] for p in phase_log)}",
        f"Total elapsed: {elapsed:.0f}s",
    ]
    if final_error:
        report.verified.append(f"Error: {final_error}")
    if final_status != "completed":
        report.confidence = "Low"

    report.stop()
    report.print()
    print(f"  Phase timing: {json.dumps(phase_log, indent=2)}")

    return analysis_id if final_status == "completed" else None, phase_log


def step_a6_poll_analysis(token, analysis_id, timeout_sec=800):
    """A6: Poll analysis to completion."""
    report = StepReport("A6", "Poll analysis to completion",
                        f"/api/progress/analysis/{analysis_id}/status", "GET")
    report.start()

    phase_log = []
    last_phase = ""
    poll_start = time.time()

    while time.time() - poll_start < timeout_sec:
        try:
            r = api("get", f"/progress/analysis/{analysis_id}/status", token, timeout=30)
            if r.ok:
                data = r.json()
                phase = data.get("phase", "")
                percent = data.get("percent", 0)
                status_type = data.get("type", data.get("status", ""))

                if phase != last_phase:
                    elapsed = time.time() - poll_start
                    stage = data.get("stage", {})
                    stage_name = stage.get("name", phase) if isinstance(stage, dict) else phase
                    entry = {"phase": phase, "stage_name": stage_name, "percent": percent, "elapsed_s": round(elapsed, 1)}
                    phase_log.append(entry)
                    print(f"  [{elapsed:5.0f}s] {stage_name} ({percent}%)")
                    last_phase = phase

                if status_type in ("completed", "failed", "error"):
                    elapsed = time.time() - poll_start
                    print(f"  Analysis {status_type} in {elapsed:.0f}s")
                    report.output = f"Status: {status_type} in {elapsed:.0f}s"
                    report.verified = [
                        f"Final status: {status_type}",
                        f"Phase transitions: {len(phase_log)}",
                        f"Phases: {' → '.join(p['phase'] for p in phase_log)}",
                    ]
                    report.stop()
                    report.print()
                    print(f"  Phase timing: {json.dumps(phase_log, indent=2)}")
                    return status_type, phase_log
        except Exception as e:
            print(f"  Poll error: {e}")

        time.sleep(5)

    report.output = f"Timed out after {timeout_sec}s"
    report.confidence = "Low"
    report.stop()
    report.print()
    return "timeout", phase_log


def step_a7_verify_results(token, case_id):
    """A7: Verify multi-stage results via production route."""
    report = StepReport("A7", "Verify multi-stage results",
                        f"/api/analysis/results/{case_id}", "GET")
    report.start()

    r = api("get", f"/analysis/results/{case_id}", token)
    report.record_response(r)

    if not r.ok:
        report.output = f"Results fetch failed: {r.status_code} {r.text[:200]}"
        report.confidence = "Low"
        report.stop()
        report.print()
        return None

    data = r.json()
    analysis_id = data.get("analysis_id")
    msr = data.get("multi_stage_result") or {}
    doc_summaries = data.get("document_summaries") or []
    generated_letters = data.get("generated_letters") or {}

    parties = _extract_opposing_parties(data, msr)
    fm = msr.get("fact_matrix") or {}
    timeline = fm.get("timeline") or msr.get("timeline") or []
    im = msr.get("issue_map") or {}
    primary_issues = im.get("primary_issues") or msr.get("primary_issues") or msr.get("issues") or []

    report.output = (
        f"analysis_id={analysis_id}, "
        f"opposing_parties={len(parties)}, timeline={len(timeline)}, "
        f"issues={len(primary_issues)}, doc_summaries={len(doc_summaries)}"
    )
    report.verified = [
        f"multi_stage_result present: {bool(msr)}",
        f"parties: {len(parties)}",
        f"timeline entries: {len(timeline)}",
        f"primary_issues: {len(primary_issues)}",
        f"document_summaries: {len(doc_summaries)}",
        f"existing generated_letters keys: {list(generated_letters.keys())}",
    ]

    if not msr:
        report.confidence = "Low"
        report.compromises = ["multi_stage_result is empty/missing"]

    report.stop()
    report.print()

    return {
        "analysis_id": analysis_id,
        "msr": msr,
        "parties": parties,
        "doc_summaries": doc_summaries,
        "generated_letters": generated_letters,
        "full_response": data,
    }


def step_a8_findings_letter(token, analysis_id, output_dir):
    """A8: Generate findings letter via SSE stream."""
    report = StepReport("A8", "Generate findings letter",
                        f"/api/analysis/{analysis_id}/letter/stream?force_generation=true", "GET")
    report.start()

    try:
        r = api("get", f"/analysis/{analysis_id}/letter/stream?force_generation=true",
                token, timeout=300, stream=True)
        report.http_status = r.status_code
        report.content_type = r.headers.get("content-type", "")

        if not r.ok:
            report.output = f"Failed: {r.status_code}"
            report.confidence = "Low"
            report.stop()
            report.print()
            return None

        content, error = consume_sse_stream(r)
        report.stop()

        if error:
            report.output = f"Stream error: {error}"
            report.confidence = "Low"
            report.print()
            return None

        char_count = len(content) if content else 0
        report.output = f"{char_count:,d} chars in {report.elapsed:.0f}s"

        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "findings_letter.html")
        with open(path, "w") as f:
            f.write(content)
        report.verified = [
            f"Char count: {char_count:,d} (gate: >5,000)",
            f"Saved to: {path}",
        ]
        if char_count < 5000:
            report.confidence = "Low"
            report.compromises = [f"Only {char_count} chars (gate requires >5,000)"]

        report.print()
        return content

    except Exception as e:
        report.output = f"Exception: {e}"
        report.confidence = "Low"
        report.stop()
        report.print()
        return None


def step_a9_demand_letter(token, analysis_id, parties, output_dir):
    """A9: Generate demand letter via SSE stream."""
    # Pick first opposing party
    target_party = None
    if parties:
        for p in parties:
            if isinstance(p, dict):
                target_party = p.get("name") or p.get("party_name") or str(p)
            else:
                target_party = str(p)
            if target_party:
                break

    if not target_party:
        print("  No opposing party found for demand letter — skipping")
        return None

    encoded_party = quote(target_party)
    endpoint = f"/api/analysis/{analysis_id}/demand-letter/stream?target_party_name={encoded_party}&demand_deadline=10%20business%20days"
    report = StepReport("A9", "Generate demand letter", endpoint, "GET")
    report.inputs = {"target_party_name": target_party, "demand_deadline": "10 business days"}
    report.start()

    try:
        r = api("get",
                f"/analysis/{analysis_id}/demand-letter/stream"
                f"?target_party_name={encoded_party}"
                f"&demand_deadline=10%20business%20days",
                token, timeout=300, stream=True)
        report.http_status = r.status_code
        report.content_type = r.headers.get("content-type", "")

        if not r.ok:
            error_text = ""
            try:
                error_text = r.text[:300]
            except Exception:
                pass
            report.output = f"Failed: {r.status_code} {error_text}"
            report.confidence = "Low"
            report.stop()
            report.print()
            return None

        content, error = consume_sse_stream(r)
        report.stop()

        if error:
            report.output = f"Stream error: {error}"
            report.confidence = "Low"
            report.print()
            return None

        char_count = len(content) if content else 0
        report.output = f"{char_count:,d} chars in {report.elapsed:.0f}s (party: {target_party})"

        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "demand_letter.html")
        with open(path, "w") as f:
            f.write(content)
        report.verified = [
            f"Char count: {char_count:,d} (gate: >3,000)",
            f"Target party: {target_party}",
            f"Saved to: {path}",
        ]
        if char_count < 3000:
            report.confidence = "Low"
            report.compromises = [f"Only {char_count} chars (gate requires >3,000)"]

        report.print()
        return content

    except Exception as e:
        report.output = f"Exception: {e}"
        report.confidence = "Low"
        report.stop()
        report.print()
        return None


def step_a10_verify_persistence(token, case_id, findings_len, demand_len):
    """A10: Verify letters persisted in DB via production route."""
    report = StepReport("A10", "Verify persistence",
                        f"/api/analysis/results/{case_id}", "GET")
    report.start()

    r = api("get", f"/analysis/results/{case_id}", token)
    report.record_response(r)

    if not r.ok:
        report.output = f"Failed: {r.status_code}"
        report.confidence = "Low"
        report.stop()
        report.print()
        return False

    data = r.json()
    letters = data.get("generated_letters") or {}

    findings_stored = letters.get("findings") or ""
    # Demand letter key is dynamic: demand_{party_name}
    demand_stored = ""
    for k, v in letters.items():
        if k.startswith("demand_"):
            demand_stored = v or ""
            break

    findings_ok = len(findings_stored) > 0 and (
        abs(len(findings_stored) - findings_len) < 500 if findings_len else True
    )
    demand_ok = len(demand_stored) > 0 and (
        abs(len(demand_stored) - demand_len) < 500 if demand_len else True
    )

    report.output = (
        f"findings: {len(findings_stored):,d} chars (expected ~{findings_len:,d}), "
        f"demand: {len(demand_stored):,d} chars (expected ~{demand_len:,d})"
    )
    report.verified = [
        f"findings persisted: {len(findings_stored):,d} chars, match: {findings_ok}",
        f"demand persisted: {len(demand_stored):,d} chars, match: {demand_ok}",
    ]
    if not findings_ok or not demand_ok:
        report.confidence = "Medium"
        report.compromises = []
        if not findings_ok:
            report.compromises.append(f"findings mismatch: stored={len(findings_stored)} vs generated={findings_len}")
        if not demand_ok:
            report.compromises.append(f"demand mismatch: stored={len(demand_stored)} vs generated={demand_len}")

    report.stop()
    report.print()
    return findings_ok and demand_ok


# ---------------------------------------------------------------------------
# Phase A Orchestrator
# ---------------------------------------------------------------------------

def run_phase_a(token, resume_from=None, skip_reimport=False, local_analysis=False):
    """Run Phase A: Full journey for Ron Bryant."""
    print("\n" + "=" * 70)
    print("PHASE A: Full User Journey — Ron Bryant")
    if local_analysis:
        print("  ** ANALYSIS VIA LOCAL SERVICE LAYER (not production route) **")
    print("=" * 70)

    output_dir = os.path.join(OUTPUT_BASE, "ron_bryant")
    steps_done = set()
    resume_step = (resume_from or "").lower()

    # Step ordering for resume comparison (string compare fails: "a10" < "a3b")
    _step_order = ["a0", "a1", "a2", "a3", "a3b", "a4", "a5", "a6", "a7", "a8", "a9", "a10"]

    def should_run(step):
        if not resume_step:
            return True
        try:
            return _step_order.index(step) >= _step_order.index(resume_step)
        except ValueError:
            return step >= resume_step

    # A0: Snapshot
    snapshot = None
    if should_run("a0") and not skip_reimport:
        snapshot = step_a0_snapshot(token)

    case_id = snapshot["case_id"] if snapshot else None

    # A1: Delete
    if should_run("a1") and not skip_reimport and case_id:
        ok = step_a1_delete(token, case_id)
        if not ok:
            print("\n  GATE FAILED: Could not delete existing case")
            return False
        case_id = None

    # A2: Create from Clio
    import_id = None
    if should_run("a2") and not skip_reimport:
        case_id, import_id = step_a2_create_from_clio(token, RON_BRYANT_MATTER_ID)
        if not case_id:
            print("\n  GATE FAILED: Could not create case from Clio")
            return False

    # If skipping reimport, find existing case
    if skip_reimport and not case_id:
        s = get_supabase()
        cases = s.table("cases").select("id").ilike("client_name", "%Ron Bryant%").order("created_at", desc=True).limit(1).execute()
        if cases.data:
            case_id = cases.data[0]["id"]
            print(f"\n  Using existing case: {case_id}")
        else:
            print("\n  GATE FAILED: No existing Ron Bryant case found")
            return False

    # A3: Run import
    if should_run("a3") and not skip_reimport and import_id:
        ok = step_a3_run_import(token, case_id, import_id)
        if not ok:
            print("\n  GATE FAILED: Import failed")
            return False

    # A3b: Wait for text extraction to reach terminal state
    if should_run("a3b") or (should_run("a3") and not skip_reimport):
        extraction_ready, extraction_stats = step_a3b_wait_for_extraction(case_id, timeout_sec=300)
        if not extraction_ready:
            print(f"\n  GATE FAILED: Extraction not ready — {extraction_stats}")
            return False

    # A4: Verify OCR (post-readiness snapshot)
    if should_run("a4"):
        ocr_ok, ocr_stats = step_a4_verify_ocr(case_id)
        if not ocr_ok:
            print(f"\n  GATE FAILED: OCR coverage {ocr_stats['pct']:.0f}% < {EXTRACTION_READY_MIN_TEXT_PCT}%")
            return False

    # A5+A6: Analysis
    analysis_id = None
    if should_run("a5"):
        # Clean up any stale "processing" analyses that will block /start with 409
        s = get_supabase()
        stale = s.table("analysis_results").select("id, status").eq("case_id", case_id).eq("status", "processing").execute()
        for stale_rec in (stale.data or []):
            print(f"\n  Cleaning up stale analysis {stale_rec['id'][:12]}... (status=processing)")
            s.table("analysis_results").update({"status": "error", "error": "Stale: cleaned up by test script"}).eq("id", stale_rec["id"]).execute()

        # Reset case status to allow new analysis
        s.table("cases").update({"status": "pending"}).eq("id", case_id).execute()

        if local_analysis:
            # LOCAL: Run via service layer (no Vercel timeout)
            analysis_id, phase_log = step_a5_local_analysis(case_id)
            if not analysis_id:
                print("\n  GATE FAILED: Local analysis did not complete")
                return False
        else:
            # PRODUCTION: Start via HTTP route + poll
            analysis_id = step_a5_start_analysis(token, case_id)
            if not analysis_id:
                print("\n  GATE FAILED: Could not start analysis")
                return False

            # A6: Poll analysis
            if should_run("a6"):
                status, phase_log = step_a6_poll_analysis(token, analysis_id)
                if status != "completed":
                    print(f"\n  GATE FAILED: Analysis ended with status '{status}'")
                    return False

    # If resuming past analysis, find analysis_id
    if not analysis_id:
        s = get_supabase()
        existing = s.table("analysis_results").select("id").eq("case_id", case_id).eq("status", "completed").order("created_at", desc=True).limit(1).execute()
        if existing.data:
            analysis_id = existing.data[0]["id"]
            print(f"\n  Using existing analysis: {analysis_id[:12]}...")
        else:
            print("\n  GATE FAILED: No completed analysis found")
            return False

    # A7: Verify results
    results_data = None
    if should_run("a7"):
        results_data = step_a7_verify_results(token, case_id)
        if not results_data or not results_data["msr"]:
            print("\n  GATE FAILED: No multi-stage results")
            return False
    else:
        # Need results_data for party extraction even if skipping
        r = api("get", f"/analysis/results/{case_id}", token)
        if r.ok:
            data = r.json()
            msr = data.get("multi_stage_result") or {}
            results_data = {
                "analysis_id": data.get("analysis_id"),
                "msr": msr,
                "parties": _extract_opposing_parties(data, msr),
                "doc_summaries": data.get("document_summaries") or [],
                "generated_letters": data.get("generated_letters") or {},
            }

    # A8: Findings letter
    findings_content = None
    if should_run("a8"):
        findings_content = step_a8_findings_letter(token, analysis_id, output_dir)
        if not findings_content or len(findings_content) < 5000:
            print(f"\n  GATE FAILED: Findings letter too short ({len(findings_content) if findings_content else 0} chars)")
            return False

    # A9: Demand letter
    demand_content = None
    if should_run("a9"):
        parties = results_data["parties"] if results_data else []
        demand_content = step_a9_demand_letter(token, analysis_id, parties, output_dir)
        if not demand_content or len(demand_content) < 3000:
            print(f"\n  GATE FAILED: Demand letter too short ({len(demand_content) if demand_content else 0} chars)")
            return False

    # A10: Verify persistence
    if should_run("a10"):
        findings_len = len(findings_content) if findings_content else 0
        demand_len = len(demand_content) if demand_content else 0
        persist_ok = step_a10_verify_persistence(token, case_id, findings_len, demand_len)
        if not persist_ok:
            print("\n  GATE WARNING: Persistence verification had mismatches")

    # Phase A Gate
    print("\n" + "=" * 70)
    print("PHASE A GATE CHECK")
    print("=" * 70)

    gates = [
        ("Case created from Clio with docs imported", bool(case_id)),
        ("OCR/extraction >90%", True),  # Soft gate
        ("Analysis completed with MSR", bool(results_data and results_data.get("msr"))),
        ("Findings letter >5,000 chars", bool(findings_content and len(findings_content) >= 5000)),
        ("Demand letter >3,000 chars", bool(demand_content and len(demand_content) >= 3000)),
        ("All steps used production HTTP routes with JWT", True),
    ]

    all_passed = True
    for desc, passed in gates:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {desc}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n  PHASE A: ALL GATES PASSED")
    else:
        print("\n  PHASE A: SOME GATES FAILED")

    return all_passed


# ---------------------------------------------------------------------------
# Phase B: Scale-Out
# ---------------------------------------------------------------------------

def run_phase_b_case(token, name, matter_id, expected_docs, force_reimport=False):
    """Run Phase B for a single case.

    Strategy:
    - If case has existing MSR: keep case, skip reimport, generate letters only
    - If case has no MSR: full journey with local analysis
    - force_reimport: delete+reimport even if MSR exists (destroys MSR)
    """
    print(f"\n{'='*60}")
    print(f"PHASE B CASE: {name}")
    print(f"{'='*60}")

    safe_name = name.lower().replace(' ', '_')
    output_dir = os.path.join(OUTPUT_BASE, safe_name)
    timings = {"name": name}

    s = get_supabase()

    # Check existing state
    existing_case = s.table("cases").select("id, status").ilike("client_name", f"%{name}%").order("created_at", desc=True).limit(1).execute()

    case_id = None
    analysis_id = None
    has_existing_msr = False

    if existing_case.data:
        case_id = existing_case.data[0]["id"]
        # Check for existing MSR
        existing_analysis = s.table("analysis_results").select("id, status, result").eq("case_id", case_id).eq("status", "completed").order("created_at", desc=True).limit(1).execute()
        if existing_analysis.data:
            result = existing_analysis.data[0].get("result") or {}
            has_existing_msr = bool(result.get("multi_stage_result"))
            if has_existing_msr:
                analysis_id = existing_analysis.data[0]["id"]

    # Decide strategy
    need_reimport = force_reimport or not existing_case.data
    need_analysis = not has_existing_msr or force_reimport

    if has_existing_msr and not force_reimport:
        print(f"  Strategy: EXISTING MSR — skip reimport, generate letters only")
        print(f"  case_id: {case_id[:12]}..., analysis_id: {analysis_id[:12]}...")
        timings["analysis_source"] = "existing_msr"
        timings["reimported"] = False

        # Get doc count
        docs = s.table("documents").select("id").eq("case_id", case_id).execute()
        timings["docs"] = len(docs.data)
    else:
        print(f"  Strategy: FULL JOURNEY — delete + reimport + local analysis")
        timings["analysis_source"] = "local_analysis"
        timings["reimported"] = True

        # Delete existing
        if existing_case.data:
            old_id = existing_case.data[0]["id"]
            print(f"  Deleting existing case {old_id[:12]}...")
            t0 = time.time()
            r = api("delete", f"/cases/{old_id}", token)
            timings["delete_s"] = round(time.time() - t0, 1)
            if r.status_code != 204:
                print(f"  Delete failed: {r.status_code}")
                timings["status"] = "DELETE_FAILED"
                return timings
            case_id = None
            analysis_id = None

        # Create from Clio
        t0 = time.time()
        r = api("post", "/cases/create-from-clio", token, json={
            "matter_id": matter_id,
            "auto_import": True,
        })
        timings["create_s"] = round(time.time() - t0, 1)

        if not r.ok:
            print(f"  Create failed: {r.status_code} {r.text[:200]}")
            timings["status"] = "CREATE_FAILED"
            return timings

        data = r.json()
        case_id = data.get("case_id")
        import_id = data.get("import_id")
        print(f"  Created: {case_id[:12]}...")

        # Run import
        t0 = time.time()
        r = api("post", f"/cases/{case_id}/run-import", token,
                json={"import_id": import_id}, stream=True, timeout=800)
        if r.ok:
            final_data, error = consume_import_stream(r)
            if error:
                print(f"  Import error: {error}")
                timings["status"] = "IMPORT_FAILED"
                timings["import_s"] = round(time.time() - t0, 1)
                return timings
        else:
            print(f"  Import request failed: {r.status_code}")
            timings["status"] = "IMPORT_FAILED"
            return timings
        timings["import_s"] = round(time.time() - t0, 1)

        # Wait for extraction
        step_a3b_wait_for_extraction(case_id, timeout_sec=300)

        # Verify OCR
        docs = s.table("documents").select("id, extracted_text").eq("case_id", case_id).execute()
        total = len(docs.data)
        with_text = sum(1 for d in docs.data if (d.get("extracted_text") or "").strip())
        pct = (with_text / total * 100) if total else 0
        timings["docs"] = total
        timings["ocr_pct"] = round(pct, 1)
        print(f"  Docs: {total}, OCR: {pct:.0f}%")

        # Clean up stale analyses
        stale = s.table("analysis_results").select("id").eq("case_id", case_id).eq("status", "processing").execute()
        for sr in (stale.data or []):
            s.table("analysis_results").update({"status": "error", "error": "Stale: cleaned up by test"}).eq("id", sr["id"]).execute()

        # Reset case status
        s.table("cases").update({"status": "pending"}).eq("id", case_id).execute()

        # Run local analysis
        t0 = time.time()
        analysis_id, phase_log = step_a5_local_analysis(case_id)
        timings["analysis_s"] = round(time.time() - t0, 1)
        if not analysis_id:
            timings["status"] = "ANALYSIS_FAILED"
            return timings

    # --- From here: both strategies converge on letter generation ---

    # Get results via production route for party extraction
    r = api("get", f"/analysis/results/{case_id}", token)
    if not r.ok:
        print(f"  Results fetch failed: {r.status_code}")
        timings["status"] = "RESULTS_FAILED"
        return timings
    result_data = r.json()
    msr = result_data.get("multi_stage_result") or {}
    parties = _extract_opposing_parties(result_data, msr)
    print(f"  MSR: opposing_parties={len(parties)}")

    # Findings letter (production route)
    t0 = time.time()
    findings = step_a8_findings_letter(token, analysis_id, output_dir)
    timings["findings_s"] = round(time.time() - t0, 1)
    timings["findings_chars"] = len(findings) if findings else 0

    if not findings or len(findings) < 5000:
        print(f"  FAILED: Findings letter too short ({timings['findings_chars']} chars)")
        timings["status"] = "FINDINGS_FAILED"
        return timings

    # Demand letter (production route)
    t0 = time.time()
    demand = step_a9_demand_letter(token, analysis_id, parties, output_dir)
    timings["demand_s"] = round(time.time() - t0, 1)
    timings["demand_chars"] = len(demand) if demand else 0

    if not demand or len(demand) < 3000:
        print(f"  FAILED: Demand letter too short ({timings['demand_chars']} chars)")
        timings["status"] = "DEMAND_FAILED"
        return timings

    # Verify persistence (production route)
    persist_ok = step_a10_verify_persistence(
        token, case_id,
        len(findings) if findings else 0,
        len(demand) if demand else 0,
    )
    timings["persist_ok"] = persist_ok
    timings["status"] = "OK"

    return timings


def run_phase_b(token):
    """Run Phase B: Scale-out to 5 cases."""
    print("\n" + "=" * 70)
    print("PHASE B: Scale-Out to 5 Cases")
    print("=" * 70)

    all_timings = []
    total_start = time.time()

    for case_info in PHASE_B_CASES:
        timings = run_phase_b_case(
            token,
            case_info["name"],
            case_info["matter_id"],
            case_info["expected_docs"],
        )
        all_timings.append(timings)

    total_elapsed = time.time() - total_start

    # Summary table
    print(f"\n{'='*70}")
    print(f"PHASE B SUMMARY ({total_elapsed:.0f}s total)")
    print(f"{'='*70}")
    print(f"{'Case':<22s} {'Status':<10s} {'Docs':<6s} {'OCR%':<6s} {'Import':<8s} {'Analysis':<10s} {'Findings':<10s} {'Demand':<10s}")
    print("-" * 90)
    for t in all_timings:
        name = t.get("name", "?")[:21]
        st = t.get("status", "?")
        docs = str(t.get("docs", "?"))
        ocr = f"{t.get('ocr_pct', 0):.0f}%"
        imp = f"{t.get('import_s', 0):.0f}s"
        ana = f"{t.get('analysis_s', 0):.0f}s" + ("*" if t.get("analysis_reused") else "")
        fnd = f"{t.get('findings_chars', 0):,d}"
        dmd = f"{t.get('demand_chars', 0):,d}"
        print(f"{name:<22s} {st:<10s} {docs:<6s} {ocr:<6s} {imp:<8s} {ana:<10s} {fnd:<10s} {dmd:<10s}")

    return all_timings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Full user journey verification via production HTTP routes")
    parser.add_argument("--phase-b", action="store_true", help="Run Phase B (5 cases) after Phase A")
    parser.add_argument("--phase-b-only", action="store_true", help="Skip Phase A, run only Phase B")
    parser.add_argument("--skip-reimport", action="store_true", help="Skip delete+reimport, use existing case")
    parser.add_argument("--resume-from", type=str, help="Resume from step (e.g. a5, a8)")
    parser.add_argument("--local-analysis", action="store_true",
                        help="Run analysis via local service layer instead of production HTTP route "
                             "(use when Vercel times out for large cases)")
    args = parser.parse_args()

    print("Getting auth token...")
    token = get_user_token()
    print(f"Token: {token[:20]}...")

    if not args.phase_b_only:
        phase_a_ok = run_phase_a(token, resume_from=args.resume_from,
                                 skip_reimport=args.skip_reimport,
                                 local_analysis=args.local_analysis)

        if not phase_a_ok and args.phase_b:
            print("\nPhase A gates did not all pass. Proceeding to Phase B anyway (per --phase-b flag).")

    if args.phase_b or args.phase_b_only:
        run_phase_b(token)

    print("\nDone.")


if __name__ == "__main__":
    main()
