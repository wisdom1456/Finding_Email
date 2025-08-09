#!/usr/bin/env python3
"""
Direct CSS Corruption Diagnostic Test
Tests HTML processing methods directly with existing corrupted HTML to capture H1 and H2 diagnostic logging.
"""
from __future__ import annotations

import json
import os
import sys


sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend_logic.email_generator import EmailGeneratorV2


def load_sample_corrupted_html():
    """Load the sample corrupted HTML file for testing."""
    sample_file = "test_data/Findings_Letter_Amber Bell  Erik Devlin-26.html"
    
    if not os.path.exists(sample_file):
        print(f"❌ Sample file not found: {sample_file}")
        return None
        
    try:
        with open(sample_file, encoding="utf-8") as f:
            content = f.read()
        print(f"✅ Loaded sample HTML: {len(content)} characters")
        return content
    except Exception as e:
        print(f"❌ Error loading sample file: {e}")
        return None

def test_css_corruption_direct():
    """Test HTML processing methods directly to capture CSS corruption diagnostic data."""
    print("🔍 Direct CSS Corruption Diagnostic Test")
    print("📊 Testing HTML processing methods with corrupted sample")
    print("=" * 70)
    
    # Load corrupted HTML sample
    print("📄 Loading corrupted HTML sample...")
    html_content = load_sample_corrupted_html()
    if not html_content:
        return False
    
    # Verify CSS corruption exists in the sample
    import re
    style_matches = re.findall(r"<style[^>]*>(.*?)</style>", html_content, re.DOTALL | re.IGNORECASE)
    if style_matches:
        css_content = style_matches[0]
        has_newlines = "\n" in css_content
        line_count = len(css_content.split("\n"))
        
        print("📊 Sample HTML CSS Analysis:")
        print(f"   • Style blocks found: {len(style_matches)}")
        print(f"   • CSS sample length: {len(css_content[:200])} chars (first 200)")
        print(f"   • Has newlines: {has_newlines}")
        print(f"   • Line count: {line_count}")
        print(f"   • CSS corruption present: {not has_newlines and line_count == 1}")
        
        if not has_newlines and line_count == 1:
            print("✅ Confirmed: CSS corruption exists in sample")
        else:
            print("⚠️  Sample may not show CSS corruption pattern")
    else:
        print("❌ No CSS style blocks found in sample")
        return False
    
    print("\n🔧 Initializing EmailGeneratorV2 for method testing...")
    try:
        # Create a minimal mock client for initialization
        class MockOpenAIClient:
            def __init__(self):
                pass
        
        generator = EmailGeneratorV2(MockOpenAIClient())
        print("✅ EmailGeneratorV2 initialized successfully")
        
        print("\n🚀 Testing H1: AdvancedNormalizationProcessor CSS logging...")
        print("📡 Monitoring for CSS_CORRUPTION_DEBUG (H1) log entries...")
        print("-" * 70)
        
        # Test H1: Call _apply_normalization_fixes directly
        try:
            h1_result = generator._apply_normalization_fixes(html_content)
            print(f"✅ H1 method completed: {len(h1_result)} characters output")
        except Exception as e:
            print(f"❌ H1 method failed: {e}")
            h1_result = html_content
        
        print("\n🚀 Testing H2: BeautifulSoup prettify CSS logging...")
        print("📡 Monitoring for CSS_CORRUPTION_DEBUG (H2) log entries...")
        print("-" * 70)
        
        # Test H2: Call _prettify_html_output directly
        try:
            h2_result = generator._prettify_html_output(h1_result)
            print(f"✅ H2 method completed: {len(h2_result)} characters output")
        except Exception as e:
            print(f"❌ H2 method failed: {e}")
            h2_result = h1_result
        
        print("\n📊 Final HTML CSS Analysis (after H1 + H2):")
        style_matches_final = re.findall(r"<style[^>]*>(.*?)</style>", h2_result, re.DOTALL | re.IGNORECASE)
        if style_matches_final:
            css_final = style_matches_final[0]
            has_newlines_final = "\n" in css_final
            line_count_final = len(css_final.split("\n"))
            
            print(f"   • Style blocks found: {len(style_matches_final)}")
            print(f"   • CSS sample length: {len(css_final[:200])} chars (first 200)")
            print(f"   • Has newlines: {has_newlines_final}")
            print(f"   • Line count: {line_count_final}")
            print(f"   • CSS corruption still present: {not has_newlines_final and line_count_final == 1}")
        else:
            print("❌ No CSS style blocks found in final output")
        
        return True
        
    except Exception as e:
        print(f"❌ Diagnostic test failed: {e}")
        return False

def main():
    """Main execution function."""
    print("🧪 Direct CSS Corruption Diagnostic Test")
    print("="*70)
    print("This test directly calls HTML processing methods to capture")
    print("CSS corruption diagnostic logging without OpenAI dependency.")
    print("")
    print("Key methods being tested:")
    print("  H1: _apply_normalization_fixes() - AdvancedNormalizationProcessor")
    print("  H2: _prettify_html_output() - BeautifulSoup prettify method")
    print("")
    
    success = test_css_corruption_direct()
    
    print("\n" + "="*70)
    print("🎯 DIRECT DIAGNOSTIC TEST SUMMARY")
    print("="*70)
    
    if success:
        print("✅ Direct diagnostic test completed successfully")
        print("📊 Review the CSS_CORRUPTION_DEBUG log entries above to identify:")
        print("   • Which method (H1 or H2) shows CSS corruption between entry/exit")
        print("   • Exact transformation where newlines are collapsed")
        print("   • Root cause component responsible for corruption")
        print("   • css_corruption_detected flag changes")
    else:
        print("❌ Direct diagnostic test failed to complete")
        print("🔧 Check error messages above for troubleshooting")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
