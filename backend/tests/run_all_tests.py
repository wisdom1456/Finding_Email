#!/usr/bin/env python3
"""
Master Test Runner for Legal Document Analysis
Runs comprehensive tests for all three client cases and generates a summary report.
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import json

# Test configurations
TESTS = [
    {
        "name": "Badam Test",
        "client": "Balaji Badam",
        "case_type": "Landlord-Tenant Eviction",
        "script": "test_badam_comprehensive.py",
        "expected_docs": "~20 documents (leases, eviction notices, communications)"
    },
    {
        "name": "Price Test", 
        "client": "Clifton Price",
        "case_type": "Property Damage - Water Intrusion",
        "script": "test_price_comprehensive.py",
        "expected_docs": "~15+ documents (emails, photos, maintenance records)"
    },
    {
        "name": "Velasco Test",
        "client": "Miguel & Rachael Velasco", 
        "case_type": "Property Damage - Flooding",
        "script": "test_velasco_comprehensive.py",
        "expected_docs": "~6 documents (disclosure, estimates, flood evidence)"
    }
]

def print_banner(title: str) -> None:
    """Print a formatted banner for section headers."""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def print_test_header(test_info: Dict[str, str]) -> None:
    """Print test information header."""
    print(f"\n🧪 TEST: {test_info['name']}")
    print(f"👤 Client: {test_info['client']}")
    print(f"⚖️  Case Type: {test_info['case_type']}")
    print(f"📁 Expected: {test_info['expected_docs']}")
    print("-" * 60)

def run_single_test(test_info: Dict[str, str]) -> Dict[str, Any]:
    """Run a single test and capture results."""
    print_test_header(test_info)
    
    start_time = time.time()
    script_path = Path(__file__).parent / test_info["script"]
    
    try:
        # Run the test script
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        duration = time.time() - start_time
        
        # Parse the output for key metrics
        output_lines = result.stdout.split('\n')
        
        test_result = {
            "test_name": test_info["name"],
            "client": test_info["client"],
            "case_type": test_info["case_type"],
            "duration": duration,
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "metrics": extract_metrics_from_output(output_lines)
        }
        
        if result.returncode == 0:
            print(f"✅ {test_info['name']} completed successfully in {duration:.1f}s")
        else:
            print(f"❌ {test_info['name']} failed after {duration:.1f}s")
            print(f"Error: {result.stderr}")
        
        return test_result
        
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        print(f"⏰ {test_info['name']} timed out after {duration:.1f}s")
        return {
            "test_name": test_info["name"],
            "client": test_info["client"],
            "case_type": test_info["case_type"],
            "duration": duration,
            "success": False,
            "error": "Timeout",
            "metrics": {}
        }
    except Exception as e:
        duration = time.time() - start_time
        print(f"💥 {test_info['name']} crashed: {e}")
        return {
            "test_name": test_info["name"],
            "client": test_info["client"],
            "case_type": test_info["case_type"], 
            "duration": duration,
            "success": False,
            "error": str(e),
            "metrics": {}
        }

def extract_metrics_from_output(output_lines: List[str]) -> Dict[str, Any]:
    """Extract key metrics from test output."""
    metrics = {}
    
    for line in output_lines:
        # Extract document counts
        if "Documents processed:" in line:
            try:
                metrics["documents_processed"] = int(line.split(":")[-1].strip())
            except:
                pass
        
        # Extract email length
        if "Email generated:" in line and "characters" in line:
            try:
                text = line.split(":")[-1].strip()
                metrics["email_length"] = int(text.split()[0].replace(",", ""))
            except:
                pass
        
        # Extract download files count
        if "Download files:" in line:
            try:
                metrics["download_files"] = int(line.split(":")[-1].strip())
            except:
                pass
        
        # Extract error count
        if "Errors encountered:" in line:
            try:
                metrics["errors"] = int(line.split(":")[-1].strip())
            except:
                pass
        
        # Extract payload size
        if "Total payload size:" in line and "MB" in line:
            try:
                text = line.split("(")[-1].split("MB")[0].strip()
                metrics["payload_mb"] = float(text)
            except:
                pass
    
    return metrics

def generate_summary_report(results: List[Dict[str, Any]]) -> None:
    """Generate a comprehensive summary report."""
    print_banner("📊 COMPREHENSIVE TEST SUMMARY REPORT")
    
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r["success"])
    failed_tests = total_tests - successful_tests
    
    print(f"📅 Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🧪 Total Tests: {total_tests}")
    print(f"✅ Successful: {successful_tests}")
    print(f"❌ Failed: {failed_tests}")
    print(f"📊 Success Rate: {(successful_tests/total_tests)*100:.1f}%")
    
    # Individual test results
    print(f"\n📋 Individual Test Results:")
    for i, result in enumerate(results, 1):
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        duration = result["duration"]
        
        print(f"\n  {i}. {result['test_name']} - {status}")
        print(f"     Client: {result['client']}")
        print(f"     Case: {result['case_type']}")
        print(f"     Duration: {duration:.1f}s")
        
        if result["success"] and result["metrics"]:
            metrics = result["metrics"]
            if "documents_processed" in metrics:
                print(f"     Documents: {metrics['documents_processed']}")
            if "email_length" in metrics:
                print(f"     Email: {metrics['email_length']:,} characters")
            if "payload_mb" in metrics:
                print(f"     Payload: {metrics['payload_mb']:.1f} MB")
            if "errors" in metrics and metrics["errors"] > 0:
                print(f"     ⚠️  Errors: {metrics['errors']}")
        elif not result["success"]:
            error = result.get("error", "Unknown error")
            print(f"     Error: {error}")
    
    # Aggregate metrics for successful tests
    successful_results = [r for r in results if r["success"]]
    if successful_results:
        print(f"\n📊 Aggregate Metrics (Successful Tests):")
        
        total_docs = sum(r["metrics"].get("documents_processed", 0) for r in successful_results)
        total_email_chars = sum(r["metrics"].get("email_length", 0) for r in successful_results)
        total_payload = sum(r["metrics"].get("payload_mb", 0) for r in successful_results)
        total_duration = sum(r["duration"] for r in successful_results)
        
        print(f"  📁 Total Documents Processed: {total_docs}")
        print(f"  📧 Total Email Characters: {total_email_chars:,}")
        print(f"  💾 Total Payload Size: {total_payload:.1f} MB")
        print(f"  ⏱️  Total Processing Time: {total_duration:.1f}s")
        
        if total_docs > 0:
            avg_chars_per_doc = total_email_chars / total_docs
            print(f"  📊 Average Email Length per Document: {avg_chars_per_doc:.0f} chars")
    
    # Quality indicators
    print(f"\n🔍 Quality Indicators:")
    for result in successful_results:
        metrics = result["metrics"]
        test_name = result["test_name"]
        
        # Email length assessment
        email_length = metrics.get("email_length", 0)
        if email_length > 0:
            if email_length < 1000:
                quality = "🟡 Short"
            elif email_length < 3000:
                quality = "🟢 Good"
            else:
                quality = "🟢 Comprehensive"
            
            print(f"  {test_name}: {quality} ({email_length:,} chars)")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    if failed_tests > 0:
        print(f"  🔧 Fix {failed_tests} failed test(s) before proceeding")
    
    if successful_tests > 0:
        print(f"  📧 Review generated emails for quality and professional tone")
        print(f"  📋 Verify all uploaded documents are properly referenced")
        print(f"  🎯 Check case-specific analysis for accuracy")
    
    print(f"  📝 Save test results for quality analysis iteration")

def save_results_summary(results: List[Dict[str, Any]]) -> None:
    """Save test results summary to file."""
    results_dir = Path(__file__).parent / "test_results"
    results_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_file = results_dir / f"test_summary_{timestamp}.json"
    
    summary_data = {
        "test_date": datetime.now().isoformat(),
        "total_tests": len(results),
        "successful_tests": sum(1 for r in results if r["success"]),
        "results": results
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, indent=2, default=str, ensure_ascii=False)
    
    print(f"\n💾 Results summary saved: {summary_file.name}")

def main():
    """Main test runner execution."""
    print_banner("🧪 LEGAL DOCUMENT ANALYSIS - COMPREHENSIVE TEST SUITE")
    print(f"📅 Test Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Testing all {len(TESTS)} client cases with full document sets")
    
    # Check if backend is running
    print(f"\n🔍 Pre-flight Checks:")
    print(f"  📡 Backend API: Assuming running on http://127.0.0.1:8000")
    print(f"  📁 Test Scripts: {len(TESTS)} test files prepared")
    print(f"  ⏱️  Timeout: 10 minutes per test")
    
    input(f"\n🚀 Press Enter to start comprehensive testing...")
    
    results = []
    
    # Run each test
    for i, test_info in enumerate(TESTS, 1):
        print_banner(f"RUNNING TEST {i}/{len(TESTS)}: {test_info['name']}")
        result = run_single_test(test_info)
        results.append(result)
        
        # Short pause between tests
        if i < len(TESTS):
            print(f"\n⏸️  Pausing 5 seconds before next test...")
            time.sleep(5)
    
    # Generate comprehensive report
    generate_summary_report(results)
    
    # Save results
    save_results_summary(results)
    
    print_banner("🎉 ALL TESTS COMPLETE")
    successful_tests = sum(1 for r in results if r["success"])
    
    if successful_tests == len(TESTS):
        print("✅ All tests passed! Ready for email quality analysis.")
    else:
        failed_count = len(TESTS) - successful_tests
        print(f"⚠️  {failed_count} test(s) failed. Review errors before proceeding.")
    
    print(f"\n📂 Check test_results/ directories for detailed outputs")
    print(f"📧 Review generated email content for quality assessment")

if __name__ == "__main__":
    main()