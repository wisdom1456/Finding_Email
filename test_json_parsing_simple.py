#!/usr/bin/env python3
"""
Simple test script that doesn't require API keys - just tests the parse_json_response method.
"""
from __future__ import annotations

import os
import sys


sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_json_parsing_simple():
    """Test the JSON parsing method without API calls."""
    print("Testing JSON parsing without API keys...")
    
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
        ('```json\n{"key": "value", "array": [1, 2, 3]}\n```', "JSON in labeled markdown"),
        
        # JSON in markdown code block without label
        ('```\n{"key": "value", "nested": {"inner": "data"}}\n```', "JSON in unlabeled markdown"),
        
        # Empty content
        ("", "Empty content"),
        
        # Invalid JSON
        ('{"invalid": json}', "Invalid JSON"),
    ]
    
    print(f"\nRunning {len(test_cases)} test cases...\n")
    
    for i, (content, description) in enumerate(test_cases, 1):
        print(f"Test {i}: {description}")
        print(f"Input: {content[:50]}{'...' if len(content) > 50 else ''}")
        
        try:
            result = client.parse_json_response(content)
            print(f"Return type: {type(result)}")
            
            if result is not None:
                print("✅ Success: Parsed JSON")
                print(f"   Result: {str(result)[:100]}{'...' if len(str(result)) > 100 else ''}")
                
                # This is the issue - checking for "success" key on direct JSON result
                if isinstance(result, dict) and "success" in result:
                    print(f"   Has 'success' key: {result['success']}")
                else:
                    print("   ❌ No 'success' key found (this is the problem!)")
            else:
                print("❌ Failed: Returned None")
        except Exception as e:
            print(f"🚨 Error: {e}")
        
        print("-" * 60)
    
    print("JSON parsing tests completed!")
    print("\n🔍 ISSUE IDENTIFIED:")
    print("   parse_json_response() returns the parsed JSON directly")
    print("   But ai_analyzer_refactored.py expects a dict with 'success' key")

if __name__ == "__main__":
    test_json_parsing_simple()
