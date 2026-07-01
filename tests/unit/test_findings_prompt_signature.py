"""Regression tests for findings-letter prompt signature handling.

The findings letter previously injected ``attorney_title="Senior Partner"``
as a hardcoded fallback and left bare ``{attorney_name}``/``{firm_name}``
template slots. With empty attorney info these rendered as labeled-empty
lines that gpt-4o filled with placeholders like ``(555) 555-5555`` and
``[Last Name]``.

This test proves the prompt never contains those hallucination triggers.
"""

from __future__ import annotations

from legal_portal.services.shared.json_processing_service import JsonProcessingService


PLACEHOLDER_TOKENS = (
    "555-5555",
    "(555)",
    "[Last Name]",
    "[First Name]",
    "[Firm Name]",
    "Senior Partner",  # hardcoded fallback that used to leak
)


def _assert_no_placeholders(prompt: str) -> None:
    for token in PLACEHOLDER_TOKENS:
        assert token not in prompt, f"placeholder {token!r} leaked into findings prompt"


def test_findings_prompt_with_full_profile_renders_signature_cleanly():
    service = JsonProcessingService(client=None, config={})  # type: ignore[arg-type]
    prompt = service._build_findings_prompt(
        jurisdiction="Florida",
        intake_content="",
        document_summaries="",
        quality_context="",
        statute_context="",
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law, PLLC",
        contact_phone="(727) 275-9575",
        contact_email="franklin@brflorida.com",
        clio_matter_context="",
        qa_context="",
        firm_address="1810 Wellness Lane\nSuite A\nTrinity, FL 34655",
        bar_number="FL-12345",
        client_name="Jane Doe",
    )

    assert "Franklin Riley" in prompt
    assert "Bernhardt Riley, Attorneys at Law, PLLC" in prompt
    assert "1810 Wellness Lane" in prompt
    assert "Trinity, FL 34655" in prompt
    assert "(727) 275-9575" in prompt
    assert "franklin@brflorida.com" in prompt
    assert "FL-12345" in prompt
    _assert_no_placeholders(prompt)
    # Old Palm Harbor HQ street tokens must not resurface post-migration.
    for _old in ("2706", "US-19", "Suite 213", "34683", "Palm Harbor"):
        assert _old not in prompt, f"old-address token {_old!r} leaked into findings prompt"


def test_findings_prompt_with_missing_contact_omits_phone_line():
    """When phone is missing, the prompt must NOT contain a Phone: label
    or any hardcoded fallback like Senior Partner. The signature block
    is shorter, not blank-padded."""
    service = JsonProcessingService(client=None, config={})  # type: ignore[arg-type]
    prompt = service._build_findings_prompt(
        jurisdiction="Florida",
        intake_content="",
        document_summaries="",
        quality_context="",
        statute_context="",
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley Law Firm",
        contact_phone=None,
        contact_email=None,
        clio_matter_context="",
        qa_context="",
        client_name="Jane Doe",
    )

    assert "Franklin Riley" in prompt
    assert "Bernhardt Riley Law Firm" in prompt
    _assert_no_placeholders(prompt)
    # Bare labeled-empty slots that previously caused hallucination
    assert "Phone: \n" not in prompt
    assert "Email: \n" not in prompt


def test_findings_prompt_with_no_attorney_name_uses_safe_sentinel():
    """If no attorney_name is provided, the renderer falls back to
    'Attorney' — never 'Senior Partner'."""
    service = JsonProcessingService(client=None, config={})  # type: ignore[arg-type]
    prompt = service._build_findings_prompt(
        jurisdiction="New Mexico",
        intake_content="",
        document_summaries="",
        quality_context="",
        statute_context="",
        attorney_name=None,
        firm_name=None,
        contact_phone=None,
        contact_email=None,
        clio_matter_context="",
        qa_context="",
        client_name="Jane Doe",
    )

    _assert_no_placeholders(prompt)
    assert "Attorney" in prompt
