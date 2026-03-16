"""Unit tests for signature-aware reconciliation in gap analysis."""

from legal_portal.core.data_models import (
    GapAnalysisResult,
    GapCategory,
    GapItem,
    GapSeverity,
)
from legal_portal.services.analysis.gap_analysis_service import GapAnalysisService


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


def test_reconcile_treats_party_identity_execution_gap_as_non_blocking_when_signed():
    """Standing/entity execution concerns become non-blocking when signed docs exist."""
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

    assert reconciled.total_gaps == 0
    assert reconciled.high_count == 0
    assert reconciled.gaps_by_category[GapCategory.MISSING_DOCUMENT.value] == []
    assert reconciled.gaps_by_category.get(GapCategory.INCOMPLETE_INFO.value, []) == []
    assert any(
        "treated 1 party/standing signature-coverage concern(s) as non-blocking"
        in note
        for note in reconciled.reconciliation_notes
    )


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


def test_reconcile_matches_party_signed_operating_agreement_wording():
    """'No ... party-signed ... provided' wording should reconcile when signed docs exist."""
    missing_gap = GapItem(
        gap_id="gap-party-signed-op-agreement",
        category=GapCategory.MISSING_DOCUMENT,
        severity=GapSeverity.HIGH,
        title="No Complete Party-signed, Dated Operating Agreement Provided",
        description=(
            "While several versions of the operating agreement are present, it is unclear if any "
            "provided version was executed by all relevant parties."
        ),
        affected_issue="Operating agreement enforcement",
        related_documents=[
            "Grow1 Operating Agreement.pdf",
            "Grow1 Operating Agreement (2).pdf",
            "Grow1 Operating Agreement (3).pdf",
        ],
        recommendations=[
            "Obtain a version of the operating agreement signed by all members.",
            "Review signature pages for completeness and date conformity.",
        ],
        impact_on_case=(
            "Lack of a definitive, executed operating agreement makes enforcement uncertain."
        ),
    )
    result = GapAnalysisResult(
        total_gaps=1,
        critical_count=0,
        high_count=1,
        medium_count=0,
        low_count=0,
        gaps_by_category={GapCategory.MISSING_DOCUMENT.value: [missing_gap]},
        overall_completeness_score=68.0,
        attorney_summary="Execution support is unclear.",
    )
    signature_evidence = [
        {
            "file_name": "Grow1 Operating Agreement.pdf",
            "status": "signed",
            "confidence": "low",
            "has_digital_signature": False,
            "instrument_hints": ["operating agreement"],
        },
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
    ]

    service = GapAnalysisService(openai_client=None)  # type: ignore[arg-type]
    reconciled = service._reconcile_signature_execution_gaps(result, signature_evidence)

    assert reconciled.total_gaps == 0
    assert reconciled.high_count == 0
    assert reconciled.gaps_by_category[GapCategory.MISSING_DOCUMENT.value] == []


def test_reconcile_suppresses_missing_complete_executed_operating_agreement_gap():
    """Signed operating agreements should suppress party-completeness missing-doc wording."""
    missing_gap = GapItem(
        gap_id="gap-op-agreement-party-complete",
        category=GapCategory.MISSING_DOCUMENT,
        severity=GapSeverity.CRITICAL,
        title="Missing Complete Executed Operating Agreement",
        description=(
            "Multiple operating agreement versions are present, but it is unclear whether any copy "
            "contains all necessary signatures from required LLC members/managers."
        ),
        affected_issue="Breach of Contract / Operating Agreement",
        related_documents=[
            "Grow1 Operating Agreement.pdf",
            "Grow1 Operating Agreement (2).pdf",
            "Grow1 Operating Agreement (3).pdf",
        ],
        recommendations=[
            "Obtain and review a complete, fully executed version of the Operating Agreement.",
            "Confirm signatory authority and party alignment.",
        ],
        impact_on_case=(
            "Clients' rights and standing may be challenged without confirmed party alignment."
        ),
    )
    result = GapAnalysisResult(
        total_gaps=1,
        critical_count=1,
        high_count=0,
        medium_count=0,
        low_count=0,
        gaps_by_category={GapCategory.MISSING_DOCUMENT.value: [missing_gap]},
        overall_completeness_score=58.0,
        attorney_summary="Execution support is unclear.",
    )
    signature_evidence = [
        {
            "file_name": "Grow1 Operating Agreement.pdf",
            "status": "signed",
            "confidence": "low",
            "has_digital_signature": False,
            "instrument_hints": ["operating agreement"],
        },
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
    ]

    service = GapAnalysisService(openai_client=None)  # type: ignore[arg-type]
    reconciled = service._reconcile_signature_execution_gaps(result, signature_evidence)

    assert reconciled.total_gaps == 0
    assert reconciled.critical_count == 0
    assert reconciled.gaps_by_category[GapCategory.MISSING_DOCUMENT.value] == []
    assert reconciled.gaps_by_category.get(GapCategory.INCOMPLETE_INFO.value, []) == []
    assert any(
        "treated 1 party/standing signature-coverage concern(s) as non-blocking"
        in note
        for note in reconciled.reconciliation_notes
    )


def test_reconcile_suppresses_low_confidence_execution_followup_gap_when_signed_docs_present():
    """Low-confidence execution wording should be non-blocking if signed agreements exist."""
    missing_gap = GapItem(
        gap_id="gap-low-confidence-exec",
        category=GapCategory.MISSING_DOCUMENT,
        severity=GapSeverity.HIGH,
        title="Low-confidence execution on key Operating Agreement(s)",
        description=(
            "Operating agreements are present but signature confidence is low and signature review "
            "is not completed."
        ),
        affected_issue="Breach of contract / Operating Agreement",
        related_documents=[
            "Grow1 Operating Agreement.pdf",
            "Grow1 Operating Agreement (2).pdf",
            "Grow1 Operating Agreement (3).pdf",
        ],
        recommendations=[
            "Obtain fully executed copies signed by all required parties.",
            "Complete signature review.",
        ],
        impact_on_case="Contract enforcement could be challenged.",
    )
    result = GapAnalysisResult(
        total_gaps=1,
        critical_count=0,
        high_count=1,
        medium_count=0,
        low_count=0,
        gaps_by_category={GapCategory.MISSING_DOCUMENT.value: [missing_gap]},
        overall_completeness_score=70.0,
        attorney_summary="Execution quality concern remains.",
    )
    signature_evidence = [
        {
            "file_name": "Grow1 Operating Agreement.pdf",
            "status": "signed",
            "confidence": "low",
            "has_digital_signature": False,
            "instrument_hints": ["operating agreement"],
        }
    ]

    service = GapAnalysisService(openai_client=None)  # type: ignore[arg-type]
    reconciled = service._reconcile_signature_execution_gaps(result, signature_evidence)

    assert reconciled.total_gaps == 0
    assert reconciled.high_count == 0
    assert reconciled.gaps_by_category[GapCategory.MISSING_DOCUMENT.value] == []
    assert any(
        "execution/signature coverage gap(s) treated as non-blocking" in note
        for note in reconciled.reconciliation_notes
    )


def test_reconcile_suppresses_signature_execution_date_timeline_gap_when_signed_docs_present():
    """Timeline gaps only about signature/execution dates should be non-blocking when signed docs exist."""
    timeline_gap = GapItem(
        gap_id="gap-signature-date-timeline",
        category=GapCategory.TIMELINE_GAP,
        severity=GapSeverity.MEDIUM,
        title="Missing signature/execution dates on Operating Agreement(s)",
        description=(
            "Operating agreements appear signed but signature or execution dates are unclear."
        ),
        affected_issue="Breach of contract / Operating Agreement",
        related_documents=[
            "Grow1 Operating Agreement.pdf",
            "Grow1 Operating Agreement (2).pdf",
            "Grow1 Operating Agreement (3).pdf",
        ],
        recommendations=[
            "Confirm date conformity across all operating agreement signatures."
        ],
        impact_on_case="Timeline certainty is reduced.",
    )
    result = GapAnalysisResult(
        total_gaps=1,
        critical_count=0,
        high_count=0,
        medium_count=1,
        low_count=0,
        gaps_by_category={GapCategory.TIMELINE_GAP.value: [timeline_gap]},
        overall_completeness_score=74.0,
        attorney_summary="Timeline remains incomplete.",
    )
    signature_evidence = [
        {
            "file_name": "Grow1 Operating Agreement (2).pdf",
            "status": "signed",
            "confidence": "low",
            "has_digital_signature": False,
            "instrument_hints": ["operating agreement"],
        }
    ]

    service = GapAnalysisService(openai_client=None)  # type: ignore[arg-type]
    reconciled = service._reconcile_signature_execution_gaps(result, signature_evidence)

    assert reconciled.total_gaps == 0
    assert reconciled.medium_count == 0
    assert reconciled.gaps_by_category[GapCategory.TIMELINE_GAP.value] == []
