#!/usr/bin/env python3
"""Stream latency diagnostic — measures time-to-first-token on production.

Usage:
    python3 scripts/test_stream_latency.py              # auto-picks a case
    python3 scripts/test_stream_latency.py <case_id>    # specific case

After running, check Vercel logs for [STREAM:*] lines:
    npx vercel logs https://finding-emails.vercel.app --follow
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


def _get_json(url: str, headers: dict) -> tuple:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=CTX) as resp:
        body = resp.read()
        return json.loads(body), len(body)


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
    print(f"  OK — token acquired")
    return token


def find_case(token: str, case_id: str | None) -> str:
    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"}

    if case_id:
        print(f"\n[2/4] Using provided case: {case_id}")
        return case_id

    print("\n[2/4] Finding a case with documents...")
    cases, _ = _get_json(
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


def measure_payload(token: str, case_id: str):
    print("\n[3/4] Measuring document payload size...")
    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"}

    t0 = time.time()
    docs, resp_bytes = _get_json(
        f"{SUPABASE_URL}/rest/v1/documents?select=id,file_name,extracted_text"
        f"&case_id=eq.{case_id}&limit=200",
        headers,
    )
    fetch_time = time.time() - t0

    total_bytes = 0
    max_bytes = 0
    nonempty = 0
    for d in docs:
        t = d.get("extracted_text") or ""
        b = len(t.encode("utf-8"))
        total_bytes += b
        if b > max_bytes:
            max_bytes = b
        if b > 0:
            nonempty += 1
        label = d.get("file_name", "?")[:50]
        print(f"    {label:50s}  {b:>10,} bytes")

    print()
    print(f"    docs: {nonempty}/{len(docs)} with text")
    print(f"    total extracted_text: {total_bytes:,} bytes ({total_bytes/1024/1024:.1f} MB)")
    print(f"    max single doc: {max_bytes:,} bytes ({max_bytes/1024:.0f} KB)")
    print(f"    supabase response: {resp_bytes:,} bytes")
    print(f"    fetch time: {fetch_time:.1f}s")
    print()
    print(f"    ⚠  The /stream endpoint fetches this same payload.")
    print(f"       If total > 10MB, TEXT_FETCH will be slow.")


def stream_analysis(token: str, case_id: str):
    print()
    print("═" * 50)
    print(f"[4/4] Streaming /api/analysis/stream/{case_id}")
    print("═" * 50)
    print()

    url = f"{API_BASE}/api/analysis/stream/{case_id}"
    print(f"  URL: {url}")
    print(f"  Started: {time.strftime('%H:%M:%S')}")
    print()

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    })

    t_start = time.time()

    try:
        resp = urllib.request.urlopen(req, timeout=700, context=CTX)
    except Exception as e:
        print(f"  ✗ Connection failed after {time.time() - t_start:.1f}s: {e}")
        sys.exit(1)

    t_response = time.time()
    print(f"  ✓ HTTP {resp.status} — response headers after {t_response - t_start:.1f}s")

    first_data = False
    first_thinking = False
    first_token = False
    token_count = 0
    buffer = ""
    last_heartbeat = ""

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

                if not first_data:
                    first_data = True
                    print(f"  ✓ First SSE event after {time.time() - t_start:.1f}s")

                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                # Inventory event (quick preview)
                if data.get("phase") == "inventory":
                    print(f"  📋 Document inventory: {data.get('total', '?')} documents")

                # Preview tokens (quick preview via gpt-5-mini)
                if data.get("phase") == "preview" and "token" in data:
                    if not hasattr(stream_analysis, '_preview_started'):
                        stream_analysis._preview_started = True
                        t_preview = time.time() - t_start
                        print(f"  ✓ PREVIEW FIRST TOKEN at {t_preview:.1f}s (gpt-5-mini)")

                if data.get("phase") == "preview" and data.get("done"):
                    t_preview_done = time.time() - t_start
                    print(f"  ✓ Preview complete at {t_preview_done:.1f}s")

                if data.get("phase") == "preview_classifications":
                    cls_list = data.get("classifications", [])
                    print(f"  📊 Document classifications: {len(cls_list)} documents classified")
                    for c in cls_list[:5]:
                        print(f"    {c.get('document_name','?'):40s}  {c.get('relevance_level','?'):12s}  {c.get('document_type','?')}")
                    if len(cls_list) > 5:
                        print(f"    ... and {len(cls_list) - 5} more")

                # Section progress
                if data.get("phase") == "section":
                    print(f"    § Section {data.get('index','?')}/{data.get('total','?')}: {data.get('section','?')}")

                # Thinking heartbeats
                if data.get("phase") == "thinking":
                    if not first_thinking:
                        first_thinking = True
                        print(f"  ◐ Thinking phase started")
                    elapsed = data.get("elapsed", "?")
                    last_heartbeat = f"{elapsed}s"
                    # Print periodic updates
                    if isinstance(elapsed, int) and elapsed % 30 == 0 and elapsed > 0:
                        print(f"    ... still thinking ({elapsed}s)")

                # First token transition
                if data.get("phase") == "streaming" and not first_token:
                    first_token = True
                    thinking_time = data.get("thinking_time", "?")
                    total = time.time() - t_start
                    print(f"  ✓ FIRST TOKEN at {total:.1f}s (server thinking_time={thinking_time}s)")
                    print()

                # Count tokens
                if "token" in data:
                    token_count += 1
                    if token_count <= 3:
                        preview = data["token"][:80].replace("\n", "\\n")
                        print(f"    token[{token_count}]: \"{preview}\"")
                    elif token_count == 4:
                        print("    ... (suppressing further tokens)")
                    # Print progress every 500 tokens
                    elif token_count % 500 == 0:
                        print(f"    ... {token_count} tokens ({time.time() - t_start:.0f}s)")

                # Stream heartbeats
                if "heartbeat" in data:
                    pass  # silent

                # Done — the final done event has 'content' or 'docs_in_scope';
                # preview done has 'phase': 'preview' and should NOT terminate.
                if data.get("done") and data.get("phase") != "preview":
                    total = time.time() - t_start
                    print()
                    print(f"  ✓ Stream complete at {total:.1f}s")
                    print(f"    tokens={token_count}")
                    print(f"    docs_in_scope={data.get('docs_in_scope', '?')}")
                    print(f"    docs_omitted={data.get('docs_omitted', '?')}")
                    print(f"    context_tokens={data.get('context_tokens', '?')}")
                    resp.close()
                    _print_summary(t_start, t_response)
                    return

                # Error
                if data.get("error"):
                    print(f"  ✗ ERROR: {data['error']}")
                    resp.close()
                    _print_summary(t_start, t_response)
                    return

    except KeyboardInterrupt:
        print(f"\n  ⚠ Interrupted after {time.time() - t_start:.1f}s")
        print(f"    tokens received: {token_count}")
        print(f"    last heartbeat: {last_heartbeat}")
    except Exception as e:
        print(f"  ✗ Failed after {time.time() - t_start:.1f}s: {e}")

    _print_summary(t_start, t_response)


def _print_summary(t_start: float, t_response: float):
    total = time.time() - t_start
    print()
    print("═" * 50)
    print("  CLIENT-SIDE SUMMARY")
    print("═" * 50)
    print(f"  Total elapsed:         {total:.1f}s")
    print(f"  HTTP response start:   {t_response - t_start:.1f}s")
    print()
    print("  Now check Vercel logs for [STREAM:*] breakdown:")
    print("    npx vercel logs finding-emails --follow")
    print()
    print("  Fill in the interpretation template:")
    print("    CASE_FETCH         = __s")
    print("    TEXT_FETCH         = __s  (total_text_bytes=__)")
    print("    DOC_SUMMARIES      = __s  (since entry)")
    print("    CONTEXT_BUILT      = __s")
    print("    PROMPT_STATS       = prompt_chars=__")
    print("    LLM_START          = __s  (since entry)")
    print("    FIRST_TOKEN        = thinking=__s  total=__s")
    print()


def main():
    case_id = sys.argv[1] if len(sys.argv) > 1 else None
    token = authenticate()
    case_id = find_case(token, case_id)
    measure_payload(token, case_id)
    stream_analysis(token, case_id)


if __name__ == "__main__":
    main()
