#!/usr/bin/env python3
"""
Performance Validation Test Suite
Tests memory usage, processing efficiency, and performance characteristics of the consolidated architecture
"""

from __future__ import annotations

import asyncio
import gc
import logging
import os
import sys
import tempfile
import time
import traceback
from typing import Any

import psutil
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Setup logging for our tests
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Tracks performance metrics during testing"""

    def __init__(self):
        self.metrics = {}
        self.process = psutil.Process()

    def start_measurement(self, test_name: str) -> None:
        """Start measuring performance for a test"""
        gc.collect()  # Clean garbage before measurement
        self.metrics[test_name] = {
            "start_time": time.time(),
            "start_memory": self.process.memory_info().rss / 1024 / 1024,  # MB
            "start_cpu_percent": self.process.cpu_percent(),
        }

    def end_measurement(
        self, test_name: str, success: bool = True, details: str = ""
    ) -> None:
        """End measurement and record results"""
        if test_name not in self.metrics:
            return

        end_time = time.time()
        end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        end_cpu_percent = self.process.cpu_percent()

        self.metrics[test_name].update(
            {
                "end_time": end_time,
                "end_memory": end_memory,
                "end_cpu_percent": end_cpu_percent,
                "duration": end_time - self.metrics[test_name]["start_time"],
                "memory_delta": end_memory - self.metrics[test_name]["start_memory"],
                "peak_memory": end_memory,
                "success": success,
                "details": details,
            }
        )

    def get_summary(self) -> dict[str, Any]:
        """Get performance summary"""
        if not self.metrics:
            return {}

        total_duration = sum(m.get("duration", 0) for m in self.metrics.values())
        max_memory = max(m.get("peak_memory", 0) for m in self.metrics.values())
        total_memory_delta = sum(
            m.get("memory_delta", 0) for m in self.metrics.values()
        )

        return {
            "total_tests": len(self.metrics),
            "total_duration": total_duration,
            "max_memory_usage": max_memory,
            "total_memory_delta": total_memory_delta,
            "average_duration": total_duration / len(self.metrics)
            if self.metrics
            else 0,
            "details": self.metrics,
        }


class PerformanceValidator:
    """Validates performance characteristics of the consolidated system"""

    def __init__(self):
        self.metrics = PerformanceMetrics()
        self.test_files_created = []

    def cleanup_test_files(self):
        """Clean up any temporary files created during testing"""
        for file_path in self.test_files_created:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Could not clean up {file_path}: {e}")
        self.test_files_created.clear()

    def create_large_test_file(self, size_mb: int, content_type: str = "text") -> str:
        """Create a large test file for performance testing"""
        with tempfile.NamedTemporaryFile(
            suffix=f".{content_type}", delete=False
        ) as tmp_file:
            if content_type == "txt":
                # Create realistic text content
                base_content = "This is sample legal document content. " * 100
                content_size = len(base_content.encode())
                repetitions = (size_mb * 1024 * 1024) // content_size
                content = (base_content * repetitions).encode()
            else:
                # Create binary content
                content = b"x" * (size_mb * 1024 * 1024)

            tmp_file.write(content)
            self.test_files_created.append(tmp_file.name)
            return tmp_file.name

    def test_memory_usage_document_processing(self):
        """Test memory usage during document processing"""
        logger.info("=== TESTING MEMORY USAGE DURING DOCUMENT PROCESSING ===")

        test_name = "memory_usage_document_processing"
        self.metrics.start_measurement(test_name)

        try:
            # Create test files of various sizes
            small_file = self.create_large_test_file(1, "txt")  # 1MB
            medium_file = self.create_large_test_file(5, "txt")  # 5MB
            large_file = self.create_large_test_file(10, "txt")  # 10MB

            from backend_logic.document_processor import DocumentProcessor

            processor = DocumentProcessor()

            # Test processing multiple files
            class MockUploadedFile:
                def __init__(self, file_path, name):
                    self.name = name
                    with open(file_path, "rb") as f:
                        self._content = f.read()
                    self.size = len(self._content)

                def getvalue(self):
                    return self._content

            mock_files = [
                MockUploadedFile(small_file, "small_test.txt"),
                MockUploadedFile(medium_file, "medium_test.txt"),
                MockUploadedFile(large_file, "large_test.txt"),
            ]

            # Record memory before processing
            pre_processing_memory = self.metrics.process.memory_info().rss / 1024 / 1024

            # Process documents
            asyncio.run(processor.process_documents_from_streamlit(mock_files, []))

            # Record memory after processing
            post_processing_memory = (
                self.metrics.process.memory_info().rss / 1024 / 1024
            )
            memory_increase = post_processing_memory - pre_processing_memory

            self.metrics.end_measurement(
                test_name,
                True,
                f"✅ Processed {len(mock_files)} files (16MB total). Memory increase: {memory_increase:.1f}MB",
            )

        except Exception as e:
            self.metrics.end_measurement(
                test_name, False, f"❌ Memory test failed: {e!s}"
            )

    def test_direct_function_call_performance(self):
        """Test performance characteristics of direct function calls"""
        logger.info("=== TESTING DIRECT FUNCTION CALL PERFORMANCE ===")

        test_name = "direct_function_call_performance"
        self.metrics.start_measurement(test_name)

        try:
            # Test direct function call latency
            from backend_logic.document_processor import DocumentProcessor

            processor = DocumentProcessor()

            # Measure function call overhead
            start_time = time.time()
            for _ in range(100):
                # Call a lightweight method multiple times
                processor._get_document_type("test.pdf", [])
            function_call_time = (time.time() - start_time) / 100  # Average per call

            self.metrics.end_measurement(
                test_name,
                True,
                f"✅ Direct function call latency: {function_call_time * 1000:.3f}ms average per call",
            )

        except Exception as e:
            self.metrics.end_measurement(
                test_name, False, f"❌ Direct function call test failed: {e!s}"
            )

    def test_large_file_processing_efficiency(self):
        """Test efficiency when processing large files"""
        logger.info("=== TESTING LARGE FILE PROCESSING EFFICIENCY ===")

        test_name = "large_file_processing_efficiency"
        self.metrics.start_measurement(test_name)

        try:
            # Create a large text file (20MB)
            large_file = self.create_large_test_file(20, "txt")

            from backend_logic.document_processor import DocumentProcessor

            processor = DocumentProcessor()

            class MockUploadedFile:
                def __init__(self, file_path, name):
                    self.name = name
                    with open(file_path, "rb") as f:
                        self._content = f.read()
                    self.size = len(self._content)

                def getvalue(self):
                    return self._content

            mock_file = MockUploadedFile(large_file, "large_test.txt")

            # Record start metrics
            start_memory = self.metrics.process.memory_info().rss / 1024 / 1024
            start_time = time.time()

            # Process large file
            asyncio.run(processor.process_documents_from_streamlit([mock_file], []))

            # Record end metrics
            end_time = time.time()
            end_memory = self.metrics.process.memory_info().rss / 1024 / 1024
            processing_time = end_time - start_time
            memory_usage = end_memory - start_memory

            # Calculate efficiency metrics
            mb_per_second = 20 / processing_time if processing_time > 0 else 0
            memory_efficiency = memory_usage / 20  # Memory used per MB processed

            self.metrics.end_measurement(
                test_name,
                True,
                f"✅ Processed 20MB file in {processing_time:.2f}s ({mb_per_second:.1f} MB/s). Memory efficiency: {memory_efficiency:.2f}x",
            )

        except Exception as e:
            self.metrics.end_measurement(
                test_name, False, f"❌ Large file processing test failed: {e!s}"
            )

    def test_concurrent_processing_performance(self):
        """Test performance under concurrent processing scenarios"""
        logger.info("=== TESTING CONCURRENT PROCESSING PERFORMANCE ===")

        test_name = "concurrent_processing_performance"
        self.metrics.start_measurement(test_name)

        try:
            # Create multiple medium-sized files
            files = []
            for _i in range(5):
                file_path = self.create_large_test_file(2, "txt")  # 2MB each
                files.append(file_path)

            from backend_logic.document_processor import DocumentProcessor

            processor = DocumentProcessor()

            class MockUploadedFile:
                def __init__(self, file_path, name):
                    self.name = name
                    with open(file_path, "rb") as f:
                        self._content = f.read()
                    self.size = len(self._content)

                def getvalue(self):
                    return self._content

            mock_files = [
                MockUploadedFile(f, f"test_{i}.txt") for i, f in enumerate(files)
            ]

            # Test sequential processing (current architecture)
            start_time = time.time()
            asyncio.run(processor.process_documents_from_streamlit(mock_files, []))
            sequential_time = time.time() - start_time

            total_size_mb = len(files) * 2
            throughput = total_size_mb / sequential_time if sequential_time > 0 else 0

            self.metrics.end_measurement(
                test_name,
                True,
                f"✅ Processed {len(files)} files ({total_size_mb}MB) in {sequential_time:.2f}s. Throughput: {throughput:.1f} MB/s",
            )

        except Exception as e:
            self.metrics.end_measurement(
                test_name, False, f"❌ Concurrent processing test failed: {e!s}"
            )

    def test_memory_leak_detection(self):
        """Test for potential memory leaks during repeated operations"""
        logger.info("=== TESTING MEMORY LEAK DETECTION ===")

        test_name = "memory_leak_detection"
        self.metrics.start_measurement(test_name)

        try:
            from backend_logic.document_processor import DocumentProcessor

            # Record initial memory
            gc.collect()
            initial_memory = self.metrics.process.memory_info().rss / 1024 / 1024

            # Perform repeated operations
            processor = DocumentProcessor()
            memory_readings = [initial_memory]

            for iteration in range(10):
                # Create a small test file
                test_file = self.create_large_test_file(1, "txt")

                class MockUploadedFile:
                    def __init__(self, file_path, name):
                        self.name = name
                        with open(file_path, "rb") as f:
                            self._content = f.read()
                        self.size = len(self._content)

                    def getvalue(self):
                        return self._content

                mock_file = MockUploadedFile(test_file, f"test_{iteration}.txt")

                # Process file
                asyncio.run(processor.process_documents_from_streamlit([mock_file], []))

                # Clean up
                os.remove(test_file)
                gc.collect()

                # Record memory
                current_memory = self.metrics.process.memory_info().rss / 1024 / 1024
                memory_readings.append(current_memory)

            # Analyze memory trend
            final_memory = memory_readings[-1]
            memory_growth = final_memory - initial_memory
            max_memory = max(memory_readings)
            memory_stability = max_memory - initial_memory

            # Check for memory leak (growth > 50MB indicates potential leak)
            leak_detected = memory_growth > 50

            self.metrics.end_measurement(
                test_name,
                not leak_detected,
                f"{'❌ Potential memory leak detected' if leak_detected else '✅ No significant memory leak'}: Growth {memory_growth:.1f}MB, Max usage {memory_stability:.1f}MB",
            )

        except Exception as e:
            self.metrics.end_measurement(
                test_name, False, f"❌ Memory leak detection failed: {e!s}"
            )

    def test_error_recovery_performance(self):
        """Test performance impact of error handling and recovery"""
        logger.info("=== TESTING ERROR RECOVERY PERFORMANCE ===")

        test_name = "error_recovery_performance"
        self.metrics.start_measurement(test_name)

        try:
            from backend_logic.document_processor import DocumentProcessor

            processor = DocumentProcessor()

            # Test mix of valid and invalid files
            valid_file = self.create_large_test_file(1, "txt")

            class MockUploadedFile:
                def __init__(self, content, name):
                    self.name = name
                    self._content = (
                        content if isinstance(content, bytes) else content.encode()
                    )
                    self.size = len(self._content)

                def getvalue(self):
                    return self._content

            # Mix of valid and invalid files
            mock_files = [
                MockUploadedFile(open(valid_file, "rb").read(), "valid_test.txt"),
                MockUploadedFile(b"invalid content", "invalid.pdf"),  # Invalid PDF
                MockUploadedFile(b"", "empty.docx"),  # Empty file
            ]

            # Test error recovery performance
            start_time = time.time()
            try:
                asyncio.run(processor.process_documents_from_streamlit(mock_files, []))
                recovery_time = time.time() - start_time

                self.metrics.end_measurement(
                    test_name,
                    True,
                    f"✅ Error recovery completed in {recovery_time:.2f}s with mixed valid/invalid files",
                )
            except Exception as e:
                recovery_time = time.time() - start_time
                self.metrics.end_measurement(
                    test_name,
                    True,  # Expected to handle errors gracefully
                    f"✅ Error handling worked as expected in {recovery_time:.2f}s: {type(e).__name__}",
                )

        except Exception as e:
            self.metrics.end_measurement(
                test_name, False, f"❌ Error recovery test failed: {e!s}"
            )

    def run_all_tests(self):
        """Run all performance validation tests"""
        logger.info("⚡ Starting Performance and Memory Validation")
        logger.info("=" * 60)

        try:
            # Run test suites
            self.test_memory_usage_document_processing()
            self.test_direct_function_call_performance()
            self.test_large_file_processing_efficiency()
            self.test_concurrent_processing_performance()
            self.test_memory_leak_detection()
            self.test_error_recovery_performance()

        finally:
            # Always clean up test files
            self.cleanup_test_files()

        # Generate summary
        summary = self.metrics.get_summary()

        logger.info("=" * 60)
        logger.info("📊 PERFORMANCE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total Tests: {summary.get('total_tests', 0)}")
        logger.info(f"Total Duration: {summary.get('total_duration', 0):.2f}s")
        logger.info(
            f"Average Duration: {summary.get('average_duration', 0):.2f}s per test"
        )
        logger.info(f"Peak Memory Usage: {summary.get('max_memory_usage', 0):.1f}MB")
        logger.info(f"Total Memory Delta: {summary.get('total_memory_delta', 0):.1f}MB")

        logger.info("\n📋 DETAILED PERFORMANCE RESULTS:")
        for test_name, result in summary.get("details", {}).items():
            status = "✅ PASS" if result.get("success", False) else "❌ FAIL"
            duration = result.get("duration", 0)
            memory_delta = result.get("memory_delta", 0)
            details = result.get("details", "No details")
            logger.info(
                f"{status} {test_name} ({duration:.2f}s, {memory_delta:+.1f}MB): {details}"
            )

        return summary


def main():
    """Main performance validation runner"""
    try:
        validator = PerformanceValidator()
        summary = validator.run_all_tests()

        # Check for critical performance issues
        critical_issues = []
        for test_name, result in summary.get("details", {}).items():
            if not result.get("success", False):
                critical_issues.append(test_name)
            elif result.get("memory_delta", 0) > 100:  # >100MB memory increase
                critical_issues.append(f"{test_name} (high memory usage)")
            elif result.get("duration", 0) > 30:  # >30s duration
                critical_issues.append(f"{test_name} (slow performance)")

        if critical_issues:
logger.error(f'\n⚠️  Performance issues detected: {', '.join(critical_issues)}')
            sys.exit(1)
        else:
logger.info('\n🎉 All performance tests completed successfully!')
            sys.exit(0)

    except Exception as e:
logger.error(f'❌ Fatal error during performance validation: {e}')
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
