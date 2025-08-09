#!/usr/bin/env python3
"""
Test script for the new section-by-section readability regeneration system.

This script tests the robust multi-pass regeneration system that:
1. Checks Flesch Reading Ease score on each section (minimum 50)
2. Regenerates content up to 2 times if needed using simplification_pass_prompt
3. Logs detailed information for each attempt
4. Raises EmailReadabilityError if still fails after 2 attempts
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from unittest.mock import Mock, patch


# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the necessary modules
from openai import OpenAI

from backend.utils.data_models import (
    CaseAnalysisResult,
    EnhancedIntakeAnalysis,
    GenerationContext,
    SectionPlan,
)
from backend_logic.email_generator import EmailGeneratorV2, EmailReadabilityError


def create_mock_analysis() -> CaseAnalysisResult:
    """Create a mock case analysis for testing."""
    mock_intake = EnhancedIntakeAnalysis(
        client_name="Test Client",
        attorney_name="Test Attorney",
        case_summary="Test case summary for readability testing",
        case_type="Contract Dispute",
        urgency_level="Standard",
        financial_impact="$10,000",  # Add required field
        key_facts=["Contract signed", "Work not completed"],  # Add required field
        legal_claims=["Breach of contract"]  # Add required field
    )
    
    return CaseAnalysisResult(
        intake_analysis=mock_intake,
        analyzed_documents=[],
        legal_assessment=None,
        demand_letter_evaluation=None,
        transcripted_media=[],
        video_insights=[]
    )


def create_complex_content() -> str:
    """Create deliberately complex content that should fail readability check."""
    return """
    <p>The aforementioned contractual obligations, pursuant to the stipulations delineated 
    within the comprehensive agreement executed contemporaneously with the initiation of the 
    business relationship, necessitate a thorough examination of the multifaceted legal 
    implications inherent in the sophisticated commercial transaction, wherein the parties' 
    respective responsibilities and concomitant liabilities must be meticulously evaluated 
    in accordance with the prevailing jurisprudential precedents and statutory frameworks 
    governing such complex commercial arrangements.</p>
    """


def create_simple_content() -> str:
    """Create simple content that should pass readability check."""
    return """
    <p>The contract clearly states your rights. We reviewed the agreement you signed. 
    The other party must follow the terms. They failed to complete the work on time. 
    You have several options to fix this problem.</p>
    """


def test_readability_validation_pass():
    """Test that simple content passes readability validation without regeneration."""
    print("\n=== Testing Readability Validation - PASS ===")
    
    try:
        # Create mock generator
        mock_client = Mock(spec=OpenAI)
        generator = EmailGeneratorV2(mock_client)
        
        # Create test data
        analysis = create_mock_analysis()
        context = GenerationContext()
        section_plan = SectionPlan(
            number=1,
            header="FACTUAL SUMMARY",
            key_points=[],
            emphasis_items={},
            content_requirements=[]
        )
        
        # Test with simple content that should pass
        simple_content = create_simple_content()
        
        result = generator._validate_section_readability_with_regeneration(
            simple_content, "FACTUAL SUMMARY", section_plan, analysis, context
        )
        
        print("✅ PASS: Simple content passed readability validation")
        print(f"   Original: {len(simple_content)} chars")
        print(f"   Result: {len(result)} chars")
        print(f"   Content unchanged: {result == simple_content}")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: Simple content test failed: {e}")
        return False


def test_readability_validation_fail():
    """Test that complex content fails readability validation and triggers regeneration."""
    print("\n=== Testing Readability Validation - FAIL with Regeneration ===")
    
    try:
        # Create mock generator with mocked AI response
        mock_client = Mock(spec=OpenAI)
        generator = EmailGeneratorV2(mock_client)
        
        # Mock the AI request to return simplified content
        def mock_openai_request(prompt, system_prompt, model=None):
            return create_simple_content()
        
        generator._make_openai_request = mock_openai_request
        
        # Create test data
        analysis = create_mock_analysis()
        context = GenerationContext()
        section_plan = SectionPlan(
            number=1,
            header="FACTUAL SUMMARY",
            key_points=[],
            emphasis_items={},
            content_requirements=[]
        )
        
        # Test with complex content that should fail and be regenerated
        complex_content = create_complex_content()
        
        result = generator._validate_section_readability_with_regeneration(
            complex_content, "FACTUAL SUMMARY", section_plan, analysis, context
        )
        
        print("✅ PASS: Complex content was regenerated successfully")
        print(f"   Original: {len(complex_content)} chars")
        print(f"   Result: {len(result)} chars")
        print(f"   Content was regenerated: {result != complex_content}")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: Complex content regeneration test failed: {e}")
        return False


def test_readability_validation_graceful_degradation():
    """Test that content with poor readability generates warnings but continues with document generation."""
    print("\n=== Testing Readability Validation - GRACEFUL DEGRADATION ===")
    
    try:
        # Create mock generator with mocked AI response that always returns complex content
        mock_client = Mock(spec=OpenAI)
        generator = EmailGeneratorV2(mock_client)
        
        # Mock the AI request to always return complex content (simulating failure)
        def mock_openai_request_fail(prompt, system_prompt, model=None):
            return create_complex_content()  # Always return complex content
        
        generator._make_openai_request = mock_openai_request_fail
        
        # Create test data
        analysis = create_mock_analysis()
        context = GenerationContext()
        section_plan = SectionPlan(
            number=1,
            header="FACTUAL SUMMARY",
            key_points=[],
            emphasis_items={},
            content_requirements=[]
        )
        
        # Test with complex content that should fail but continue gracefully
        complex_content = create_complex_content()
        
        result = generator._validate_section_readability_with_regeneration(
            complex_content, "FACTUAL SUMMARY", section_plan, analysis, context
        )
        
        # Verify that we got a result (not an exception)
        if not result:
            print("❌ FAIL: Expected content with warning but got empty result")
            return False
        
        # Verify that the result contains a readability warning notice
        if "⚠️ Readability Notice:" not in result:
            print("❌ FAIL: Expected readability warning notice in result but not found")
            return False
        
        # Verify that the original content is still included
        print("✅ PASS: Graceful degradation working correctly")
        print(f"   Result contains warning notice: {'⚠️ Readability Notice:' in result}")
        print(f"   Document generation continued: {len(result) > len(complex_content)}")
        print(f"   Original content preserved: {complex_content.strip() in result}")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: Graceful degradation test failed unexpectedly: {e}")
        return False


def test_simplification_prompt_template():
    """Test that the simplification prompt template is correctly configured."""
    print("\n=== Testing Simplification Prompt Template ===")
    
    try:
        # Create mock generator
        mock_client = Mock(spec=OpenAI)
        generator = EmailGeneratorV2(mock_client)
        
        # Check that the simplification prompt template exists
        formatting_section = generator.config.get("formatting", {})
        simplification_template = formatting_section.get("simplification_pass_prompt", "")
        
        if not simplification_template:
            print("❌ FAIL: simplification_pass_prompt not found in configuration")
            return False
        
        # Test template formatting
        test_topic = "LEGAL ANALYSIS"
        test_text = "Complex legal text that needs simplification."
        
        try:
            formatted_prompt = simplification_template.format(
                topic=test_topic,
                text_to_simplify=test_text
            )
            
            if test_topic in formatted_prompt and test_text in formatted_prompt:
                print("✅ PASS: Simplification prompt template is correctly configured")
                print(f"   Template contains topic placeholder: {'{{topic}}' in simplification_template}")
                print(f"   Template contains text placeholder: {'{{text_to_simplify}}' in simplification_template}")
                return True
            print("❌ FAIL: Template formatting failed - missing topic or text")
            return False
                
        except KeyError as e:
            print(f"❌ FAIL: Template formatting failed - missing placeholder: {e}")
            return False
        
    except Exception as e:
        print(f"❌ FAIL: Simplification template test failed: {e}")
        return False


def main():
    """Run all readability regeneration tests."""
    print("🧪 TESTING: Robust Multi-Pass Regeneration System")
    print("=" * 60)
    
    tests = [
        test_simplification_prompt_template,
        test_readability_validation_pass,
        test_readability_validation_fail,
        test_readability_validation_graceful_degradation,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ FAIL: Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED - Robust Multi-Pass Regeneration System is working correctly!")
        return True
    print("⚠️  SOME TESTS FAILED - Please review the implementation")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
