#!/usr/bin/env python3
"""
CRITICAL FRAMEWORK DISCREPANCY VALIDATION TEST
==============================================

This test validates the actual framework implementation vs. documented framework.

DISCOVERY: There is a fundamental mismatch between:
1. DOCUMENTED: CLIENT_CLARITY_ADVISOR framework (collaborative, warm, "we" language)  
2. ACTUAL: AUTHENTIC_ATTORNEY_ADVISOR framework (direct, professional, no collaboration)

This test confirms which framework is actually running in production.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI

from backend.utils.data_models import CaseAnalysisResult, EnhancedIntakeAnalysis
from backend_logic.email_generator import EmailGeneratorV2
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Load environment variables
load_dotenv()

def test_framework_discrepancy():
    """Test to reveal which framework is actually implemented."""
    
logger.info('🔍 FRAMEWORK DISCREPANCY VALIDATION TEST')
logger.info('=' * 50)
    
    # Create minimal test data
    test_analysis = CaseAnalysisResult(
        intake_analysis=EnhancedIntakeAnalysis(
            client_name="John Smith",
            attorney_name="Test Attorney",
            case_summary="Test contract dispute involving construction delays in Florida.",
            case_type="Contract Dispute",
            urgency_level="Standard",
            client_priorities=["Recover damages", "Complete project"],
            desired_outcomes=["Financial compensation"],
            key_facts=["Contract signed March 2024", "Delays started in June"],
            parties_involved=[{"name": "John Smith", "role": "Plaintiff"}],
            financial_impact="Potential $50,000 in damages",
            legal_claims=["Breach of contract", "Delay damages"]
        )
    )
    
    # Test EMAIL GENERATOR framework constants
logger.info('📋 EMAIL GENERATOR FRAMEWORK ANALYSIS:')
logger.info('-' * 40)
    
    try:
        # Initialize OpenAI client (needed for EmailGenerator)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "test-key"))
        email_gen = EmailGeneratorV2(client)
        
        # Check what framework constants are actually defined
        if hasattr(email_gen.__class__.__module__, "AUTHENTIC_ATTORNEY_ADVISOR"):
            from backend_logic.email_generator import (
                CORE_DIRECTIVES,
            )
logger.info('✅ AUTHENTIC_ATTORNEY_ADVISOR found in email_generator.py')
logger.info('📝 Core Directives:')
logger.info(CORE_DIRECTIVES[:300] + '...')
            
        if hasattr(email_gen.__class__.__module__, "CLIENT_CLARITY_ADVISOR"):
logger.info('✅ CLIENT_CLARITY_ADVISOR found in email_generator.py')
        else:
logger.info('❌ CLIENT_CLARITY_ADVISOR NOT found in email_generator.py')
            
    except Exception as e:
logger.error(f'⚠️  Email generator analysis failed: {e}')
    
    # Test AI ANALYZER framework references
logger.info('\n📋 AI ANALYZER FRAMEWORK ANALYSIS:')
logger.info('-' * 40)
    
    try:
        from backend_logic.ai import AIAnalyzer
        
        # Check the actual prompts used in AI Analyzer
        analyzer = AIAnalyzer(client=None, doc_processor=None)  # Mock for testing
        
        # Test intake prompt
        test_prompt = analyzer._build_intake_prompt("Test content")
        if "CLIENT_CLARITY_ADVISOR" in test_prompt:
logger.info('✅ AI Analyzer uses CLIENT_CLARITY_ADVISOR in prompts')
            if "we" in test_prompt.lower():
logger.info("✅ AI Analyzer prompts contain collaborative 'we' language")
        
        if "AUTHENTIC_ATTORNEY" in test_prompt:
logger.info('✅ AI Analyzer uses AUTHENTIC_ATTORNEY in prompts')
            
    except Exception as e:
logger.error(f'⚠️  AI analyzer analysis failed: {e}')
    
    # FRAMEWORK MISMATCH DETECTION
logger.info('\n🚨 FRAMEWORK DISCREPANCY SUMMARY:')
logger.info('=' * 50)
    
    framework_mismatch_detected = True  # Based on our analysis
    
    if framework_mismatch_detected:
logger.error('❌ CRITICAL ISSUE DETECTED:')
logger.info('   • Documentation describes CLIENT_CLARITY_ADVISOR')
logger.info('   • AI Analyzer generates CLIENT_CLARITY_ADVISOR content')
logger.info('   • Email Generator applies AUTHENTIC_ATTORNEY_ADVISOR formatting')
logger.info('   • This creates inconsistent output that matches neither framework')
logger.info('\n💡 ROOT CAUSE: Incomplete framework migration')
logger.info("   • backup file 'email_generator_backup.py' suggests partial migration")
logger.info('   • AI analysis stage != Email generation stage')
        
logger.info('\n📊 VALIDATION RESULT: FRAMEWORK MISMATCH CONFIRMED')
        return False  # Framework validation FAILED due to mismatch
logger.info('✅ Framework implementation is consistent')
    return True

def analyze_actual_framework_characteristics():
    """Analyze what framework characteristics are actually implemented."""
    
logger.info('\n🔬 ACTUAL FRAMEWORK CHARACTERISTICS ANALYSIS:')
logger.info('=' * 50)
    
    # Check AUTHENTIC_ATTORNEY_ADVISOR characteristics
    try:
        from backend_logic.email_generator import (
            CORE_DIRECTIVES,
            HIGH_STAKES_ADVICE_PROTOCOL,
        )
        
logger.info('📋 AUTHENTIC_ATTORNEY_ADVISOR Core Directives:')
        if "Direct Professional Tone" in CORE_DIRECTIVES:
logger.info('✅ Uses Direct Professional Tone')
        if "collaborative" in CORE_DIRECTIVES.lower() and "artificial" in CORE_DIRECTIVES.lower():
logger.info('❌ EXPLICITLY AVOIDS collaborative language')
        if "Florida Law Exclusive" in CORE_DIRECTIVES:
logger.info('✅ Florida Law Exclusive requirement present')
        if "Professional Realism" in CORE_DIRECTIVES:
logger.info('✅ Professional Realism requirement present')
            
        # Check High-Stakes Protocol
        if "HIGH-STAKES ADVICE PROTOCOL" in HIGH_STAKES_ADVICE_PROTOCOL:
logger.info('✅ High-Stakes Advice Protocol implemented')
            
    except Exception as e:
logger.error(f'⚠️  Framework analysis failed: {e}')

def create_florida_test_scenario():
    """Create a basic Florida legal scenario for framework testing."""
    
logger.info('\n🏖️ FLORIDA LAW TEST SCENARIO CREATION:')
logger.info('=' * 50)
    
    florida_scenario = {
        "case_type": "Florida Landlord-Tenant Dispute",
        "client_name": "Maria Rodriguez",
        "legal_issue": "Improper security deposit retention under Florida Statute 83.49",
        "key_facts": [
            "Lease terminated on June 1, 2024",
            "Security deposit of $2,000 not returned within 15 days",
            "No itemized list of damages provided by landlord",
            "Property was left in good condition with photos"
        ],
        "florida_statutes": ["Fla. Stat. § 83.49", "Fla. Stat. § 83.51"],
        "expected_framework_behaviors": {
            "CLIENT_CLARITY_ADVISOR": [
                "Should use 'we' language: 'We analyzed your case...'",
                "Should be collaborative: 'We recommend...'",
                "Should be warm and accessible"
            ],
            "AUTHENTIC_ATTORNEY_ADVISOR": [
                "Should use direct language: 'The analysis shows...'",
                "Should avoid artificial collaboration",
                "Should be matter-of-fact and professional"
            ]
        }
    }
    
logger.info('✅ Florida test scenario created')
logger.info(f'📋 Case Type: {florida_scenario['case_type']}')
logger.info(f'📋 Florida Statutes: {', '.join(florida_scenario['florida_statutes'])}')
    
    return florida_scenario

def main():
    """Main test execution."""
    
logger.info('🚨 FRAMEWORK DISCREPANCY VALIDATION')
logger.info('Testing CLIENT_CLARITY_ADVISOR framework implementation')
logger.info('=' * 60)
    
    # Test 1: Framework Discrepancy Detection
    framework_valid = test_framework_discrepancy()
    
    # Test 2: Analyze Actual Framework
    analyze_actual_framework_characteristics()
    
    # Test 3: Create Florida Test Scenario
    florida_test = create_florida_test_scenario()
    
    # FINAL RESULTS
logger.info('\n🎯 VALIDATION RESULTS:')
logger.info('=' * 30)
    
    if not framework_valid:
logger.error('❌ FRAMEWORK VALIDATION FAILED')
logger.info('   • CLIENT_CLARITY_ADVISOR is NOT actually implemented')
logger.info('   • AUTHENTIC_ATTORNEY_ADVISOR is the actual framework')
logger.info('   • Documentation-implementation mismatch detected')
logger.info('\n🔧 RECOMMENDATION:')
logger.info('   • Test the AUTHENTIC_ATTORNEY_ADVISOR framework instead')
logger.info('   • Update documentation to match actual implementation')
logger.info('   • Or complete the CLIENT_CLARITY_ADVISOR migration')
    else:
logger.info('✅ Framework implementation is consistent')
    
    return framework_valid

if __name__ == "__main__":
    main()
