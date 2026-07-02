"""Integration tests for SELECT column strings.

Executes the exact SELECT column lists from production code against real
PostgreSQL to catch schema mismatches (e.g. the file_size KeyError).
"""


from .conftest import pytestmark  # noqa: F401 – applies skip + marker

# ---------------------------------------------------------------------------
# These strings are copied verbatim from production code.
# If production changes, these tests should be updated to match.
# ---------------------------------------------------------------------------

# src/legal_portal/api/routes/documents.py  lines 554-559
DOCUMENTS_LIST_SELECT = (
    "id, case_id, file_name, file_type, file_size, storage_path, status, "
    "extraction_method, extraction_quality, extracted_at, page_count, "
    "ocr_provider, extraction_error, is_verified, is_flagged_as_junk, "
    "text_edited_at, metadata, created_at, updated_at"
)

# src/legal_portal/api/routes/analysis.py  line 3307
ANALYSIS_DOCUMENTS_SELECT = (
    "id, file_name, file_type, extracted_text, extraction_quality, status, metadata"
)

# src/legal_portal/api/routes/analysis.py  line 3051
CASE_OWNERSHIP_SELECT = "id, client_name, jurisdiction"


class TestListDocumentsSelect:
    """Validates the exact 19-column SELECT used by list_documents_for_case."""

    def test_select_succeeds(self, service_supabase, case_id, document_id):
        """The production SELECT string executes without error."""
        result = (
            service_supabase.table("documents")
            .select(DOCUMENTS_LIST_SELECT)
            .eq("case_id", str(case_id))
            .execute()
        )
        assert len(result.data) >= 1

    def test_file_size_is_integer(self, service_supabase, case_id, document_id):
        """file_size column is returned and is an integer (not null)."""
        result = (
            service_supabase.table("documents")
            .select(DOCUMENTS_LIST_SELECT)
            .eq("id", str(document_id))
            .execute()
        )
        row = result.data[0]
        assert "file_size" in row, "file_size column missing from SELECT result"
        assert isinstance(row["file_size"], int), f"file_size is {type(row['file_size'])}, expected int"

    def test_all_19_columns_present(self, service_supabase, case_id, document_id):
        """All 19 columns are present in the response."""
        result = (
            service_supabase.table("documents")
            .select(DOCUMENTS_LIST_SELECT)
            .eq("id", str(document_id))
            .execute()
        )
        row = result.data[0]
        expected_columns = {
            "id", "case_id", "file_name", "file_type", "file_size",
            "storage_path", "status", "extraction_method", "extraction_quality",
            "extracted_at", "page_count", "ocr_provider", "extraction_error",
            "is_verified", "is_flagged_as_junk", "text_edited_at", "metadata",
            "created_at", "updated_at",
        }
        assert set(row.keys()) == expected_columns


class TestAnalysisDocumentsSelect:
    """Validates the 7-column SELECT used by save_streaming_analysis."""

    def test_select_succeeds(self, service_supabase, case_id, document_id):
        """The production SELECT string executes without error."""
        result = (
            service_supabase.table("documents")
            .select(ANALYSIS_DOCUMENTS_SELECT)
            .eq("case_id", str(case_id))
            .execute()
        )
        assert len(result.data) >= 1
        row = result.data[0]
        expected = {"id", "file_name", "file_type", "extracted_text", "extraction_quality", "status", "metadata"}
        assert set(row.keys()) == expected


class TestCaseOwnershipSelect:
    """Validates the case ownership SELECT."""

    def test_select_succeeds(self, service_supabase, case_id):
        """The production case ownership SELECT executes without error."""
        result = (
            service_supabase.table("cases")
            .select(CASE_OWNERSHIP_SELECT)
            .eq("id", str(case_id))
            .execute()
        )
        assert len(result.data) == 1
        row = result.data[0]
        assert set(row.keys()) == {"id", "client_name", "jurisdiction"}
