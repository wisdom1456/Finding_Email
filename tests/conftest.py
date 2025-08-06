"""
Shared test fixtures and configuration for unified testing framework.

This file provides common fixtures, mock data, and utilities for testing
the backend_logic modules directly without HTTP overhead.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Import data models
from backend.utils.data_models import (
    CaseAnalysisResult,
    DocumentType,
    EnhancedIntakeAnalysis,
    FileType,
    ProcessedDocument,
)
from backend_logic.ai_analyzer import AIAnalyzer

# Import the modules we'll be testing directly
from backend_logic.document_processor import DocumentProcessor
from backend_logic.email_generator import EmailGenerator
from backend_logic.quality_validator import QualityValidator


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def document_processor():
    """Fixture providing a DocumentProcessor instance."""
    return DocumentProcessor()


@pytest.fixture
def ai_analyzer():
    """Fixture providing an AIAnalyzer instance."""
    return AIAnalyzer()


@pytest.fixture
def email_generator():
    """Fixture providing an EmailGenerator instance."""
    return EmailGenerator()


@pytest.fixture
def quality_validator():
    """Fixture providing a QualityValidator instance."""
    return QualityValidator()


@pytest.fixture
def sample_intake_analysis():
    """Sample intake analysis data for testing."""
    return EnhancedIntakeAnalysis(
        client_name="Erik Devlin",
        attorney_name="Test Attorney",
        case_summary="Contractor dispute regarding incomplete home construction work",
        case_type="Contractor Dispute",
        urgency_level="Medium",
        client_priorities=["Recover financial damages", "Complete the work"],
        desired_outcomes=["Compensation for damages", "Project completion"],
        key_facts=[
            "Contract signed in June 2025",
            "Work left incomplete",
            "Property damage occurred",
        ],
        parties_involved=[
            {"name": "Erik Devlin", "role": "Client"},
            {"name": "LLW Construction", "role": "Contractor"},
        ],
        financial_impact="Estimated $15,000 in damages",
        legal_claims=["Breach of contract", "Property damage"],
    )


@pytest.fixture
def sample_processed_documents():
    """Sample processed documents for testing."""
    return [
        ProcessedDocument(
            file_name="intake_form.pdf",
            content="This is a sample intake form content with client details...",
            file_type=FileType.PDF,
            document_type=DocumentType.INTAKE_FORM,
        ),
        ProcessedDocument(
            file_name="contract.pdf",
            content="This is a sample contract document with terms and conditions...",
            file_type=FileType.PDF,
            document_type=DocumentType.CASE_DOCUMENT,
        ),
        ProcessedDocument(
            file_name="correspondence.eml",
            content="Email correspondence between client and contractor...",
            file_type=FileType.EML,
            document_type=DocumentType.CASE_DOCUMENT,
        ),
    ]


@pytest.fixture
def sample_case_analysis():
    """Sample case analysis result for testing."""
    return CaseAnalysisResult(
        intake_analysis=EnhancedIntakeAnalysis(
            client_name="Erik Devlin",
            case_type="Contractor Dispute",
            case_summary="Contractor dispute case",
        ),
        analyzed_documents=[
            {
                "filename": "contract.pdf",
                "document_type": "Contract",
                "inferred_title": "Construction Contract",
                "summary": "Standard construction contract",
                "key_information": "Payment terms and scope of work",
                "relevance_to_case": "Primary evidence of agreement",
            }
        ],
    )


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for testing."""
    return {
        "client_name": "Erik Devlin",
        "case_type": "Contractor Dispute",
        "case_summary": "Test case summary",
        "urgency_level": "Medium",
        "client_priorities": ["Priority 1", "Priority 2"],
        "key_facts": ["Fact 1", "Fact 2"],
        "legal_claims": ["Claim 1", "Claim 2"],
    }


@pytest.fixture
def temp_file_path():
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(b"Sample file content for testing")
        temp_path = tmp_file.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def sample_pdf_content():
    """Sample PDF content as bytes for testing."""
    # This is a minimal PDF content for testing
    pdf_header = b"%PDF-1.4\n"
    pdf_content = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    pdf_footer = b"xref\n0 1\n0000000000 65535 f\ntrailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n9\n%%EOF"
    return pdf_header + pdf_content + pdf_footer


@pytest.fixture
def devlin_test_config():
    """Configuration for Devlin test case."""
    return {
        "client_name": "Erik Devlin",
        "case_type": "Contractor Dispute",
        "api_url": "http://127.0.0.1:8000/process_documents",
        "input_dir": "input",
        "output_dir": "output",
        "reference_dir": "reference",
        "supported_extensions": [".pdf", ".docx", ".doc", ".txt", ".eml"],
        "video_extensions": [".mp4", ".avi", ".mov"],
        "intake_patterns": [
            "Intake for Contractor Dispute",
            "Intake (General)",
            "Intake Form",
        ],
        "validation": {
            "document_intake": {"enabled": True},
            "email_comparison": {
                "enabled": True,
                "reference_file": "reference_email.rtf",
                "min_substance_score": 0.75,
            },
        },
    }


@pytest.fixture
def badam_test_config():
    """Configuration for Badam test case."""
    return {
        "client_name": "Balaji Badam",
        "case_type": "Landlord/Tenant Dispute",
        "supported_extensions": [
            ".pdf",
            ".docx",
            ".doc",
            ".txt",
            ".eml",
            ".jpg",
            ".jpeg",
            ".png",
        ],
        "intake_patterns": ["Intake", "intake"],
        "validation": {
            "document_intake": {"enabled": True},
            "ai_analysis": {"enabled": True},
        },
    }


@pytest.fixture
async def mock_ai_analyzer():
    """Mock AI analyzer for testing without actual API calls."""
    mock_analyzer = AsyncMock(spec=AIAnalyzer)

    # Mock the analyze_intake method
    mock_analyzer.analyze_intake.return_value = EnhancedIntakeAnalysis(
        client_name="Test Client", case_type="Test Case", case_summary="Test summary"
    )

    # Mock the analyze_case_documents method
    mock_analyzer.analyze_case_documents.return_value = [
        {
            "filename": "test.pdf",
            "document_type": "Contract",
            "inferred_title": "Test Document",
            "summary": "Test summary",
            "key_information": "Test info",
            "relevance_to_case": "Test relevance",
        }
    ]

    return mock_analyzer


@pytest.fixture
def preserved_test_data():
    """Preserve critical test data from the original framework."""
    return {
        "devlin_case": {
            "case_reference": "DEVLIN-001",
            "expected_client": "Erik Devlin",
            "expected_case_type": "Contractor Dispute",
            "document_count": 8,
            "intake_form_name": "Devlin - Intake for Contractor Dispute.pdf",
        },
        "badam_case": {
            "case_reference": "BADAM-001",
            "expected_client": "Balaji Badam",
            "expected_case_type": "Landlord/Tenant Dispute",
            "document_count": 15,
            "intake_form_name": "Badam - Intake Form.pdf",
        },
    }


@pytest.fixture
def email_validation_thresholds():
    """Email validation scoring thresholds."""
    return {
        "min_substance_score": 0.75,
        "min_structure_score": 0.8,
        "min_completeness_score": 0.85,
        "min_professional_tone_score": 0.9,
    }


# Mock patches for external dependencies
@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client to avoid actual API calls during testing."""
    with patch("backend_logic.ai_analyzer.OpenAI") as mock_client:
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '{"test": "response"}'

        mock_instance.chat.completions.create.return_value = mock_response
        mock_client.return_value = mock_instance

        yield mock_instance


@pytest.fixture
def mock_file_processors():
    """Mock file processors to avoid file system dependencies."""
    with patch("backend_logic.document_processor.PROCESSOR_MAP") as mock_processors:

        async def mock_pdf_processor(file_path, doc_type, filename):
            return ProcessedDocument(
                file_name=filename,
                content="Mocked PDF content",
                file_type=FileType.PDF,
                document_type=doc_type,
            )

        async def mock_docx_processor(file_path, doc_type, filename):
            return ProcessedDocument(
                file_name=filename,
                content="Mocked DOCX content",
                file_type=FileType.DOCX,
                document_type=doc_type,
            )

        mock_processors.return_value = {
            "application/pdf": mock_pdf_processor,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": mock_docx_processor,
            "text/plain": mock_docx_processor,  # Use same mock for simplicity
        }

        yield mock_processors
