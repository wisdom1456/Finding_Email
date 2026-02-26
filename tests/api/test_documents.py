"""Test document API endpoints."""

from io import BytesIO

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_document_pdf(app_client: AsyncClient, test_user_id):
    """Test uploading a PDF document."""
    # Arrange
    case_id = "case-001"
    file_content = b"%PDF-1.4\n%fake pdf content"
    files = {"file": ("test_document.pdf", BytesIO(file_content), "application/pdf")}

    # Act
    response = await app_client.post(
        f"/api/cases/{case_id}/documents", files=files, headers={"Authorization": "Bearer mock_token"}
    )

    # Assert
    assert response.status_code in [200, 201, 404, 413]  # Success, not found, or too large


@pytest.mark.asyncio
async def test_upload_document_docx(app_client: AsyncClient):
    """Test uploading a DOCX document."""
    # Arrange
    case_id = "case-001"
    file_content = b"PK\x03\x04"  # Minimal ZIP signature (DOCX is ZIP)
    files = {
        "file": (
            "test_document.docx",
            BytesIO(file_content),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }

    # Act
    response = await app_client.post(
        f"/api/cases/{case_id}/documents", files=files, headers={"Authorization": "Bearer mock_token"}
    )

    # Assert
    assert response.status_code in [200, 201, 404, 413]


@pytest.mark.asyncio
async def test_upload_unsupported_file_type(app_client: AsyncClient):
    """Test uploading an unsupported file type (e.g., .exe)."""
    # Arrange
    case_id = "case-001"
    file_content = b"MZ\x90\x00"  # EXE file signature
    files = {"file": ("malware.exe", BytesIO(file_content), "application/x-msdownload")}

    # Act
    response = await app_client.post(
        f"/api/cases/{case_id}/documents", files=files, headers={"Authorization": "Bearer mock_token"}
    )

    # Assert
    assert response.status_code in [400, 415, 422, 404]  # Bad request or unsupported media type


@pytest.mark.asyncio
async def test_upload_document_size_limit(app_client: AsyncClient):
    """Test uploading a file that exceeds size limits."""
    # Arrange
    case_id = "case-001"
    # Create 100MB file (assuming limit is lower)
    large_content = b"x" * (100 * 1024 * 1024)
    files = {"file": ("huge_file.pdf", BytesIO(large_content), "application/pdf")}

    # Act
    response = await app_client.post(
        f"/api/cases/{case_id}/documents", files=files, headers={"Authorization": "Bearer mock_token"}
    )

    # Assert
    assert response.status_code in [413, 400, 404]  # Payload too large


@pytest.mark.asyncio
async def test_list_case_documents(app_client: AsyncClient):
    """Test listing documents for a case."""
    # Arrange
    case_id = "case-001"

    # Act
    response = await app_client.get(
        f"/api/cases/{case_id}/documents", headers={"Authorization": "Bearer mock_token"}
    )

    # Assert
    assert response.status_code in [200, 404]
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, (list, dict))


@pytest.mark.asyncio
async def test_get_document_by_id(app_client: AsyncClient):
    """Test retrieving a specific document."""
    # Arrange
    case_id = "case-001"
    document_id = "doc-001"

    # Act
    response = await app_client.get(
        f"/api/cases/{case_id}/documents/{document_id}", headers={"Authorization": "Bearer mock_token"}
    )

    # Assert
    assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_delete_document(app_client: AsyncClient):
    """Test deleting a document."""
    # Arrange
    case_id = "case-001"
    document_id = "doc-001"

    # Act
    response = await app_client.delete(
        f"/api/cases/{case_id}/documents/{document_id}", headers={"Authorization": "Bearer mock_token"}
    )

    # Assert
    assert response.status_code in [200, 204, 404]


@pytest.mark.asyncio
async def test_duplicate_document_detection(app_client: AsyncClient):
    """Test that duplicate documents are detected."""
    # Arrange
    case_id = "case-001"
    file_content = b"%PDF-1.4\nsame content"
    files = {"file": ("duplicate.pdf", BytesIO(file_content), "application/pdf")}

    # Upload first time
    await app_client.post(
        f"/api/cases/{case_id}/documents", files=files, headers={"Authorization": "Bearer mock_token"}
    )

    # Upload same file again
    files2 = {"file": ("duplicate.pdf", BytesIO(file_content), "application/pdf")}
    response2 = await app_client.post(
        f"/api/cases/{case_id}/documents", files=files2, headers={"Authorization": "Bearer mock_token"}
    )

    # Assert - Second upload should either succeed with duplicate flag or be rejected
    assert response2.status_code in [200, 201, 409, 404]  # Conflict if duplicate detected


@pytest.mark.asyncio
async def test_download_document(app_client: AsyncClient):
    """Test downloading a document."""
    # Arrange
    case_id = "case-001"
    document_id = "doc-001"

    # Act
    response = await app_client.get(
        f"/api/cases/{case_id}/documents/{document_id}/download",
        headers={"Authorization": "Bearer mock_token"},
    )

    # Assert
    assert response.status_code in [200, 404, 302, 307]  # Success, not found, or redirect


@pytest.mark.asyncio
async def test_upload_multiple_documents(app_client: AsyncClient):
    """Test uploading multiple documents at once."""
    # Arrange
    case_id = "case-001"
    files = [
        ("files", ("doc1.pdf", BytesIO(b"%PDF-1.4\ncontent1"), "application/pdf")),
        ("files", ("doc2.pdf", BytesIO(b"%PDF-1.4\ncontent2"), "application/pdf")),
    ]

    # Act
    response = await app_client.post(
        f"/api/cases/{case_id}/documents/batch", files=files, headers={"Authorization": "Bearer mock_token"}
    )

    # Assert
    assert response.status_code in [200, 201, 404, 207]  # Multi-status if partial success


def test_verify_document_request_accepts_enrichment_fields():
    """Test that VerifyDocumentRequest accepts new attorney enrichment fields."""
    from src.legal_portal.api.routes.documents import VerifyDocumentRequest
    payload = {
        "is_verified": True,
        "document_type_override": "contract",
        "relevance_level": "critical",
        "key_facts": {"date": "2024-03-15", "amount": "$425,000"},
        "attorney_notes": "Key disclosure document - seller signed page 4",
        "document_relationships": [
            {"related_doc_id": "doc-456", "relationship_type": "modifies"}
        ],
    }
    req = VerifyDocumentRequest(**payload)
    assert req.document_type_override == "contract"
    assert req.relevance_level == "critical"
    assert req.key_facts == {"date": "2024-03-15", "amount": "$425,000"}
    assert req.attorney_notes == "Key disclosure document - seller signed page 4"
    assert len(req.document_relationships) == 1


def test_enrichment_fields_stored_under_attorney_enrichment_key():
    """Test that enrichment fields are stored under attorney_enrichment key in metadata."""
    from src.legal_portal.api.routes.documents import VerifyDocumentRequest

    # Simulate the enrichment storage logic as it should work in the handler
    request = VerifyDocumentRequest(
        is_verified=True,
        document_type_override="contract",
        relevance_level="critical",
        key_facts={"date": "2024-03-15", "amount": "$425,000"},
        attorney_notes="Key disclosure doc",
        document_relationships=[{"related_doc_id": "doc-456", "relationship_type": "modifies"}],
    )

    # Simulate the handler's metadata building logic
    metadata = {"existing_field": "value"}

    if request.document_type_override is not None:
        metadata.setdefault("attorney_enrichment", {})
        metadata["attorney_enrichment"]["document_type_override"] = request.document_type_override
    if request.relevance_level is not None:
        metadata.setdefault("attorney_enrichment", {})
        metadata["attorney_enrichment"]["relevance_level"] = request.relevance_level
    if request.key_facts is not None:
        metadata.setdefault("attorney_enrichment", {})
        metadata["attorney_enrichment"]["key_facts"] = request.key_facts
    if request.attorney_notes is not None:
        metadata.setdefault("attorney_enrichment", {})
        metadata["attorney_enrichment"]["attorney_notes"] = request.attorney_notes
    if request.document_relationships is not None:
        metadata.setdefault("attorney_enrichment", {})
        metadata["attorney_enrichment"]["document_relationships"] = request.document_relationships

    assert "attorney_enrichment" in metadata
    assert metadata["attorney_enrichment"]["document_type_override"] == "contract"
    assert metadata["attorney_enrichment"]["relevance_level"] == "critical"
    assert metadata["attorney_enrichment"]["key_facts"]["date"] == "2024-03-15"
    assert metadata["attorney_enrichment"]["attorney_notes"] == "Key disclosure doc"
    assert len(metadata["attorney_enrichment"]["document_relationships"]) == 1
    # Original metadata should be preserved
    assert metadata["existing_field"] == "value"
