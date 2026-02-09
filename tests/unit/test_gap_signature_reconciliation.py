"""Unit tests for signature-aware reconciliation in gap analysis."""

from legal_portal.core.data_models import (
    GapAnalysisResult,
    GapCategory,
    GapItem,
    GapSeverity,
)
from legal_portal.services.gap_analysis_service import GapAnalysisService


def test_reconcile_removes_false_missing_executed_gap_when_signed_doc_matches():
    """Signed metadata should suppress false missing-executed document gaps."""
    missing_gap = GapItem(
        gap_id="gap-exec",
        category=GapCategory.MISSING_DOCUMENT,
        severity=GapSeverity.CRITICAL,
        title="Missing executed subscription agreement",
        description="No signed subscription agreement was provided.",
        affected_issue="Breach of contract",
        related_documents=["Subscription Agreement.pdf"],
        recommendations=["Provide executed agreement copy."],
        impact_on_case="Contract formation cannot be shown.",
    )
    timeline_gap = GapItem(
        gap_id="gap-date",
        category=GapCategory.TIMELINE_GAP,
        severity=GapSeverity.HIGH,
        title="Missing funding date",
        description="Investment date is unclear.",
        affected_issue="Statute of limitations",
        related_documents=[],
        recommendations=["Provide transfer date evidence."],
        impact_on_case="Limitations analysis is uncertain.",
    )

    result = GapAnalysisResult(
        total_gaps=2,
        critical_count=1,
        high_count=1,
        medium_count=0,
        low_count=0,
        gaps_by_category={
            GapCategory.MISSING_DOCUMENT.value: [missing_gap],
            GapCategory.TIMELINE_GAP.value: [timeline_gap],
        },
        overall_completeness_score=60.0,
        attorney_summary="Case has critical missing items.",
    )
    signature_evidence = [
        {
            "file_name": "Subscription Agreement.pdf",
            "status": "signed",
            "confidence": "high",
            "has_digital_signature": True,
        }
    ]

    service = GapAnalysisService(openai_client=None)  # type: ignore[arg-type]
    reconciled = service._reconcile_signature_execution_gaps(result, signature_evidence)

    assert reconciled.total_gaps == 1
    assert reconciled.critical_count == 0
    assert reconciled.high_count == 1
    assert reconciled.gaps_by_category[GapCategory.MISSING_DOCUMENT.value] == []
    assert reconciled.overall_completeness_score > 60.0
    assert "Execution metadata confirms signed documents" in reconciled.attorney_summary
    assert any(
        "Execution metadata confirms signed documents" in note
        for note in reconciled.reconciliation_notes
    )


def test_reconcile_does_not_suppress_party_identity_execution_gap():
    """Execution gaps that are really standing/entity issues should remain open."""
    missing_gap = GapItem(
        gap_id="gap-exec-standing",
        category=GapCategory.MISSING_DOCUMENT,
        severity=GapSeverity.HIGH,
        title="Missing executed agreement for correct plaintiff entity",
        description=(
            "Executed agreement appears absent for the individual plaintiffs, and standing "
            "is unclear because investor identity may be entity-based."
        ),
        affected_issue="Standing",
        related_documents=[],
        recommendations=["Clarify investor identity and contracting party."],
        impact_on_case="Correct plaintiff cannot be confirmed.",
    )
    result = GapAnalysisResult(
        total_gaps=1,
        critical_count=0,
        high_count=1,
        medium_count=0,
        low_count=0,
        gaps_by_category={GapCategory.MISSING_DOCUMENT.value: [missing_gap]},
        overall_completeness_score=70.0,
        attorney_summary="Standing remains unclear.",
    )
    signature_evidence = [
        {
            "file_name": "Subscription Agreement.pdf",
            "status": "signed",
            "confidence": "high",
            "has_digital_signature": True,
        }
    ]

    service = GapAnalysisService(openai_client=None)  # type: ignore[arg-type]
    reconciled = service._reconcile_signature_execution_gaps(result, signature_evidence)

    assert reconciled.total_gaps == 1
    assert reconciled.high_count == 1
    assert len(reconciled.gaps_by_category[GapCategory.MISSING_DOCUMENT.value]) == 1
