"""
Tests for DocumentProcessor - migrated from HTTP-based to direct import testing.

This module tests the document processing logic that was previously accessed
via FastAPI endpoints. Now tests the backend_logic.document_processor module directly.
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from typing import List
from unittest.mock import Mock, AsyncMock, patch

from backend_logic.document_processor import DocumentProcessor, DocumentProcessingError
from backend.utils.data_models import ProcessedDocument, DocumentType, FileType


class TestDocumentProcessor:
    """Test cases for DocumentProcessor functionality."""

    @pytest.mark.asyncio
    async def test_document_processor_initialization(self, document_processor):
        """Test DocumentProcessor initializes correctly."""
        assert document_processor is not None

    @pytest.mark.asyncio
    async def test_get_document_type_intake_form(self, document_processor):
        """Test document type detection for intake forms."""
        intake_filenames = ["intake_form.pdf", "client_intake.docx"]
        
        doc_type = document_processor._get_document_type("intake_form.pdf", intake_filenames)
        assert doc_type == DocumentType.INTAKE_FORM
        
        doc_type = document_processor._get_document_type("other_document.pdf", intake_filenames)
        assert doc_type == DocumentType.CASE_DOCUMENT

    @pytest.mark.asyncio 
    async def test_get_document_type_case_document(self, document_processor):
        """Test document type detection for case documents."""
        intake_filenames = ["intake_form.pdf"]
        
        doc_type = document_processor._get_document_type("contract.pdf", intake_filenames)
        assert doc_type == DocumentType.CASE_DOCUMENT
        
        doc_type = document_processor._get_document_type("correspondence.eml", intake_filenames)
        assert doc_type == DocumentType.CASE_DOCUMENT

    @pytest.mark.asyncio
    async def test_process_documents_with_mocked_files(self, document_processor):
        """Test document processing with mocked file processors."""
        # Create mock file objects
        mock_files = [
            Mock(tmp_path="test1.pdf", filename="test1.pdf"),
            Mock(tmp_path="test2.docx", filename="test2.docx")
        ]

        intake_filenames = ["test1.pdf"]

        # Use AsyncMock for file processors
        async def mock_pdf_processor(file_path, doc_type, filename):
            return ProcessedDocument(
                file_name=filename,
                content="PDF content",
                file_type=FileType.PDF,
                document_type=doc_type
            )
        async def mock_docx_processor(file_path, doc_type, filename):
            return ProcessedDocument(
                file_name=filename,
                content="DOCX content",
                file_type=FileType.DOCX,
                document_type=doc_type
            )
        mock_file_processors = {
            "application/pdf": mock_pdf_processor,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": mock_docx_processor
        }

        with patch('backend_logic.document_processor.PROCESSOR_MAP', mock_file_processors):
            with patch('mimetypes.guess_type') as mock_mime:
                mock_mime.side_effect = [
                    ("application/pdf", None),
                    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", None)
                ]
                results = await document_processor.process_documents(mock_files, intake_filenames)
                assert len(results) == 2
                assert all(isinstance(result, ProcessedDocument) for result in results)

    @pytest.mark.asyncio
    async def test_process_documents_with_unsupported_file(self, document_processor):
        """Test processing with unsupported file type raises appropriate error."""
        mock_file = Mock(tmp_path="test.xyz", filename="test.xyz")
        intake_filenames = []
        
        with patch('mimetypes.guess_type', return_value=(None, None)):
            with pytest.raises(DocumentProcessingError, match="No processor available"):
                await document_processor.process_documents([mock_file], intake_filenames)

    @pytest.mark.asyncio
    async def test_process_documents_from_streamlit_success(self, document_processor, sample_pdf_content):
        """Test processing Streamlit uploaded files successfully."""
        # Create mock Streamlit uploaded file
        mock_uploaded_file = Mock()
        mock_uploaded_file.name = "test.pdf"
        mock_uploaded_file.getvalue.return_value = sample_pdf_content
        
        intake_filenames = ["test.pdf"]
        
        # Mock the file processor
        async def mock_pdf_processor(file_path, doc_type, filename):
            return ProcessedDocument(
                file_name=filename,
                content="Processed PDF content",
                file_type=FileType.PDF,
                document_type=doc_type
            )
        
        with patch('backend_logic.document_processor.PROCESSOR_MAP', 
                   {"application/pdf": mock_pdf_processor}):
            with patch('mimetypes.guess_type', return_value=("application/pdf", None)):
                results = await document_processor.process_documents_from_streamlit(
                    [mock_uploaded_file], intake_filenames
                )
                
                assert len(results) == 1
                assert results[0].file_name == "test.pdf"
                assert results[0].file_type == FileType.PDF
                assert results[0].document_type == DocumentType.INTAKE_FORM

    @pytest.mark.asyncio
    async def test_process_documents_from_streamlit_file_error(self, document_processor):
        """Test handling file processing errors in Streamlit upload."""
        mock_uploaded_file = Mock()
        mock_uploaded_file.name = "test.pdf"
        mock_uploaded_file.getvalue.side_effect = Exception("File read error")
        
        intake_filenames = []
        
        with pytest.raises(DocumentProcessingError, match="Error processing file"):
            await document_processor.process_documents_from_streamlit(
                [mock_uploaded_file], intake_filenames
            )

    @pytest.mark.asyncio
    async def test_fallback_processor_selection_pdf(self, document_processor):
        """Test fallback processor selection for PDF files."""
        mock_file = Mock(tmp_path="test.pdf", filename="test.pdf")
        
        async def mock_pdf_processor(file_path, doc_type, filename):
            return ProcessedDocument(
                file_name=filename,
                content="PDF content",
                file_type=FileType.PDF,
                document_type=doc_type
            )
        
        # Mock mimetypes to return None to trigger fallback
        with patch('mimetypes.guess_type', return_value=(None, None)):
            with patch('backend_logic.document_processor.PROCESSOR_MAP',
                       {"application/pdf": mock_pdf_processor}):
                results = await document_processor.process_documents([mock_file], [])
                assert len(results) == 1
                assert results[0].file_type == FileType.PDF

    @pytest.mark.asyncio
    async def test_fallback_processor_selection_docx(self, document_processor):
        """Test fallback processor selection for DOCX files."""
        mock_file = Mock(tmp_path="test.docx", filename="test.docx")
        
        async def mock_docx_processor(file_path, doc_type, filename):
            return ProcessedDocument(
                file_name=filename,
                content="DOCX content",
                file_type=FileType.DOCX,
                document_type=doc_type
            )
        
        # Mock mimetypes to return None to trigger fallback
        with patch('mimetypes.guess_type', return_value=(None, None)):
            with patch('backend_logic.document_processor.PROCESSOR_MAP', 
                       {"application/vnd.openxmlformats-officedocument.wordprocessingml.document": mock_docx_processor}):
                
                results = await document_processor.process_documents([mock_file], [])
                
                assert len(results) == 1
                assert results[0].file_type == FileType.DOCX

    # PDF compression logic removed in consolidation; test removed.

    def test_document_processing_error_inheritance(self):
        """Test DocumentProcessingError is properly defined."""
        error = DocumentProcessingError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"


class TestDocumentProcessorIntegration:
    """Integration tests for DocumentProcessor with real file processing."""
    
    @pytest.mark.asyncio
    async def test_process_multiple_document_types(self, document_processor, temp_file_path):
        """Test processing multiple document types together."""
        # Create test files with different types
        pdf_file = Mock(tmp_path=temp_file_path, filename="test.pdf")
        txt_file = Mock(tmp_path=temp_file_path, filename="test.txt") 
        
        intake_filenames = ["test.txt"]
        
        async def mock_processor(file_path, doc_type, filename):
            if filename.endswith('.pdf'):
                file_type = FileType.PDF
            else:
                file_type = FileType.TXT
                
            return ProcessedDocument(
                file_name=filename,
                content=f"Content from {filename}",
                file_type=file_type,
                document_type=doc_type
            )
        
        processor_map = {
            "application/pdf": mock_processor,
            "text/plain": mock_processor
        }
        
        with patch('backend_logic.document_processor.PROCESSOR_MAP', processor_map):
            with patch('mimetypes.guess_type') as mock_mime:
                mock_mime.side_effect = [
                    ("application/pdf", None),
                    ("text/plain", None)
                ]
                results = await document_processor.process_documents([pdf_file, txt_file], intake_filenames)
                assert len(results) == 2
                # Check PDF result
                pdf_result = next(r for r in results if r.file_name == "test.pdf")
                assert pdf_result.file_type == FileType.PDF
                assert pdf_result.document_type == DocumentType.CASE_DOCUMENT
                # Check TXT result (should be intake form)
                txt_result = next(r for r in results if r.file_name == "test.txt")
                assert txt_result.file_type == FileType.TXT
                assert txt_result.document_type == DocumentType.INTAKE_FORM

    @pytest.mark.asyncio
    async def test_error_handling_preserves_other_files(self, document_processor):
        """Test that processing errors for one file don't affect others."""
        good_file = Mock(tmp_path="good.pdf", filename="good.pdf")
        bad_file = Mock(tmp_path="bad.xyz", filename="bad.xyz")
        
        async def mock_pdf_processor(file_path, doc_type, filename):
            return ProcessedDocument(
                file_name=filename,
                content="Good file content",
                file_type=FileType.PDF,
                document_type=doc_type
            )
        
        with patch('backend_logic.document_processor.PROCESSOR_MAP',
                   {"application/pdf": mock_pdf_processor}):
            with patch('mimetypes.guess_type') as mock_mime:
                mock_mime.side_effect = [
                    ("application/pdf", None),
                    (None, None)  # This will cause bad.xyz to fail
                ]
                # Should raise error for the unsupported file
                with pytest.raises(DocumentProcessingError):
                    await document_processor.process_documents([good_file, bad_file], [])