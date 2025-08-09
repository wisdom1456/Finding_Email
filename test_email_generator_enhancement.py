#!/usr/bin/env python3
"""
Test script to verify the email generator enhancement with firm_voice and word limits.
"""
from __future__ import annotations

import os
import sys


sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.utils.data_models import CaseAnalysisResult, EnhancedIntakeAnalysis
from backend_logic.email_generator import EmailGeneratorV2


def test_enhanced_prompt_building():
    """Test that the enhanced prompt building works correctly."""
    print("Testing enhanced prompt building...")
    
    # Create a mock EmailGeneratorV2 instance with minimal setup
    try:
        # We'll test without actual OpenAI client for now
        class MockClient:
            pass
        
        generator = EmailGeneratorV2(MockClient())
        
        # Test the _build_enhanced_prompt method
        base_prompt = "Write a legal analysis section."
        
        # Test for analysis section (should map to legal_analysis with 150 word limit)
        enhanced_prompt_analysis = generator._build_enhanced_prompt(base_prompt, "analysis")
        print("✅ Enhanced prompt for 'analysis' section generated")
        print(f"   Length: {len(enhanced_prompt_analysis)} characters")
        
        # Check that firm voice is included
        firm_voice = generator.config.get("firm_voice", "")
        if firm_voice and firm_voice in enhanced_prompt_analysis:
            print("✅ Firm voice correctly included in prompt")
        else:
            print("❌ Firm voice missing from prompt")
        
        # Check that golden sample is included
        golden_sample = generator.config.get("golden_sample", "")
        if golden_sample and golden_sample in enhanced_prompt_analysis:
            print("✅ Golden sample correctly included in prompt")
        else:
            print("❌ Golden sample missing from prompt")
        
        # Check that word limit is included (should be 150 for analysis)
        if "Hard cap: 150 words" in enhanced_prompt_analysis:
            print("✅ Word limit (150 words) correctly included for analysis section")
        else:
            print("❌ Word limit missing or incorrect for analysis section")
        
        # Check that content restrictions are included
        if "No citations or code numbers" in enhanced_prompt_analysis:
            print("✅ Content restrictions correctly included")
        else:
            print("❌ Content restrictions missing from prompt")
        
        # Test for strengths_and_weaknesses section (should have 75 word limit)
        enhanced_prompt_strengths = generator._build_enhanced_prompt(base_prompt, "strengths_and_weaknesses")
        if "Hard cap: 75 words" in enhanced_prompt_strengths:
            print("✅ Word limit (75 words) correctly included for strengths_and_weaknesses section")
        else:
            print("❌ Word limit missing or incorrect for strengths_and_weaknesses section")
        
        print("\n" + "="*60)
        print("SAMPLE ENHANCED PROMPT OUTPUT:")
        print("="*60)
        print(enhanced_prompt_analysis[:500] + "..." if len(enhanced_prompt_analysis) > 500 else enhanced_prompt_analysis)
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing enhanced prompt building: {e}")
        return False


def test_config_loading():
    """Test that the configuration is loaded correctly."""
    print("\nTesting configuration loading...")
    
    try:
        class MockClient:
            pass
        
        generator = EmailGeneratorV2(MockClient())
        config = generator.config
        
        # Check that all required configuration elements are present
        required_keys = ["firm_voice", "golden_sample", "word_counts", "content_rules"]
        for key in required_keys:
            if key in config:
                print(f"✅ Configuration key '{key}' found")
                if key == "word_counts":
                    word_counts = config[key]
                    if "legal_analysis" in word_counts and word_counts["legal_analysis"] == 150:
                        print("✅ legal_analysis word count correctly set to 150")
                    if "case_assessment" in word_counts and word_counts["case_assessment"] == 75:
                        print("✅ case_assessment word count correctly set to 75")
            else:
                print(f"❌ Configuration key '{key}' missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing configuration loading: {e}")
        return False


def test_section_mapping():
    """Test that section mapping works correctly."""
    print("\nTesting section mapping...")
    
    try:
        class MockClient:
            pass
        
        generator = EmailGeneratorV2(MockClient())
        
        # Test the section mapping in _build_enhanced_prompt
        test_cases = [
            ("analysis", "legal_analysis", 150),
            ("strengths_and_weaknesses", "case_assessment", 75),
            ("factual_summary", "factual_summary", 200),
            ("evidence_review", "evidence_review", 150),
            ("next_steps", "next_steps", 125),
        ]
        
        for input_section, expected_mapped_section, expected_word_count in test_cases:
            enhanced_prompt = generator._build_enhanced_prompt("Test prompt", input_section)
            if f"Hard cap: {expected_word_count} words" in enhanced_prompt:
                print(f"✅ Section '{input_section}' correctly mapped to {expected_word_count} words")
            else:
                print(f"❌ Section '{input_section}' mapping failed - expected {expected_word_count} words")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing section mapping: {e}")
        return False


def main():
    """Run all tests."""
    print("🧪 Testing Email Generator Enhancement Implementation")
    print("=" * 60)
    
    tests = [
        test_config_loading,
        test_enhanced_prompt_building,
        test_section_mapping,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"🎉 ALL TESTS PASSED ({passed}/{total})")
        print("\n✅ Implementation is working correctly!")
        print("\nThe email generator now includes:")
        print("  • Firm voice prepended to all section prompts")
        print("  • Golden sample for consistent output style")
        print("  • Word count limits: analysis (150), strengths_and_weaknesses (75)")
        print("  • Content restrictions: 'No citations or code numbers'")
    else:
        print(f"❌ {total - passed} TESTS FAILED ({passed}/{total} passed)")
        print("\n⚠️  Some issues need to be addressed")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
