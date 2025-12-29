"""End-to-end integration tests for citation tracking with corpus validation."""

import pytest

from legal_portal.core.data_models import AnalyzedDocument, CaseAnalysisResult, IntakeAnalysis
from legal_portal.services.citation_tracking_service import CitationTrackingService
from legal_portal.services.corpus_coverage_service import CorpusCoverageService
from legal_portal.services.statute_validation_service import StatuteValidationService


@pytest.mark.asyncio
async def test_end_to_end_citation_with_corpus():
    """Test complete citation flow with corpus validation."""
    # Setup
    corpus_service = StatuteValidationService()
    coverage_service = CorpusCoverageService()
    tracker = CitationTrackingService(corpus_service=corpus_service)

    # Sample letter
    letter = """
    Good afternoon Client,

    Following our review of your documents, I am providing my initial findings.

    1. Factual Summary

    The construction contract dated March 15, 2024 specified $50,000 payment for the work.
    Under Florida Statute § 558.004, written notice is required before filing suit.
    The contractor failed to complete work as documented in the timeline.

    2. Key Legal Points

    Your case involves potential claims under Florida construction law.
    The contract clearly establishes the payment terms and completion schedule.

    3. Recommended Action

    I recommend that you preserve all documentation and contact our office to discuss next steps.

    Thank you, and I remain committed to protecting your interests throughout this process.
    """

    # Sample documents
    docs = [
        AnalyzedDocument(
            file_name="Contract_2024.pdf",
            summary="Construction agreement signed March 15 2024 for fifty thousand dollars",
            document_type="contract",
            key_information="Payment terms and completion schedule",
            relevance_to_case="Primary contractual agreement",
        ),
        AnalyzedDocument(
            file_name="Timeline.pdf",
            summary="Project timeline showing work stoppage and incomplete tasks",
            document_type="timeline",
            key_information="Work ceased without completion",
            relevance_to_case="Chronology of contractor abandonment",
        ),
    ]

    # Create mock case analysis
    mock_intake = IntakeAnalysis(
        client_name="Test Client",
        case_type="Construction Law",
        summary="Construction defect and abandonment case",
    )

    mock_analysis = CaseAnalysisResult(intake_analysis=mock_intake, analyzed_documents=docs)

    # Check corpus coverage
    coverage = coverage_service.analyze_coverage(
        case_type="Construction Law", case_facts="Construction defect dispute"
    )

    # Create citation map
    citation_map = tracker.create_citation_map(
        letter_id="test-123",
        client_name="Test Client",
        letter_content=letter,
        case_analysis=mock_analysis,
        case_type="Construction Law",
        is_corpus_covered=coverage.get("is_covered", False),
        average_doc_quality=8.0,
    )

    # Assertions
    assert len(citation_map.citations) >= 1, "Should create at least 1 citation"
    assert citation_map.metadata.get("citation_coverage", 0) > 0, "Coverage should be > 0%"
    assert citation_map.letter_id == "test-123"
    assert citation_map.client_name == "Test Client"
    assert citation_map.case_type == "Construction Law"
    assert len(citation_map.source_documents) >= 2


@pytest.mark.asyncio
async def test_integration_with_low_quality_docs():
    """Test citation tracking with low quality documents."""
    corpus_service = StatuteValidationService()
    tracker = CitationTrackingService(corpus_service=corpus_service)

    # Letter with facts
    letter = """
    The contract was signed in March 2024.
    Payment was supposed to be $50,000.
    Work was not completed by the contractor.
    """

    # Low quality documents (minimal information)
    docs = [
        AnalyzedDocument(
            file_name="unclear_doc.pdf",
            summary="Some contract info",
            document_type="document",
            key_information="unclear",
            relevance_to_case="unknown",
        )
    ]

    mock_analysis = CaseAnalysisResult(
        intake_analysis=IntakeAnalysis(client_name="Client", case_type="General", summary="Case"),
        analyzed_documents=docs,
    )

    # Use low document quality setting
    citation_map = tracker.create_citation_map(
        letter_id="test-low-quality",
        client_name="Client",
        letter_content=letter,
        case_analysis=mock_analysis,
        case_type="General",
        is_corpus_covered=False,
        average_doc_quality=3.0,  # Low quality
    )

    # Should use more lenient threshold
    assert citation_map.metadata.get("adaptive_threshold", 0.15) < 0.15
    assert citation_map.metadata["average_doc_quality"] == 3.0


@pytest.mark.asyncio
async def test_integration_with_high_quality_docs():
    """Test citation tracking with high quality documents."""
    corpus_service = StatuteValidationService()
    tracker = CitationTrackingService(corpus_service=corpus_service)

    # Letter with facts
    letter = """
    The construction contract dated March 15, 2024 specified payment of $50,000.
    The contractor was required to complete work by June 1, 2024.
    As of July 1, 2024, the work remains incomplete.
    """

    # High quality documents (detailed information)
    docs = [
        AnalyzedDocument(
            file_name="Detailed_Contract.pdf",
            summary="Comprehensive construction agreement dated March 15, 2024, specifying payment of $50,000 and completion by June 1, 2024",
            document_type="contract",
            key_information="Payment: $50,000; Completion date: June 1, 2024; Parties: Client and Contractor LLC",
            relevance_to_case="Primary agreement establishing all contractual obligations and payment terms",
        )
    ]

    mock_analysis = CaseAnalysisResult(
        intake_analysis=IntakeAnalysis(
            client_name="Client", case_type="Construction Law", summary="Construction contract dispute"
        ),
        analyzed_documents=docs,
    )

    # Use high document quality setting
    citation_map = tracker.create_citation_map(
        letter_id="test-high-quality",
        client_name="Client",
        letter_content=letter,
        case_analysis=mock_analysis,
        case_type="Construction Law",
        is_corpus_covered=True,
        average_doc_quality=9.0,  # High quality
    )

    # Should use stricter threshold and get better coverage
    assert citation_map.metadata.get("adaptive_threshold", 0.15) > 0.15
    assert citation_map.metadata["average_doc_quality"] == 9.0
    assert len(citation_map.citations) >= 1


@pytest.mark.asyncio
async def test_integration_corpus_coverage_impact():
    """Test that corpus coverage affects threshold."""
    corpus_service = StatuteValidationService()
    tracker = CitationTrackingService(corpus_service=corpus_service)

    letter = "The contract specified payment terms and completion dates."

    docs = [
        AnalyzedDocument(
            file_name="Contract.pdf",
            summary="Contract with payment and timeline terms",
            document_type="contract",
            key_information="Payment and completion information",
            relevance_to_case="Primary agreement",
        )
    ]

    mock_analysis = CaseAnalysisResult(
        intake_analysis=IntakeAnalysis(
            client_name="Client", case_type="Construction Law", summary="Construction case"
        ),
        analyzed_documents=docs,
    )

    # Test with corpus coverage
    citation_map_covered = tracker.create_citation_map(
        letter_id="covered",
        client_name="Client",
        letter_content=letter,
        case_analysis=mock_analysis,
        case_type="Construction Law",
        is_corpus_covered=True,
        average_doc_quality=7.0,
    )

    # Test without corpus coverage
    citation_map_not_covered = tracker.create_citation_map(
        letter_id="not-covered",
        client_name="Client",
        letter_content=letter,
        case_analysis=mock_analysis,
        case_type="General",
        is_corpus_covered=False,
        average_doc_quality=7.0,
    )

    # Covered cases should have stricter threshold
    threshold_covered = citation_map_covered.metadata.get("adaptive_threshold", 0.15)
    threshold_not_covered = citation_map_not_covered.metadata.get("adaptive_threshold", 0.15)

    assert threshold_covered > threshold_not_covered


@pytest.mark.asyncio
async def test_integration_citation_export():
    """Test citation map export functionality."""
    tracker = CitationTrackingService()

    letter = "The contract was signed on March 15, 2024 for $50,000."

    docs = [
        AnalyzedDocument(
            file_name="Contract.pdf",
            summary="Contract dated March 15, 2024 for $50,000",
            document_type="contract",
            key_information="Date: March 15, 2024; Amount: $50,000",
            relevance_to_case="Primary agreement",
        )
    ]

    mock_analysis = CaseAnalysisResult(
        intake_analysis=IntakeAnalysis(client_name="Client", case_type="General", summary="Case"),
        analyzed_documents=docs,
    )

    tracker.create_citation_map(
        letter_id="export-test",
        client_name="Client",
        letter_content=letter,
        case_analysis=mock_analysis,
    )

    # Test dict export
    export_dict = tracker.export_citation_map("dict")
    assert export_dict is not None
    assert export_dict["letter_id"] == "export-test"
    assert "citations" in export_dict

    # Test JSON export
    export_json = tracker.export_citation_map("json")
    assert export_json is not None
    assert "export-test" in export_json


@pytest.mark.asyncio
async def test_integration_citation_summary():
    """Test citation summary generation."""
    tracker = CitationTrackingService()

    letter = "The contract was signed for $50,000. Work was not completed."

    docs = [
        AnalyzedDocument(
            file_name="Contract.pdf",
            summary="Contract with payment terms",
            document_type="contract",
            key_information="$50,000 payment",
            relevance_to_case="Agreement",
        )
    ]

    mock_analysis = CaseAnalysisResult(
        intake_analysis=IntakeAnalysis(client_name="Test Client", case_type="General", summary="Case"),
        analyzed_documents=docs,
    )

    tracker.create_citation_map(
        letter_id="summary-test",
        client_name="Test Client",
        letter_content=letter,
        case_analysis=mock_analysis,
    )

    summary = tracker.get_citation_summary()

    assert summary["letter_id"] == "summary-test"
    assert summary["client_name"] == "Test Client"
    assert "total_citations" in summary
    assert "citation_coverage" in summary
    assert "confidence_breakdown" in summary
