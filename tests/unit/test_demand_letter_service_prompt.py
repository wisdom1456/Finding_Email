"""Unit tests for demand-letter prompt assembly."""

from __future__ import annotations

from legal_portal.services.demand_letter_service import DemandLetterService


def test_build_demand_prompt_appends_strategy_directives() -> None:
    service = DemandLetterService(openai_client=None)  # type: ignore[arg-type]
    prompt = service._build_demand_prompt(
        target_party_name="Cuchillo Greens Grow 1, LLC",
        party_context="Party context",
        analysis_context="Analysis context",
        demand_amount=120000.0,
        demand_deadline="10 business days",
        specific_demands="1. Provide accounting",
        attorney_name="Senior Partner",
        firm_name="New Mexico Counsel",
        contact_phone="(505) 555-0199",
        contact_email="partner@example.com",
        client_name="Erica and Ron",
        jurisdiction_name="New Mexico",
        strategy_object={"ranked_theories": [{"theory": "Unjust Enrichment", "priority": 1}]},
    )

    assert "BALANCED CLIENT STRATEGY DIRECTIVES" in prompt
    assert "Present legal theories in strategy_object.ranked_theories priority order." in prompt
