"""Unit tests for constrained repair guardrails."""

from __future__ import annotations

import asyncio

from legal_portal.services.json_processing_service import JsonProcessingService


def test_repair_skips_when_no_violations() -> None:
    service = JsonProcessingService(client=None, config={})  # type: ignore[arg-type]
    draft = "Opening - What We Reviewed\n\nSample content."

    repaired = asyncio.run(service.repair_letter_constraints(draft, []))

    assert repaired == draft


def test_repair_skips_for_empty_draft() -> None:
    service = JsonProcessingService(client=None, config={})  # type: ignore[arg-type]

    repaired = asyncio.run(
        service.repair_letter_constraints(
            "",
            [{"rule": "word_count_bounds", "severity": "warning", "message": "Too short"}],
        )
    )

    assert repaired == ""


def test_normalize_client_letter_markdown_cleans_headers_and_file_tokens() -> None:
    service = JsonProcessingService(client=None, config={})  # type: ignore[arg-type]
    draft = (
        "Good afternoon Erica and Ron,\n\n"
        "Opening review\n"
        "I reviewed SubscriptionAgreementEJAJ-TXFinal120.pdf and MEMOTERMSFORFINANCINGCuchilloGrow1LLC.pdf.\n\n"
        "Facts\n"
        "The breachofcontract theory remains viable.\n"
    )

    normalized = service.normalize_client_letter_markdown(draft, letter_type="findings")

    assert "Opening review" not in normalized
    assert "Facts\n" not in normalized
    assert "breachofcontract" not in normalized
    assert "Subscription Agreement EJAJ TX Final 120" in normalized
    assert "Memo Terms For Financing Cuchillo Grow 1 LLC" in normalized
