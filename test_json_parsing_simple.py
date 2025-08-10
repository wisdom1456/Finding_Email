#!/usr/bin/env python3
"""
Simple test script that doesn't require API keys - just tests the parse_json_response method.
"""

from __future__ import annotations

import os
import sys

from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")


sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def test_json_parsing_simple():
    """Test the JSON parsing method without API calls."""
    logger.debug("Testing JSON parsing without API keys...")

    # Import only the client class but don't instantiate it with API calls
    from backend_logic.ai.openai_client import OpenAIClient

    # Create a mock client that doesn't need API key for parse_json_response
    class MockOpenAIClient:
        def _extract_json_content(self, content: str) -> str:
            return OpenAIClient()._extract_json_content(content)

        def parse_json_response(self, content: str):
            return OpenAIClient().parse_json_response(content)

    client = MockOpenAIClient()

    # Test cases
    test_cases = [
        # Plain JSON
        ('{"key": "value", "number": 42}', "Plain JSON"),
        # JSON in markdown code block with json label
        (
            '```json\n{"key": "value", "array": [1, 2, 3]}\n```',
            "JSON in labeled markdown",
        ),
        # JSON in markdown code block without label
        (
            '```\n{"key": "value", "nested": {"inner": "data"}}\n```',
            "JSON in unlabeled markdown",
        ),
        # Empty content
        ("", "Empty content"),
        # Invalid JSON
        ('{"invalid": json}', "Invalid JSON"),
    ]

    logger.info(f"\nRunning {len(test_cases)} test cases...\n")

    for i, (content, description) in enumerate(test_cases, 1):
        logger.info(f"Test {i}: {description}")
        logger.info(f"Input: {content[:50]}{('...' if len(content) > 50 else '')}")

        try:
            result = client.parse_json_response(content)
            logger.info(f"Return type: {type(result)}")

            if result is not None:
                logger.info("✅ Success: Parsed JSON")
                logger.info(
                    f"   Result: {str(result)[:100]}{('...' if len(str(result)) > 100 else '')}"
                )

                # This is the issue - checking for "success" key on direct JSON result
                if isinstance(result, dict) and "success" in result:
                    logger.info(f"   Has 'success' key: {result['success']}")
                else:
                    logger.info("   ❌ No 'success' key found (this is the problem!)")
            else:
                logger.error("❌ Failed: Returned None")
        except Exception as e:
            logger.error(f"🚨 Error: {e}")

        logger.info("-" * 60)

    logger.debug("JSON parsing tests completed!")
    logger.info("\n🔍 ISSUE IDENTIFIED:")
    logger.info("   parse_json_response() returns the parsed JSON directly")
    logger.info("   But ai_analyzer_refactored.py expects a dict with 'success' key")


if __name__ == "__main__":
    test_json_parsing_simple()
