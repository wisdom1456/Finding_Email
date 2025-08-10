#!/usr/bin/env python3
"""
Test script for the updated JSON parsing logic in OpenAI client.
"""
from __future__ import annotations

import os
import sys
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend_logic.ai.openai_client import OpenAIClient


def test_json_parsing():
    """Test the new JSON parsing functionality."""
logger.debug('Testing JSON parsing improvements...')

    # Create a client instance
    client = OpenAIClient()

    # Test cases
    test_cases = [
        # Plain JSON
        ('{"key": "value", "number": 42}', "Plain JSON"),

        # JSON in markdown code block with json label
        ('```json\n{"key": "value", "array": [1, 2, 3]}\n```', "JSON in labeled markdown"),

        # JSON in markdown code block without label
        ('```\n{"key": "value", "nested": {"inner": "data"}}\n```', "JSON in unlabeled markdown"),

        # JSON array
        ('[{"item": 1}, {"item": 2}]', "Plain JSON array"),

        # JSON array in markdown
        ('```json\n[{"name": "test"}, {"name": "test2"}]\n```', "JSON array in markdown"),

        # Empty content
        ("", "Empty content"),

        # Invalid JSON
        ('{"invalid": json}', "Invalid JSON"),

        # Text with no JSON
        ("This is just plain text with no JSON content.", "Plain text"),
    ]

logger.info(f'\nRunning {len(test_cases)} test cases...\n')

    for i, (content, description) in enumerate(test_cases, 1):
logger.info(f'Test {i}: {description}')
logger.info(f'Input: {content[:50]}{('...' if len(content) > 50 else '')}')

        try:
            result = client.parse_json_response(content)
            if result is not None:
logger.info(f'✅ Success: Parsed JSON - {type(result).__name__}')
logger.info(f'   Result: {str(result)[:100]}{('...' if len(str(result)) > 100 else '')}')
            else:
logger.error('❌ Failed: Returned None')
        except Exception as e:
logger.error(f'🚨 Error: {e}')

logger.info('-' * 60)

logger.debug('JSON parsing tests completed!')

if __name__ == "__main__":
    test_json_parsing()
