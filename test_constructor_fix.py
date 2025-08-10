#!/usr/bin/env python3
"""
Test script to validate the PromptAndApiService constructor fix.
This script attempts to instantiate EmailGeneratorV2 which should no longer throw the TypeError.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")


# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_email_generator_initialization():
    """Test that EmailGeneratorV2 can be initialized without TypeError."""
    try:
        logger.info("🧪 Testing EmailGeneratorV2 initialization...")

        # Import the class that was causing the TypeError
        from backend_logic.email_generator import EmailGeneratorV2

        logger.info("✅ Import successful")

        # Create a mock client (the required parameter)
        class MockClient:
            pass

        mock_client = MockClient()

        # Try to initialize it (this previously caused the PromptAndApiService TypeError)
        email_gen = EmailGeneratorV2(client=mock_client)

        logger.info("✅ EmailGeneratorV2 initialization successful!")
        logger.error("🎉 PromptAndApiService TypeError has been resolved!")

        return True

    except TypeError as e:
        logger.error(f"❌ TypeError still exists: {e}")
        logger.debug("📍 Stack trace:")
        traceback.print_exc()
        return False

    except Exception as e:
        logger.error(f"⚠️  Other error occurred (but not the target TypeError): {e}")
        logger.debug("📍 Stack trace:")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🐛 TESTING PROMPTANDAPISERVICE CONSTRUCTOR FIX")
    logger.info("=" * 60)

    success = test_email_generator_initialization()

    logger.info("=" * 60)
    if success:
        logger.info("✅ TEST PASSED: Constructor fix is working!")
    else:
        logger.error("❌ TEST FAILED: Constructor issue persists")
    logger.info("=" * 60)

    sys.exit(0 if success else 1)
