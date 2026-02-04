"""Unit tests for Clio API client pagination and data retrieval."""

import pytest
from unittest.mock import Mock, patch, call
from datetime import datetime

from legal_portal.api.services.clio_client import ClioClient, ClioAPIError


class TestClioPagination:
    """Test pagination functionality across all Clio client methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock requests session."""
        with patch('legal_portal.api.services.clio_client.requests.Session') as mock:
            yield mock.return_value

    @pytest.fixture
    def clio_client(self, mock_session):
        """Create a Clio client with mocked session."""
        return ClioClient(access_token="test_token")

    def test_get_documents_single_page(self, clio_client, mock_session):
        """Test get_documents with less than 100 documents (single page)."""
        # Mock API response with 50 documents
        mock_documents = [
            {
                "id": i,
                "name": f"Document_{i}.pdf",
                "content_type": "application/pdf",
                "size": 1000,
                "created_at": "2024-01-01T00:00:00Z",
                "latest_document_version": {"url": f"https://example.com/doc{i}"}
            }
            for i in range(50)
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": mock_documents}
        mock_session.request.return_value = mock_response

        # Execute
        documents = clio_client.get_documents(matter_id=123)

        # Verify
        assert len(documents) == 50
        assert documents[0]["name"] == "Document_0.pdf"
        assert documents[49]["name"] == "Document_49.pdf"

        # Should only call API once (partial page = last page)
        assert mock_session.request.call_count == 1

    def test_get_documents_multiple_pages(self, clio_client, mock_session):
        """Test get_documents with more than 100 documents (pagination)."""
        # Mock API responses: page 1 (100 docs), page 2 (100 docs), page 3 (25 docs)
        def mock_api_call(*args, **kwargs):
            page = kwargs.get('params', {}).get('page', 1)

            if page == 1:
                data = [{"id": i, "name": f"Doc_{i}.pdf", "content_type": "application/pdf",
                        "size": 1000, "created_at": "2024-01-01T00:00:00Z",
                        "latest_document_version": None} for i in range(100)]
            elif page == 2:
                data = [{"id": i, "name": f"Doc_{i}.pdf", "content_type": "application/pdf",
                        "size": 1000, "created_at": "2024-01-01T00:00:00Z",
                        "latest_document_version": None} for i in range(100, 200)]
            elif page == 3:
                data = [{"id": i, "name": f"Doc_{i}.pdf", "content_type": "application/pdf",
                        "size": 1000, "created_at": "2024-01-01T00:00:00Z",
                        "latest_document_version": None} for i in range(200, 225)]
            else:
                data = []

            response = Mock()
            response.status_code = 200
            response.json.return_value = {"data": data}
            return response

        mock_session.request.side_effect = mock_api_call

        # Execute
        documents = clio_client.get_documents(matter_id=123)

        # Verify
        assert len(documents) == 225
        assert documents[0]["name"] == "Doc_0.pdf"
        assert documents[224]["name"] == "Doc_224.pdf"

        # Should call API 3 times (3 pages)
        assert mock_session.request.call_count == 3

    def test_get_documents_empty_response(self, clio_client, mock_session):
        """Test get_documents with no documents."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_session.request.return_value = mock_response

        documents = clio_client.get_documents(matter_id=123)

        assert len(documents) == 0
        assert mock_session.request.call_count == 1

    def test_get_notes_pagination(self, clio_client, mock_session):
        """Test get_notes with pagination across multiple pages."""
        def mock_api_call(*args, **kwargs):
            page = kwargs.get('params', {}).get('page', 1)

            if page == 1:
                data = [{"id": i, "subject": f"Note {i}", "detail": "Content",
                        "date": "2024-01-01"} for i in range(100)]
            elif page == 2:
                data = [{"id": i, "subject": f"Note {i}", "detail": "Content",
                        "date": "2024-01-01"} for i in range(100, 150)]
            else:
                data = []

            response = Mock()
            response.status_code = 200
            response.json.return_value = {"data": data}
            return response

        mock_session.request.side_effect = mock_api_call

        notes = clio_client.get_notes(matter_id=123)

        assert len(notes) == 150
        assert notes[0]["subject"] == "Note 0"
        assert notes[149]["subject"] == "Note 149"
        assert mock_session.request.call_count == 2

    def test_get_communications_no_limit(self, clio_client, mock_session):
        """Test get_communications no longer has 500-item safety limit."""
        # This tests the fix for removing the arbitrary 500-item cap
        def mock_api_call(*args, **kwargs):
            page = kwargs.get('params', {}).get('page', 1)

            # Simulate 7 pages of 100 items each = 700 items total
            if page <= 6:
                data = [
                    {
                        "id": (page - 1) * 100 + i,
                        "subject": f"Email {(page - 1) * 100 + i}",
                        "date": "2024-01-01T00:00:00Z",
                        "senders": [{"id": 1, "name": "Sender", "type": "Person"}],
                        "receivers": [],
                        "body": "Content",
                        "type": "Email"
                    }
                    for i in range(100)
                ]
            elif page == 7:
                data = [
                    {
                        "id": 600 + i,
                        "subject": f"Email {600 + i}",
                        "date": "2024-01-01T00:00:00Z",
                        "senders": [{"id": 1, "name": "Sender", "type": "Person"}],
                        "receivers": [],
                        "body": "Content",
                        "type": "Email"
                    }
                    for i in range(50)
                ]
            else:
                data = []

            response = Mock()
            response.status_code = 200
            response.json.return_value = {"data": data}
            return response

        mock_session.request.side_effect = mock_api_call

        # Execute - should fetch ALL 650 communications, not stop at 500
        communications = clio_client.get_communications(matter_id=123, limit=100)

        # Verify we got all 650, proving the 500-item limit was removed
        assert len(communications) == 650
        assert communications[0].subject == "Email 0"
        assert communications[649].subject == "Email 649"

        # Should call API 7 times
        assert mock_session.request.call_count == 7

    def test_get_documents_handles_missing_fields(self, clio_client, mock_session):
        """Test get_documents gracefully handles missing optional fields."""
        mock_documents = [
            {
                "id": 1,
                # name missing - should default to ""
                "content_type": "application/pdf",
                # size missing - should default to 0
                # created_at missing - should default to ""
                # latest_document_version missing - should be None
            }
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": mock_documents}
        mock_session.request.return_value = mock_response

        documents = clio_client.get_documents(matter_id=123)

        assert len(documents) == 1
        assert documents[0]["name"] == ""
        assert documents[0]["size"] == 0
        assert documents[0]["created_at"] == ""
        assert documents[0]["latest_document_version"] is None

    def test_get_documents_api_error_propagates(self, clio_client, mock_session):
        """Test get_documents propagates API errors correctly."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_session.request.return_value = mock_response

        with pytest.raises(ClioAPIError, match="API error 500"):
            clio_client.get_documents(matter_id=123)

    def test_pagination_increments_correctly(self, clio_client, mock_session):
        """Test that page parameter increments correctly across calls."""
        call_count = 0
        captured_pages = []

        def mock_api_call(*args, **kwargs):
            nonlocal call_count
            page = kwargs.get('params', {}).get('page', 1)
            captured_pages.append(page)

            # Return full pages for first 2 calls, partial for 3rd
            if call_count < 2:
                data = [{"id": i, "name": f"Doc_{i}", "content_type": "application/pdf",
                        "size": 1000, "created_at": "2024-01-01",
                        "latest_document_version": None} for i in range(100)]
            else:
                data = [{"id": i, "name": f"Doc_{i}", "content_type": "application/pdf",
                        "size": 1000, "created_at": "2024-01-01",
                        "latest_document_version": None} for i in range(30)]

            call_count += 1
            response = Mock()
            response.status_code = 200
            response.json.return_value = {"data": data}
            return response

        mock_session.request.side_effect = mock_api_call

        clio_client.get_documents(matter_id=123)

        # Verify pages were requested in order: 1, 2, 3
        assert captured_pages == [1, 2, 3]


class TestClioClientRateLimiting:
    """Test rate limiting doesn't interfere with pagination."""

    @pytest.fixture
    def clio_client(self):
        """Create a Clio client."""
        with patch('legal_portal.api.services.clio_client.requests.Session'):
            client = ClioClient(access_token="test_token")
            # Speed up tests by reducing rate limit delay
            client.rate_limit_delay = 0.001
            return client

    def test_pagination_respects_rate_limiting(self, clio_client):
        """Test that pagination works correctly with rate limiting."""
        with patch.object(clio_client.session, 'request') as mock_request:
            def mock_api_call(*args, **kwargs):
                page = kwargs.get('params', {}).get('page', 1)
                data = [{"id": i, "name": f"Doc_{i}", "content_type": "pdf",
                        "size": 1000, "created_at": "2024-01-01",
                        "latest_document_version": None} for i in range(50)]

                response = Mock()
                response.status_code = 200
                response.json.return_value = {"data": data if page == 1 else []}
                return response

            mock_request.side_effect = mock_api_call

            documents = clio_client.get_documents(matter_id=123)

            # Should still work correctly
            assert len(documents) == 50
