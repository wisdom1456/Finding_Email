#!/usr/bin/env python3
"""
Framework Validation Test
Validates the TestOrchestrator with the Erik Devlin case.
"""

from __future__ import annotations

import pytest

from backend.tests.utils.test_framework import TestOrchestrator
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



@pytest.mark.framework
def test_devlin_case_with_framework():
    """
    Runs the Erik Devlin comprehensive test using the new reusable framework.
    This test ensures that the abstraction was successful and that the framework
    is backward-compatible with the original test case.
    """
logger.info('🚀 Starting framework validation with Devlin case...')

    # Path to the configuration file for the Devlin case
    config_path = "backend/tests/test_results/devlin/config.yaml"

    # Initialize the orchestrator with the specific test config
    orchestrator = TestOrchestrator(config_path)

    # Execute the full test
    orchestrator.run_test()

logger.info('✅ Framework validation test completed.')


if __name__ == "__main__":
    pytest.main([__file__])
