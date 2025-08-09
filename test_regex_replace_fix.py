#!/usr/bin/env python3
"""
Test script to verify the regex_replace filter fix works correctly.
"""
from __future__ import annotations

import os
import sys


# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from jinja2 import DictLoader, Environment

from backend_logic.email_generator import regex_replace_filter


def test_regex_replace_filter():
    """Test the regex_replace_filter function directly."""
    print("Testing regex_replace_filter function...")
    
    # Test 1: Basic regex replacement
    test_input = "Please complete this within 14 days"
    pattern = r"\b(within\s+\d+\s+days?)\b"
    replacement = r"<strong>\1</strong>"
    result = regex_replace_filter(test_input, pattern, replacement)
    expected = "Please complete this <strong>within 14 days</strong>"
    
    print(f"Test 1 - Input: {test_input}")
    print(f"Test 1 - Result: {result}")
    print(f"Test 1 - Expected: {expected}")
    print(f"Test 1 - {'✅ PASS' if result == expected else '❌ FAIL'}")
    
    # Test 2: Date format replacement
    test_input2 = "Due by March 15, 2025"
    pattern2 = r"\b(by\s+\w+\s+\d{1,2},?\s+\d{4})\b"
    replacement2 = r"<strong>\1</strong>"
    result2 = regex_replace_filter(test_input2, pattern2, replacement2)
    expected2 = "Due <strong>by March 15, 2025</strong>"
    
    print(f"\nTest 2 - Input: {test_input2}")
    print(f"Test 2 - Result: {result2}")
    print(f"Test 2 - Expected: {expected2}")
    print(f"Test 2 - {'✅ PASS' if result2 == expected2 else '❌ FAIL'}")
    
    # Test 3: Handle None input
    result3 = regex_replace_filter(None, r"test", "replacement")
    expected3 = ""
    
    print("\nTest 3 - Input: None")
    print(f"Test 3 - Result: '{result3}'")
    print(f"Test 3 - Expected: '{expected3}'")
    print(f"Test 3 - {'✅ PASS' if result3 == expected3 else '❌ FAIL'}")
    
    return result == expected and result2 == expected2 and result3 == expected3

def test_jinja2_integration():
    """Test the filter works in a Jinja2 template."""
    print("\nTesting Jinja2 template integration...")
    
    # Create a simple template with the regex_replace filter
    template_str = """
    {% set original = "Complete within 30 days of 12/25/2024" %}
    {% set with_bold_duration = original | regex_replace('\\b(within\\s+\\d+\\s+days?)\\b', '<strong>\\1</strong>') %}
    {% set with_bold_date = with_bold_duration | regex_replace('\\b(\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4})\\b', '<strong>\\1</strong>') %}
    {{ with_bold_date }}
    """.strip()
    
    # Create Jinja2 environment and register the filter
    env = Environment(loader=DictLoader({"test": template_str}))
    env.filters["regex_replace"] = regex_replace_filter
    
    template = env.get_template("test")
    result = template.render().strip()
    expected = "Complete <strong>within 30 days</strong> of <strong>12/25/2024</strong>"
    
    print(f"Template result: {result}")
    print(f"Expected: {expected}")
    print(f"Jinja2 Integration - {'✅ PASS' if result == expected else '❌ FAIL'}")
    
    return result == expected

def main():
    """Run all tests."""
    print("🔧 Testing regex_replace filter fix...")
    print("=" * 60)
    
    try:
        # Test the function directly
        function_test_passed = test_regex_replace_filter()
        
        # Test Jinja2 integration
        jinja2_test_passed = test_jinja2_integration()
        
        print("\n" + "=" * 60)
        if function_test_passed and jinja2_test_passed:
            print("🎉 ALL TESTS PASSED! The regex_replace filter fix is working correctly.")
            print("✅ The TemplateRuntimeError should now be resolved.")
        else:
            print("❌ Some tests failed. Please check the implementation.")
            
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
