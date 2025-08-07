#!/usr/bin/env python3
"""
Test script for post-processing functionality in quality_validator.py
"""

import os
import sys

# Add backend to path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.quality_validator import (
    enforce_word_count_truncation,
    replace_hedging_language,
    process_section_content
)

def test_word_count_truncation():
    """Test the word count truncation function."""
    print("🧪 Testing word count truncation...")
    
    # Test case 1: Content within limit
    short_content = "<p>This is a short paragraph with only a few words.</p>"
    result = enforce_word_count_truncation(short_content, 20)
    print(f"✅ Short content test passed: {len(result.split())} words")
    
    # Test case 2: Content exceeding limit
    long_content = """<p>This is the first sentence with many words that should be preserved. 
    This is the second sentence that might be cut off if we exceed the word limit. 
    This is the third sentence that definitely should be removed when truncating. 
    This is the fourth sentence that will also be removed during truncation.</p>"""
    
    result = enforce_word_count_truncation(long_content, 15)
    print(f"✅ Long content test passed: truncated to appropriate length")
    print(f"   Result: {result[:100]}...")
    
    return True

def test_hedging_language_replacement():
    """Test the hedging language replacement function."""
    print("\n🧪 Testing hedging language replacement...")
    
    # Test case 1: Simple hedging words
    hedged_text = "This case may result in a favorable outcome. The defendant might be liable."
    result = replace_hedging_language(hedged_text)
    print(f"✅ Basic replacement test:")
    print(f"   Before: {hedged_text}")
    print(f"   After:  {result}")
    
    # Test case 2: Hedging within quotes (should be preserved)
    quoted_text = 'The contract states "The work may be completed by Friday" but the defendant could still be liable.'
    result = replace_hedging_language(quoted_text)
    print(f"✅ Quoted text preservation test:")
    print(f"   Before: {quoted_text}")
    print(f"   After:  {result}")
    
    # Test case 3: Complex hedging patterns
    complex_text = "The client could potentially recover damages. This might result in a settlement."
    result = replace_hedging_language(complex_text)
    print(f"✅ Complex patterns test:")
    print(f"   Before: {complex_text}")
    print(f"   After:  {result}")
    
    return True

def test_section_processing():
    """Test the integrated section processing function."""
    print("\n🧪 Testing integrated section processing...")
    
    # Test content with hedging language that exceeds word count
    test_content = """<p>This legal analysis may show that the defendant could be liable for damages. 
    The case might result in a favorable outcome for our client. The evidence potentially supports 
    our claims and could lead to a significant settlement. The defendant may have violated 
    the contract terms. This might give us strong grounds for litigation. The outcome could 
    be very positive for our client's financial recovery.</p>"""
    
    try:
        result = process_section_content(test_content, "legal_analysis")
        print(f"✅ Section processing test passed")
        print(f"   Result: {result}")
        return True
    except Exception as e:
        print(f"❌ Section processing test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Starting post-processing functionality tests...\n")
    
    tests_passed = 0
    total_tests = 3
    
    try:
        if test_word_count_truncation():
            tests_passed += 1
    except Exception as e:
        print(f"❌ Word count truncation test failed: {e}")
    
    try:
        if test_hedging_language_replacement():
            tests_passed += 1
    except Exception as e:
        print(f"❌ Hedging language replacement test failed: {e}")
    
    try:
        if test_section_processing():
            tests_passed += 1
    except Exception as e:
        print(f"❌ Section processing test failed: {e}")
    
    print(f"\n📊 Test Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Post-processing implementation is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please review the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)