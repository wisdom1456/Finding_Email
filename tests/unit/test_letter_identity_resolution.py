"""Unit tests for letter identity fallback resolution."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from legal_portal.api.routes import analysis as analysis_routes


class _FakeSupabaseQuery:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows
        self._filters: List[tuple[str, Any]] = []

    def select(self, *_args, **_kwargs):
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

    def table(self, table_name: str):
        return _FakeSupabaseQuery(self._tables.get(table_name, []))


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
