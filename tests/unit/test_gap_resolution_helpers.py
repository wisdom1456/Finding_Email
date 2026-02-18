"""Unit tests for gap resolution selective refresh helpers."""

from __future__ import annotations

from legal_portal.api.routes import analysis as analysis_routes
from legal_portal.api.routes.analysis import (
    GapResolutionItemRequest,
    GapResolutionRefreshRequest,
    _build_case_document_state_hash,
    _build_gap_analysis_input_hash,
    _build_gap_resolution_hash,
    _build_resolution_context,
    _build_signature_evidence,
    _build_supporting_document_hash,
    _derive_signature_detection_for_gap_doc,
    _infer_signature_detection_from_text,
)


def _make_request(resolutions, attached_document_ids=None, notes=None):
    return GapResolutionRefreshRequest(
        case_id="case-123",
        resolutions=resolutions,
        attached_document_ids=attached_document_ids or [],
        global_resolution_notes=notes,
    )


def test_gap_resolution_hash_is_stable_across_ordering():
    """Hash should stay stable for semantically identical payloads."""
    req_a = _make_request(
        resolutions=[
            GapResolutionItemRequest(
                gap_id="gap_b",
                resolution_text="Payment receipt attached",
                mark_resolved=True,
                related_document_ids=["doc-2", "doc-1"],
            ),
            GapResolutionItemRequest(
                gap_id="gap_a",
                resolution_text="Signed agreement was uploaded",
                mark_resolved=True,
                related_document_ids=[],
            ),
        ],
        attached_document_ids=["doc-9", "doc-3"],
        notes="General context",
    )

    req_b = _make_request(
        resolutions=[
            GapResolutionItemRequest(
                gap_id="gap_a",
                resolution_text="Signed agreement was uploaded",
                mark_resolved=True,
                related_document_ids=[],
            ),
            GapResolutionItemRequest(
                gap_id="gap_b",
                resolution_text="Payment receipt attached",
                mark_resolved=True,
                related_document_ids=["doc-1", "doc-2"],
            ),
        ],
        attached_document_ids=["doc-3", "doc-9"],
        notes="General context",
    )

    assert _build_gap_resolution_hash(req_a) == _build_gap_resolution_hash(req_b)


def test_resolution_context_includes_prior_gap_and_resolution_text():
    """Context should carry prior gap details and user resolution payload."""
    request = _make_request(
        resolutions=[
            GapResolutionItemRequest(
                gap_id="gap_sig",
                resolution_text="The PDF is digitally signed with DocuSign envelope ID.",
                mark_resolved=True,
            )
        ],
        notes="Client provided updated supporting records.",
    )
    existing_gap = {
        "gaps_by_category": {
            "missing_document": [
                {
                    "gap_id": "gap_sig",
                    "title": "Missing executed subscription agreement",
                    "severity": "critical",
                    "category": "missing_document",
                }
            ]
        }
    }
    supporting_docs = [
        {
            "id": "doc-1",
            "file_name": "Subscription Agreement.pdf",
            "signature_detection": {"status": "signed", "confidence": "high"},
            "text_excerpt": "Counterpart Signature Page ... DocuSign Envelope ID: 123",
        }
    ]

    context = _build_resolution_context(existing_gap, request, supporting_docs)

    assert "gap_id: gap_sig" in context
    assert "Missing executed subscription agreement" in context
    assert "DocuSign envelope ID" in context or "DocuSign Envelope ID" in context
    assert "ATTACHED SUPPORTING DOCUMENT EXCERPTS" in context
    assert "signature_detection" in context


def test_infer_signature_detection_from_text_detects_signed_markers():
    """Legacy extracted text with strong markers should be treated as signed."""
    text = """
    Subscription Agreement
    Counterpart Signature Page
    Signed by: Erica Corley
    Date Signed: 01/13/2026
    DocuSign Envelope ID: ABC-123
    """

    result = _infer_signature_detection_from_text(text)

    assert result is not None
    assert result["status"] == "signed"
    assert result["has_signature_markers"] is True
    assert result["signature_marker_count"] >= 3
    assert result["signing_date"] == "2026-01-13"
    assert "DocuSign envelope marker" in result["indicators"]


def test_infer_signature_detection_from_text_ignores_single_blank_signature_label():
    """A lone placeholder signature field should not imply an executed document."""
    text = "Borrower Signature: ____________________"
    result = _infer_signature_detection_from_text(text)
    assert result is None


def test_supporting_document_hash_stable_across_row_ordering():
    """Supporting-doc hash should be order-invariant for equivalent rows."""
    rows_a = [
        {
            "id": "doc-b",
            "updated_at": "2026-02-09T01:00:00Z",
            "extracted_text": "Payment confirmation attached.",
            "manual_text": None,
            "metadata": {"signature_detection": {"status": "not_detected"}},
        },
        {
            "id": "doc-a",
            "updated_at": "2026-02-09T00:00:00Z",
            "extracted_text": "DocuSign Envelope ID: XYZ",
            "manual_text": None,
            "metadata": {"signature_detection": {"status": "signed"}},
        },
    ]
    rows_b = [rows_a[1], rows_a[0]]

    hash_a = _build_supporting_document_hash(rows_a, ["doc-a", "doc-b"])
    hash_b = _build_supporting_document_hash(rows_b, ["doc-b", "doc-a"])
    assert hash_a == hash_b


def test_supporting_document_hash_changes_when_text_changes():
    """Hash should change when supporting doc content changes."""
    rows = [
        {
            "id": "doc-a",
            "updated_at": "2026-02-09T00:00:00Z",
            "extracted_text": "Wire receipt amount 120000",
            "manual_text": None,
            "metadata": {},
        }
    ]
    changed_rows = [
        {
            "id": "doc-a",
            "updated_at": "2026-02-09T00:00:00Z",
            "extracted_text": "Wire receipt amount 125000",
            "manual_text": None,
            "metadata": {},
        }
    ]

    original = _build_supporting_document_hash(rows, ["doc-a"])
    changed = _build_supporting_document_hash(changed_rows, ["doc-a"])
    assert original != changed


def test_case_document_state_hash_changes_when_signature_status_changes():
    """Case-document state hash should invalidate cache when signature status changes."""
    docs_unsigned = [
        {
            "id": "doc-a",
            "updated_at": "2026-02-09T00:00:00Z",
            "status": "ready",
            "file_name": "Subscription Agreement.pdf",
            "file_type": "application/pdf",
            "manual_text": "",
            "extracted_text": "Subscription Agreement text",
            "metadata": {"signature_detection": {"status": "not_detected"}},
        }
    ]
    docs_signed = [
        {
            **docs_unsigned[0],
            "metadata": {"signature_detection": {"status": "signed", "confidence": "high"}},
        }
    ]

    unsigned_hash = _build_case_document_state_hash(docs_unsigned)
    signed_hash = _build_case_document_state_hash(docs_signed)

    assert unsigned_hash != signed_hash


def test_signature_evidence_collects_metadata_and_sorts_by_filename():
    """Signature evidence should include parsed rows and preserve authoritative status fields."""
    docs = [
        {
            "id": "doc-2",
            "file_name": "B.pdf",
            "file_type": "application/pdf",
            "manual_text": "",
            "extracted_text": "Subscription Agreement\nSigned by: A",
            "metadata": {"signature_detection": {"status": "signed", "confidence": "medium"}},
        },
        {
            "id": "doc-1",
            "file_name": "A.pdf",
            "file_type": "application/pdf",
            "manual_text": "",
            "extracted_text": "Borrower Signature: _______",
            "metadata": {"signature_detection": {"status": "not_detected", "confidence": "high"}},
        },
    ]

    evidence = _build_signature_evidence(docs)

    assert [row["file_name"] for row in evidence] == ["A.pdf", "B.pdf"]
    assert evidence[1]["status"] == "signed"
    assert "subscription agreement" in evidence[1]["instrument_hints"]


def test_derive_signature_detection_supports_docx_text_fallback():
    """Text fallback should infer signatures for non-PDF text-like docs (e.g., DOCX)."""
    doc = {
        "id": "doc-1",
        "file_name": "Subscription Agreement.docx",
        "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "manual_text": "",
        "extracted_text": (
            "Subscription Agreement\n"
            "Counterpart Signature Page\n"
            "Signed by: Erica Corley\n"
            "Date Signed: 01/13/2026\n"
        ),
        "metadata": {},
    }

    signature = _derive_signature_detection_for_gap_doc(doc)
    assert signature is not None
    assert signature["status"] == "signed"
    assert signature["signing_date"] == "2026-01-13"


def test_derive_signature_detection_skips_image_like_documents():
    """Image-like files should not run text signature fallback."""
    doc = {
        "id": "doc-2",
        "file_name": "scan.jpg",
        "file_type": "image/jpeg",
        "manual_text": "",
        "extracted_text": "Counterpart Signature Page\nSigned by: Someone",
        "metadata": {},
    }

    signature = _derive_signature_detection_for_gap_doc(doc)
    assert signature is None


def test_derive_signature_detection_honors_attorney_verified_signed_override():
    """Attorney verification should override weak/negative automatic detection."""
    doc = {
        "id": "doc-3",
        "file_name": "Operating Agreement.pdf",
        "file_type": "application/pdf",
        "manual_text": "",
        "extracted_text": "Operating Agreement\nSignature: _________",
        "metadata": {
            "signature_detection": {
                "status": "not_detected",
                "confidence": "medium",
                "detection_source": "ocr_text",
            },
            "signature_verification": {
                "status": "signed",
                "notes": "Confirmed signed counterpart in reviewed upload.",
                "verified_by_user_id": "user-1",
                "verified_at": "2026-02-17T10:00:00Z",
            },
        },
    }

    signature = _derive_signature_detection_for_gap_doc(doc)
    assert signature is not None
    assert signature["status"] == "signed"
    assert signature["confidence"] == "verified"
    assert signature["detection_source"] == "attorney_verification"
    assert signature["verified_by_attorney"] is True


def test_build_signature_evidence_uses_attorney_signature_override():
    """Signature evidence rows should reflect attorney verified status when provided."""
    docs = [
        {
            "id": "doc-1",
            "file_name": "Subscription Agreement.pdf",
            "file_type": "application/pdf",
            "manual_text": "",
            "extracted_text": "Subscription Agreement terms...",
            "metadata": {
                "signature_verification": {
                    "status": "signed",
                    "verified_at": "2026-02-17T10:00:00Z",
                    "verified_by_user_id": "user-1",
                }
            },
        }
    ]

    evidence = _build_signature_evidence(docs)
    assert len(evidence) == 1
    assert evidence[0]["status"] == "signed"
    assert evidence[0]["confidence"] == "verified"
    assert evidence[0]["detection_source"] == "attorney_verification"


def test_gap_analysis_input_hash_changes_when_document_state_changes():
    """Gap-input hash should change when case document state hash changes."""
    payload = {
        "document_summaries": [{"document_name": "Agreement.pdf"}],
        "multi_stage_result": {
            "fact_matrix": {"parties": []},
            "issue_map": {"primary_issues": []},
            "deep_analysis": {"overall_case_strength": "moderate"},
        },
    }

    hash_a = _build_gap_analysis_input_hash(
        analysis_id="analysis-1",
        result_payload=payload,
        case_document_state_hash="state-a",
    )
    hash_b = _build_gap_analysis_input_hash(
        analysis_id="analysis-1",
        result_payload=payload,
        case_document_state_hash="state-b",
    )

    assert hash_a != hash_b


def test_gap_analysis_input_hash_changes_when_logic_version_changes(monkeypatch):
    """Hash should invalidate when reconciliation logic version changes."""
    payload = {
        "document_summaries": [{"document_name": "Agreement.pdf"}],
        "multi_stage_result": {
            "fact_matrix": {"parties": []},
            "issue_map": {"primary_issues": []},
            "deep_analysis": {"overall_case_strength": "moderate"},
        },
    }
    hash_current = analysis_routes._build_gap_analysis_input_hash(
        analysis_id="analysis-1",
        result_payload=payload,
        case_document_state_hash="state-a",
    )

    monkeypatch.setattr(
        analysis_routes,
        "_GAP_ANALYSIS_INPUT_SCHEMA_VERSION",
        "test-version-v2",
    )
    hash_after_bump = analysis_routes._build_gap_analysis_input_hash(
        analysis_id="analysis-1",
        result_payload=payload,
        case_document_state_hash="state-a",
    )

    assert hash_current != hash_after_bump
