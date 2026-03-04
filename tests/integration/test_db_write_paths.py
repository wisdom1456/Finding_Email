"""Integration tests for database write paths.

Validates that INSERT/UPDATE/UPSERT operations succeed against the real
PostgreSQL schema, catching column mismatches and constraint violations
that mocks can never detect.
"""

import json
import uuid

import pytest

from .conftest import pytestmark  # noqa: F401 – applies skip + marker


class TestDocumentUpdates:
    """UPDATE documents with extraction fields."""

    def test_update_all_extraction_fields(self, service_supabase, case_id, document_id):
        """All extraction columns accepted by real schema."""
        result = (
            service_supabase.table("documents")
            .update({
                "status": "ready",
                "extracted_text": "Sample extracted text from integration test.",
                "extraction_method": "pdfplumber",
                "extraction_quality": "high",
                "extracted_at": "2025-01-01T00:00:00+00:00",
                "page_count": 5,
                "ocr_provider": "tesseract",
                "extraction_error": None,
                "manual_text": None,
                "is_verified": True,
                "is_flagged_as_junk": False,
                "text_edited_at": None,
                "metadata": {"source": "integration_test"},
            })
            .eq("id", str(document_id))
            .execute()
        )
        assert len(result.data) == 1
        assert result.data[0]["extraction_method"] == "pdfplumber"

    def test_update_file_size_is_integer(self, service_supabase, document_id):
        """file_size column accepts integer values (caught KeyError in prod)."""
        result = (
            service_supabase.table("documents")
            .update({"file_size": 99999})
            .eq("id", str(document_id))
            .execute()
        )
        assert result.data[0]["file_size"] == 99999

    def test_update_document_status_valid(self, service_supabase, document_id):
        """Valid status values accepted by CHECK constraint."""
        for status in ("ready", "needs_review", "extraction_failed", "pending", "skipped"):
            result = (
                service_supabase.table("documents")
                .update({"status": status})
                .eq("id", str(document_id))
                .execute()
            )
            assert result.data[0]["status"] == status

    def test_update_document_status_invalid_rejected(self, service_supabase, document_id):
        """Invalid status rejected by CHECK constraint."""
        with pytest.raises(Exception):
            service_supabase.table("documents").update(
                {"status": "INVALID_STATUS"}
            ).eq("id", str(document_id)).execute()


class TestAnalysisResultsUpsert:
    """UPSERT analysis_results with JSONB payloads."""

    def test_upsert_small_result(self, service_supabase, case_id):
        """Small JSONB payload succeeds."""
        result = (
            service_supabase.table("analysis_results")
            .upsert({
                "case_id": str(case_id),
                "status": "completed",
                "result": {"summary": "Test analysis result"},
                "completed_at": "2025-01-01T00:00:00+00:00",
            })
            .execute()
        )
        assert len(result.data) == 1
        assert result.data[0]["status"] == "completed"

    def test_upsert_large_jsonb_payload(self, service_supabase, case_id):
        """~500KB JSONB payload succeeds (tests statement timeout threshold)."""
        large_payload = {
            "documents": [
                {
                    "id": str(uuid.uuid4()),
                    "facts": [f"Fact {i}: " + "x" * 500 for i in range(200)],
                    "summary": "A" * 2000,
                }
                for _ in range(5)
            ]
        }
        payload_size = len(json.dumps(large_payload))
        assert payload_size > 400_000, f"Payload only {payload_size} bytes"

        result = (
            service_supabase.table("analysis_results")
            .upsert({
                "case_id": str(case_id),
                "status": "completed",
                "result": large_payload,
                "completed_at": "2025-01-01T00:00:00+00:00",
            })
            .execute()
        )
        assert len(result.data) == 1


class TestCaseUpdates:
    """UPDATE cases table."""

    def test_update_case_status_valid(self, service_supabase, case_id):
        """Valid status values accepted by CHECK constraint."""
        for status in ("pending", "processing", "completed", "error", "cancelled"):
            result = (
                service_supabase.table("cases")
                .update({"status": status})
                .eq("id", str(case_id))
                .execute()
            )
            assert result.data[0]["status"] == status

    def test_update_case_status_invalid_rejected(self, service_supabase, case_id):
        """Invalid case status rejected by CHECK constraint."""
        with pytest.raises(Exception):
            service_supabase.table("cases").update(
                {"status": "BOGUS"}
            ).eq("id", str(case_id)).execute()

    def test_update_nonexistent_row_returns_empty(self, service_supabase):
        """Updating a non-existent row returns empty data, not an error."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        result = (
            service_supabase.table("cases")
            .update({"status": "completed"})
            .eq("id", fake_id)
            .execute()
        )
        assert result.data == []
