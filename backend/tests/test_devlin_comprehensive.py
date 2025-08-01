#!/usr/bin/env python3
"""
Comprehensive Test Suite for Erik Devlin Case
Tests the full document analysis pipeline with all available client documents.
"""

import sys
# Add the project root to the Python path
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))
import requests
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Any
from backend.tests.utils.email_comparator import EmailComparator

# --- Test Configuration ---
CONFIG_PATH = Path("test_results/devlin/config.json")

def load_config() -> Dict[str, Any]:
    """Load test configuration from JSON file."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

config = load_config()

# --- Constants from Config ---
API_URL = config["api_url"]
CLIENT_NAME = config["client_name"]
CASE_TYPE = config["case_type"]
CASE_REFERENCE = config["case_reference"]
INPUT_PATH = Path(config["input_path"])
OUTPUT_PATH = Path(config["output_path"])
REFERENCE_PATH = Path(config["reference_path"])
SUPPORTED_EXTENSIONS = set(config["supported_extensions"])
VIDEO_EXTENSIONS = set(config["video_extensions"])

# --- Test Utilities ---

def print_banner(title: str) -> None:
    """Print a formatted banner for section headers."""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def print_progress(current: int, total: int, description: str) -> None:
    """Print progress bar with description."""
    percentage = (current / total) * 100 if total > 0 else 0
    bar_length = 40
    filled_length = int(bar_length * current // total) if total > 0 else 0
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    print(f"\r[{bar}] {percentage:6.1f}% | {current}/{total} | {description}", end='', flush=True)

def ensure_output_directory() -> Path:
    """Create output directory if it doesn't exist."""
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    return OUTPUT_PATH

# --- Document Handling ---

def categorize_documents() -> Tuple[str, List[str]]:
    """
    Categorize documents into intake form and case documents.
    For testing purposes, only returns the intake form and ONE case document.
    Returns: (intake_form_path, case_document_paths)
    """
    print_banner(f"📁 DOCUMENT DISCOVERY - {CASE_REFERENCE} (TESTING MODE: 2 FILES ONLY)")
    
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Client documents directory not found: {INPUT_PATH}")
    
    all_files = [f for f in INPUT_PATH.iterdir() if f.is_file()]
    print(f"📂 Found {len(all_files)} total files in {INPUT_PATH.name}")
    
    supported_files = []
    skipped_files = []
    
    for file_path in all_files:
        if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            supported_files.append(file_path)
        elif file_path.suffix.lower() in VIDEO_EXTENSIONS:
            skipped_files.append(f"{file_path.name} (video)")
        else:
            skipped_files.append(f"{file_path.name} (unsupported)")
    
    print(f"✅ Supported files: {len(supported_files)}")
    print(f"⏭️  Skipped files: {len(skipped_files)}")
    
    if skipped_files:
        print("\n📋 Skipped Files:")
        for i, skipped in enumerate(skipped_files, 1):
            print(f"  {i:2d}. {skipped}")
    
    intake_form = None
    intake_patterns = ["Intake for Contractor Dispute", "Intake (General)", "Intake Form"]
    for pattern in intake_patterns:
        for file_path in supported_files:
            if pattern in file_path.name:
                intake_form = str(file_path)
                break
        if intake_form:
            break
            
    if not intake_form:
        for file_path in supported_files:
            if "intake" in file_path.name.lower():
                intake_form = str(file_path)
                break
    
    if not intake_form:
        raise FileNotFoundError("No intake form found in client documents")
    
    # TESTING MODE: Only use ONE case document instead of all
    all_case_documents = [str(f) for f in supported_files if str(f) != intake_form]
    
    if all_case_documents:
        # Take the first case document for testing
        case_documents = [all_case_documents[0]]
        print(f"\n🧪 TESTING MODE: Using only 1 of {len(all_case_documents)} available case documents")
    else:
        case_documents = []
    
    print(f"\n📄 INTAKE FORM: {Path(intake_form).name}")
    print(f"📁 CASE DOCUMENTS: {len(case_documents)} files (limited for testing)")
    
    if case_documents:
        print("\n📋 Case Documents (Testing Set):")
        for i, doc_path in enumerate(case_documents, 1):
            doc_name = Path(doc_path).name
            file_size = Path(doc_path).stat().st_size
            print(f"  {i:2d}. {doc_name} ({file_size:,} bytes)")
    
    return intake_form, case_documents

def read_file_content(file_path: str) -> Tuple[bytes, str]:
    """Read file content and determine MIME type."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        ext = Path(file_path).suffix.lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.txt': 'text/plain',
            '.eml': 'message/rfc822',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png'
        }
        
        mime_type = mime_types.get(ext, 'application/octet-stream')
        return content, mime_type
        
    except Exception as e:
        raise Exception(f"Error reading file {file_path}: {e}")

# --- Test Orchestration ---

def prepare_test_data() -> List[Tuple[str, Tuple[str, bytes, str]]]:
    """Prepare all files for upload with progress tracking."""
    print_banner("📦 PREPARING TEST DATA")
    
    intake_form, case_documents = categorize_documents()
    total_files = 1 + len(case_documents)
    files_data = []
    
    print(f"\n🔄 Loading {total_files} files...")
    
    # Load intake form
    print_progress(0, total_files, "Loading intake form...")
    try:
        content, mime_type = read_file_content(intake_form)
        files_data.append(
            ('intake_form', (Path(intake_form).name, content, mime_type))
        )
        print_progress(1, total_files, f"Loaded: {Path(intake_form).name}")
    except Exception as e:
        print(f"\n❌ Failed to load intake form: {e}")
        return []
    
    # Load case documents
    for i, doc_path in enumerate(case_documents, 1):
        try:
            print_progress(i, total_files, f"Loading: {Path(doc_path).name}")
            content, mime_type = read_file_content(doc_path)
            files_data.append(
                ('case_documents', (Path(doc_path).name, content, mime_type))
            )
            print_progress(i + 1, total_files, f"Loaded: {Path(doc_path).name}")
        except Exception as e:
            print(f"\n⚠️  Failed to load {Path(doc_path).name}: {e}")
            continue
    
    print(f"\n✅ Successfully prepared {len(files_data)} files for upload")
    
    total_size = sum(len(data[1][1]) for data in files_data)
    print(f"📊 Total payload size: {total_size:,} bytes ({total_size / 1_048_576:.1f} MB)")
    
    return files_data

def send_request(files_data: List[Tuple[str, Tuple[str, bytes, str]]]) -> Dict[str, Any]:
    """Send request to API with progress tracking."""
    print_banner("🚀 SENDING API REQUEST")
    
    print(f"🌐 Endpoint: {API_URL}")
    print(f"📁 Files: {len(files_data)}")
    print(f"⏱️  Timeout: 300 seconds")
    
    start_time = time.time()
    
    try:
        print("\n🔄 Sending request...")
        response = requests.post(API_URL, files=files_data, timeout=300)
        
        duration = time.time() - start_time
        print(f"✅ Request completed in {duration:.1f} seconds")
        
        if response.status_code == 200:
            print(f"✅ Success! Status: {response.status_code}")
            return response.json()
        else:
            print(f"❌ Request failed! Status: {response.status_code}")
            print(f"Response: {response.text}")
            return {"error": f"HTTP {response.status_code}", "details": response.text}
            
    except requests.exceptions.Timeout:
        print(f"⏰ Request timed out after 300 seconds")
        return {"error": "Timeout", "details": "Request exceeded 300 second timeout"}
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")
        return {"error": "Request failed", "details": str(e)}

# --- Validation Pipeline ---

def validate_response(response: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    Basic validation pipeline for the API response.
    Returns a dictionary with validation results and the generated email content.
    """
    print_banner("VALIDATION PIPELINE")
    validation_results = {"overall_status": "PASS", "checks": []}
    email_content = None

    # 1. Document Intake Validation
    try:
        validate_document_intake(response, validation_results)
    except Exception as e:
        validation_results["checks"].append({"check": "Document Intake", "status": "FAIL", "details": str(e)})
        validation_results["overall_status"] = "FAIL"

    # 2. AI Analysis Validation
    try:
        validate_ai_analysis(response, validation_results)
    except Exception as e:
        validation_results["checks"].append({"check": "AI Analysis", "status": "FAIL", "details": str(e)})
        validation_results["overall_status"] = "FAIL"

    # 3. File Generation Validation
    try:
        validate_file_generation(response, validation_results)
    except Exception as e:
        validation_results["checks"].append({"check": "File Generation", "status": "FAIL", "details": str(e)})
        validation_results["overall_status"] = "FAIL"
        
    # 4. Email Comparison
    try:
        email_content = validate_email_comparison(response, validation_results)
    except Exception as e:
        validation_results["checks"].append({"check": "Email Comparison", "status": "FAIL", "details": str(e)})
        validation_results["overall_status"] = "FAIL"

    return validation_results, email_content

def validate_document_intake(response: Dict[str, Any], results: Dict[str, Any]):
    """Validate the document intake part of the analysis."""
    print("  - Validating Document Intake...")
    intake_check = {"check": "Document Intake", "status": "PASS", "details": []}
    
    analysis = response.get("analysis", {})
    intake_analysis = analysis.get("intake_analysis", {})
    
    if not intake_analysis:
        intake_check["status"] = "FAIL"
        intake_check["details"].append("Missing 'intake_analysis' section.")
    else:
        if intake_analysis.get("client_name") != CLIENT_NAME:
            intake_check["status"] = "FAIL"
            intake_check["details"].append(f"Client name mismatch. Expected: {CLIENT_NAME}, Got: {intake_analysis.get('client_name')}")
        if intake_analysis.get("case_type") != CASE_TYPE:
            intake_check["status"] = "FAIL"
            intake_check["details"].append(f"Case type mismatch. Expected: {CASE_TYPE}, Got: {intake_analysis.get('case_type')}")

    if not intake_check["details"]:
        intake_check["details"].append("Intake analysis section is valid.")
        
    results["checks"].append(intake_check)
    if intake_check["status"] == "FAIL":
        results["overall_status"] = "FAIL"

def validate_ai_analysis(response: Dict[str, Any], results: Dict[str, Any]):
    """Validate the AI-driven analysis components."""
    print("  - Validating AI Analysis...")
    ai_check = {"check": "AI Analysis", "status": "PASS", "details": []}
    
    analysis = response.get("analysis", {})
    if not analysis:
        ai_check["status"] = "FAIL"
        ai_check["details"].append("Missing 'analysis' section.")
    else:
        if not analysis.get("case_analyses"):
            ai_check["status"] = "FAIL"
            ai_check["details"].append("Missing 'case_analyses' data.")
        if not analysis.get("legal_assessment"):
            ai_check["status"] = "FAIL"
            ai_check["details"].append("Missing 'legal_assessment' data.")

    if not ai_check["details"]:
        ai_check["details"].append("AI analysis components are present.")

    results["checks"].append(ai_check)
    if ai_check["status"] == "FAIL":
        results["overall_status"] = "FAIL"
        
def validate_file_generation(response: Dict[str, Any], results: Dict[str, Any]):
    """Validate the file generation and download links."""
    print("  - Validating File Generation...")
    file_gen_check = {"check": "File Generation", "status": "PASS", "details": []}

    email = response.get("email", {})
    if not email.get("download_links"):
        file_gen_check["status"] = "FAIL"
        file_gen_check["details"].append("Missing 'download_links'.")
    
    if not email.get("case_analysis_text"):
        file_gen_check["status"] = "FAIL"
        file_gen_check["details"].append("Missing 'case_analysis_text'.")

    if not file_gen_check["details"]:
        file_gen_check["details"].append("File generation components are present.")
        
    results["checks"].append(file_gen_check)
    if file_gen_check["status"] =="FAIL":
         results["overall_status"] = "FAIL"

def validate_email_comparison(response: Dict[str, Any], results: Dict[str, Any]):
    """Compare the generated email with the reference email."""
    print("  - Validating Email Comparison...")
    comparison_check = {"check": "Email Comparison", "status": "PASS", "details": []}
    
    try:
        reference_email_path = REFERENCE_PATH / "reference_email.rtf"
        generated_email_content = response.get("email", {}).get("case_analysis_text")

        if not reference_email_path.exists():
            raise FileNotFoundError(f"Reference email not found at {reference_email_path}")

        if not generated_email_content:
            comparison_check["status"] = "FAIL"
            comparison_check["details"].append("No generated email content to compare.")
        else:
            comparator = EmailComparator(str(reference_email_path), generated_email_content)
            comparison_results, processed_content = comparator.compare()
            
            if comparison_results.get('substance', {}).get('score', 0) < 0.8:
                comparison_check["status"] = "WARNING"
                comparison_check["details"].append(f"Substance similarity score is low: {comparison_results.get('substance', {}).get('score', 0):.2f}")

            comparison_check["details"].append(comparator.get_results_as_json())
            
    except Exception as e:
        comparison_check["status"] = "FAIL"
        comparison_check["details"].append(f"An error occurred during email comparison: {e}")

    results["checks"].append(comparison_check)
    if comparison_check["status"] in ["FAIL", "WARNING"]:
        results["overall_status"] = "FAIL"
# --- Main Execution ---

def analyze_and_save(result: Dict[str, Any]) -> None:
    """Analyze the response and save all relevant artifacts."""
    print_banner("📊 RESPONSE ANALYSIS & SAVING")
    
    output_dir = ensure_output_directory()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save full JSON response
    json_file = output_dir / f"response_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    print(f"📄 Full response saved: {json_file.name}")
    
    # Perform validation and get email content
    validation_results, email_content = validate_response(result)
    validation_file = output_dir / f"validation_{timestamp}.json"
    with open(validation_file, 'w', encoding='utf-8') as f:
        json.dump(validation_results, f, indent=2, default=str, ensure_ascii=False)
    print(f"✔️ Validation results saved: {validation_file.name}")

    # Save email content only if it exists
    if email_content:
        email_file = output_dir / f"email_content_{timestamp}.txt"
        try:
            with open(email_file, 'w', encoding='utf-8') as f:
                f.write(email_content)
            print(f"📧 Email content saved: {email_file.name}")
        except TypeError:
            print(f"⚠️  Could not save email content because it is not a string.")
    
    print(f"\n\n-LL-ANALYSIS-COMPLETE-\n")
    
    if validation_results["overall_status"] == "FAIL":
        print("\n❌ VALIDATION FAILED")
        for check in validation_results["checks"]:
            if check["status"] == "FAIL":
                # Ensure details are properly formatted for printing
                details_str = ', '.join(map(str, check.get("details", [])))
                print(f"  - {check['check']}: {details_str}")
    else:
        print("\n✅ VALIDATION PASSED")

def main():
    """Main test execution function."""
    print_banner(f"🧪 COMPREHENSIVE TEST SUITE - {CASE_REFERENCE}")
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Case Type: {CASE_TYPE}")
    
    try:
        # Step 1: Prepare test data
        files_data = prepare_test_data()
        if not files_data:
            print("❌ Failed to prepare test data. Exiting.")
            return

        # Step 2: Send API request
        result = send_request(files_data)
        
        # Step 3: Analyze response and save
        analyze_and_save(result)
        
        # Step 4: Final summary
        print_banner("🎉 TEST SETUP COMPLETE")
        print("Test infrastructure is ready and the test has been executed.")

    except Exception as e:
        print(f"\n💥 FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()