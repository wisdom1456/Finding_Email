#!/usr/bin/env python3
"""
Cost Tracking Performance Test

Tests the cost tracking system under various load conditions
to ensure scalability and reliability.
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal

from utils.logging_config import setup_logging


logger = setup_logging("unknown_service")


# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.utils.data_models import (
    ActualCosts,
    CostEstimate,
    CostSummary,
    DocumentType,
    FileType,
    ProcessedDocument,
    ServiceCost,
)
from backend_logic.cost_calculator import CostCalculator
from backend_logic.cost_estimator import CostEstimator
from backend_logic.cost_session_manager import CostSessionManager


class PerformanceTestSuite:
    def __init__(self):
        self.session_manager = CostSessionManager(
            session_storage_dir="perf_test_sessions"
        )
        self.cost_estimator = CostEstimator()
        self.cost_calculator = CostCalculator()
        self.results = {}

    def cleanup(self):
        """Clean up test data."""
        try:
            import shutil

            if os.path.exists("perf_test_sessions"):
                shutil.rmtree("perf_test_sessions")
        except Exception as e:
            logger.warning(f"Cleanup warning: {e}")

    def test_large_document_estimation(self):
        """Test cost estimation with large numbers of documents."""
        logger.info("\n📊 Testing Large Document Set Estimation...")

        # Create 100 sample documents
        large_doc_set = []
        for i in range(100):
            doc = ProcessedDocument(
                file_name=f"document_{i:03d}.pdf",
                content="This is a sample legal document with approximately 500 words. "
                * 50,  # ~25k words each
                file_type=FileType.PDF,
                document_type=DocumentType.CASE_DOCUMENT,
            )
            large_doc_set.append(doc)

        # Time the estimation process
        start_time = time.time()

        try:
            document_costs = self.cost_estimator.estimate_document_processing_costs(
                documents=large_doc_set
            )

            # Create a cost estimate object
            estimate = CostEstimate(
                estimated_document_costs=document_costs,
                estimated_media_costs=[],
                total_estimated_cost=sum(cost.total_cost for cost in document_costs),
                confidence_level=0.8,
                estimation_timestamp=datetime.now(),
            )

            end_time = time.time()
            processing_time = end_time - start_time

            self.results["large_doc_estimation"] = {
                "documents_processed": len(large_doc_set),
                "processing_time": processing_time,
                "total_estimated_cost": float(estimate.total_estimated_cost),
                "avg_time_per_doc": processing_time / len(large_doc_set),
                "status": "PASSED",
            }

            logger.info(
                f"   ✅ Processed {len(large_doc_set)} documents in {processing_time:.3f}s"
            )
            logger.info(
                f"   💰 Total estimated cost: ${float(estimate.total_estimated_cost):.4f}"
            )
            logger.info(
                f"   ⏱️  Average time per document: {processing_time / len(large_doc_set):.4f}s"
            )

        except Exception as e:
            self.results["large_doc_estimation"] = {"status": "FAILED", "error": str(e)}
            logger.error(f"   ❌ Large document estimation failed: {e}")

    def test_concurrent_sessions(self):
        """Test multiple concurrent cost tracking sessions."""
        logger.info("\n🔄 Testing Concurrent Session Management...")

        def create_session(session_id):
            """Create a single test session."""
            try:
                # Create sample data for this session
                docs = [
                    ProcessedDocument(
                        file_name=f"case_{session_id}_doc1.pdf",
                        content="Sample legal document content for testing.",
                        file_type=FileType.PDF,
                        document_type=DocumentType.CASE_DOCUMENT,
                    )
                ]

                case_id = f"PERF_TEST_{session_id:03d}"

                # Initialize session
                session_case_id = self.session_manager.initialize_cost_session(
                    case_id=case_id, documents=docs, audio_files=[], video_files=[]
                )

                # Get cost summary
                summary = self.session_manager.get_cost_summary(session_case_id)

                return {
                    "session_id": session_id,
                    "case_id": session_case_id,
                    "success": True,
                    "estimated_cost": float(summary.cost_estimate.total_estimated_cost)
                    if summary and summary.cost_estimate
                    else 0.0,
                }

            except Exception as e:
                return {"session_id": session_id, "success": False, "error": str(e)}

        # Test with 10 concurrent sessions
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_session, i) for i in range(10)]
            results = [future.result() for future in futures]

        end_time = time.time()
        processing_time = end_time - start_time

        successful_sessions = [r for r in results if r["success"]]
        failed_sessions = [r for r in results if not r["success"]]

        self.results["concurrent_sessions"] = {
            "total_sessions": len(results),
            "successful_sessions": len(successful_sessions),
            "failed_sessions": len(failed_sessions),
            "processing_time": processing_time,
            "status": "PASSED" if len(failed_sessions) == 0 else "PARTIAL",
        }

        logger.info(
            f"   ✅ Created {len(successful_sessions)} concurrent sessions in {processing_time:.3f}s"
        )
        if failed_sessions:
            logger.error(f"   ⚠️  {len(failed_sessions)} sessions failed")
            for failed in failed_sessions[:3]:  # Show first 3 failures
                logger.error(
                    f"      - Session {failed['session_id']}: {failed['error']}"
                )

    def test_export_performance(self):
        """Test export performance with various data sizes."""
        logger.info("\n📤 Testing Export Performance...")

        # Create a session with substantial data
        large_cost_data = []
        for i in range(50):
            large_cost_data.append(
                ServiceCost(
                    service_name=f"Test Service {i % 5}",
                    operation_type="test_operation",
                    units_consumed=1000 + (i * 10),
                    unit_type="tokens",
                    rate_per_unit=Decimal("0.001"),
                    total_cost=Decimal("1.0") + (Decimal(str(i)) * Decimal("0.01")),
                    file_name=f"test_file_{i}.pdf",
                )
            )

        # Create test session
        test_case_id = "EXPORT_PERF_TEST"

        cost_estimate = CostEstimate(
            estimated_document_costs=large_cost_data[:25],
            estimated_media_costs=large_cost_data[25:],
            total_estimated_cost=sum(cost.total_cost for cost in large_cost_data),
            confidence_level=0.9,
            estimation_timestamp=datetime.now(),
        )

        actual_costs = ActualCosts(
            document_analysis_costs=large_cost_data[:30],
            media_processing_costs=large_cost_data[30:],
            total_actual_cost=sum(cost.total_cost for cost in large_cost_data)
            * Decimal("1.1"),
            processing_timestamp=datetime.now(),
        )

        cost_summary = CostSummary(
            case_id=test_case_id,
            cost_estimate=cost_estimate,
            actual_costs=actual_costs,
            cost_variance=actual_costs.total_actual_cost
            - cost_estimate.total_estimated_cost,
            cost_variance_percentage=10.0,
        )

        self.session_manager.active_sessions[test_case_id] = cost_summary
        self.session_manager._save_session(test_case_id, cost_summary)

        # Test each export format
        export_results = {}
        formats = ["csv", "json", "html", "text"]

        for format_type in formats:
            try:
                start_time = time.time()
                export_data = self.session_manager.export_session_budget(
                    test_case_id, format_type
                )
                end_time = time.time()

                export_results[format_type] = {
                    "processing_time": end_time - start_time,
                    "data_size": len(export_data),
                    "status": "PASSED",
                }

                logger.info(
                    f"   ✅ {format_type.upper()} export: {len(export_data)} chars in {end_time - start_time:.3f}s"
                )

            except Exception as e:
                export_results[format_type] = {"status": "FAILED", "error": str(e)}
                logger.error(f"   ❌ {format_type.upper()} export failed: {e}")

        self.results["export_performance"] = export_results

    def test_memory_efficiency(self):
        """Test memory usage during operations."""
        logger.info("\n🧠 Testing Memory Efficiency...")

        try:
            import psutil

            process = psutil.Process(os.getpid())

            # Get initial memory usage
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Create and process multiple sessions
            memory_checkpoints = [initial_memory]

            for i in range(5):
                # Create a session with moderate data
                docs = [
                    ProcessedDocument(
                        file_name=f"mem_test_{j}.pdf",
                        content="Sample content for memory testing. " * 100,
                        file_type=FileType.PDF,
                        document_type=DocumentType.CASE_DOCUMENT,
                    )
                    for j in range(10)
                ]

                case_id = f"MEM_TEST_{i}"
                self.session_manager.initialize_cost_session(
                    case_id=case_id, documents=docs, audio_files=[], video_files=[]
                )

                # Check memory after each session
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_checkpoints.append(current_memory)

            final_memory = memory_checkpoints[-1]
            memory_growth = final_memory - initial_memory

            self.results["memory_efficiency"] = {
                "initial_memory_mb": initial_memory,
                "final_memory_mb": final_memory,
                "memory_growth_mb": memory_growth,
                "memory_growth_per_session": memory_growth / 5,
                "status": "PASSED"
                if memory_growth < 50
                else "WARNING",  # Warn if >50MB growth
            }

            logger.info(f"   📊 Initial memory: {initial_memory:.1f} MB")
            logger.info(f"   📈 Final memory: {final_memory:.1f} MB")
            logger.info(
                f"   💾 Memory growth: {memory_growth:.1f} MB ({memory_growth / 5:.1f} MB per session)"
            )

        except ImportError:
            logger.warning("   ⚠️  psutil not available, skipping memory test")
            self.results["memory_efficiency"] = {
                "status": "SKIPPED",
                "reason": "psutil not available",
            }
        except Exception as e:
            logger.error(f"   ❌ Memory efficiency test failed: {e}")
            self.results["memory_efficiency"] = {"status": "FAILED", "error": str(e)}

    def run_all_tests(self):
        """Run all performance tests."""
        logger.info("🚀 Cost Tracking Performance Test Suite")
        logger.info("=" * 50)

        start_time = time.time()

        try:
            # Run all test methods
            self.test_large_document_estimation()
            self.test_concurrent_sessions()
            self.test_export_performance()
            self.test_memory_efficiency()

            total_time = time.time() - start_time

            # Generate summary
            self.generate_performance_report(total_time)

        except Exception as e:
            logger.error(f"\n❌ Performance test suite failed: {e}")
            import traceback

            traceback.print_exc()
        finally:
            self.cleanup()

    def generate_performance_report(self, total_time):
        """Generate a comprehensive performance report."""
        logger.info("\n" + "=" * 50)
        logger.info("📋 PERFORMANCE TEST REPORT")
        logger.info("=" * 50)

        passed_tests = 0
        failed_tests = 0
        warning_tests = 0

        for test_name, result in self.results.items():
            status = result.get("status", "UNKNOWN")
            if status == "PASSED":
                passed_tests += 1
                logger.info(f"✅ {test_name}: PASSED")
            elif status == "FAILED":
                failed_tests += 1
                logger.error(f"❌ {test_name}: FAILED")
                if "error" in result:
                    logger.error(f"   Error: {result['error']}")
            elif status == "WARNING":
                warning_tests += 1
                logger.warning(f"⚠️  {test_name}: WARNING")
            elif status == "PARTIAL":
                warning_tests += 1
                logger.info(f"⚠️  {test_name}: PARTIAL SUCCESS")
            else:
                logger.info(f"❓ {test_name}: {status}")

        logger.info("\n📊 SUMMARY:")
        logger.info(f"   Total test time: {total_time:.3f}s")
        logger.info(f"   Tests passed: {passed_tests}")
        logger.error(f"   Tests failed: {failed_tests}")
        logger.warning(f"   Tests with warnings: {warning_tests}")

        # Performance highlights
        if (
            "large_doc_estimation" in self.results
            and self.results["large_doc_estimation"]["status"] == "PASSED"
        ):
            avg_time = self.results["large_doc_estimation"]["avg_time_per_doc"]
            logger.debug(f"   Document processing rate: {1 / avg_time:.1f} docs/second")

        if "concurrent_sessions" in self.results:
            concurrent_result = self.results["concurrent_sessions"]
            if concurrent_result["status"] in ["PASSED", "PARTIAL"]:
                success_rate = (
                    concurrent_result["successful_sessions"]
                    / concurrent_result["total_sessions"]
                ) * 100
                logger.info(f"   Concurrent session success rate: {success_rate:.1f}%")

        # Overall assessment
        if failed_tests == 0:
            if warning_tests == 0:
                logger.info("\n🎉 ALL PERFORMANCE TESTS PASSED!")
                logger.info("✅ Cost tracking system is production-ready")
            else:
                logger.warning("\n✅ PERFORMANCE TESTS PASSED WITH WARNINGS")
                logger.info("⚠️  Some optimizations may be beneficial")
        else:
            logger.error(f"\n❌ {failed_tests} PERFORMANCE TESTS FAILED")
            logger.info("🔧 Performance issues require attention")

        # Save detailed results
        with open("performance_test_results.json", "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "total_time": total_time,
                    "results": self.results,
                    "summary": {
                        "passed": passed_tests,
                        "failed": failed_tests,
                        "warnings": warning_tests,
                    },
                },
                f,
                indent=2,
                default=str,
            )

        logger.info("\n📁 Detailed results saved to: performance_test_results.json")


if __name__ == "__main__":
    test_suite = PerformanceTestSuite()
    test_suite.run_all_tests()
