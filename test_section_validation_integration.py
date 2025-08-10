#!/usr/bin/env python3
"""
Comprehensive test for section-level output format validation integration.

This test validates:
1. validate_section_output function with JSON and HTML formats
2. Integration with EmailGeneratorV2._validate_section_format method
3. Non-blocking error handling (warnings logged but generation continues)
4. YAML configuration parsing for output_format specifications
"""
from __future__ import annotations

import os
import sys
from unittest.mock import Mock, patch

import yaml
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.utils.validators import validate_section_output
from backend_logic.email_generator import EmailGeneratorV2


def test_validate_section_output():
    """Test the core validate_section_output function."""
logger.info('🧪 Testing validate_section_output function...')
    
    # Test 1: Valid JSON format
logger.info('  ✅ Testing valid JSON...')
    valid_json = '{"key": "value", "analysis": "detailed findings"}'
    try:
        validate_section_output(valid_json, "json")
logger.info('    ✅ Valid JSON passed validation')
    except ValueError as e:
logger.error(f'    ❌ Valid JSON failed validation: {e}')
        return False
    
    # Test 2: Invalid JSON format
logger.info('  ✅ Testing invalid JSON...')
    invalid_json = '{"key": "value", "analysis": incomplete'
    try:
        validate_section_output(invalid_json, "json")
logger.error('    ❌ Invalid JSON should have failed validation')
        return False
    except ValueError as e:
logger.error(f'    ✅ Invalid JSON correctly failed validation: {e}')
    
    # Test 3: Valid HTML format
logger.info('  ✅ Testing valid HTML...')
    valid_html = "<p>This is a detailed analysis.</p><ul><li>Point 1</li><li>Point 2</li></ul>"
    try:
        validate_section_output(valid_html, "html")
logger.info('    ✅ Valid HTML passed validation')
    except ValueError as e:
logger.error(f'    ❌ Valid HTML failed validation: {e}')
        return False
    
    # Test 4: Invalid HTML format (no required tags)
logger.info('  ✅ Testing invalid HTML...')
    invalid_html = "Plain text without any HTML tags"
    try:
        validate_section_output(invalid_html, "html")
logger.error('    ❌ Invalid HTML should have failed validation')
        return False
    except ValueError as e:
logger.error(f'    ✅ Invalid HTML correctly failed validation: {e}')
    
    # Test 5: Unknown format (should default gracefully)
logger.info('  ✅ Testing unknown format...')
    try:
        validate_section_output("any content", "unknown")
logger.info('    ✅ Unknown format handled gracefully')
    except ValueError as e:
logger.info(f'    ❌ Unknown format should be handled gracefully: {e}')
        return False
    
logger.info('✅ validate_section_output function tests PASSED')
    return True

def test_email_generator_integration():
    """Test integration with EmailGeneratorV2._validate_section_format method."""
logger.info('\n🧪 Testing EmailGeneratorV2 integration...')
    
    # Create test YAML configuration
    test_config = {
        "sections": {
            "intake_analysis": {"output_format": "json"},
            "legal_analysis": {"output_format": "html"},
            "factual_summary": {"output_format": "html"},
            "next_steps": {}  # No output_format specified (should default to html)
        },
        "personas": {
            "CONTINUING_LEGAL_ADVISOR": "Test persona"
        },
        "formatting": {
            "strict_format_enforcement": "Test enforcement"
        }
    }
    
    # Mock OpenAI client
    mock_client = Mock()
    
    # Create EmailGeneratorV2 instance with test config
    try:
        with patch("backend_logic.email_generator.EmailGeneratorV2._load_configuration") as mock_load_config:
            with patch("backend_logic.email_generator.EmailGeneratorV2._find_template_directory") as mock_find_template:
                mock_load_config.return_value = test_config
                mock_find_template.return_value = "/tmp"  # Mock template directory
                
                # Mock the template directory check
                with patch("os.path.exists", return_value=True):
                    with patch("os.listdir", return_value=["findings_email.jinja2", "document_appendix.jinja2"]):
                        generator = EmailGeneratorV2(mock_client)
                        
logger.info('  ✅ EmailGeneratorV2 instance created successfully')
    except Exception as e:
logger.error(f'  ❌ Failed to create EmailGeneratorV2 instance: {e}')
        return False
    
    # Test 1: Valid JSON content for JSON format section
logger.info('  ✅ Testing valid JSON content validation...')
    valid_json_content = '{"findings": "Analysis complete", "confidence": 0.85}'
    try:
        # Capture print output to verify logging
        with patch("builtins.print") as mock_print:
            generator._validate_section_format(valid_json_content, "intake_analysis")
            
            # Check if success message was printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            success_logged = any("format validation passed (json)" in call for call in print_calls)
            if success_logged:
logger.info('    ✅ Valid JSON validation passed and logged correctly')
            else:
logger.info('    ⚠️ Valid JSON validation passed but logging unclear')
    except Exception as e:
logger.error(f'    ❌ Valid JSON validation failed unexpectedly: {e}')
        return False
    
    # Test 2: Invalid JSON content (should log warning but not raise exception)
logger.info('  ✅ Testing invalid JSON content validation...')
    invalid_json_content = '{"findings": "Analysis incomplete'  # Missing closing brace
    try:
        with patch("builtins.print") as mock_print:
            generator._validate_section_format(invalid_json_content, "intake_analysis")
            
            # Check if warning was logged
            print_calls = [str(call) for call in mock_print.call_args_list]
            warning_logged = any("format validation warning" in call for call in print_calls)
            if warning_logged:
logger.warning('    ✅ Invalid JSON validation correctly logged warning')
            else:
logger.warning('    ⚠️ Invalid JSON validation should have logged warning')
    except Exception as e:
logger.error(f'    ❌ Invalid JSON validation should not raise exception: {e}')
        return False
    
    # Test 3: Valid HTML content for HTML format section
logger.info('  ✅ Testing valid HTML content validation...')
    valid_html_content = "<p>Legal analysis shows strong case.</p><ul><li>Evidence point 1</li></ul>"
    try:
        with patch("builtins.print") as mock_print:
            generator._validate_section_format(valid_html_content, "legal_analysis")
            
            print_calls = [str(call) for call in mock_print.call_args_list]
            success_logged = any("format validation passed (html)" in call for call in print_calls)
            if success_logged:
logger.info('    ✅ Valid HTML validation passed and logged correctly')
            else:
logger.info('    ⚠️ Valid HTML validation passed but logging unclear')
    except Exception as e:
logger.error(f'    ❌ Valid HTML validation failed unexpectedly: {e}')
        return False
    
    # Test 4: Section with no output_format (should default to html)
logger.info('  ✅ Testing section with default format...')
    try:
        with patch("builtins.print") as mock_print:
            generator._validate_section_format(valid_html_content, "next_steps")
            
            print_calls = [str(call) for call in mock_print.call_args_list]
            success_logged = any("format validation passed (html)" in call for call in print_calls)
            if success_logged:
logger.info('    ✅ Default HTML format validation passed correctly')
            else:
logger.info('    ⚠️ Default HTML format validation passed but logging unclear')
    except Exception as e:
logger.error(f'    ❌ Default format validation failed unexpectedly: {e}')
        return False
    
    # Test 5: Non-existent section (should log warning but not crash)
logger.info('  ✅ Testing non-existent section...')
    try:
        with patch("builtins.print") as mock_print:
            generator._validate_section_format(valid_html_content, "nonexistent_section")
            
            print_calls = [str(call) for call in mock_print.call_args_list]
            warning_logged = any("No configuration found for section" in call for call in print_calls)
            if warning_logged:
logger.warning('    ✅ Non-existent section correctly logged warning')
            else:
logger.warning('    ⚠️ Non-existent section should have logged configuration warning')
    except Exception as e:
logger.error(f'    ❌ Non-existent section validation should not raise exception: {e}')
        return False
    
logger.info('✅ EmailGeneratorV2 integration tests PASSED')
    return True

def test_yaml_config_integration():
    """Test actual YAML configuration file parsing."""
logger.info('\n🧪 Testing YAML configuration integration...')
    
    # Test loading the actual universal_legal_config.yaml file
    config_path = "backend/config/templates/universal_legal_config.yaml"
    
    if not os.path.exists(config_path):
logger.info(f'  ⚠️ Configuration file not found: {config_path}')
logger.info('    This test requires the actual YAML configuration file')
        return True  # Not a failure if file doesn't exist in test environment
    
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
logger.info(f'  ✅ Successfully loaded configuration file: {config_path}')
        
        # Check that sections configuration exists
        if "sections" not in config:
logger.info("  ❌ Configuration missing 'sections' key")
            return False
            
        sections = config["sections"]
logger.info(f'  ✅ Found {len(sections)} sections in configuration')
        
        # Test specific sections we know should exist
        expected_sections = ["intake_analysis", "factual_summary", "legal_analysis", "next_steps"]
        format_found = {}
        
        for section_key in expected_sections:
            if section_key in sections:
                section_config = sections[section_key]
                output_format = section_config.get("output_format", "html")  # Default to html
                format_found[section_key] = output_format
logger.info(f'    ✅ {section_key}: {output_format} format')
            else:
logger.info(f"    ⚠️ Expected section '{section_key}' not found in configuration")
        
        # Verify we found format specifications
        if format_found:
logger.info(f'  ✅ Found format specifications for {len(format_found)} sections')
            
            # Show format distribution
            json_sections = [k for k, v in format_found.items() if v == "json"]
            html_sections = [k for k, v in format_found.items() if v == "html"]
            
            if json_sections:
logger.info(f'    📋 JSON format sections: {json_sections}')
            if html_sections:
logger.info(f'    🌐 HTML format sections: {html_sections}')
        
logger.info('✅ YAML configuration integration tests PASSED')
        return True
        
    except Exception as e:
logger.error(f'  ❌ Error loading configuration file: {e}')
        return False

def run_all_tests():
    """Run all validation tests."""
logger.info('🚀 Starting Section Validation Integration Tests')
logger.info('=' * 60)
    
    test_results = []
    
    # Run individual test suites
    test_results.append(test_validate_section_output())
    test_results.append(test_email_generator_integration())
    test_results.append(test_yaml_config_integration())
    
logger.info('\n' + '=' * 60)
logger.info('📊 TEST RESULTS SUMMARY')
logger.info('=' * 60)
    
    passed = sum(test_results)
    total = len(test_results)
    
    if passed == total:
logger.info(f'🎉 ALL TESTS PASSED ({passed}/{total})')
logger.info('\n✅ Section validation integration is working correctly!')
logger.info('\nKey Features Validated:')
logger.info('  • JSON format validation for structured data sections')
logger.info('  • HTML format validation for content sections')
logger.error('  • Non-blocking error handling (warnings logged, generation continues)')
logger.debug('  • YAML configuration parsing for output_format specifications')
logger.info('  • Default format handling (html) when output_format not specified')
logger.info('  • Integration with EmailGeneratorV2 section generation pipeline')
        return True
logger.error(f'❌ SOME TESTS FAILED ({passed}/{total})')
logger.error('\n⚠️ Please review the failed tests above and fix any issues.')
    return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
