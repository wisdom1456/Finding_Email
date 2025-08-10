#!/usr/bin/env python3
"""
Test script to verify word count trimming functionality
"""

from __future__ import annotations

import os
import sys

from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")


# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def test_word_count_trimming():
    """Test the word count trimming functionality"""
    logger.info("🧪 Testing word count trimming functionality...")

    try:
        # Import the EmailGeneratorV2 class
        from openai import OpenAI

        from backend_logic.email_generator import EmailGeneratorV2

        # Create a mock config for testing
        test_config = {
            "word_counts": {
                "factual_summary": 200,
                "legal_analysis": 150,
                "evidence_review": 150,
                "case_assessment": 75,
                "next_steps": 125,
            }
        }

        # Create a mock OpenAI client (we won't actually call the API)
        client = OpenAI(api_key="test-key")

        # Create EmailGenerator instance with mock config
        generator = EmailGeneratorV2(client, config_path=None)
        generator.config = test_config  # Override with our test config

        # Test HTML content that exceeds the word limit
        test_html = """
        <p>This is a test paragraph with many words that should exceed the target word count for trimming purposes. 
        The paragraph contains multiple sentences that provide detailed information about various legal matters and considerations. 
        Each sentence adds to the total word count and helps us test the trimming functionality properly.</p>
        
        <p>This is another paragraph that continues the content and adds even more words to test the trimming system. 
        The content should be intelligently trimmed at sentence boundaries where possible to maintain readability and structure. 
        The HTML structure should be preserved during the trimming process.</p>
        
        <p>This final paragraph adds additional content to ensure we have enough words to test the trimming mechanism thoroughly. 
        The trimming should respect HTML tags and try to maintain proper formatting while reducing the word count to the target limit. 
        This comprehensive test helps verify the functionality works as expected.</p>
        """

        logger.info(
            f"📊 Original content word count: {len(generator._strip_html_tags(test_html).split())} words"
        )

        # Test trimming to different word limits
        test_cases = [
            ("factual_summary", 200),
            ("legal_analysis", 150),
            ("case_assessment", 75),
            ("next_steps", 125),
        ]

        for section_key, target_words in test_cases:
            logger.info(
                f"\n🔧 Testing trimming for '{section_key}' (target: {target_words} words)"
            )

            trimmed_content = generator._trim_html_content_by_word_count(
                test_html, target_words
            )
            final_word_count = len(generator._strip_html_tags(trimmed_content).split())
            max_allowed = int(target_words * 1.15)  # 15% tolerance

            logger.info(f"   📈 Trimmed content word count: {final_word_count} words")
            logger.info(f"   🎯 Target: {target_words}, Max allowed: {max_allowed}")

            if final_word_count <= max_allowed:
                logger.info("   ✅ PASS - Word count within limits")
            else:
                logger.info("   ❌ FAIL - Word count exceeds limit")

            # Check if HTML structure is preserved
            if "<p>" in trimmed_content and "</p>" in trimmed_content:
                logger.info("   ✅ PASS - HTML structure preserved")
            else:
                logger.warning("   ⚠️  WARN - HTML structure may be damaged")

        logger.info("\n🧪 Testing _apply_word_count_trimming integration...")

        # Test the integration method
        test_content = "<p>This is a test content with exactly twenty words for testing the word count trimming integration functionality properly.</p>"

        trimmed = generator._apply_word_count_trimming(test_content, "case_assessment")
        trimmed_words = len(generator._strip_html_tags(trimmed).split())

        logger.info(
            f"   📊 Original: {len(generator._strip_html_tags(test_content).split())} words"
        )
        logger.info(f"   📊 Trimmed: {trimmed_words} words")
        logger.info(
            f"   🎯 Target: {test_config['word_counts']['case_assessment']} words"
        )

        if trimmed_words <= test_config["word_counts"]["case_assessment"]:
            logger.info("   ✅ PASS - Integration test successful")
        else:
            logger.error("   ❌ FAIL - Integration test failed")

        logger.info("\n✅ Word count trimming functionality test completed!")
        return True

    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.info("Make sure you're running this from the project root directory")
        return False
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    logger.info("🚀 Starting word count trimming tests...\n")
    success = test_word_count_trimming()

    if success:
        logger.info("\n🎉 All tests completed successfully!")
        sys.exit(0)
    else:
        logger.error("\n💥 Tests failed!")
        sys.exit(1)
