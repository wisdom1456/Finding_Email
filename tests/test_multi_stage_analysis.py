"""Test script for multi-stage analysis pipeline.

This script tests the enhanced 4-stage analysis workflow to ensure it produces
attorney-quality letters with proper structure, tone, and legal reasoning.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Load environment variables first
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from legal_portal.core.document_processor import DocumentProcessor  # noqa: E402
from legal_portal.services.json_processing_service import JsonProcessingService  # noqa: E402
from legal_portal.services.multi_stage_analyzer import MultiStageAnalyzer  # noqa: E402
from legal_portal.services.statute_recommendation_service import StatuteRecommendationService  # noqa: E402
from legal_portal.utils.logging_config import get_module_logger  # noqa: E402
from legal_portal.utils.openai_client import OpenAIClient  # noqa: E402

logger = get_module_logger(__name__)


async def test_multi_stage_pipeline():
    """Test the complete multi-stage analysis pipeline."""
    print("\n" + "=" * 80)
    print("MULTI-STAGE ANALYSIS PIPELINE TEST")
    print("=" * 80 + "\n")

    # Initialize services
    print("1️⃣  Initializing services...")
    openai_client = OpenAIClient()
    doc_processor = DocumentProcessor()
    statute_service = StatuteRecommendationService()
    analyzer = MultiStageAnalyzer(openai_client=openai_client, statute_service=statute_service)
    json_service = JsonProcessingService(client=openai_client, config={})

    # Test with Erik Devlin case (from real_findings_letters folder)
    test_case_dir = Path(__file__).parent / "test_data" / "Balaji_Badam"

    if not test_case_dir.exists():
        print(f"❌ Test data directory not found: {test_case_dir}")
        print("   Please ensure test data exists before running this test.")
        return

    print(f"2️⃣  Loading test case from: {test_case_dir}")

    # Find intake form
    intake_files = list(test_case_dir.glob("*intake*.txt")) + list(test_case_dir.glob("*intake*.json"))
    if not intake_files:
        print("❌ No intake form found")
        return

    intake_path = str(intake_files[0])
    print(f"   Found intake: {intake_path}")

    # Find case documents (exclude intake)
    doc_files = [f for f in test_case_dir.glob("*.*") if f.suffix in [".pdf", ".jpg", ".png", ".eml", ".txt"]]
    doc_files = [f for f in doc_files if "intake" not in f.name.lower()]
    doc_paths = [str(f) for f in doc_files[:5]]  # Limit to 5 docs for testing

    print(f"   Found {len(doc_paths)} case documents")

    # Process intake
    print("\n3️⃣  Processing intake form...")
    processed_intake = await doc_processor.process_documents_from_paths(
        [intake_path], intake_filenames=[os.path.basename(intake_path)]
    )

    if not processed_intake:
        print("❌ Failed to process intake")
        return

    intake_content = processed_intake[0].content
    print(f"   ✅ Processed: {len(intake_content)} characters")

    # Process documents
    print("\n4️⃣  Processing case documents...")
    processed_docs = []
    if doc_paths:
        processed_docs = await doc_processor.process_documents_from_paths(
            doc_paths, intake_filenames=[os.path.basename(intake_path)]
        )
        print(f"   ✅ Processed: {len(processed_docs)} documents")
    else:
        print("   ⚠️  No case documents to process")

    # Create test case info and review data
    case_info = {
        "clientName": "Test Client",
        "attorneyName": "John Doe",
        "firmName": "Test Law Firm",
        "caseType": "Construction Defect",
    }

    review_data = {"legal_issues": ["breach of contract", "construction defects"], "confirmed_qa_pairs": []}

    # Run multi-stage analysis
    print("\n5️⃣  Running multi-stage analysis pipeline...")
    print("   Stage 1: Extracting fact matrix...")

    fact_matrix, legal_issue_map, deep_analysis, letter_structure = await analyzer.analyze_case(
        intake_content=intake_content,
        processed_documents=processed_docs,
        case_info=case_info,
        review_data=review_data,
        progress_callback=lambda msg, phase=None: print(f"      → {msg}"),
    )

    print("\n6️⃣  Analysis Results:")
    print(f"   Parties: {len(fact_matrix.parties)}")
    print(f"   Timeline Events: {len(fact_matrix.timeline)}")
    print(f"   Financial Items: {len(fact_matrix.financial_data)}")
    print(f"   Legal Issues: {len(legal_issue_map.primary_issues)}")
    print(f"   Relevant Statutes: {len(legal_issue_map.relevant_statutes)}")
    print(f"   Letter Structure: {letter_structure.style}")
    print(f"   Reasoning: {letter_structure.reasoning}")

    # Display fact matrix details
    print("\n7️⃣  Fact Matrix Details:")
    for party in fact_matrix.parties[:3]:  # Show first 3 parties
        print(f"   - {party.name}: {party.role}")

    for event in fact_matrix.timeline[:3]:  # Show first 3 timeline events
        print(f"   - {event.date}: {event.description}")

    # Display legal analysis
    print("\n8️⃣  Legal Analysis:")
    for analysis in deep_analysis.issue_analyses[:3]:  # Show first 3 issues
        print(f"   Issue: {analysis.issue_name}")
        print(f"   Legal Standard: {analysis.legal_standard[:100]}...")
        print(f"   Confidence: {analysis.confidence_level}")
        print()

    # Generate adaptive letter
    print("\n9️⃣  Generating adaptive findings email...")

    verified_statutes = [
        {"citation": s["citation"], "title": s.get("title", ""), "summary": s.get("description", "")}
        for s in legal_issue_map.relevant_statutes
    ]

    letter_html = await json_service.generate_findings_letter_adaptive(
        intake_content=intake_content,
        fact_matrix=fact_matrix,
        legal_analysis=deep_analysis,
        structure_guidance=letter_structure,
        verified_statutes=verified_statutes,
        attorney_name=case_info["attorneyName"],
        firm_name=case_info["firmName"],
        confirmed_qa_pairs=[],
        contact_phone="(727) 275-9575",
        contact_email="test@example.com",
        quality_context="",
        clio_matter_context="",
    )

    print(f"   ✅ Generated letter: {len(letter_html)} characters")

    # Save output
    output_dir = Path(__file__).parent / "validation_output"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / "multi_stage_test_letter.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(letter_html)

    print(f"\n   💾 Saved to: {output_file}")

    # Save analysis results
    analysis_file = output_dir / "multi_stage_analysis.json"
    analysis_data = {
        "fact_matrix": {
            "parties": [p.model_dump() for p in fact_matrix.parties],
            "timeline": [e.model_dump() for e in fact_matrix.timeline],
            "financial_data": [f.model_dump() for f in fact_matrix.financial_data],
        },
        "legal_issue_map": {
            "primary_issues": legal_issue_map.primary_issues,
            "relevant_statutes": legal_issue_map.relevant_statutes,
        },
        "deep_analysis": {
            "issue_analyses": [a.model_dump() for a in deep_analysis.issue_analyses],
            "overall_case_strength": deep_analysis.overall_case_strength,
            "key_strengths": deep_analysis.key_strengths,
            "key_challenges": deep_analysis.key_challenges,
        },
        "letter_structure": {"style": letter_structure.style, "reasoning": letter_structure.reasoning},
    }

    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analysis_data, f, indent=2, default=str)

    print(f"   💾 Analysis saved to: {analysis_file}")

    print("\n" + "=" * 80)
    print("✅ MULTI-STAGE ANALYSIS TEST COMPLETE")
    print("=" * 80 + "\n")

    # Quality checks
    print("🔍 Quality Checks:")
    checks = [
        ("Subject line present", "Subject:" in letter_html),
        ("Numbered sections", any(f"{i}." in letter_html for i in range(1, 6))),
        ("Professional tone", "Good afternoon" in letter_html or "I hope this" in letter_html),
        ("Legal citations", "Fla. Stat" in letter_html or "Florida Statutes" in letter_html),
        ("Recommendations", "recommend" in letter_html.lower()),
    ]

    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"   {status} {check_name}")

    return {
        "fact_matrix": fact_matrix,
        "legal_issue_map": legal_issue_map,
        "deep_analysis": deep_analysis,
        "letter_structure": letter_structure,
        "letter_html": letter_html,
    }


if __name__ == "__main__":
    asyncio.run(test_multi_stage_pipeline())
