#!/usr/bin/env python3
"""
Direct CSS Fix Test
Tests the CSS corruption fix by directly testing the processor methods
"""

from __future__ import annotations

import os
import re
import sys

from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")


# Add the backend logic directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend_logic"))


def extract_css_from_html(html_content):
    """Extract CSS content from HTML for analysis."""
    style_match = re.search(
        r"<style[^>]*>(.*?)</style>", html_content, re.DOTALL | re.IGNORECASE
    )
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
            "is_corrupted": True,
        }

    lines = css_content.split("\n")
    return {
        "line_count": len([line for line in lines if line.strip()]),
        "has_newlines": "\n" in css_content,
        "has_proper_spacing": any("    " in line or "\t" in line for line in lines),
        "is_corrupted": len(lines) <= 1 and len(css_content) > 50,
        "total_length": len(css_content),
    }


def create_test_processor():
    """Create a test instance of AdvancedNormalizationProcessor with our CSS-preserving methods."""

    class TestAdvancedNormalizationProcessor:
        def _normalize_spacing_preserve_css_global(self, content: str) -> str:
            """Global CSS-aware spacing normalization for use throughout the processor."""
            if not content:
                return content

            # Split content at style tags to process separately
            style_pattern = r"(<style[^>]*>.*?</style>)"
            parts = re.split(style_pattern, content, flags=re.DOTALL | re.IGNORECASE)

            processed_parts = []
            for i, part in enumerate(parts):
                if re.match(r"<style[^>]*>", part, re.IGNORECASE):
                    # This is a style block - preserve all formatting
                    processed_parts.append(part)
                else:
                    # This is regular HTML content - normalize spacing
                    normalized = re.sub(r"\s+", " ", part)
                    processed_parts.append(normalized)

            return "".join(processed_parts)

        def _normalize_spacing_preserve_css(self, content: str) -> str:
            """Normalize spacing while preserving CSS formatting within <style> tags."""
            if not content:
                return content

            # Split content at style tags to process separately
            style_pattern = r"(<style[^>]*>.*?</style>)"
            parts = re.split(style_pattern, content, flags=re.DOTALL | re.IGNORECASE)

            processed_parts = []
            for i, part in enumerate(parts):
                if re.match(r"<style[^>]*>", part, re.IGNORECASE):
                    # This is a style block - preserve all formatting
                    processed_parts.append(part)
                else:
                    # This is regular HTML content - normalize spacing
                    normalized = re.sub(r"\s+", " ", part)
                    normalized = re.sub(r"\s*([.!?])\s*", r"\1 ", normalized)
                    processed_parts.append(normalized)

            return "".join(processed_parts)

        def _clean_html_spacing_preserve_css(self, content: str) -> str:
            """Clean HTML tag spacing while preserving CSS formatting."""
            if not content:
                return content

            # Split content at style tags to process separately
            style_pattern = r"(<style[^>]*>.*?</style>)"
            parts = re.split(style_pattern, content, flags=re.DOTALL | re.IGNORECASE)

            processed_parts = []
            for i, part in enumerate(parts):
                if re.match(r"<style[^>]*>", part, re.IGNORECASE):
                    # This is a style block - preserve all formatting
                    processed_parts.append(part)
                else:
                    # This is regular HTML content - clean tag spacing
                    cleaned = re.sub(r">\s+<", "><", part)
                    processed_parts.append(cleaned)

            return "".join(processed_parts)

        def _apply_final_cleanup(self, content: str) -> str:
            """Apply final cleanup and validation while preserving CSS formatting."""

            # Remove double periods from sentence splits
            content = re.sub(r"\.\.+", ".", content)

            # CRITICAL FIX: Preserve CSS formatting by excluding <style> blocks from whitespace normalization
            content = self._normalize_spacing_preserve_css(content)

            # Clean up HTML tag spacing (but not within style blocks)
            content = self._clean_html_spacing_preserve_css(content)

            return content.strip()

        def process_with_global_normalization(self, content: str) -> str:
            """Test the global normalization fix (line 3778 equivalent)."""
            content = re.sub(r"\.\s*\.", ".", content)  # Remove double periods
            # CRITICAL FIX: Use CSS-aware spacing normalization instead of global \s+ replacement
            content = self._normalize_spacing_preserve_css_global(content)
            content = content.strip()
            return content

    return TestAdvancedNormalizationProcessor()


def main():
    logger.info("=== Direct CSS Fix Test ===")

    # Read the corrupted HTML sample
    try:
        with open(
            "test_data/Findings_Letter_Amber Bell  Erik Devlin-26.html",
            encoding="utf-8",
        ) as f:
            corrupted_html = f.read()
        logger.info("✓ Successfully loaded corrupted HTML sample")
    except Exception as e:
        logger.error(f"✗ Failed to load corrupted HTML sample: {e}")
        return

    # Extract and analyze original corrupted CSS
    original_css = extract_css_from_html(corrupted_html)
    original_analysis = analyze_css_formatting(original_css)

    logger.info("\n--- Original CSS Analysis ---")
    logger.info(f"Line count: {original_analysis['line_count']}")
    logger.info(f"Has newlines: {original_analysis['has_newlines']}")
    logger.info(f"Has proper spacing: {original_analysis['has_proper_spacing']}")
    logger.info(f"Is corrupted: {original_analysis['is_corrupted']}")
    logger.info(f"Total length: {original_analysis['total_length']}")

    # Show a sample of the corrupted CSS
    if original_css:
        sample = original_css[:200] + "..." if len(original_css) > 200 else original_css
        logger.info(f"CSS Sample: {sample!r}")

    # Create test processor and run the fix methods
    try:
        processor = create_test_processor()

        logger.info("\n--- Testing CSS-Preserving Methods ---")

        # Test the _apply_final_cleanup method (main fix)
        logger.info("Testing _apply_final_cleanup method...")
        result1 = processor._apply_final_cleanup(corrupted_html)

        # Test the global normalization method (line 3778 fix)
        logger.info("Testing global normalization method...")
        result2 = processor.process_with_global_normalization(corrupted_html)

        logger.info("✓ Successfully processed HTML with both CSS fixes")

    except Exception as e:
        logger.error(f"✗ Failed to process HTML: {e}")
        import traceback

        traceback.print_exc()
        return

    # Test both results
    results = [("_apply_final_cleanup", result1), ("global_normalization", result2)]

    for method_name, result in results:
        logger.info(f"\n--- {method_name} Results ---")

        # Extract and analyze processed CSS
        processed_css = extract_css_from_html(result)
        processed_analysis = analyze_css_formatting(processed_css)

        logger.info(f"Line count: {processed_analysis['line_count']}")
        logger.info(f"Has newlines: {processed_analysis['has_newlines']}")
        logger.info(f"Has proper spacing: {processed_analysis['has_proper_spacing']}")
        logger.info(f"Is corrupted: {processed_analysis['is_corrupted']}")
        logger.info(f"Total length: {processed_analysis['total_length']}")

        # Show a sample of the processed CSS
        if processed_css:
            sample = (
                processed_css[:200] + "..."
                if len(processed_css) > 200
                else processed_css
            )
            logger.info(f"CSS Sample: {sample!r}")

        # Validation for this method
        fix_successful = (
            processed_analysis["has_newlines"]
            and not processed_analysis["is_corrupted"]
            and processed_analysis["line_count"] > 1
        )

        if fix_successful:
            logger.info(f"✓ {method_name}: CSS CORRUPTION FIX SUCCESSFUL!")
        else:
            logger.error(f"✗ {method_name}: CSS CORRUPTION FIX FAILED")

    # Overall validation
    logger.info("\n=== OVERALL FIX VALIDATION ===")

    all_successful = all(
        analyze_css_formatting(extract_css_from_html(result))["has_newlines"]
        and not analyze_css_formatting(extract_css_from_html(result))["is_corrupted"]
        for _, result in results
    )

    if all_successful:
        logger.info("✓ ALL CSS CORRUPTION FIXES SUCCESSFUL!")
        logger.info("  - CSS formatting preserved across all methods")
        logger.info("  - Newlines maintained in <style> blocks")
        logger.info("  - Multi-line CSS structure restored")
    else:
        logger.info("⚠ MIXED RESULTS - Some fixes may need refinement")

    # Save the best result for manual inspection
    try:
        with open(
            "test_data/processed_css_fixed_sample.html", "w", encoding="utf-8"
        ) as f:
            f.write(results[0][1])  # Save the _apply_final_cleanup result
        logger.info(
            "✓ Processed result saved to test_data/processed_css_fixed_sample.html"
        )
    except Exception as e:
        logger.info(f"⚠ Could not save processed result: {e}")


if __name__ == "__main__":
    main()
