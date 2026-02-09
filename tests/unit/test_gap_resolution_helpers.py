"""Unit tests for gap resolution selective refresh helpers."""

from __future__ import annotations

from legal_portal.api.routes.analysis import (
    GapResolutionItemRequest,
    GapResolutionRefreshRequest,
    _build_gap_resolution_hash,
    _build_resolution_context,
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
