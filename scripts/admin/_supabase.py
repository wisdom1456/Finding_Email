"""Shared helpers for admin scripts.

The 1000-row pagination cap on PostgREST silently truncates results.
This module's ``paginate()`` works around that by walking ranges until
the response is short.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, List

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

from supabase import Client, create_client  # noqa: E402


def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not (url and key):
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY missing", file=sys.stderr)
        sys.exit(1)
    return create_client(url, key)


PAGE = 1000


def paginate(query_builder: Callable[[int, int], Any]) -> List[dict]:
    """Repeatedly call query_builder(start, end) until an empty page.

    Usage:
        rows = paginate(lambda s, e:
            sb.table('documents').select('id, status').order('id').range(s, e))
    """
    all_rows: List[dict] = []
    page = 0
    while True:
        start = page * PAGE
        end = start + PAGE - 1
        resp = query_builder(start, end).execute()
        rows = resp.data or []
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < PAGE:
            break
        page += 1
    return all_rows
