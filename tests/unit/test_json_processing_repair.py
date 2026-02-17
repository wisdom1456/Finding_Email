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
