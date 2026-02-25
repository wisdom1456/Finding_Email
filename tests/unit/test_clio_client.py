"""Unit tests for Clio API client pagination and data retrieval."""

import pytest
from unittest.mock import Mock, patch, call
from datetime import datetime

from legal_portal.api.services.clio_client import ClioClient, ClioAPIError, ClioRateLimitError


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
        next_url_page_2 = "https://app.clio.com/api/v4/documents.json?page_token=abc123"
        next_url_page_3 = "https://app.clio.com/api/v4/documents.json?page_token=def456"

        response_page_1 = Mock()
        response_page_1.status_code = 200
        response_page_1.json.return_value = {
            "data": [
                {
                    "id": i,
                    "name": f"Doc_{i}.pdf",
                    "content_type": "application/pdf",
                    "size": 1000,
                    "created_at": "2024-01-01T00:00:00Z",
                    "latest_document_version": None,
                }
                for i in range(100)
            ],
            "meta": {"paging": {"next": next_url_page_2}},
        }

        response_page_2 = Mock()
        response_page_2.status_code = 200
        response_page_2.json.return_value = {
            "data": [
                {
                    "id": i,
                    "name": f"Doc_{i}.pdf",
                    "content_type": "application/pdf",
                    "size": 1000,
                    "created_at": "2024-01-01T00:00:00Z",
                    "latest_document_version": None,
                }
                for i in range(100, 200)
            ],
            "meta": {"paging": {"next": next_url_page_3}},
        }

        response_page_3 = Mock()
        response_page_3.status_code = 200
        response_page_3.json.return_value = {
            "data": [
                {
                    "id": i,
                    "name": f"Doc_{i}.pdf",
                    "content_type": "application/pdf",
                    "size": 1000,
                    "created_at": "2024-01-01T00:00:00Z",
                    "latest_document_version": None,
                }
                for i in range(200, 225)
            ],
            "meta": {"paging": {}},
        }

        mock_session.request.side_effect = [response_page_1, response_page_2, response_page_3]

        # Execute
        documents = clio_client.get_documents(matter_id=123)

        # Verify
        assert len(documents) == 225
        assert documents[0]["name"] == "Doc_0.pdf"
        assert documents[224]["name"] == "Doc_224.pdf"

        # Should call API 3 times (3 pages)
        assert mock_session.request.call_count == 3

        first_call = mock_session.request.call_args_list[0].kwargs
        second_call = mock_session.request.call_args_list[1].kwargs
        third_call = mock_session.request.call_args_list[2].kwargs

        assert first_call["url"] == "https://app.clio.com/api/v4/documents.json"
        assert first_call["params"]["matter_id"] == 123
        assert first_call["params"]["limit"] == 100
        assert second_call["url"] == next_url_page_2
        assert second_call["params"] is None
        assert third_call["url"] == next_url_page_3
        assert third_call["params"] is None

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

    def test_pagination_follows_next_urls(self, clio_client, mock_session):
        """Test document pagination follows Clio's meta.paging.next URLs."""
        next_url_page_2 = "https://app.clio.com/api/v4/documents.json?page_token=abc123"
        next_url_page_3 = "https://app.clio.com/api/v4/documents.json?page_token=def456"
        captured_urls = []
        captured_params = []

        def mock_api_call(*args, **kwargs):
            captured_urls.append(kwargs.get("url"))
            captured_params.append(kwargs.get("params"))

            if len(captured_urls) == 1:
                data = [
                    {
                        "id": i,
                        "name": f"Doc_{i}",
                        "content_type": "application/pdf",
                        "size": 1000,
                        "created_at": "2024-01-01",
                        "latest_document_version": None,
                    }
                    for i in range(100)
                ]
                meta = {"paging": {"next": next_url_page_2}}
            elif len(captured_urls) == 2:
                data = [
                    {
                        "id": i,
                        "name": f"Doc_{i}",
                        "content_type": "application/pdf",
                        "size": 1000,
                        "created_at": "2024-01-01",
                        "latest_document_version": None,
                    }
                    for i in range(100, 200)
                ]
                meta = {"paging": {"next": next_url_page_3}}
            else:
                data = [
                    {
                        "id": i,
                        "name": f"Doc_{i}",
                        "content_type": "application/pdf",
                        "size": 1000,
                        "created_at": "2024-01-01",
                        "latest_document_version": None,
                    }
                    for i in range(200, 230)
                ]
                meta = {"paging": {}}

            response = Mock()
            response.status_code = 200
            response.json.return_value = {"data": data, "meta": meta}
            return response

        mock_session.request.side_effect = mock_api_call

        clio_client.get_documents(matter_id=123)

        assert captured_urls == [
            "https://app.clio.com/api/v4/documents.json",
            next_url_page_2,
            next_url_page_3,
        ]
        assert captured_params[0]["matter_id"] == 123
        assert captured_params[1] is None
        assert captured_params[2] is None

    def test_pagination_detects_repeated_next_url(self, clio_client, mock_session):
        """Fail fast if Clio returns a repeated cursor URL to avoid infinite loops."""
        repeated_next_url = "https://app.clio.com/api/v4/documents.json?page_token=repeat123"

        response_page_1 = Mock()
        response_page_1.status_code = 200
        response_page_1.json.return_value = {
            "data": [
                {
                    "id": i,
                    "name": f"Doc_{i}.pdf",
                    "content_type": "application/pdf",
                    "size": 1000,
                    "created_at": "2024-01-01T00:00:00Z",
                    "latest_document_version": None,
                }
                for i in range(100)
            ],
            "meta": {"paging": {"next": repeated_next_url}},
        }

        response_page_2 = Mock()
        response_page_2.status_code = 200
        response_page_2.json.return_value = {
            "data": [
                {
                    "id": i,
                    "name": f"Doc_{i}.pdf",
                    "content_type": "application/pdf",
                    "size": 1000,
                    "created_at": "2024-01-01T00:00:00Z",
                    "latest_document_version": None,
                }
                for i in range(100, 200)
            ],
            "meta": {"paging": {"next": repeated_next_url}},
        }

        mock_session.request.side_effect = [response_page_1, response_page_2]

        with pytest.raises(ClioAPIError, match="repeated document pagination URL"):
            clio_client.get_documents(matter_id=123)


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

    def test_retries_on_429_then_succeeds(self, clio_client):
        """Retry transient Clio 429 responses and succeed when the API recovers."""
        with patch.object(clio_client.session, 'request') as mock_request, \
             patch('legal_portal.api.services.clio_client.time.sleep'):
            rate_limited = Mock()
            rate_limited.status_code = 429
            rate_limited.headers = {}
            rate_limited.text = "Too Many Requests"

            success = Mock()
            success.status_code = 200
            success.json.return_value = {"data": []}

            mock_request.side_effect = [rate_limited, rate_limited, success]

            documents = clio_client.get_documents(matter_id=123)

            assert documents == []
            assert mock_request.call_count == 3

    def test_uses_retry_after_header_on_429(self, clio_client):
        """Honor Retry-After when Clio returns explicit backoff guidance."""
        with patch.object(clio_client.session, 'request') as mock_request, \
             patch('legal_portal.api.services.clio_client.time.sleep') as mock_sleep:
            rate_limited = Mock()
            rate_limited.status_code = 429
            rate_limited.headers = {"Retry-After": "7"}
            rate_limited.text = "Too Many Requests"

            success = Mock()
            success.status_code = 200
            success.json.return_value = {"data": []}

            mock_request.side_effect = [rate_limited, success]

            clio_client.get_documents(matter_id=123)

            sleep_args = [args[0] for args, _ in mock_sleep.call_args_list if args]
            assert any(wait >= 7 for wait in sleep_args)

    def test_raises_after_exhausting_429_retries(self, clio_client):
        """Raise ClioRateLimitError once all configured retries are consumed."""
        with patch.object(clio_client.session, 'request') as mock_request, \
             patch('legal_portal.api.services.clio_client.time.sleep'):
            rate_limited = Mock()
            rate_limited.status_code = 429
            rate_limited.headers = {}
            rate_limited.text = "Too Many Requests"

            mock_request.side_effect = [rate_limited] * 5

            with pytest.raises(ClioRateLimitError, match="Rate limit exceeded"):
                clio_client.get_documents(matter_id=123)
