"""Unit tests for document triage classification logic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from legal_portal.services.analysis.document_triage import (
    TriageTier,
    TriageResult,
    triage_document,
    triage_documents,
)


def _make_doc(
    file_name: str = "test.pdf",
    content: str = "Some content here",
    file_type: str = "application/pdf",
    registry: dict | None = None,
    document_id: str | None = None,
    extraction_quality: str = "high",
):
    """Create a minimal document-like object for testing."""
    ft = SimpleNamespace(value=file_type)
    return SimpleNamespace(
        file_name=file_name,
        content=content,
        file_type=ft,
        registry=registry or {},
        document_id=document_id,
        extraction_quality=extraction_quality,
        metadata=SimpleNamespace(file_size=len(content)),
    )


# ============================================================
# T4: Skip — Boilerplate
# ============================================================


class TestT4Boilerplate:
    def test_skip_documents_needed_to_proceed(self):
        doc = _make_doc(file_name="Documents Needed to Proceed.pdf")
        result = triage_document(doc)
        assert result.tier == TriageTier.T4_SKIP
        assert "boilerplate" in result.reason

    def test_skip_attaching_instructions(self):
        doc = _make_doc(file_name="Attaching a Document Instructions.pdf")
        result = triage_document(doc)
        assert result.tier == TriageTier.T4_SKIP
        assert "boilerplate" in result.reason

    def test_skip_case_insensitive(self):
        doc = _make_doc(file_name="DOCUMENTS NEEDED TO PROCEED.PDF")
        result = triage_document(doc)
        assert result.tier == TriageTier.T4_SKIP

    def test_skip_zero_text_non_image(self):
        doc = _make_doc(file_name="empty.txt", content="", file_type="text/plain")
        result = triage_document(doc)
        assert result.tier == TriageTier.T4_SKIP
        assert "zero_text" in result.reason

    def test_do_not_skip_zero_text_image(self):
        """Images with no extracted text should NOT be T4 — they may show damage evidence."""
        doc = _make_doc(file_name="IMG_001.jpg", content="", file_type="image/jpeg")
        result = triage_document(doc)
        assert result.tier != TriageTier.T4_SKIP


# ============================================================
# T1: Full — High-value documents
# ============================================================


class TestT1HighValue:
    def test_contract_by_type_label(self):
        doc = _make_doc(
            file_name="random.pdf",
            content="x" * 5000,
            registry={"document_type": "contract"},
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL
        assert "high_value_type" in result.reason

    def test_agreement_by_type_label(self):
        doc = _make_doc(
            file_name="file.pdf",
            content="x" * 5000,
            registry={"document_type": "operating agreement"},
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL

    def test_intake_form_by_filename(self):
        doc = _make_doc(file_name="Intake Form - General (John Smith).pdf", content="x" * 5000)
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL
        assert "high_value_filename" in result.reason

    def test_complaint_by_filename(self):
        doc = _make_doc(file_name="01. Complaint [Filed 1.8.2026].pdf", content="x" * 10000)
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL

    def test_subscription_agreement_by_filename(self):
        doc = _make_doc(file_name="Subscription_Agreement_EJAJ-TX_Final120.doc.pdf", content="x" * 5000)
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL

    def test_demand_letter_by_filename(self):
        doc = _make_doc(file_name="Demand Letter_Devlin and Bell.pdf", content="x" * 5000)
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL

    def test_notice_of_intent_by_filename(self):
        doc = _make_doc(file_name="Notice of Intent w EX_Badam.pdf", content="x" * 5000)
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL

    def test_high_value_clio_note_case_summary(self):
        doc = _make_doc(file_name="Clio Note - Initial Case Summary.txt", content="x" * 5000)
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL
        assert "high_value_clio_note" in result.reason

    def test_high_value_clio_note_intake(self):
        doc = _make_doc(file_name="Clio Note - Intake.txt", content="x" * 5000)
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL

    def test_high_value_clio_note_attorney_initial(self):
        doc = _make_doc(file_name="Clio Note - Attorney Initial Case Summary.txt", content="x" * 5000)
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL

    def test_attorney_representation_agreement(self):
        doc = _make_doc(
            file_name="Attorney Representation Agreement (Metlife) (Tammy Bartek).pdf",
            content="x" * 10000,
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL

    def test_legal_filing_by_type_label(self):
        doc = _make_doc(
            file_name="Document_40766760_RD.pdf",
            content="x" * 8000,
            registry={"document_type": "legal filing"},
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL


# ============================================================
# T3: Metadata-only — Low-signal documents
# ============================================================


class TestT3Metadata:
    def test_low_text_photo(self):
        doc = _make_doc(
            file_name="IMG_0532.JPEG",
            content="Visible water damage on ceiling tile" * 5,  # ~180 chars
            file_type="image/jpeg",
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T3_METADATA
        assert "low_text_image" in result.reason

    def test_low_text_png(self):
        doc = _make_doc(
            file_name="Screenshot 2026-01-27.png",
            content="text overlay on image",
            file_type="image/png",
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T3_METADATA

    def test_staff_initial_note_short(self):
        doc = _make_doc(
            file_name="Clio Note - EM NOTE.txt",
            content="Called client, left VM.",  # 22 chars
            file_type="text/plain",
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T3_METADATA
        assert "staff_note" in result.reason

    def test_staff_note_mt(self):
        doc = _make_doc(
            file_name="Clio Note - MT NOTE.txt",
            content="Sent follow-up email to opposing counsel.",
            file_type="text/plain",
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T3_METADATA

    def test_staff_note_dw_assignment(self):
        doc = _make_doc(
            file_name="Clio Note - DW assignment.txt",
            content="Assigned to DW for initial review.",
            file_type="text/plain",
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T3_METADATA

    def test_zero_text_image_not_skipped(self):
        """Zero-text images should be T3 (metadata) not T4 (skip)."""
        doc = _make_doc(file_name="IMG_6652.jpeg", content="", file_type="image/jpeg")
        result = triage_document(doc)
        assert result.tier == TriageTier.T3_METADATA

    def test_image_with_substantial_text_not_t3(self):
        """Images with >2K extracted text should get full treatment."""
        doc = _make_doc(
            file_name="IMG_scan.jpg",
            content="x" * 3000,
            file_type="image/jpeg",
        )
        result = triage_document(doc)
        assert result.tier != TriageTier.T3_METADATA


# ============================================================
# T2: Light — Moderate-value documents
# ============================================================


class TestT2Light:
    def test_clio_communication(self):
        doc = _make_doc(
            file_name="Clio Communication - RE: Hearing Request.txt",
            content="x" * 5000,
            file_type="text/plain",
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T2_LIGHT
        assert "clio_communication" in result.reason

    def test_staff_note_with_substantial_content(self):
        """Staff notes with >800 chars should be T2 (light) not T3 (metadata)."""
        doc = _make_doc(
            file_name="Clio Note - EM NOTE.txt",
            content="x" * 1500,
            file_type="text/plain",
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T2_LIGHT

    def test_short_document(self):
        """Documents with <3K text default to T2 if not otherwise classified."""
        doc = _make_doc(
            file_name="some_letter.pdf",
            content="x" * 2000,
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T2_LIGHT
        assert "short_doc" in result.reason


# ============================================================
# Default behavior
# ============================================================


class TestDefaults:
    def test_default_to_full(self):
        """Unclassified substantial documents get T1 full."""
        doc = _make_doc(
            file_name="Important_Legal_Filing.pdf",
            content="x" * 10000,
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL
        assert "default_full" in result.reason

    def test_large_pdf_default_full(self):
        doc = _make_doc(
            file_name="unknown_document.pdf",
            content="x" * 50000,
        )
        result = triage_document(doc)
        assert result.tier == TriageTier.T1_FULL


# ============================================================
# Batch triage
# ============================================================


class TestTriageDocuments:
    def test_returns_all_tiers(self):
        docs = [
            _make_doc(file_name="Documents Needed to Proceed.pdf"),  # T4
            _make_doc(file_name="IMG_001.jpg", content="x" * 100, file_type="image/jpeg"),  # T3
            _make_doc(file_name="Clio Communication - FW.txt", content="x" * 5000),  # T2
            _make_doc(file_name="Operating Agreement.pdf", content="x" * 10000,
                      registry={"document_type": "contract"}),  # T1
        ]
        results = triage_documents(docs)
        assert len(results[TriageTier.T4_SKIP]) == 1
        assert len(results[TriageTier.T3_METADATA]) == 1
        assert len(results[TriageTier.T2_LIGHT]) == 1
        assert len(results[TriageTier.T1_FULL]) == 1

    def test_feature_flag_disabled(self):
        """When triage is disabled, all docs get T1_FULL."""
        docs = [
            _make_doc(file_name="Documents Needed to Proceed.pdf"),
            _make_doc(file_name="IMG_001.jpg", content="", file_type="image/jpeg"),
        ]
        results = triage_documents(docs, enable_triage=False)
        assert len(results[TriageTier.T1_FULL]) == 2
        assert len(results[TriageTier.T4_SKIP]) == 0

    def test_empty_input(self):
        results = triage_documents([])
        assert all(len(v) == 0 for v in results.values())


# ============================================================
# T3 metadata-only summary builder
# ============================================================


class TestBuildMetadataOnlySummaries:
    def test_builds_summary_from_image(self):
        from legal_portal.services.analysis.main_processor import _build_metadata_only_summaries

        doc = _make_doc(
            file_name="IMG_6652.jpeg",
            content="Visible water stain on ceiling",
            file_type="image/jpeg",
            document_id="doc-123",
        )
        summaries = _build_metadata_only_summaries([doc])
        assert len(summaries) == 1
        s = summaries[0]
        assert s.document_name == "IMG_6652.jpeg"
        assert s.document_id == "doc-123"
        assert "Evidence" in s.document_type
        assert "Metadata-only" in s.executive_summary
        assert "T3_METADATA" in s.extraction_notes

    def test_builds_summary_from_clio_note(self):
        from legal_portal.services.analysis.main_processor import _build_metadata_only_summaries

        doc = _make_doc(
            file_name="Clio Note - EM NOTE.txt",
            content="Left VM for client re: status update.",
            file_type="text/plain",
        )
        summaries = _build_metadata_only_summaries([doc])
        assert len(summaries) == 1
        s = summaries[0]
        assert s.document_name == "Clio Note - EM NOTE.txt"
        assert "Correspondence" in s.document_type
        assert s.key_content is not None

    def test_empty_input(self):
        from legal_portal.services.analysis.main_processor import _build_metadata_only_summaries

        summaries = _build_metadata_only_summaries([])
        assert summaries == []
