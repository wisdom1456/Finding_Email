#!/usr/bin/env python3
"""Demand letter streaming latency diagnostic — measures TTFT and phase timing.

Usage:
    python3 scripts/test_letter_latency.py                          # auto-picks case
    python3 scripts/test_letter_latency.py <case_id>                # specific case
    python3 scripts/test_letter_latency.py <case_id> <party_name>   # specific party
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


def _get_json(url: str, headers: dict):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=CTX) as resp:
        return json.loads(resp.read())


def authenticate() -> str:
    print("[1/4] Authenticating...")
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


def find_analysis(token: str, case_id: str | None) -> tuple[str, str, dict]:
    """Find a case with completed analysis and return (case_id, analysis_id, msr)."""
    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"}

    if case_id:
        print(f"\n[2/4] Using provided case: {case_id}")
    else:
        print("\n[2/4] Finding a case with completed analysis...")
        cases = _get_json(
            f"{SUPABASE_URL}/rest/v1/cases?select=id,client_name,status"
            "&status=eq.completed&order=updated_at.desc&limit=5",
            headers,
        )
        if not cases:
            print("  No completed cases found.")
            sys.exit(1)
        case_id = cases[0]["id"]
        print(f"  Selected case: {case_id[:8]}... ({cases[0].get('client_name', '?')})")

    # Fetch analysis results
    results = _get_json(
        f"{SUPABASE_URL}/rest/v1/analysis_results?select=id,result"
        f"&case_id=eq.{case_id}&order=created_at.desc&limit=1",
        headers,
    )
    if not results:
        print("  No analysis results found for this case.")
        sys.exit(1)

    analysis_id = results[0]["id"]
    result = results[0].get("result", {})
    msr = result.get("multi_stage_result", {})
    print(f"  Analysis ID: {analysis_id[:8]}...")

    return case_id, analysis_id, msr


def find_target_party(msr: dict, party_name: str | None) -> str:
    """Extract a target party name from analysis results."""
    if party_name:
        print(f"\n[3/4] Using provided party: {party_name}")
        return party_name

    print("\n[3/4] Finding target party from analysis...")

    # Try fact_matrix.parties
    fm = msr.get("fact_matrix", {})
    parties = fm.get("parties", [])
    if parties:
        # Pick first non-client party, or just the first
        for p in parties:
            role = (p.get("role") or "").lower()
            if role not in ("client", "plaintiff", "claimant"):
                name = p.get("name", "Unknown Party")
                print(f"  Found opposing party: {name} (role={role})")
                return name
        # Fallback to first party
        name = parties[0].get("name", "Unknown Party")
        print(f"  Using first party: {name}")
        return name

    # Fallback
    print("  No parties found, using 'Opposing Party'")
    return "Opposing Party"


def stream_letter(token: str, analysis_id: str, target_party: str):
    print()
    print("=" * 60)
    print(f"[4/4] Streaming GET /api/letter/{analysis_id}/demand-letter/stream")
    print("=" * 60)
    print()

    params = urllib.parse.urlencode({
        "target_party_name": target_party,
        "demand_deadline": "10 business days",
        "schema_version": 2,
    })
    url = f"{API_BASE}/api/letter/{analysis_id}/demand-letter/stream?{params}"
    print(f"  URL: {url[:100]}...")
    print(f"  Party: {target_party}")
    print(f"  Started: {time.strftime('%H:%M:%S')}")
    print()

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    })

    t_start = time.time()

    try:
        resp = urllib.request.urlopen(req, timeout=300, context=CTX)
    except Exception as e:
        print(f"  x Connection failed after {time.time() - t_start:.1f}s: {e}")
        sys.exit(1)

    t_response = time.time()
    print(f"  HTTP {resp.status} — response headers after {t_response - t_start:.1f}s")

    first_token = False
    token_count = 0
    phases = {}
    word_count = 0
    buffer = ""

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

                elapsed = time.time() - t_start
                event = data.get("event") or data.get("type", "")

                # Phase events
                if event == "phase":
                    phase = data.get("phase", "?")
                    message = data.get("message", "")
                    percent = data.get("percent", "")
                    phases[phase] = elapsed
                    print(f"  [{elapsed:6.1f}s] phase={phase:20s} {message} ({percent}%)")

                # Token events
                elif event == "token" or "token" in data:
                    tok = data.get("token", "")
                    if tok:
                        token_count += 1
                        if not first_token:
                            first_token = True
                            t_first = elapsed
                            print(f"  [{elapsed:6.1f}s] FIRST TOKEN")
                            preview = tok[:80].replace("\n", "\\n")
                            print(f"    token[1]: \"{preview}\"")
                        elif token_count <= 3:
                            preview = tok[:80].replace("\n", "\\n")
                            print(f"    token[{token_count}]: \"{preview}\"")
                        elif token_count == 4:
                            print("    ... (suppressing further tokens)")
                        elif token_count % 500 == 0:
                            print(f"    ... {token_count} tokens ({elapsed:.0f}s)")

                # Heartbeat
                elif event == "heartbeat":
                    pass

                # Done
                elif data.get("done") or event == "done":
                    print(f"\n  Stream complete at {elapsed:.1f}s")
                    print(f"    tokens={token_count}")
                    resp.close()
                    _print_summary(t_start, t_response, phases, token_count, first_token)
                    return

                # Error
                elif event == "error" or data.get("error"):
                    recoverable = data.get("recoverable", False)
                    label = "WARNING (recoverable)" if recoverable else "ERROR"
                    print(f"  [{elapsed:6.1f}s] {label}: {data.get('error', '?')}")

    except KeyboardInterrupt:
        print(f"\n  Interrupted after {time.time() - t_start:.1f}s")
        print(f"    tokens received: {token_count}")
    except Exception as e:
        print(f"  Failed after {time.time() - t_start:.1f}s: {e}")

    _print_summary(t_start, t_response, phases, token_count, first_token)


def _print_summary(t_start, t_response, phases, token_count, first_token):
    total = time.time() - t_start
    print()
    print("=" * 60)
    print("  DEMAND LETTER LATENCY SUMMARY")
    print("=" * 60)
    print(f"  Total elapsed:         {total:.1f}s")
    print(f"  HTTP response start:   {t_response - t_start:.1f}s")
    print(f"  Total tokens:          {token_count}")
    print()
    if phases:
        print("  Phase timings:")
        prev_t = 0
        for phase, t in sorted(phases.items(), key=lambda x: x[1]):
            delta = t - prev_t
            print(f"    {phase:25s} at {t:6.1f}s  (+{delta:.1f}s)")
            prev_t = t
    print()


def main():
    import urllib.parse

    case_id = sys.argv[1] if len(sys.argv) > 1 else None
    party_name = sys.argv[2] if len(sys.argv) > 2 else None

    token = authenticate()
    case_id, analysis_id, msr = find_analysis(token, case_id)
    target_party = find_target_party(msr, party_name)
    stream_letter(token, analysis_id, target_party)


if __name__ == "__main__":
    main()
