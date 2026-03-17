#!/usr/bin/env python3
"""Test that streaming analysis save produces correct structured data.

Streams the analysis, captures the server-side content from the done event,
calls the save endpoint, then verifies case_analysis fields are populated.
"""

import json
import re
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


def authenticate():
    data = json.dumps({"email": EMAIL, "password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        data=data,
        headers={"Content-Type": "application/json", "apikey": SUPABASE_ANON_KEY},
    )
    resp = urllib.request.urlopen(req, context=CTX)
    return json.loads(resp.read())["access_token"]


def stream_and_save(token, case_id):
    url = f"{API_BASE}/api/analysis/stream/{case_id}"
    print(f"[1] Streaming {url}...")

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    })

    t_start = time.time()
    resp = urllib.request.urlopen(req, timeout=700, context=CTX)
    print(f"    HTTP {resp.status} after {time.time()-t_start:.1f}s")

    server_content = None
    token_count = 0
    preview_tokens = 0
    buffer = ""

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
                d = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            if d.get("phase") == "preview" and "token" in d:
                preview_tokens += 1

            if d.get("token") and d.get("phase") != "preview":
                token_count += 1
                if token_count % 1000 == 0:
                    print(f"    ... {token_count} tokens ({time.time()-t_start:.0f}s)")

            if d.get("done") and d.get("phase") != "preview":
                server_content = d.get("content", "")
                elapsed = time.time() - t_start
                print(f"    Done at {elapsed:.1f}s | tokens={token_count} | preview_tokens={preview_tokens}")
                print(f"    server_content: {len(server_content)} chars")

                headers_found = re.findall(r"## .+", server_content)
                print(f"    ## headers: {headers_found}")

                resp.close()
                return server_content

    print("    WARNING: Stream ended without done event")
    resp.close()
    return None


def save_analysis(token, case_id, content):
    print(f"\n[2] Saving analysis ({len(content)} chars)...")
    save_url = f"{API_BASE}/api/analysis/stream/{case_id}/save"
    save_data = json.dumps({"content": content}).encode()
    req = urllib.request.Request(save_url, data=save_data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=60, context=CTX)
        body = json.loads(resp.read())
        print(f"    Save OK: {resp.status}")
        return True
    except urllib.error.HTTPError as e:
        print(f"    Save FAILED: {e.code}")
        print(f"    {e.read().decode()[:500]}")
        return False
    except Exception as e:
        print(f"    Save error: {e}")
        return False


def verify_saved(token, case_id):
    print("\n[3] Verifying saved data...")
    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"}
    url = (
        f"{SUPABASE_URL}/rest/v1/analysis_results"
        f"?case_id=eq.{case_id}&status=eq.completed"
        f"&order=created_at.desc&limit=1"
    )
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, context=CTX)
    results = json.loads(resp.read())

    if not results:
        print("    NO completed analysis found!")
        return False

    r = results[0]
    result = r.get("result", {})
    if isinstance(result, str):
        result = json.loads(result)

    ca = result.get("case_analysis")
    if isinstance(ca, str):
        try:
            ca = json.loads(ca)
        except json.JSONDecodeError:
            print(f"    Failed to parse case_analysis: {ca[:200]}")
            return False

    if not ca:
        print("    case_analysis is empty!")
        return False

    summary_len = len(ca.get("case_summary", ""))
    practice = ca.get("practice_area", "<missing>")
    issues = ca.get("key_issues", [])
    statutes = ca.get("relevant_statutes", [])

    print(f"    case_summary: {'YES' if summary_len > 0 else 'EMPTY'} ({summary_len} chars)")
    print(f"    practice_area: {practice}")
    print(f"    key_issues: {len(issues)} items")
    for ki in issues[:3]:
        print(f"      - {ki[:100]}")
    print(f"    relevant_statutes: {len(statutes)} items")
    for s in statutes[:3]:
        print(f"      - {s}")

    sa = result.get("streaming_analysis", "")
    sa_headers = re.findall(r"## .+", sa)
    print(f"    streaming_analysis: {len(sa)} chars, ## headers: {sa_headers}")

    ok = summary_len > 0 and len(issues) > 0
    print(f"\n    RESULT: {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    case_id = sys.argv[1] if len(sys.argv) > 1 else "64b1cd3f-28d9-4dc7-b411-71f11cf0077e"
    token = authenticate()
    print(f"Authenticated. Case: {case_id}\n")

    content = stream_and_save(token, case_id)
    if not content:
        print("FAILED: No content from stream")
        sys.exit(1)

    if not save_analysis(token, case_id, content):
        print("FAILED: Save endpoint returned error")
        sys.exit(1)

    if not verify_saved(token, case_id):
        print("\nFAILED: Saved data is incomplete")
        sys.exit(1)

    print("\nSUCCESS: Analysis saved with complete structured data")


if __name__ == "__main__":
    main()
