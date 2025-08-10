#!/usr/bin/env python3
"""
Debug script to test our JSON-based architecture and see the actual output
"""

from __future__ import annotations

import os
import sys

from openai import OpenAI

from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend_logic")
)


from backend.utils.data_models import (
    AnalyzedDocument,
    CaseAnalysisResult,
    DemandLetterEvaluation,
    EnhancedIntakeAnalysis,
    FinalAnalysis,
    FindingsLetterContent,
    LegalAssessment,
)
from backend_logic.config import get_openai_api_key
from backend_logic.email_generator import EmailGeneratorV2


def create_simple_test_case():
    """Create a simple test case to debug the JSON architecture."""

    # Simple intake analysis
    intake = EnhancedIntakeAnalysis(
        client_name="Jane Smith",
        attorney_name="John Attorney",
        case_summary="Test civil rights case",
        case_type="Civil Rights Violation",
        urgency_level="High",
        client_priorities=["Seek compensation"],
        desired_outcomes=["Settlement"],
        key_facts=["Incident occurred March 15, 2024"],
        parties_involved=[],
        financial_impact="$75,000 in damages",
        legal_claims=["42 U.S.C. § 1983 Civil Rights Violation"],
    )

    # Simple document
    docs = [
        AnalyzedDocument(
            file_name="incident_report.pdf",
            document_type="Incident Report",
            inferred_title="Official Documentation",
            analysis="Clear evidence of misconduct",
            summary="Strong supporting evidence",
            key_information="Witness statements and photos",
            relevance_to_case="Critical evidence",
            key_points=["Timeline established", "Multiple witnesses"],
        )
    ]

    # Simple assessments
    legal_assessment = LegalAssessment(
        case_type="Federal Civil Rights",
        claim_viability="Strong viability",
        overall_evidence_strength="Excellent",
        potential_challenges="Statute of limitations",
        recommended_actions="File complaint immediately",
        demand_letter_appropriate="Yes",
        urgency_assessment="High priority",
    )

    demand_eval = DemandLetterEvaluation(
        is_appropriate="Yes",
        reasoning="Strong evidence supports demand",
        potential_outcomes=["Settlement $100,000-150,000"],
        relevant_statutes=["42 U.S.C. § 1983"],
    )

    final_analysis = FinalAnalysis(
        case_summary="Strong civil rights case with excellent evidence",
        recommendations="Proceed with demand letter immediately",
        next_steps=[
            "File demand letter within 14 days",
            "Gather witness statements by August 30",
        ],
    )

    findings_content = FindingsLetterContent(
        factual_summary="Test case with strong evidence of civil rights violations",
        legal_analysis="Clear violations under federal law",
        strengths_of_case="Multiple witnesses and documentation",
        challenges_and_risks="Potential statute of limitations defense",
        recommended_next_steps="Immediate filing required",
        demand_letter_analysis="Strong case merits aggressive approach",
    )

    return CaseAnalysisResult(
        intake_analysis=intake,
        analyzed_documents=docs,
        legal_assessment=legal_assessment,
        demand_letter_evaluation=demand_eval,
        final_analysis=final_analysis,
        findings_letter_content=findings_content,
    )


def main():
    logger.debug("🔬 Debug: Testing JSON-based Architecture")
    logger.info("=" * 50)

    try:
        # Initialize generator
        api_key = get_openai_api_key()
        client = OpenAI(api_key=api_key)
        generator = EmailGeneratorV2(client=client)

        # Create test case
        test_case = create_simple_test_case()
        logger.info("✅ Test case created")

        # Generate email
        logger.info("\n🔄 Generating email...")
        result = generator.generate_email_and_analysis_docs(test_case)

        if result:
            logger.info("✅ Email generated successfully")
            logger.info(f"📧 Keys in result: {list(result.keys())}")

            # Save raw output for inspection
            with open("debug_raw_output.html", "w", encoding="utf-8") as f:
                f.write(result["main_letter"])

            logger.debug("📄 Raw HTML output saved to: debug_raw_output.html")

            # Show preview of content
            content_preview = result["main_letter"][:500]
            logger.info(f"\n📋 Content Preview:\n{content_preview}...")

        else:
            logger.error("❌ Email generation failed - returned None")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
