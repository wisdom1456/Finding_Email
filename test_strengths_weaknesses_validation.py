#!/usr/bin/env python3
"""
Test script to verify the enhanced strengths and weaknesses validation.

This script tests:
1. The enhanced case assessment generation with explicit section requirements
2. The validation guard that prevents emails with empty weaknesses
3. The fail-fast behavior when validation fails
"""

import sys
import traceback
from unittest.mock import Mock, MagicMock

# Import the modules we need to test
try:
    from backend_logic.email_generator import EmailGeneratorV2
    from backend.quality_validator import validate_email_completeness, WeaknessesValidationError
    from backend.utils.data_models import GeneratedLetter, CaseAnalysisResult, EnhancedIntakeAnalysis
    from openai import OpenAI
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


def create_mock_letter_with_empty_weaknesses():
    """Create a mock letter with empty weaknesses field."""
    return GeneratedLetter(
        executive_summary="Sample executive summary",
        background_summary="Sample background", 
        analysis_and_position="Sample analysis",
        media_summary="",
        video_analysis_appendix="",
        strengths="<p><strong>STRENGTHS</strong></p><p>This case has strong documentation and clear liability.</p>",
        challenges="",  # Empty weaknesses - should trigger validation failure
        recommendations="Sample recommendations",
        next_steps="Sample next steps",
        closing_paragraph="Sample closing"
    )


def create_mock_letter_with_placeholder_weaknesses():
    """Create a mock letter with placeholder weaknesses content."""
    return GeneratedLetter(
        executive_summary="Sample executive summary",
        background_summary="Sample background",
        analysis_and_position="Sample analysis", 
        media_summary="",
        video_analysis_appendix="",
        strengths="<p><strong>STRENGTHS</strong></p><p>This case has strong documentation and clear liability.</p>",
        challenges="<p>Strategic considerations under Florida law.</p>",  # Placeholder - should trigger validation failure
        recommendations="Sample recommendations",
        next_steps="Sample next steps",
        closing_paragraph="Sample closing"
    )


def create_mock_letter_with_valid_content():
    """Create a mock letter with valid strengths and weaknesses content."""
    return GeneratedLetter(
        executive_summary="Sample executive summary",
        background_summary="Sample background",
        analysis_and_position="Sample analysis",
        media_summary="",
        video_analysis_appendix="",
        strengths="""<p><strong>STRENGTHS</strong></p>
        <p>This case demonstrates several compelling strengths that support our client's position:</p>
        <ul>
        <li>Clear contractual breach with documented performance failures</li>
        <li>Strong documentary evidence including emails and written correspondence</li>
        <li>Quantifiable damages with supporting financial records</li>
        </ul>""",
        challenges="""<p><strong>POTENTIAL CHALLENGES</strong></p>
        <p>While the case is strong, we must address several strategic considerations:</p>
        <ul>
        <li>Opposing party may assert comparative negligence defenses</li>
        <li>Statute of limitations timing requires careful analysis</li>
        <li>Discovery costs may be substantial given document volume</li>
        </ul>""",
        recommendations="Sample recommendations",
        next_steps="Sample next steps", 
        closing_paragraph="Sample closing"
    )


def test_validation_functions():
    """Test the validation functions directly."""
    print("🧪 Testing validation functions...")
    
    # Test 1: Empty weaknesses should fail
    print("\n📋 Test 1: Empty weaknesses validation")
    try:
        letter = create_mock_letter_with_empty_weaknesses()
        validate_email_completeness(letter)
        print("❌ FAILED: Empty weaknesses should have triggered validation error")
        return False
    except WeaknessesValidationError as e:
        print(f"✅ PASSED: Correctly caught empty weaknesses - {e}")
    except Exception as e:
        print(f"❌ FAILED: Unexpected error - {e}")
        return False
    
    # Test 2: Placeholder weaknesses should fail
    print("\n📋 Test 2: Placeholder weaknesses validation")
    try:
        letter = create_mock_letter_with_placeholder_weaknesses()
        validate_email_completeness(letter)
        print("❌ FAILED: Placeholder weaknesses should have triggered validation error")
        return False
    except WeaknessesValidationError as e:
        print(f"✅ PASSED: Correctly caught placeholder weaknesses - {e}")
    except Exception as e:
        print(f"❌ FAILED: Unexpected error - {e}")
        return False
    
    # Test 3: Valid content should pass
    print("\n📋 Test 3: Valid content validation")
    try:
        letter = create_mock_letter_with_valid_content()
        validate_email_completeness(letter)
        print("✅ PASSED: Valid content passed validation")
    except WeaknessesValidationError as e:
        print(f"❌ FAILED: Valid content should not trigger validation error - {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error - {e}")
        return False
    
    return True


def test_enhanced_prompt_structure():
    """Test that the enhanced prompt includes the required structure."""
    print("\n🧪 Testing enhanced prompt structure...")
    
    try:
        # Create a mock OpenAI client
        mock_client = Mock(spec=OpenAI)
        
        # Mock the chat completion response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = """
        **STRENGTHS**
        This case demonstrates clear contractual breach with strong documentation supporting our client's position.
        
        **POTENTIAL CHALLENGES**  
        Opposing party may assert comparative negligence and discovery costs could be substantial.
        """
        
        mock_client.with_options.return_value.chat.completions.create.return_value = mock_response
        
        # Create email generator with mock client
        generator = EmailGeneratorV2(mock_client)
        
        # Mock the configuration loading to avoid file dependencies
        generator.config = {
            'personas': {'CONTINUING_LEGAL_ADVISOR': 'You are a legal advisor.'},
            'word_counts': {'strengths_and_weaknesses': 200},
            'firm_voice': 'Professional legal analysis',
            'golden_sample': 'Sample legal writing',
            'content_rules': []
        }
        
        # Create a minimal case analysis for testing
        mock_analysis = Mock(spec=CaseAnalysisResult)
        mock_analysis.model_dump_json.return_value = '{"case": "test"}'
        
        # Create a mock section plan
        from backend.utils.data_models import SectionPlan
        section_plan = SectionPlan(
            number=1,
            header="CASE ASSESSMENT",
            key_points=["Test point"],
            emphasis_items={},
            content_requirements=["strengths", "challenges"]
        )
        
        # Create mock context
        from backend.utils.data_models import GenerationContext
        context = GenerationContext()
        
        # Test the enhanced case assessment generation
        result = generator._generate_case_assessment_content(section_plan, mock_analysis, context)
        
        print(f"✅ PASSED: Enhanced prompt generated content: {len(result)} characters")
        
        # Verify that the prompt was called with enhanced requirements
        args, kwargs = mock_client.with_options.return_value.chat.completions.create.call_args
        prompt_content = kwargs['messages'][1]['content']
        
        if "CRITICAL REQUIREMENT: You MUST generate TWO distinct sections" in prompt_content:
            print("✅ PASSED: Enhanced prompt includes critical requirement for two sections")
        else:
            print("❌ FAILED: Enhanced prompt missing critical requirement")
            return False
            
        if "**STRENGTHS**" in prompt_content and "**POTENTIAL CHALLENGES**" in prompt_content:
            print("✅ PASSED: Enhanced prompt includes required section headers")
        else:
            print("❌ FAILED: Enhanced prompt missing required section headers")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: Error testing enhanced prompt - {e}")
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("🚀 TESTING STRENGTHS & WEAKNESSES VALIDATION")
    print("=" * 60)
    
    all_tests_passed = True
    
    # Test validation functions
    if not test_validation_functions():
        all_tests_passed = False
    
    # Test enhanced prompt structure
    if not test_enhanced_prompt_structure():
        all_tests_passed = False
    
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 ALL TESTS PASSED!")
        print("✅ The email generator now enforces both strengths and weaknesses generation")
        print("✅ The validation guard prevents emails with empty 'Potential Challenges' sections")
        print("✅ The system will fail-fast when validation requirements are not met")
    else:
        print("❌ SOME TESTS FAILED!")
        print("Please review the implementation and fix any issues.")
    print("=" * 60)
    
    return 0 if all_tests_passed else 1


if __name__ == "__main__":
    sys.exit(main())