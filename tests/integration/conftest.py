"""Fixtures for integration tests against local Supabase."""

import os
import socket
import uuid

import pytest
from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Configuration – defaults match `supabase start` on localhost
# ---------------------------------------------------------------------------
SUPABASE_TEST_URL = os.getenv("SUPABASE_TEST_URL", "http://127.0.0.1:54321")
SUPABASE_TEST_SERVICE_KEY = os.getenv(
    "SUPABASE_TEST_SERVICE_KEY",
    # Default local service-role key emitted by `supabase start`
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU",
)
SUPABASE_TEST_ANON_KEY = os.getenv(
    "SUPABASE_TEST_ANON_KEY",
    # Default local anon key emitted by `supabase start`
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0",
)

USER_A_EMAIL = "user_a@test.local"
USER_A_PASSWORD = "password123"

USER_B_EMAIL = "user_b@test.local"
USER_B_PASSWORD = "password123"

# Populated at runtime after admin-creating users
USER_A_ID: str = ""
USER_B_ID: str = ""


# ---------------------------------------------------------------------------
# Skip-all guard – gracefully skip when local Supabase isn't running
# ---------------------------------------------------------------------------
def _supabase_is_running() -> bool:
    """Return True if the local Supabase API port is reachable."""
    try:
        host = SUPABASE_TEST_URL.split("//")[1].split(":")[0]
        port = int(SUPABASE_TEST_URL.rsplit(":", 1)[1].rstrip("/"))
        with socket.create_connection((host, port), timeout=2):
            return True
    except (OSError, ValueError, IndexError):
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _supabase_is_running(),
        reason="Local Supabase is not running (start with `supabase start`)",
    ),
]


def _ensure_test_user(email: str, password: str) -> str:
    """Create a test user via sign-up, return user id.

    Uses the anon-key client sign_up endpoint which handles its own
    schema properly (unlike raw SQL inserts into auth.users).
    """
    client = create_client(SUPABASE_TEST_URL, SUPABASE_TEST_ANON_KEY)
    try:
        resp = client.auth.sign_up({"email": email, "password": password})
        return resp.user.id
    except Exception:
        # User may already exist; try to sign in instead
        resp = client.auth.sign_in_with_password({"email": email, "password": password})
        return resp.user.id


# ---------------------------------------------------------------------------
# Session-scoped clients
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def service_supabase() -> Client:
    """Service-role client – bypasses RLS."""
    return create_client(SUPABASE_TEST_URL, SUPABASE_TEST_SERVICE_KEY)


@pytest.fixture(scope="session")
def user_a_supabase(service_supabase: Client) -> Client:
    """Authenticated client for User A (subject to RLS)."""
    global USER_A_ID
    USER_A_ID = _ensure_test_user(USER_A_EMAIL, USER_A_PASSWORD)
    # Approve user so RLS policies that check profiles.approved pass
    service_supabase.table("profiles").update({"approved": True}).eq("id", USER_A_ID).execute()
    client = create_client(SUPABASE_TEST_URL, SUPABASE_TEST_ANON_KEY)
    client.auth.sign_in_with_password({"email": USER_A_EMAIL, "password": USER_A_PASSWORD})
    return client


@pytest.fixture(scope="session")
def user_b_supabase(service_supabase: Client) -> Client:
    """Authenticated client for User B (subject to RLS)."""
    global USER_B_ID
    USER_B_ID = _ensure_test_user(USER_B_EMAIL, USER_B_PASSWORD)
    # Approve user so RLS tests reflect ownership isolation, not approval blocking
    service_supabase.table("profiles").update({"approved": True}).eq("id", USER_B_ID).execute()
    client = create_client(SUPABASE_TEST_URL, SUPABASE_TEST_ANON_KEY)
    client.auth.sign_in_with_password({"email": USER_B_EMAIL, "password": USER_B_PASSWORD})
    return client


@pytest.fixture(scope="session")
def user_a_id(user_a_supabase: Client) -> str:
    """User A's UUID (available after user_a_supabase creates the user)."""
    return USER_A_ID


@pytest.fixture(scope="session")
def user_b_id(user_b_supabase: Client) -> str:
    """User B's UUID (available after user_b_supabase creates the user)."""
    return USER_B_ID


# ---------------------------------------------------------------------------
# Function-scoped test data – auto-cleaned via CASCADE
# ---------------------------------------------------------------------------
@pytest.fixture()
def case_id(service_supabase: Client, user_a_id: str) -> uuid.UUID:
    """Create a case owned by User A; deleted after test via CASCADE."""
    row = (
        service_supabase.table("cases")
        .insert({
            "user_id": user_a_id,
            "client_name": "Integration Test Client",
            "jurisdiction": "Florida",
            "status": "pending",
        })
        .execute()
    )
    cid = row.data[0]["id"]
    yield uuid.UUID(cid)
    # Cleanup – CASCADE deletes documents + analysis_results
    service_supabase.table("cases").delete().eq("id", cid).execute()


@pytest.fixture()
def document_id(service_supabase: Client, case_id: uuid.UUID) -> uuid.UUID:
    """Create a document in the test case; auto-deleted via CASCADE on case."""
    row = (
        service_supabase.table("documents")
        .insert({
            "case_id": str(case_id),
            "file_name": "test_document.pdf",
            "file_type": "application/pdf",
            "file_size": 12345,
            "storage_path": f"test/{uuid.uuid4()}/test_document.pdf",
            "status": "ready",
        })
        .execute()
    )
    return uuid.UUID(row.data[0]["id"])
