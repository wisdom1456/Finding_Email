"""Integration tests for Row Level Security (RLS) policies.

Verifies that authenticated users can only access their own data and that
the service-role client bypasses all RLS restrictions.
"""

import uuid

import pytest
from postgrest.exceptions import APIError

from .conftest import pytestmark  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _create_case_for_user(service_supabase, user_id: str, label: str = "RLS Test") -> str:
    """Create a case owned by the given user, return its id."""
    row = (
        service_supabase.table("cases")
        .insert({
            "user_id": user_id,
            "client_name": label,
            "jurisdiction": "Florida",
            "status": "pending",
        })
        .execute()
    )
    return row.data[0]["id"]


# ---------------------------------------------------------------------------
# Cases RLS
# ---------------------------------------------------------------------------
class TestCasesRLS:
    """Cases table: users can only see/modify their own cases."""

    def test_user_a_sees_own_case(self, service_supabase, user_a_supabase, case_id):
        """User A can SELECT a case they own."""
        result = (
            user_a_supabase.table("cases")
            .select("id")
            .eq("id", str(case_id))
            .execute()
        )
        assert len(result.data) == 1

    def test_user_b_cannot_see_user_a_case(self, service_supabase, user_b_supabase, case_id):
        """User B cannot SELECT User A's case."""
        result = (
            user_b_supabase.table("cases")
            .select("id")
            .eq("id", str(case_id))
            .execute()
        )
        assert result.data == []

    def test_user_b_cannot_update_user_a_case(self, service_supabase, user_b_supabase, case_id):
        """User B cannot UPDATE User A's case."""
        result = (
            user_b_supabase.table("cases")
            .update({"client_name": "Hacked"})
            .eq("id", str(case_id))
            .execute()
        )
        assert result.data == []
        # Confirm original value unchanged
        check = (
            service_supabase.table("cases")
            .select("client_name")
            .eq("id", str(case_id))
            .execute()
        )
        assert check.data[0]["client_name"] != "Hacked"

    def test_user_b_cannot_delete_user_a_case(self, service_supabase, user_b_supabase, case_id):
        """User B cannot DELETE User A's case."""
        result = (
            user_b_supabase.table("cases")
            .delete()
            .eq("id", str(case_id))
            .execute()
        )
        assert result.data == []
        # Case still exists
        check = (
            service_supabase.table("cases")
            .select("id")
            .eq("id", str(case_id))
            .execute()
        )
        assert len(check.data) == 1


# ---------------------------------------------------------------------------
# Documents RLS
# ---------------------------------------------------------------------------
class TestDocumentsRLS:
    """Documents table: access governed by case ownership."""

    def test_user_a_sees_own_documents(self, user_a_supabase, case_id, document_id):
        """User A can SELECT documents in their own case."""
        result = (
            user_a_supabase.table("documents")
            .select("id")
            .eq("case_id", str(case_id))
            .execute()
        )
        ids = [r["id"] for r in result.data]
        assert str(document_id) in ids

    def test_user_b_cannot_see_user_a_documents(self, user_b_supabase, case_id, document_id):
        """User B cannot SELECT documents in User A's case."""
        result = (
            user_b_supabase.table("documents")
            .select("id")
            .eq("case_id", str(case_id))
            .execute()
        )
        assert result.data == []

    def test_user_b_cannot_insert_into_user_a_case(self, user_b_supabase, case_id):
        """User B cannot INSERT a document into User A's case."""
        with pytest.raises(APIError):
            user_b_supabase.table("documents").insert({
                "case_id": str(case_id),
                "file_name": "malicious.pdf",
                "file_type": "application/pdf",
                "file_size": 100,
                "storage_path": f"test/{uuid.uuid4()}/malicious.pdf",
                "status": "pending",
            }).execute()


# ---------------------------------------------------------------------------
# Analysis Results RLS
# ---------------------------------------------------------------------------
class TestAnalysisResultsRLS:
    """Analysis results: viewable through case ownership."""

    def test_user_a_sees_own_analysis(self, service_supabase, user_a_supabase, case_id):
        """User A can see analysis results for their own case."""
        # Create an analysis result via service role
        service_supabase.table("analysis_results").insert({
            "case_id": str(case_id),
            "status": "completed",
            "result": {"test": True},
        }).execute()

        result = (
            user_a_supabase.table("analysis_results")
            .select("id, status")
            .eq("case_id", str(case_id))
            .execute()
        )
        assert len(result.data) >= 1

    def test_user_b_cannot_see_user_a_analysis(self, service_supabase, user_b_supabase, case_id):
        """User B cannot see analysis results for User A's case."""
        # Ensure at least one result exists
        service_supabase.table("analysis_results").insert({
            "case_id": str(case_id),
            "status": "completed",
            "result": {"test": True},
        }).execute()

        result = (
            user_b_supabase.table("analysis_results")
            .select("id")
            .eq("case_id", str(case_id))
            .execute()
        )
        assert result.data == []


# ---------------------------------------------------------------------------
# Service-role bypass
# ---------------------------------------------------------------------------
class TestServiceRoleBypass:
    """Service-role client bypasses all RLS policies."""

    def test_service_role_sees_all_cases(self, service_supabase, user_a_id, user_b_id):
        """Service role can see cases across all users."""
        id_a = _create_case_for_user(service_supabase, user_a_id, "Service Test A")
        id_b = _create_case_for_user(service_supabase, user_b_id, "Service Test B")

        try:
            result = (
                service_supabase.table("cases")
                .select("id, user_id")
                .in_("id", [id_a, id_b])
                .execute()
            )
            user_ids = {r["user_id"] for r in result.data}
            assert user_a_id in user_ids
            assert user_b_id in user_ids
        finally:
            service_supabase.table("cases").delete().eq("id", id_a).execute()
            service_supabase.table("cases").delete().eq("id", id_b).execute()

    def test_service_role_can_update_any_case(self, service_supabase, user_b_id):
        """Service role can update cases regardless of ownership."""
        cid = _create_case_for_user(service_supabase, user_b_id, "Before Update")
        try:
            result = (
                service_supabase.table("cases")
                .update({"client_name": "After Update"})
                .eq("id", cid)
                .execute()
            )
            assert result.data[0]["client_name"] == "After Update"
        finally:
            service_supabase.table("cases").delete().eq("id", cid).execute()


# ---------------------------------------------------------------------------
# Profiles privilege escalation (20260702000000_harden_profiles_and_analysis_rls)
# ---------------------------------------------------------------------------
class TestProfilesPrivilegeEscalation:
    """Users must not be able to write approved/role on their own profile."""

    def test_user_cannot_self_approve(self, user_a_supabase, user_a_id):
        """Writing `approved` with a user JWT is denied at the column level."""
        with pytest.raises(APIError):
            user_a_supabase.table("profiles").update({"approved": True}).eq(
                "id", user_a_id
            ).execute()

    def test_user_cannot_self_promote_role(self, service_supabase, user_a_supabase, user_a_id):
        """Writing `role` with a user JWT is denied at the column level."""
        try:
            with pytest.raises(APIError):
                user_a_supabase.table("profiles").update({"role": "admin"}).eq(
                    "id", user_a_id
                ).execute()
        finally:
            # If the privilege gap regresses, don't leave an admin behind.
            service_supabase.table("profiles").update({"role": "user"}).eq(
                "id", user_a_id
            ).execute()

    def test_user_can_update_own_safe_fields(self, user_a_supabase, user_a_id):
        """The Settings flow (user JWT updating editable columns) still works."""
        result = (
            user_a_supabase.table("profiles")
            .update({"full_name": "Integration Test User A"})
            .eq("id", user_a_id)
            .execute()
        )
        assert result.data[0]["full_name"] == "Integration Test User A"

    def test_user_b_cannot_update_user_a_profile(self, user_b_supabase, user_a_id):
        """Cross-user profile updates are filtered by RLS (0 rows)."""
        result = (
            user_b_supabase.table("profiles")
            .update({"full_name": "Hacked"})
            .eq("id", user_a_id)
            .execute()
        )
        assert result.data == []


# ---------------------------------------------------------------------------
# Analysis results write ownership (20260702000000_harden_profiles_and_analysis_rls)
# ---------------------------------------------------------------------------
class TestAnalysisResultsWriteRLS:
    """Insert/update on analysis_results must require case ownership."""

    def test_user_b_cannot_insert_analysis_for_user_a_case(self, user_b_supabase, case_id):
        """User B cannot INSERT an analysis row into User A's case."""
        with pytest.raises(APIError):
            user_b_supabase.table("analysis_results").insert({
                "case_id": str(case_id),
                "status": "completed",
                "result": {"poisoned": True},
            }).execute()

    def test_user_b_cannot_update_user_a_analysis(
        self, service_supabase, user_b_supabase, case_id
    ):
        """User B cannot UPDATE an analysis row belonging to User A's case."""
        row = service_supabase.table("analysis_results").insert({
            "case_id": str(case_id),
            "status": "completed",
            "result": {"test": True},
        }).execute()
        result_id = row.data[0]["id"]

        result = (
            user_b_supabase.table("analysis_results")
            .update({"status": "error"})
            .eq("id", result_id)
            .execute()
        )
        assert result.data == []

        check = (
            service_supabase.table("analysis_results")
            .select("status")
            .eq("id", result_id)
            .execute()
        )
        assert check.data[0]["status"] == "completed"

    def test_user_a_can_insert_analysis_for_own_case(self, user_a_supabase, case_id):
        """The analysis-start path (user JWT insert on own case) still works."""
        result = user_a_supabase.table("analysis_results").insert({
            "case_id": str(case_id),
            "status": "pending",
        }).execute()
        assert result.data[0]["case_id"] == str(case_id)

    def test_user_a_can_update_own_analysis(self, user_a_supabase, case_id):
        """The analysis-start path (user JWT update on own case) still works."""
        row = user_a_supabase.table("analysis_results").insert({
            "case_id": str(case_id),
            "status": "pending",
        }).execute()
        result_id = row.data[0]["id"]

        result = (
            user_a_supabase.table("analysis_results")
            .update({"status": "processing"})
            .eq("id", result_id)
            .execute()
        )
        assert result.data[0]["status"] == "processing"
