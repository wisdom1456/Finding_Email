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


def test_normalize_deduplicates_canonical_section_headings() -> None:
    """Duplicate canonical headings (e.g., two '## KEY LEGAL ISSUES') must be collapsed to one."""
    service = JsonProcessingService(client=None, config={})  # type: ignore[arg-type]
    draft = (
        "Good afternoon Client,\n\n"
        "## BACKGROUND & ISSUE\n\n"
        "Background text.\n\n"
        "## KEY LEGAL ISSUES\n\n"
        "Issue text.\n\n"
        "## ANALYSIS\n\n"
        "Analysis text.\n\n"
        "## RECOMMENDED NEXT STEPS\n\n"
        "Next steps text.\n\n"
        "## Key Legal Issues\n\n"
        "Duplicate engagement-scope text that should not get this heading.\n"
    )

    normalized = service.normalize_client_letter_markdown(draft, letter_type="findings")

    count = normalized.count("## KEY LEGAL ISSUES")
    assert count == 1, f"Expected 1 KEY LEGAL ISSUES heading, found {count}"


def test_normalize_deduplicates_key_provisions_and_key_legal_issues() -> None:
    """KEY PROVISIONS and KEY LEGAL ISSUES are the same section — only the first survives."""
    service = JsonProcessingService(client=None, config={})  # type: ignore[arg-type]
    draft = (
        "## BACKGROUND & ISSUE\n\nText.\n\n"
        "## Key Legal Issues\n\nIssue text.\n\n"
        "## ANALYSIS\n\nAnalysis text.\n\n"
        "## RECOMMENDED NEXT STEPS\n\nSteps text.\n\n"
        "## Key Provisions\n\nDuplicate.\n"
    )

    normalized = service.normalize_client_letter_markdown(draft, letter_type="findings")

    kli_count = normalized.count("## KEY LEGAL ISSUES")
    kp_count = normalized.count("## KEY PROVISIONS")
    assert kli_count == 1, f"Expected 1 KEY LEGAL ISSUES, found {kli_count}"
    assert kp_count == 0, f"Expected 0 KEY PROVISIONS, found {kp_count}"


def test_normalize_client_letter_markdown_cleans_snake_case_headers_and_placeholders() -> None:
    service = JsonProcessingService(client=None, config={})  # type: ignore[arg-type]
    draft = (
        "Good afternoon Erica and Ron,\n\n"
        "Opening_review\n"
        "Summary text.\n\n"
        "action_items\n"
        "Do X.\n\n"
        "core_issue\n"
        "Main issue text.\n\n"
        "legal_theories\n"
        "Theory text.\n\n"
        "timing_risk\n"
        "Risk text.\n\n"
        "Thank you,\n"
        "[Attorney Name]\n"
        "[New Mexico Law Firm Name]\n"
    )

    normalized = service.normalize_client_letter_markdown(
        draft,
        letter_type="findings",
        attorney_name="Franklin Riley",
        firm_name="Bernhardt Riley, Attorneys at Law",
    )

    assert "Opening_review" not in normalized
    assert "action_items" not in normalized
    assert "core_issue" not in normalized
    assert "legal_theories" not in normalized
    assert "timing_risk" not in normalized
    assert "[Attorney Name]" not in normalized
    assert "[New Mexico Law Firm Name]" not in normalized
    assert "Franklin Riley" in normalized
    assert "Bernhardt Riley, Attorneys at Law" in normalized
