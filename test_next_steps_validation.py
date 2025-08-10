#!/usr/bin/env python3
"""
Test script for the next steps validation functionality.
"""
from __future__ import annotations

import os
import sys
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.utils.validators import validate_next_steps_formatting


def test_validate_next_steps_formatting():
    """Test the validate_next_steps_formatting function."""
    
logger.debug('Testing validate_next_steps_formatting function...')
    
    # Test case 1: Valid content with <strong> tags
    valid_content = """
    <p>Based on our analysis, I recommend the following next steps:</p>
    <ul>
    <li>File demand letter by <strong>January 15, 2025</strong></li>
    <li>Gather additional evidence within <strong>30 days</strong></li>
    <li>Schedule follow-up consultation</li>
    </ul>
    """
    
    try:
        validate_next_steps_formatting(valid_content)
logger.info('✅ Test 1 PASSED: Valid content with <strong> tags accepted')
    except ValueError as e:
logger.error(f'❌ Test 1 FAILED: Valid content rejected: {e}')
        return False
    
    # Test case 2: Invalid content without <strong> tags
    invalid_content = """
    <p>Based on our analysis, I recommend the following next steps:</p>
    <ul>
    <li>File demand letter by January 15, 2025</li>
    <li>Gather additional evidence within 30 days</li>
    <li>Schedule follow-up consultation</li>
    </ul>
    """
    
    try:
        validate_next_steps_formatting(invalid_content)
logger.error('❌ Test 2 FAILED: Invalid content was accepted (should have been rejected)')
        return False
    except ValueError as e:
logger.info('✅ Test 2 PASSED: Invalid content correctly rejected')
logger.error(f'   Error message: {e}')
    
    # Test case 3: Empty content
    try:
        validate_next_steps_formatting("")
logger.error('❌ Test 3 FAILED: Empty content was accepted')
        return False
    except ValueError as e:
logger.info('✅ Test 3 PASSED: Empty content correctly rejected')
logger.error(f'   Error message: {e}')
    
    # Test case 4: None content
    try:
        validate_next_steps_formatting(None)
logger.error('❌ Test 4 FAILED: None content was accepted')
        return False
    except ValueError as e:
logger.info('✅ Test 4 PASSED: None content correctly rejected')
logger.error(f'   Error message: {e}')
    
    # Test case 5: Content with <STRONG> tags (case insensitive)
    content_with_uppercase = """
    <p>Important deadline: <STRONG>March 1, 2025</STRONG></p>
    """
    
    try:
        validate_next_steps_formatting(content_with_uppercase)
logger.info('✅ Test 5 PASSED: Case insensitive <STRONG> tags accepted')
    except ValueError as e:
logger.error(f'❌ Test 5 FAILED: Case insensitive tags rejected: {e}')
        return False
    
    return True


def test_integration():
    """Test basic integration check (import test)."""
logger.info('\nTesting integration...')
    
    try:
        # Test that the import works correctly
        from backend_logic.email_generator import EmailGeneratorV2
logger.info('✅ Import test PASSED: EmailGeneratorV2 can be imported with validation')
        return True
    except ImportError as e:
logger.error(f'❌ Import test FAILED: {e}')
        return False


def main():
    """Run all tests."""
logger.debug('=== Next Steps Validation Test Suite ===\n')
    
    # Run validation tests
    validation_passed = test_validate_next_steps_formatting()
    
    # Run integration tests
    integration_passed = test_integration()
    
logger.info('\n=== Test Results ===')
    if validation_passed and integration_passed:
logger.info('🎉 ALL TESTS PASSED!')
logger.info('✅ Validation function correctly identifies missing <strong> tags')
logger.info('✅ Integration with EmailGeneratorV2 successful')
logger.info('\nImplementation Summary:')
logger.debug('- Added validate_next_steps_formatting() to backend/utils/validators.py')
logger.debug('- Integrated validation into _generate_next_steps_content() in EmailGeneratorV2')
logger.info('- Validation checks for <strong> tags (case insensitive)')
logger.warning("- Logs warnings when validation fails but doesn't interrupt generation process")
        return 0
logger.error('❌ SOME TESTS FAILED!')
    return 1


if __name__ == "__main__":
    exit(main())
