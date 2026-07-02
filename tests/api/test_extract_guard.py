"""Guard: POST /documents/{id}/extract must not re-extract healthy docs.

Note on adaptation from the task brief: the route handler itself is named
`trigger_extraction` (decorated with @router.post("/{document_id}/extract")),
so it cannot be patched without replacing the endpoint. The route delegates
the real extraction work to `_trigger_extraction_inner` (imported from
legal_portal.services.documents.extraction_service), so that's what these
tests patch. The mock document also includes a `cases.user_id` field because
the guard performs its own ownership-verified fetch before deciding to skip.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_doc(extracted: bool):
    return {
        "id": "doc-1",
        "case_id": "case-1",
        "status": "ready" if extracted else "pending",
        "extracted_text": "existing text" if extracted else None,
        "extracted_at": "2026-01-01T00:00:00Z" if extracted else None,
        "storage_path": "u/c/f.pdf",
        "cases": {"user_id": "user-1"},
    }


def _client_with_doc(doc):
    """Build a TestClient with auth + supabase deps overridden."""
    from legal_portal.api.main import app
    from legal_portal.api.routes import documents as documents_module

    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [doc]

    app.dependency_overrides[documents_module.get_current_user] = lambda: {"id": "user-1"}
    app.dependency_overrides[documents_module.get_user_supabase_client] = lambda: supabase
    return TestClient(app)


def test_extract_skips_already_extracted_doc():
    client = _client_with_doc(_make_doc(extracted=True))
    with patch(
        "legal_portal.api.routes.documents._trigger_extraction_inner"
    ) as mock_extract:
        resp = client.post("/api/documents/doc-1/extract")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("skipped") is True
    mock_extract.assert_not_called()


def test_extract_runs_when_forced():
    client = _client_with_doc(_make_doc(extracted=True))
    with patch(
        "legal_portal.api.routes.documents._trigger_extraction_inner"
    ) as mock_extract:
        mock_extract.return_value = {"success": True}
        resp = client.post("/api/documents/doc-1/extract?force=true")
    assert resp.status_code == 200
    mock_extract.assert_called_once()


def test_extract_runs_with_force_method():
    client = _client_with_doc(_make_doc(extracted=True))
    with patch(
        "legal_portal.api.routes.documents._trigger_extraction_inner"
    ) as mock_extract:
        mock_extract.return_value = {"success": True}
        resp = client.post("/api/documents/doc-1/extract?force_method=vision")
    assert resp.status_code == 200
    mock_extract.assert_called_once()


def test_extract_runs_for_unextracted_doc():
    client = _client_with_doc(_make_doc(extracted=False))
    with patch(
        "legal_portal.api.routes.documents._trigger_extraction_inner"
    ) as mock_extract:
        mock_extract.return_value = {"success": True}
        resp = client.post("/api/documents/doc-1/extract")
    assert resp.status_code == 200
    mock_extract.assert_called_once()


def test_guard_fetch_failure_returns_500_with_extraction_error_detail():
    """A generic failure in the guard's own fetch must preserve the pre-guard
    response shape: HTTPException(500, detail="Error extracting text: ...")
    rendered as {"detail": ...} — not the app-wide generic error envelope."""
    from legal_portal.api.main import app
    from legal_portal.api.routes import documents as documents_module

    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception(
        "connection reset by peer"
    )

    app.dependency_overrides[documents_module.get_current_user] = lambda: {"id": "user-1"}
    app.dependency_overrides[documents_module.get_user_supabase_client] = lambda: supabase
    client = TestClient(app, raise_server_exceptions=False)

    with patch(
        "legal_portal.api.routes.documents._trigger_extraction_inner"
    ) as mock_extract:
        resp = client.post("/api/documents/doc-1/extract")

    assert resp.status_code == 500
    body = resp.json()
    assert body.get("detail", "").startswith("Error extracting text:")
    mock_extract.assert_not_called()
