"""Bulk-extract full-coverage fix (Phase 1).

Covers the two defects behind the Erica Corley silent-skip incident:
  1. The retry-set query must exclude non-retryable statuses (+ junk) so the
     frontend coverage loop can converge without re-selecting docs it can never
     extract.
  2. Per-doc failures/skips (timeout, exception, large-PDF) must be durably
     persisted to the document row (status=extraction_failed + extraction_error)
     so they leave the retry-set and surface to the user — no silent failures.

Harness mirrors tests/api/test_extract_guard.py: FastAPI TestClient with the
auth + supabase dependencies overridden, and _trigger_extraction_inner patched.
"""

import asyncio
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _chain(data):
    """A Supabase query-builder mock where every filter method returns self,
    so assertions don't depend on the exact chain order."""
    c = MagicMock()
    for m in ("select", "neq", "eq", "or_", "order", "limit", "range"):
        getattr(c, m).return_value = c
    c.execute.return_value.data = data
    return c


def _client(query_docs):
    from legal_portal.api.main import app
    from legal_portal.api.routes import documents as dm

    user_sb = MagicMock()
    user_sb.table.return_value = _chain(query_docs)
    service_sb = MagicMock()  # .update(...).eq(...).execute() auto-mocks

    app.dependency_overrides[dm.get_current_user] = lambda: {"id": "user-1"}
    app.dependency_overrides[dm.get_user_supabase_client] = lambda: user_sb
    app.dependency_overrides[dm.get_supabase_client] = lambda: service_sb
    return TestClient(app), user_sb, service_sb


def test_bulk_query_excludes_nonretryable_statuses():
    client, user_sb, _ = _client([])
    with patch("legal_portal.api.routes.documents._trigger_extraction_inner"):
        resp = client.post("/api/documents/bulk-extract", json={"case_id": "case-1"})
    assert resp.status_code == 200
    chain = user_sb.table.return_value
    excluded = {a.args[1] for a in chain.neq.call_args_list if a.args and a.args[0] == "status"}
    # DocumentStatus is a str-Enum, so members compare/hash equal to their values.
    assert {"skipped", "duplicate", "corrupted", "download_failed", "extraction_failed"} <= excluded


def test_timeout_marks_document_extraction_failed():
    docs = [{"id": "d1", "file_name": "a.pdf", "file_type": "application/pdf",
             "storage_path": "p", "file_size": 1000}]
    client, _, service_sb = _client(docs)
    with patch("legal_portal.api.routes.documents._trigger_extraction_inner",
               side_effect=asyncio.TimeoutError()):
        resp = client.post("/api/documents/bulk-extract", json={"case_id": "case-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["failed_count"] == 1
    payload = service_sb.table.return_value.update.call_args.args[0]
    assert payload["status"] == "extraction_failed"
    assert "extraction_error" in payload


def test_large_pdf_marks_extraction_failed_and_reports_remaining():
    docs = [{"id": "big", "file_name": "big.pdf", "file_type": "application/pdf",
             "storage_path": "p", "file_size": 20 * 1024 * 1024}]
    client, _, service_sb = _client(docs)
    with patch("legal_portal.api.routes.documents._trigger_extraction_inner") as inner:
        resp = client.post("/api/documents/bulk-extract", json={"case_id": "case-1"})
    inner.assert_not_called()
    body = resp.json()
    assert body["failed_count"] == 1
    assert body["remaining"] == 0
    payload = service_sb.table.return_value.update.call_args.args[0]
    assert payload["status"] == "extraction_failed"
    assert "too large" in payload["extraction_error"].lower()
