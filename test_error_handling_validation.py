#!/usr/bin/env python3
"""
Performance and Error Handling Validation Test Suite
Tests the robustness, logging, and performance of the consolidated Legal Document Analysis Portal
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import traceback
from typing import Any
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')


# Import our new test utilities
from backend.tests.utils import TestUtility

# Setup logging for our tests
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Test data for validation
INVALID_FILE_CONTENT = b"This is not a valid PDF or document file"
LARGE_FILE_SIZE = 50 * 1024 * 1024  # 50MB
CORRUPTED_PDF_HEADER = b"%PDF-1.4\n%corrupted content here"


class ErrorHandlingValidator:
    """Validates error handling and robustness of the consolidated system"""

    def __init__(self):
        self.test_util = TestUtility()

    def test_environment_variables(self):
        """Test behavior with missing environment variables"""
        logger.info("=== TESTING ENVIRONMENT VARIABLES ===")

        # Setup environment without OPENAI_API_KEY
        self.test_util.setup_test_environment({"OPENAI_API_KEY": None})

        def test_openai_init():
            from openai import OpenAI
            OpenAI()  # Should fail with missing API key
            return False  # If we get here, test failed

        # Test that OpenAI initialization properly fails with missing key
        self.test_util.expect_exception(
            "missing_openai_key_handling",
            Exception,
            test_openai_init
        )

        # Restore environment
        self.test_util.restore_test_environment()

    def test_invalid_file_uploads(self):
        """Test error handling with invalid file uploads"""
        logger.info("=== TESTING INVALID FILE UPLOADS ===")

        test_files = [
            ("invalid_text.pdf", INVALID_FILE_CONTENT, "text/plain"),
            ("corrupted.pdf", CORRUPTED_PDF_HEADER, "application/pdf"),
            (
                "empty.docx",
                b"",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            ("large_fake.txt", b"x" * 1000, "text/plain"),  # Fake large file
        ]

        for filename, content, _content_type in test_files:
            # Create mock file using utility
            mock_file, _temp_path = self.test_util.create_mock_file(filename, content, _content_type)

            def test_file_processing():
                from backend_logic.document_processor import DocumentProcessor
                processor = DocumentProcessor()

                # Process the file - should handle errors gracefully
                asyncio.run(processor.process_documents_from_streamlit([mock_file], []))

                # For empty files, processing should fail
                if content == b"":
                    return False  # Empty file should have failed
                return True  # File handled gracefully

            # Run the test with automatic timing and error handling
            if content == b"":
                # Empty files should raise an exception
                self.test_util.expect_exception(
                    f"invalid_file_{filename}",
                    Exception,
                    test_file_processing
                )
            else:
                # Other invalid files should either pass or fail gracefully
                self.test_util.run_test(f"invalid_file_{filename}", test_file_processing)

    def test_direct_function_call_error_handling(self):
        """Test that direct function calls handle errors properly without HTTP abstraction"""
        logger.info("=== TESTING DIRECT FUNCTION CALL ERROR HANDLING ===")

        from backend_logic.ai import AIAnalyzer
        from backend_logic.document_processor import DocumentProcessor

        # Test 1: DocumentProcessor with invalid input
        processor = DocumentProcessor()

        def test_processor_null_input():
            asyncio.run(processor.process_documents_from_streamlit(None, []))
            return False  # Should not reach here

        self.test_util.expect_exception(
            "direct_call_null_input",
            Exception,
            test_processor_null_input
        )

        # Test 2: AIAnalyzer with invalid OpenAI client
        def test_analyzer_invalid_client():
            AIAnalyzer(None, processor)  # Invalid client
            return False  # Should not reach here

        self.test_util.expect_exception(
            "direct_call_invalid_client",
            Exception,
            test_analyzer_invalid_client
        )

    def test_logging_system(self):
        """Test logging system configuration and output"""
        logger.info("=== TESTING LOGGING SYSTEM ===")

        def test_logging_output():
            if not os.environ.get("OPENAI_API_KEY"):
                return False  # Cannot test without API key

            from openai import OpenAI
            from backend_logic.ai import AIAnalyzer

            # Create components that should produce logging
            client = OpenAI()
            AIAnalyzer(client, None)

            # Test print-based logging
logger.info('AI ANALYZER: Test logging output')
            return True

        # Use capture_output to test logging functionality
        result, output = self.test_util.capture_output(test_logging_output)

        if result is False:
            # API key not available
            self.test_util.run_test(
                "logging_system_output",
                lambda: False  # Explicitly mark as failed due to missing API key
            )
        elif "AI ANALYZER:" in output or len(output) > 0:
            # Logging output captured successfully
            self.test_util.run_test(
                "logging_system_output",
                lambda: True
            )
        else:
            # No output captured
            self.test_util.run_test(
                "logging_system_output",
                lambda: False
            )

    def test_ai_service_connectivity(self):
        """Test behavior when AI services are unavailable"""
        logger.info("=== TESTING AI SERVICE CONNECTIVITY ===")

        if not os.environ.get("OPENAI_API_KEY"):
            # Cannot test without API key
            self.test_util.run_test(
                "ai_service_connectivity",
                lambda: False  # Mark as failed due to missing API key
            )
            return

        # Setup environment with invalid API key to simulate service unavailability
        original_key = os.environ.get("OPENAI_API_KEY")
        self.test_util.setup_test_environment({"OPENAI_API_KEY": "invalid_key_test"})

        def test_ai_request_with_invalid_key():
            from openai import OpenAI
            from backend_logic.ai import AIAnalyzer
            from backend_logic.document_processor import DocumentProcessor

            client = OpenAI()
            processor = DocumentProcessor()
            analyzer = AIAnalyzer(client, processor)

            # This should fail with invalid API key
            asyncio.run(analyzer._make_openai_request("test prompt", "gpt-4o-mini"))
            return False  # Should not reach here

        # Test that invalid API key properly fails
        self.test_util.expect_exception(
            "ai_service_unavailable_handling",
            Exception,
            test_ai_request_with_invalid_key
        )

        # Restore original environment
        self.test_util.restore_test_environment()

    def run_all_tests(self):
        """Run all validation tests"""
        logger.info("🔧 Starting Performance and Error Handling Validation")
        logger.info("=" * 60)

        # Run test suites
        self.test_environment_variables()
        self.test_invalid_file_uploads()
        self.test_direct_function_call_error_handling()
        self.test_logging_system()
        self.test_ai_service_connectivity()

        # Generate and log summary using utility function
        summary = self.test_util.log_summary(logger)

        # Cleanup resources
        self.test_util.cleanup()

        return summary


def main():
    """Main validation runner"""
    try:
        validator = ErrorHandlingValidator()
        summary = validator.run_all_tests()

        # Exit with appropriate code
        if summary["failed"] > 0:
logger.error(f'\n⚠️  {summary['failed']} tests failed. Review the issues above.')
            sys.exit(1)
        else:
logger.info(f'\n🎉 All {summary['passed']} tests passed!')
            sys.exit(0)

    except Exception as e:
logger.error(f'❌ Fatal error during validation: {e}')
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
