#!/usr/bin/env python3
"""
Test script to verify structured logging implementation.
This script demonstrates the JSON-formatted logging output.
"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend_logic.utils.logging_config import setup_logging, get_module_logger

def test_structured_logging():
    """Test the structured logging implementation."""
    
    # Setup logging
    setup_logging()
    
    # Get logger for this module
    logger = get_module_logger(__name__)
    
logger.info('=== Testing Structured Logging Implementation ===\n')
logger.info('The following logs will be in JSON format:\n')
    
    # Test different log levels
    logger.debug("Debug message for testing", extra={"test_type": "debug", "data": {"key": "value"}})
    
    logger.info("Application started successfully", extra={
        "session_id": "test-session-123",
        "user_action": "startup",
        "performance": {"startup_time_ms": 1250}
    })
    
    logger.warning("Configuration warning detected", extra={
        "config_file": "universal_legal_config.yaml",
        "warning_type": "missing_optional_field",
        "field": "custom_citation_filter"
    })
    
    # Test error logging with exception details
    try:
        # Simulate an error
        result = 1 / 0
    except ZeroDivisionError as e:
        logger.error("Mathematical operation failed", extra={
            "operation": "division",
            "error": str(e),
            "error_type": type(e).__name__,
            "context": {"numerator": 1, "denominator": 0}
        })
    
    # Test service-specific logging
    service_logger = get_module_logger("backend_logic.email_generation.services.test_service")
    service_logger.info("Document processing completed", extra={
        "document_id": "doc-456",
        "processing_time_ms": 2340,
        "pages_processed": 15,
        "citations_found": 23
    })
    
logger.info('\n=== Structured Logging Test Complete ===')
logger.info('All logs above are in machine-readable JSON format for production observability.')

if __name__ == "__main__":
    test_structured_logging()