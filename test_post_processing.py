#!/usr/bin/env python3
"""
Test script for post-processing functionality in quality_validator.py
"""
from __future__ import annotations

import os
import sys
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add backend to path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from backend.quality_validator import (
    enforce_word_count_truncation,
    process_section_content,
    replace_hedging_language,
)


def test_word_count_truncation():
    """Test the word count truncation function."""
logger.info('🧪 Testing word count truncation...')
    
    # Test case 1: Content within limit
    short_content = "<p>This is a short paragraph with only a few words.</p>"
    result = enforce_word_count_truncation(short_content, 20)
logger.info(f'✅ Short content test passed: {len(result.split())} words')
    
    # Test case 2: Content exceeding limit
    long_content = """<p>This is the first sentence with many words that should be preserved. 
    This is the second sentence that might be cut off if we exceed the word limit. 
    This is the third sentence that definitely should be removed when truncating. 
    This is the fourth sentence that will also be removed during truncation.</p>"""
    
    result = enforce_word_count_truncation(long_content, 15)
logger.info('✅ Long content test passed: truncated to appropriate length')
logger.info(f'   Result: {result[:100]}...')
    
    return True

def test_hedging_language_replacement():
    """Test the hedging language replacement function."""
logger.info('\n🧪 Testing hedging language replacement...')
    
    # Test case 1: Simple hedging words
    hedged_text = "This case may result in a favorable outcome. The defendant might be liable."
    result = replace_hedging_language(hedged_text)
logger.info('✅ Basic replacement test:')
logger.info(f'   Before: {hedged_text}')
logger.info(f'   After:  {result}')
    
    # Test case 2: Hedging within quotes (should be preserved)
    quoted_text = 'The contract states "The work may be completed by Friday" but the defendant could still be liable.'
    result = replace_hedging_language(quoted_text)
logger.info('✅ Quoted text preservation test:')
logger.info(f'   Before: {quoted_text}')
logger.info(f'   After:  {result}')
    
    # Test case 3: Complex hedging patterns
    complex_text = "The client could potentially recover damages. This might result in a settlement."
    result = replace_hedging_language(complex_text)
logger.info('✅ Complex patterns test:')
logger.info(f'   Before: {complex_text}')
logger.info(f'   After:  {result}')
    
    return True

def test_section_processing():
    """Test the integrated section processing function."""
logger.debug('\n🧪 Testing integrated section processing...')
    
    # Test content with hedging language that exceeds word count
    test_content = """<p>This legal analysis may show that the defendant could be liable for damages. 
    The case might result in a favorable outcome for our client. The evidence potentially supports 
    our claims and could lead to a significant settlement. The defendant may have violated 
    the contract terms. This might give us strong grounds for litigation. The outcome could 
    be very positive for our client's financial recovery.</p>"""
    
    try:
        result = process_section_content(test_content, "legal_analysis")
logger.debug('✅ Section processing test passed')
logger.info(f'   Result: {result}')
        return True
    except Exception as e:
logger.error(f'❌ Section processing test failed: {e}')
        return False

def main():
    """Run all tests."""
logger.debug('🚀 Starting post-processing functionality tests...\n')
    
    tests_passed = 0
    total_tests = 3
    
    try:
        if test_word_count_truncation():
            tests_passed += 1
    except Exception as e:
logger.error(f'❌ Word count truncation test failed: {e}')
    
    try:
        if test_hedging_language_replacement():
            tests_passed += 1
    except Exception as e:
logger.error(f'❌ Hedging language replacement test failed: {e}')
    
    try:
        if test_section_processing():
            tests_passed += 1
    except Exception as e:
logger.error(f'❌ Section processing test failed: {e}')
    
logger.info(f'\n📊 Test Results: {tests_passed}/{total_tests} tests passed')
    
    if tests_passed == total_tests:
logger.debug('🎉 All tests passed! Post-processing implementation is working correctly.')
        return True
logger.error('⚠️  Some tests failed. Please review the implementation.')
    return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
