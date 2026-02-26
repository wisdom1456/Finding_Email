"""Integration-style tests for findings stream event contract and budget behavior."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from legal_portal.api.routes import analysis as analysis_routes


def _build_analysis_record(analysis_id: str = "analysis-test-1") -> Dict[str, Any]:
    """Build a minimal completed analysis record required by stream endpoint."""
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
                            "date": "2022-02-28",
                            "description": "Full Bloom Down Payment entry posted.",
                            "source_document": "Investor Ledger",
                        },
                        {
                            "date": "2023-02-14",
                            "description": "Email update acknowledged changed circumstances.",
                            "source_document": "Update Email",
                        },
                    ],
                    "financial_data": [
                        {
                            "amount": 47656.0,
                            "description": "Full Bloom Down Payment",
                            "date": "2022-02-28",
                            "source_document": "Investor Ledger",
                        },
                        {
                            "amount": 3300.0,
                            "description": "Expense transfer",
                            "date": "2022-06-13",
                            "source_document": "Project Ledger",
                        },
                    ],
                    "key_documents": [
                        {
                            "document_name": "Signed Financing Memo",
                            "document_type": "Contract",
                            "date": "2022-02-15",
                            "significance": "Primary deal terms",
                        }
                    ],
                    "preliminary_issues": ["Repayment non-performance", "Entity targeting"],
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
    def __init__(self, supabase: "_FakeSupabase", table_name: str):
        self.supabase = supabase
        self.table_name = table_name
        self._operation = "select"
        self._payload: Dict[str, Any] = {}

    def select(self, *_args, **_kwargs):
        self._operation = "select"
        return self

    def update(self, payload: Dict[str, Any]):
        self._operation = "update"
        self._payload = payload
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self.table_name == "analysis_results" and self._operation == "select":
            return SimpleNamespace(data=[self.supabase.analysis_record])
        if self.table_name == "analysis_results" and self._operation == "update":
            self.supabase.last_update_payload = self._payload
            if "result" in self._payload:
                self.supabase.analysis_record["result"] = self._payload["result"]
            return SimpleNamespace(data=[{"id": self.supabase.analysis_record["id"]}])
        return SimpleNamespace(data=[])


class _FakeSupabase:
    def __init__(self, analysis_record: Dict[str, Any]):
        self.analysis_record = analysis_record
        self.last_update_payload: Optional[Dict[str, Any]] = None

    def table(self, table_name: str):
        return _FakeSupabaseQuery(self, table_name)


class _FakeOpenAIClient:
    def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
        self.args = args
        self.kwargs = kwargs


@dataclass
class _SettingsStub:
    letter_stream_schema_v2: bool = True
    letter_quality_lint_enabled: bool = True
    letter_conditional_repair_enabled: bool = True
    letter_strategy_enabled: bool = True
    letter_quality_critic_enabled: bool = True
    letter_term_micro_explainers_enabled: bool = True
    letter_internal_budget_seconds: int = 240
    letter_context_budget_seconds: int = 20
    letter_draft_budget_seconds: int = 60
    letter_lint_budget_seconds: int = 20
    letter_repair_budget_seconds: int = 30
    letter_finalize_budget_seconds: int = 10
    letter_stream_heartbeat_seconds: int = 1
    letter_strategy_budget_seconds: int = 15
    letter_critic_budget_seconds: int = 20


async def _collect_sse_events(streaming_response) -> List[Dict[str, Any]]:
    """Collect and parse SSE payloads from StreamingResponse."""
    raw = ""
    async for chunk in streaming_response.body_iterator:
        if isinstance(chunk, (bytes, bytearray)):
            raw += chunk.decode("utf-8")
        else:
            raw += str(chunk)

    events: List[Dict[str, Any]] = []
    for block in raw.split("\n\n"):
        lines = [line for line in block.splitlines() if line.startswith("data: ")]
        if not lines:
            continue
        payload = "\n".join(line[len("data: "):] for line in lines).strip()
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


async def _no_op_ensure_gap(*_args, **_kwargs) -> None:
    return None


async def _fake_ai_preferences(*_args, **_kwargs) -> Dict[str, str]:
    return {}


@pytest.mark.asyncio
async def test_findings_stream_event_order_with_strategy_critic_and_repair(monkeypatch):
    """Stream emits expected v2 phase/event order and applies critic+repair path."""
    record = _build_analysis_record("analysis-stream-order")
    supabase = _FakeSupabase(record)
    settings = _SettingsStub()

    class _FakeJsonProcessingService:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            self.args = args
            self.kwargs = kwargs

        async def build_findings_strategy(self, **_kwargs):
            return {
                "case_summary": "Strategy summary",
                "ranked_theories": [],
                "timeline_highlights": [],
                "risk_flags": [],
                "uncertainty_items": [],
                "recommended_sequence": [],
            }

        async def stream_findings_letter_adaptive(self, **_kwargs):
            yield "Initial draft text with contract and timeline anchor."
            yield " Additional discussion of repayment obligations."

        async def run_quality_critic(self, **_kwargs):
            return {
                "failed_sections": [
                    {
                        "section_name": "Legal Theories",
                        "issue_type": "evidence_linkage",
                        "required_fix": "Add one explicit date and amount anchor.",
                        "do_not_change": "Facts section wording",
                        "priority": "high",
                    }
                ]
            }

        async def repair_letter_constraints(
            self,
            _draft_markdown,
            _violations,
            *,
            mode="default",
            model="gpt-5-mini",
            critic_feedback=None,
        ):
            assert mode == "strict_quality"
            assert model == "gpt-5-mini"
            assert critic_feedback and critic_feedback.get("failed_sections")
            return (
                "Repaired draft includes February 14, 2023 email and $47,656.00 payment anchor "
                "to support the contract claim."
            )

        def _convert_markdown_to_html(self, markdown_content: str) -> str:
            return f"<html><body>{markdown_content}</body></html>"

    class _FakeLetterValidationService:
        def __init__(self):
            self.calls = 0

        def lint_client_letter(self, _content, *, mode="default", letter_type="findings"):
            self.calls += 1
            if self.calls == 1:
                return {
                    "mode": mode,
                    "letter_type": letter_type,
                    "lint_passed": False,
                    "score": 72,
                    "violations": [
                        {"rule": "evidence_linkage_score", "severity": "error", "message": "Low linkage"}
                    ],
                    "quality_report_v2": {
                        "term_explainer_passed": False,
                        "evidence_linkage_score": 0.7,
                        "section_depth_score": 0.6,
                        "unsupported_assertion_flags": [],
                    },
                }
            return {
                "mode": mode,
                "letter_type": letter_type,
                "lint_passed": True,
                "score": 97,
                "violations": [],
                "quality_report_v2": {
                    "term_explainer_passed": True,
                    "evidence_linkage_score": 0.95,
                    "section_depth_score": 0.9,
                    "unsupported_assertion_flags": [],
                },
            }

    monkeypatch.setattr(analysis_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(analysis_routes, "_ensure_fresh_gap_analysis_for_letter_generation", _no_op_ensure_gap)
    monkeypatch.setattr(analysis_routes, "_get_user_ai_preferences", _fake_ai_preferences)
    monkeypatch.setattr(analysis_routes, "OpenAIClient", _FakeOpenAIClient)
    monkeypatch.setattr(analysis_routes, "JsonProcessingService", _FakeJsonProcessingService)
    monkeypatch.setattr(analysis_routes, "LetterValidationService", _FakeLetterValidationService)
    monkeypatch.setattr(analysis_routes, "_emit_generation_metrics", lambda _metrics: None)

    response = await analysis_routes.stream_findings_letter(
        analysis_id=record["id"],
        schema_version=2,
        mode="strict_quality",
        user={"id": "user-1"},
        supabase=supabase,
    )
    events = await _collect_sse_events(response)

    event_names = [event.get("event") for event in events if isinstance(event.get("event"), str)]
    phase_names = [event.get("phase") for event in events if event.get("event") == "phase"]

    assert phase_names[:4] == ["strategy", "context_build", "draft_generation", "lint_validation"]
    assert "repair" in phase_names
    assert phase_names[-1] == "finalizing"
    assert "quality" in event_names
    assert "final" in event_names
    assert "done" in event_names

    quality_event = next(event for event in events if event.get("event") == "quality")
    metrics = quality_event["generation_metrics"]
    assert metrics["strategy_used"] is True
    assert metrics["critic_attempted"] is True
    assert metrics["critic_applied"] is True
    assert metrics["repair_applied"] is True

    final_event = next(event for event in events if event.get("event") == "final")
    assert "Repaired draft includes February 14, 2023 email" in final_event["content"]["html"]
    assert "<!DOCTYPE html>" in final_event["content"]["html"]
    assert "<head>" in final_event["content"]["html"]
    assert "<style>" in final_event["content"]["html"]

    assert supabase.last_update_payload is not None
    persisted_findings = supabase.last_update_payload["result"]["generated_letters"]["findings"]
    assert "<!DOCTYPE html>" in persisted_findings
    assert "<style>" in persisted_findings
    findings_meta = supabase.last_update_payload["result"]["generated_letters"]["findings_meta"]
    assert findings_meta["strategy_object"] is not None
    assert findings_meta["quality_report_v2"] is not None


@pytest.mark.asyncio
async def test_findings_stream_skips_critic_and_repair_when_budget_insufficient(monkeypatch):
    """Critic and repair are skipped with explicit reason when budgets are too high."""
    record = _build_analysis_record("analysis-budget-skip")
    supabase = _FakeSupabase(record)
    settings = _SettingsStub(
        letter_critic_budget_seconds=500,
        letter_repair_budget_seconds=500,
    )

    class _FakeJsonProcessingService:
        critic_called = False
        repair_called = False

        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            self.args = args
            self.kwargs = kwargs

        async def build_findings_strategy(self, **_kwargs):
            return {
                "case_summary": "Strategy summary",
                "ranked_theories": [],
                "timeline_highlights": [],
                "risk_flags": [],
                "uncertainty_items": [],
                "recommended_sequence": [],
            }

        async def stream_findings_letter_adaptive(self, **_kwargs):
            yield "Draft content with some legal theory but weak linkage."

        async def run_quality_critic(self, **_kwargs):
            _FakeJsonProcessingService.critic_called = True
            return {"failed_sections": []}

        async def repair_letter_constraints(self, *_args, **_kwargs):
            _FakeJsonProcessingService.repair_called = True
            return "Should not be used"

        def _convert_markdown_to_html(self, markdown_content: str) -> str:
            return f"<html><body>{markdown_content}</body></html>"

    class _FakeLetterValidationService:
        def lint_client_letter(self, _content, *, mode="default", letter_type="findings"):
            return {
                "mode": mode,
                "letter_type": letter_type,
                "lint_passed": False,
                "score": 70,
                "violations": [
                    {"rule": "section_depth", "severity": "error", "message": "Section too thin"}
                ],
                "quality_report_v2": {
                    "term_explainer_passed": False,
                    "evidence_linkage_score": 0.7,
                    "section_depth_score": 0.6,
                    "unsupported_assertion_flags": [],
                },
            }

    monkeypatch.setattr(analysis_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(analysis_routes, "_ensure_fresh_gap_analysis_for_letter_generation", _no_op_ensure_gap)
    monkeypatch.setattr(analysis_routes, "_get_user_ai_preferences", _fake_ai_preferences)
    monkeypatch.setattr(analysis_routes, "OpenAIClient", _FakeOpenAIClient)
    monkeypatch.setattr(analysis_routes, "JsonProcessingService", _FakeJsonProcessingService)
    monkeypatch.setattr(analysis_routes, "LetterValidationService", _FakeLetterValidationService)
    monkeypatch.setattr(analysis_routes, "_emit_generation_metrics", lambda _metrics: None)

    response = await analysis_routes.stream_findings_letter(
        analysis_id=record["id"],
        schema_version=2,
        mode="strict_quality",
        user={"id": "user-1"},
        supabase=supabase,
    )
    events = await _collect_sse_events(response)

    phase_names = [event.get("phase") for event in events if event.get("event") == "phase"]
    assert "repair" not in phase_names

    quality_event = next(event for event in events if event.get("event") == "quality")
    metrics = quality_event["generation_metrics"]
    report = quality_event["quality_report"]

    assert metrics["critic_attempted"] is False
    assert metrics["critic_skipped_reason"] == "insufficient_budget"
    assert metrics["repair_attempted"] is False
    assert report["repair_skipped"] == "insufficient_budget"
    assert _FakeJsonProcessingService.critic_called is False
    assert _FakeJsonProcessingService.repair_called is False


@pytest.mark.asyncio
async def test_findings_stream_emits_recoverable_timeout_and_finishes(monkeypatch):
    """Draft budget timeout emits recoverable error and still returns final output."""
    record = _build_analysis_record("analysis-timeout")
    supabase = _FakeSupabase(record)
    settings = _SettingsStub(
        letter_quality_lint_enabled=False,
        letter_conditional_repair_enabled=False,
        letter_strategy_enabled=False,
        letter_draft_budget_seconds=1,
        letter_internal_budget_seconds=20,
        letter_context_budget_seconds=10,
        letter_lint_budget_seconds=28,
        letter_finalize_budget_seconds=1,
        letter_stream_heartbeat_seconds=1,
    )

    class _FakeJsonProcessingService:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            self.args = args
            self.kwargs = kwargs

        async def stream_findings_letter_adaptive(self, **_kwargs):
            # >= 80 words so timeout becomes recoverable.
            yield " ".join(["anchor"] * 90)
            await asyncio.sleep(3)

        def _convert_markdown_to_html(self, markdown_content: str) -> str:
            return f"<html><body>{markdown_content}</body></html>"

    monkeypatch.setattr(analysis_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(analysis_routes, "_ensure_fresh_gap_analysis_for_letter_generation", _no_op_ensure_gap)
    monkeypatch.setattr(analysis_routes, "_get_user_ai_preferences", _fake_ai_preferences)
    monkeypatch.setattr(analysis_routes, "OpenAIClient", _FakeOpenAIClient)
    monkeypatch.setattr(analysis_routes, "JsonProcessingService", _FakeJsonProcessingService)
    monkeypatch.setattr(analysis_routes, "_emit_generation_metrics", lambda _metrics: None)

    response = await analysis_routes.stream_findings_letter(
        analysis_id=record["id"],
        schema_version=2,
        mode="strict_quality",
        user={"id": "user-1"},
        supabase=supabase,
    )
    events = await _collect_sse_events(response)

    timeout_errors = [
        event
        for event in events
        if event.get("event") == "error" and event.get("recoverable") is True
    ]
    assert timeout_errors
    assert timeout_errors[0].get("code") == "draft_budget_exceeded"

    quality_event = next(event for event in events if event.get("event") == "quality")
    assert quality_event["generation_metrics"]["timeout"] is True

    assert any(event.get("event") == "final" for event in events)
    assert any(event.get("event") == "done" for event in events)


@pytest.mark.asyncio
async def test_findings_stream_reverts_polish_when_fact_integrity_fails(monkeypatch):
    """If polish introduces drift, stream should keep pre-polish draft and mark revert reason."""
    record = _build_analysis_record("analysis-polish-integrity")
    supabase = _FakeSupabase(record)
    settings = _SettingsStub(
        letter_quality_lint_enabled=False,
        letter_conditional_repair_enabled=False,
        letter_strategy_enabled=False,
    )

    class _FakeJsonProcessingService:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            self.args = args
            self.kwargs = kwargs

        async def stream_findings_letter_adaptive(self, **_kwargs):
            yield "Original draft cites $47,656.00 paid on February 14, 2023."

        def _convert_markdown_to_html(self, markdown_content: str) -> str:
            return f"<html><body>{markdown_content}</body></html>"

    class _FakeLetterValidationService:
        def lint_client_letter(self, _content, *, mode="default", letter_type="findings"):
            return {
                "mode": mode,
                "letter_type": letter_type,
                "lint_passed": True,
                "score": 100,
                "violations": [],
                "quality_report_v2": {
                    "term_explainer_passed": True,
                    "evidence_linkage_score": 1.0,
                    "section_depth_score": 1.0,
                    "unsupported_assertion_flags": [],
                },
            }

        def check_polish_fact_integrity(self, _original, _polished, *, tracked_entities=None):
            return {
                "passed": False,
                "reason": "amount_drift,date_drift",
                "introduced_amounts": ["57656.00"],
                "removed_amounts": ["47656.00"],
                "introduced_dates": ["february 28 2023"],
                "removed_dates": ["february 14 2023"],
                "introduced_entities": [],
                "removed_entities": [],
            }

    async def _fake_polish(_openai_client, _raw_letter, timeout_seconds=55.0):
        return {
            "success": True,
            "polished_letter": "Polished text changed to $57,656.00 on February 28, 2023.",
        }

    monkeypatch.setattr(analysis_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(analysis_routes, "_ensure_fresh_gap_analysis_for_letter_generation", _no_op_ensure_gap)
    monkeypatch.setattr(analysis_routes, "_get_user_ai_preferences", _fake_ai_preferences)
    monkeypatch.setattr(analysis_routes, "OpenAIClient", _FakeOpenAIClient)
    monkeypatch.setattr(analysis_routes, "JsonProcessingService", _FakeJsonProcessingService)
    monkeypatch.setattr(analysis_routes, "LetterValidationService", _FakeLetterValidationService)
    monkeypatch.setattr("legal_portal.utils.letter_polish.polish_letter_async", _fake_polish)
    monkeypatch.setattr(analysis_routes, "_emit_generation_metrics", lambda _metrics: None)

    response = await analysis_routes.stream_findings_letter(
        analysis_id=record["id"],
        schema_version=2,
        mode="strict_quality",
        user={"id": "user-1"},
        supabase=supabase,
    )
    events = await _collect_sse_events(response)

    final_event = next(event for event in events if event.get("event") == "final")
    quality_event = next(event for event in events if event.get("event") == "quality")

    # Must keep pre-polish facts because integrity gate failed.
    assert "$47,656.00" in final_event["content"]["html"]
    assert "$57,656.00" not in final_event["content"]["html"]
    assert quality_event["generation_metrics"]["polish_reverted"] is True
    assert quality_event["generation_metrics"]["polish_revert_reason"].startswith("fact_integrity:")
