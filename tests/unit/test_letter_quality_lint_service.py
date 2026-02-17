"""Unit tests for deterministic letter quality linting."""

from __future__ import annotations

from legal_portal.services.letter_quality_lint_service import LetterQualityLintService


def _strict_mode_sample() -> str:
    """Build a strict-quality findings sample with required sections."""
    facts = (
        "Based on the records, the 2022 payment history includes a $47,656.00 Full Bloom Down Payment entry "
        "and a $3,300.00 transfer tied to project expenses. The February 14, 2023 email update acknowledges "
        "changed circumstances and limited communication. The file also reflects similarly named Cuchillo entities, "
        "which is why we must map each promise to the right legal entity and authorized representative. "
        "This factual sequence matters because recovery depends on proving what was promised, what was paid, and "
        "what performance did not occur. The subscription agreement materials and operating agreement versions in the "
        "file provide document anchors for that mapping, and the ledger entries tie the chronology to concrete amounts."
    )
    contract = (
        "Breach of contract (which means enforcing the written deal when one side does not perform) is the primary "
        "path because signed financing and subscription materials identify the obligations. The payment entries and "
        "email record give us date and amount anchors to tie non-performance to the agreed terms. The practical "
        "impact is that we can demand repayment or documented cure based on specific deal language instead of broad claims."
    )
    fraud = (
        "Misrepresentation (meaning a materially false statement used to induce action) is secondary leverage if we "
        "can tie exact statements to investment decisions. The February 14, 2023 communication and any written repayment "
        "assurances should be anchored by date and sender. The practical impact is negotiation leverage, but only where "
        "the proof is specific and document-backed."
    )
    securities = (
        "Securities law theories (rules requiring fair and accurate investor disclosures) can support a negotiated "
        "resolution if offering materials omitted key facts. We should tie this theory to the investor packet version, "
        "timing of delivery, and payment timeline. The practical impact is additional pressure for repayment without "
        "overstating exposure."
    )
    liability = (
        "Individual liability and veil piercing (an exception that can allow personal liability when the LLC form is "
        "misused) remain conditional. We should preserve this angle but prioritize claims against the entity that signed "
        "the controlling documents, including the operating agreement and the February 14, 2023 update email chain. "
        "The practical impact is better collectability planning while avoiding premature allegations."
    )
    strategy = (
        "We recommend a targeted demand letter first because it is efficient and preserves litigation options. The "
        "letter should identify the investment amounts, controlling documents, repayment failure, and a written response "
        "deadline, while demanding a full accounting of funds received and used. This approach gives the other side a "
        "clear path to resolve the matter and builds a cleaner record if litigation becomes necessary."
    )
    return (
        "Good afternoon Erica and Ron,\n\n"
        "We reviewed the signed financing memo, operating agreements, subscription packet, "
        "and related emails.\n\n"
        "As discussed, the primary concern is whether there is a legally supportable path to recover funds.\n\n"
        "Based on the records:\n"
        f"{facts}\n\n"
        "Here are the key points of our analysis:\n\n"
        f"{contract}\n\n"
        f"{fraud}\n\n"
        f"{securities}\n\n"
        f"{liability}\n\n"
        "The statute of limitations (the filing deadline after which a claim can be barred) and related deadline "
        "tracking remain critical.\n\n"
        "Based on the above, we recommend:\n"
        f"{strategy}\n\n"
        "If you would like us to proceed now, please provide:\n"
        "- Provide proof of payment records.\n"
        "- Provide complete offering materials.\n"
        "- Provide written repayment statements.\n"
        "- Confirm deadline references and authority roles.\n\n"
        + " ".join(["record"] * 260)
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
    assert "quality_report_v2" in report
    assert "evidence_linkage_score" in report


def test_demand_strict_mode_flags_missing_specificity() -> None:
    """Demand strict mode should flag missing specificity package fields."""
    service = LetterQualityLintService()
    content = "Dear Party,\n\nPay now.\n\nRegards."

    report = service.lint_letter(content, mode="strict_quality", letter_type="demand")
    violations = report["violations"]

    assert any(item["rule"] == "demand_specificity" for item in violations)
    assert report["quality_report_v2"]["demand_specificity_passed"] is False


def test_strict_quality_flags_explicit_section_headers() -> None:
    """Strict findings mode should reject internal section-label styling."""
    service = LetterQualityLintService()
    content = (
        "Opening review\n\n"
        "Facts (document-backed chronology)\n\n"
        "Legal theories\n\n"
        "Strategy (prioritized)\n\n"
        + " ".join(["word"] * 700)
    )

    report = service.lint_letter(content, mode="strict_quality", letter_type="findings")

    assert any(item["rule"] == "explicit_section_headers" for item in report["violations"])


def test_strict_quality_flags_internal_meta_labels_and_snake_case_tokens() -> None:
    """Strict findings mode should reject leaked internal labels and tokens."""
    service = LetterQualityLintService()
    content = (
        "Good afternoon,\n\n"
        "Here are the key points of our analysis: micro-explainer for unjust_enrichment applies.\n\n"
        + " ".join(["word"] * 700)
    )

    report = service.lint_letter(content, mode="strict_quality", letter_type="findings")
    rules = {item["rule"] for item in report["violations"]}

    assert "micro_explainer_label" in rules
    assert "snake_case_legal_token" in rules


def test_strict_quality_flags_parenthetical_citation_overload() -> None:
    """Strict findings mode should flag over-stacked citation parentheticals."""
    service = LetterQualityLintService()
    overloaded_paragraph = (
        "Based on the records, repayment is still unresolved "
        "(subscription pkt, 2022) (financing memo, signed) (Feb 14, 2023 update) "
        "(investor ledger $47,656.00) and you should proceed now."
    )
    content = (
        "Good afternoon,\n\n"
        + overloaded_paragraph
        + "\n\n"
        + " ".join(["word"] * 700)
    )

    report = service.lint_letter(content, mode="strict_quality", letter_type="findings")

    assert any(item["rule"] == "citation_parenthetical_overload" for item in report["violations"])


def test_strict_quality_flags_raw_filename_exposure() -> None:
    """Strict findings mode should flag machine-like file tokens in client prose."""
    service = LetterQualityLintService()
    content = (
        "Good afternoon,\n\n"
        "We reviewed SubscriptionAgreementEJAJ-TXFinal120.pdf and MEMOTERMSFORFINANCINGCuchilloGrow1LLC.pdf.\n\n"
        + " ".join(["word"] * 700)
    )

    report = service.lint_letter(content, mode="strict_quality", letter_type="findings")

    assert any(item["rule"] == "raw_filename_exposure" for item in report["violations"])
