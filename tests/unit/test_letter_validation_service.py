"""Unit tests for polish fact-integrity checks in LetterValidationService."""

from legal_portal.services.letters.letter_validation_service import LetterValidationService


def test_polish_fact_integrity_passes_when_facts_preserved() -> None:
    service = LetterValidationService()
    original = (
        "Client paid $47,656.00 on February 14, 2023. "
        "Cuchillo Greens Grow 1, LLC did not return funds."
    )
    polished = (
        "As discussed, you paid $47,656.00 on February 14, 2023, and "
        "Cuchillo Greens Grow 1, LLC did not return the funds."
    )

    report = service.check_polish_fact_integrity(
        original,
        polished,
        tracked_entities=["Cuchillo Greens Grow 1, LLC"],
    )

    assert report["passed"] is True
    assert report["reason"] == "ok"


def test_polish_fact_integrity_flags_amount_drift() -> None:
    service = LetterValidationService()
    original = "Client paid $47,656.00."
    polished = "Client paid $57,656.00."

    report = service.check_polish_fact_integrity(original, polished)

    assert report["passed"] is False
    assert "amount_drift" in report["reason"]
    assert report["introduced_amounts"] == ["57656.00"]
    assert report["removed_amounts"] == ["47656.00"]


def test_polish_fact_integrity_flags_date_drift() -> None:
    service = LetterValidationService()
    original = "Payment was made on February 14, 2023."
    polished = "Payment was made on February 28, 2023."

    report = service.check_polish_fact_integrity(original, polished)

    assert report["passed"] is False
    assert "date_drift" in report["reason"]
    assert "february 28 2023" in report["introduced_dates"]
    assert "february 14 2023" in report["removed_dates"]


def test_polish_fact_integrity_flags_tracked_entity_drift() -> None:
    service = LetterValidationService()
    original = "Cuchillo Greens Grow 1, LLC failed to perform."
    polished = "Grow Holdings, LLC failed to perform."

    report = service.check_polish_fact_integrity(
        original,
        polished,
        tracked_entities=["Cuchillo Greens Grow 1, LLC", "Grow Holdings, LLC"],
    )

    assert report["passed"] is False
    assert "entity_drift" in report["reason"]
    assert report["introduced_entities"] == ["Grow Holdings, LLC"]
    assert report["removed_entities"] == ["Cuchillo Greens Grow 1, LLC"]
