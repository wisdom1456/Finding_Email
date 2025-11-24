#!/usr/bin/env python3
"""Test script to validate the enhanced HTML formatting in the findings letter generation.
This script tests the JsonProcessingService directly to ensure proper HTML structure.
"""

import os
import sys

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from legal_portal.config.config_manager import ConfigManager
    from legal_portal.config.default import get_openai_config
    from legal_portal.core.data_models import (
        CaseAnalysisResult,
        DemandLetterEvaluation,
        EnhancedIntakeAnalysis,
        FinalAnalysis,
        LegalAssessment,
        PartyInvolved,
    )
    from legal_portal.services.json_processing_service import JsonProcessingService
    from openai import OpenAI
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)


def create_mock_case_analysis():
    """Create a mock case analysis for testing HTML generation."""
    # Create mock parties involved
    parties = [
        PartyInvolved(name="John Doe", role="Client"),
        PartyInvolved(name="ABC Construction", role="Contractor"),
    ]

    # Create mock intake analysis
    intake_analysis = EnhancedIntakeAnalysis(
        client_name="John Doe",
        attorney_name="Jane Attorney",
        case_summary="Client engaged ABC Construction for $50,000 home renovation. Contractor abandoned project 60% complete with water damage from faulty installation. Client seeks damages.",
        case_type="Construction Law",
        urgency_level="High",
        client_priorities=["Financial Recovery", "Property Resolution"],
        desired_outcomes=["Compensation for damages", "Contract completion"],
        key_facts=[
            "Contract amount: $50,000 with $30,000 already paid",
            "Project 60% complete when abandoned",
            "Water damage caused by faulty installation",
            "Additional $12,000 needed for repairs",
        ],
        parties_involved=parties,
        financial_impact="Estimated $32,000 - $45,000 in damages",
        legal_claims=["Breach of Contract", "Negligent Workmanship"],
    )

    # Create mock legal assessment
    legal_assessment = LegalAssessment(
        case_type="Construction Law",
        claim_viability="Strong - clear breach of contract with quantifiable damages",
        overall_evidence_strength="High - contracts, correspondence, expert assessment available",
        potential_challenges="Contractor may dispute scope; proving causation for water damage",
        recommended_actions="Send demand letter; prepare for litigation if needed",
        demand_letter_appropriate=True,
        urgency_assessment="High - potential for further damage if not resolved quickly",
    )

    # Create mock demand letter evaluation
    demand_letter_eval = DemandLetterEvaluation(
        is_appropriate=True,
        reasoning="Clear breach with quantifiable damages makes demand letter effective",
        potential_outcomes=["Settlement negotiations", "Full payment", "Partial payment"],
        relevant_statutes=["Florida Statute § 713.345", "Florida Construction Defects Law"],
    )

    # Create mock final analysis
    final_analysis = FinalAnalysis(
        case_summary="Strong case for breach of contract with clear damages and evidence",
        recommendations="Pursue demand letter followed by litigation if necessary",
        next_steps=[
            "Draft and send demand letter",
            "Document all damages with expert assessment",
            "Preserve all evidence and communications",
        ],
    )

    # Create complete case analysis result
    case_analysis = CaseAnalysisResult(
        intake_analysis=intake_analysis,
        legal_assessment=legal_assessment,
        demand_letter_evaluation=demand_letter_eval,
        final_analysis=final_analysis,
    )

    return case_analysis


def validate_html_structure(html_content):
    """Validate that the HTML contains proper structure and tags."""
    validation_results = {
        "has_legal_letter_container": '<div class="legal-letter">' in html_content,
        "has_h1_title": "<h1>" in html_content,
        "has_h2_sections": "<h2>" in html_content,
        "has_h3_subsections": "<h3>" in html_content,
        "has_paragraphs": "<p>" in html_content,
        "has_lists": "<ul>" in html_content and "<li>" in html_content,
        "has_strong_emphasis": "<strong>" in html_content,
        "has_proper_closing": "</div>" in html_content,
        "total_length": len(html_content),
    }

    return validation_results


def main():
    """Main test function."""
    print("🧪 Testing Enhanced HTML Formatting for Findings Letters")
    print("=" * 60)

    try:
        # Initialize configuration and service
        print("📋 Initializing services...")
        config_manager = ConfigManager()

        # Get OpenAI configuration and create client
        openai_config = get_openai_config()
        openai_client = OpenAI(api_key=openai_config.get("api_key"))

        # Get the legal config for the service
        legal_config = config_manager.config

        # Create the JsonProcessingService with proper arguments
        json_service = JsonProcessingService(openai_client, legal_config)

        # Create mock case analysis
        print("🏗️  Creating mock case analysis...")
        case_analysis = create_mock_case_analysis()
        print(f"   ✅ Created case for: {case_analysis.intake_analysis.client_name}")
        print(f"   ✅ Case Type: {case_analysis.intake_analysis.case_type}")

        # Generate HTML letter
        print("\n🎨 Generating HTML letter with enhanced formatting...")
        html_content = json_service.generate_html_letter(case_analysis)

        if not html_content:
            print("❌ ERROR: No HTML content generated!")
            return False

        # Validate HTML structure
        print("\n🔍 Validating HTML structure...")
        validation = validate_html_structure(html_content)

        print("\n📊 Validation Results:")
        for check, passed in validation.items():
            if check == "total_length":
                print(f"   📏 HTML Length: {passed:,} characters")
            else:
                status = "✅" if passed else "❌"
                print(f"   {status} {check.replace('_', ' ').title()}: {passed}")

        # Show HTML preview
        print("\n📄 HTML Preview (first 500 characters):")
        print("-" * 50)
        print(html_content[:500] + "..." if len(html_content) > 500 else html_content)
        print("-" * 50)

        # Save output for inspection
        output_file = "test_generated_letter.html"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"\n💾 Full HTML saved to: {output_file}")

        # Check for success
        required_checks = [
            "has_legal_letter_container",
            "has_h1_title",
            "has_h2_sections",
            "has_paragraphs",
            "has_strong_emphasis",
        ]
        all_passed = all(validation[check] for check in required_checks)

        if all_passed:
            print("\n🎉 SUCCESS: HTML formatting validation passed!")
            print("   The enhanced prompt is generating properly structured HTML.")
            return True
        else:
            print("\n⚠️  WARNING: Some HTML structure checks failed.")
            print("   Review the validation results above.")
            return False

    except Exception as e:
        print(f"\n❌ ERROR during testing: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
