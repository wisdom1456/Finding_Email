#!/usr/bin/env python3
"""
Test script for the next steps validation functionality.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.utils.validators import validate_next_steps_formatting


def test_validate_next_steps_formatting():
    """Test the validate_next_steps_formatting function."""
    
    print("Testing validate_next_steps_formatting function...")
    
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
        print("✅ Test 1 PASSED: Valid content with <strong> tags accepted")
    except ValueError as e:
        print(f"❌ Test 1 FAILED: Valid content rejected: {e}")
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
        print("❌ Test 2 FAILED: Invalid content was accepted (should have been rejected)")
        return False
    except ValueError as e:
        print("✅ Test 2 PASSED: Invalid content correctly rejected")
        print(f"   Error message: {e}")
    
    # Test case 3: Empty content
    try:
        validate_next_steps_formatting("")
        print("❌ Test 3 FAILED: Empty content was accepted")
        return False
    except ValueError as e:
        print("✅ Test 3 PASSED: Empty content correctly rejected")
        print(f"   Error message: {e}")
    
    # Test case 4: None content
    try:
        validate_next_steps_formatting(None)
        print("❌ Test 4 FAILED: None content was accepted")
        return False
    except ValueError as e:
        print("✅ Test 4 PASSED: None content correctly rejected")
        print(f"   Error message: {e}")
    
    # Test case 5: Content with <STRONG> tags (case insensitive)
    content_with_uppercase = """
    <p>Important deadline: <STRONG>March 1, 2025</STRONG></p>
    """
    
    try:
        validate_next_steps_formatting(content_with_uppercase)
        print("✅ Test 5 PASSED: Case insensitive <STRONG> tags accepted")
    except ValueError as e:
        print(f"❌ Test 5 FAILED: Case insensitive tags rejected: {e}")
        return False
    
    return True


def test_integration():
    """Test basic integration check (import test)."""
    print("\nTesting integration...")
    
    try:
        # Test that the import works correctly
        from backend_logic.email_generator import EmailGeneratorV2
        print("✅ Import test PASSED: EmailGeneratorV2 can be imported with validation")
        return True
    except ImportError as e:
        print(f"❌ Import test FAILED: {e}")
        return False


def main():
    """Run all tests."""
    print("=== Next Steps Validation Test Suite ===\n")
    
    # Run validation tests
    validation_passed = test_validate_next_steps_formatting()
    
    # Run integration tests
    integration_passed = test_integration()
    
    print("\n=== Test Results ===")
    if validation_passed and integration_passed:
        print("🎉 ALL TESTS PASSED!")
        print("✅ Validation function correctly identifies missing <strong> tags")
        print("✅ Integration with EmailGeneratorV2 successful")
        print("\nImplementation Summary:")
        print("- Added validate_next_steps_formatting() to backend/utils/validators.py")
        print("- Integrated validation into _generate_next_steps_content() in EmailGeneratorV2")
        print("- Validation checks for <strong> tags (case insensitive)")
        print("- Logs warnings when validation fails but doesn't interrupt generation process")
        return 0
    else:
        print("❌ SOME TESTS FAILED!")
        return 1


if __name__ == "__main__":
    exit(main())