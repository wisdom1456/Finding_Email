"""Tests for triage frontend compatibility.

Verifies that:
- T4 skipped documents produce SkippedDocument entries with correct fields
- T3 metadata-only summaries carry the T3_METADATA marker in extraction_notes
- Coverage stats can be correctly derived from summary + skipped data
"""

from __future__ import annotations

from types import SimpleNamespace

from legal_portal.core.models.document_models import SkippedDocument
from legal_portal.services.analysis.document_triage import (
    TriageTier,
    triage_document,
)


def _make_doc(
    file_name: str = "test.pdf",
    content: str = "Some content here",
    file_type: str = "application/pdf",
    registry: dict | None = None,
    document_id: str | None = None,
    extraction_quality: str = "high",
):
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
# T4: SkippedDocument creation for frontend
# ============================================================


class TestT4SkippedDocumentSurfacing:
    """T4 documents should produce SkippedDocument entries the frontend can display."""

    def test_boilerplate_produces_skipped_document(self):
        doc = _make_doc(
            file_name="Documents Needed to Proceed.pdf",
            document_id="doc-t4-1",
        )
        tr = triage_document(doc)
        assert tr.tier == TriageTier.T4_SKIP

        # Simulate what main_processor now does for T4
        sd = SkippedDocument(
            document_id=doc.document_id or "",
            file_name=doc.file_name,
            reason=f"Triage: {tr.reason}",
            error_type="TRIAGE_SKIP",
            recommendation="Boilerplate or zero-content document excluded from analysis.",
        )
        assert sd.error_type == "TRIAGE_SKIP"
        assert "boilerplate" in sd.reason.lower()
        assert sd.file_name == "Documents Needed to Proceed.pdf"

    def test_zero_text_non_image_produces_skipped_document(self):
        doc = _make_doc(file_name="empty.txt", content="", file_type="text/plain")
        tr = triage_document(doc)
        assert tr.tier == TriageTier.T4_SKIP

        sd = SkippedDocument(
            document_id="",
            file_name=doc.file_name,
            reason=f"Triage: {tr.reason}",
            error_type="TRIAGE_SKIP",
            recommendation="Boilerplate or zero-content document excluded from analysis.",
        )
        assert "zero_text" in sd.reason.lower()

    def test_triage_skip_separate_from_error_skips(self):
        """TRIAGE_SKIP should be distinguishable from extraction errors."""
        triage_skip = SkippedDocument(
            document_id="doc-1",
            file_name="boilerplate.pdf",
            reason="Triage: boilerplate: documents needed to proceed",
            error_type="TRIAGE_SKIP",
            recommendation="Boilerplate or zero-content document excluded from analysis.",
        )
        error_skip = SkippedDocument(
            document_id="doc-2",
            file_name="corrupted.pdf",
            reason="Download failed: 404",
            error_type="DOWNLOAD_FAILED",
            recommendation="Re-upload this document.",
        )
        assert triage_skip.error_type != error_skip.error_type
        assert triage_skip.error_type == "TRIAGE_SKIP"


# ============================================================
# T3: extraction_notes marker for frontend detection
# ============================================================


class TestT3ExtractionNotesMarker:
    """T3 metadata-only summaries must contain 'T3_METADATA' in extraction_notes."""

    def test_image_summary_has_t3_marker(self):
        from legal_portal.services.analysis.main_processor import _build_metadata_only_summaries

        doc = _make_doc(
            file_name="IMG_001.jpg",
            content="water damage visible",
            file_type="image/jpeg",
            document_id="doc-t3-1",
        )
        summaries = _build_metadata_only_summaries([doc])
        assert len(summaries) == 1
        assert "T3_METADATA" in summaries[0].extraction_notes

    def test_staff_note_summary_has_t3_marker(self):
        from legal_portal.services.analysis.main_processor import _build_metadata_only_summaries

        doc = _make_doc(
            file_name="Clio Note - EM NOTE.txt",
            content="Called client.",
            file_type="text/plain",
        )
        summaries = _build_metadata_only_summaries([doc])
        assert "T3_METADATA" in summaries[0].extraction_notes


# ============================================================
# Coverage stats simulation (mirrors frontend logic)
# ============================================================


class TestCoverageStatsDerivation:
    """Mirrors the frontend docCoverageStats logic to validate correct classification."""

    @staticmethod
    def _compute_coverage(summaries: list[dict], skipped: list[dict], total_docs: int):
        """Python port of the frontend $derived.by logic for docCoverageStats."""
        group_summary_count = 0
        grouped_doc_count = 0
        individual_count = 0
        metadata_only_count = 0

        for s in summaries:
            if s.get("group_type") and s.get("member_count", 0) > 1:
                group_summary_count += 1
                grouped_doc_count += s["member_count"]
            elif "T3_METADATA" in (s.get("extraction_notes") or ""):
                metadata_only_count += 1
            else:
                individual_count += 1

        return {
            "total": total_docs,
            "fullyAnalyzed": individual_count,
            "grouped": grouped_doc_count,
            "groupCount": group_summary_count,
            "metadataOnly": metadata_only_count,
            "skipped": len(skipped),
        }

    def test_mixed_tiers(self):
        summaries = [
            {"document_name": "contract.pdf", "document_type": "contract"},
            {"document_name": "email.txt", "document_type": "correspondence"},
            {"document_name": "IMG_001.jpg", "extraction_notes": "Triage tier: T3_METADATA. File type: image/jpeg. "},
            {"document_name": "thread", "group_type": "email_thread", "member_count": 3},
        ]
        skipped = [
            {"file_name": "boilerplate.pdf", "error_type": "TRIAGE_SKIP"},
        ]
        stats = self._compute_coverage(summaries, skipped, total_docs=7)

        assert stats["fullyAnalyzed"] == 2
        assert stats["grouped"] == 3
        assert stats["groupCount"] == 1
        assert stats["metadataOnly"] == 1
        assert stats["skipped"] == 1
        assert stats["total"] == 7

    def test_all_metadata_only(self):
        summaries = [
            {"document_name": f"IMG_{i}.jpg", "extraction_notes": "Triage tier: T3_METADATA. File type: image/jpeg. "}
            for i in range(5)
        ]
        stats = self._compute_coverage(summaries, [], total_docs=5)
        assert stats["fullyAnalyzed"] == 0
        assert stats["metadataOnly"] == 5

    def test_no_summaries(self):
        stats = self._compute_coverage([], [], total_docs=3)
        assert stats["fullyAnalyzed"] == 0
        assert stats["metadataOnly"] == 0
        assert stats["skipped"] == 0

    def test_old_summaries_without_extraction_notes(self):
        """Pre-triage summaries have no extraction_notes — should count as fully analyzed."""
        summaries = [
            {"document_name": "old_doc.pdf", "document_type": "contract"},
        ]
        stats = self._compute_coverage(summaries, [], total_docs=1)
        assert stats["fullyAnalyzed"] == 1
        assert stats["metadataOnly"] == 0
