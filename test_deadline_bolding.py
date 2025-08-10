#!/usr/bin/env python3
"""
Test script for deadline bolding functionality.

This script tests the regex safety-net function that ensures all deadlines
in the "Next Steps" section are properly bolded.
"""
from __future__ import annotations

import os
import sys
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from quality_validator import bold_deadlines_in_next_steps


def test_deadline_bolding():
    """Test the deadline bolding function with various scenarios."""
    
logger.info('🧪 Testing deadline bolding functionality...')
logger.info('=' * 60)
    
    # Test Case 1: Calendar intervals that need bolding
    test_case_1 = """
    <p>Please complete the following actions within 14 days to ensure compliance.</p>
    <ul>
        <li>Submit documentation within 30 days of notice</li>
        <li>Schedule consultation within 7 days</li>
    </ul>
    """
    
logger.info('Test Case 1: Calendar intervals')
logger.info('Input:' + " " + test_case_1.strip())
    result_1 = bold_deadlines_in_next_steps(test_case_1)
logger.info('Output:' + " " + result_1.strip())
logger.info('✅ PASS' if '<strong>within 14 days</strong>' in result_1 and '<strong>within 30 days</strong>' in result_1 and ('<strong>within 7 days</strong>' in result_1) else '❌ FAIL')
logger.info('')
    
    # Test Case 2: Absolute dates that need bolding
    test_case_2 = """
    <p>Important deadlines:</p>
    <ul>
        <li>File response by August 21, 2025</li>
        <li>Complete discovery by December 15, 2024</li>
    </ul>
    """
    
logger.info('Test Case 2: Absolute dates')
logger.info('Input:' + " " + test_case_2.strip())
    result_2 = bold_deadlines_in_next_steps(test_case_2)
logger.info('Output:' + " " + result_2.strip())
logger.info('✅ PASS' if '<strong>by August 21, 2025</strong>' in result_2 and '<strong>by December 15, 2024</strong>' in result_2 else '❌ FAIL')
logger.info('')
    
    # Test Case 3: Mixed content with some already bolded
    test_case_3 = """
    <p>Next steps include:</p>
    <ul>
        <li>Already bolded: <strong>within 21 days</strong> submit forms</li>
        <li>Not bolded: Complete review within 10 days</li>
        <li>Also not bolded: Respond by March 5, 2025</li>
    </ul>
    """
    
logger.info('Test Case 3: Mixed content (some already bolded)')
logger.info('Input:' + " " + test_case_3.strip())
    result_3 = bold_deadlines_in_next_steps(test_case_3)
logger.info('Output:' + " " + result_3.strip())
    # Should preserve existing bold and add new bold
    has_preserved_bold = "<strong>within 21 days</strong>" in result_3
    has_new_bold_days = "<strong>within 10 days</strong>" in result_3
    has_new_bold_date = "<strong>by March 5, 2025</strong>" in result_3
logger.info('✅ PASS' if has_preserved_bold and has_new_bold_days and has_new_bold_date else '❌ FAIL')
logger.info('')
    
    # Test Case 4: No deadlines to bold
    test_case_4 = """
    <p>General recommendations:</p>
    <ul>
        <li>Review case materials thoroughly</li>
        <li>Contact our office for questions</li>
    </ul>
    """
    
logger.info('Test Case 4: No deadlines present')
logger.info('Input:' + " " + test_case_4.strip())
    result_4 = bold_deadlines_in_next_steps(test_case_4)
logger.info('Output:' + " " + result_4.strip())
logger.info('✅ PASS' if result_4.strip() == test_case_4.strip() else '❌ FAIL')
logger.info('')
    
    # Test Case 5: Edge cases with variations
    test_case_5 = """
    <p>Action items:</p>
    <ul>
        <li>Submit within 1 day for urgent cases</li>
        <li>Complete by January 1, 2026 at latest</li>
        <li>Review within 45 days of service</li>
    </ul>
    """
    
logger.info("Test Case 5: Edge cases (singular 'day', different format)")
logger.info('Input:' + " " + test_case_5.strip())
    result_5 = bold_deadlines_in_next_steps(test_case_5)
logger.info('Output:' + " " + result_5.strip())
    has_singular_day = "<strong>within 1 day</strong>" in result_5
    has_date_format = "<strong>by January 1, 2026</strong>" in result_5
    has_plural_days = "<strong>within 45 days</strong>" in result_5
logger.info('✅ PASS' if has_singular_day and has_date_format and has_plural_days else '❌ FAIL')
logger.info('')
    
logger.info('=' * 60)
logger.info('🎯 All tests completed!')


if __name__ == "__main__":
    test_deadline_bolding()
