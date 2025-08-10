#!/usr/bin/env python3
"""
Test Utilities Module
Consolidates common testing patterns and boilerplate code for the Legal Document Analysis Portal
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import traceback
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple, Union


# Setup logging for tests
logger = logging.getLogger(__name__)


class ValidationResults:
    """Stores validation test results with timing and success tracking"""

    def __init__(self):
        self.tests = {}
        self.start_time = time.time()

    def add_test(
        self, test_name: str, success: bool, details: str, execution_time: float = 0
    ) -> None:
        """Add a test result with timing and details"""
        self.tests[test_name] = {
            "success": success,
            "details": details,
            "execution_time": execution_time,
            "timestamp": time.time(),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Generate a comprehensive test summary"""
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


class MockUploadedFile:
    """Mock Streamlit uploaded file object for testing"""

    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content
        self.size = len(content)

    def getvalue(self) -> bytes:
        """Return file content as bytes"""
        return self._content


class TestUtility:
    """Centralized utility class for common testing operations"""

    def __init__(self):
        self.results = ValidationResults()
        self._temp_files: List[str] = []
        self._original_env_vars: Dict[str, Optional[str]] = {}

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources"""
        self.cleanup()

    def setup_test_environment(self, env_vars: Dict[str, Optional[str]]) -> None:
        """
        Setup test environment by manipulating environment variables

        Args:
            env_vars: Dict of environment variable names to values (None to delete)
        """
        for var_name, var_value in env_vars.items():
            # Store original value for restoration
            self._original_env_vars[var_name] = os.environ.get(var_name)

            # Set or delete the environment variable
            if var_value is None:
                if var_name in os.environ:
                    del os.environ[var_name]
            else:
                os.environ[var_name] = var_value

    def restore_test_environment(self) -> None:
        """Restore original environment variables"""
        for var_name, original_value in self._original_env_vars.items():
            if original_value is None:
                if var_name in os.environ:
                    del os.environ[var_name]
            else:
                os.environ[var_name] = original_value
        self._original_env_vars.clear()

    def create_mock_file(
        self, filename: str, content: bytes, content_type: str = "text/plain"
    ) -> Tuple[MockUploadedFile, str]:
        """
        Create a temporary mock file for testing

        Args:
            filename: Name of the mock file
            content: Binary content of the file
            content_type: MIME type of the file

        Returns:
            Tuple of (MockUploadedFile, temp_file_path)
        """
        # Create temporary file
        suffix = f".{filename.split('.')[-1]}" if "." in filename else ".tmp"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        # Track for cleanup
        self._temp_files.append(tmp_file_path)

        # Create mock object
        mock_file = MockUploadedFile(filename, content)

        return mock_file, tmp_file_path

    def run_test(self, test_name: str, test_function, *args, **kwargs) -> Any:
        """
        Wrapper to run a test function with timing and error handling

        Args:
            test_name: Name of the test for reporting
            test_function: Function to execute
            *args, **kwargs: Arguments to pass to test_function

        Returns:
            Result of test_function or None if failed
        """
        start_time = time.time()
        try:
            result = test_function(*args, **kwargs)
            execution_time = time.time() - start_time

            # If result is a boolean, use it for success
            if isinstance(result, bool):
                success = result
                details = (
                    "✅ Test completed successfully" if success else "❌ Test failed"
                )
            else:
                success = True
                details = "✅ Test completed successfully"

            self.results.add_test(test_name, success, details, execution_time)
            return result

        except Exception as e:
            execution_time = time.time() - start_time
            self.results.add_test(
                test_name,
                False,
                f"❌ Test failed with exception: {type(e).__name__}: {e!s}",
                execution_time,
            )
            return None

    async def run_async_test(
        self, test_name: str, async_test_function, *args, **kwargs
    ) -> Any:
        """
        Wrapper to run an async test function with timing and error handling

        Args:
            test_name: Name of the test for reporting
            async_test_function: Async function to execute
            *args, **kwargs: Arguments to pass to async_test_function

        Returns:
            Result of async_test_function or None if failed
        """
        start_time = time.time()
        try:
            result = await async_test_function(*args, **kwargs)
            execution_time = time.time() - start_time

            # If result is a boolean, use it for success
            if isinstance(result, bool):
                success = result
                details = (
                    "✅ Async test completed successfully"
                    if success
                    else "❌ Async test failed"
                )
            else:
                success = True
                details = "✅ Async test completed successfully"

            self.results.add_test(test_name, success, details, execution_time)
            return result

        except Exception as e:
            execution_time = time.time() - start_time
            self.results.add_test(
                test_name,
                False,
                f"❌ Async test failed with exception: {type(e).__name__}: {e!s}",
                execution_time,
            )
            return None

    def capture_output(self, test_function, *args, **kwargs) -> Tuple[Any, str]:
        """
        Capture stdout output from a test function

        Args:
            test_function: Function to execute
            *args, **kwargs: Arguments to pass to test_function

        Returns:
            Tuple of (function_result, captured_output)
        """
        import sys

        captured_output = StringIO()
        original_stdout = sys.stdout
        sys.stdout = captured_output

        try:
            result = test_function(*args, **kwargs)
            sys.stdout = original_stdout
            output = captured_output.getvalue()
            return result, output
        finally:
            sys.stdout = original_stdout

    def expect_exception(
        self, test_name: str, exception_type: type, test_function, *args, **kwargs
    ) -> bool:
        """
        Test that a function raises a specific exception type

        Args:
            test_name: Name of the test for reporting
            exception_type: Expected exception type
            test_function: Function that should raise the exception
            *args, **kwargs: Arguments to pass to test_function

        Returns:
            True if expected exception was raised, False otherwise
        """
        start_time = time.time()
        try:
            test_function(*args, **kwargs)
            # If no exception was raised, test failed
            execution_time = time.time() - start_time
            self.results.add_test(
                test_name,
                False,
                f"❌ Expected {exception_type.__name__} but no exception was raised",
                execution_time,
            )
            return False

        except exception_type as e:
            # Expected exception was raised
            execution_time = time.time() - start_time
            self.results.add_test(
                test_name,
                True,
                f"✅ Expected exception {exception_type.__name__} was properly raised: {e!s}",
                execution_time,
            )
            return True

        except Exception as e:
            # Wrong exception type was raised
            execution_time = time.time() - start_time
            self.results.add_test(
                test_name,
                False,
                f"❌ Expected {exception_type.__name__} but got {type(e).__name__}: {e!s}",
                execution_time,
            )
            return False

    def cleanup(self) -> None:
        """Clean up temporary files and restore environment"""
        # Clean up temporary files
        for temp_file in self._temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {temp_file}: {e}")
        self._temp_files.clear()

        # Restore environment variables
        self.restore_test_environment()

    def get_summary(self) -> Dict[str, Any]:
        """Get test results summary"""
        return self.results.get_summary()

    def log_summary(
        self, logger_instance: Optional[logging.Logger] = None
    ) -> Dict[str, Any]:
        """
        Log comprehensive test summary

        Args:
            logger_instance: Logger to use (defaults to module logger)

        Returns:
            Test summary dictionary
        """
        if logger_instance is None:
            logger_instance = logger

        summary = self.get_summary()

        logger_instance.info("=" * 60)
        logger_instance.info("🎯 TEST VALIDATION SUMMARY")
        logger_instance.info("=" * 60)
        logger_instance.info(f"Total Tests: {summary['total_tests']}")
        logger_instance.info(f"Passed: {summary['passed']}")
        logger_instance.info(f"Failed: {summary['failed']}")
        logger_instance.info(f"Success Rate: {summary['success_rate']:.1f}%")
        logger_instance.info(
            f"Total Execution Time: {summary['total_execution_time']:.2f}s"
        )

        logger_instance.info("\n📋 DETAILED RESULTS:")
        for test_name, result in summary["details"].items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            logger_instance.info(f"{status} {test_name}: {result['details']}")

        return summary
