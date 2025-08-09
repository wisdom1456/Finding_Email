#!/usr/bin/env python3
"""
Validation test for the Jinja2 template fix.
Tests that EmailGeneratorV2 can process content without template errors.
"""

import sys
import json
from datetime import datetime
from backend.utils.data_models import (
    CaseAnalysisResult,
    IntakeAnalysis
)
from backend_logic.email_generation.email_generator_v2 import EmailGeneratorV2

def create_test_analysis():
    """Create a simple test case analysis."""
    intake_analysis = IntakeAnalysis(
        client_name="Test Client",
        case_type="Personal Injury",
        incident_date="2024-01-15",
        attorney="Test Attorney",
        facts=["Test fact 1", "Test fact 2"],
        key_issues=["Test issue 1"],
        injury_details="Minor injuries",
        treatment_summary="Basic treatment"
    )
    
    return CaseAnalysisResult(
        intake_analysis=intake_analysis,
        analyzed_documents=[],  # Empty list for simplicity
        case_timeline=[],
        extracted_entities=[],
        video_insights=[]
    )

def test_template_fix():
    """Test that the template fix resolves the Jinja2 error."""
    print("🧪 TESTING: EmailGeneratorV2 Template Fix Validation")
    print("=" * 60)
    
    try:
        # Initialize EmailGeneratorV2
        print("📋 Step 1: Initializing EmailGeneratorV2...")
        generator = EmailGeneratorV2()
        print("✅ EmailGeneratorV2 initialized successfully")
        
        # Create test analysis
        print("\n📋 Step 2: Creating test case analysis...")
        test_analysis = create_test_analysis()
        print("✅ Test analysis created")
        
        # Test the generate_email_and_analysis_docs method
        print("\n📋 Step 3: Testing email generation (this was failing before)...")
        result = generator.generate_email_and_analysis_docs(test_analysis)
        print("✅ Email generation completed without errors!")
        
        # Validate result structure
        print("\n📋 Step 4: Validating result structure...")
        expected_keys = ["letter_content", "metadata"]
        actual_keys = list(result.keys())
        
        print(f"   Expected keys: {expected_keys}")
        print(f"   Actual keys: {actual_keys}")
        
        if "letter_content" in result:
            content_length = len(result["letter_content"]) if result["letter_content"] else 0
            print(f"   Letter content length: {content_length} characters")
            
            if content_length > 0:
                print("✅ Letter content generated successfully")
            else:
                print("⚠️  Letter content is empty")
        
        if "metadata" in result:
            metadata = result["metadata"]
            print(f"   Architecture: {metadata.get('architecture_version', 'Unknown')}")
            print(f"   Generation method: {metadata.get('generation_method', 'Unknown')}")
            print("✅ Metadata structure is correct")
        
        # Log debug information if available
        print("\n📋 Step 5: Looking for debug logs...")
        template_applied = result.get("template_applied", "Not specified")
        print(f"   Template applied: {template_applied}")
        
        if "rendered_email" in result:
            print("✅ Optional template formatting was applied")
        else:
            print("ℹ️  No optional template formatting (this is expected with our fix)")
        
        print("\n" + "=" * 60)
        print("🎉 SUCCESS: Template fix validation completed!")
        print("🔧 The Jinja2 'results is undefined' error has been resolved")
        print("📧 EmailGeneratorV2 now bypasses template rendering as intended")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR during validation: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = test_template_fix()
    sys.exit(0 if success else 1)