#!/usr/bin/env python3
"""
Test script to validate the prompt generation modifications.
This script tests that firm_voice, plain_english_mandate, and golden_sample
are properly injected at the top of every section-level prompt.
"""
from __future__ import annotations

import os
import sys

import yaml
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from backend_logic.email_generator import EmailGeneratorV2


def test_prompt_injection():
    """Test that the enhanced prompt injection works correctly."""
logger.info('🧪 Testing Enhanced Prompt Injection')
logger.info('=' * 50)
    
    try:
        # Create a mock client (we won't actually make API calls)
        class MockOpenAIClient:
            pass
        
        # Initialize EmailGenerator with mock client
        generator = EmailGeneratorV2(MockOpenAIClient())
        
        # Test data
        test_sections = [
            ("factual_summary", 200),
            ("legal_analysis", 150),
            ("case_assessment", 75),
            ("evidence_review", 150),
            ("next_steps", 125)
        ]
        
        # Base prompt to test with
        base_prompt = "This is a test prompt for section generation."
        
logger.info('✅ EmailGenerator initialized successfully')
logger.info(f'✅ Configuration loaded from: {generator.config is not None}')
        
        # Test each section type
        for section_key, expected_word_limit in test_sections:
logger.info(f'\n🔍 Testing section: {section_key}')
            
            # Build enhanced prompt
            enhanced_prompt = generator._build_enhanced_prompt(base_prompt, section_key)
            
            # Verify components are present
            firm_voice = generator.config.get("firm_voice", "")
            plain_english_mandate = generator.config.get("plain_english_mandate", [])
            golden_sample = generator.config.get("golden_sample", "")
            
            # Check that all components are in the prompt
            checks = {
                "firm_voice": firm_voice in enhanced_prompt if firm_voice else True,
                "plain_english_mandate": any(mandate in enhanced_prompt for mandate in plain_english_mandate) if plain_english_mandate else True,
                "golden_sample": golden_sample in enhanced_prompt if golden_sample else True,
                "word_limit": f"≤ {expected_word_limit} words" in enhanced_prompt,
                "instruction_format": f"Draft the {section_key} for a client email" in enhanced_prompt,
                "base_prompt": base_prompt in enhanced_prompt
            }
            
            # Report results
            for check_name, result in checks.items():
                status = "✅" if result else "❌"
logger.info(f'  {status} {check_name}: {('PASS' if result else 'FAIL')}')
                
            # Show prompt structure preview
            prompt_lines = enhanced_prompt.split("\n")
logger.info(f'  📄 Prompt length: {len(enhanced_prompt)} characters')
logger.info(f'  📄 Prompt lines: {len(prompt_lines)}')
logger.info(f'  📄 First 150 chars: {enhanced_prompt[:150]}...')
            
            if not all(checks.values()):
logger.error(f'  ⚠️  FAILED checks for section: {section_key}')
logger.info('  📝 Full prompt preview:')
logger.info('  ' + '\n  '.join(prompt_lines[:10]))
                return False
                
logger.info('\n🎉 All tests PASSED!')
        
        # Show detailed structure for one example
logger.info("\n📋 Example prompt structure for 'factual_summary':")
        example_prompt = generator._build_enhanced_prompt(base_prompt, "factual_summary")
        example_lines = example_prompt.split("\n")
        for i, line in enumerate(example_lines[:15], 1):
logger.info(f'  {i:2d}: {line}')
        if len(example_lines) > 15:
logger.info(f'  ... ({len(example_lines) - 15} more lines)')
            
        return True
        
    except Exception as e:
logger.error(f'❌ Test failed with error: {e}')
        import traceback
        traceback.print_exc()
        return False


def test_configuration_loading():
    """Test that the configuration file loads correctly."""
logger.info('\n🔧 Testing Configuration Loading')
logger.info('-' * 30)
    
    try:
        config_path = "backend/config/templates/universal_legal_config.yaml"
        
        if not os.path.exists(config_path):
logger.info(f'❌ Configuration file not found: {config_path}')
            return False
            
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
            
        # Check required keys
        required_keys = ["firm_voice", "plain_english_mandate", "golden_sample", "word_counts"]
        
        for key in required_keys:
            if key in config:
logger.info(f'✅ {key}: Present')
                
                # Show preview of content
                value = config[key]
                if isinstance(value, str):
                    preview = value[:100] + "..." if len(value) > 100 else value
logger.info(f'   Preview: {preview}')
                elif isinstance(value, list):
logger.info(f'   Items: {len(value)}')
                    if value:
logger.info(f'   First item: {value[0][:50]}...' if len(str(value[0])) > 50 else f'   First item: {value[0]}')
                elif isinstance(value, dict):
logger.info(f'   Keys: {list(value.keys())[:5]}{('...' if len(value) > 5 else '')}')
                    
            else:
logger.info(f'❌ {key}: Missing')
                return False
                
logger.info('✅ All required configuration keys present')
        return True
        
    except Exception as e:
logger.error(f'❌ Configuration loading failed: {e}')
        return False


if __name__ == "__main__":
logger.info('🚀 Starting Prompt Injection Validation Tests')
logger.info('=' * 60)
    
    # Run configuration test first
    config_success = test_configuration_loading()
    
    if config_success:
        # Run prompt injection test
        test_success = test_prompt_injection()
        
        if test_success:
logger.info('\n🎉 ALL TESTS PASSED - Prompt injection is working correctly!')
            sys.exit(0)
        else:
logger.error('\n💥 TESTS FAILED - Prompt injection needs fixes')
            sys.exit(1)
    else:
logger.error('\n💥 CONFIGURATION TEST FAILED - Cannot proceed with prompt tests')
        sys.exit(1)
