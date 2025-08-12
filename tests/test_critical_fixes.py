#!/usr/bin/env python3
"""Targeted validation tests for the three critical error fixes.
"""
from __future__ import annotations

import os
import sys
import traceback
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_cost_session_id_fix():
    """Test Priority 1: cost_session_id initialization fix in app.py"""
    print("🧪 Testing Priority 1: cost_session_id initialization...")

    try:
        # Import the session state initialization function
        import streamlit as st

        from app import initialize_session_state

        # Mock streamlit session state
        class MockSessionState:
            def __init__(self):
                self._state = {}

            def __contains__(self, key):
                return key in self._state

            def __getitem__(self, key):
                return self._state[key]

            def __setitem__(self, key, value):
                self._state[key] = value

            def get(self, key, default=None):
                return self._state.get(key, default)

        # Replace st.session_state temporarily
        original_session_state = getattr(st, "session_state", None)
        st.session_state = MockSessionState()

        # Test the initialization
        initialize_session_state()

        # Verify cost_session_id is now a proper UUID, not None
        cost_session_id = st.session_state.get("cost_session_id")

        assert cost_session_id is not None, "cost_session_id should not be None"
        assert isinstance(cost_session_id, str), "cost_session_id should be a string"

        # Verify it's a valid UUID format
        try:
            uuid.UUID(cost_session_id)
        except ValueError:
            raise AssertionError("cost_session_id should be a valid UUID")

        print("✅ FIXED: cost_session_id now properly initialized as UUID")
        print(f"   Generated cost_session_id: {cost_session_id}")

        # Restore original session state
        if original_session_state:
            st.session_state = original_session_state

        return True

    except Exception as e:
        print(f"❌ FAILED: cost_session_id test failed: {e}")
        traceback.print_exc()
        return False


def test_structured_logger_exception_method():
    """Test Priority 2: StructuredLogger exception method fix"""
    print("\n🧪 Testing Priority 2: StructuredLogger exception method...")

    try:
        from utils.structured_logger import StructuredLogger

        # Create a logger instance
        logger = StructuredLogger("test_logger", "INFO")

        # Verify the exception method exists
        assert hasattr(logger, "exception"), "StructuredLogger should have exception method"
        assert callable(logger.exception), "exception method should be callable"

        # Test calling the exception method
        try:
            # Create a test exception context
            raise ValueError("Test exception for logging")
        except ValueError:
            # This should work without AttributeError
            logger.exception("Test exception message")

        print("✅ FIXED: StructuredLogger.exception() method now available")
        print("   Method signature: exception(message: str, **kwargs)")

        return True

    except Exception as e:
        print(f"❌ FAILED: StructuredLogger exception method test failed: {e}")
        traceback.print_exc()
        return False


def test_ai_analyzer_error_handling():
    """Test Priority 3: AI analyzer error handling (verify it's already fixed)"""
    print("\n🧪 Testing Priority 3: AI analyzer error handling...")

    try:
        from legal_portal.services.ai_analyzer import analyze_document, establish_context

        # Test with empty input to trigger error condition
        print("   Testing establish_context with empty input...")
        error_context = establish_context("")  # This should trigger error but not crash

        # Verify it handles the error gracefully
        assert isinstance(error_context, dict), "Should return dict even on error"
        assert error_context.get("ai_analysis_failed") == True, "Should indicate AI analysis failed"

        print("   Testing analyze_document with empty input...")
        error_analysis = analyze_document("", {"case_type": "test"})

        # Verify it handles the error gracefully
        assert isinstance(error_analysis, dict), "Should return dict even on error"
        assert error_analysis.get("ai_analysis_failed") == True, "Should indicate AI analysis failed"

        print("✅ CONFIRMED: AI analyzer error handling already fixed")
        print("   Uses dict key access instead of attribute access for error objects")

        return True

    except AttributeError as e:
        if "'dict' object has no attribute 'error'" in str(e):
            print(f"❌ FAILED: AI analyzer still has the AttributeError bug: {e}")
            return False
        raise
    except Exception as e:
        print(f"❌ FAILED: AI analyzer test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all validation tests"""
    print("🔧 CRITICAL ERROR FIXES VALIDATION")
    print("=" * 50)

    tests = [
        test_cost_session_id_fix,
        test_structured_logger_exception_method,
        test_ai_analyzer_error_handling,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            results.append(False)

    print("\n" + "=" * 50)
    print("📊 VALIDATION SUMMARY")
    print("=" * 50)

    passed = sum(results)
    total = len(results)

    print(f"Tests Passed: {passed}/{total}")

    if passed == total:
        print("🎉 ALL CRITICAL FIXES VALIDATED SUCCESSFULLY!")
        print("   The Findings Email workflow should now work without crashes.")
    else:
        print("⚠️  Some fixes need additional work.")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
