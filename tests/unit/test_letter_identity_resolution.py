"""Unit tests for letter identity fallback resolution."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from legal_portal.api.routes import analysis as analysis_routes


class _FakeSupabaseQuery:
    def __init__(self, rows: List[Dict[str, Any]], select_log: List[str]):
        self._rows = rows
        self._filters: List[tuple[str, Any]] = []
        self._select_log = select_log

    def select(self, *args, **_kwargs):
        # Record select columns so tests can assert the widened SELECT
        if args and isinstance(args[0], str):
            self._select_log.append(args[0])
        return self

    def eq(self, key: str, value: Any):
        self._filters.append((key, value))
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        rows = list(self._rows)
        for key, value in self._filters:
            rows = [row for row in rows if row.get(key) == value]
        return SimpleNamespace(data=rows[:1])


class _FakeSupabase:
    def __init__(self, *, cases: List[Dict[str, Any]], profiles: List[Dict[str, Any]]):
        self._tables = {
            "cases": cases,
            "profiles": profiles,
        }
        # Maps table_name -> list of select() column strings seen
        self.select_log: Dict[str, List[str]] = {"cases": [], "profiles": []}

    def table(self, table_name: str):
        return _FakeSupabaseQuery(
            self._tables.get(table_name, []),
            self.select_log.setdefault(table_name, []),
        )


def test_resolve_letter_identity_uses_profile_when_artifacts_missing():
    """Profile should fill attorney/firm/contact when artifacts are empty."""
    supabase = _FakeSupabase(
        cases=[
            {
                "id": "case-1",
                "user_id": "user-1",
                "client_name": "Erica Corley and Ron Curl",
            }
        ],
        profiles=[
            {
                "id": "user-1",
                "full_name": "Franklin Riley",
                "firm_name": "Bernhardt Riley Law Firm",
                "phone": "(727) 275-9575",
                "email": "modible@gmail.com",
            }
        ],
    )

    resolved = analysis_routes._resolve_letter_identity_context(
        supabase=supabase,
        case_id="case-1",
        artifacts={},
    )

    assert resolved["attorney_name"] == "Franklin Riley"
    assert resolved["firm_name"] == "Bernhardt Riley Law Firm"
    assert resolved["contact_phone"] == "(727) 275-9575"
    assert resolved["contact_email"] == "modible@gmail.com"
    assert resolved["client_name"] == "Erica Corley and Ron Curl"


def test_resolve_letter_identity_honors_override_precedence():
    """Overrides should win over artifacts and profile defaults."""
    supabase = _FakeSupabase(
        cases=[
            {
                "id": "case-2",
                "user_id": "user-2",
                "client_name": "Case Client",
            }
        ],
        profiles=[
            {
                "id": "user-2",
                "full_name": "Profile Name",
                "firm_name": "Profile Firm",
                "phone": "555-0000",
                "email": "profile@example.com",
            }
        ],
    )

    resolved = analysis_routes._resolve_letter_identity_context(
        supabase=supabase,
        case_id="case-2",
        artifacts={
            "attorney_name": "Artifact Name",
            "firm_name": "Artifact Firm",
            "contact_phone": "555-1111",
            "contact_email": "artifact@example.com",
            "client_name": "Artifact Client",
        },
        overrides={
            "attorney_name": "Override Name",
            "firm_name": "Override Firm",
            "contact_phone": "555-2222",
            "contact_email": "override@example.com",
            "client_name": "Override Client",
        },
    )

    assert resolved["attorney_name"] == "Override Name"
    assert resolved["firm_name"] == "Override Firm"
    assert resolved["contact_phone"] == "555-2222"
    assert resolved["contact_email"] == "override@example.com"
    assert resolved["client_name"] == "Override Client"


def test_resolve_letter_identity_selects_widened_profile_columns():
    """SELECT must include all signature-relevant profile fields, not just 4.

    Why: previously only full_name,firm_name,phone,email were SELECTed,
    so firm_address, email_signature, bar_number, default_demand_deadline
    were unavailable to the letter prompt. Empty slots in the prompt
    template invited gpt-4o to hallucinate placeholders.
    """
    supabase = _FakeSupabase(
        cases=[{"id": "case-3", "user_id": "user-3"}],
        profiles=[{"id": "user-3", "full_name": "Test"}],
    )

    analysis_routes._resolve_letter_identity_context(
        supabase=supabase,
        case_id="case-3",
        artifacts={},
    )

    profile_selects = supabase.select_log.get("profiles", [])
    assert profile_selects, "expected a select on profiles"
    cols = profile_selects[0]
    for required in (
        "full_name",
        "firm_name",
        "firm_address",
        "phone",
        "email",
        "email_signature",
        "bar_number",
        "default_demand_deadline",
    ):
        assert required in cols, f"{required!r} missing from profile SELECT: {cols!r}"


def test_resolve_letter_identity_exposes_new_profile_fields():
    """Resolved dict should include the new fields so callers can build
    a signature block."""
    supabase = _FakeSupabase(
        cases=[{"id": "case-4", "user_id": "user-4", "client_name": "Test Client"}],
        profiles=[
            {
                "id": "user-4",
                "full_name": "Franklin Riley",
                "firm_name": "Bernhardt Riley Law Firm",
                "firm_address": "2706 US-19 ALT\nSuite 213\nPalm Harbor, FL 34683",
                "phone": "(727) 275-9575",
                "email": "franklin@brflorida.com",
                "email_signature": None,
                "bar_number": "FL-12345",
                "default_demand_deadline": "21 days from receipt",
            }
        ],
    )

    resolved = analysis_routes._resolve_letter_identity_context(
        supabase=supabase,
        case_id="case-4",
        artifacts={},
    )

    assert resolved["firm_address"] == "2706 US-19 ALT\nSuite 213\nPalm Harbor, FL 34683"
    assert resolved["bar_number"] == "FL-12345"
    assert resolved["demand_deadline_default"] == "21 days from receipt"
    # email_signature is optional and not set here — must be None, not ""
    assert resolved["email_signature"] is None


def test_resolve_letter_identity_returns_none_not_empty_string_for_missing():
    """Critical for hallucination prevention: missing fields must be None,
    never '' — downstream renderers must be able to distinguish 'absent'
    from 'present but empty' so they can OMIT the line entirely."""
    supabase = _FakeSupabase(
        cases=[{"id": "case-5", "user_id": "user-5"}],
        profiles=[
            {
                "id": "user-5",
                "full_name": "Solo Attorney",
                # phone, firm_name, etc. intentionally absent
            }
        ],
    )

    resolved = analysis_routes._resolve_letter_identity_context(
        supabase=supabase,
        case_id="case-5",
        artifacts={},
    )

    # These were not provided — must be None, not ""
    assert resolved["firm_name"] is None
    assert resolved["firm_address"] is None
    assert resolved["contact_phone"] is None
    assert resolved["contact_email"] is None
    assert resolved["bar_number"] is None
    assert resolved["email_signature"] is None
    assert resolved["demand_deadline_default"] is None
