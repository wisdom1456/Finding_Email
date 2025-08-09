#!/usr/bin/env python3
"""
CSS Fix Validation Test
Tests the CSS corruption fix against the corrupted HTML sample
"""
from __future__ import annotations

import os
import re
import sys


# Add the backend logic directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend_logic"))

from email_generator import EmailGeneratorV2


def extract_css_from_html(html_content):
    """Extract CSS content from HTML for analysis."""
    style_match = re.search(r"<style[^>]*>(.*?)</style>", html_content, re.DOTALL | re.IGNORECASE)
    if style_match:
        return style_match.group(1).strip()
    return None

def analyze_css_formatting(css_content):
    """Analyze CSS formatting characteristics."""
    if not css_content:
        return {
            "line_count": 0,
            "has_newlines": False,
            "has_proper_spacing": False,
            "is_corrupted": True
        }
    
    lines = css_content.split("\n")
    return {
        "line_count": len([line for line in lines if line.strip()]),
        "has_newlines": "\n" in css_content,
        "has_proper_spacing": any("    " in line or "\t" in line for line in lines),
        "is_corrupted": len(lines) <= 1 and len(css_content) > 50,
        "total_length": len(css_content)
    }

def main():
    print("=== CSS Fix Validation Test ===")
    
    # Read the corrupted HTML sample
    try:
        with open("test_data/Findings_Letter_Amber Bell  Erik Devlin-26.html", encoding="utf-8") as f:
            corrupted_html = f.read()
        print("✓ Successfully loaded corrupted HTML sample")
    except Exception as e:
        print(f"✗ Failed to load corrupted HTML sample: {e}")
        return
    
    # Extract and analyze original corrupted CSS
    original_css = extract_css_from_html(corrupted_html)
    original_analysis = analyze_css_formatting(original_css)
    
    print("\n--- Original CSS Analysis ---")
    print(f"Line count: {original_analysis['line_count']}")
    print(f"Has newlines: {original_analysis['has_newlines']}")
    print(f"Has proper spacing: {original_analysis['has_proper_spacing']}")
    print(f"Is corrupted: {original_analysis['is_corrupted']}")
    print(f"Total length: {original_analysis['total_length']}")
    
    # Show a sample of the corrupted CSS
    if original_css:
        sample = original_css[:200] + "..." if len(original_css) > 200 else original_css
        print(f"CSS Sample: {sample!r}")
    
    # Create EmailGeneratorV2 instance and test the fix
    try:
        generator = EmailGeneratorV2()
        
        # Test the AdvancedNormalizationProcessor with the corrupted HTML
        # We'll directly test the processor's methods
        processor_class = None
        
        # Get the AdvancedNormalizationProcessor class from the generator
        for attr_name in dir(generator):
            attr = getattr(generator, attr_name)
            if hasattr(attr, "__name__") and "AdvancedNormalizationProcessor" in str(attr):
                processor_class = attr
                break
        
        if not processor_class:
            # Try to find it in the _apply_normalization_fixes method
            print("Creating processor instance through normalization fixes...")
            # We'll test by calling the actual method that uses the processor
            result = generator._apply_normalization_fixes(corrupted_html)
        else:
            # Create processor instance and test
            processor = processor_class()
            result = processor.process_html_content(corrupted_html)
        
        print("✓ Successfully processed HTML with CSS fix")
        
    except Exception as e:
        print(f"✗ Failed to process HTML: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Extract and analyze processed CSS
    processed_css = extract_css_from_html(result)
    processed_analysis = analyze_css_formatting(processed_css)
    
    print("\n--- Processed CSS Analysis ---")
    print(f"Line count: {processed_analysis['line_count']}")
    print(f"Has newlines: {processed_analysis['has_newlines']}")
    print(f"Has proper spacing: {processed_analysis['has_proper_spacing']}")
    print(f"Is corrupted: {processed_analysis['is_corrupted']}")
    print(f"Total length: {processed_analysis['total_length']}")
    
    # Show a sample of the processed CSS
    if processed_css:
        sample = processed_css[:200] + "..." if len(processed_css) > 200 else processed_css
        print(f"CSS Sample: {sample!r}")
    
    # Validation results
    print("\n=== FIX VALIDATION RESULTS ===")
    
    # Check if the fix worked
    fix_successful = (
        processed_analysis["has_newlines"] and
        not processed_analysis["is_corrupted"] and
        processed_analysis["line_count"] > 1
    )
    
    if fix_successful:
        print("✓ CSS CORRUPTION FIX SUCCESSFUL!")
        print("  - CSS formatting preserved")
        print("  - Newlines maintained")
        print("  - Multi-line structure restored")
    else:
        print("✗ CSS CORRUPTION FIX FAILED")
        print("  - CSS formatting may still be corrupted")
        
    # Additional checks
    if original_analysis["is_corrupted"] and not processed_analysis["is_corrupted"]:
        print("✓ Corruption successfully resolved")
    elif not original_analysis["is_corrupted"]:
        print("ℹ Original CSS was not corrupted")
    else:
        print("✗ Corruption persists")
    
    # Save the processed result for manual inspection
    try:
        with open("test_data/processed_fixed_sample.html", "w", encoding="utf-8") as f:
            f.write(result)
        print("✓ Processed result saved to test_data/processed_fixed_sample.html")
    except Exception as e:
        print(f"⚠ Could not save processed result: {e}")

if __name__ == "__main__":
    main()
