"""Unit tests for letter signature rendering.

These tests prove the renderer never emits placeholder strings or blank
labeled lines that would invite LLM hallucination (e.g., 'Phone: ' with
no value, which prompts the model to invent '(555) 555-5555').
"""

from __future__ import annotations

import pytest

from legal_portal.services.letters.signature_renderer import (
    render_letter_signature_parts,
)


PLACEHOLDER_TOKENS = (
    "555-5555",
    "(555)",
    "[Last Name]",
    "[First Name]",
    "[Firm Name]",
    "[Phone]",
    "[Email]",
)


def _assert_no_placeholders(text: str) -> None:
    for token in PLACEHOLDER_TOKENS:
        assert token not in text, f"placeholder {token!r} leaked into output: {text!r}"


def test_full_profile_renders_all_lines():
    parts = render_letter_signature_parts(
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley Law Firm",
        firm_address="2706 US-19 ALT\nSuite 213\nPalm Harbor, FL 34683",
        phone="(727) 275-9575",
        email="franklin@brflorida.com",
        client_name="Jane Doe",
    )

    sig = parts["signature_block"]
    assert "Franklin Riley" in sig
    assert "Bernhardt Riley Law Firm" in sig
    assert "(727) 275-9575" in sig
    assert "franklin@brflorida.com" in sig
    _assert_no_placeholders(sig)

    contact_line = parts["closing_contact_sentence"]
    assert "(727) 275-9575" in contact_line
    assert "franklin@brflorida.com" in contact_line
    _assert_no_placeholders(contact_line)


def test_missing_phone_omits_phone_line():
    parts = render_letter_signature_parts(
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley Law Firm",
        phone=None,
        email="franklin@brflorida.com",
        client_name="Jane Doe",
    )
    sig = parts["signature_block"]
    contact = parts["closing_contact_sentence"]

    # No literal "Phone:" label appears anywhere — otherwise LLM hallucinates a value
    assert "Phone:" not in sig
    assert "Phone:" not in contact
    # Email line still present
    assert "franklin@brflorida.com" in sig
    _assert_no_placeholders(sig)
    _assert_no_placeholders(contact)


def test_missing_phone_and_email_yields_no_contact_sentence_at_all():
    parts = render_letter_signature_parts(
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley Law Firm",
        phone=None,
        email=None,
        client_name="Jane Doe",
    )
    # With no contact method, the "reach out to our office" sentence
    # must be empty — otherwise the LLM hallucinates contact info.
    assert parts["closing_contact_sentence"] == ""
    sig = parts["signature_block"]
    assert "Franklin Riley" in sig
    assert "Phone:" not in sig
    assert "Email:" not in sig
    _assert_no_placeholders(sig)


def test_missing_firm_omits_firm_line():
    parts = render_letter_signature_parts(
        attorney_name="Solo Practitioner",
        firm_name=None,
        phone="555-0100",
        email="solo@example.com",
        client_name="Jane Doe",
    )
    sig = parts["signature_block"]
    assert "Solo Practitioner" in sig
    # Empty firm name means the firm line is absent (not blank)
    lines = [ln for ln in sig.split("\n") if ln.strip()]
    assert all("Firm" not in ln or ln.endswith("Firm Name:") is False for ln in lines)
    _assert_no_placeholders(sig)


def test_attorney_name_with_only_first_name_passes_through_verbatim():
    # The renderer does not invent a last name. The "force full name"
    # constraint lives at the profile-completeness layer, not here.
    parts = render_letter_signature_parts(
        attorney_name="Ceryn",
        firm_name="Bernhardt Riley Law Firm",
        phone="(727) 275-9575",
        email="ceryn@brflorida.com",
        client_name="Jane Doe",
    )
    sig = parts["signature_block"]
    assert "Ceryn" in sig
    # Must NOT contain a placeholder for the missing last name
    _assert_no_placeholders(sig)


def test_attorney_name_required():
    with pytest.raises(ValueError):
        render_letter_signature_parts(
            attorney_name=None,
            firm_name="Some Firm",
            phone="555-0100",
            email="x@example.com",
            client_name="Client",
        )


def test_no_senior_partner_default():
    # Even with everything else empty, the renderer never injects
    # "Senior Partner" as a fallback title.
    parts = render_letter_signature_parts(
        attorney_name="Franklin Riley",
        firm_name=None,
        phone=None,
        email=None,
        client_name="Jane Doe",
    )
    sig = parts["signature_block"]
    assert "Senior Partner" not in sig
    assert "Division Attorney" not in sig
    _assert_no_placeholders(sig)


def test_custom_email_signature_override_used_verbatim():
    # If the user has set profiles.email_signature, that string wins
    # over the computed signature block — they've taken control.
    custom = "Sincerely,\n\n/s/ Franklin Riley\nFranklin Riley, Esq.\nFL Bar #12345"
    parts = render_letter_signature_parts(
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley Law Firm",
        phone="(727) 275-9575",
        email="franklin@brflorida.com",
        client_name="Jane Doe",
        signature_override=custom,
    )
    assert parts["signature_block"] == custom


def test_client_name_appears_in_signature_block():
    # "Attorney for {client_name}" line must still appear
    parts = render_letter_signature_parts(
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley Law Firm",
        phone="(727) 275-9575",
        email="franklin@brflorida.com",
        client_name="Jane Doe",
    )
    assert "Jane Doe" in parts["signature_block"]
