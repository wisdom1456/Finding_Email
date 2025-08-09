#!/usr/bin/env python3
"""
CSS Corruption Diagnostic Test
Executes email generation pipeline with H1 and H2 logging injection to identify root cause of CSS formatting corruption.
"""
from __future__ import annotations

import json
import os
import sys


sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.utils.data_models import CaseAnalysisResult, EnhancedIntakeAnalysis
from backend_logic.email_generator import EmailGeneratorV2


def run_css_corruption_diagnostic():
    """Execute email generation with CSS corruption logging enabled."""
    print("🔍 Starting CSS Corruption Diagnostic Test")
    print("📊 Diagnostic logs will be prefixed with: CSS_CORRUPTION_DEBUG")
    print("=" * 70)
    
    # Create test parameters for a typical findings letter
    test_params = {
        "client_name": "Test Client",
        "client_email": "test@example.com",
        "attorney_name": "Test Attorney",
        "attorney_email": "attorney@example.com",
        "report_type": "findings_letter",
        "case_details": {
            "case_number": "CSS-DEBUG-001",
            "case_title": "CSS Corruption Diagnostic Test Case",
            "investigation_summary": "Testing CSS corruption diagnostic logging to identify root cause"
        }
    }
    
    print("📋 Test Parameters:")
    print(f"   • Report Type: {test_params['report_type']}")
    print(f"   • Case Number: {test_params['case_details']['case_number']}")
    print(f"   • Case Title: {test_params['case_details']['case_title']}")
    print("")
    
    # Initialize generator - using minimal mock for this diagnostic test
    print("🔧 Initializing EmailGeneratorV2...")
    try:
        # Create a simple mock client that won't actually call OpenAI
        class MockOpenAIClient:
            def __init__(self):
                pass
        
        generator = EmailGeneratorV2(MockOpenAIClient())
        print("✅ EmailGeneratorV2 initialized successfully")
        
        # Create a mock analysis object with proper structure for EnhancedIntakeAnalysis
        mock_intake = EnhancedIntakeAnalysis(
            client_name=test_params["client_name"],
            attorney_name=test_params["attorney_name"],
            case_summary=test_params["case_details"]["investigation_summary"],
            case_type="Contract Dispute",
            urgency_level="Standard",
            client_priorities=["Diagnose CSS corruption", "Fix rendering issues"],
            desired_outcomes=["Identify root cause", "Implement fix"],
            key_facts=["CSS corruption in email output", "Newlines collapsed into single line"],
            parties_involved=[{"name": test_params["client_name"], "role": "Client"}],
            financial_impact="Potential impact to legal document rendering quality",
            legal_claims=["CSS diagnostic test case"]
        )
        
        mock_analysis = CaseAnalysisResult(
            intake_analysis=mock_intake
        )
        
        # Run the email generation pipeline
        print("\n🚀 Executing email generation pipeline with CSS diagnostic logging...")
        print("📡 Monitoring for CSS_CORRUPTION_DEBUG log entries...")
        print("-" * 70)
        
        result = generator.generate_email_and_analysis_docs(mock_analysis)
        
        print("-" * 70)
        print("✅ Email generation pipeline completed successfully")
        
        # Extract and analyze HTML output
        html_content = result.get("html_content", "")
        if html_content:
            print(f"📄 HTML output generated: {len(html_content)} characters")
            
            # Check for CSS corruption in the final output
            import re
            style_matches = re.findall(r"<style[^>]*>(.*?)</style>", html_content, re.DOTALL | re.IGNORECASE)
            if style_matches:
                css_content = style_matches[0]
                has_newlines = "\n" in css_content
                line_count = len(css_content.split("\n"))
                
                print("📊 Final HTML CSS Analysis:")
                print(f"   • Style blocks found: {len(style_matches)}")
                print(f"   • CSS sample length: {len(css_content[:200])} chars (first 200)")
                print(f"   • Has newlines: {has_newlines}")
                print(f"   • Line count: {line_count}")
                print(f"   • CSS corruption detected: {not has_newlines and line_count == 1}")
                
                if not has_newlines and line_count == 1:
                    print("⚠️  CSS CORRUPTION DETECTED in final output!")
                    print("📝 CSS appears to be collapsed into a single line")
                else:
                    print("✅ CSS appears to be properly formatted in final output")
            else:
                print("❓ No CSS style blocks found in final output")
        else:
            print("❌ No HTML content generated")
            
        return True
        
    except Exception as e:
        print(f"❌ Email generation failed with error: {e}")
        print(f"📍 Error type: {type(e).__name__}")
        return False

def main():
    """Main execution function."""
    print("🧪 CSS Corruption Diagnostic Test")
    print("="*70)
    print("This test executes the email generation pipeline with diagnostic")
    print("logging to identify which component is causing CSS corruption.")
    print("")
    print("Key hypotheses being tested:")
    print("  H1: AdvancedNormalizationProcessor corrupting CSS")
    print("  H2: BeautifulSoup prettify method corrupting CSS")
    print("")
    
    success = run_css_corruption_diagnostic()
    
    print("\n" + "="*70)
    print("🎯 DIAGNOSTIC TEST SUMMARY")
    print("="*70)
    
    if success:
        print("✅ Diagnostic test completed successfully")
        print("📊 Review the CSS_CORRUPTION_DEBUG log entries above to identify:")
        print("   • Which hypothesis shows CSS corruption (entry vs exit)")
        print("   • Exact point where newlines are collapsed")
        print("   • Root cause component responsible for corruption")
    else:
        print("❌ Diagnostic test failed to complete")
        print("🔧 Check error messages above for troubleshooting")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
