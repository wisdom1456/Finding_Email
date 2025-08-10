#!/usr/bin/env python3
"""
Test script for the improved _ensure_html_structure() method.

This script tests the enhanced paragraph enforcement logic to ensure it properly
handles edge cases like floating text after closing block tags.
"""
from __future__ import annotations

import os
import sys
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from openai import OpenAI

from backend_logic.email_generator import EmailGeneratorV2


def test_html_structure_improvements():
    """Test the improved _ensure_html_structure() method with various edge cases."""

    # Create a mock EmailGenerator instance for testing
    mock_client = OpenAI(api_key="test-key-for-testing")
    generator = EmailGeneratorV2(mock_client)

    # Test cases covering various scenarios
    test_cases = [
        {
            "name": "Basic floating text",
            "input": "This is some floating text that needs paragraph tags.",
            "expected_contains": ["<p>This is some floating text that needs paragraph tags.</p>"]
        },
        {
            "name": "Already wrapped paragraph",
            "input": "<p>This text is already properly wrapped.</p>",
            "expected_contains": ["<p>This text is already properly wrapped.</p>"]
        },
        {
            "name": "Mixed content - some wrapped, some floating",
            "input": "<p>Already wrapped text.</p>\nFloating text that needs wrapping.",
            "expected_contains": ["<p>Already wrapped text.</p>", "<p>Floating text that needs wrapping.</p>"]
        },
        {
            "name": "Text after closing ul tag (edge case)",
            "input": "<ul><li>Item 1</li><li>Item 2</li></ul>This text appears after the list.",
            "expected_contains": ["</ul>", "<p>This text appears after the list.</p>"]
        },
        {
            "name": "Text after closing div tag",
            "input": "<div>Content in div</div>Floating text after div.",
            "expected_contains": ["</div>", "<p>Floating text after div.</p>"]
        },
        {
            "name": "Complex mixed content",
            "input": """<h2>Legal Analysis</h2>
<p>This paragraph is properly wrapped.</p>
<ul>
<li>List item 1</li>
<li>List item 2</li>
</ul>
This text appears after the list and should be wrapped.
<div>Content in a div</div>More floating text here.
<p>Another proper paragraph.</p>
Final floating text at the end.""",
            "expected_contains": [
                "<h2>Legal Analysis</h2>",
                "<p>This paragraph is properly wrapped.</p>",
                "</ul>",
                "<p>This text appears after the list and should be wrapped.</p>",
                "</div>",
                "<p>More floating text here.</p>",
                "<p>Another proper paragraph.</p>",
                "<p>Final floating text at the end.</p>"
            ]
        },
        {
            "name": "Empty content",
            "input": "",
            "expected_contains": []
        },
        {
            "name": "Only whitespace",
            "input": "   \n\n   ",
            "expected_contains": []
        },
        {
            "name": "Content with only HTML tags",
            "input": "<br><hr>",
            "expected_contains": ["<br><hr>"]
        },
        {
            "name": "Multiple floating text lines",
            "input": """First line of floating text.
Second line of floating text.
Third line of floating text.""",
            "expected_contains": [
                "<p>First line of floating text.</p>",
                "<p>Second line of floating text.</p>",
                "<p>Third line of floating text.</p>"
            ]
        }
    ]

logger.info('Testing improved _ensure_html_structure() method...')
logger.info('=' * 60)

    passed_tests = 0
    failed_tests = 0

    for i, test_case in enumerate(test_cases, 1):
logger.info(f'\nTest {i}: {test_case['name']}')
logger.info(f'Input: {test_case['input']!r}')

        try:
            # Call the improved method
            result = generator._ensure_html_structure(test_case["input"])
logger.info(f'Output: {result!r}')

            # Check if expected content is present
            test_passed = True
            for expected in test_case["expected_contains"]:
                if expected not in result:
logger.info(f"❌ FAIL: Expected '{expected}' not found in result")
                    test_passed = False

            if test_passed:
logger.info('✅ PASS')
                passed_tests += 1
            else:
                failed_tests += 1

        except Exception as e:
logger.error(f'❌ ERROR: {e}')
            failed_tests += 1

logger.info('\n' + '=' * 60)
logger.error(f'Test Results: {passed_tests} passed, {failed_tests} failed')

    if failed_tests == 0:
logger.info('🎉 All tests passed! The improved _ensure_html_structure() method is working correctly.')
        return True
logger.error('⚠️  Some tests failed. Please review the implementation.')
    return False


def test_specific_edge_case():
    """Test the specific edge case mentioned in the user request."""

    mock_client = OpenAI(api_key="test-key-for-testing")
    generator = EmailGeneratorV2(mock_client)

logger.info('\n' + '=' * 60)
logger.info('Testing Specific Edge Case: Text after closing </ul> tag')
logger.info('=' * 60)

    # This is the specific problematic case mentioned by the user
    problematic_input = """<ul>
<li>First item</li>
<li>Second item</li>
</ul>This text should be wrapped in paragraph tags."""

logger.info(f'Input: {problematic_input!r}')

    result = generator._ensure_html_structure(problematic_input)
logger.info(f'Output: {result!r}')

    # Check that the floating text after </ul> is properly wrapped
    if "<p>This text should be wrapped in paragraph tags.</p>" in result:
logger.info('✅ SUCCESS: Floating text after </ul> is properly wrapped!')
        return True
logger.error('❌ FAILURE: Floating text after </ul> was not properly wrapped!')
    return False


if __name__ == "__main__":
logger.info('HTML Structure Improvement Test Suite')
logger.info('Testing enhanced paragraph enforcement logic')
logger.info('')

    # Run comprehensive tests
    general_tests_passed = test_html_structure_improvements()

    # Run specific edge case test
    edge_case_passed = test_specific_edge_case()

    # Overall result
logger.info('\n' + '=' * 60)
    if general_tests_passed and edge_case_passed:
logger.info('🎉 ALL TESTS PASSED! The _ensure_html_structure() improvement is successful.')
        sys.exit(0)
    else:
logger.error('❌ SOME TESTS FAILED! Please review the implementation.')
        sys.exit(1)
