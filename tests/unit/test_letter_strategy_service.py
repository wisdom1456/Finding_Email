"""Unit tests for pre-draft letter strategy generation."""

from __future__ import annotations

import asyncio

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
from legal_portal.services.letter_strategy_service import LetterStrategyService


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
