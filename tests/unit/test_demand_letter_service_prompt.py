"""Unit tests for demand-letter prompt assembly."""

from __future__ import annotations

from legal_portal.services.letters.demand_letter_service import DemandLetterService


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


def test_build_demand_prompt_with_missing_contact_produces_no_blank_slots() -> None:
    """Regression: when phone/email are absent, the prompt must contain
    neither ``Phone: `` nor ``Email: `` labeled-empty lines, AND must
    contain no hallucination-inviting placeholders.
    """
    service = DemandLetterService(openai_client=None)  # type: ignore[arg-type]
    prompt = service._build_demand_prompt(
        target_party_name="Acme Corp",
        party_context="Party context",
        analysis_context="Analysis context",
        demand_amount=None,
        demand_deadline="10 business days",
        specific_demands="1. Provide accounting",
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley Law Firm",
        contact_phone=None,
        contact_email=None,
        client_name="Jane Doe",
        jurisdiction_name="Florida",
    )

    # Bare labeled-empty slots that previously caused gpt-4o to invent values
    assert "Phone: \n" not in prompt
    assert "Email: \n" not in prompt
    assert "Phone: {" not in prompt  # unsubstituted template var
    assert "Email: {" not in prompt
    # Known hallucinated placeholders must not appear in the prompt itself
    for token in ("(555) 555-5555", "[Last Name]", "Senior Partner"):
        assert token not in prompt, f"placeholder {token!r} leaked into prompt"


def test_build_demand_prompt_includes_rendered_signature_block() -> None:
    """The {signature_block} slot must be populated with the rendered
    multi-line signature (attorney name, firm, contact lines)."""
    service = DemandLetterService(openai_client=None)  # type: ignore[arg-type]
    prompt = service._build_demand_prompt(
        target_party_name="Acme Corp",
        party_context="Party context",
        analysis_context="Analysis context",
        demand_amount=None,
        demand_deadline="10 business days",
        specific_demands="1. Provide accounting",
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley Law Firm",
        contact_phone="(727) 275-9575",
        contact_email="franklin@brflorida.com",
        client_name="Jane Doe",
        jurisdiction_name="Florida",
    )

    assert "Franklin Riley" in prompt
    assert "Bernhardt Riley Law Firm" in prompt
    assert "(727) 275-9575" in prompt
    assert "franklin@brflorida.com" in prompt
    assert "Attorney for Jane Doe" in prompt
