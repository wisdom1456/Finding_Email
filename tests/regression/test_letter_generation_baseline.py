"""Regression baseline tests for findings and demand letter generation.

These tests establish deterministic, no-network baseline behavior for the active
generation services. They are intentionally focused on high-value output signals:
- Required structure markers
- Core factual/legal anchors (dates, amounts, statutes)
- No placeholder leakage in client-facing content
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import AsyncGenerator, Dict, Optional

import pytest

from legal_portal.core.data_models import (
    DeepAnalysis,
    FactMatrix,
    GapAnalysisResult,
    GapCategory,
    GapItem,
    GapSeverity,
    LetterStructure,
)
from legal_portal.services.demand_letter_service import DemandLetterService
from legal_portal.services.json_processing_service import JsonProcessingService

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "letters"


def _strip_html_tags(html: str) -> str:
    """Extract text content for assertions."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _sample_fact_matrix_dict() -> Dict:
    """Build a minimal valid fact matrix payload."""
    return {
        "parties": [
            {
                "name": "Amber Bell",
                "role": "Client",
                "contact_info": None,
                "first_mentioned_in": "Intake.pdf",
                "is_opposing_party": False,
                "entity_type": "individual",
            },
            {
                "name": "LLW Construction, Inc.",
                "role": "Opposing Party",
                "contact_info": "123 Main Street, Tampa, FL 33602",
                "first_mentioned_in": "Contract.pdf",
                "is_opposing_party": True,
                "entity_type": "corporation",
            },
        ],
        "timeline": [
            {
                "date": "March 15, 2025",
                "description": "LLW Construction, Inc. stopped work after partial performance.",
                "source_document": "Timeline.txt",
                "significance": "Marks transition from delay to non-performance.",
                "supporting_evidence": ["Timeline.txt", "Contract.pdf"],
            }
        ],
        "financial_data": [
            {
                "amount": 100000.0,
                "description": "Payments made by client",
                "date": "2025-02-28",
                "source_document": "PaymentRecords.pdf",
                "payment_type": "paid",
                "category": "payment_made",
            }
        ],
        "key_documents": [
            {
                "document_name": "Contract.pdf",
                "document_type": "Contract",
                "date": "2024-11-15",
                "significance": "Establishes contractual duties and scope.",
            }
        ],
        "preliminary_issues": ["Construction defects", "Breach of contract"],
        "property_details": {
            "address": "3414 South Belcher Drive, Tampa, Florida",
            "property_type": "Residential",
            "additional_details": {},
        },
        "extraction_notes": None,
    }


def _sample_deep_analysis_dict() -> Dict:
    """Build a minimal valid deep analysis payload."""
    return {
        "issue_analyses": [
            {
                "issue_name": "Construction Defect and Non-Performance",
                "legal_standard": "Contractors must perform competent work and complete agreed scope.",
                "fact_application": (
                    "The contractor accepted payment and left critical work incomplete."
                ),
                "statute_analysis": "Florida Statute § 558.004 applies to pre-suit notice requirements.",
                "case_law_support": None,
                "remedies_available": ["Damages", "Specific performance", "Pre-suit demand"],
                "procedural_requirements": "Provide Chapter 558 notice before litigation.",
                "confidence_level": "strong",
                "supporting_evidence": ["Contract.pdf", "PaymentRecords.pdf", "Timeline.txt"],
            }
        ],
        "risk_assessment": {
            "major_risks": ["Potential lien exposure"],
            "risk_mitigation_steps": ["Immediate pre-suit notice and demand strategy"],
            "statute_of_limitations_concerns": None,
            "evidence_gaps": [],
        },
        "deadline_tracking": [
            {
                "deadline_date": "2026-03-01",
                "description": "Serve pre-suit notice",
                "consequence_if_missed": "Delay in filing and reduced leverage",
                "urgency": "important",
                "statute_basis": "Florida Statute § 558.004",
            }
        ],
        "evidence_strength": {
            "strong_evidence": ["Signed contract", "Documented payment history"],
            "weak_evidence": [],
            "missing_evidence": [],
            "overall_strength": "strong",
        },
        "overall_case_strength": "strong",
        "key_strengths": ["Substantial documented payment", "Clear non-performance timeline"],
        "key_challenges": ["Potential third-party lien filings"],
        "is_viable": True,
        "viability_reasoning": "Facts and records support actionable claims.",
        "recommend_demand_letter": True,
    }


def _sample_missing_doc_gap_analysis(gap_title: str, gap_description: str) -> GapAnalysisResult:
    """Build a minimal gap-analysis payload for prompt-guardrail tests."""
    gap = GapItem(
        gap_id="gap-doc-1",
        category=GapCategory.MISSING_DOCUMENT,
        severity=GapSeverity.HIGH,
        title=gap_title,
        description=gap_description,
        affected_issue="Contract formation",
        related_documents=[],
        recommendations=["Provide the referenced agreement."],
        impact_on_case="May weaken proof of agreed terms.",
    )
    return GapAnalysisResult(
        total_gaps=1,
        critical_count=0,
        high_count=1,
        medium_count=0,
        low_count=0,
        gaps_by_category={GapCategory.MISSING_DOCUMENT.value: [gap]},
        overall_completeness_score=72.0,
        attorney_summary="One missing-document issue remains.",
    )


class FakeLetterOpenAIClient:
    """Deterministic in-memory OpenAI client stub for regression tests."""

    def __init__(self, findings_markdown: str, demand_markdown: str) -> None:
        self.findings_markdown = findings_markdown
        self.demand_markdown = demand_markdown
        self.last_response_request: Optional[Dict] = None
        self.last_stream_request: Optional[Dict] = None
        self.last_chat_completion_request: Optional[Dict] = None

    def get_preferred_model(self, _operation_type: str, fallback: str = "gpt-5.2") -> str:
        """Return fallback model to preserve service behavior."""
        return fallback

    def create_response(self, **kwargs) -> Dict:
        """Return deterministic findings content for non-streaming calls."""
        self.last_response_request = kwargs
        return {
            "content": self.findings_markdown,
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
            "model": kwargs.get("model", "fake-model"),
        }

    def create_chat_completion(self, **kwargs) -> Dict:
        """Return deterministic content for polish-pass chat calls."""
        self.last_chat_completion_request = kwargs
        return {
            "content": self.findings_markdown,
            "usage": {"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150},
            "model": kwargs.get("model", "fake-model"),
        }

    async def create_response_stream(self, **kwargs) -> AsyncGenerator[str, None]:
        """Yield deterministic demand content in stream-sized chunks."""
        self.last_stream_request = kwargs
        chunk_size = 120
        for idx in range(0, len(self.demand_markdown), chunk_size):
            yield self.demand_markdown[idx : idx + chunk_size]


@pytest.fixture
def baseline_markdown_fixtures() -> Dict[str, str]:
    """Load deterministic baseline markdown fixtures."""
    findings = (FIXTURES_DIR / "findings_markdown_baseline.md").read_text(encoding="utf-8")
    demand = (FIXTURES_DIR / "demand_markdown_baseline.md").read_text(encoding="utf-8")
    return {"findings": findings, "demand": demand}


@pytest.mark.asyncio
async def test_findings_generation_baseline_contains_required_markers(
    baseline_markdown_fixtures, monkeypatch
):
    """Findings letter baseline should preserve key structure and avoid placeholders."""
    # Keep polish pass deterministic: return the unmodified raw letter.
    monkeypatch.setattr(
        "legal_portal.utils.letter_polish.LetterPolisher.polish_letter",
        lambda self, raw_letter: {
            "success": True,
            "polished_letter": raw_letter,
            "changes_made": [],
            "original_length": len(raw_letter),
            "polished_length": len(raw_letter),
        },
    )

    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    letter_html = await service.generate_findings_letter_adaptive(
        intake_content='{"client_name":"Amber Bell"}',
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[
            {
                "citation": "Florida Statute § 558.004",
                "title": "Notice and opportunity to repair",
                "summary": "Establishes pre-suit notice requirements.",
                "relevance_reason": "Construction defect pre-suit process",
            }
        ],
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        confirmed_qa_pairs=[{"question": "Main issue?", "answer": "Incomplete contractor work"}],
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        jurisdiction="Florida",
    )

    assert "<html" in letter_html.lower()
    text = _strip_html_tags(letter_html)

    assert "Here are the key points of our analysis:" in text
    assert "March 15, 2025" in text
    assert "$100,000.00" in text
    assert "Florida Statute § 558.004" in text

    assert "[EMAIL PLACEHOLDER]" not in text
    assert "[insert]" not in text.lower()
    assert " N/A " not in f" {text} "


@pytest.mark.asyncio
async def test_demand_generation_baseline_contains_required_markers(baseline_markdown_fixtures):
    """Demand letter baseline should preserve formal structure and avoid placeholders."""
    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = DemandLetterService(openai_client=fake_client)

    letter_html = await service.generate_demand_letter(
        fact_matrix_dict=_sample_fact_matrix_dict(),
        deep_analysis_dict=_sample_deep_analysis_dict(),
        target_party_name="LLW Construction, Inc.",
        demand_amount=100000.0,
        demand_deadline="10 business days",
        specific_demands=[
            "Provide a detailed cure plan in writing.",
            "Remediate all defective work at no cost.",
            "Reimburse amounts paid for incomplete work.",
        ],
        attorney_info={
            "name": "Franklin Riley",
            "firm": "Bernhardt Riley, Attorneys at Law",
            "phone": "(727) 275-9575",
            "email": "counsel@firm.com",
        },
        client_name="Amber Bell",
        jurisdiction="Florida",
    )

    assert "<html" in letter_html.lower()
    text = _strip_html_tags(letter_html)

    assert "As such, let this correspondence serve as a formal demand that:" in text
    assert "One Hundred Thousand U.S. Dollars and Zero Cents ($100,000.00)" in text
    assert "RE: Demand Letter Regarding" in text

    assert "[insert]" not in text.lower()
    assert "[EMAIL PLACEHOLDER]" not in text
    assert " N/A " not in f" {text} "


@pytest.mark.asyncio
async def test_findings_prompt_context_consistent_for_adaptive_and_stream(
    baseline_markdown_fixtures, monkeypatch
):
    """Adaptive and streaming prompts should share Q&A formatting and CLIO handling."""
    monkeypatch.setattr(
        "legal_portal.utils.letter_polish.LetterPolisher.polish_letter",
        lambda self, raw_letter: {
            "success": True,
            "polished_letter": raw_letter,
            "changes_made": [],
            "original_length": len(raw_letter),
            "polished_length": len(raw_letter),
        },
    )

    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    qa_pairs = [
        {"question": "What happened?", "answer": "Work stopped after payment."},
        {"question": "Did we send notice?", "answer": "Yes, written notice was sent."},
    ]
    clio_marker = "CLIO_CTX_MARKER_UNIQUE"
    quality_marker = "QUALITY_CTX_MARKER_UNIQUE"

    await service.generate_findings_letter_adaptive(
        intake_content='{"client_name":"Amber Bell"}',
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[
            {
                "citation": "Florida Statute § 558.004",
                "title": "Notice and opportunity to repair",
                "summary": "Establishes pre-suit notice requirements.",
                "relevance_reason": "Construction defect pre-suit process",
            }
        ],
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        confirmed_qa_pairs=qa_pairs,
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        quality_context=quality_marker,
        clio_matter_context=clio_marker,
        jurisdiction="Florida",
    )

    async for _token in service.stream_findings_letter_adaptive(
        intake_content='{"client_name":"Amber Bell"}',
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[
            {
                "citation": "Florida Statute § 558.004",
                "title": "Notice and opportunity to repair",
                "summary": "Establishes pre-suit notice requirements.",
                "relevance_reason": "Construction defect pre-suit process",
            }
        ],
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        confirmed_qa_pairs=qa_pairs,
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        quality_context=quality_marker,
        clio_matter_context=clio_marker,
        jurisdiction="Florida",
    ):
        pass

    adaptive_prompt = fake_client.last_response_request["input"]
    stream_prompt = fake_client.last_stream_request["input"]

    for prompt in (adaptive_prompt, stream_prompt):
        assert "USER-CONFIRMED INTAKE QUESTIONS & ANSWERS:" in prompt
        assert "1. Q: What happened?" in prompt
        assert "A: Work stopped after payment." in prompt
        assert "2. Q: Did we send notice?" in prompt
        assert "A: Yes, written notice was sent." in prompt
        assert str(qa_pairs) not in prompt
        assert quality_marker in prompt
        assert prompt.count(clio_marker) == 1


@pytest.mark.asyncio
async def test_findings_from_json_prompt_uses_single_clio_section(baseline_markdown_fixtures):
    """JSON findings prompt should format Q&A pairs and avoid CLIO duplication."""
    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    qa_pairs = [{"question": "Primary concern?", "answer": "Incomplete contractor work."}]
    clio_marker = "CLIO_CTX_SINGLE_INSERTION"
    quality_marker = "QUALITY_CTX_BASELINE"

    await service.generate_findings_letter_from_json(
        intake_content='{"client_name":"Amber Bell"}',
        document_summaries_json='{"documents":[{"name":"Contract.pdf"}]}',
        quality_context=quality_marker,
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        confirmed_qa_pairs=qa_pairs,
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        statute_context="Florida Statute § 558.004",
        clio_matter_context=clio_marker,
        jurisdiction="Florida",
    )

    from_json_prompt = fake_client.last_response_request["input"]
    assert "USER-CONFIRMED INTAKE QUESTIONS & ANSWERS:" in from_json_prompt
    assert "1. Q: Primary concern?" in from_json_prompt
    assert "A: Incomplete contractor work." in from_json_prompt
    assert quality_marker in from_json_prompt
    assert from_json_prompt.count(clio_marker) == 1


@pytest.mark.asyncio
async def test_findings_from_json_prompt_avoids_email_placeholder_when_missing(
    baseline_markdown_fixtures,
):
    """Findings prompts should not include `[EMAIL PLACEHOLDER]` when contact email is absent."""
    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    await service.generate_findings_letter_from_json(
        intake_content='{"client_name":"Amber Bell"}',
        document_summaries_json='{"documents":[{"name":"Contract.pdf"}]}',
        quality_context="QUALITY_CTX_BASELINE",
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        confirmed_qa_pairs=[],
        contact_phone=None,
        contact_email=None,
        statute_context="Florida Statute § 558.004",
        clio_matter_context="",
        jurisdiction="Florida",
    )

    from_json_prompt = fake_client.last_response_request["input"]
    assert "[EMAIL PLACEHOLDER]" not in from_json_prompt


@pytest.mark.asyncio
async def test_findings_prompt_marks_present_agreement_gap_as_already_provided(
    baseline_markdown_fixtures, monkeypatch
):
    """Prompt context should avoid treating present agreements as missing docs."""
    monkeypatch.setattr(
        "legal_portal.utils.letter_polish.LetterPolisher.polish_letter",
        lambda self, raw_letter: {
            "success": True,
            "polished_letter": raw_letter,
            "changes_made": [],
            "original_length": len(raw_letter),
            "polished_length": len(raw_letter),
        },
    )

    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    await service.generate_findings_letter_adaptive(
        intake_content='{"client_name":"Amber Bell"}',
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[],
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        jurisdiction="Florida",
        original_documents={
            "Subscription Agreement.pdf": "Subscription Agreement terms...",
            "Operating Agreement.pdf": "Operating Agreement terms...",
        },
        gap_analysis=_sample_missing_doc_gap_analysis(
            gap_title="Missing subscription agreement",
            gap_description="No subscription agreement was provided.",
        ),
    )

    prompt = fake_client.last_response_request["input"]
    assert "--- DOCUMENT REGISTER (AUTHORITATIVE LIST OF PROVIDED FILES) ---" in prompt
    assert "Subscription Agreement.pdf | type=Case Document" in prompt
    assert "**DOCUMENTS ALREADY PRESENT (do NOT request again):**" in prompt
    assert "- Missing subscription agreement" in prompt
    assert "\n**MISSING DOCUMENTS (do not assume contents):**\n- Missing subscription agreement\n" not in prompt


@pytest.mark.asyncio
async def test_findings_prompt_keeps_execution_gap_without_signature_proof(
    baseline_markdown_fixtures, monkeypatch
):
    """Execution-specific gaps should remain until signature evidence reconciles them."""
    monkeypatch.setattr(
        "legal_portal.utils.letter_polish.LetterPolisher.polish_letter",
        lambda self, raw_letter: {
            "success": True,
            "polished_letter": raw_letter,
            "changes_made": [],
            "original_length": len(raw_letter),
            "polished_length": len(raw_letter),
        },
    )

    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    await service.generate_findings_letter_adaptive(
        intake_content='{"client_name":"Amber Bell"}',
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[],
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        jurisdiction="Florida",
        original_documents={
            "Subscription Agreement.pdf": "Unsigned copy for review",
        },
        gap_analysis=_sample_missing_doc_gap_analysis(
            gap_title="Missing executed subscription agreement",
            gap_description="No signed subscription agreement was provided.",
        ),
    )

    prompt = fake_client.last_response_request["input"]
    assert "**MISSING DOCUMENTS (do not assume contents):**" in prompt
    assert "- Missing executed subscription agreement" in prompt


@pytest.mark.asyncio
async def test_findings_prompt_does_not_suppress_missing_gap_from_generic_filename(
    baseline_markdown_fixtures, monkeypatch
):
    """Generic present filenames should not hide unrelated missing document gaps."""
    monkeypatch.setattr(
        "legal_portal.utils.letter_polish.LetterPolisher.polish_letter",
        lambda self, raw_letter: {
            "success": True,
            "polished_letter": raw_letter,
            "changes_made": [],
            "original_length": len(raw_letter),
            "polished_length": len(raw_letter),
        },
    )

    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    await service.generate_findings_letter_adaptive(
        intake_content='{"client_name":"Amber Bell"}',
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[],
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        jurisdiction="Florida",
        original_documents={
            "Contract.pdf": "General construction contract text",
        },
        gap_analysis=_sample_missing_doc_gap_analysis(
            gap_title="Missing operating agreement",
            gap_description="No operating agreement was provided.",
        ),
    )

    prompt = fake_client.last_response_request["input"]
    assert "**MISSING DOCUMENTS (do not assume contents):**" in prompt
    assert "- Missing operating agreement" in prompt
    assert "**DOCUMENTS ALREADY PRESENT (do NOT request again):**" not in prompt


@pytest.mark.asyncio
async def test_findings_prompt_uses_document_summaries_for_register_context(
    baseline_markdown_fixtures, monkeypatch
):
    """Document register should reflect provided structured summaries and case_place context."""
    monkeypatch.setattr(
        "legal_portal.utils.letter_polish.LetterPolisher.polish_letter",
        lambda self, raw_letter: {
            "success": True,
            "polished_letter": raw_letter,
            "changes_made": [],
            "original_length": len(raw_letter),
            "polished_length": len(raw_letter),
        },
    )

    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    await service.generate_findings_letter_adaptive(
        intake_content='{"client_name":"Amber Bell"}',
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[],
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        jurisdiction="Florida",
        original_documents=None,
        document_summaries_for_context=[
            {
                "document_name": "Subscription_Agreement_EJAJ-TX_Final120.doc.pdf",
                "document_type": "Contract",
                "legal_significance": "Defines investor rights and obligations.",
            }
        ],
        gap_analysis=_sample_missing_doc_gap_analysis(
            gap_title="Missing subscription agreement",
            gap_description="No subscription agreement was provided.",
        ),
    )

    prompt = fake_client.last_response_request["input"]
    assert "--- DOCUMENT REGISTER (AUTHORITATIVE LIST OF PROVIDED FILES) ---" in prompt
    assert "Subscription_Agreement_EJAJ-TX_Final120.doc.pdf | type=Contract" in prompt
    assert "case_place=Defines investor rights and obligations." in prompt
    assert "**DOCUMENTS ALREADY PRESENT (do NOT request again):**" in prompt


@pytest.mark.asyncio
async def test_findings_prompt_includes_authority_fields_from_document_registry(
    baseline_markdown_fixtures, monkeypatch
):
    """Document registry rows should appear as authoritative context in findings prompts."""
    monkeypatch.setattr(
        "legal_portal.utils.letter_polish.LetterPolisher.polish_letter",
        lambda self, raw_letter: {
            "success": True,
            "polished_letter": raw_letter,
            "changes_made": [],
            "original_length": len(raw_letter),
            "polished_length": len(raw_letter),
        },
    )

    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    await service.generate_findings_letter_adaptive(
        intake_content='{"client_name":"Amber Bell"}',
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[],
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        jurisdiction="Florida",
        document_registry=[
            {
                "document_name": "Subscription Agreement.pdf",
                "document_type": "Contract",
                "role_in_case": "deal terms and investor rights",
                "authority_level": "controlling_signed_instrument",
                "execution_status": "signed",
                "primary_instrument": "subscription agreement",
                "legal_significance": "Defines investor rights and obligations.",
                "instrument_hints": ["subscription agreement"],
            }
        ],
    )

    prompt = fake_client.last_response_request["input"]
    assert "authority=controlling_signed_instrument" in prompt
    assert "execution=signed" in prompt
    assert "instrument=subscription agreement" in prompt


@pytest.mark.asyncio
async def test_findings_generation_retries_compact_prompt_after_empty_response(
    baseline_markdown_fixtures, monkeypatch
):
    """If the first adaptive call is empty, service should retry with compact context."""
    monkeypatch.setattr(
        "legal_portal.utils.letter_polish.LetterPolisher.polish_letter",
        lambda self, raw_letter: {
            "success": True,
            "polished_letter": raw_letter,
            "changes_made": [],
            "original_length": len(raw_letter),
            "polished_length": len(raw_letter),
        },
    )

    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    prompts = []

    def _flaky_findings_call(prompt, *_args):
        prompts.append(prompt)
        if len(prompts) == 1:
            return ""
        return baseline_markdown_fixtures["findings"]

    monkeypatch.setattr(service, "_make_openai_request_responses_api", _flaky_findings_call)

    letter_html = await service.generate_findings_letter_adaptive(
        intake_content='{"client_name":"Amber Bell"}',
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[],
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
        contact_phone="(727) 275-9575",
        contact_email="counsel@firm.com",
        jurisdiction="Florida",
        original_documents={
            "Subscription Agreement.pdf": "A" * 7000,
            "Operating Agreement.pdf": "B" * 7000,
        },
    )

    assert "<html" in letter_html.lower()
    assert len(prompts) == 2
    assert "--- FULL DOCUMENT CONTENT (for precision and citations) ---" in prompts[0]
    assert "--- FULL DOCUMENT CONTENT (for precision and citations) ---" not in prompts[1]


def test_format_multi_stage_context_limits_raw_document_budget(baseline_markdown_fixtures):
    """Raw document context should be bounded for large case files."""
    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = JsonProcessingService(client=fake_client, config={})

    many_docs = {f"Doc-{i}.txt": "Z" * 7000 for i in range(25)}
    context = service._format_multi_stage_context(
        fact_matrix=FactMatrix(**_sample_fact_matrix_dict()),
        legal_analysis=DeepAnalysis(**_sample_deep_analysis_dict()),
        structure_guidance=LetterStructure(
            style="natural_flow",
            intro="Here are the key points of our analysis:",
            issue_format="flowing_bullet_paragraphs",
            reasoning="Natural flow preferred for client readability.",
        ),
        verified_statutes=[],
        original_documents=many_docs,
        document_summaries=None,
        gap_analysis=None,
    )

    assert context.count("\nDOCUMENT: ") <= service._MAX_RAW_DOCS_FOR_PROMPT
    assert "omitted from full text context to preserve model context budget" in context


@pytest.mark.asyncio
async def test_demand_prompt_avoids_na_placeholder_when_amount_missing(baseline_markdown_fixtures):
    """Demand prompt should not inject `N/A` for missing demand amount."""
    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=baseline_markdown_fixtures["demand"],
    )
    service = DemandLetterService(openai_client=fake_client)

    async for _token in service.stream_demand_letter(
        fact_matrix_dict=_sample_fact_matrix_dict(),
        deep_analysis_dict=_sample_deep_analysis_dict(),
        target_party_name="LLW Construction, Inc.",
        demand_amount=None,
        demand_deadline="10 business days",
        specific_demands=["Provide a written cure plan."],
        attorney_info={
            "name": "Franklin Riley",
            "firm": "Bernhardt Riley, Attorneys at Law",
            "phone": "(727) 275-9575",
            "email": "counsel@firm.com",
        },
        client_name="Amber Bell",
        jurisdiction="Florida",
    ):
        pass

    demand_prompt = fake_client.last_stream_request["input"]
    assert "Amount: N/A" not in demand_prompt
    assert "Amount: To be determined based on currently documented losses." in demand_prompt


@pytest.mark.asyncio
async def test_demand_generation_strips_streamed_markdown_code_fences(
    baseline_markdown_fixtures,
):
    """Demand generation should remove markdown code fences before HTML formatting."""
    fake_client = FakeLetterOpenAIClient(
        findings_markdown=baseline_markdown_fixtures["findings"],
        demand_markdown=(
            "```markdown\n## RE: Demand Letter Regarding Construction Defects\n\n"
            "As such, let this correspondence serve as a formal demand that:\n```"
        ),
    )
    service = DemandLetterService(openai_client=fake_client)

    letter_html = await service.generate_demand_letter(
        fact_matrix_dict=_sample_fact_matrix_dict(),
        deep_analysis_dict=_sample_deep_analysis_dict(),
        target_party_name="LLW Construction, Inc.",
        demand_amount=100000.0,
        demand_deadline="10 business days",
        specific_demands=["Provide a detailed cure plan in writing."],
        attorney_info={
            "name": "Franklin Riley",
            "firm": "Bernhardt Riley, Attorneys at Law",
            "phone": "(727) 275-9575",
            "email": "counsel@firm.com",
        },
        client_name="Amber Bell",
        jurisdiction="Florida",
    )

    assert "<pre>" not in letter_html.lower()
    assert "<code>" not in letter_html.lower()
