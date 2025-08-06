"""
Unified Test Utilities Module

This module provides a centralized collection of testing utilities, fixtures,
and helper functions for the Legal Document Analysis Portal test suite.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Import data models for type hints
from backend.utils.data_models import (
    CaseAnalysisResult,
    DocumentType,
    EnhancedIntakeAnalysis,
    FileType,
    ProcessedDocument,
)


class TestUtils:
    """Collection of static utility methods for testing."""

    @staticmethod
    def create_temp_file(content: bytes = b"test content", suffix: str = ".txt") -> str:
        """Create a temporary file with specified content."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(content)
            return tmp_file.name

    @staticmethod
    def create_temp_env_file(env_vars: dict[str, str]) -> str:
        """Create a temporary .env file for testing."""
        content = "\n".join(f"{key}={value}" for key, value in env_vars.items())
        return TestUtils.create_temp_file(content.encode(), ".env")

    @staticmethod
    def cleanup_temp_file(file_path: str) -> None:
        """Clean up a temporary file."""
        if os.path.exists(file_path):
            os.remove(file_path)

    @staticmethod
    def create_mock_processed_document(
        filename: str = "test.pdf",
        content: str = "Test content",
        file_type: FileType = FileType.PDF,
        doc_type: DocumentType = DocumentType.CASE_DOCUMENT,
    ) -> ProcessedDocument:
        """Create a mock ProcessedDocument for testing."""
        return ProcessedDocument(
            file_name=filename,
            content=content,
            file_type=file_type,
            document_type=doc_type,
        )

    @staticmethod
    def create_mock_intake_analysis(
        client_name: str = "Test Client",
        case_type: str = "Test Case",
        case_summary: str = "Test case summary",
    ) -> EnhancedIntakeAnalysis:
        """Create a mock EnhancedIntakeAnalysis for testing."""
        return EnhancedIntakeAnalysis(
            client_name=client_name,
            attorney_name="Test Attorney",
            case_summary=case_summary,
            case_type=case_type,
            urgency_level="Medium",
            client_priorities=["Priority 1", "Priority 2"],
            desired_outcomes=["Outcome 1", "Outcome 2"],
            key_facts=["Fact 1", "Fact 2"],
            parties_involved=[
                {"name": client_name, "role": "Client"},
                {"name": "Other Party", "role": "Defendant"},
            ],
            financial_impact="Test financial impact",
            legal_claims=["Claim 1", "Claim 2"],
        )

    @staticmethod
    def create_sample_pdf_content() -> bytes:
        """Create minimal valid PDF content for testing."""
        pdf_header = b"%PDF-1.4\n"
        pdf_content = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        pdf_footer = b"xref\n0 1\n0000000000 65535 f\ntrailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF"
        return pdf_header + pdf_content + pdf_footer

    @staticmethod
    def create_mock_openai_response(data: dict[str, Any] | None = None) -> str:
        """Create a mock OpenAI API response in JSON format."""
        default_data = {
            "client_name": "Test Client",
            "case_type": "Test Case",
            "case_summary": "Test summary",
            "urgency_level": "Medium",
            "client_priorities": ["Priority 1"],
            "key_facts": ["Fact 1"],
            "legal_claims": ["Claim 1"],
        }
        if data:
            default_data.update(data)
        return json.dumps(default_data)


class MockConfigFactory:
    """Factory for creating mock configuration objects for testing."""

    @staticmethod
    def create_minimal_config() -> dict[str, str]:
        """Create minimal configuration for testing."""
        return {
            "OPENAI_API_KEY": "sk-test123456789",
        }

    @staticmethod
    def create_full_config() -> dict[str, str]:
        """Create full configuration with Google Cloud settings."""
        return {
            "OPENAI_API_KEY": "sk-test123456789",
            "GCP_PROJECT_ID": "test-project",
            "GCP_BUCKET_NAME": "test-bucket",
            "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/credentials.json",
            "PORT": "8501",
            "RAILWAY_STATIC_URL": "https://test.railway.app",
        }

    @staticmethod
    def create_invalid_config() -> dict[str, str]:
        """Create configuration with invalid values for testing."""
        return {
            "OPENAI_API_KEY": "invalid-key-format",
            "GCP_PROJECT_ID": "test-project",
            "GCP_BUCKET_NAME": "test-bucket",
            "GOOGLE_APPLICATION_CREDENTIALS": "/nonexistent/path.json",
        }


class MockAIServices:
    """Factory for creating mock AI service instances."""

    @staticmethod
    def create_mock_ai_analyzer() -> AsyncMock:
        """Create a mock AI analyzer with realistic responses."""
        mock_analyzer = AsyncMock()
        
        # Mock analyze_intake method
        mock_analyzer.analyze_intake.return_value = TestUtils.create_mock_intake_analysis()
        
        # Mock analyze_case_documents method
        mock_analyzer.analyze_case_documents.return_value = [
            {
                "filename": "test.pdf",
                "document_type": "Contract",
                "inferred_title": "Test Document",
                "summary": "Test summary",
                "key_information": "Test information",
                "relevance_to_case": "High relevance",
            }
        ]
        
        return mock_analyzer

    @staticmethod
    def create_mock_email_generator() -> Mock:
        """Create a mock email generator with realistic responses."""
        mock_generator = Mock()
        
        mock_generator.generate_findings_email.return_value = {
            "case_analysis_text": "Test findings email content",
            "case_analysis_html": "<p>Test findings email content</p>",
        }
        
        return mock_generator


class TestDataPresets:
    """Predefined test data for common testing scenarios."""

    DEVLIN_CASE = {
        "client_name": "Erik Devlin",
        "case_type": "Contractor Dispute",
        "case_summary": "Contractor dispute regarding incomplete home construction work",
        "document_count": 8,
        "intake_form_name": "Devlin - Intake for Contractor Dispute.pdf",
    }

    BADAM_CASE = {
        "client_name": "Balaji Badam",
        "case_type": "Landlord/Tenant Dispute",
        "case_summary": "Landlord/tenant dispute regarding property issues",
        "document_count": 15,
        "intake_form_name": "Badam - Intake Form.pdf",
    }

    PRICE_CASE = {
        "client_name": "Clifton Price",
        "case_type": "Property Damage",
        "case_summary": "Property damage claim with extensive documentation",
        "document_count": 40,
        "intake_form_name": "Price - Intake Form.pdf",
    }


def print_test_banner(title: str) -> None:
    """Print a formatted test banner for console output."""
    print(f"\n{'=' * 80}\n  🧪 {title}\n{'=' * 80}")


def assert_valid_email_structure(email_content: str) -> None:
    """Assert that email content has valid structure."""
    assert isinstance(email_content, str)
    assert len(email_content) > 0
    assert "Dear" in email_content or "Hello" in email_content  # Greeting
    assert "Sincerely" in email_content or "Best regards" in email_content  # Closing


def assert_valid_case_analysis(analysis: CaseAnalysisResult) -> None:
    """Assert that case analysis result has valid structure."""
    assert analysis.intake_analysis is not None
    assert analysis.intake_analysis.client_name
    assert analysis.intake_analysis.case_type
    assert analysis.analyzed_documents is not None
    assert len(analysis.analyzed_documents) >= 0


# Context managers for temporary environment setup
class TempEnvVar:
    """Context manager for temporarily setting environment variables."""

    def __init__(self, **kwargs):
        self.env_vars = kwargs
        self.original_values = {}

    def __enter__(self):
        for key, value in self.env_vars.items():
            self.original_values[key] = os.environ.get(key)
            os.environ[key] = value
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for key in self.env_vars:
            if self.original_values[key] is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = self.original_values[key]


class TempConfigFile:
    """Context manager for temporarily creating configuration files."""

    def __init__(self, config_data: dict[str, str], filename: str = ".env"):
        self.config_data = config_data
        self.filename = filename
        self.temp_path = None

    def __enter__(self):
        self.temp_path = TestUtils.create_temp_env_file(self.config_data)
        return self.temp_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_path:
            TestUtils.cleanup_temp_file(self.temp_path)