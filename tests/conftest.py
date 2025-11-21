"""Shared pytest fixtures and mocks for Legal Portal tests."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Import data models
from legal_portal.core.data_models import (
    DocumentSummaryStructured,
    FileMetadata,
    FileType,
    KeyAmount,
    KeyDate,
    ProcessedDocument,
)


@pytest.fixture(scope="session", autouse=True)
def mock_streamlit_context():
    """Global autouse fixture to mock Streamlit context and prevent RuntimeErrors.

    This prevents tests from crashing when code tries to access st.session_state
    or other Streamlit components that require a running Streamlit app.
    """
    with patch("streamlit.session_state", new_callable=dict) as mock_session:
        with patch("streamlit.error") as mock_error:
            with patch("streamlit.warning") as mock_warning:
                with patch("streamlit.info") as mock_info:
                    with patch("streamlit.success") as mock_success:
                        with patch("streamlit.spinner"):
                            # Set up default session state values
                            mock_session.update(
                                {
                                    "authenticated": True,
                                    "progress_callback": None,
                                }
                            )
                            yield {
                                "session_state": mock_session,
                                "error": mock_error,
                                "warning": mock_warning,
                                "info": mock_info,
                                "success": mock_success,
                            }


# pytest-asyncio is configured via pytest.ini or pyproject.toml
# No need for explicit configuration fixture


@pytest.fixture
def mock_openai_client(monkeypatch):
    """Mock OpenAI client that returns deterministic JSON responses."""

    def mock_create_chat_completion(
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        """Return deterministic mock response based on prompt content."""
        user_message = messages[-1]["content"] if messages else ""

        # Determine response based on prompt content
        if "documents" in user_message.lower() or "document" in user_message.lower():
            # Document summarization response
            response_json = {
                "documents": [
                    {
                        "document_name": "Contract.pdf",
                        "document_type": "Contract",
                        "parties": ["John Doe", "Acme Corporation"],
                        "jurisdiction_inferred": "Florida",
                        "key_dates": [
                            {
                                "date": "2024-01-15",
                                "event": "Contract signed",
                                "source_document": "Contract.pdf, Page 1",
                            }
                        ],
                        "key_amounts": [
                            {
                                "amount": "$50,000.00",
                                "description": "Purchase price",
                                "source_document": "Contract.pdf, Section 3.1",
                            }
                        ],
                        "issues_identified": ["Breach of warranty clause 5.2", "Failure to deliver on time"],
                        "risk_items": [],
                        "contract_clauses_referenced": [
                            {
                                "clause_number": "5.2",
                                "title": "Warranty",
                                "snippet": "Seller warrants that goods are free from defects",
                            }
                        ],
                        "procedural_requirements": [],
                        "relevance_to_case": "Establishes contractual obligations and breach terms",
                        "extraction_quality": "high",
                        "extraction_notes": None,
                    }
                ]
            }
        else:
            # Letter generation response
            response_json = {
                "letter_content": """<html><body>
                    <h1>Findings Letter</h1>
                    <p>Dear John Doe,</p>
                    <p>This letter summarizes our analysis of your case.</p>
                    <h2>Legal Analysis</h2>
                    <p>Based on our review, we have identified potential claims under
                    Fla. Stat. § 501.204 (FDUTPA).</p>
                    <h2>Document Review</h2>
                    <p>The contract dated January 15, 2024 establishes clear obligations.</p>
                </body></html>"""
            }

        return {
            "content": json.dumps(response_json),
            "usage": {"prompt_tokens": 1000, "completion_tokens": 2000, "total_tokens": 3000},
            "model": model,
        }

    # Mock the OpenAIClient class
    mock_client = MagicMock()
    mock_client.create_chat_completion = mock_create_chat_completion
    mock_client.analyze_with_prompt = mock_create_chat_completion

    # Patch the OpenAIClient instantiation
    monkeypatch.setattr("legal_portal.utils.openai_client.OpenAIClient", lambda: mock_client)

    return mock_client


@pytest.fixture
def mock_corpus_data(monkeypatch):
    """Mock corpus data with 5 known statutes + aliases."""
    mock_statutes = {
        "Fla. Stat. § 501.204": {
            "id": "statute:501.204",
            "citation_text": "Fla. Stat. § 501.204",
            "chapter": "501",
            "section": "204",
            "title": "Unfair and Deceptive Trade Practices",
            "summary": "Prohibits unfair methods of competition and unfair or deceptive acts",
        },
        "Fla. Stat. § 83.56": {
            "id": "statute:83.56",
            "citation_text": "Fla. Stat. § 83.56",
            "chapter": "83",
            "section": "56",
            "title": "Landlord-Tenant: Security Deposits",
            "summary": "Regulates security deposit handling",
        },
        "Fla. Stat. § 702.01": {
            "id": "statute:702.01",
            "citation_text": "Fla. Stat. § 702.01",
            "chapter": "702",
            "section": "01",
            "title": "Foreclosure Proceedings",
            "summary": "Establishes foreclosure procedures",
        },
        "Fla. Stat. § 558.004": {
            "id": "statute:558.004",
            "citation_text": "Fla. Stat. § 558.004",
            "chapter": "558",
            "section": "004",
            "title": "Construction Defects: Notice",
            "summary": "Pre-suit notice requirements for construction defects",
        },
        "Fla. Stat. § 627.70131": {
            "id": "statute:627.70131",
            "citation_text": "Fla. Stat. § 627.70131",
            "chapter": "627",
            "section": "70131",
            "title": "Property Insurance Claims",
            "summary": "Property insurance claim procedures",
        },
    }

    mock_aliases = {
        "f.s. § 501.204": "Fla. Stat. § 501.204",
        "florida statute 501.204": "Fla. Stat. § 501.204",
        "section 501.204": "Fla. Stat. § 501.204",
    }

    mock_rules = {
        "Fla. R. Civ. P. 1.010": {
            "id": "rule:1.010",
            "citation_key": "Fla. R. Civ. P. 1.010",
            "title": "Scope and Title",
        }
    }

    def mock_load_corpus(self):
        """Mock _load_corpus method."""
        self.statutes = mock_statutes.copy()
        self.aliases = mock_aliases.copy()
        self.rules = mock_rules.copy()

    # Patch StatuteValidationService to use mock corpus
    monkeypatch.setattr(
        "legal_portal.services.statute_validation_service.StatuteValidationService._load_corpus",
        mock_load_corpus,
    )

    return {"statutes": mock_statutes, "aliases": mock_aliases, "rules": mock_rules}


@pytest.fixture
def mock_file_processors(monkeypatch, tmp_path):
    """Mock file processors to return fake extracted text."""

    def mock_process_pdf(file_path: str) -> str:
        return "This is extracted text from a PDF document. It contains important legal information."

    def mock_process_docx(file_path: str) -> str:
        return "This is extracted text from a DOCX document. Contract terms and conditions."

    def mock_process_txt(file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def mock_process_image(file_path: str) -> str:
        return "This is OCR text extracted from an image. Visual description of document content."

    # Create a temporary file for text processing
    test_file = tmp_path / "test_document.txt"
    test_file.write_text("Sample document content for testing.")

    # Patch the file processors
    monkeypatch.setattr("legal_portal.services.file_processors.pdf_processor.process_pdf", mock_process_pdf)
    monkeypatch.setattr(
        "legal_portal.services.file_processors.docx_processor.process_docx", mock_process_docx
    )
    monkeypatch.setattr("legal_portal.services.file_processors.txt_processor.process_txt", mock_process_txt)
    monkeypatch.setattr(
        "legal_portal.services.file_processors.image_processor.process_image", mock_process_image
    )

    return {
        "pdf": mock_process_pdf,
        "docx": mock_process_docx,
        "txt": mock_process_txt,
        "image": mock_process_image,
        "test_file": str(test_file),
    }


@pytest.fixture
def sample_intake_content():
    """Realistic minimal intake text (~200 words)."""
    return """CLIENT INTAKE FORM

Client Name: John Doe
Attorney: Jane Smith, Esq.
Case Reference: CASE-2024-001
Date: January 10, 2024

CASE SUMMARY:
The client entered into a contract with Acme Corporation on January 15, 2024,
for the purchase of goods valued at $50,000. The contract included warranty
provisions in clause 5.2. However, Acme Corporation failed to deliver the goods
on time and the goods delivered were defective, violating the warranty terms.

LEGAL ISSUES:
1. Breach of contract - failure to deliver on time
2. Breach of warranty - defective goods delivered
3. Potential FDUTPA violation - deceptive trade practices

KEY DATES:
- January 15, 2024: Contract signed
- February 1, 2024: Delivery deadline (missed)
- February 5, 2024: Defective goods received
- February 10, 2024: Client notified Acme of breach

DOCUMENTS PROVIDED:
- Purchase contract (Contract.pdf)
- Delivery receipts
- Photos of defective goods
- Email correspondence with Acme

DESIRED OUTCOME:
The client seeks compensation for the defective goods and damages for the
delayed delivery. They also want to explore potential claims under Florida's
consumer protection laws."""


@pytest.fixture
def sample_document_summaries():
    """2-3 DocumentSummaryStructured objects for testing."""
    return [
        DocumentSummaryStructured(
            document_name="Contract.pdf",
            document_type="Contract",
            parties=["John Doe", "Acme Corporation"],
            key_dates=[
                KeyDate(date="2024-01-15", event="Contract signed", source_document="Contract.pdf, Page 1")
            ],
            key_amounts=[
                KeyAmount(
                    amount="$50,000.00",
                    description="Purchase price",
                    source_document="Contract.pdf, Section 3.1",
                )
            ],
            issues_identified=["Breach of warranty clause 5.2", "Failure to deliver on time"],
            relevance_to_case="Establishes contractual obligations and breach terms",
            extraction_quality="high",
        ),
        DocumentSummaryStructured(
            document_name="Email_Correspondence.pdf",
            document_type="Correspondence",
            parties=["John Doe", "Acme Corporation"],
            key_dates=[
                KeyDate(
                    date="2024-02-10",
                    event="Client notified Acme of breach",
                    source_document="Email_Correspondence.pdf",
                )
            ],
            key_amounts=[],
            issues_identified=["Acme refused to acknowledge breach"],
            relevance_to_case="Shows defendant's response to breach notification",
            extraction_quality="high",
        ),
    ]


@pytest.fixture
def sample_case_info():
    """Return dict with client/attorney/matter info."""
    return {
        "clientName": "John Doe",
        "attorneyName": "Jane Smith, Esq.",
        "caseReference": "CASE-2024-001",
        "firmName": "Smith & Associates",
        "contactPhone": "(555) 123-4567",
        "contactEmail": "jane.smith@lawfirm.com",
        "caseType": "Consumer Protection",
    }


@pytest.fixture
def sample_processing_logs():
    """Known token usage for cost tests."""
    return {
        "documents": {
            "Contract.pdf": {
                "token_usage": {"prompt_tokens": 1000, "completion_tokens": 2000, "total_tokens": 3000},
                "model": "gpt-4o",
            },
            "Email_Correspondence.pdf": {
                "token_usage": {"prompt_tokens": 800, "completion_tokens": 1500, "total_tokens": 2300},
                "model": "gpt-4o",
            },
        }
    }


@pytest.fixture
def sample_processed_document():
    """Return a sample ProcessedDocument for testing."""
    return ProcessedDocument(
        file_name="test_document.pdf",
        content="This is sample extracted content from a PDF document.",
        document_type="CASE_DOCUMENT",
        file_type=FileType.PDF,
        metadata=FileMetadata(file_name="test_document.pdf", file_type=FileType.PDF, file_size=1024),
        extraction_method="pdf_extraction",
        extraction_quality="high",
    )


@pytest.fixture
def sample_review_data():
    """Sample review_data dict for testing."""
    return {
        "client_name": "John Doe",
        "legal_issue": "Breach of contract and warranty",
        "key_documents": ["Contract.pdf", "Email_Correspondence.pdf"],
        "confirmed_qa_pairs": [{"question": "What is the purchase price?", "answer": "$50,000.00"}],
    }


# ============================================================================
# FastAPI Testing Fixtures
# ============================================================================


@pytest.fixture
def test_user_id():
    """Return a deterministic test user UUID."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def test_user_token(test_user_id):
    """Return a mock JWT token for authenticated endpoints."""
    # In real tests, this would be a properly signed JWT
    # For now, return a simple mock token
    return f"Bearer mock_jwt_token_for_{test_user_id}"


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client for service-role operations."""
    mock_client = MagicMock()

    # Mock table operations
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.neq.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.single.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[], error=None)

    mock_client.table.return_value = mock_table

    # Mock auth operations
    mock_auth = MagicMock()
    mock_auth.get_user.return_value = MagicMock(
        user=MagicMock(id="00000000-0000-0000-0000-000000000001", email="test@example.com"), error=None
    )
    mock_client.auth = mock_auth

    # Mock storage operations
    mock_storage = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.upload.return_value = MagicMock(data={"path": "test/path"}, error=None)
    mock_bucket.download.return_value = MagicMock(data=b"fake file content", error=None)
    mock_bucket.remove.return_value = MagicMock(data=None, error=None)
    mock_bucket.get_public_url.return_value = "https://example.com/fake-url"
    mock_storage.from_.return_value = mock_bucket
    mock_client.storage = mock_storage

    return mock_client


@pytest.fixture
def mock_supabase_user_client(test_user_id):
    """Mock Supabase client with RLS context (user-scoped)."""
    mock_client = MagicMock()

    # Mock table operations with RLS filtering
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.single.return_value = mock_table

    # Default to returning user's own cases
    mock_table.execute.return_value = MagicMock(
        data=[
            {
                "id": "case-001",
                "user_id": test_user_id,
                "case_name": "Test Case",
                "created_at": datetime.utcnow().isoformat(),
            }
        ],
        error=None,
    )

    mock_client.table.return_value = mock_table

    return mock_client


@pytest_asyncio.fixture
async def app_client(mock_supabase_client, mock_openai_client) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI test client with mocked dependencies."""
    # Import the FastAPI app
    try:
        from legal_portal.api.main import app
    except ImportError:
        # If main.py doesn't exist yet, create a minimal app
        app = FastAPI(title="Test App")

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

    # Override dependencies
    from legal_portal.api.dependencies import get_supabase_client, get_user_supabase_client

    async def override_get_supabase():
        return mock_supabase_client

    async def override_get_user_supabase():
        return mock_supabase_client

    app.dependency_overrides[get_supabase_client] = override_get_supabase
    app.dependency_overrides[get_user_supabase_client] = override_get_user_supabase

    # Create async client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def case_factory(test_user_id):
    """Factory for creating test case data."""

    def _create_case(**overrides):
        defaults = {
            "id": f"case-{datetime.utcnow().timestamp()}",
            "user_id": test_user_id,
            "case_name": "Test Case",
            "client_name": "John Doe",
            "attorney_name": "Jane Smith",
            "case_type": "Consumer Protection",
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        defaults.update(overrides)
        return defaults

    return _create_case


@pytest.fixture
def document_factory(test_user_id):
    """Factory for creating test document data."""

    def _create_document(**overrides):
        defaults = {
            "id": f"doc-{datetime.utcnow().timestamp()}",
            "user_id": test_user_id,
            "case_id": "case-001",
            "file_name": "test_document.pdf",
            "file_type": "pdf",
            "file_size": 1024,
            "storage_path": f"documents/{test_user_id}/test_document.pdf",
            "uploaded_at": datetime.utcnow().isoformat(),
        }
        defaults.update(overrides)
        return defaults

    return _create_document
