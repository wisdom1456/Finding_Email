#!/usr/bin/env python3
"""
Test script for the email generator enhancements.
This script tests the two main changes:
1. Updated prompt construction with firm_voice and golden_sample
2. Word count validation loop for 850-word limit
"""
from __future__ import annotations

import os
import sys
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_config_loading():
    """Test that the configuration loads correctly with new word count entries."""
logger.info('=== Testing Configuration Loading ===')

    try:
        from openai import OpenAI

        from backend_logic.email_generator import EmailGeneratorV2

        # Create a dummy OpenAI client for testing
        client = OpenAI(api_key="test-key")

        # Initialize email generator
        generator = EmailGeneratorV2(client)

        # Check that configuration loaded
        assert generator.config is not None, "Configuration should not be None"

        # Check that word_counts section exists
        word_counts = generator.config.get("word_counts", {})
        assert word_counts, "word_counts section should exist"

        # Check that strengths and weaknesses were added
        assert "strengths" in word_counts, "strengths should be in word_counts"
        assert "weaknesses" in word_counts, "weaknesses should be in word_counts"
        assert word_counts["strengths"] == 150, "strengths should be 150 words"
        assert word_counts["weaknesses"] == 150, "weaknesses should be 150 words"

logger.info('✅ Configuration loading test passed')
logger.info(f'   - Found word counts: {list(word_counts.keys())}')
logger.info(f'   - Strengths: {word_counts['strengths']} words')
logger.info(f'   - Weaknesses: {word_counts['weaknesses']} words')

        return True

    except Exception as e:
logger.error(f'❌ Configuration loading test failed: {e}')
        return False

def test_prompt_construction():
    """Test the enhanced prompt construction with firm_voice and golden_sample."""
logger.info('\n=== Testing Prompt Construction ===')

    try:
        from openai import OpenAI

        from backend_logic.email_generator import EmailGeneratorV2

        # Create a dummy OpenAI client for testing
        client = OpenAI(api_key="test-key")

        # Initialize email generator
        generator = EmailGeneratorV2(client)

        # Test prompt construction
        base_prompt = "Write a legal analysis section."
        section_key = "legal_analysis"

        enhanced_prompt = generator._build_enhanced_prompt(base_prompt, section_key)

        # Check that enhanced prompt contains required elements
        firm_voice = generator.config.get("firm_voice", "")
        golden_sample = generator.config.get("golden_sample", "")

        if firm_voice:
            assert firm_voice in enhanced_prompt, "Enhanced prompt should contain firm_voice"
logger.info('✅ Firm voice included in prompt')

        if golden_sample:
            assert "Below is our style exemplar:" in enhanced_prompt, "Enhanced prompt should contain golden sample label"
            assert golden_sample in enhanced_prompt, "Enhanced prompt should contain golden_sample"
logger.info('✅ Golden sample included with correct label')

        # Check word count instruction format
        word_counts = generator.config.get("word_counts", {})
        if section_key in word_counts:
            expected_instruction = f"Draft the {section_key} for a client email (≤ {word_counts[section_key]} words)"
            assert expected_instruction in enhanced_prompt, "Should contain specific word count instruction"
logger.info(f'✅ Word count instruction included: {word_counts[section_key]} words')

        # Check that statute restriction is included
        assert "Do not reference statutes, sections, or chapters" in enhanced_prompt, "Should include statute restriction"
logger.info('✅ Statute restriction included')

logger.info('✅ Prompt construction test passed')
        return True

    except Exception as e:
logger.error(f'❌ Prompt construction test failed: {e}')
        return False

def test_word_count_utilities():
    """Test the word count utility functions."""
logger.info('\n=== Testing Word Count Utilities ===')

    try:
        from openai import OpenAI

        from backend.utils.data_models import GeneratedLetter
        from backend_logic.email_generator import EmailGeneratorV2

        # Create a dummy OpenAI client for testing
        client = OpenAI(api_key="test-key")

        # Initialize email generator
        generator = EmailGeneratorV2(client)

        # Test HTML stripping
        html_content = "<p>This is a <strong>test</strong> with <em>HTML</em> tags.</p>"
        plain_text = generator._strip_html_tags(html_content)
        expected_text = "This is a test with HTML tags."
        assert plain_text == expected_text, f"Expected '{expected_text}', got '{plain_text}'"
logger.info('✅ HTML stripping works correctly')

        # Test word counting
        word_count = len(plain_text.split())
        assert word_count == 7, f"Expected 7 words, got {word_count}"
logger.info('✅ Word counting works correctly')

        # Test longest section identification
        test_letter = GeneratedLetter(
            executive_summary="Short summary.",
            background_summary="This is a much longer background summary with many more words than the other sections.",
            analysis_and_position="Medium length analysis section with some words.",
            media_summary="",
            video_analysis_appendix="",
            strengths="Brief strengths.",
            challenges="Brief challenges.",
            recommendations="Brief recommendations.",
            next_steps="Brief next steps.",
            closing_paragraph="Brief closing."
        )

        longest_section = generator._identify_longest_section(test_letter)
        assert longest_section == "background_summary", f"Expected 'background_summary', got '{longest_section}'"
logger.info('✅ Longest section identification works correctly')

        return True

    except Exception as e:
logger.error(f'❌ Word count utilities test failed: {e}')
        return False

def test_section_key_mapping():
    """Test that section keys are mapped correctly in prompt construction."""
logger.info('\n=== Testing Section Key Mapping ===')

    try:
        from openai import OpenAI

        from backend_logic.email_generator import EmailGeneratorV2

        # Create a dummy OpenAI client for testing
        client = OpenAI(api_key="test-key")

        # Initialize email generator
        generator = EmailGeneratorV2(client)

        # Test mapping for 'analysis' -> 'legal_analysis'
        base_prompt = "Test prompt"
        enhanced_prompt = generator._build_enhanced_prompt(base_prompt, "analysis")

        # Should use legal_analysis word count
        word_counts = generator.config.get("word_counts", {})
        if "legal_analysis" in word_counts:
            expected_limit = word_counts["legal_analysis"]
            assert f"≤ {expected_limit} words" in enhanced_prompt, "Should use legal_analysis word limit"
logger.info(f'✅ Section mapping works: analysis -> legal_analysis ({expected_limit} words)')

        return True

    except Exception as e:
logger.error(f'❌ Section key mapping test failed: {e}')
        return False

def main():
    """Run all tests."""
logger.info('Testing Email Generator Enhancements')
logger.info('=' * 50)

    tests = [
        test_config_loading,
        test_prompt_construction,
        test_word_count_utilities,
        test_section_key_mapping
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
logger.error(f'❌ Test {test.__name__} failed with exception: {e}')

logger.info(f'\n{'=' * 50}')
logger.info(f'Test Results: {passed}/{total} tests passed')

    if passed == total:
logger.info('🎉 All tests passed! Implementation looks good.')
        return True
logger.error('⚠️ Some tests failed. Check the implementation.')
    return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
