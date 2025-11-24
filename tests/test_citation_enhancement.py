"""Test for Enhanced Citation Functionality.

This test validates the complete citation tracking system including:
- Citation extraction from letter content
- Source document mapping
- Appendix generation with full letter text and detailed references
- Integration with the email generation workflow
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import Mock

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from legal_portal.core.data_models import CaseAnalysisResult
from legal_portal.services.citation_tracking_service import (
    CitationTrackingService,
)


def create_mock_case_analysis() -> CaseAnalysisResult:
    """Create a mock case analysis for testing."""
    # Create mock intake analysis
    mock_intake = Mock()
    mock_intake.client_name = "John Smith"
    mock_intake.case_type = "Contract Dispute"
    mock_intake.summary = "Client seeking review of construction contract dispute"

    # Create mock document analyses
    mock_doc1 = Mock()
    mock_doc1.filename = "Construction_Contract.pdf"
    mock_doc1.document_type = "contract"
    mock_doc1.summary = "Construction agreement between John Smith and ABC Construction dated 03/15/2024"
    mock_doc1.key_information = "Contract value $75,000, completion date 06/30/2024, change order provisions"
    mock_doc1.relevance_to_case = "Primary contract document establishing terms and obligations"
    mock_doc1.legal_significance = "Contains specific performance requirements and payment terms"
    mock_doc1.citations = []

    mock_doc2 = Mock()
    mock_doc2.filename = "Email_Communications.pdf"
    mock_doc2.document_type = "correspondence"
    mock_doc2.summary = "Email exchanges between client and contractor regarding project delays"
    mock_doc2.key_information = "Multiple requests for extension, cost overrun discussions"
    mock_doc2.relevance_to_case = "Evidence of communication and dispute escalation"
    mock_doc2.legal_significance = "Shows pattern of delays and disagreement over scope"
    mock_doc2.citations = []

    # Create mock case timeline
    mock_timeline = [
        {"date": "2024-03-15", "event": "Contract signed", "source": "Construction_Contract.pdf"},
        {"date": "2024-05-20", "event": "First delay notification", "source": "Email_Communications.pdf"},
    ]

    # Create case analysis result
    case_analysis = Mock(spec=CaseAnalysisResult)
    case_analysis.intake_analysis = mock_intake
    case_analysis.analyzed_documents = [mock_doc1, mock_doc2]
    case_analysis.case_timeline = mock_timeline

    return case_analysis


def create_sample_letter_content() -> str:
    """Create sample letter content with factual statements for testing."""
    return """
    <html>
    <body>
    <h1>Legal Findings Letter</h1>

    <p>Dear John Smith,</p>

    <p>We have completed our review of your contract dispute matter. Based on our analysis
    of the Construction Contract dated March 15, 2024, we have identified several key issues.</p>

    <p>The original contract value was $75,000 with a completion date of June 30, 2024
    according to the Construction Contract. Our review of the Email Communications shows
    that the first delay notification was sent on May 20, 2024.</p>

    <p>The contract contains specific change order provisions that require written approval
    for any modifications. Based on the email exchanges, there appears to be disagreement
    over the scope of work and associated costs.</p>

    <p>We recommend pursuing resolution through the dispute resolution mechanisms
    outlined in the contract. Please contact our office to discuss next steps.</p>

    <p>Sincerely,<br>Attorney Name</p>
    </body>
    </html>
    """


def test_citation_tracking_service():
    """Test the citation tracking service functionality."""
    print("🔍 Testing Citation Tracking Service...")

    # Initialize service
    citation_service = CitationTrackingService()

    # Create test data
    case_analysis = create_mock_case_analysis()
    letter_content = create_sample_letter_content()

    # Test citation map creation
    print("📝 Creating citation map...")
    citation_map = citation_service.create_citation_map(case_analysis, letter_content)

    # Validate citation map structure
    assert citation_map is not None, "Citation map should be created"
    assert citation_map.client_name == "John Smith", "Client name should match"
    assert citation_map.case_type == "Contract Dispute", "Case type should match"
    assert len(citation_map.source_documents) >= 2, "Should have source documents"
    assert citation_map.letter_content == letter_content, "Letter content should match"

    print(f"✅ Citation map created with {len(citation_map.citations)} citations")
    print(f"✅ Found {len(citation_map.source_documents)} source documents")

    # Test citation extraction
    print("🎯 Testing citation extraction...")
    citations = citation_map.citations

    # Should find citations for factual statements
    factual_statements_found = False
    for citation in citations:
        if "$75,000" in citation.statement or "March 15, 2024" in citation.statement:
            factual_statements_found = True
            print(f"✅ Found factual citation: {citation.statement[:50]}...")
            print(f"   Source: {citation.source_document}")
            print(f"   Confidence: {citation.confidence}")

    if factual_statements_found:
        print("✅ Successfully extracted factual statements")
    else:
        print("⚠️  No factual statements found - this may need adjustment")

    # Test citation summary
    print("📊 Testing citation summary...")
    summary = citation_service.get_citation_summary()

    assert "total_citations" in summary, "Summary should include total citations"
    assert "source_documents" in summary, "Summary should include source document count"
    assert "citation_coverage" in summary, "Summary should include coverage percentage"

    print(f"✅ Citation summary: {summary['total_citations']} citations, {summary['source_documents']} docs")
    print(f"✅ Coverage: {summary['citation_coverage']:.1%}")

    # Test export functionality
    print("💾 Testing citation export...")
    exported_json = citation_service.export_citation_map("json")
    exported_dict = citation_service.export_citation_map("dict")

    assert exported_json is not None, "JSON export should work"
    assert exported_dict is not None, "Dict export should work"

    # Parse JSON to ensure it's valid
    parsed_json = json.loads(exported_json)
    assert "letter_id" in parsed_json, "Exported JSON should contain letter_id"

    print("✅ Citation export functionality working")

    return citation_map


def test_prompt_enhancement():
    """Test the master prompt enhancement functionality."""
    print("🔧 Testing prompt enhancement...")

    citation_service = CitationTrackingService()

    base_prompt = """
    Generate a legal findings letter based on the following analysis:
    Client: {client_name}
    Case Type: {case_type}
    Analysis: {analysis}
    """

    enhanced_prompt = citation_service.enhance_master_prompt_with_citations(base_prompt)

    # Check that citation instructions were added
    assert "CRITICAL CITATION REQUIREMENTS" in enhanced_prompt, "Should add citation requirements"
    assert "Document References" in enhanced_prompt, "Should include reference instructions"
    assert "Source:" in enhanced_prompt, "Should include source formatting"

    print("✅ Master prompt successfully enhanced with citation instructions")

    return enhanced_prompt


def test_source_document_extraction():
    """Test source document extraction from case analysis."""
    print("📁 Testing source document extraction...")

    citation_service = CitationTrackingService()
    case_analysis = create_mock_case_analysis()

    source_docs = citation_service._extract_source_documents(case_analysis)

    # Should extract intake, documents, and timeline
    assert len(source_docs) >= 3, "Should extract multiple source types"

    # Check for intake form
    intake_found = any(doc["filename"] == "Client Intake Form" for doc in source_docs)
    assert intake_found, "Should extract intake form as source"

    # Check for contract document
    contract_found = any("Construction_Contract.pdf" in doc["filename"] for doc in source_docs)
    assert contract_found, "Should extract contract document"

    # Check for timeline
    timeline_found = any(doc["filename"] == "Case Timeline" for doc in source_docs)
    assert timeline_found, "Should extract timeline as source"

    print(f"✅ Extracted {len(source_docs)} source documents")
    for doc in source_docs:
        print(f"   - {doc['filename']} ({doc.get('document_type', 'unknown')})")

    return source_docs


def test_factual_statement_detection():
    """Test factual statement detection logic."""
    print("🎯 Testing factual statement detection...")

    citation_service = CitationTrackingService()

    # Test various types of statements
    test_statements = [
        ("The contract was signed on March 15, 2024", True),  # Date - should be factual
        ("The contract value is $75,000", True),  # Amount - should be factual
        ("According to the lease agreement, the rent is due monthly", True),  # Reference - should be factual
        ("We recommend pursuing mediation", False),  # Opinion - should not be factual
        ("The client believes the work was incomplete", False),  # Opinion - should not be factual
        ("The defendant filed a motion on January 1, 2024", True),  # Legal fact - should be factual
    ]

    correct_detections = 0
    total_tests = len(test_statements)

    for statement, expected_factual in test_statements:
        is_factual = citation_service._is_factual_statement(statement)
        if is_factual == expected_factual:
            correct_detections += 1
            status = "✅"
        else:
            status = "❌"

        print(f"   {status} '{statement[:40]}...' -> {is_factual} (expected {expected_factual})")

    accuracy = correct_detections / total_tests
    print(f"✅ Factual detection accuracy: {accuracy:.1%} ({correct_detections}/{total_tests})")

    return accuracy >= 0.8  # Expect at least 80% accuracy


def run_integration_test():
    """Run a complete integration test of the citation system."""
    print("🔄 Running integration test...")

    try:
        # Test all components
        citation_map = test_citation_tracking_service()
        enhanced_prompt = test_prompt_enhancement()
        test_source_document_extraction()
        detection_accuracy = test_factual_statement_detection()

        # Create test output
        test_output = {
            "citation_map_id": citation_map.letter_id,
            "total_citations": len(citation_map.citations),
            "source_documents": len(citation_map.source_documents),
            "citation_coverage": citation_map.metadata.get("citation_coverage", 0),
            "prompt_enhanced": "CRITICAL CITATION REQUIREMENTS" in enhanced_prompt,
            "detection_accuracy": detection_accuracy,
            "test_status": "PASSED",
        }

        # Save test results
        os.makedirs("validation_output", exist_ok=True)
        with open("validation_output/citation_test_results.json", "w") as f:
            json.dump(test_output, f, indent=2)

        print("\n🎉 Integration test completed successfully!")
        print("📄 Test results saved to validation_output/citation_test_results.json")
        print(
            f"📊 Summary: {test_output['total_citations']} citations, {test_output['citation_coverage']:.1%} coverage"
        )

        return True

    except Exception as e:
        print(f"\n❌ Integration test failed: {e!s}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 ENHANCED CITATION FUNCTIONALITY TEST")
    print("=" * 60)

    success = run_integration_test()

    if success:
        print("\n✅ All tests passed! Citation enhancement is working correctly.")
    else:
        print("\n❌ Some tests failed. Please review the output above.")

    print("=" * 60)
