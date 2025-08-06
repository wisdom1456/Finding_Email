#!/usr/bin/env python3
"""
Comprehensive Test Suite for Miguel Velasco Case
Tests the full document analysis pipeline with all available client documents.
Property flooding/damage case.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


# Configuration
API_URL = "http://127.0.0.1:8000/api/v1/analysis/full-pipeline"
CLIENT_NAME = "Velasco, Miguel & Rachael"
CASE_TYPE = "Property Damage - Flooding"

# Base paths
BASE_PATH = Path(__file__).parent.parent.parent  # Go up to project root
CLIENT_BASE = BASE_PATH / "samples" / "Velasco, Miguel [MetLife]"
DOCUMENTS_PATH = (
    CLIENT_BASE / "Shared Folder with Client" / "Shared with Bernhardt Riley"
)
RESULTS_PATH = BASE_PATH / "backend" / "tests" / "test_results" / "velasco"

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
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_progress(current: int, total: int, description: str) -> None:
    """Print progress bar with description."""
    percentage = (current / total) * 100 if total > 0 else 0
    bar_length = 40
    filled_length = int(bar_length * current // total) if total > 0 else 0
    bar = "█" * filled_length + "-" * (bar_length - filled_length)
    print(
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
    Discover all documents for Miguel Velasco case.
    Note: Intake form is already in the client folder.
    Returns: (intake_form_path, case_document_paths)
    """
    print_banner(f"📁 DOCUMENT DISCOVERY - {CLIENT_NAME}")

    if not DOCUMENTS_PATH.exists():
        msg = f"Client documents directory not found: {DOCUMENTS_PATH}"
        raise FileNotFoundError(
            msg
        )

    print(f"📂 Scanning: {DOCUMENTS_PATH.name}")

    all_files = [f for f in DOCUMENTS_PATH.iterdir() if f.is_file()]
    print(f"📁 Found {len(all_files)} total files")

    # Filter by supported file types
    supported_files = []
    skipped_files = []

    for file_path in all_files:
        if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            supported_files.append(file_path)
            print(f"  ✅ {file_path.name}")
        elif file_path.suffix.lower() in VIDEO_EXTENSIONS:
            skipped_files.append(f"{file_path.name} (video)")
            print(f"  ⏭️  {file_path.name} (video - skipped)")
        else:
            skipped_files.append(f"{file_path.name} (unsupported)")
            print(f"  ❓ {file_path.name} (unsupported)")

    print("\n📊 DISCOVERY SUMMARY:")
    print(f"  ✅ Supported files: {len(supported_files)}")
    print(f"  ⏭️  Skipped files: {len(skipped_files)}")

    if skipped_files:
        print("\n📋 Skipped Files:")
        for i, skipped in enumerate(skipped_files, 1):
            print(f"  {i:2d}. {skipped}")

    # Identify intake form (should be "Intake - Miguel and Rachael.pdf")
    intake_form = None
    case_documents = []

    # Look for intake form patterns
    intake_patterns = ["Intake - Miguel and Rachael", "Intake"]
    for file_path in supported_files:
        for pattern in intake_patterns:
            if pattern in file_path.name:
                intake_form = str(file_path)
                break
        if intake_form:
            break

    if not intake_form:
        msg = "No intake form found in client documents"
        raise FileNotFoundError(msg)

    # All other supported files are case documents
    case_documents = [str(f) for f in supported_files if str(f) != intake_form]

    print(f"\n📄 INTAKE FORM: {Path(intake_form).name}")
    print(f"📁 CASE DOCUMENTS: {len(case_documents)} files")

    # List case documents with descriptions based on names
    if case_documents:
        print("\n📋 Case Documents:")
        for i, doc_path in enumerate(case_documents, 1):
            doc_name = Path(doc_path).name
            file_size = Path(doc_path).stat().st_size

            # Add context based on filename
            doc_type = "Unknown"
            if "disclosure" in doc_name.lower():
                doc_type = "Property Disclosure"
            elif "estimate" in doc_name.lower() or "insured" in doc_name.lower():
                doc_type = "Insurance Estimate"
            elif "flooding" in doc_name.lower() or "flood" in doc_name.lower():
                doc_type = "Flood Documentation"
            elif "issues" in doc_name.lower() or "explaining" in doc_name.lower():
                doc_type = "Issue Explanation"
            elif "screenshot" in doc_name.lower():
                doc_type = "Screenshot Evidence"

            print(f"  {i:2d}. {doc_name}")
            print(f"      Type: {doc_type}")
            print(f"      Size: {file_size:,} bytes")

    return intake_form, case_documents


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

    print(f"\n🔄 Loading {total_files} files...")

    # Load intake form
    print_progress(0, total_files, "Loading intake form...")
    try:
        content, mime_type = read_file_content(intake_form)
        files_data.append(("intake_form", (Path(intake_form).name, content, mime_type)))
        print_progress(1, total_files, f"Loaded: {Path(intake_form).name}")
    except Exception as e:
        print(f"\n❌ Failed to load intake form: {e}")
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
            print(f"\n⚠️  Failed to load {Path(doc_path).name}: {e}")
            continue

    print(f"\n✅ Successfully prepared {len(files_data)} files for upload")

    # Summary with file type breakdown and flooding case specifics
    file_types = {}
    total_size = 0
    flooding_docs = 0
    insurance_docs = 0

    for _, (filename, content, mime_type) in files_data:
        ext = Path(filename).suffix.lower()
        if ext not in file_types:
            file_types[ext] = {"count": 0, "size": 0}
        file_types[ext]["count"] += 1
        file_types[ext]["size"] += len(content)
        total_size += len(content)

        # Count case-specific document types
        if any(term in filename.lower() for term in ["flood", "water", "damage"]):
            flooding_docs += 1
        if any(term in filename.lower() for term in ["insurance", "estimate", "claim"]):
            insurance_docs += 1

    print("\n📊 File Type Breakdown:")
    for ext, info in file_types.items():
        size_mb = info["size"] / 1024 / 1024
        print(f"  {ext}: {info['count']} files ({size_mb:.1f} MB)")

    print("\n🏠 Case-Specific Documents:")
    print(f"  💧 Flooding evidence: {flooding_docs} files")
    print(f"  🏢 Insurance documents: {insurance_docs} files")

    print(
        f"📊 Total payload size: {total_size:,} bytes ({total_size / 1024 / 1024:.1f} MB)"
    )

    return files_data


def send_request(
    files_data: list[tuple[str, tuple[str, bytes, str]]],
) -> dict[str, Any]:
    """Send request to API with progress tracking."""
    print_banner("🚀 SENDING API REQUEST")

    print(f"🌐 Endpoint: {API_URL}")
    print(f"📁 Files: {len(files_data)}")
    print("⏱️  Timeout: 300 seconds")
    print(f"🎯 Case Type: {CASE_TYPE}")

    start_time = time.time()

    try:
        print("\n🔄 Sending request...")
        response = requests.post(API_URL, files=files_data, timeout=300)

        duration = time.time() - start_time
        print(f"✅ Request completed in {duration:.1f} seconds")

        if response.status_code == 200:
            print(f"✅ Success! Status: {response.status_code}")
            return response.json()
        print(f"❌ Request failed! Status: {response.status_code}")
        print(f"Response: {response.text}")
        return {"error": f"HTTP {response.status_code}", "details": response.text}

    except requests.exceptions.Timeout:
        print("⏰ Request timed out after 300 seconds")
        return {"error": "Timeout", "details": "Request exceeded 300 second timeout"}
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")
        return {"error": "Request failed", "details": str(e)}


def analyze_response(result: dict[str, Any]) -> dict[str, Any]:
    """Analyze the API response and extract key metrics."""
    print_banner("📊 RESPONSE ANALYSIS")

    if "error" in result:
        print(f"❌ Error Response: {result['error']}")
        if "details" in result:
            print(f"Details: {result['details']}")
        return {"status": "error", "error": result["error"]}

    analysis_data = {}

    # Check overall structure
    has_analysis = "analysis" in result
    has_email = "email" in result

    print("📋 Response Structure:")
    print(f"  ✅ Analysis section: {'Yes' if has_analysis else 'No'}")
    print(f"  ✅ Email section: {'Yes' if has_email else 'No'}")

    if has_analysis:
        analysis = result["analysis"]

        # Intake analysis
        if "intake_analysis" in analysis:
            intake = analysis["intake_analysis"]
            print("\n📄 Intake Analysis:")
            print(f"  👥 Clients: {intake.get('client_name', 'N/A')}")
            print(f"  ⚖️  Case Type: {intake.get('case_type', 'N/A')}")
            print(f"  🚨 Urgency: {intake.get('urgency_level', 'N/A')}")

            # Look for flooding-specific details
            key_facts = intake.get("key_facts", [])
            if key_facts:
                print(f"  📋 Key Facts ({len(key_facts)}):")
                for fact in key_facts[:3]:
                    print(f"    • {fact}")
                if len(key_facts) > 3:
                    print(f"    ... and {len(key_facts) - 3} more")

            analysis_data["intake"] = {
                "client_name": intake.get("client_name"),
                "case_type": intake.get("case_type"),
                "urgency": intake.get("urgency_level"),
                "key_facts_count": len(key_facts),
            }

        # Case document analyses
        if "case_analyses" in analysis:
            case_docs = analysis["case_analyses"]
            print(f"\n📁 Case Documents Analyzed: {len(case_docs)}")

            analysis_data["case_documents"] = []

            # Analyze each document with flooding context
            for i, doc in enumerate(case_docs, 1):
                doc_title = doc.get("document_title", f"Document {i}")
                doc_type = doc.get("document_type", "Unknown")
                summary = doc.get("summary", "")
                summary_length = len(summary)

                print(f"  {i:2d}. {doc_title}")
                print(f"      Type: {doc_type}")
                print(f"      Summary: {summary_length} characters")

                # Look for flooding-related terms in summary
                flooding_terms = [
                    "flood",
                    "water",
                    "damage",
                    "moisture",
                    "insurance",
                    "estimate",
                ]
                term_counts = {
                    term: summary.lower().count(term) for term in flooding_terms
                }
                relevant_terms = {
                    term: count for term, count in term_counts.items() if count > 0
                }

                if relevant_terms:
                    print(f"      Key terms: {', '.join(relevant_terms.keys())}")

                analysis_data["case_documents"].append(
                    {
                        "title": doc_title,
                        "type": doc_type,
                        "summary_length": summary_length,
                        "flooding_terms": relevant_terms,
                    }
                )

        # Legal assessment
        if "legal_assessment" in analysis:
            legal = analysis["legal_assessment"]
            print("\n⚖️  Legal Assessment:")
            print(f"  📊 Claim Viability: {legal.get('claim_viability', 'N/A')}")
            print(f"  📈 Evidence Strength: {legal.get('evidence_strength', 'N/A')}")

            challenges = legal.get("potential_challenges", [])
            if challenges:
                print(f"  ⚠️  Potential Challenges ({len(challenges)}):")
                for challenge in challenges[:3]:
                    print(f"    • {challenge}")
                if len(challenges) > 3:
                    print(f"    ... and {len(challenges) - 3} more")

            recommendations = legal.get("recommended_actions", [])
            if recommendations:
                print(f"  💡 Recommendations ({len(recommendations)}):")
                for rec in recommendations[:3]:
                    print(f"    • {rec}")
                if len(recommendations) > 3:
                    print(f"    ... and {len(recommendations) - 3} more")

            analysis_data["legal_assessment"] = {
                "claim_viability": legal.get("claim_viability"),
                "evidence_strength": legal.get("evidence_strength"),
                "challenges_count": len(challenges),
                "recommendations_count": len(recommendations),
            }

    if has_email:
        email_response = result["email"]

        print("\n📧 Email Generation:")

        # Download links
        download_links = email_response.get("download_links", [])
        print(f"  💾 Download Links: {len(download_links)}")

        for link in download_links:
            file_name = link.get("file_name", "Unknown")
            print(f"    📎 {file_name}")

        # Case analysis text
        case_text = email_response.get("case_analysis_text", "")
        print(f"  📝 Case Analysis: {len(case_text)} characters")

        # Look for specific flooding/property damage terms in the email
        flooding_terms = [
            "flood",
            "water",
            "property",
            "damage",
            "insurance",
            "estimate",
            "disclosure",
        ]
        term_counts = {term: case_text.lower().count(term) for term in flooding_terms}
        relevant_terms = {
            term: count for term, count in term_counts.items() if count > 0
        }

        if relevant_terms:
            print("  🔍 Case-Specific Terms Found:")
            for term, count in relevant_terms.items():
                print(f"    • '{term}': {count} mentions")

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
        print(f"\n⚠️  Errors Found: {len(errors)}")
        for i, error in enumerate(errors, 1):
            source = error.get("source", "Unknown")
            message = error.get("error_message", "No message")
            print(f"  {i}. [{source}] {message}")

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
    print(f"📄 Full response: {json_file.name}")

    # Save analysis summary
    summary_file = results_dir / f"analysis_{timestamp}.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(analysis_data, f, indent=2, default=str, ensure_ascii=False)
    print(f"📊 Analysis summary: {summary_file.name}")

    # Save email content if available
    if "email" in result and "case_analysis_text" in result["email"]:
        email_file = results_dir / f"email_content_{timestamp}.txt"
        with open(email_file, "w", encoding="utf-8") as f:
            f.write(result["email"]["case_analysis_text"])
        print(f"📧 Email content: {email_file.name}")

    print(f"📁 Results saved to: {results_dir}")


def main():
    """Main test execution function."""
    print_banner(f"🧪 COMPREHENSIVE TEST SUITE - {CLIENT_NAME}")
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Case Type: {CASE_TYPE}")
    print("👥 Multiple Clients: Miguel & Rachael Velasco")

    try:
        # Step 1: Prepare test data
        files_data = prepare_test_data()
        if not files_data:
            print("❌ Failed to prepare test data. Exiting.")
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
            print("✅ Test completed successfully!")

            # Quick stats specific to flooding case
            if "case_documents" in analysis_data:
                docs_count = len(analysis_data["case_documents"])
                print(f"📁 Documents processed: {docs_count}")

                # Count flooding-specific documents
                flooding_docs = sum(
                    1
                    for doc in analysis_data["case_documents"]
                    if doc.get("flooding_terms")
                )
                print(f"💧 Flooding-related docs: {flooding_docs}")

            if "email" in analysis_data:
                email_length = analysis_data["email"]["case_analysis_length"]
                links_count = analysis_data["email"]["download_links_count"]
                print(f"📧 Email generated: {email_length:,} characters")
                print(f"💾 Download files: {links_count}")

                # Show case-specific analysis
                terms = analysis_data["email"].get("case_specific_terms", {})
                if terms:
                    total_terms = sum(terms.values())
                    print(f"🔍 Property damage terms: {total_terms} total mentions")

            if "errors" in analysis_data:
                error_count = len(analysis_data["errors"])
                print(f"⚠️  Errors encountered: {error_count}")
        else:
            print("❌ Test failed!")

    except Exception as e:
        print(f"\n💥 FATAL ERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
