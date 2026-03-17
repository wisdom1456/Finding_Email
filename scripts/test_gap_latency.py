#!/usr/bin/env python3
"""Gap analysis latency diagnostic — measures phase timing on production.

Usage:
    python3 scripts/test_gap_latency.py                      # auto-picks, uses cache
    python3 scripts/test_gap_latency.py --force               # force fresh LLM analysis
    python3 scripts/test_gap_latency.py <case_id> --force     # specific case, fresh
"""

import json
import ssl
import sys
import time
import urllib.request

import certifi

API_BASE = "https://finding-emails.vercel.app"
SUPABASE_URL = "https://nqjepycmhddfekeufcle.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5xamVweWNtaGRkZmVrZXVmY2xlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM1OTMyMjAsImV4cCI6MjA3OTE2OTIyMH0."
    "SL5N1PtgQazgtqlMgisGdIaMz94p4jvH1IJUqI6S4FM"
)
EMAIL = "modible@gmail.com"
PASSWORD = "Today1911!"

CTX = ssl.create_default_context(cafile=certifi.where())


def _post_json(url: str, data: dict, headers: dict | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=h)
    with urllib.request.urlopen(req, context=CTX) as resp:
        return json.loads(resp.read())


def _get_json(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=CTX) as resp:
        return json.loads(resp.read())


def authenticate() -> str:
    print("[1/3] Authenticating...")
    resp = _post_json(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        {"email": EMAIL, "password": PASSWORD},
        {"apikey": SUPABASE_ANON_KEY},
    )
    token = resp.get("access_token")
    if not token:
        print(f"  FAILED: {resp}")
        sys.exit(1)
    print("  OK — token acquired")
    return token


def find_case_with_analysis(token: str, case_id: str | None) -> str:
    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"}

    if case_id:
        print(f"\n[2/3] Using provided case: {case_id}")
        return case_id

    print("\n[2/3] Finding a case with completed analysis...")
    cases = _get_json(
        f"{SUPABASE_URL}/rest/v1/cases?select=id,client_name,status"
        "&status=eq.completed&order=updated_at.desc&limit=5",
        headers,
    )
    if not cases:
        print("  No completed cases found.")
        sys.exit(1)

    print("  Available cases:")
    for c in cases:
        print(f"    {c['id'][:8]}...  {c.get('client_name','?'):30s}  status={c['status']}")

    selected = cases[0]["id"]
    print(f"  Selected: {selected}")
    return selected


def stream_gap_analysis(token: str, case_id: str, force_refresh: bool = False):
    print()
    print("=" * 60)
    print(f"[3/3] Streaming POST /api/analysis/analyze-gaps/stream")
    if force_refresh:
        print("     (force_refresh=true — bypassing cache)")
    print("=" * 60)
    print()

    url = f"{API_BASE}/api/analysis/analyze-gaps/stream"
    body = json.dumps({"case_id": case_id, "force_refresh": force_refresh}).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )

    t_start = time.time()

    try:
        resp = urllib.request.urlopen(req, timeout=300, context=CTX)
    except Exception as e:
        print(f"  x Connection failed after {time.time() - t_start:.1f}s: {e}")
        sys.exit(1)

    t_response = time.time()
    print(f"  HTTP {resp.status} — response headers after {t_response - t_start:.1f}s")

    phases = {}
    buffer = ""
    result_data = None

    try:
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break

            buffer += chunk.decode("utf-8", errors="replace")
            lines = buffer.split("\n")
            buffer = lines.pop()

            for line in lines:
                if not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type", "")
                elapsed = time.time() - t_start

                if event_type == "phase":
                    phase = data.get("phase", "?")
                    message = data.get("message", "")
                    doc_count = data.get("doc_count")
                    gaps_found = data.get("gaps_found")
                    phases[phase] = elapsed

                    extra = ""
                    if doc_count is not None:
                        extra = f" (docs={doc_count})"
                    if gaps_found is not None:
                        extra = f" (gaps={gaps_found})"

                    print(f"  [{elapsed:6.1f}s] phase={phase:15s} {message}{extra}")

                elif event_type == "result":
                    result_data = data.get("data", {})
                    server_elapsed = data.get("elapsed")
                    total_gaps = result_data.get("total_gaps", "?")
                    score = result_data.get("overall_completeness_score", "?")
                    categories = result_data.get("gaps_by_category", {})

                    se_str = f"{server_elapsed:.1f}s" if server_elapsed else "n/a"
                    print(f"\n  RESULT at {elapsed:.1f}s (server_elapsed={se_str})")
                    print(f"    total_gaps:       {total_gaps}")
                    print(f"    completeness:     {score}")
                    print(f"    categories:")
                    for cat, items in categories.items():
                        if isinstance(items, list) and items:
                            print(f"      {cat}: {len(items)} gaps")

                elif event_type == "error":
                    print(f"\n  ERROR at {elapsed:.1f}s: {data.get('error', '?')}")

        resp.close()

    except KeyboardInterrupt:
        print(f"\n  Interrupted after {time.time() - t_start:.1f}s")
    except Exception as e:
        print(f"  Failed after {time.time() - t_start:.1f}s: {e}")

    # Summary
    total = time.time() - t_start
    print()
    print("=" * 60)
    print("  GAP ANALYSIS LATENCY SUMMARY")
    print("=" * 60)
    print(f"  Total elapsed:         {total:.1f}s")
    print(f"  HTTP response start:   {t_response - t_start:.1f}s")
    print()
    if phases:
        print("  Phase timings:")
        prev_t = 0
        for phase, t in sorted(phases.items(), key=lambda x: x[1]):
            delta = t - prev_t
            print(f"    {phase:20s} at {t:6.1f}s  (+{delta:.1f}s)")
            prev_t = t
    print()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    case_id = args[0] if args else None
    token = authenticate()
    case_id = find_case_with_analysis(token, case_id)
    stream_gap_analysis(token, case_id, force_refresh=force)


if __name__ == "__main__":
    main()
