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


def test_reconcile_matches_signed_doc_with_uuid_filename_using_instrument_hints():
    """Signed docs with opaque filenames should still reconcile by instrument hints."""
    missing_gap = GapItem(
        gap_id="gap-exec-generic",
        category=GapCategory.MISSING_DOCUMENT,
        severity=GapSeverity.HIGH,
        title="Missing executed investment/contract documents",
        description="No executed contract documents were identified in the record.",
        affected_issue="Breach of contract",
        related_documents=[],
        recommendations=["Provide signed investment agreement documents."],
        impact_on_case="Contract enforceability remains uncertain.",
    )
    result = GapAnalysisResult(
        total_gaps=1,
        critical_count=0,
        high_count=1,
        medium_count=0,
        low_count=0,
        gaps_by_category={GapCategory.MISSING_DOCUMENT.value: [missing_gap]},
        overall_completeness_score=66.0,
        attorney_summary="Executed agreement support is unclear.",
    )
    signature_evidence = [
        {
            "file_name": "020a16cd-33bf-4fb6-b580-da7423ba8de5.pdf",
            "status": "signed",
            "confidence": "high",
            "has_digital_signature": True,
            "instrument_hints": ["subscription agreement", "membership units"],
        }
    ]

    service = GapAnalysisService(openai_client=None)  # type: ignore[arg-type]
    reconciled = service._reconcile_signature_execution_gaps(result, signature_evidence)

    assert reconciled.total_gaps == 0
    assert reconciled.high_count == 0
    assert reconciled.gaps_by_category[GapCategory.MISSING_DOCUMENT.value] == []


def test_reconcile_matches_contracts_wording_to_signed_subscription_agreement():
    """Plural contract wording should still match signed subscription agreements."""
    missing_gap = GapItem(
        gap_id="gap-contracts",
        category=GapCategory.MISSING_DOCUMENT,
        severity=GapSeverity.CRITICAL,
        title="Missing executed contract(s) between investors and Cuchillo Greens Grow 1 LLC",
        description="No executed contract documents were produced to confirm investment terms.",
        affected_issue="Breach of contract",
        related_documents=[],
        recommendations=["Provide executed contract(s) for the investment."],
        impact_on_case="Contract enforceability remains unclear.",
    )
    result = GapAnalysisResult(
        total_gaps=1,
        critical_count=1,
        high_count=0,
        medium_count=0,
        low_count=0,
        gaps_by_category={GapCategory.MISSING_DOCUMENT.value: [missing_gap]},
        overall_completeness_score=66.0,
        attorney_summary="Executed agreements appear missing.",
    )
    signature_evidence = [
        {
            "file_name": "Subscription_Agreement_EJAJ-TX_Final120.doc.pdf",
            "status": "signed",
            "confidence": "high",
            "has_digital_signature": True,
            "instrument_hints": ["subscription agreement", "membership units"],
        }
    ]

    service = GapAnalysisService(openai_client=None)  # type: ignore[arg-type]
    reconciled = service._reconcile_signature_execution_gaps(result, signature_evidence)

    assert reconciled.total_gaps == 0
    assert reconciled.critical_count == 0
    assert reconciled.gaps_by_category[GapCategory.MISSING_DOCUMENT.value] == []


def test_reconcile_matches_absence_wording_for_counterparty_executed_gap():
    """Absence/no-clear-evidence phrasing should still reconcile against signed docs."""
    missing_gap = GapItem(
        gap_id="gap-counterparty-exec",
        category=GapCategory.MISSING_DOCUMENT,
        severity=GapSeverity.CRITICAL,
        title="Absence of Counterparty-Executed Key Agreements",
        description=(
            "There is no clear evidence of fully executed, mutually signed versions of the "
            "operating agreement and subscription agreements."
        ),
        affected_issue="Breach of contract",
        related_documents=[
            "Grow1 Operating Agreement (2).pdf",
            "Grow1 Operating Agreement (3).pdf",
            "Grow1 Operating Agreement.pdf",
            "Subscription_Agreement_EJAJ-TX_Final120.doc.pdf",
        ],
        recommendations=[
            "Obtain fully executed copies of all key agreements.",
            "Review all signature pages for counterparty signatures.",
        ],
        impact_on_case="Contract enforceability remains uncertain.",
    )
    result = GapAnalysisResult(
        total_gaps=1,
        critical_count=1,
        high_count=0,
        medium_count=0,
        low_count=0,
        gaps_by_category={GapCategory.MISSING_DOCUMENT.value: [missing_gap]},
        overall_completeness_score=62.0,
        attorney_summary="Execution support is unclear.",
    )
    signature_evidence = [
        {
            "file_name": "Grow1 Operating Agreement (2).pdf",
            "status": "signed",
            "confidence": "low",
            "has_digital_signature": False,
            "instrument_hints": ["operating agreement"],
        },
        {
            "file_name": "Grow1 Operating Agreement (3).pdf",
            "status": "signed",
            "confidence": "low",
            "has_digital_signature": False,
            "instrument_hints": ["operating agreement"],
        },
        {
            "file_name": "Grow1 Operating Agreement.pdf",
            "status": "signed",
            "confidence": "low",
            "has_digital_signature": False,
            "instrument_hints": ["operating agreement"],
        },
        {
            "file_name": "Subscription_Agreement_EJAJ-TX_Final120.doc.pdf",
            "status": "signed",
            "confidence": "high",
            "has_digital_signature": True,
            "instrument_hints": ["subscription agreement", "membership units"],
        },
    ]

    service = GapAnalysisService(openai_client=None)  # type: ignore[arg-type]
    reconciled = service._reconcile_signature_execution_gaps(result, signature_evidence)

    assert reconciled.total_gaps == 0
    assert reconciled.critical_count == 0
    assert reconciled.gaps_by_category[GapCategory.MISSING_DOCUMENT.value] == []
