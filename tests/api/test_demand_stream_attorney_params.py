"""Attorney identity override params on GET /{analysis_id}/demand-letter/stream.

The synchronous POST /generate-letter route accepts attorney_name / firm_name /
contact_phone / contact_email and forwards them to
`_resolve_letter_identity_context(..., overrides=...)`. These tests pin the same
contract onto the streaming route:

- params present -> the overrides dict carries them (explicit param wins over profile)
- params absent  -> overrides is None, exactly as before the params existed
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

from legal_portal.api.routes import letter_routes


def _build_analysis_record(analysis_id: str = "analysis-attorney-1") -> Dict[str, Any]:
    """Minimal completed analysis record accepted by the stream endpoint."""
    return {
        "id": analysis_id,
        "case_id": "case-1",
        "result": {
            "main_letter": "",
            "document_summaries": "[]",
            "case_analysis": "{}",
            "status": "completed",
            "artifacts": {"jurisdiction": "Florida"},
            "multi_stage_result": {
                "fact_matrix": {},
                "deep_analysis": {},
            },
        },
    }


class _FakeSupabase:
    def __init__(self, analysis_record: Dict[str, Any]):
        self.analysis_record = analysis_record

    def table(self, table_name: str):
        record = self.analysis_record

        class _Query:
            def select(self, *_a, **_k):
                return self

            def eq(self, *_a, **_k):
                return self

            def limit(self, *_a, **_k):
                return self

            def execute(self):
                if table_name == "analysis_results":
                    return SimpleNamespace(data=[record])
                return SimpleNamespace(data=[])

        return _Query()


@dataclass
class _SettingsStub:
    demand_letter_stream_enabled: bool = True
    letter_stream_schema_v2: bool = True


async def _fake_ai_preferences(*_args, **_kwargs) -> Dict[str, str]:
    return {}


def _patch_route_collaborators(monkeypatch) -> Dict[str, Any]:
    """Patch route collaborators; return a dict capturing the identity-resolution call."""
    captured: Dict[str, Any] = {"called": False}

    def _capturing_resolve(**kwargs):
        captured["called"] = True
        captured["kwargs"] = kwargs
        return {
            "attorney_name": None,
            "firm_name": None,
            "firm_address": None,
            "contact_phone": None,
            "contact_email": None,
            "bar_number": None,
            "email_signature": None,
            "client_name": None,
        }

    monkeypatch.setattr(letter_routes, "get_settings", lambda: _SettingsStub())
    monkeypatch.setattr(letter_routes, "_ensure_case_access", lambda *_a, **_k: None)
    monkeypatch.setattr(letter_routes, "_get_user_ai_preferences", _fake_ai_preferences)
    monkeypatch.setattr(letter_routes, "_resolve_letter_identity_context", _capturing_resolve)
    return captured


@pytest.mark.asyncio
async def test_attorney_params_present_are_passed_as_identity_overrides(monkeypatch):
    record = _build_analysis_record()
    captured = _patch_route_collaborators(monkeypatch)

    await letter_routes.stream_demand_letter(
        analysis_id=record["id"],
        target_party_name="Acme Corp",
        demand_amount=None,
        demand_deadline="10 business days",
        specific_demands="",
        schema_version=2,
        mode="strict_quality",
        attorney_name="Jane Doe",
        firm_name="Doe & Associates",
        contact_phone="555-1234",
        contact_email="jane@doe.com",
        user={"id": "user-1"},
        supabase=_FakeSupabase(record),
    )

    assert captured["called"] is True
    assert captured["kwargs"]["overrides"] == {
        "attorney_name": "Jane Doe",
        "firm_name": "Doe & Associates",
        "contact_phone": "555-1234",
        "contact_email": "jane@doe.com",
    }


@pytest.mark.asyncio
async def test_partial_attorney_params_only_carry_provided_values(monkeypatch):
    """None and empty-string params are filtered; only real values become overrides."""
    record = _build_analysis_record()
    captured = _patch_route_collaborators(monkeypatch)

    await letter_routes.stream_demand_letter(
        analysis_id=record["id"],
        target_party_name="Acme Corp",
        demand_amount=None,
        demand_deadline="10 business days",
        specific_demands="",
        schema_version=2,
        mode="strict_quality",
        attorney_name="Jane Doe",
        firm_name=None,
        contact_phone="",  # e.g. `?contact_phone=` — empty must not override profile
        contact_email=None,
        user={"id": "user-1"},
        supabase=_FakeSupabase(record),
    )

    assert captured["kwargs"]["overrides"] == {"attorney_name": "Jane Doe"}


@pytest.mark.asyncio
async def test_attorney_params_absent_leaves_overrides_none_as_today(monkeypatch):
    """FastAPI resolves omitted query params to their None defaults; with all four
    None the route must pass overrides=None — byte-identical to the pre-override
    call, which passed no overrides argument at all."""
    record = _build_analysis_record()
    captured = _patch_route_collaborators(monkeypatch)

    await letter_routes.stream_demand_letter(
        analysis_id=record["id"],
        target_party_name="Acme Corp",
        demand_amount=None,
        demand_deadline="10 business days",
        specific_demands="",
        schema_version=2,
        mode="strict_quality",
        attorney_name=None,
        firm_name=None,
        contact_phone=None,
        contact_email=None,
        user={"id": "user-1"},
        supabase=_FakeSupabase(record),
    )

    assert captured["called"] is True
    assert captured["kwargs"].get("overrides") is None
