"""Tests for on-demand findings letter formatting behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest
from starlette.requests import Request

from legal_portal.api.routes import analysis as analysis_routes
from legal_portal.api.routes import letter_routes
from legal_portal.core.data_models import LetterType


def _build_analysis_record(analysis_id: str = "analysis-findings-format") -> Dict[str, Any]:
    return {
        "id": analysis_id,
        "case_id": "case-1",
        "result": {
            "main_letter": "",
            "document_summaries": "[]",
            "case_analysis": "{}",
            "status": "completed",
            "intake_content": "Client invested in project and seeks recovery.",
            "artifacts": {
                "jurisdiction": "New Mexico",
                "attorney_name": "Partner Name",
                "firm_name": "Test Firm",
                "contact_phone": "(505) 555-0000",
                "contact_email": "partner@testfirm.com",
            },
            "multi_stage_result": {
                "fact_matrix": {
                    "parties": [
                        {"name": "Erica Client", "role": "Client", "is_opposing_party": False},
                        {
                            "name": "Cuchillo Greens Grow 1, LLC",
                            "role": "Opposing Party",
                            "is_opposing_party": True,
                        },
                    ],
                    "timeline": [
                        {
                            "date": "2023-02-14",
                            "description": "Email update acknowledged changed circumstances.",
                            "source_document": "Update Email",
                        }
                    ],
                    "financial_data": [
                        {
                            "amount": 47656.0,
                            "description": "Full Bloom Down Payment",
                            "date": "2022-02-28",
                            "source_document": "Investor Ledger",
                        }
                    ],
                    "key_documents": [
                        {
                            "document_name": "Signed Financing Memo",
                            "document_type": "Contract",
                            "date": "2022-02-15",
                            "significance": "Primary deal terms",
                        }
                    ],
                    "preliminary_issues": ["Repayment non-performance"],
                },
                "deep_analysis": {
                    "issue_analyses": [
                        {
                            "issue_name": "Breach of Contract",
                            "legal_standard": "Existence of contract, breach, and damages.",
                            "fact_application": "Signed terms and payment records indicate non-performance.",
                            "remedies_available": ["Damages"],
                            "confidence_level": "strong",
                            "supporting_evidence": [
                                "Signed financing memo",
                                "Investor ledger entry for $47,656.00",
                            ],
                        }
                    ],
                    "risk_assessment": {
                        "major_risks": ["Entity attribution ambiguity"],
                        "risk_mitigation_steps": ["Target correct signatory entities"],
                        "evidence_gaps": ["Need complete wire records"],
                    },
                    "deadline_tracking": [
                        {
                            "deadline_date": "2026-03-05",
                            "description": "Potential limitations trigger",
                            "consequence_if_missed": "Possible time bar",
                            "urgency": "critical",
                        }
                    ],
                    "evidence_strength": {
                        "strong_evidence": ["Signed financing memo"],
                        "weak_evidence": ["Oral statements"],
                        "missing_evidence": ["Complete repayment thread"],
                        "overall_strength": "moderate",
                    },
                    "overall_case_strength": "moderate",
                    "key_strengths": ["Signed deal docs", "Payment records"],
                    "key_challenges": ["Entity mapping"],
                    "is_viable": True,
                    "recommend_demand_letter": True,
                },
                "letter_structure": {
                    "style": "natural_flow",
                    "intro": "Here are the key points of our analysis:",
                    "issue_format": "bullet_paragraphs",
                },
                "verified_statutes": [],
                "original_documents": {},
                "document_registry": [],
            },
        },
    }


class _FakeSupabaseQuery:
    def __init__(self, supabase: "_FakeSupabase"):
        self.supabase = supabase
        self._payload: Optional[Dict[str, Any]] = None

    def update(self, payload: Dict[str, Any]):
        self._payload = payload
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        self.supabase.last_update_payload = self._payload
        if self._payload and "result" in self._payload:
            self.supabase.analysis_record["result"] = self._payload["result"]
        return SimpleNamespace(data=[{"id": self.supabase.analysis_record["id"]}])


class _FakeSupabase:
    def __init__(self, analysis_record: Dict[str, Any]):
        self.analysis_record = analysis_record
        self.last_update_payload: Optional[Dict[str, Any]] = None

    def table(self, _table_name: str):
        return _FakeSupabaseQuery(self)


class _SettingsStub:
    letter_internal_budget_seconds = 240
    letter_strategy_budget_seconds = 15
    letter_critic_budget_seconds = 20
    letter_repair_budget_seconds = 30
    letter_finalize_budget_seconds = 10
    letter_strategy_enabled = False
    letter_quality_lint_enabled = False
    letter_conditional_repair_enabled = False
    letter_quality_critic_enabled = False


class _FakeOpenAIClient:
    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.args = args
        self.kwargs = kwargs


class _FakeJsonProcessingService:
    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.args = args
        self.kwargs = kwargs

    async def generate_findings_letter_adaptive(self, **_kwargs):
        return "<html><body><div class='legal-letter'><p>Findings draft body.</p></div></body></html>"

    def _convert_markdown_to_html(self, markdown_content: str) -> str:
        return f"<html><body>{markdown_content}</body></html>"


async def _no_op_ensure_gap(*_args, **_kwargs) -> None:
    return None


@pytest.mark.asyncio
async def test_generate_letter_findings_returns_410_gone(monkeypatch):
    """Synchronous findings letter endpoint now returns 410 Gone — use streaming."""
    from fastapi import HTTPException

    analysis_record = _build_analysis_record()
    supabase = _FakeSupabase(analysis_record)

    monkeypatch.setattr(letter_routes, "get_settings", lambda: _SettingsStub())
    monkeypatch.setattr(letter_routes, "_ensure_case_access", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        letter_routes,
        "_fetch_latest_analysis_result",
        lambda *_args, **_kwargs: analysis_record,
    )
    monkeypatch.setattr(letter_routes, "_ensure_fresh_gap_analysis_for_letter_generation", _no_op_ensure_gap)
    monkeypatch.setattr(letter_routes, "_get_user_ai_preferences", _no_op_ensure_gap)
    monkeypatch.setattr(letter_routes, "_emit_generation_metrics", lambda _metrics: None)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/analysis/generate-letter",
            "headers": [],
            "query_string": b"",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await letter_routes.generate_letter.__wrapped__(  # type: ignore[attr-defined]
            letter_request=letter_routes.LetterGenerationRequest(
                case_id="case-1",
                letter_type=LetterType.FINDINGS,
            ),
            request=request,
            user={"id": "user-1"},
            supabase=supabase,
        )

    assert exc_info.value.status_code == 410
