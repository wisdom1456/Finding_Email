"""Render attorney signature and closing-contact text for letter prompts.

Why this exists: the demand-letter prompt template previously had bare
template slots like ``Phone: {contact_phone}``. When the attorney's profile
lacked a phone, the slot rendered to ``Phone: `` — a labeled-but-empty line
that prompted gpt-4o to hallucinate ``(555) 555-5555`` to "complete" the
letter. Same pattern for ``Email:``, ``[Last Name]``, and ``Senior Partner``.

This module produces fully-rendered strings with missing fields *omitted
entirely* (not blanked), so the model has nothing to fill.
"""

from __future__ import annotations

from typing import Dict, Optional


def render_letter_signature_parts(
    *,
    attorney_name: Optional[str],
    firm_name: Optional[str] = None,
    firm_address: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    bar_number: Optional[str] = None,
    client_name: Optional[str] = None,
    signature_override: Optional[str] = None,
) -> Dict[str, str]:
    """Build the two text artifacts injected into letter prompts.

    Returns a dict with:
      - ``signature_block``: the multi-line closing signature
      - ``closing_contact_sentence``: the "please reach out" sentence
        (empty string if no contact method is available)
    """
    if not attorney_name or not str(attorney_name).strip():
        raise ValueError("attorney_name is required")

    if signature_override and signature_override.strip():
        return {
            "signature_block": signature_override.strip(),
            "closing_contact_sentence": _build_closing_contact(phone, email),
        }

    attorney_name = attorney_name.strip()
    lines: list[str] = ["Sincerely,", "", f"/s/ {attorney_name}", f"{attorney_name}, Esq."]
    if bar_number and bar_number.strip():
        lines.append(f"Bar No. {bar_number.strip()}")
    if firm_name and firm_name.strip():
        lines.append(firm_name.strip())
    if firm_address and firm_address.strip():
        for addr_line in firm_address.strip().splitlines():
            if addr_line.strip():
                lines.append(addr_line.strip())
    if phone and phone.strip():
        lines.append(phone.strip())
    if email and email.strip():
        lines.append(email.strip())
    if client_name and client_name.strip():
        lines.append(f"Attorney for {client_name.strip()}")

    return {
        "signature_block": "\n".join(lines),
        "closing_contact_sentence": _build_closing_contact(phone, email),
    }


def _build_closing_contact(phone: Optional[str], email: Optional[str]) -> str:
    """Build the 'please do not hesitate to reach out' sentence.

    Omits any contact method that is missing. Returns ``""`` if both are
    missing — the calling template should handle the empty case gracefully
    (no labeled-but-empty line).
    """
    phone_clean = (phone or "").strip()
    email_clean = (email or "").strip()
    if not phone_clean and not email_clean:
        return ""
    if phone_clean and email_clean:
        return (
            "Please do not hesitate to reach out to our office at "
            f"{phone_clean} or via e-mail at {email_clean}."
        )
    if phone_clean:
        return f"Please do not hesitate to reach out to our office at {phone_clean}."
    return f"Please do not hesitate to reach out to our office via e-mail at {email_clean}."
