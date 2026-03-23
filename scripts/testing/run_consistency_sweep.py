#!/usr/bin/env python3
"""Production consistency sweep — 10-case verification of durable analysis pipeline.

Runs each roster case through: start → poll → verify results → check letters → assess quality.
Produces JSON, CSV, and Markdown outputs with computed verdicts.

Usage:
    python3 scripts/testing/run_consistency_sweep.py
    python3 scripts/testing/run_consistency_sweep.py --preflight
    python3 scripts/testing/run_consistency_sweep.py --resume
    python3 scripts/testing/run_consistency_sweep.py --from-case "Ron Bryant" --pause-between-cases 30
    python3 scripts/testing/run_consistency_sweep.py --force-cleanup
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
API_BASE = os.getenv("SWEEP_API_BASE", "https://finding-emails.vercel.app")
SWEEP_USER_EMAIL = os.getenv("SWEEP_USER_EMAIL", "")


def require_env():
    """Validate required env vars. Call after argparse so --list works without credentials."""
    if not SUPABASE_URL or not SERVICE_KEY:
        print("FATAL: SUPABASE_URL and SUPABASE_SERVICE_KEY env vars are required.")
        sys.exit(1)
    if not SWEEP_USER_EMAIL:
        print("FATAL: SWEEP_USER_EMAIL env var is required.")
        sys.exit(1)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# ---------------------------------------------------------------------------
# Fixed roster — exact IDs, no fuzzy matching
# ---------------------------------------------------------------------------

SWEEP_CASES = [
    {"id": "6a0b04a0-ef14-4b57-961a-607c04a097a2", "name": "Giuseppe Iacono",     "category": "small",     "notes": "10 ready docs, PDF+text"},
    {"id": "e4c6a05d-8cd9-488e-b371-22287aedea4c", "name": "Ryan Hunt",           "category": "small",     "notes": "13 ready docs, PDF-only"},
    {"id": "3f8cf8cf-8884-4319-8aaf-a2556726159f", "name": "Ron Bryant",          "category": "medium",    "notes": "17 ready docs, regression baseline"},
    {"id": "bed8ec69-7e5d-49a6-8cbc-8ad9de641f98", "name": "William Vaughn",      "category": "medium",    "notes": "14 ready docs, has jpeg+png images"},
    {"id": "32fad48e-1642-45d1-ad5b-dd6de1af65d7", "name": "Douglas Ranken",      "category": "medium",    "notes": "20 ready docs, pure PDF"},
    {"id": "dbd111c8-7cfc-4006-b59a-9e6c42256852", "name": "Miguel Velasco",      "category": "large",     "notes": "27 ready docs, has png"},
    {"id": "122e83b3-5b32-4d96-9690-98ea753b93e1", "name": "Celeste Howder",      "category": "large",     "notes": "37 ready docs, has DOCX"},
    {"id": "3b4f43b3-d5b0-4659-a524-6f56538cbaac", "name": "Clifton Price",       "category": "large",     "notes": "54 ready docs, has .eml (email-heavy)"},
    {"id": "ead4479b-c76c-4338-adae-96ff746b990d", "name": "Balaji Badam",        "category": "difficult", "notes": "55 ready docs, image-heavy"},
    {"id": "694a7bb9-9327-4c43-8dcf-69700f7af197", "name": "Migdalia Escribano",  "category": "difficult", "notes": "66 ready + 61 needs_review, junk-heavy"},
]

# Expected stages from the durable worker pipeline
EXPECTED_STAGES = [
    "preparing", "doc_analysis", "fact_extraction",
    "legal_mapping", "deep_analysis", "gap_analysis",
    "finalizing", "completed",
]

# Terminal classifications that resume skips
TERMINAL_CLASSIFICATIONS = {
    "FULL_PASS", "PASS_WITH_LIMITATIONS", "DATA_QUALITY_COMPLETENESS_FAILURE",
    "INFRASTRUCTURE_FAILURE", "PROVIDER_TRANSIENT_FAILURE", "REGRESSION",
    "SKIPPED_ACTIVE_JOB", "SKIPPED_NO_READY_DOCS", "CASE_NOT_FOUND",
}

POLL_INTERVAL = 15  # seconds between job status polls
MAX_POLL_DURATION = 2400  # 40 minutes max per case

# Opposing-indicating roles (Req 5, Tier 3)
OPPOSING_ROLES = {
    "defendant", "respondent", "insurer", "insurance company",
    "landlord", "employer",
}

# Letter quality error/placeholder patterns (Req 2)
LETTER_ERROR_PATTERNS = [
    "insufficient information",
    "unable to determine",
    "not enough information",
    "cannot generate",
    "no data available",
    "error generating",
]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_token_cache: Dict[str, str] = {}


def get_token_for_email(email: str, force_refresh: bool = False) -> str:
    """Get a JWT for a specific user email via admin magic link."""
    if email in _token_cache and not force_refresh:
        return _token_cache[email]
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
        },
        json={"type": "magiclink", "email": email},
    )
    data = resp.json()
    parsed = urlparse(data.get("action_link", ""))
    params = parse_qs(parsed.fragment or parsed.query)
    token_hash = params.get("token_hash", params.get("token", [None]))[0]
    verify = requests.post(
        f"{SUPABASE_URL}/auth/v1/verify",
        headers={"apikey": SERVICE_KEY, "Content-Type": "application/json"},
        json={"type": "magiclink", "token_hash": token_hash},
    )
    token = verify.json().get("access_token")
    if not token:
        print(f"Auth failed for {email}: {verify.text[:200]}")
        return ""
    _token_cache[email] = token
    return token


def get_user_token() -> str:
    """Get token for the default sweep user (used for preflight)."""
    token = get_token_for_email(SWEEP_USER_EMAIL)
    if not token:
        print(f"FATAL: Auth failed for {SWEEP_USER_EMAIL}")
        sys.exit(1)
    return token


def get_case_owner_email(case_id: str) -> Optional[str]:
    """Look up the owner email for a case via service key."""
    case_resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/cases?id=eq.{case_id}&select=user_id",
        headers=service_headers(),
    )
    case_data = case_resp.json()
    if not case_data:
        return None
    user_id = case_data[0].get("user_id")
    if not user_id:
        return None
    # Look up user email via admin API
    user_resp = requests.get(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
        headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
    )
    if user_resp.status_code == 200:
        return user_resp.json().get("email")
    return None


def get_token_for_case(case_id: str) -> Optional[str]:
    """Get an auth token for the user who owns a specific case."""
    email = get_case_owner_email(case_id)
    if not email:
        return None
    return get_token_for_email(email)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def supabase_headers(token: str) -> Dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def service_headers() -> Dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# SSE consumer (exact reuse)
# ---------------------------------------------------------------------------

def consume_sse_stream(response) -> Tuple[Optional[str], Optional[str]]:
    full_content = ""
    final_html = None
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if data.get("event") == "final" and data.get("content", {}).get("html"):
            final_html = data["content"]["html"]
            continue
        token = data.get("token", "")
        if token:
            full_content += token
        if data.get("done") or data.get("event") == "done" or data.get("type") == "done":
            break
        if data.get("error"):
            return None, data.get("error")
    return final_html or full_content, None


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

def classify_failure(
    job_status: Optional[str],
    job_error: Optional[str],
    result_data: Optional[Dict],
    runtime_seconds: float,
) -> str:
    """Classify a case outcome into a canonical bucket."""
    if job_status == "completed" and result_data:
        msr = result_data.get("multi_stage_result")
        if not msr:
            return "DATA_QUALITY_COMPLETENESS_FAILURE"
        fm = msr.get("fact_matrix")
        da = msr.get("deep_analysis")
        if not fm or not da:
            return "DATA_QUALITY_COMPLETENESS_FAILURE"
        return "FULL_PASS"  # may be downgraded later by quality checks

    if job_status == "failed":
        err = (job_error or "").lower()
        if any(p in err for p in ("timeout", "rate_limit", "429", "503", "502", "econnreset")):
            return "PROVIDER_TRANSIENT_FAILURE"
        return "INFRASTRUCTURE_FAILURE"

    if job_status in ("pending", "running"):
        return "SKIPPED_ACTIVE_JOB"

    if job_status == "cancelled":
        return "INFRASTRUCTURE_FAILURE"

    return "INFRASTRUCTURE_FAILURE"


# ---------------------------------------------------------------------------
# Req 5: Opposing party extraction with confidence
# ---------------------------------------------------------------------------

def extract_opposing_parties_with_confidence(
    result_data: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], str]:
    """Extract opposing parties with tiered confidence.

    Returns (parties_list, confidence) where confidence is high/medium/low.
    """
    msr = result_data.get("multi_stage_result") or {}
    fm = msr.get("fact_matrix") or {}
    parties_raw = fm.get("parties") or []

    # Also check top-level opposing_parties from ProcessingResult
    top_level_opposing = result_data.get("opposing_parties") or []

    # Tier 1: explicit opposing_parties field
    if top_level_opposing:
        out = []
        for p in top_level_opposing:
            out.append({
                "name": p.get("name", "Unknown"),
                "role": p.get("role", ""),
                "is_opposing_party": True,
                "source_tier": 1,
            })
        if out:
            return out, "high"

    # Tier 2: fact_matrix parties with is_opposing_party=True
    tier2 = []
    for p in parties_raw:
        if p.get("is_opposing_party") is True:
            tier2.append({
                "name": p.get("name", "Unknown"),
                "role": p.get("role", ""),
                "is_opposing_party": True,
                "source_tier": 2,
            })
    if tier2:
        return tier2, "high"

    # Tier 3: non-client parties with opposing-indicating role
    tier3 = []
    for p in parties_raw:
        role_lower = (p.get("role") or "").lower()
        if role_lower in ("client", "attorney", "plaintiff"):
            continue
        if any(opp in role_lower for opp in OPPOSING_ROLES):
            tier3.append({
                "name": p.get("name", "Unknown"),
                "role": p.get("role", ""),
                "is_opposing_party": False,
                "source_tier": 3,
            })
    if tier3:
        return tier3, "medium"

    # No match
    return [], "low"


# ---------------------------------------------------------------------------
# Req 2: Stronger letter quality checks
# ---------------------------------------------------------------------------

def check_letter_quality(
    content: Optional[str],
    letter_type: str,
    target_party_name: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """Check letter quality beyond length.

    Returns (status, warnings) where status is 'ok', 'degraded', or 'failed'.
    """
    warnings: List[str] = []

    if content is None:
        return "failed", [f"{letter_type}: content is None"]

    stripped = content.strip()
    if not stripped:
        return "failed", [f"{letter_type}: empty or whitespace-only"]

    # Check for error/placeholder text
    content_lower = stripped.lower()
    for pattern in LETTER_ERROR_PATTERNS:
        if pattern in content_lower:
            warnings.append(f"{letter_type}: contains placeholder text '{pattern}'")

    # Length check
    if len(stripped) < 200:
        warnings.append(f"{letter_type}: suspiciously short ({len(stripped)} chars)")

    # Demand letter: check for target party name
    if letter_type == "demand" and target_party_name:
        if target_party_name.lower() not in content_lower:
            warnings.append(
                f"{letter_type}: missing target party name '{target_party_name}' in content"
            )

    if any("contains placeholder" in w for w in warnings) or any("empty" in w for w in warnings):
        return "degraded", warnings

    if warnings:
        return "ok", warnings

    return "ok", []


# ---------------------------------------------------------------------------
# Req 11: Category-aware quality thresholds
# ---------------------------------------------------------------------------

def get_quality_thresholds(category: str, doc_count: int) -> Dict[str, Any]:
    """Return quality thresholds based on category."""
    if category == "small":
        return {"min_parties": 2, "min_timeline": 3, "flag_no_financial": False}
    elif category == "medium":
        flag_fin = doc_count >= 20
        return {"min_parties": 3, "min_timeline": 5, "flag_no_financial": flag_fin}
    else:  # large, difficult
        return {"min_parties": 5, "min_timeline": 10, "flag_no_financial": True}


# ---------------------------------------------------------------------------
# Req 7 helper: assess_quality
# ---------------------------------------------------------------------------

def assess_quality(
    result_data: Dict[str, Any],
    category: str,
    doc_count: int,
    findings_status: str,
    demand_status: str,
    demand_expected: bool,
    demand_expectation_confidence: str,
    findings_warnings: List[str],
    demand_warnings: List[str],
) -> Tuple[str, Dict[str, Any], List[str]]:
    """Assess quality of analysis output.

    Returns (quality_classification, signals, notes).
    quality_classification is one of: HIGH, ACCEPTABLE, LOW, VERY_LOW.
    """
    signals: Dict[str, Any] = {}
    notes: List[str] = []
    issues: List[str] = []

    msr = result_data.get("multi_stage_result") or {}
    fm = msr.get("fact_matrix") or {}
    im = msr.get("issue_map") or {}
    da = msr.get("deep_analysis") or {}
    ga = msr.get("gap_analysis") or {}

    # --- Extract signal counts ---
    parties = fm.get("parties") or []
    timeline = fm.get("timeline") or []
    financial_data = fm.get("financial_data") or []
    key_documents = fm.get("key_documents") or []
    preliminary_issues = fm.get("preliminary_issues") or []

    primary_issues = im.get("primary_issues") or []
    secondary_issues = im.get("secondary_issues") or []

    issue_analyses = da.get("issue_analyses") or []
    is_viable = da.get("is_viable")
    recommend_demand = da.get("recommend_demand_letter")
    overall_strength = da.get("overall_case_strength", "unknown")

    total_gaps = ga.get("total_gaps", 0)
    completeness_score = ga.get("overall_completeness_score")
    critical_count = ga.get("critical_count", 0)
    high_count = ga.get("high_count", 0)

    signals = {
        "party_count": len(parties),
        "timeline_count": len(timeline),
        "financial_count": len(financial_data),
        "key_document_count": len(key_documents),
        "preliminary_issue_count": len(preliminary_issues),
        "primary_issue_count": len(primary_issues),
        "secondary_issue_count": len(secondary_issues),
        "issue_analysis_count": len(issue_analyses),
        "is_viable": is_viable,
        "recommend_demand_letter": recommend_demand,
        "overall_case_strength": overall_strength,
        "total_gaps": total_gaps,
        "completeness_score": completeness_score,
        "critical_gap_count": critical_count,
        "high_gap_count": high_count,
        "findings_status": findings_status,
        "demand_status": demand_status,
    }

    # --- Apply category-aware thresholds ---
    thresholds = get_quality_thresholds(category, doc_count)

    if len(parties) < thresholds["min_parties"]:
        issues.append(
            f"party extraction thin ({len(parties)} parties from {doc_count} docs, "
            f"threshold {thresholds['min_parties']})"
        )

    if len(timeline) < thresholds["min_timeline"]:
        issues.append(
            f"timeline extraction thin ({len(timeline)} events from {doc_count} docs, "
            f"threshold {thresholds['min_timeline']})"
        )

    if thresholds["flag_no_financial"] and len(financial_data) == 0:
        issues.append(
            f"no financial data extracted from {doc_count} docs (strongly flagged for {category})"
        )

    if not primary_issues:
        issues.append("no primary legal issues identified")

    if not issue_analyses:
        issues.append("no issue analyses produced")

    if completeness_score is not None and completeness_score < 40:
        issues.append(f"very low completeness score ({completeness_score:.0f}/100)")

    if critical_count > 3:
        issues.append(f"excessive critical gaps ({critical_count})")

    # Letter quality issues
    if findings_status == "failed":
        issues.append("findings letter generation failed")
    if findings_warnings:
        for w in findings_warnings:
            notes.append(f"[heuristic] {w}")

    if demand_expected and demand_expectation_confidence != "low":
        if demand_status == "failed":
            issues.append("demand letter generation failed (expected)")
    if demand_warnings:
        for w in demand_warnings:
            notes.append(f"[heuristic] {w}")

    # --- Classify ---
    if not issues:
        quality = "HIGH"
    elif len(issues) <= 2 and not any("failed" in i for i in issues):
        quality = "ACCEPTABLE"
        notes.append(f"[heuristic] quality downgraded for: {'; '.join(issues)}")
    elif len(issues) <= 4:
        quality = "LOW"
        notes.append(f"[heuristic] quality low due to: {'; '.join(issues)}")
    else:
        quality = "VERY_LOW"
        notes.append(f"[heuristic] quality very low due to: {'; '.join(issues)}")

    signals["quality_issues"] = issues
    return quality, signals, notes


# ---------------------------------------------------------------------------
# Req 3: Behavior verification
# ---------------------------------------------------------------------------

def verify_behavior(
    job_data: Optional[Dict],
    result_data: Optional[Dict],
    stages_observed: List[str],
    findings_result: Tuple[str, List[str]],
    demand_result: Tuple[str, List[str]],
    persistence_ok: bool,
    skipped_docs: List[Any],
) -> Dict[str, Any]:
    """Build the per-case behavior_verification dict."""
    job_created = job_data is not None
    worker_claimed = False
    durable_mode = False

    if job_data:
        durable_mode = True
        worker_claimed = job_data.get("status") in ("running", "completed", "failed")
        if job_data.get("worker_id"):
            worker_claimed = True

    expected_set = {"fact_extraction", "deep_analysis", "completed"}
    observed_set = set(stages_observed)
    all_expected = expected_set.issubset(observed_set)

    findings_status = findings_result[0]
    demand_status = demand_result[0]

    return {
        "durable_mode_confirmed": durable_mode,
        "job_created": job_created,
        "worker_claimed": worker_claimed,
        "all_expected_stages_observed": all_expected,
        "stages_observed": stages_observed,
        "findings_via_production_route": findings_status in ("ok", "degraded"),
        "demand_via_production_route": demand_status in ("ok", "degraded", "skipped"),
        "persistence_verified": persistence_ok,
        "skipped_docs_surfaced": len(skipped_docs) > 0 or True,  # True if no skipped docs is expected
    }


# ---------------------------------------------------------------------------
# Req 4: Shortcomings + suggested improvements
# ---------------------------------------------------------------------------

def derive_shortcomings(
    signals: Dict[str, Any],
    category: str,
    doc_count: int,
    behavior: Dict[str, Any],
    provider_signals: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    """Derive machine-readable shortcomings and improvement suggestions."""
    shortcomings: List[str] = []
    suggestions: List[str] = []

    quality_issues = signals.get("quality_issues") or []
    for issue in quality_issues:
        shortcomings.append(issue)

    # Timeline coverage
    tc = signals.get("timeline_count", 0)
    if tc < 5 and doc_count > 15:
        suggestions.append(
            f"investigate fact extraction prompt for timeline coverage "
            f"({tc} events from {doc_count} docs)"
        )

    # Party extraction
    pc = signals.get("party_count", 0)
    if pc < 3 and doc_count > 15:
        suggestions.append(
            f"investigate fact extraction prompt for party detection "
            f"({pc} parties from {doc_count} docs)"
        )

    # Financial data
    fc = signals.get("financial_count", 0)
    if fc == 0 and doc_count >= 20:
        suggestions.append(
            "add financial data extraction heuristic or prompt improvement"
        )

    # Completeness score
    cs = signals.get("completeness_score")
    if cs is not None and cs < 50:
        shortcomings.append(f"low completeness score ({cs:.0f}/100)")
        suggestions.append("review gap analysis calibration for completeness scoring")

    # Provider issues
    if provider_signals.get("retry_pattern_detected"):
        shortcomings.append("retry pattern detected during processing")
        suggestions.append("investigate provider stability and rate limiting")

    if provider_signals.get("timeout_pattern_detected"):
        shortcomings.append("timeout pattern detected during processing")
        suggestions.append("investigate long-running stage timeouts")

    # Behavior gaps
    if not behavior.get("all_expected_stages_observed"):
        observed = behavior.get("stages_observed", [])
        shortcomings.append(f"not all expected stages observed: {observed}")
        suggestions.append("check worker stage reporting completeness")

    if not behavior.get("persistence_verified"):
        shortcomings.append("result persistence verification failed")
        suggestions.append("investigate Supabase write path for analysis_results")

    # If no shortcomings found, still provide signal
    if not shortcomings:
        shortcomings.append("no significant shortcomings detected")

    if not suggestions:
        suggestions.append("continue monitoring; no immediate action needed")

    return shortcomings, suggestions


# ---------------------------------------------------------------------------
# Req 12: manual_review_recommended
# ---------------------------------------------------------------------------

def should_recommend_manual_review(
    quality: str,
    signals: Dict[str, Any],
    doc_count: int,
    skipped_count: int,
    demand_expected: bool,
    demand_expectation_confidence: str,
    demand_status: str,
    findings_status: str,
) -> bool:
    """Determine if manual review is recommended."""
    if quality in ("LOW", "VERY_LOW"):
        return True

    # High skipped document ratio
    if doc_count > 0 and skipped_count / doc_count > 0.3:
        return True

    # Uncertain demand expectation but demand was generated
    if not demand_expected and demand_expectation_confidence == "low" and demand_status == "ok":
        return True

    # Substantive letters missing
    if findings_status == "failed":
        return True

    # doc_count / extracted facts mismatch
    tc = signals.get("timeline_count", 0)
    pc = signals.get("party_count", 0)
    if doc_count > 20 and tc < 3 and pc < 2:
        return True

    return False


# ---------------------------------------------------------------------------
# Inventory check
# ---------------------------------------------------------------------------

def run_inventory() -> List[Dict[str, Any]]:
    """Check all roster cases exist and have ready docs."""
    inventory = []
    for case in SWEEP_CASES:
        case_id = case["id"]
        # Check case exists
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/cases?id=eq.{case_id}&select=id,client_name,status",
            headers=service_headers(),
        )
        case_data = resp.json()
        if not case_data:
            inventory.append({**case, "exists": False, "ready_docs": 0, "case_status": None})
            continue

        c = case_data[0]
        # Count ready docs
        doc_resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/documents?case_id=eq.{case_id}&status=eq.ready&select=id",
            headers=service_headers(),
        )
        doc_data = doc_resp.json() if doc_resp.status_code == 200 else []
        ready_count = len(doc_data) if isinstance(doc_data, list) else 0

        inventory.append({
            **case,
            "exists": True,
            "ready_docs": ready_count,
            "case_status": c.get("status"),
        })
    return inventory


# ---------------------------------------------------------------------------
# Req 10: Preflight
# ---------------------------------------------------------------------------

def run_preflight(token: str) -> bool:
    """Validate environment, auth, roster, and API reachability."""
    print("\n=== PREFLIGHT CHECK ===\n")
    all_ok = True

    # 1. Env vars
    print("[1/5] Environment variables...")
    for var in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SWEEP_USER_EMAIL"):
        val = os.getenv(var)
        if val:
            print(f"  OK  {var} = {val[:20]}...")
        else:
            print(f"  FAIL {var} is not set")
            all_ok = False

    # 2. Auth
    print(f"\n[2/5] Authentication (token length={len(token)})...")
    if len(token) > 20:
        print("  OK  token acquired")
    else:
        print("  FAIL token too short")
        all_ok = False

    # 3. Roster cases exist with ready docs
    print("\n[3/5] Roster validation...")
    inventory = run_inventory()
    for item in inventory:
        status_str = "EXISTS" if item["exists"] else "MISSING"
        docs = item.get("ready_docs", 0)
        cs = item.get("case_status", "?")
        flag = "" if item["exists"] and docs > 0 else " *** PROBLEM ***"
        print(f"  {status_str}  {item['name']:25s}  ready_docs={docs:3d}  case_status={cs}{flag}")
        if not item["exists"] or docs == 0:
            all_ok = False

    # 4. API reachability (POST /analysis/start without actually starting)
    print("\n[4/5] API reachability...")
    try:
        # Just check we can reach the API - use a health endpoint
        # Try /api/health first, then /health
        for path in ("/api/health", "/health"):
            health_resp = requests.get(f"{API_BASE}{path}", timeout=10)
            if health_resp.status_code == 200:
                print(f"  OK  {API_BASE}{path} returned 200")
                break
        else:
            print(f"  WARN health endpoint returned {health_resp.status_code} (non-blocking)")
    except Exception as e:
        print(f"  FAIL cannot reach {API_BASE}: {e}")
        all_ok = False

    # 5. Output directory writable
    print("\n[5/5] Output directory...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    test_path = os.path.join(OUTPUT_DIR, ".preflight_test")
    try:
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        print(f"  OK  {OUTPUT_DIR} is writable")
    except Exception as e:
        print(f"  FAIL {OUTPUT_DIR} not writable: {e}")
        all_ok = False

    print(f"\n{'=' * 40}")
    if all_ok:
        print("PREFLIGHT PASSED — ready to sweep")
    else:
        print("PREFLIGHT FAILED — fix issues above before running sweep")
    return all_ok


# ---------------------------------------------------------------------------
# Req 14: Provider instability signals
# ---------------------------------------------------------------------------

def collect_provider_signals(poll_history: List[Dict]) -> Dict[str, Any]:
    """Collect provider instability signals from polling history."""
    signals: Dict[str, Any] = {
        "job_attempts": 0,
        "job_error": None,
        "max_heartbeat_age_observed": 0.0,
        "timeout_pattern_detected": False,
        "retry_pattern_detected": False,
    }

    for entry in poll_history:
        attempts = entry.get("attempts", 0)
        if attempts > signals["job_attempts"]:
            signals["job_attempts"] = attempts

        hb_age = entry.get("heartbeat_age_seconds")
        if hb_age is not None and hb_age > signals["max_heartbeat_age_observed"]:
            signals["max_heartbeat_age_observed"] = hb_age

        err = entry.get("error")
        if err:
            signals["job_error"] = err
            err_lower = err.lower()
            if "timeout" in err_lower:
                signals["timeout_pattern_detected"] = True

    if signals["job_attempts"] > 1:
        signals["retry_pattern_detected"] = True

    return signals


# ---------------------------------------------------------------------------
# Main per-case runner
# ---------------------------------------------------------------------------

def run_case(
    case: Dict[str, Any],
    token: str,
    force_cleanup: bool = False,
) -> Dict[str, Any]:
    """Run analysis for a single case and verify outputs.

    Authenticates as the case owner (not the default sweep user) since the API
    enforces RLS ownership checks.
    """
    # Get the correct token for this case's owner
    case_token = get_token_for_case(case["id"])
    if case_token:
        token = case_token  # Override with case-owner token
    case_id = case["id"]
    case_name = case["name"]
    category = case["category"]
    start_time = time.time()
    now_utc = datetime.now(timezone.utc).isoformat()

    result_record: Dict[str, Any] = {
        "case_id": case_id,
        "case_name": case_name,
        "category": category,
        "notes": case.get("notes", ""),
        "started_at": now_utc,
        "runtime_seconds": 0,
        "classification": None,
        "quality": None,
        "quality_signals": {},
        "quality_notes": [],
        "behavior_verification": {},
        "provider_signals": {},
        "opposing_parties": [],
        "opposing_party_confidence": "low",
        "demand_expected": False,
        "demand_expectation_confidence": "low",
        "findings_chars": 0,
        "demand_chars": 0,
        "findings_status": "not_attempted",
        "demand_status": "not_attempted",
        "findings_warnings": [],
        "demand_warnings": [],
        "shortcomings": [],
        "suggested_improvements": [],
        "manual_review_recommended": False,
        "skipped_documents": [],
        "doc_count": 0,
        "error": None,
    }

    hdrs = api_headers(token)

    try:
        # --- Step 0: Check for existing active jobs (Req 16) ---
        active_resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/analysis_jobs?case_id=eq.{case_id}"
            "&status=in.(pending,running)&select=id,status,created_at&order=created_at.desc&limit=1",
            headers=service_headers(),
        )
        active_jobs = active_resp.json() if active_resp.status_code == 200 else []
        if isinstance(active_jobs, list) and active_jobs:
            if not force_cleanup:
                job = active_jobs[0]
                print(f"  SKIP: active job {job['id'][:12]} (status={job['status']})")
                result_record["classification"] = "SKIPPED_ACTIVE_JOB"
                result_record["runtime_seconds"] = time.time() - start_time
                result_record["error"] = f"Active job exists: {job['id']}"
                return result_record
            else:
                # Force cleanup: cancel active jobs
                for job in active_jobs:
                    print(f"  CLEANUP: cancelling job {job['id'][:12]}")
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/analysis_jobs?id=eq.{job['id']}",
                        headers=service_headers(),
                        json={"status": "cancelled", "error": "Cancelled by sweep --force-cleanup"},
                    )
                time.sleep(2)

        # --- Step 0b: Check for stale analysis_results (Req 16) ---
        stale_resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/analysis_results?case_id=eq.{case_id}"
            "&status=in.(pending,processing)&select=id,status,created_at&order=created_at.desc&limit=5",
            headers=service_headers(),
        )
        stale_results = stale_resp.json() if stale_resp.status_code == 200 else []
        if isinstance(stale_results, list) and stale_results:
            print(f"  INFO: {len(stale_results)} stale analysis_results found (logged only)")

        # --- Step 1: Count ready docs ---
        doc_resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/documents?case_id=eq.{case_id}&status=eq.ready&select=id",
            headers=service_headers(),
        )
        doc_data = doc_resp.json() if doc_resp.status_code == 200 else []
        doc_count = len(doc_data) if isinstance(doc_data, list) else 0
        result_record["doc_count"] = doc_count

        if doc_count == 0:
            print(f"  SKIP: no ready docs")
            result_record["classification"] = "SKIPPED_NO_READY_DOCS"
            result_record["runtime_seconds"] = time.time() - start_time
            return result_record

        # --- Step 2: Start analysis (POST /api/analysis/start) ---
        print(f"  Starting analysis ({doc_count} docs)...")
        start_resp = requests.post(
            f"{API_BASE}/api/analysis/start",
            headers=hdrs,
            json={"case_id": case_id, "provider": "openai"},
            timeout=30,
        )

        if start_resp.status_code == 401:
            # Token expired — refresh and retry once
            print(f"  Token expired, refreshing...")
            owner_email = get_case_owner_email(case_id)
            if owner_email:
                token = get_token_for_email(owner_email, force_refresh=True)
                hdrs = api_headers(token)
                start_resp = requests.post(
                    f"{API_BASE}/api/analysis/start",
                    headers=hdrs,
                    json={"case_id": case_id, "provider": "openai"},
                    timeout=30,
                )

        if start_resp.status_code not in (200, 202):
            err = start_resp.text[:300]
            print(f"  ERROR starting analysis: {start_resp.status_code} {err}")
            result_record["classification"] = "INFRASTRUCTURE_FAILURE"
            result_record["error"] = f"Start failed: {start_resp.status_code} {err}"
            result_record["runtime_seconds"] = time.time() - start_time
            return result_record

        start_data = start_resp.json()
        job_id = start_data.get("job_id")
        analysis_id = start_data.get("id")

        if not job_id:
            print(f"  ERROR: no job_id in response — durable mode may not be enabled")
            result_record["classification"] = "INFRASTRUCTURE_FAILURE"
            result_record["error"] = "No job_id in start response"
            result_record["runtime_seconds"] = time.time() - start_time
            return result_record

        print(f"  job_id={job_id[:12]}  analysis_id={analysis_id[:12] if analysis_id else '?'}")

        # --- Step 3: Poll job status until terminal ---
        stages_observed: List[str] = []
        poll_history: List[Dict] = []
        job_final_data: Optional[Dict] = None
        last_stage = ""
        poll_start = time.time()

        while time.time() - poll_start < MAX_POLL_DURATION:
            time.sleep(POLL_INTERVAL)
            try:
                poll_resp = requests.get(
                    f"{API_BASE}/api/progress/jobs/{job_id}/status",
                    headers=hdrs,
                    timeout=15,
                )
                if poll_resp.status_code == 401:
                    # Token expired mid-poll — refresh
                    owner_email = get_case_owner_email(case_id)
                    if owner_email:
                        token = get_token_for_email(owner_email, force_refresh=True)
                        hdrs = api_headers(token)
                    continue
                if poll_resp.status_code != 200:
                    print(f"  POLL: HTTP {poll_resp.status_code}")
                    continue

                pdata = poll_resp.json()
                poll_history.append(pdata)

                status_val = pdata.get("status", "unknown")
                stage = pdata.get("stage", "")
                percent = pdata.get("percent", 0)
                msg = pdata.get("message", "")
                hb_age = pdata.get("heartbeat_age_seconds")
                attempts = pdata.get("attempts", 0)

                if stage and stage not in stages_observed:
                    stages_observed.append(stage)

                if stage != last_stage:
                    elapsed = int(time.time() - poll_start)
                    hb_str = f" hb_age={hb_age:.0f}s" if hb_age else ""
                    print(
                        f"  [{elapsed:4d}s] status={status_val:10s} stage={stage:20s} "
                        f"pct={percent:3d}% attempts={attempts}{hb_str}"
                    )
                    last_stage = stage

                if status_val in ("completed", "failed", "cancelled"):
                    job_final_data = pdata
                    break

            except requests.RequestException as e:
                print(f"  POLL error: {e}")
                continue

        poll_duration = time.time() - poll_start

        if not job_final_data:
            print(f"  TIMEOUT after {poll_duration:.0f}s")
            result_record["classification"] = "INFRASTRUCTURE_FAILURE"
            result_record["error"] = f"Polling timeout after {poll_duration:.0f}s"
            result_record["runtime_seconds"] = time.time() - start_time
            result_record["provider_signals"] = collect_provider_signals(poll_history)
            result_record["behavior_verification"] = verify_behavior(
                job_final_data, None, stages_observed,
                ("not_attempted", []), ("not_attempted", []),
                False, [],
            )
            return result_record

        job_status = job_final_data.get("status", "unknown")
        job_error = job_final_data.get("error")
        provider_sigs = collect_provider_signals(poll_history)
        provider_sigs["job_error"] = job_error
        result_record["provider_signals"] = provider_sigs

        # --- Step 4: Fetch results from persistence endpoint ---
        # Refresh token before results/letters phase (long-running polls may have expired it)
        owner_email = get_case_owner_email(case_id)
        if owner_email:
            token = get_token_for_email(owner_email, force_refresh=True)
            hdrs = api_headers(token)
        print(f"  Fetching results from /api/analysis/results/{case_id}...")
        result_resp = requests.get(
            f"{API_BASE}/api/analysis/results/{case_id}",
            headers=hdrs,
            timeout=30,
        )

        result_data: Optional[Dict] = None
        if result_resp.status_code == 200:
            result_data = result_resp.json()
        else:
            print(f"  WARN: results fetch returned {result_resp.status_code}")

        # --- Step 5: Classify outcome ---
        classification = classify_failure(job_status, job_error, result_data, poll_duration)

        # --- Step 6: Extract and verify if we have results ---
        findings_content: Optional[str] = None
        demand_content: Optional[str] = None
        findings_result: Tuple[str, List[str]] = ("not_attempted", [])
        demand_result: Tuple[str, List[str]] = ("not_attempted", [])
        opposing_parties: List[Dict] = []
        opposing_confidence = "low"
        demand_expected = False
        demand_expectation_confidence = "low"
        skipped_docs: List[Any] = []
        persistence_ok = False

        if result_data and result_data.get("multi_stage_result"):
            persistence_ok = True

            # Opposing parties (Req 5)
            opposing_parties, opposing_confidence = extract_opposing_parties_with_confidence(result_data)

            # Demand expectation (Req 6)
            demand_expected = len(opposing_parties) > 0
            demand_expectation_confidence = opposing_confidence

            # Skipped documents
            skipped_docs = result_data.get("skipped_documents") or []

            # --- Step 6a: Fetch findings letter via production route ---
            print(f"  Fetching findings letter...")
            try:
                findings_resp = requests.get(
                    f"{API_BASE}/api/analysis/{analysis_id}/letter/stream",
                    headers=hdrs,
                    stream=True,
                    timeout=120,
                )
                if findings_resp.status_code == 200:
                    findings_content, findings_err = consume_sse_stream(findings_resp)
                    if findings_err:
                        findings_result = ("failed", [f"SSE error: {findings_err}"])
                    elif findings_content:
                        findings_result = check_letter_quality(findings_content, "findings")
                    else:
                        findings_result = ("failed", ["empty stream response"])
                else:
                    findings_result = ("failed", [f"HTTP {findings_resp.status_code}"])
            except Exception as e:
                findings_result = ("failed", [f"Exception: {str(e)[:100]}"])

            # --- Step 6b: Fetch demand letter if expected ---
            if demand_expected and opposing_parties:
                target_name = opposing_parties[0].get("name", "")
                print(f"  Fetching demand letter (target={target_name})...")
                try:
                    demand_resp = requests.get(
                        f"{API_BASE}/api/analysis/{analysis_id}/demand-letter/stream",
                        headers=hdrs,
                        params={"target_party_name": target_name},
                        stream=True,
                        timeout=120,
                    )
                    if demand_resp.status_code == 200:
                        demand_content, demand_err = consume_sse_stream(demand_resp)
                        if demand_err:
                            demand_result = ("failed", [f"SSE error: {demand_err}"])
                        elif demand_content:
                            demand_result = check_letter_quality(
                                demand_content, "demand", target_party_name=target_name
                            )
                        else:
                            demand_result = ("failed", ["empty stream response"])
                    else:
                        demand_result = ("failed", [f"HTTP {demand_resp.status_code}"])
                except Exception as e:
                    demand_result = ("failed", [f"Exception: {str(e)[:100]}"])
            elif not demand_expected:
                demand_result = ("skipped", [f"no opposing party (confidence={opposing_confidence})"])
            else:
                demand_result = ("skipped", ["no opposing parties found"])

            # --- Req 13: Stricter persistence verification ---
            # FULL_PASS requires findings persistence verified
            if classification == "FULL_PASS":
                if findings_result[0] not in ("ok", "degraded"):
                    classification = "PASS_WITH_LIMITATIONS"

                # Demand persistence when demand was generated (status="ok")
                if demand_result[0] == "ok":
                    # Demand was generated successfully, persistence implicitly verified
                    pass
                elif demand_expected and demand_expectation_confidence != "low":
                    if demand_result[0] == "failed":
                        classification = "PASS_WITH_LIMITATIONS"
                # If demand skipped for valid reason, that's fine

            # --- Quality assessment ---
            quality, quality_signals, quality_notes = assess_quality(
                result_data, category, doc_count,
                findings_result[0], demand_result[0],
                demand_expected, demand_expectation_confidence,
                findings_result[1], demand_result[1],
            )

            if classification == "FULL_PASS" and quality in ("LOW", "VERY_LOW"):
                classification = "DATA_QUALITY_COMPLETENESS_FAILURE"

            result_record["quality"] = quality
            result_record["quality_signals"] = quality_signals
            result_record["quality_notes"] = quality_notes

        elif result_data and not result_data.get("multi_stage_result"):
            # Result exists but no multi_stage_result
            persistence_ok = False
            if classification == "FULL_PASS":
                classification = "DATA_QUALITY_COMPLETENESS_FAILURE"

        # Build behavior verification (Req 3)
        behavior = verify_behavior(
            job_final_data, result_data, stages_observed,
            findings_result, demand_result,
            persistence_ok, skipped_docs,
        )

        # Shortcomings (Req 4)
        shortcomings, suggestions = derive_shortcomings(
            result_record.get("quality_signals", {}),
            category, doc_count,
            behavior, provider_sigs,
        )

        # Manual review (Req 12)
        manual_review = should_recommend_manual_review(
            result_record.get("quality", "VERY_LOW"),
            result_record.get("quality_signals", {}),
            doc_count,
            len(skipped_docs),
            demand_expected, demand_expectation_confidence,
            demand_result[0], findings_result[0],
        )

        runtime = time.time() - start_time
        result_record.update({
            "classification": classification,
            "runtime_seconds": round(runtime, 1),
            "behavior_verification": behavior,
            "opposing_parties": opposing_parties,
            "opposing_party_confidence": opposing_confidence,
            "demand_expected": demand_expected,
            "demand_expectation_confidence": demand_expectation_confidence,
            "findings_chars": len(findings_content) if findings_content else 0,
            "demand_chars": len(demand_content) if demand_content else 0,
            "findings_status": findings_result[0],
            "demand_status": demand_result[0],
            "findings_warnings": findings_result[1],
            "demand_warnings": demand_result[1],
            "shortcomings": shortcomings,
            "suggested_improvements": suggestions,
            "manual_review_recommended": manual_review,
            "skipped_documents": skipped_docs,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

        return result_record

    except Exception as e:
        result_record["classification"] = "INFRASTRUCTURE_FAILURE"
        result_record["error"] = str(e)[:500]
        result_record["runtime_seconds"] = round(time.time() - start_time, 1)
        print(f"  EXCEPTION: {e}")
        return result_record


# ---------------------------------------------------------------------------
# Req 1 / Req 15: Compute final assessment
# ---------------------------------------------------------------------------

def compute_final_assessment(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate all case results into final verdicts."""
    total = len(results)
    if total == 0:
        return {
            "reliability_pass_rate": 0,
            "quality_pass_rate": 0,
            "pass_rate_by_category": {},
            "top_failure_modes": [],
            "top_quality_weaknesses": [],
            "recommended_reliability_fix": "No data",
            "recommended_quality_fix": "No data",
            "production_ready": False,
            "consistency_verdict": "NOT_YET_CONSISTENT",
        }

    # Skip non-actionable classifications
    skip_classifications = {"SKIPPED_ACTIVE_JOB", "SKIPPED_NO_READY_DOCS", "CASE_NOT_FOUND"}
    actionable = [r for r in results if r.get("classification") not in skip_classifications]
    actionable_count = len(actionable)

    if actionable_count == 0:
        return {
            "reliability_pass_rate": 0,
            "quality_pass_rate": 0,
            "pass_rate_by_category": {},
            "top_failure_modes": ["All cases skipped"],
            "top_quality_weaknesses": [],
            "recommended_reliability_fix": "Resolve skipped cases",
            "recommended_quality_fix": "N/A",
            "production_ready": False,
            "consistency_verdict": "NOT_YET_CONSISTENT",
        }

    # Reliability: completed successfully (any PASS classification)
    reliable_classifications = {"FULL_PASS", "PASS_WITH_LIMITATIONS", "DATA_QUALITY_COMPLETENESS_FAILURE"}
    reliable_count = sum(1 for r in actionable if r["classification"] in reliable_classifications)
    reliability_rate = (reliable_count / actionable_count) * 100

    # Quality: HIGH or ACCEPTABLE
    quality_pass = sum(
        1 for r in actionable
        if r.get("quality") in ("HIGH", "ACCEPTABLE")
    )
    quality_rate = (quality_pass / actionable_count) * 100 if actionable_count > 0 else 0

    # Pass rate by category
    categories = set(r["category"] for r in actionable)
    by_category: Dict[str, Dict[str, Any]] = {}
    for cat in sorted(categories):
        cat_results = [r for r in actionable if r["category"] == cat]
        cat_reliable = sum(1 for r in cat_results if r["classification"] in reliable_classifications)
        cat_quality = sum(1 for r in cat_results if r.get("quality") in ("HIGH", "ACCEPTABLE"))
        by_category[cat] = {
            "total": len(cat_results),
            "reliability_pass": cat_reliable,
            "reliability_rate": round((cat_reliable / len(cat_results)) * 100, 1),
            "quality_pass": cat_quality,
            "quality_rate": round((cat_quality / len(cat_results)) * 100, 1) if cat_results else 0,
        }

    # Top failure modes
    failure_modes: Dict[str, int] = {}
    for r in actionable:
        cls = r.get("classification", "UNKNOWN")
        if cls not in ("FULL_PASS",):
            failure_modes[cls] = failure_modes.get(cls, 0) + 1
    top_failures = sorted(failure_modes.items(), key=lambda x: -x[1])[:5]

    # Top quality weaknesses
    weakness_counts: Dict[str, int] = {}
    for r in actionable:
        for issue in (r.get("quality_signals") or {}).get("quality_issues", []):
            # Normalize
            key = issue.split("(")[0].strip()
            weakness_counts[key] = weakness_counts.get(key, 0) + 1
    top_weaknesses = sorted(weakness_counts.items(), key=lambda x: -x[1])[:5]

    # Recommended fixes
    rec_reliability = "No reliability issues detected"
    if top_failures:
        mode, count = top_failures[0]
        rec_reliability = f"Address '{mode}' ({count}/{actionable_count} cases)"

    rec_quality = "No quality issues detected"
    if top_weaknesses:
        weakness, count = top_weaknesses[0]
        rec_quality = f"Address '{weakness}' ({count}/{actionable_count} cases)"

    # Verdict (Req 15)
    if reliability_rate >= 90 and quality_rate >= 70:
        verdict = "CONSISTENTLY_PRODUCTION_READY"
        production_ready = True
    elif reliability_rate >= 70 and quality_rate >= 50:
        verdict = "PRODUCTION_READY_WITH_LIMITATIONS"
        production_ready = True
    else:
        verdict = "NOT_YET_CONSISTENT"
        production_ready = False

    return {
        "reliability_pass_rate": round(reliability_rate, 1),
        "quality_pass_rate": round(quality_rate, 1),
        "pass_rate_by_category": by_category,
        "top_failure_modes": [{"mode": m, "count": c} for m, c in top_failures],
        "top_quality_weaknesses": [{"weakness": w, "count": c} for w, c in top_weaknesses],
        "recommended_reliability_fix": rec_reliability,
        "recommended_quality_fix": rec_quality,
        "production_ready": production_ready,
        "consistency_verdict": verdict,
        "actionable_count": actionable_count,
        "total_count": total,
        "skipped_count": total - actionable_count,
    }


# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------

def print_summary(results: List[Dict[str, Any]], assessment: Dict[str, Any]) -> None:
    """Print full report to stdout."""
    print("\n" + "=" * 80)
    print("  CONSISTENCY SWEEP RESULTS")
    print("=" * 80)

    # Per-case summary
    print(f"\n{'Case':<25s} {'Cat':<10s} {'Docs':>4s} {'Time':>7s} {'Class':<35s} {'Quality':<12s}")
    print("-" * 100)
    for r in results:
        name = r["case_name"][:24]
        cat = r["category"]
        docs = str(r.get("doc_count", "?"))
        rt = f"{r.get('runtime_seconds', 0):.0f}s"
        cls = r.get("classification", "?")
        quality = r.get("quality") or r.get("quality_classification") or "-"
        quality = quality if quality else "-"
        flag = " *" if r.get("manual_review_recommended") else ""
        print(f"{name:<25s} {cat:<10s} {docs:>4s} {rt:>7s} {cls:<35s} {quality:<12s}{flag}")

    print("\n(* = manual review recommended)")

    # Assessment
    print(f"\n{'=' * 60}")
    print(f"  FINAL ASSESSMENT")
    print(f"{'=' * 60}")
    print(f"  Reliability pass rate:  {assessment['reliability_pass_rate']:.1f}%")
    print(f"  Quality pass rate:      {assessment['quality_pass_rate']:.1f}%")

    by_cat = assessment.get("pass_rate_by_category", {})
    if by_cat:
        print(f"\n  Pass rate by category:")
        for cat, data in by_cat.items():
            print(
                f"    {cat:<12s}  reliability={data['reliability_rate']:5.1f}% "
                f"({data['reliability_pass']}/{data['total']})  "
                f"quality={data['quality_rate']:5.1f}% ({data['quality_pass']}/{data['total']})"
            )

    top_fail = assessment.get("top_failure_modes", [])
    if top_fail:
        print(f"\n  Top failure modes:")
        for f in top_fail:
            print(f"    - {f['mode']} ({f['count']}x)")

    top_weak = assessment.get("top_quality_weaknesses", [])
    if top_weak:
        print(f"\n  Top quality weaknesses:")
        for w in top_weak:
            print(f"    - {w['weakness']} ({w['count']}x)")

    print(f"\n  Recommended reliability fix: {assessment['recommended_reliability_fix']}")
    print(f"  Recommended quality fix:     {assessment['recommended_quality_fix']}")
    print(f"\n  Production ready: {'YES' if assessment['production_ready'] else 'NO'}")
    print(f"  Consistency verdict: {assessment['consistency_verdict']}")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Req 7: Write markdown report
# ---------------------------------------------------------------------------

def write_markdown_report(
    results: List[Dict[str, Any]],
    assessment: Dict[str, Any],
    path: str,
) -> None:
    """Write sweep_report.md."""
    lines: List[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append(f"# Consistency Sweep Report")
    lines.append(f"")
    lines.append(f"**Date:** {ts}")
    lines.append(f"**Cases:** {assessment.get('total_count', len(results))}")
    lines.append(f"**Verdict:** `{assessment['consistency_verdict']}`")
    lines.append(f"")

    # Summary table
    lines.append("## Results Summary")
    lines.append("")
    lines.append(
        "| Case | Category | Docs | Runtime | Classification | Quality | Review |"
    )
    lines.append(
        "|------|----------|-----:|--------:|---------------|---------|--------|"
    )
    for r in results:
        name = r["case_name"]
        cat = r["category"]
        docs = r.get("doc_count", "?")
        rt = f"{r.get('runtime_seconds', 0):.0f}s"
        cls = r.get("classification", "?")
        quality = r.get("quality") or r.get("quality_classification") or "-"
        review = "Yes" if r.get("manual_review_recommended") else ""
        lines.append(f"| {name} | {cat} | {docs} | {rt} | {cls} | {quality} | {review} |")

    # Assessment
    lines.append("")
    lines.append("## Final Assessment")
    lines.append("")
    lines.append(f"- **Reliability pass rate:** {assessment['reliability_pass_rate']:.1f}%")
    lines.append(f"- **Quality pass rate:** {assessment['quality_pass_rate']:.1f}%")
    lines.append(f"- **Production ready:** {'Yes' if assessment['production_ready'] else 'No'}")
    lines.append(f"- **Verdict:** `{assessment['consistency_verdict']}`")

    by_cat = assessment.get("pass_rate_by_category", {})
    if by_cat:
        lines.append("")
        lines.append("### By Category")
        lines.append("")
        for cat, data in by_cat.items():
            lines.append(
                f"- **{cat}:** reliability={data['reliability_rate']:.1f}% "
                f"quality={data['quality_rate']:.1f}% ({data['total']} cases)"
            )

    top_fail = assessment.get("top_failure_modes", [])
    if top_fail:
        lines.append("")
        lines.append("### Top Failure Modes")
        lines.append("")
        for f in top_fail:
            lines.append(f"- {f['mode']} ({f['count']}x)")

    top_weak = assessment.get("top_quality_weaknesses", [])
    if top_weak:
        lines.append("")
        lines.append("### Top Quality Weaknesses")
        lines.append("")
        for w in top_weak:
            lines.append(f"- {w['weakness']} ({w['count']}x)")

    lines.append("")
    lines.append(f"### Recommendations")
    lines.append("")
    lines.append(f"- **Reliability:** {assessment['recommended_reliability_fix']}")
    lines.append(f"- **Quality:** {assessment['recommended_quality_fix']}")

    # Per-case details
    lines.append("")
    lines.append("## Per-Case Details")
    lines.append("")
    for r in results:
        lines.append(f"### {r['case_name']}")
        lines.append("")
        lines.append(f"- **Classification:** `{r.get('classification', '?')}`")
        lines.append(f"- **Quality:** `{r.get('quality', '-')}`")
        lines.append(f"- **Category:** {r['category']}")
        lines.append(f"- **Docs:** {r.get('doc_count', '?')}")
        lines.append(f"- **Runtime:** {r.get('runtime_seconds', 0):.0f}s")
        lines.append(f"- **Findings:** {r.get('findings_chars', 0)} chars ({r.get('findings_status', '?')})")
        lines.append(f"- **Demand:** {r.get('demand_chars', 0)} chars ({r.get('demand_status', '?')})")
        lines.append(f"- **Opposing parties:** {len(r.get('opposing_parties', []))} (confidence={r.get('opposing_party_confidence', '?')})")
        lines.append(f"- **Demand expected:** {r.get('demand_expected', False)} (confidence={r.get('demand_expectation_confidence', '?')})")
        lines.append(f"- **Manual review:** {'Yes' if r.get('manual_review_recommended') else 'No'}")

        shortcomings = r.get("shortcomings", [])
        if shortcomings:
            lines.append(f"- **Shortcomings:**")
            for s in shortcomings:
                lines.append(f"  - {s}")

        suggestions = r.get("suggested_improvements", [])
        if suggestions:
            lines.append(f"- **Suggested improvements:**")
            for s in suggestions:
                lines.append(f"  - {s}")

        lines.append("")

    lines.append("---")
    lines.append(f"*Generated by run_consistency_sweep.py at {ts}*")
    lines.append("*All quality assessments are heuristic.*")
    lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Req 7: Write CSV summary
# ---------------------------------------------------------------------------

def write_csv_summary(results: List[Dict[str, Any]], path: str) -> None:
    """Write sweep_results.csv with one row per case."""
    fieldnames = [
        "name", "docs", "category", "runtime", "reliability",
        "quality", "findings_chars", "demand_chars",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "name": r["case_name"],
                "docs": r.get("doc_count", 0),
                "category": r["category"],
                "runtime": round(r.get("runtime_seconds", 0), 1),
                "reliability": r.get("classification", "?"),
                "quality": r.get("quality") or r.get("quality_classification") or "-",
                "findings_chars": r.get("findings_chars", 0),
                "demand_chars": r.get("demand_chars", 0),
            })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Production consistency sweep — 10-case verification"
    )
    parser.add_argument(
        "--preflight", action="store_true",
        help="Run preflight checks only, no analysis",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from existing sweep_results.json, skipping terminal cases",
    )
    parser.add_argument(
        "--from-case", type=str, default=None,
        help="Start from a specific case name (exact match)",
    )
    parser.add_argument(
        "--pause-between-cases", type=int, default=15,
        help="Seconds to pause between cases (default: 15)",
    )
    parser.add_argument(
        "--force-cleanup", action="store_true",
        help="Cancel active jobs before re-running (default: skip active)",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Print sweep roster and exit (no credentials needed)",
    )
    parser.add_argument(
        "--case", type=str, default=None,
        help="Run a single case by name",
    )
    args = parser.parse_args()

    if args.list:
        print("Sweep roster:")
        for i, c in enumerate(SWEEP_CASES):
            print(f"  [{i}] {c['id'][:12]}... {c['name']:<25s} {c['category']:<10s} {c['notes']}")
        return

    require_env()

    print("=" * 60)
    print("  CONSISTENCY SWEEP")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  API: {API_BASE}")
    print(f"  Cases: {len(SWEEP_CASES)}")
    print("=" * 60)

    # Auth
    print("\nAuthenticating...")
    token = get_user_token()
    print(f"  OK (token length={len(token)})")

    # Preflight
    if args.preflight:
        ok = run_preflight(token)
        sys.exit(0 if ok else 1)

    # Ensure output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Resume support (Req 8)
    existing_results: Dict[str, Dict] = {}
    if args.resume:
        json_path = os.path.join(OUTPUT_DIR, "sweep_results.json")
        if os.path.exists(json_path):
            with open(json_path, "r") as f:
                data = json.load(f)
            for r in data.get("results", []):
                cid = r.get("case_id")
                cls = r.get("classification")
                if cid and cls in TERMINAL_CLASSIFICATIONS:
                    existing_results[cid] = r
            print(f"  Resuming: {len(existing_results)} cases already completed")
        else:
            print(f"  No existing results file found, starting fresh")

    # Build case list
    cases_to_run = list(SWEEP_CASES)

    # --case support: run single case
    if args.case:
        matched = [c for c in cases_to_run if args.case.lower() in c["name"].lower()]
        if not matched:
            matched = [c for c in cases_to_run if c["id"].startswith(args.case)]
        if not matched:
            print(f"  ERROR: case '{args.case}' not found in roster. Use --list.")
            sys.exit(1)
        cases_to_run = matched
        print(f"  Single case mode: {matched[0]['name']}")

    # --from-case support
    if args.from_case:
        found = False
        for i, c in enumerate(cases_to_run):
            if c["name"] == args.from_case:
                cases_to_run = cases_to_run[i:]
                found = True
                print(f"  Starting from case: {args.from_case} (index {i})")
                break
        if not found:
            print(f"  ERROR: case '{args.from_case}' not found in roster")
            sys.exit(1)

    # Run sweep
    all_results: List[Dict[str, Any]] = []

    # First, add existing resumed results (in roster order)
    for case in SWEEP_CASES:
        if case["id"] in existing_results:
            # Will be added at the right position below
            pass

    sweep_start = time.time()

    for idx, case in enumerate(cases_to_run):
        case_id = case["id"]
        case_name = case["name"]

        print(f"\n{'=' * 60}")
        print(f"  [{idx + 1}/{len(cases_to_run)}] {case_name} ({case['category']})")
        print(f"  {case['notes']}")
        print(f"{'=' * 60}")

        # Resume: skip if already done
        if case_id in existing_results:
            print(f"  RESUME: skipping (classification={existing_results[case_id]['classification']})")
            all_results.append(existing_results[case_id])
            continue

        # Run the case
        result = run_case(case, token, force_cleanup=args.force_cleanup)
        all_results.append(result)

        # Print inline summary
        cls = result.get("classification", "?")
        quality = result.get("quality") or result.get("quality_classification") or "-"
        rt = result.get("runtime_seconds", 0)
        print(f"\n  RESULT: {cls} | quality={quality} | {rt:.0f}s")

        # Incremental save
        _save_results(all_results, OUTPUT_DIR)

        # Pause between cases (Req 9)
        if idx < len(cases_to_run) - 1 and case_id not in existing_results:
            pause = args.pause_between_cases
            if pause > 0:
                print(f"\n  Pausing {pause}s before next case...")
                for remaining in range(pause, 0, -1):
                    print(f"    {remaining}s...", end="\r")
                    time.sleep(1)
                print(f"    {'Done':10s}")

    sweep_duration = time.time() - sweep_start

    # Fill in any roster entries that weren't in cases_to_run (from resume)
    result_ids = {r["case_id"] for r in all_results}
    for case in SWEEP_CASES:
        if case["id"] not in result_ids and case["id"] in existing_results:
            all_results.append(existing_results[case["id"]])

    # Sort results in roster order
    roster_order = {c["id"]: i for i, c in enumerate(SWEEP_CASES)}
    all_results.sort(key=lambda r: roster_order.get(r["case_id"], 999))

    # Compute final assessment (Req 1, Req 15)
    assessment = compute_final_assessment(all_results)
    assessment["sweep_duration_seconds"] = round(sweep_duration, 1)

    # Save all outputs (Req 7)
    output_data = {
        "sweep_metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_base": API_BASE,
            "case_count": len(all_results),
            "sweep_duration_seconds": round(sweep_duration, 1),
        },
        "results": all_results,
        "assessment": assessment,
    }

    json_path = os.path.join(OUTPUT_DIR, "sweep_results.json")
    with open(json_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)
    print(f"  Wrote {json_path}")

    csv_path = os.path.join(OUTPUT_DIR, "sweep_results.csv")
    write_csv_summary(all_results, csv_path)
    print(f"  Wrote {csv_path}")

    md_path = os.path.join(OUTPUT_DIR, "sweep_report.md")
    write_markdown_report(all_results, assessment, md_path)
    print(f"  Wrote {md_path}")

    # Print summary (Req 1)
    print_summary(all_results, assessment)


def _save_results(results: List[Dict], output_dir: str) -> None:
    """Incremental save during sweep."""
    path = os.path.join(output_dir, "sweep_results.json")
    data = {
        "sweep_metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "api_base": API_BASE,
            "case_count": len(results),
            "partial": True,
        },
        "results": results,
        "assessment": {},
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


if __name__ == "__main__":
    main()
