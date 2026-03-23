"""Regression tests for _make_openai_request_responses_api return type contracts.

Ensures the string-return helper always returns Optional[str] and the
full-dict helper always returns Dict[str, Any]. Prevents the regression
from bf3e231 where changing the return type broke 7 callers.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


class TestMakeOpenAIRequestReturnTypes:
    """Verify return type contracts for the two API helpers."""

    def _make_service(self):
        """Create a JsonProcessingService with a mocked OpenAI client."""
        from legal_portal.services.shared.json_processing_service import JsonProcessingService
        mock_client = MagicMock()
        mock_client.create_response.return_value = {
            "content": "test response content",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "model": "gpt-5.4",
        }
        mock_client.get_preferred_model.return_value = "gpt-5.4"
        mock_client._is_gpt5_model.return_value = True
        service = JsonProcessingService(client=mock_client, config={})
        return service, mock_client

    def test_string_helper_returns_string(self):
        """_make_openai_request_responses_api must return Optional[str], not dict."""
        service, _ = self._make_service()
        result = service._make_openai_request_responses_api("test prompt")
        assert isinstance(result, str), f"Expected str, got {type(result).__name__}"
        assert result == "test response content"

    def test_string_helper_returns_none_on_empty(self):
        """String helper returns None when model returns empty content."""
        service, mock_client = self._make_service()
        mock_client.create_response.return_value = {
            "content": None,
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
            "model": "gpt-5.4",
        }
        result = service._make_openai_request_responses_api("test prompt")
        assert result is None

    def test_full_helper_returns_dict(self):
        """_make_openai_request_responses_api_full must return Dict with all fields."""
        service, _ = self._make_service()
        result = service._make_openai_request_responses_api_full("test prompt")
        assert isinstance(result, dict), f"Expected dict, got {type(result).__name__}"
        assert "content" in result
        assert "finish_reason" in result
        assert "usage" in result
        assert "model" in result
        assert result["content"] == "test response content"
        assert result["finish_reason"] == "stop"

    def test_string_helper_strip_safe(self):
        """String helper result must be safe to call .strip() on (or be None)."""
        service, _ = self._make_service()
        result = service._make_openai_request_responses_api("test prompt")
        # This is the exact pattern used by repair_letter_constraints
        stripped = (result or "").strip()
        assert isinstance(stripped, str)

    def test_full_helper_strip_would_fail(self):
        """Full helper result must NOT have .strip() — it's a dict."""
        service, _ = self._make_service()
        result = service._make_openai_request_responses_api_full("test prompt")
        with pytest.raises(AttributeError):
            result.strip()


class TestRepairLetterConstraintsContract:
    """Verify demand-letter repair path handles string return correctly."""

    @pytest.mark.asyncio
    async def test_repair_returns_string(self):
        """repair_letter_constraints must return a string, not a dict."""
        from legal_portal.services.shared.json_processing_service import JsonProcessingService
        mock_client = MagicMock()
        mock_client.create_response.return_value = {
            "content": "repaired letter content",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "model": "gpt-5-mini",
        }
        mock_client._is_gpt5_model.return_value = True
        service = JsonProcessingService(client=mock_client, config={})

        result = await service.repair_letter_constraints(
            draft_markdown="Original draft with issues.",
            violations=[{"rule": "test", "message": "fix this", "severity": "warning"}],
            mode="default",
            model="gpt-5-mini",
        )
        assert isinstance(result, str), f"Expected str, got {type(result).__name__}"
        assert result == "repaired letter content"

    @pytest.mark.asyncio
    async def test_repair_empty_returns_original(self):
        """When repair returns empty, original draft is preserved."""
        from legal_portal.services.shared.json_processing_service import JsonProcessingService
        mock_client = MagicMock()
        mock_client.create_response.return_value = {
            "content": "",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
            "model": "gpt-5-mini",
        }
        mock_client._is_gpt5_model.return_value = True
        service = JsonProcessingService(client=mock_client, config={})

        result = await service.repair_letter_constraints(
            draft_markdown="Keep this original draft.",
            violations=[{"rule": "test", "message": "fix", "severity": "warning"}],
        )
        assert result == "Keep this original draft."


class TestSummarizationMetadataContract:
    """Verify summarization path gets full metadata dict."""

    @pytest.mark.asyncio
    async def test_try_summarization_call_returns_full_dict(self):
        """_try_summarization_call must return dict with finish_reason and usage."""
        from legal_portal.services.shared.json_processing_service import JsonProcessingService
        mock_client = MagicMock()
        mock_client.create_response.return_value = {
            "content": '{"documents": []}',
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "model": "gpt-5.4",
        }
        mock_client.get_preferred_model.return_value = "gpt-5.4"
        mock_client._is_gpt5_model.return_value = True
        service = JsonProcessingService(client=mock_client, config={})

        result = await service._try_summarization_call(
            prompt="test prompt",
            model="gpt-5.4",
            max_output_tokens=12000,
            instructions="Return JSON.",
        )
        assert isinstance(result, dict)
        assert result["finish_reason"] == "stop"
        assert result["content"] == '{"documents": []}'
        assert "usage" in result

    @pytest.mark.asyncio
    async def test_process_documents_returns_3_tuple_with_metadata(self):
        """process_documents_to_json must return (content, errors, metadata)."""
        from legal_portal.services.shared.json_processing_service import JsonProcessingService
        mock_client = MagicMock()
        mock_client.create_response.return_value = {
            "content": '{"documents": [{"document_name": "test.pdf"}]}',
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "model": "gpt-5.4",
        }
        mock_client.get_preferred_model.return_value = "gpt-5.4"
        mock_client._is_gpt5_model.return_value = True
        service = JsonProcessingService(client=mock_client, config={})

        content, errors, meta = await service.process_documents_to_json("test prompt")
        assert isinstance(content, str)
        assert isinstance(errors, list)
        assert len(errors) == 0
        assert isinstance(meta, dict)
        assert meta["finish_reason"] == "stop"
        assert meta["model"] == "gpt-5.4"
        assert meta["response_chars"] > 0
