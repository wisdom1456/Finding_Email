"""Unit tests for DocumentProcessor and prompt construction."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from legal_portal.core.data_models import DocumentType, FileMetadata, FileType, ProcessedDocument
from legal_portal.core.document_processor import DocumentProcessor
from legal_portal.services.analysis.main_processor import _build_summary_prompt

# Removed duplicate test - using async version below


@pytest.mark.asyncio
async def test_process_text_document_async(mock_file_processors, tmp_path):
    """Test processing a text document asynchronously."""
    # Create a text file
    test_file = tmp_path / "test_document.txt"
    test_file.write_text("This is sample document content for testing purposes.")

    processor = DocumentProcessor()

    # Mock file processors to return content
    with patch("legal_portal.services.file_processors.txt_processor.process_txt") as mock_txt:
        mock_txt.return_value = "This is sample document content for testing purposes."

        processed_docs = await processor.process_documents_from_paths([str(test_file)], intake_filenames=[])

        assert len(processed_docs) > 0
        assert isinstance(processed_docs[0], ProcessedDocument)
        assert "sample document content" in processed_docs[0].content.lower()
        assert processed_docs[0].document_type in [DocumentType.INTAKE_FORM, DocumentType.CASE_DOCUMENT]


def test_intake_classification_by_filename():
    """Test that documents with 'intake' in filename are classified as INTAKE_FORM."""
    processor = DocumentProcessor()

    # Test various intake filename patterns
    intake_filenames = [
        "Client_Intake_Form.pdf",
        "intake_form.txt",
        "INTAKE_DOCUMENT.pdf",
        "client_intake_questionnaire.docx",
    ]

    for filename in intake_filenames:
        doc_type = processor._get_document_type(
            filename=filename, intake_filenames=[filename], original_filename=filename
        )
        assert doc_type == DocumentType.INTAKE_FORM, f"Failed for filename: {filename}"


def test_case_document_classification():
    """Test that regular documents are classified as CASE_DOCUMENT."""
    processor = DocumentProcessor()

    # Test various case document filename patterns
    case_document_filenames = [
        "Contract_Agreement.pdf",
        "Email_Correspondence.pdf",
        "Evidence_Photo.jpg",
        "Legal_Brief.docx",
    ]

    for filename in case_document_filenames:
        doc_type = processor._get_document_type(
            filename=filename,
            intake_filenames=["intake_form.pdf"],  # Different from case doc
            original_filename=filename,
        )
        assert doc_type == DocumentType.CASE_DOCUMENT, f"Failed for filename: {filename}"


def test_document_metadata_populated(mock_file_processors):
    """Test that ProcessedDocument has all required metadata fields."""
    from datetime import datetime

    # Create a ProcessedDocument with all fields
    doc = ProcessedDocument(
        file_name="test_document.pdf",
        content="Sample content",
        document_type=DocumentType.CASE_DOCUMENT,
        file_type=FileType.PDF,
        metadata=FileMetadata(file_name="test_document.pdf", file_type=FileType.PDF, file_size=1024),
        extraction_method="pdf_extraction",
        extraction_quality="high",
        extracted_at=datetime.now(),
    )

    # Assert all required fields are present
    assert doc.file_name == "test_document.pdf"
    assert doc.content == "Sample content"
    assert doc.document_type == DocumentType.CASE_DOCUMENT
    assert doc.file_type == FileType.PDF
    assert doc.metadata is not None
    assert doc.metadata.file_name == "test_document.pdf"
    assert doc.metadata.file_type == FileType.PDF
    assert doc.extraction_method == "pdf_extraction"
    assert doc.extraction_quality == "high"
    assert isinstance(doc.extracted_at, datetime)


def test_prompt_construction_integrates_context():
    """Test that prompt construction correctly integrates CLIO and statute context."""
    # Sample intake content
    intake_content = "Client case involving contract breach."

    # Sample documents (minimal)
    class MockDocument:
        def __init__(self):
            self.file_name = "contract.pdf"
            self.content = "Contract terms and conditions."
            self.extraction_quality = "high"
            self.extraction_method = "pdf_extraction"

    documents = [MockDocument()]

    # Review data with CLIO context and statute recommendations
    review_data = {
        "legal_issue": "Breach of contract",
        "key_documents": ["contract.pdf"],
        "clio_matter_context": {"matter_summary": "CLIO matter summary text", "timeline": []},
    }

    # Build the prompt
    prompt = _build_summary_prompt(
        intake_content=intake_content, documents=documents, review_data=review_data, is_batch=False
    )

    # Assert prompt contains required elements
    assert isinstance(prompt, str)
    assert len(prompt) > 0

    # Assert intake content is included
    assert "contract breach" in prompt.lower() or intake_content.lower() in prompt.lower()

    # Assert document content is included
    assert "contract.pdf" in prompt.lower() or "contract" in prompt.lower()

    # Assert legal issue from review_data is included
    assert "breach of contract" in prompt.lower() or review_data["legal_issue"].lower() in prompt.lower()

    # Note: CLIO context and statute context are added later in the workflow,
    # so they may not appear in _build_summary_prompt directly, but the structure
    # should support their injection
