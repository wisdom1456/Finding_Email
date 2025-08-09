#!/usr/bin/env python3
"""
Diagnostic test to trigger the EmailGenerator and capture debug logs.
This test will help identify where the 'NoneType' object error occurs.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime


# Add the backend directories to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend_logic"))

from openai import OpenAI

from backend.utils.data_models import (
    AnalyzedDocument,
    CaseAnalysisResult,
    EnhancedIntakeAnalysis,
)
from backend_logic.email_generator import EmailGeneratorV2


def create_minimal_test_case():
    """Create a minimal test case to trigger the email generator."""
    print("🧪 Creating minimal test case for EmailGenerator debugging...")
    
    # Create minimal intake analysis
    intake_analysis = EnhancedIntakeAnalysis(
        client_name="Test Client",
        attorney_name="Test Attorney",
        case_summary="Test case for debugging email generation",
        case_type="Contract Dispute",
        urgency_level="Standard",
        financial_impact="Moderate financial exposure, approximately $50,000 in damages"
    )
    
    # Create minimal analyzed document
    analyzed_doc = AnalyzedDocument(
        file_name="test_document.pdf",
        summary="Test document summary",
        key_information="Test key information from document"
    )
    
    # Create minimal case analysis result
    case_analysis = CaseAnalysisResult(
        intake_analysis=intake_analysis,
        analyzed_documents=[analyzed_doc],
        legal_assessment=None,  # This might trigger our issue
        demand_letter_evaluation=None,  # This might trigger our issue
        transcripted_media=[],
        video_insights=[]
    )
    
    return case_analysis

def test_email_generator_with_debug():
    """Test the EmailGenerator to capture diagnostic logs."""
    print("🔍 Testing EmailGenerator with diagnostic logging...")
    print("=" * 60)
    
    try:
        # Create a mock OpenAI client (we'll see if config loading works first)
        print("Step 1: Creating OpenAI client...")
        client = OpenAI(api_key="test-key")  # Mock key for testing
        
        print("Step 2: Initializing EmailGeneratorV2...")
        # This should trigger our config loading diagnostic logs
        email_generator = EmailGeneratorV2(client=client)
        
        print("Step 3: Creating test case data...")
        case_analysis = create_minimal_test_case()
        
        print("Step 4: Triggering email generation (this should show our diagnostic logs)...")
        # This should trigger both config loading and OpenAI API diagnostic logs
        result = email_generator.generate_email_with_debug(case_analysis)
        
        print("Step 5: Results summary...")
        print("✅ Email generation completed without fatal errors")
        print(f"📧 Letter fields populated: {len([f for f in result.letter.__fields__ if getattr(result.letter, f)])}")
        print(f"🐛 Debug info available: {result.debug_info is not None}")
        
        if result.debug_info and "errors" in result.debug_info:
            print(f"❌ Errors detected: {len(result.debug_info['errors'])}")
            for error in result.debug_info["errors"]:
                print(f"   - {error}")
        
        return True
        
    except Exception as e:
        print(f"❌ EmailGenerator test failed with exception: {e}")
        print(f"📍 Exception type: {type(e).__name__}")
        import traceback
        print("📋 Full traceback:")
        traceback.print_exc()
        return False

def main():
    """Main test function."""
    print("🧪 EMAIL GENERATOR DIAGNOSTIC TEST")
    print("=" * 60)
    print(f"🕐 Test started at: {datetime.now().isoformat()}")
    print("📋 This test will capture diagnostic logs for both hypotheses:")
    print("   1. OpenAI API Response Issues")
    print("   2. Configuration Loading Failure")
    print("=" * 60)
    
    success = test_email_generator_with_debug()
    
    print("=" * 60)
    print(f"🕐 Test completed at: {datetime.now().isoformat()}")
    print(f"✅ Test result: {'PASSED' if success else 'FAILED'}")
    print("📊 Check the output above for EMAIL_GENERATOR_DEBUG logs")
    print("=" * 60)
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
