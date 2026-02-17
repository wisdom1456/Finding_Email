"""Unit tests for deterministic letter quality linting."""

from __future__ import annotations

from legal_portal.services.letter_quality_lint_service import LetterQualityLintService


def _strict_mode_sample() -> str:
    """Build a strict-quality findings sample with required sections."""
    filler = " ".join(["analysis"] * 660)
    return (
        "Opening - What We Reviewed\n"
        "We reviewed the signed financing memo, operating agreements, subscription packet, "
        "and related emails.\n\n"
        "Core Issue - The Real Question\n"
        "The core issue is whether there is a legally supportable path to recover funds.\n\n"
        "What the Documents Show\n"
        "Based on the records, 2022 entries include a full bloom down payment and transfer data.\n\n"
        "Legal Theories\n"
        "Contract is the primary claim. Fraud or misrepresentation can be secondary leverage. "
        "Securities concerns may support negotiation.\n\n"
        "Timing Risk\n"
        "The statute of limitations and related deadline tracking remain critical.\n\n"
        "Strategy - What We Recommend\n"
        "We recommend a demand letter as the first move, with careful party targeting.\n\n"
        "Immediate Client Action Items\n"
        "- Provide proof of payment records.\n"
        "- Provide complete offering materials.\n"
        "- Provide written repayment statements.\n"
        "- Confirm deadline references and authority roles.\n\n"
        f"{filler}"
    )


def test_strict_quality_passes_for_sectioned_strategy_memo() -> None:
    """Strict mode should pass when section and actionability checks are satisfied."""
    service = LetterQualityLintService()

    report = service.lint_letter(
        _strict_mode_sample(),
        mode="strict_quality",
        letter_type="findings",
    )

    assert report["lint_passed"] is True
    assert report["score"] >= 85
    assert report["word_count"] >= 650
    assert report["section_counts"]["action_item_bullets"] == 4


def test_strict_quality_flags_hardcoded_today_math() -> None:
    """Strict mode should reject hard-coded day-count urgency math."""
    service = LetterQualityLintService()
    content = _strict_mode_sample() + "\nMarch 5, 2026 is 16 days from today."

    report = service.lint_letter(content, mode="strict_quality", letter_type="findings")
    violations = report["violations"]

    assert any(item["rule"] == "hardcoded_today_math" for item in violations)
    assert report["lint_passed"] is False


def test_default_mode_reports_internal_language_without_failing_all_content() -> None:
    """Default mode should report internal language while returning schema-complete output."""
    service = LetterQualityLintService()
    content = "Gap analysis flagged missing proof. Contract claim remains strong."

    report = service.lint_letter(content, mode="default", letter_type="findings")

    assert "lint_passed" in report
    assert "score" in report
    assert "violations" in report
    assert any(item["rule"] == "gap_analysis_flagged" for item in report["violations"])
