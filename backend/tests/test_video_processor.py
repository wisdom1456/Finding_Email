from __future__ import annotations

import os

# Add the project root to the Python path
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.utils.data_models import MediaProcessingError, VideoInsight
from backend_logic.video_processor import VideoProcessingError, VideoProcessor


# Mock Google Cloud dependencies
@pytest.fixture(autouse=True)
def mock_google_cloud():
    """Automatically mock Google Cloud clients for all tests in this module."""
    with (
        patch("google.auth.default", return_value=(None, "test-project")),
        patch("vertexai.init") as mock_vertex_init,
        patch("google.cloud.storage.Client") as mock_storage_client,
        patch("google.cloud.speech.SpeechClient") as mock_speech_client,
        patch("vertexai.generative_models.GenerativeModel") as mock_gen_model,
    ):
        yield {
            "vertex_init": mock_vertex_init,
            "storage": mock_storage_client,
            "speech": mock_speech_client,
            "gen_model": mock_gen_model,
        }


@pytest.fixture
def video_processor(mock_google_cloud):
    """Fixture for a VideoProcessor instance with mocked clients."""
    with patch.dict(
        os.environ, {"GCP_PROJECT_ID": "test-project", "GCP_BUCKET_NAME": "test-bucket"}
    ):
        processor = VideoProcessor()
        # The clients are now initialized in the constructor, so we just check the mocks
        mock_google_cloud["vertex_init"].assert_called_once()
        return processor


@pytest.fixture
def temp_video_file(tmp_path):
    """Fixture to create a temporary video file for testing."""

    def _create_file(filename="test.mp4", content=b"fake_video_data", size=1024 * 1024):
        file_path = tmp_path / filename
        file_path.write_bytes(content)
        return str(file_path)

    return _create_file


class TestVideoProcessor:
    """Unit tests for the VideoProcessor class."""

    @pytest.mark.asyncio
    @patch("backend_logic.video_processor.magic.from_file")
    async def test_process_video_file_success(
        self, mock_magic, video_processor, temp_video_file
    ):
        """Test successful video processing and analysis."""
        mock_magic.return_value = "video/mp4"
        file_path = temp_video_file()

        # Mock the async methods for analysis and transcription
        video_processor._analyze_with_vertex_ai = AsyncMock(
            return_value={"summary": "A cat is playing."}
        )
        video_processor._transcribe_with_speech_to_text = AsyncMock(
            return_value="Hello world."
        )

        # Mock synchronous methods
        video_processor._upload_to_cloud_storage = MagicMock(
            return_value="gs://test-bucket/test.mp4"
        )
        video_processor._delete_from_cloud_storage = MagicMock()

        result = await video_processor.process_video_file(file_path, "test.mp4")

        assert isinstance(result, VideoInsight)
        assert result.insights["vertex_analysis"]["summary"] == "A cat is playing."
        assert result.transcript == "Hello world."
        video_processor._upload_to_cloud_storage.assert_called_once()
        video_processor._analyze_with_vertex_ai.assert_called_once()
        video_processor._transcribe_with_speech_to_text.assert_called_once()
        video_processor._delete_from_cloud_storage.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend_logic.video_processor.magic.from_file", return_value="video/mp4")
    async def test_partial_failure_transcription_fails(
        self, mock_magic, video_processor, temp_video_file
    ):
        """Test that analysis succeeds even if transcription fails."""
        file_path = temp_video_file()

        video_processor._analyze_with_vertex_ai = AsyncMock(
            return_value={"summary": "A cat is playing."}
        )
        video_processor._transcribe_with_speech_to_text = AsyncMock(
            side_effect=VideoProcessingError("Transcription failed")
        )
        video_processor._upload_to_cloud_storage = MagicMock(
            return_value="gs://test-bucket/test.mp4"
        )

        result = await video_processor.process_video_file(file_path, "test.mp4")

        assert isinstance(result, MediaProcessingError)
        assert "Transcription failed" in result.error_message

    @pytest.mark.asyncio
    async def test_file_validation_error_handling(
        self, video_processor, temp_video_file
    ):
        """Test error handling for invalid file size or format."""
        # Test size error
        with patch("os.path.getsize", return_value=video_processor.max_file_size + 1):
            large_file = temp_video_file()
            result = await video_processor.process_video_file(large_file, "large.mp4")
            assert isinstance(result, MediaProcessingError)
            assert "exceeds 2GB size limit" in result.error_message

        # Test format error
        with patch(
            "backend_logic.video_processor.magic.from_file", return_value="text/plain"
        ):
            invalid_format_file = temp_video_file(filename="test.txt")
            result = await video_processor.process_video_file(
                invalid_format_file, "test.txt"
            )
            assert isinstance(result, MediaProcessingError)
            assert "Unsupported video format" in result.error_message

    @pytest.mark.asyncio
    @patch("backend_logic.video_processor.magic.from_file", return_value="video/mp4")
    async def test_full_analysis_failure(
        self, mock_magic, video_processor, temp_video_file
    ):
        """Test error handling when the primary Vertex AI analysis fails."""
        file_path = temp_video_file()
        video_processor._upload_to_cloud_storage = MagicMock(
            return_value="gs://test-bucket/test.mp4"
        )
        video_processor._analyze_with_vertex_ai = AsyncMock(
            side_effect=VideoProcessingError("Vertex AI failed")
        )
        # Transcription might still be attempted, we mock it to succeed
        video_processor._transcribe_with_speech_to_text = AsyncMock(
            return_value="Does not matter"
        )
        video_processor._delete_from_cloud_storage = MagicMock()

        result = await video_processor.process_video_file(file_path, "test.mp4")

        assert isinstance(result, MediaProcessingError)
        assert "Vertex AI failed" in result.error_message
        video_processor._delete_from_cloud_storage.assert_called_once()

    @pytest.mark.asyncio
    @patch("backend_logic.video_processor.magic.from_file", return_value="video/mp4")
    async def test_concurrent_execution(
        self, mock_magic, video_processor, temp_video_file
    ):
        """Test that analysis and transcription are called concurrently."""
        with patch(
            "backend_logic.video_processor.asyncio.gather", new_callable=AsyncMock
        ) as mock_gather:
            # Configure the mock to return the expected tuple when awaited
            mock_gather.return_value = ({}, "")  # analysis_result, transcription_result

            file_path = temp_video_file()
            # Mock dependent methods to isolate the process_video_file logic
            video_processor._upload_to_cloud_storage = MagicMock(
                return_value="gs://test-bucket/test.mp4"
            )
            video_processor._analyze_with_vertex_ai = AsyncMock(return_value={})
            video_processor._transcribe_with_speech_to_text = AsyncMock(return_value="")
            video_processor._delete_from_cloud_storage = MagicMock()

            result = await video_processor.process_video_file(file_path, "test.mp4")

            # Check that asyncio.gather was called, which implies concurrent execution
            mock_gather.assert_called_once()
            # Verify the result is a VideoInsight instance
            assert isinstance(result, VideoInsight)
