#!/usr/bin/env python3
"""
Comprehensive Test Suite for Clifton Price Case
Tests the full document analysis pipeline with all available client documents.
Water intrusion/property maintenance case.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Configuration
API_URL = "http://127.0.0.1:8000/api/v1/analysis/full-pipeline"
CLIENT_NAME = "Price, Clifton"
CASE_TYPE = "Property Damage - Water Intrusion"

# Base paths
BASE_PATH = Path(__file__).parent.parent.parent  # Go up to project root
CLIENT_BASE = BASE_PATH / "samples" / "Price, Clifton [MetLife]"
INTAKE_PATH = BASE_PATH / "samples" / "Intake (General) - Clifton Price.pdf"
DOCUMENTS_PATH = (
    CLIENT_BASE / "Shared Folder with Client" / "Shared with Bernhardt Riley"
)
RESULTS_PATH = BASE_PATH / "backend" / "tests" / "test_results" / "price"

# Supported file types (excluding video files)
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".eml",
    ".jpg",
    ".jpeg",
    ".png",
}
VIDEO_EXTENSIONS = {".mov", ".mp4", ".avi", ".mkv", ".wmv"}


def print_banner(title: str) -> None:
    """Print a formatted banner for section headers."""
logger.info('\n' + '=' * 80)
logger.info(f'  {title}')
logger.info('=' * 80)


def print_progress(current: int, total: int, description: str) -> None:
    """Print progress bar with description."""
    percentage = (current / total) * 100 if total > 0 else 0
    bar_length = 40
    filled_length = int(bar_length * current // total) if total > 0 else 0
    bar = "█" * filled_length + "-" * (bar_length - filled_length)
logger.info(f'\r[{bar}] {percentage:6.1f}% | {current}/{total} | {description}')
        f"\r[{bar}] {percentage:6.1f}% | {current}/{total} | {description}",
        end="",
        flush=True,
    )


def ensure_results_directory() -> Path:
    """Create results directory if it doesn't exist."""
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)
    return RESULTS_PATH


def discover_documents() -> tuple[str, list[str]]:
    """
    Discover all documents for Clifton Price case.
    Returns: (intake_form_path, case_document_paths)
    """
    print_banner(f"📁 DOCUMENT DISCOVERY - {CLIENT_NAME}")

    # Check intake form
    if not INTAKE_PATH.exists():
        msg = f"Intake form not found: {INTAKE_PATH}"
        raise FileNotFoundError(msg)

logger.info(f'📄 INTAKE FORM: {INTAKE_PATH.name}')

    # Discover case documents from multiple folders
    case_documents = []
    folders_to_scan = [
        "Emails",
        "2024 Pictures Videos",
        "2025 Pictures Videos",
        "Concrobium",
        "Intake and Timeline",
        "Lease",
        "Texts",
        "Work Orders",
    ]

logger.info('📂 Scanning client document folders...')

    total_files = 0
    supported_files = 0
    skipped_files = []

    for folder_name in folders_to_scan:
        folder_path = DOCUMENTS_PATH / folder_name
        if folder_path.exists():
logger.info(f'\n📁 Scanning: {folder_name}/')

            # Recursively find all files in this folder
            for file_path in folder_path.rglob("*"):
                if file_path.is_file():
                    total_files += 1

                    if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                        case_documents.append(str(file_path))
                        supported_files += 1
logger.info(f'  ✅ {file_path.name}')
                    elif file_path.suffix.lower() in VIDEO_EXTENSIONS:
                        skipped_files.append(f"{file_path.name} (video)")
logger.warning(f'  ⏭️  {file_path.name} (video - skipped)')
                    else:
                        skipped_files.append(f"{file_path.name} (unsupported)")
logger.info(f'  ❓ {file_path.name} (unsupported)')
        else:
logger.info(f'⚠️  Folder not found: {folder_name}')

logger.info('\n📊 DISCOVERY SUMMARY:')
logger.info(f'  📁 Total files found: {total_files}')
logger.info(f'  ✅ Supported files: {supported_files}')
logger.warning(f'  ⏭️  Skipped files: {len(skipped_files)}')

    if skipped_files:
logger.warning('\n📋 Skipped Files:')
        for i, skipped in enumerate(skipped_files[:10], 1):  # Show first 10
logger.warning(f'  {i:2d}. {skipped}')
        if len(skipped_files) > 10:
logger.warning(f'  ... and {len(skipped_files) - 10} more')

logger.info(f'\n📄 INTAKE FORM: {INTAKE_PATH.name}')
logger.info(f'📁 CASE DOCUMENTS: {len(case_documents)} files')

    # Group documents by type for better overview
    doc_types = {}
    for doc_path in case_documents:
        folder = Path(doc_path).parent.name
        if folder not in doc_types:
            doc_types[folder] = []
        doc_types[folder].append(Path(doc_path).name)

logger.info('\n📋 Documents by Category:')
    for folder, files in doc_types.items():
logger.info(f'  📁 {folder}: {len(files)} files')
        for file in files[:3]:  # Show first 3 files
logger.info(f'    • {file}')
        if len(files) > 3:
logger.info(f'    ... and {len(files) - 3} more')

    return str(INTAKE_PATH), case_documents


def read_file_content(file_path: str) -> tuple[bytes, str]:
    """Read file content and determine MIME type."""
    try:
        with open(file_path, "rb") as f:
            content = f.read()

        # Determine MIME type based on extension
        ext = Path(file_path).suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".txt": "text/plain",
            ".eml": "message/rfc822",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }

        mime_type = mime_types.get(ext, "application/octet-stream")
        return content, mime_type

    except Exception as e:
        msg = f"Error reading file {file_path}: {e}"
        raise Exception(msg)


def prepare_test_data() -> list[tuple[str, tuple[str, bytes, str]]]:
    """Prepare all files for upload with progress tracking."""
    print_banner("📦 PREPARING TEST DATA")

    intake_form, case_documents = discover_documents()
    total_files = 1 + len(case_documents)  # 1 intake + case docs
    files_data = []

logger.info(f'\n🔄 Loading {total_files} files...')

    # Load intake form
    print_progress(0, total_files, "Loading intake form...")
    try:
        content, mime_type = read_file_content(intake_form)
        files_data.append(("intake_form", (Path(intake_form).name, content, mime_type)))
        print_progress(1, total_files, f"Loaded: {Path(intake_form).name}")
    except Exception as e:
logger.error(f'\n❌ Failed to load intake form: {e}')
        return []

    # Load case documents with progress tracking
    for i, doc_path in enumerate(case_documents, 1):
        try:
            print_progress(i, total_files, f"Loading: {Path(doc_path).name}")
            content, mime_type = read_file_content(doc_path)
            files_data.append(
                ("case_documents", (Path(doc_path).name, content, mime_type))
            )
            print_progress(i + 1, total_files, f"Loaded: {Path(doc_path).name}")
        except Exception as e:
logger.error(f'\n⚠️  Failed to load {Path(doc_path).name}: {e}')
            continue

logger.info(f'\n✅ Successfully prepared {len(files_data)} files for upload')

    # Summary with file type breakdown
    file_types = {}
    total_size = 0

    for _, (filename, content, mime_type) in files_data:
        ext = Path(filename).suffix.lower()
        if ext not in file_types:
            file_types[ext] = {"count": 0, "size": 0}
        file_types[ext]["count"] += 1
        file_types[ext]["size"] += len(content)
        total_size += len(content)

logger.info('\n📊 File Type Breakdown:')
    for ext, info in file_types.items():
        size_mb = info["size"] / 1024 / 1024
logger.info(f'  {ext}: {info['count']} files ({size_mb:.1f} MB)')

logger.info(f'📊 Total payload size: {total_size:,} bytes ({total_size / 1024 / 1024:.1f} MB)')
        f"📊 Total payload size: {total_size:,} bytes ({total_size / 1024 / 1024:.1f} MB)"
    )

    return files_data


def send_request(
    files_data: list[tuple[str, tuple[str, bytes, str]]],
) -> dict[str, Any]:
    """Send request to API with progress tracking."""
    print_banner("🚀 SENDING API REQUEST")

logger.info(f'🌐 Endpoint: {API_URL}')
logger.info(f'📁 Files: {len(files_data)}')
logger.info('⏱️  Timeout: None (unlimited)')
logger.info(f'🎯 Case Type: {CASE_TYPE}')

    start_time = time.time()

    try:
logger.info('\n🔄 Sending request...')
        response = requests.post(API_URL, files=files_data, timeout=None)

        duration = time.time() - start_time
logger.info(f'✅ Request completed in {duration:.1f} seconds')

        if response.status_code == 200:
logger.info(f'✅ Success! Status: {response.status_code}')
            return response.json()
logger.error(f'❌ Request failed! Status: {response.status_code}')
logger.info(f'Response: {response.text}')
        return {"error": f"HTTP {response.status_code}", "details": response.text}

    except requests.exceptions.Timeout:
logger.info('⏰ Request timed out (this should not happen with timeout=None)')
        return {"error": "Timeout", "details": "Unexpected timeout occurred"}
    except requests.exceptions.RequestException as e:
logger.error(f'❌ Request error: {e}')
        return {"error": "Request failed", "details": str(e)}


def analyze_response(result: dict[str, Any]) -> dict[str, Any]:
    """Analyze the API response and extract key metrics."""
    print_banner("📊 RESPONSE ANALYSIS")

    if "error" in result:
logger.error(f'❌ Error Response: {result['error']}')
        if "details" in result:
logger.info(f'Details: {result['details']}')
        return {"status": "error", "error": result["error"]}

    analysis_data = {}

    # Check overall structure
    has_analysis = "analysis" in result
    has_email = "email" in result

logger.info('📋 Response Structure:')
logger.info(f'  ✅ Analysis section: {('Yes' if has_analysis else 'No')}')
logger.info(f'  ✅ Email section: {('Yes' if has_email else 'No')}')

    if has_analysis:
        analysis = result["analysis"]

        # Intake analysis
        if "intake_analysis" in analysis:
            intake = analysis["intake_analysis"]
logger.info('\n📄 Intake Analysis:')
logger.info(f'  👤 Client: {intake.get('client_name', 'N/A')}')
logger.info(f'  ⚖️  Case Type: {intake.get('case_type', 'N/A')}')
logger.info(f'  🚨 Urgency: {intake.get('urgency_level', 'N/A')}')

            # Look for water damage specific details
            key_facts = intake.get("key_facts", [])
            if key_facts:
logger.info(f'  📋 Key Facts ({len(key_facts)}):')
                for fact in key_facts[:3]:
logger.info(f'    • {fact}')
                if len(key_facts) > 3:
logger.info(f'    ... and {len(key_facts) - 3} more')

            analysis_data["intake"] = {
                "client_name": intake.get("client_name"),
                "case_type": intake.get("case_type"),
                "urgency": intake.get("urgency_level"),
                "key_facts_count": len(key_facts),
            }

        # Case document analyses
        if "case_analyses" in analysis:
            case_docs = analysis["case_analyses"]
logger.info(f'\n📁 Case Documents Analyzed: {len(case_docs)}')

            # Group by document type
            doc_types = {}
            for doc in case_docs:
                doc_type = doc.get("document_type", "Unknown")
                if doc_type not in doc_types:
                    doc_types[doc_type] = []
                doc_types[doc_type].append(doc)

            analysis_data["case_documents"] = []
logger.info('\n📊 Document Analysis by Type:')

            for doc_type, docs in doc_types.items():
logger.info(f'  📁 {doc_type}: {len(docs)} documents')
                for doc in docs[:2]:  # Show first 2 of each type
                    doc_title = doc.get("document_title", "Untitled")
                    summary_length = len(doc.get("summary", ""))
logger.info(f'    • {doc_title} ({summary_length} chars)')

                if len(docs) > 2:
logger.info(f'    ... and {len(docs) - 2} more')

                # Add to analysis data
                for doc in docs:
                    analysis_data["case_documents"].append(
                        {
                            "title": doc.get("document_title"),
                            "type": doc.get("document_type"),
                            "summary_length": len(doc.get("summary", "")),
                        }
                    )

        # Legal assessment
        if "legal_assessment" in analysis:
            legal = analysis["legal_assessment"]
logger.info('\n⚖️  Legal Assessment:')
logger.info(f'  📊 Claim Viability: {legal.get('claim_viability', 'N/A')}')
logger.info(f'  📈 Evidence Strength: {legal.get('evidence_strength', 'N/A')}')

            challenges = legal.get("potential_challenges", [])
            if challenges:
logger.info(f'  ⚠️  Potential Challenges ({len(challenges)}):')
                for challenge in challenges[:3]:
logger.info(f'    • {challenge}')
                if len(challenges) > 3:
logger.info(f'    ... and {len(challenges) - 3} more')

            recommendations = legal.get("recommended_actions", [])
            if recommendations:
logger.info(f'  💡 Recommendations ({len(recommendations)}):')
                for rec in recommendations[:3]:
logger.info(f'    • {rec}')
                if len(recommendations) > 3:
logger.info(f'    ... and {len(recommendations) - 3} more')

            analysis_data["legal_assessment"] = {
                "claim_viability": legal.get("claim_viability"),
                "evidence_strength": legal.get("evidence_strength"),
                "challenges_count": len(challenges),
                "recommendations_count": len(recommendations),
            }

    if has_email:
        email_response = result["email"]

logger.info('\n📧 Email Generation:')

        # Download links
        download_links = email_response.get("download_links", [])
logger.info(f'  💾 Download Links: {len(download_links)}')

        for link in download_links:
            file_name = link.get("file_name", "Unknown")
logger.info(f'    📎 {file_name}')

        # Case analysis text
        case_text = email_response.get("case_analysis_text", "")
logger.info(f'  📝 Case Analysis: {len(case_text)} characters')

        # Look for specific water damage terms in the email
        water_terms = ["water", "moisture", "intrusion", "damage", "mold", "leak"]
        term_counts = {term: case_text.lower().count(term) for term in water_terms}
        relevant_terms = {
            term: count for term, count in term_counts.items() if count > 0
        }

        if relevant_terms:
logger.info('  🔍 Case-Specific Terms Found:')
            for term, count in relevant_terms.items():
logger.info(f"    • '{term}': {count} mentions")

        analysis_data["email"] = {
            "download_links_count": len(download_links),
            "case_analysis_length": len(case_text),
            "files": [link.get("file_name") for link in download_links],
            "case_specific_terms": relevant_terms,
        }

    # Check for errors
    errors = result.get("errors", [])
    if "analysis" in result and "errors" in result["analysis"]:
        errors.extend(result["analysis"]["errors"])

    if errors:
logger.error(f'\n⚠️  Errors Found: {len(errors)}')
        for i, error in enumerate(errors, 1):
            source = error.get("source", "Unknown")
            message = error.get("error_message", "No message")
logger.info(f'  {i}. [{source}] {message}')

        analysis_data["errors"] = errors

    analysis_data["status"] = "success"
    return analysis_data


def save_results(result: dict[str, Any], analysis_data: dict[str, Any]) -> None:
    """Save test results to files."""
    print_banner("💾 SAVING RESULTS")

    results_dir = ensure_results_directory()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save full JSON response
    json_file = results_dir / f"response_{timestamp}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
logger.info(f'📄 Full response: {json_file.name}')

    # Save analysis summary
    summary_file = results_dir / f"analysis_{timestamp}.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(analysis_data, f, indent=2, default=str, ensure_ascii=False)
logger.info(f'📊 Analysis summary: {summary_file.name}')

    # Save email content if available
    if "email" in result and "case_analysis_text" in result["email"]:
        email_file = results_dir / f"email_content_{timestamp}.txt"
        with open(email_file, "w", encoding="utf-8") as f:
            f.write(result["email"]["case_analysis_text"])
logger.info(f'📧 Email content: {email_file.name}')

logger.info(f'📁 Results saved to: {results_dir}')


def main():
    """Main test execution function."""
    print_banner(f"🧪 COMPREHENSIVE TEST SUITE - {CLIENT_NAME}")
logger.info(f'📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}')
logger.info(f'🎯 Case Type: {CASE_TYPE}')

    try:
        # Step 1: Prepare test data
        files_data = prepare_test_data()
        if not files_data:
logger.error('❌ Failed to prepare test data. Exiting.')
            return

        # Step 2: Send API request
        result = send_request(files_data)

        # Step 3: Analyze response
        analysis_data = analyze_response(result)

        # Step 4: Save results
        save_results(result, analysis_data)

        # Step 5: Final summary
        print_banner("🎉 TEST COMPLETE")

        if analysis_data.get("status") == "success":
logger.info('✅ Test completed successfully!')

            # Quick stats specific to water damage case
            if "case_documents" in analysis_data:
                docs_count = len(analysis_data["case_documents"])
logger.info(f'📁 Documents processed: {docs_count}')

            if "email" in analysis_data:
                email_length = analysis_data["email"]["case_analysis_length"]
                links_count = analysis_data["email"]["download_links_count"]
logger.info(f'📧 Email generated: {email_length:,} characters')
logger.info(f'💾 Download files: {links_count}')

                # Show case-specific analysis
                terms = analysis_data["email"].get("case_specific_terms", {})
                if terms:
logger.info(f'🔍 Water damage terms found: {len(terms)} types')

            if "errors" in analysis_data:
                error_count = len(analysis_data["errors"])
logger.error(f'⚠️  Errors encountered: {error_count}')
        else:
logger.error('❌ Test failed!')

    except Exception as e:
logger.error(f'\n💥 FATAL ERROR: {e}')
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
