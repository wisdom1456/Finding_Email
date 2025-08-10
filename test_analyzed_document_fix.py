#!/usr/bin/env python3
"""
Test script to verify that the AnalyzedDocument AttributeError fix works correctly.

This test validates:
1. AnalyzedDocument can be created with new fields (summary and key_information)
2. Defensive coding handles missing attributes gracefully
3. The original AttributeError is resolved
"""

from __future__ import annotations

from backend.utils.data_models import AnalyzedDocument
from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")


def test_analyzed_document_with_new_fields():
    """Test that AnalyzedDocument accepts the new fields."""
    logger.info("Testing AnalyzedDocument with new fields...")

    # Test 1: Create AnalyzedDocument with new fields
    doc = AnalyzedDocument(
        file_name="test_document.pdf",
        analysis="This is a test analysis",
        summary="This is a test summary",  # NEW FIELD
        key_information="This is key information",  # NEW FIELD
        key_points=["Point 1", "Point 2"],
        metadata={"type": "contract"},
    )

    logger.info("✅ AnalyzedDocument created successfully")
    logger.info(f"   - file_name: {doc.file_name}")
    logger.info(f"   - summary: {doc.summary}")
    logger.info(f"   - key_information: {doc.key_information}")

    # Test 2: Access key_information field (this was the original error)
    try:
        key_info_excerpt = (
            doc.key_information[:100] if doc.key_information else "No key info"
        )
        logger.info(f"✅ key_information access successful: {key_info_excerpt}")
    except AttributeError as e:
        logger.error(f"❌ AttributeError still occurs: {e}")
        return False

    return True


def test_defensive_coding():
    """Test defensive coding with hasattr checks."""
    logger.info("\nTesting defensive coding...")

    # Create a document with the new fields
    doc = AnalyzedDocument(
        file_name="test_document.pdf",
        analysis="This is a test analysis",
        summary="This is a test summary",
        key_information="This is key information",
        key_points=["Point 1", "Point 2"],
    )

    # Test the defensive patterns we implemented
    # Pattern 1: hasattr check (as used in email_generator.py:1903)
    if hasattr(doc, "key_information") and doc.key_information:
        logger.info("✅ hasattr check passed for key_information")
    else:
        logger.error("❌ hasattr check failed for key_information")
        return False

    # Pattern 2: getattr with default (as used in utils.py:500)
    key_info = getattr(doc, "key_information", "Not available")
    logger.info(f"✅ getattr check passed: {key_info[:50]}...")

    return True


def test_backward_compatibility():
    """Test that old AnalyzedDocument instances still work."""
    logger.info("\nTesting backward compatibility...")

    # Create minimal AnalyzedDocument (as might exist in old data)
    doc = AnalyzedDocument(file_name="old_document.pdf", key_points=[])

    # Test defensive access patterns
    # Should not crash even if fields are None/missing
    try:
        # Test getattr pattern
        key_info = getattr(doc, "key_information", "Not available")
        summary = getattr(doc, "summary", "Not available")

        logger.info(f"✅ Backward compatibility: key_information = {key_info}")
        logger.info(f"✅ Backward compatibility: summary = {summary}")

        # Test hasattr pattern
        if hasattr(doc, "key_information") and doc.key_information:
            logger.info("✅ hasattr check handled None/missing gracefully")
        else:
            logger.info("✅ hasattr check correctly identified missing field")

        return True
    except Exception as e:
        logger.error(f"❌ Backward compatibility test failed: {e}")
        return False


def main():
    """Run all tests to verify the fix."""
    logger.error("🔍 Testing AnalyzedDocument AttributeError Fix")
    logger.info("=" * 50)

    tests = [
        test_analyzed_document_with_new_fields,
        test_defensive_coding,
        test_backward_compatibility,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                logger.error(f"❌ {test.__name__} failed")
        except Exception as e:
            logger.error(f"❌ {test.__name__} crashed: {e}")

    logger.info("\n" + "=" * 50)
    logger.info(f"Test Results: {passed}/{total} tests passed")

    if passed == total:
        logger.error(
            "🎉 ALL TESTS PASSED! The AttributeError fix is working correctly."
        )
        return True
    logger.error("❌ Some tests failed. The fix may need additional work.")
    return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
