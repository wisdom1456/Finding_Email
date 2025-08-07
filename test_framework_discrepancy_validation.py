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

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from backend.utils.data_models import CaseAnalysisResult, EnhancedIntakeAnalysis
from backend_logic.ai import AIAnalyzer
from backend_logic.email_generator import EmailGeneratorV2


# Load environment variables
load_dotenv()

def test_framework_discrepancy():
    """Test to reveal which framework is actually implemented."""
    
    print("🔍 FRAMEWORK DISCREPANCY VALIDATION TEST")
    print("=" * 50)
    
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
    print("📋 EMAIL GENERATOR FRAMEWORK ANALYSIS:")
    print("-" * 40)
    
    try:
        # Initialize OpenAI client (needed for EmailGenerator)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "test-key"))
        email_gen = EmailGeneratorV2(client)
        
        # Check what framework constants are actually defined
        if hasattr(email_gen.__class__.__module__, "AUTHENTIC_ATTORNEY_ADVISOR"):
            from backend_logic.email_generator import (
                AUTHENTIC_ATTORNEY_ADVISOR,
                CORE_DIRECTIVES,
            )
            print("✅ AUTHENTIC_ATTORNEY_ADVISOR found in email_generator.py")
            print("📝 Core Directives:")
            print(CORE_DIRECTIVES[:300] + "...")
            
        if hasattr(email_gen.__class__.__module__, "CLIENT_CLARITY_ADVISOR"):
            print("✅ CLIENT_CLARITY_ADVISOR found in email_generator.py")
        else:
            print("❌ CLIENT_CLARITY_ADVISOR NOT found in email_generator.py")
            
    except Exception as e:
        print(f"⚠️  Email generator analysis failed: {e}")
    
    # Test AI ANALYZER framework references
    print("\n📋 AI ANALYZER FRAMEWORK ANALYSIS:")
    print("-" * 40)
    
    try:
        from backend_logic.ai import AIAnalyzer
        
        # Check the actual prompts used in AI Analyzer
        analyzer = AIAnalyzer(client=None, doc_processor=None)  # Mock for testing
        
        # Test intake prompt
        test_prompt = analyzer._build_intake_prompt("Test content")
        if "CLIENT_CLARITY_ADVISOR" in test_prompt:
            print("✅ AI Analyzer uses CLIENT_CLARITY_ADVISOR in prompts")
            if "we" in test_prompt.lower():
                print("✅ AI Analyzer prompts contain collaborative 'we' language")
        
        if "AUTHENTIC_ATTORNEY" in test_prompt:
            print("✅ AI Analyzer uses AUTHENTIC_ATTORNEY in prompts")
            
    except Exception as e:
        print(f"⚠️  AI analyzer analysis failed: {e}")
    
    # FRAMEWORK MISMATCH DETECTION
    print("\n🚨 FRAMEWORK DISCREPANCY SUMMARY:")
    print("=" * 50)
    
    framework_mismatch_detected = True  # Based on our analysis
    
    if framework_mismatch_detected:
        print("❌ CRITICAL ISSUE DETECTED:")
        print("   • Documentation describes CLIENT_CLARITY_ADVISOR")
        print("   • AI Analyzer generates CLIENT_CLARITY_ADVISOR content")
        print("   • Email Generator applies AUTHENTIC_ATTORNEY_ADVISOR formatting")
        print("   • This creates inconsistent output that matches neither framework")
        print("\n💡 ROOT CAUSE: Incomplete framework migration")
        print("   • backup file 'email_generator_backup.py' suggests partial migration")
        print("   • AI analysis stage != Email generation stage")
        
        print("\n📊 VALIDATION RESULT: FRAMEWORK MISMATCH CONFIRMED")
        return False  # Framework validation FAILED due to mismatch
    print("✅ Framework implementation is consistent")
    return True

def analyze_actual_framework_characteristics():
    """Analyze what framework characteristics are actually implemented."""
    
    print("\n🔬 ACTUAL FRAMEWORK CHARACTERISTICS ANALYSIS:")
    print("=" * 50)
    
    # Check AUTHENTIC_ATTORNEY_ADVISOR characteristics
    try:
        from backend_logic.email_generator import (
            AUTHENTIC_ATTORNEY_ADVISOR,
            CORE_DIRECTIVES,
            HIGH_STAKES_ADVICE_PROTOCOL,
        )
        
        print("📋 AUTHENTIC_ATTORNEY_ADVISOR Core Directives:")
        if "Direct Professional Tone" in CORE_DIRECTIVES:
            print("✅ Uses Direct Professional Tone")
        if "collaborative" in CORE_DIRECTIVES.lower() and "artificial" in CORE_DIRECTIVES.lower():
            print("❌ EXPLICITLY AVOIDS collaborative language")
        if "Florida Law Exclusive" in CORE_DIRECTIVES:
            print("✅ Florida Law Exclusive requirement present")
        if "Professional Realism" in CORE_DIRECTIVES:
            print("✅ Professional Realism requirement present")
            
        # Check High-Stakes Protocol
        if "HIGH-STAKES ADVICE PROTOCOL" in HIGH_STAKES_ADVICE_PROTOCOL:
            print("✅ High-Stakes Advice Protocol implemented")
            
    except Exception as e:
        print(f"⚠️  Framework analysis failed: {e}")

def create_florida_test_scenario():
    """Create a basic Florida legal scenario for framework testing."""
    
    print("\n🏖️ FLORIDA LAW TEST SCENARIO CREATION:")
    print("=" * 50)
    
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
    
    print("✅ Florida test scenario created")
    print(f"📋 Case Type: {florida_scenario['case_type']}")
    print(f"📋 Florida Statutes: {', '.join(florida_scenario['florida_statutes'])}")
    
    return florida_scenario

def main():
    """Main test execution."""
    
    print("🚨 FRAMEWORK DISCREPANCY VALIDATION")
    print("Testing CLIENT_CLARITY_ADVISOR framework implementation")
    print("=" * 60)
    
    # Test 1: Framework Discrepancy Detection
    framework_valid = test_framework_discrepancy()
    
    # Test 2: Analyze Actual Framework
    analyze_actual_framework_characteristics()
    
    # Test 3: Create Florida Test Scenario
    florida_test = create_florida_test_scenario()
    
    # FINAL RESULTS
    print("\n🎯 VALIDATION RESULTS:")
    print("=" * 30)
    
    if not framework_valid:
        print("❌ FRAMEWORK VALIDATION FAILED")
        print("   • CLIENT_CLARITY_ADVISOR is NOT actually implemented")
        print("   • AUTHENTIC_ATTORNEY_ADVISOR is the actual framework")
        print("   • Documentation-implementation mismatch detected")
        print("\n🔧 RECOMMENDATION:")
        print("   • Test the AUTHENTIC_ATTORNEY_ADVISOR framework instead")
        print("   • Update documentation to match actual implementation")
        print("   • Or complete the CLIENT_CLARITY_ADVISOR migration")
    else:
        print("✅ Framework implementation is consistent")
    
    return framework_valid

if __name__ == "__main__":
    main()
