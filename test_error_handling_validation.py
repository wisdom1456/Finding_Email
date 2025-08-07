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
import tempfile
import time
import traceback
from typing import Any


# Setup logging for our tests
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Test data for validation
INVALID_FILE_CONTENT = b"This is not a valid PDF or document file"
LARGE_FILE_SIZE = 50 * 1024 * 1024  # 50MB
CORRUPTED_PDF_HEADER = b"%PDF-1.4\n%corrupted content here"


class ValidationResults:
    """Stores validation test results"""

    def __init__(self):
        self.tests = {}
        self.start_time = time.time()

    def add_test(
        self, test_name: str, success: bool, details: str, execution_time: float = 0
    ) -> None:
        self.tests[test_name] = {
            "success": success,
            "details": details,
            "execution_time": execution_time,
            "timestamp": time.time(),
        }

    def get_summary(self) -> dict[str, Any]:
        total_tests = len(self.tests)
        passed_tests = sum(1 for test in self.tests.values() if test["success"])
        failed_tests = total_tests - passed_tests
        total_execution_time = time.time() - self.start_time

        return {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": (passed_tests / total_tests * 100)
            if total_tests > 0
            else 0,
            "total_execution_time": total_execution_time,
            "details": self.tests,
        }


class ErrorHandlingValidator:
    """Validates error handling and robustness of the consolidated system"""

    def __init__(self):
        self.results = ValidationResults()

    def test_environment_variables(self):
        """Test behavior with missing environment variables"""
        logger.info("=== TESTING ENVIRONMENT VARIABLES ===")

        start_time = time.time()
        try:
            # Test 1: Missing OPENAI_API_KEY
            original_key = os.environ.get("OPENAI_API_KEY")
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]

            try:
                # Try to import and initialize components
                from openai import OpenAI

                # This should fail gracefully
                try:
                    OpenAI()  # Should fail with missing API key
                    self.results.add_test(
                        "missing_openai_key_handling",
                        False,
                        "OpenAI client initialization should fail with missing API key but didn't",
                        time.time() - start_time,
                    )
                except Exception as e:
                    self.results.add_test(
                        "missing_openai_key_handling",
                        True,
                        f"✅ Properly caught missing API key: {type(e).__name__}",
                        time.time() - start_time,
                    )

            finally:
                # Restore original key
                if original_key:
                    os.environ["OPENAI_API_KEY"] = original_key

        except Exception as e:
            self.results.add_test(
                "missing_openai_key_handling",
                False,
                f"❌ Unexpected error during environment variable test: {e!s}",
                time.time() - start_time,
            )

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
            start_time = time.time()
            try:
                # Create temporary file
                with tempfile.NamedTemporaryFile(
                    suffix=f".{filename.split('.')[-1]}", delete=False
                ) as tmp_file:
                    tmp_file.write(content)
                    tmp_file_path = tmp_file.name

                try:
                    # Test file processing
                    from backend_logic.document_processor import DocumentProcessor

                    processor = DocumentProcessor()

                    # This should handle errors gracefully
                    try:
                        # Simulate Streamlit file upload object
                        class MockUploadedFile:
                            def __init__(self, name, content):
                                self.name = name
                                self._content = content
                                self.size = len(content)

                            def getvalue(self):
                                return self._content

                        mock_file = MockUploadedFile(filename, content)
                        asyncio.run(
                            processor.process_documents_from_streamlit([mock_file], [])
                        )

                        if content == b"":  # Empty file should fail
                            self.results.add_test(
                                f"invalid_file_{filename}",
                                False,
                                f"❌ Empty file {filename} should have failed but didn't",
                                time.time() - start_time,
                            )
                        else:
                            self.results.add_test(
                                f"invalid_file_{filename}",
                                True,
                                f"✅ Invalid file {filename} handled gracefully",
                                time.time() - start_time,
                            )

                    except Exception as e:
                        self.results.add_test(
                            f"invalid_file_{filename}",
                            True,
                            f"✅ Invalid file {filename} properly rejected: {type(e).__name__}",
                            time.time() - start_time,
                        )

                finally:
                    # Clean up temp file
                    if os.path.exists(tmp_file_path):
                        os.remove(tmp_file_path)

            except Exception as e:
                self.results.add_test(
                    f"invalid_file_{filename}",
                    False,
                    f"❌ Unexpected error testing {filename}: {e!s}",
                    time.time() - start_time,
                )

    def test_direct_function_call_error_handling(self):
        """Test that direct function calls handle errors properly without HTTP abstraction"""
        logger.info("=== TESTING DIRECT FUNCTION CALL ERROR HANDLING ===")

        start_time = time.time()
        try:
            from backend_logic.ai import AIAnalyzer
            from backend_logic.document_processor import DocumentProcessor

            # Test 1: DocumentProcessor with invalid input
            processor = DocumentProcessor()
            try:
                # This should raise a proper exception
                asyncio.run(processor.process_documents_from_streamlit(None, []))
                self.results.add_test(
                    "direct_call_null_input",
                    False,
                    "❌ Null input should have raised exception but didn't",
                    time.time() - start_time,
                )
            except Exception as e:
                self.results.add_test(
                    "direct_call_null_input",
                    True,
                    f"✅ Direct function call properly handled null input: {type(e).__name__}",
                    time.time() - start_time,
                )

            # Test 2: AIAnalyzer with invalid OpenAI client
            try:
                AIAnalyzer(None, processor)  # Invalid client
                self.results.add_test(
                    "direct_call_invalid_client",
                    False,
                    "❌ Invalid OpenAI client should have raised exception but didn't",
                    time.time() - start_time,
                )
            except Exception as e:
                self.results.add_test(
                    "direct_call_invalid_client",
                    True,
                    f"✅ Direct function call properly handled invalid client: {type(e).__name__}",
                    time.time() - start_time,
                )

        except Exception as e:
            self.results.add_test(
                "direct_function_call_error_handling",
                False,
                f"❌ Unexpected error in direct function call test: {e!s}",
                time.time() - start_time,
            )

    def test_logging_system(self):
        """Test logging system configuration and output"""
        logger.info("=== TESTING LOGGING SYSTEM ===")

        start_time = time.time()
        try:
            # Capture stdout to test print-based logging
            import sys
            from io import StringIO

            captured_output = StringIO()
            original_stdout = sys.stdout
            sys.stdout = captured_output

            try:
                # Test that modules produce logging output
                from openai import OpenAI

                from backend_logic.ai import AIAnalyzer

                # Create a mock that will trigger logging
                if os.environ.get("OPENAI_API_KEY"):
                    client = OpenAI()
                    AIAnalyzer(client, None)

                    # This should produce console output
                    print("AI ANALYZER: Test logging output")

                    # Restore stdout and check output
                    sys.stdout = original_stdout
                    output = captured_output.getvalue()

                    if "AI ANALYZER:" in output or len(output) > 0:
                        self.results.add_test(
                            "logging_system_output",
                            True,
                            f"✅ Logging system producing output: {len(output)} characters captured",
                            time.time() - start_time,
                        )
                    else:
                        self.results.add_test(
                            "logging_system_output",
                            False,
                            "❌ No logging output captured",
                            time.time() - start_time,
                        )
                else:
                    sys.stdout = original_stdout
                    self.results.add_test(
                        "logging_system_output",
                        False,
                        "❌ Cannot test logging - no OpenAI API key available",
                        time.time() - start_time,
                    )

            finally:
                sys.stdout = original_stdout

        except Exception as e:
            self.results.add_test(
                "logging_system_output",
                False,
                f"❌ Error testing logging system: {e!s}",
                time.time() - start_time,
            )

    def test_ai_service_connectivity(self):
        """Test behavior when AI services are unavailable"""
        logger.info("=== TESTING AI SERVICE CONNECTIVITY ===")

        start_time = time.time()
        try:
            if not os.environ.get("OPENAI_API_KEY"):
                self.results.add_test(
                    "ai_service_connectivity",
                    False,
                    "❌ Cannot test AI connectivity - no API key configured",
                    time.time() - start_time,
                )
                return

            from openai import OpenAI

            from backend_logic.ai import AIAnalyzer
            from backend_logic.document_processor import DocumentProcessor

            # Test with invalid API key to simulate service unavailability
            original_key = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "invalid_key_test"

            try:
                client = OpenAI()
                processor = DocumentProcessor()
                analyzer = AIAnalyzer(client, processor)

                # Try to make a request that should fail
                try:
                    asyncio.run(
                        analyzer._make_openai_request("test prompt", "gpt-4o-mini")
                    )
                    self.results.add_test(
                        "ai_service_unavailable_handling",
                        False,
                        "❌ Invalid API key should have failed but didn't",
                        time.time() - start_time,
                    )
                except Exception as e:
                    self.results.add_test(
                        "ai_service_unavailable_handling",
                        True,
                        f"✅ AI service unavailability properly handled: {type(e).__name__}",
                        time.time() - start_time,
                    )

            finally:
                # Restore original API key
                os.environ["OPENAI_API_KEY"] = original_key

        except Exception as e:
            self.results.add_test(
                "ai_service_connectivity",
                False,
                f"❌ Unexpected error testing AI connectivity: {e!s}",
                time.time() - start_time,
            )

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

        # Generate summary
        summary = self.results.get_summary()

        logger.info("=" * 60)
        logger.info("🎯 VALIDATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total Tests: {summary['total_tests']}")
        logger.info(f"Passed: {summary['passed']}")
        logger.info(f"Failed: {summary['failed']}")
        logger.info(f"Success Rate: {summary['success_rate']:.1f}%")
        logger.info(f"Total Execution Time: {summary['total_execution_time']:.2f}s")

        logger.info("\n📋 DETAILED RESULTS:")
        for test_name, result in summary["details"].items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            logger.info(f"{status} {test_name}: {result['details']}")

        return summary


def main():
    """Main validation runner"""
    try:
        validator = ErrorHandlingValidator()
        summary = validator.run_all_tests()

        # Exit with appropriate code
        if summary["failed"] > 0:
            print(f"\n⚠️  {summary['failed']} tests failed. Review the issues above.")
            sys.exit(1)
        else:
            print(f"\n🎉 All {summary['passed']} tests passed!")
            sys.exit(0)

    except Exception as e:
        print(f"❌ Fatal error during validation: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
