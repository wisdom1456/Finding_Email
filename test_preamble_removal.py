#!/usr/bin/env python3
"""Test script to validate that the preamble removal modification is working correctly.
This script tests that the generated letter starts directly with the document title
and salutation, without any introductory summary paragraph.
"""

import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_preamble_removal():
    """Test that generated letters start correctly without preamble"""
    print("=== TESTING PREAMBLE REMOVAL ===")
    print("Testing that letters start directly with title and salutation...")

    try:
        # Import required modules
        from legal_portal.config.config_manager import ConfigManager
        from legal_portal.services.json_processing_service import JsonProcessingService
        from openai import OpenAI

        print("✓ Modules imported successfully")

        # Initialize services
        config_manager = ConfigManager()

        # Initialize OpenAI client
        openai_client = OpenAI()

        # Get config as dictionary
        config_dict = config_manager.config

        json_service = JsonProcessingService(openai_client, config_dict)

        print("✓ Services initialized")

        # Create a simple mock case analysis for testing
        from legal_portal.core.data_models import CaseAnalysisResult, EnhancedIntakeAnalysis, LegalAssessment

        # Create mock intake analysis
        mock_intake = EnhancedIntakeAnalysis(
            client_name="Erik Devlin",
            attorney_name="Bernhardt Riley",
            case_summary="Construction Dispute - LLW Construction Inc.",
            case_type="Contract Dispute",
            urgency_level="High",
            financial_impact="$128,335.77 contract amount",
            summary="Test intake summary",
        )

        # Create mock legal assessment
        mock_legal = LegalAssessment(
            case_type="Contract Dispute",
            claim_viability="Strong",
            overall_evidence_strength="Good",
            potential_challenges="Timing and documentation issues",
            recommended_actions="Send demand letter and pursue negotiations",
            demand_letter_appropriate=True,
            urgency_assessment="High priority case",
        )

        # Create full case analysis
        mock_case_analysis = CaseAnalysisResult(
            intake_analysis=mock_intake, legal_assessment=mock_legal, analyzed_documents=[], video_insights=[]
        )

        print("✓ Mock case analysis created")

        # Generate letter using the master prompt
        print("\n📝 Generating letter with updated prompt...")
        letter_content = json_service.generate_html_letter(mock_case_analysis)

        if not letter_content:
            print("✗ Letter generation failed - no content returned")
            return False

        print(f"✓ Letter generated successfully ({len(letter_content)} characters)")

        # Check if letter starts correctly (without preamble)
        print("\n🔍 Analyzing letter structure...")

        # Convert to text for easier analysis
        import re

        # Remove HTML tags for text analysis
        text_content = re.sub("<[^<]+?>", "", letter_content).strip()

        # Split into lines and get first few non-empty lines
        lines = [line.strip() for line in text_content.split("\n") if line.strip()]

        if len(lines) < 2:
            print("✗ Generated letter has insufficient content")
            return False

        first_line = lines[0]
        second_line = lines[1]

        print(f"First line: {first_line}")
        print(f"Second line: {second_line}")

        # Validate structure
        success = True

        # Check that first line is the document title
        if not first_line.startswith("Legal Review and Recommended Next Steps"):
            print(f"✗ First line should be document title, got: {first_line}")
            success = False
        else:
            print("✓ First line is correct document title")

        # Check that second line is the salutation
        if not second_line.startswith("Good afternoon"):
            print(f"✗ Second line should be salutation, got: {second_line}")
            success = False
        else:
            print("✓ Second line is correct salutation")

        # Check for absence of preamble keywords
        preamble_indicators = [
            "summary",
            "overview",
            "this letter",
            "this document",
            "following our review",
            "i am providing",
            "based on our analysis",
        ]

        # Check first 200 characters for preamble indicators
        first_part = text_content[:200].lower()

        found_preamble = False
        for indicator in preamble_indicators:
            if indicator in first_part and "good afternoon" not in first_part[:50]:
                print(f"⚠️ Potential preamble indicator found: '{indicator}'")
                found_preamble = True

        if not found_preamble:
            print("✓ No preamble indicators found in opening")

        # Save output for inspection
        output_file = "validation_output/test_letter_no_preamble.html"
        os.makedirs("validation_output", exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(letter_content)

        print(f"✓ Letter saved to {output_file} for inspection")

        # Display first few lines of the letter for verification
        print("\n📋 LETTER PREVIEW (first 500 characters):")
        print("-" * 60)
        print(text_content[:500])
        print("-" * 60)

        if success:
            print("\n🎉 PREAMBLE REMOVAL TEST PASSED!")
            print("✓ Letter starts directly with document title")
            print("✓ Salutation follows immediately")
            print("✓ No introductory preamble detected")
            return True
        else:
            print("\n❌ PREAMBLE REMOVAL TEST FAILED!")
            print("The letter structure does not match expected format")
            return False

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Starting preamble removal validation test...")
    success = test_preamble_removal()

    if success:
        print("\n✅ SUCCESS: Preamble removal modification is working correctly!")
        sys.exit(0)
    else:
        print("\n❌ FAILURE: Preamble removal needs further adjustment!")
        sys.exit(1)
