"""Unit tests for pre-draft letter strategy generation."""

from __future__ import annotations

import asyncio
import json

from legal_portal.core.data_models import (
    CriticalDeadline,
    DeepAnalysis,
    EvidenceAssessment,
    Event,
    FactMatrix,
    FinancialItem,
    IssueAnalysis,
    KeyDocument,
    LetterStrategyV1,
    Party,
    RiskAssessment,
)
from legal_portal.services.letters.letter_strategy_service import LetterStrategyService


def _sample_fact_matrix() -> FactMatrix:
    return FactMatrix(
        parties=[
            Party(name="Erica Client", role="Client"),
            Party(name="Cuchillo Greens Grow 1, LLC", role="Opposing Party"),
        ],
        timeline=[
            Event(
                date="2022-02-28",
                description="Ledger entry for Full Bloom Down Payment.",
                source_document="Investor Ledger",
            ),
            Event(
                date="2023-02-14",
                description="Email update acknowledged changed circumstances.",
                source_document="Update Email",
            ),
        ],
        financial_data=[
            FinancialItem(
                amount=47656.00,
                description="Full Bloom Down Payment",
                date="2022-02-28",
                source_document="Investor Ledger",
            ),
            FinancialItem(
                amount=3300.00,
                description="Expense transfer",
                date="2022-06-13",
                source_document="Project Ledger",
            ),
        ],
        key_documents=[
            KeyDocument(
                document_name="Signed Financing Memo",
                document_type="Contract",
                date="2022-02-15",
                significance="Establishes financing structure",
            )
        ],
        preliminary_issues=["Repayment delay", "Entity responsibility"],
    )


def _sample_deep_analysis() -> DeepAnalysis:
    return DeepAnalysis(
        issue_analyses=[
            IssueAnalysis(
                issue_name="Breach of Contract",
                legal_standard="Existence of contract, breach, and damages.",
                fact_application="Signed financing terms and non-performance support this theory.",
                remedies_available=["Damages", "Specific performance"],
                confidence_level="strong",
                supporting_evidence=[
                    "Signed financing memo sets repayment framework.",
                    "Investor ledger shows $47,656.00 payment on 2022-02-28.",
                ],
            ),
            IssueAnalysis(
                issue_name="Misrepresentation",
                legal_standard="False statement of material fact, reliance, and damages.",
                fact_application="Update communications may support inducement narrative if corroborated.",
                remedies_available=["Damages"],
                confidence_level="moderate",
                supporting_evidence=[
                    "February 14, 2023 email acknowledges changed circumstances.",
                ],
            ),
        ],
        risk_assessment=RiskAssessment(
            major_risks=["Unclear entity attribution", "Timeline ambiguity"],
            risk_mitigation_steps=["Confirm authority records", "Finalize chronology"],
            evidence_gaps=["Need complete wire confirmations"],
        ),
        deadline_tracking=[
            CriticalDeadline(
                deadline_date="2026-03-05",
                description="Potential limitations trigger",
                consequence_if_missed="Claims may be time-barred",
                urgency="critical",
            )
        ],
        evidence_strength=EvidenceAssessment(
            strong_evidence=["Signed financing memo", "Ledger entries"],
            weak_evidence=["Oral statements"],
            missing_evidence=["Full email threads"],
            overall_strength="moderate",
        ),
        overall_case_strength="moderate",
        key_strengths=["Signed deal documents", "Payment records"],
        key_challenges=["Entity mapping", "Proof completeness"],
        is_viable=True,
        recommend_demand_letter=True,
    )


def _sample_deep_analysis_with_contract_enforceability_risk() -> DeepAnalysis:
    return DeepAnalysis(
        issue_analyses=[
            IssueAnalysis(
                issue_name="Breach of Contract",
                legal_standard="Existence of contract, breach, and damages.",
                fact_application=(
                    "Term sheet appears non-binding except confidentiality, so enforceability is disputed."
                ),
                remedies_available=["Damages"],
                confidence_level="strong",
                supporting_evidence=[
                    "Memorandum of terms states only confidentiality is binding.",
                    "Signed financing memo references anticipated repayment.",
                ],
            ),
            IssueAnalysis(
                issue_name="Unjust Enrichment / Restitution",
                legal_standard="Benefit conferred, retention unjust without repayment.",
                fact_application="Investment funds were received and used despite unresolved repayment.",
                remedies_available=["Restitution"],
                confidence_level="moderate",
                supporting_evidence=[
                    "Client reports total $120,000 contributed to project accounts.",
                    "2022-2023 investor packet entries reflect project expense use.",
                ],
            ),
            IssueAnalysis(
                issue_name="Fraudulent Misrepresentation",
                legal_standard="False statement, reliance, damages.",
                fact_application="Record lacks complete statement-level proof at this stage.",
                remedies_available=["Damages"],
                confidence_level="moderate",
                supporting_evidence=["February 14, 2023 update email acknowledges changed circumstances."],
            ),
        ],
        risk_assessment=RiskAssessment(
            major_risks=[
                "Contract enforceability risk due to non-binding term sheet language.",
                "Entity targeting uncertainty.",
            ],
            risk_mitigation_steps=["Prioritize restitution theory", "Confirm signatory authority"],
            evidence_gaps=["Need wire confirmations and proof of payment"],
        ),
        deadline_tracking=[
            CriticalDeadline(
                deadline_date="2026-03-05",
                description="Potential limitations trigger",
                consequence_if_missed="Claims may be time-barred",
                urgency="critical",
            )
        ],
        evidence_strength=EvidenceAssessment(
            strong_evidence=["Financing memo", "Investor packet entries"],
            weak_evidence=["Oral assurances"],
            missing_evidence=["Payment confirmations"],
            overall_strength="moderate",
        ),
        overall_case_strength="moderate",
        key_strengths=["Payment history exists"],
        key_challenges=["Contract enforceability uncertainty"],
        is_viable=True,
        recommend_demand_letter=True,
    )


class _FakeClient:
    def __init__(self, response_payload: dict) -> None:
        self._response_payload = response_payload

    def create_response(self, **_kwargs):  # noqa: ANN003
        return {"content": json.dumps(self._response_payload)}


def test_build_findings_strategy_fallback_schema() -> None:
    service = LetterStrategyService(client=None)
    strategy_dict = asyncio.run(
        service.build_findings_strategy(
            fact_matrix=_sample_fact_matrix(),
            deep_analysis=_sample_deep_analysis(),
            gap_analysis=None,
            allow_model=False,
        )
    )

    strategy = LetterStrategyV1(**strategy_dict)
    assert strategy.case_summary
    assert len(strategy.ranked_theories) >= 1
    assert strategy.ranked_theories[0].supporting_anchors
    assert len(strategy.timeline_highlights) >= 1


def test_build_demand_strategy_contains_specificity_package() -> None:
    service = LetterStrategyService(client=None)
    strategy_dict = asyncio.run(
        service.build_demand_strategy(
            fact_matrix=_sample_fact_matrix(),
            deep_analysis=_sample_deep_analysis(),
            target_party_name="Cuchillo Greens Grow 1, LLC",
            demand_amount=120000.00,
            demand_deadline="10 business days",
            specific_demands=["Provide accounting", "Repay funds"],
            client_name="Erica Client",
            gap_analysis=None,
            allow_model=False,
        )
    )

    strategy = LetterStrategyV1(**strategy_dict)
    assert strategy.demand_spec is not None
    assert strategy.demand_spec.targets == ["Cuchillo Greens Grow 1, LLC"]
    assert strategy.demand_spec.amount_mode == "fixed"
    assert strategy.demand_spec.cure_ladder


def test_risk_aware_ranking_prioritizes_restitution_when_contract_is_non_binding() -> None:
    service = LetterStrategyService(client=None)
    strategy_dict = asyncio.run(
        service.build_findings_strategy(
            fact_matrix=_sample_fact_matrix(),
            deep_analysis=_sample_deep_analysis_with_contract_enforceability_risk(),
            gap_analysis=None,
            allow_model=False,
        )
    )

    strategy = LetterStrategyV1(**strategy_dict)
    assert strategy.ranked_theories[0].theory.lower().startswith("unjust enrichment")
    assert "contract" in strategy.ranked_theories[1].theory.lower()


def test_model_ranking_is_normalized_to_analysis_priority() -> None:
    fake_response = {
        "case_summary": "Model summary",
        "ranked_theories": [
            {
                "theory": "Breach of Contract",
                "priority": 1,
                "rationale": "Model preferred contract first.",
                "supporting_anchors": [],
            },
            {
                "theory": "Unjust Enrichment / Restitution",
                "priority": 2,
                "rationale": "Model listed restitution second.",
                "supporting_anchors": [],
            },
        ],
        "timeline_highlights": [],
        "risk_flags": [],
        "uncertainty_items": [],
        "recommended_sequence": [],
        "demand_spec": None,
    }
    service = LetterStrategyService(client=_FakeClient(fake_response))
    strategy_dict = asyncio.run(
        service.build_findings_strategy(
            fact_matrix=_sample_fact_matrix(),
            deep_analysis=_sample_deep_analysis_with_contract_enforceability_risk(),
            gap_analysis=None,
            allow_model=True,
        )
    )

    strategy = LetterStrategyV1(**strategy_dict)
    assert strategy.ranked_theories[0].theory.lower().startswith("unjust enrichment")
    assert strategy.ranked_theories[0].rationale
    assert strategy.ranked_theories[0].supporting_anchors
