#!/usr/bin/env python3
"""
Reusable Test Framework for Comprehensive Case Analysis
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml

from backend.tests.utils.email_comparator import EmailComparator


class TestOrchestrator:
    """
    Orchestrates a comprehensive test for a given case.
    """

    def __init__(self, config_path: str) -> None:
        self.config = self._load_config(config_path)

        # --- Paths ---
        self.base_path = Path(config_path).parent
        self.input_path = self.base_path / self.config.get("input_dir", "input")
        self.output_path = self.base_path / self.config.get("output_dir", "output")
        self.reference_path = self.base_path / self.config.get(
            "reference_dir", "reference"
        )

        # --- Basic Info ---
        self.client_name = self.config["client_name"]
        self.case_type = self.config["case_type"]
        self.api_url = self.config["api_url"]

        # --- File Handling ---
        self.supported_extensions = set(self.config.get("supported_extensions", []))
        self.video_extensions = set(self.config.get("video_extensions", []))
        self.intake_patterns = self.config.get("intake_patterns", ["intake"])

    def _load_config(self, config_path: str) -> dict[str, Any]:
        """Load test configuration from YAML file."""
        if not Path(config_path).exists():
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)
        with open(config_path) as f:
            return yaml.safe_load(f)

    def run_test(self):
        """Main test execution function."""
        print_banner(f"🧪 COMPREHENSIVE TEST SUITE - {self.client_name}")
        print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 Case Type: {self.case_type}")

        try:
            files_data = self._prepare_test_data()
            if not files_data:
                print("❌ Failed to prepare test data. Exiting.")
                return

            result = self._send_request(files_data)
            self._analyze_and_save(result)

            print_banner("🎉 TEST RUN COMPLETE")

        except Exception as e:
            print(f"💥 FATAL ERROR: {e}")
            import traceback

            traceback.print_exc()

    def _prepare_test_data(self) -> list[tuple[str, tuple[str, bytes, str]]]:
        """Prepare all files for upload."""
        print_banner("📦 PREPARING TEST DATA")

        intake_form, case_documents = self._categorize_documents()
        total_files = 1 + len(case_documents)
        files_data = []

        print(f"🔄 Loading {total_files} files...")

        try:
            content, mime_type = read_file_content(intake_form)
            files_data.append(
                ("intake_form", (Path(intake_form).name, content, mime_type))
            )
        except Exception as e:
            print(f"❌ Failed to load intake form: {e}")
            return []

        for doc_path in case_documents:
            try:
                content, mime_type = read_file_content(doc_path)
                files_data.append(
                    ("case_documents", (Path(doc_path).name, content, mime_type))
                )
            except Exception as e:
                print(f"⚠️  Failed to load {Path(doc_path).name}: {e}")
                continue

        total_size = sum(len(data[1][1]) for data in files_data)
        print(f"✅ Prepared {len(files_data)} files ({total_size / 1_048_576:.1f} MB)")
        return files_data

    def _categorize_documents(self) -> tuple[str, list[str]]:
        """Categorize documents based on configuration."""
        print_banner(f"📁 DOCUMENT DISCOVERY - {self.client_name}")

        if not self.input_path.exists():
            msg = f"Client documents directory not found: {self.input_path}"
            raise FileNotFoundError(
                msg
            )

        all_files = [f for f in self.input_path.iterdir() if f.is_file()]
        supported_files = [
            f for f in all_files if f.suffix.lower() in self.supported_extensions
        ]

        intake_form = self._find_intake_form(supported_files)
        if not intake_form:
            msg = "No intake form found in client documents"
            raise FileNotFoundError(msg)

        case_documents = [str(f) for f in supported_files if str(f) != intake_form]

        print(f"📄 INTAKE FORM: {Path(intake_form).name}")
        print(f"📁 CASE DOCUMENTS: {len(case_documents)} files")
        return str(intake_form), case_documents

    def _find_intake_form(self, file_paths: list[Path]) -> str:
        """Find the intake form using configured patterns."""
        for pattern in self.intake_patterns:
            for file_path in file_paths:
                if pattern.lower() in file_path.name.lower():
                    return str(file_path)
        return ""

    def _send_request(
        self, files_data: list[tuple[str, tuple[str, bytes, str]]]
    ) -> dict[str, Any]:
        """Send request to the API."""
        print_banner(f"🚀 SENDING API REQUEST to {self.api_url}")

        start_time = time.time()
        try:
            response = requests.post(self.api_url, files=files_data, timeout=300)
            duration = time.time() - start_time
            print(
                f"✅ Request completed in {duration:.1f} seconds with status {response.status_code}"
            )

            return (
                response.json()
                if response.ok
                else {"error": f"HTTP {response.status_code}", "details": response.text}
            )
        except requests.exceptions.RequestException as e:
            print(f"❌ Request error: {e}")
            return {"error": "Request failed", "details": str(e)}

    def _analyze_and_save(self, result: dict[str, Any]) -> None:
        """Analyze the response and save artifacts."""
        print_banner("📊 RESPONSE ANALYSIS & SAVING")
        self.output_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save all artifacts
        self._save_json(result, f"response_{timestamp}.json")

        validation_results = self._validate_response(result)
        self._save_json(validation_results, f"validation_{timestamp}.json")

        if "email" in result and "case_analysis_text" in result["email"]:
            self._save_text(
                result["email"]["case_analysis_text"], f"email_content_{timestamp}.txt"
            )

        print(f"📁 Results saved to: {self.output_path}")

    def _validate_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Dynamically validate response based on config."""
        print_banner("VALIDATION PIPELINE")
        validation_results = {"overall_status": "PASS", "checks": []}

        validation_config = self.config.get("validation", {})
        for check_name, check_params in validation_config.items():
            validator_func_name = f"_validate_{check_name}"
            if hasattr(self, validator_func_name):
                try:
                    getattr(self, validator_func_name)(
                        response, validation_results, check_params
                    )
                except Exception as e:
                    validation_results["checks"].append(
                        {"check": check_name, "status": "FAIL", "details": str(e)}
                    )
                    validation_results["overall_status"] = "FAIL"

        return validation_results

    # --- Standard Validation Functions ---

    def _validate_document_intake(self, response, results, params):
        intake_check = {"check": "Document Intake", "status": "PASS", "details": []}
        intake_analysis = response.get("analysis", {}).get("intake_analysis", {})

        if not intake_analysis:
            intake_check["status"] = "FAIL"
            intake_check["details"].append("Missing 'intake_analysis' section.")
        else:
            if intake_analysis.get("client_name") != self.client_name:
                intake_check["status"] = "FAIL"
            if intake_analysis.get("case_type") != self.case_type:
                intake_check["status"] = "FAIL"
        results["checks"].append(intake_check)

    def _validate_email_comparison(self, response, results, params):
        comparison_check = {
            "check": "Email Comparison",
            "status": "PASS",
            "details": [],
        }
        try:
            reference_email_path = self.reference_path / params["reference_file"]
            generated_content = response.get("email", {}).get("case_analysis_text", "")

            if not generated_content:
                msg = "No generated email content to compare."
                raise ValueError(msg)

            comparator = EmailComparator(str(reference_email_path), generated_content)
            comp_results = comparator.compare()

            if comp_results["substance"]["score"] < params.get(
                "min_substance_score", 0.8
            ):
                comparison_check["status"] = "FAIL"

            comparison_check["details"] = comp_results
        except Exception as e:
            comparison_check["status"] = "FAIL"
            comparison_check["details"].append(f"Comparison error: {e}")

        results["checks"].append(comparison_check)

    def _save_json(self, data: dict[str, Any], filename: str) -> None:
        """Save dictionary as a JSON file."""
        path = self.output_path / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        print(f"📄 Saved: {filename}")

    def _save_text(self, content: str, filename: str) -> None:
        """Save text content to a file."""
        path = self.output_path / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"📧 Saved: {filename}")


# --- Helper Functions (can be moved to a separate utils file) ---


def print_banner(title: str) -> None:
    """Prints a formatted banner."""
    print(f"\n{'=' * 80}\n  {title}\n{'=' * 80}")


def read_file_content(file_path: str) -> tuple[bytes, str]:
    """Read file content and determine MIME type."""
    try:
        with open(file_path, "rb") as f:
            content = f.read()

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
        return content, mime_types.get(ext, "application/octet-stream")
    except Exception as e:
        msg = f"Error reading file {file_path}: {e}"
        raise OSError(msg)
