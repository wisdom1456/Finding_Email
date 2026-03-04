"""Integration tests for the CorrectionModal lazy-fetch fix and
VerificationHub extracted_at fix.

Bug context:
  1. CorrectionModal was initializing editedText from document.extracted_text,
     but loadDocuments() excludes extracted_text from its 19-column SELECT.
     Fix: CorrectionModal now lazy-fetches extracted_text + manual_text on mount.

  2. VerificationHub counted docs needing OCR via !doc.extracted_text, which was
     always undefined (not in SELECT). Fix: use !doc.extracted_at instead.

These tests validate the Supabase queries underlying both fixes against the
real local Supabase schema.
"""

import uuid

import pytest

from .conftest import pytestmark  # noqa: F401 – applies skip + marker

# ---------------------------------------------------------------------------
# Production SELECT strings (copied verbatim)
# ---------------------------------------------------------------------------

# frontend/src/routes/app/cases/[id]/+page.svelte  loadDocuments()
DOCUMENTS_LIST_SELECT = (
    "id, case_id, file_name, file_type, file_size, storage_path, status, "
    "extraction_method, extraction_quality, extracted_at, page_count, "
    "ocr_provider, extraction_error, is_verified, is_flagged_as_junk, "
    "text_edited_at, metadata, created_at, updated_at"
)

# CorrectionModal.svelte  fetchDocumentText()
CORRECTION_MODAL_SELECT = "extracted_text, manual_text"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_document(service_supabase, case_id, **overrides):
    """Insert a document with sensible defaults; return the row dict."""
    payload = {
        "case_id": str(case_id),
        "file_name": "test_doc.pdf",
        "file_type": "application/pdf",
        "file_size": 1024,
        "storage_path": f"test/{uuid.uuid4()}/test_doc.pdf",
        "status": "ready",
    }
    payload.update(overrides)
    result = service_supabase.table("documents").insert(payload).execute()
    return result.data[0]


# ===========================================================================
# Fix 1: CorrectionModal lazy-fetch
# ===========================================================================

class TestCorrectionModalLazyFetch:
    """Validates the two-step query pattern used after the fix:
    1. loadDocuments() returns 19 columns (no extracted_text)
    2. CorrectionModal fetches extracted_text + manual_text separately
    """

    def test_list_select_excludes_extracted_text(
        self, service_supabase, case_id, document_id
    ):
        """The 19-column list SELECT does NOT return extracted_text."""
        result = (
            service_supabase.table("documents")
            .select(DOCUMENTS_LIST_SELECT)
            .eq("id", str(document_id))
            .execute()
        )
        row = result.data[0]
        assert "extracted_text" not in row
        assert "manual_text" not in row

    def test_modal_fetch_returns_extracted_text(
        self, service_supabase, case_id
    ):
        """The CorrectionModal SELECT returns extracted_text when present."""
        doc = _insert_document(
            service_supabase,
            case_id,
            extracted_text="This is the OCR output.",
            extracted_at="2025-06-01T00:00:00+00:00",
        )
        result = (
            service_supabase.table("documents")
            .select(CORRECTION_MODAL_SELECT)
            .eq("id", doc["id"])
            .single()
            .execute()
        )
        assert result.data["extracted_text"] == "This is the OCR output."
        assert result.data["manual_text"] is None

    def test_modal_fetch_returns_manual_text(
        self, service_supabase, case_id
    ):
        """The CorrectionModal SELECT returns manual_text when present."""
        doc = _insert_document(
            service_supabase,
            case_id,
            extracted_text="Original OCR",
            manual_text="User-corrected text",
            extracted_at="2025-06-01T00:00:00+00:00",
        )
        result = (
            service_supabase.table("documents")
            .select(CORRECTION_MODAL_SELECT)
            .eq("id", doc["id"])
            .single()
            .execute()
        )
        assert result.data["manual_text"] == "User-corrected text"
        assert result.data["extracted_text"] == "Original OCR"

    def test_modal_fetch_handles_null_text(
        self, service_supabase, case_id
    ):
        """The CorrectionModal SELECT works when both text fields are NULL."""
        doc = _insert_document(service_supabase, case_id)
        result = (
            service_supabase.table("documents")
            .select(CORRECTION_MODAL_SELECT)
            .eq("id", doc["id"])
            .single()
            .execute()
        )
        assert result.data["extracted_text"] is None
        assert result.data["manual_text"] is None

    def test_two_step_round_trip(self, service_supabase, case_id):
        """Full round-trip: list SELECT misses text, modal SELECT gets it."""
        doc = _insert_document(
            service_supabase,
            case_id,
            extracted_text="Important legal text from OCR",
            extracted_at="2025-06-01T00:00:00+00:00",
        )
        doc_id = doc["id"]

        # Step 1: loadDocuments() — no extracted_text
        list_result = (
            service_supabase.table("documents")
            .select(DOCUMENTS_LIST_SELECT)
            .eq("id", doc_id)
            .execute()
        )
        list_row = list_result.data[0]
        assert "extracted_text" not in list_row
        assert list_row["extracted_at"] is not None  # timestamp IS present

        # Step 2: CorrectionModal fetchDocumentText() — gets the text
        modal_result = (
            service_supabase.table("documents")
            .select(CORRECTION_MODAL_SELECT)
            .eq("id", doc_id)
            .single()
            .execute()
        )
        assert modal_result.data["extracted_text"] == "Important legal text from OCR"


# ===========================================================================
# Fix 2: VerificationHub extracted_at indicator
# ===========================================================================

class TestVerificationHubExtractedAt:
    """Validates that extracted_at in the list SELECT reliably indicates
    whether OCR has been performed, replacing the old !doc.extracted_text check.
    """

    def test_extracted_at_null_before_ocr(self, service_supabase, case_id):
        """A new document without OCR has extracted_at = NULL in list SELECT."""
        doc = _insert_document(service_supabase, case_id, status="pending")
        result = (
            service_supabase.table("documents")
            .select(DOCUMENTS_LIST_SELECT)
            .eq("id", doc["id"])
            .execute()
        )
        row = result.data[0]
        assert row["extracted_at"] is None

    def test_extracted_at_set_after_ocr(self, service_supabase, case_id):
        """After OCR, extracted_at is a non-null timestamp in list SELECT."""
        doc = _insert_document(
            service_supabase,
            case_id,
            extracted_text="OCR output text",
            extracted_at="2025-06-15T12:30:00+00:00",
            extraction_method="tesseract",
            status="ready",
        )
        result = (
            service_supabase.table("documents")
            .select(DOCUMENTS_LIST_SELECT)
            .eq("id", doc["id"])
            .execute()
        )
        row = result.data[0]
        assert row["extracted_at"] is not None

    def test_ocr_needed_filter_uses_extracted_at(
        self, service_supabase, case_id
    ):
        """Simulates the VerificationHub filter:
        docs needing OCR = !doc.extracted_at || doc.status === 'pending'

        Documents with extracted_at set should NOT appear in the filter.
        """
        # Doc A: needs OCR (no extracted_at, pending)
        doc_a = _insert_document(
            service_supabase,
            case_id,
            file_name="needs_ocr.pdf",
            status="pending",
            storage_path=f"test/{uuid.uuid4()}/needs_ocr.pdf",
        )
        # Doc B: OCR done (has extracted_at, ready)
        doc_b = _insert_document(
            service_supabase,
            case_id,
            file_name="ocr_done.pdf",
            status="ready",
            extracted_text="Some text",
            extracted_at="2025-06-15T12:30:00+00:00",
            storage_path=f"test/{uuid.uuid4()}/ocr_done.pdf",
        )
        # Doc C: needs OCR (no extracted_at, ready — extraction failed/never ran)
        doc_c = _insert_document(
            service_supabase,
            case_id,
            file_name="no_ocr_ready.pdf",
            status="ready",
            storage_path=f"test/{uuid.uuid4()}/no_ocr_ready.pdf",
        )

        # Fetch all docs with list SELECT
        result = (
            service_supabase.table("documents")
            .select(DOCUMENTS_LIST_SELECT)
            .eq("case_id", str(case_id))
            .execute()
        )
        all_docs = result.data

        # Apply the VerificationHub filter: !d.extracted_at || d.status === 'pending'
        needs_ocr = [
            d for d in all_docs
            if not d["extracted_at"] or d["status"] == "pending"
        ]
        needs_ocr_ids = {d["id"] for d in needs_ocr}

        assert doc_a["id"] in needs_ocr_ids, "pending doc should need OCR"
        assert doc_b["id"] not in needs_ocr_ids, "OCR'd doc should NOT need OCR"
        assert doc_c["id"] in needs_ocr_ids, "doc without extracted_at should need OCR"

    def test_extracted_at_persists_after_update(
        self, service_supabase, case_id
    ):
        """extracted_at remains set even when extracted_text is updated,
        ensuring the count stays correct after re-extraction."""
        doc = _insert_document(
            service_supabase,
            case_id,
            extracted_text="First OCR pass",
            extracted_at="2025-06-15T12:00:00+00:00",
        )

        # Simulate re-extraction updating text
        service_supabase.table("documents").update({
            "extracted_text": "Second OCR pass — better quality",
            "extracted_at": "2025-06-15T13:00:00+00:00",
        }).eq("id", doc["id"]).execute()

        result = (
            service_supabase.table("documents")
            .select(DOCUMENTS_LIST_SELECT)
            .eq("id", doc["id"])
            .execute()
        )
        row = result.data[0]
        assert row["extracted_at"] is not None
        assert "extracted_text" not in row  # still excluded from list SELECT
