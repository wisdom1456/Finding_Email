import asyncio
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from openai import RateLimitError


# Add the project root to the Python path
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend_logic.audio_processor import AudioProcessor, AudioProcessingError
from backend.utils.data_models import TranscriptedMedia, MediaProcessingError, FileMetadata

@pytest.fixture
def mock_openai_client():
    """Fixture for a mocked OpenAI client."""
    return MagicMock()

@pytest.fixture
def audio_processor(mock_openai_client):
    """Fixture for an AudioProcessor instance with a mocked client."""
    return AudioProcessor(openai_client=mock_openai_client)

@pytest.fixture
def temp_audio_file(tmp_path):
    """Fixture to create a temporary audio file for testing."""
    def _create_file(filename="test.mp3", content=b"fake_audio_data", size=1024):
        file_path = tmp_path / filename
        file_path.write_bytes(content)
        # Mock the file size if needed
        os.utime(file_path, (0, size))
        return str(file_path)
    return _create_file

class TestAudioProcessor:
    """Unit tests for the AudioProcessor class."""

    @pytest.mark.asyncio
    @patch('backend_logic.audio_processor.magic.from_file')
    async def test_process_audio_file_success(self, mock_magic, audio_processor, mock_openai_client, temp_audio_file):
        """Test successful audio processing and transcription."""
        mock_magic.return_value = 'audio/mpeg'
        file_path = temp_audio_file()
        
        mock_transcription = MagicMock()
        mock_transcription.text = "This is a test transcript."
        mock_transcription.duration = 12.34
        mock_transcription.language = "en"
        
        # Configure the mock to return a dictionary from model_dump
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            'text': 'This is a test transcript.',
            'duration': 12.34,
            'language': 'en',
            'segments': [{'avg_logprob': -0.5}]
        }
        
        # Since the method expects an awaitable, we wrap the mock in an AsyncMock
        audio_processor._transcribe_with_whisper = AsyncMock(return_value=mock_response.model_dump())
        
        result = await audio_processor.process_audio_file(file_path, "test.mp3")
        
        assert isinstance(result, TranscriptedMedia)
        assert result.transcript == "This is a test transcript."
        assert result.duration == 12.34
        assert result.language == "en"

    @pytest.mark.asyncio
    async def test_file_validation_size_limit(self, audio_processor, temp_audio_file):
        """Test that files exceeding the size limit are rejected."""
        # Create a file that is too large
        large_file_path = temp_audio_file(size=audio_processor.max_file_size + 1)
        
        result = await audio_processor.process_audio_file(large_file_path, "large_file.mp3")
        
        assert isinstance(result, MediaProcessingError)
        assert "is too large" in result.error_message

    @pytest.mark.asyncio
    @patch('backend_logic.audio_processor.magic.from_file')
    async def test_file_validation_unsupported_format(self, mock_magic, audio_processor, temp_audio_file):
        """Test that unsupported audio formats are rejected."""
        mock_magic.return_value = 'application/json'  # Unsupported format
        unsupported_file_path = temp_audio_file(filename="test.json")
        
        result = await audio_processor.process_audio_file(unsupported_file_path, "test.json")
        
        assert isinstance(result, MediaProcessingError)
        assert "Unsupported audio format" in result.error_message

    @pytest.mark.asyncio
    @patch('backend_logic.audio_processor.magic.from_file')
    async def test_transcription_api_error_handling(self, mock_magic, audio_processor, mock_openai_client, temp_audio_file):
        """Test handling of OpenAI API errors during transcription."""
        mock_magic.return_value = 'audio/mpeg'
        file_path = temp_audio_file()

        # Mock the API call to raise an error
        mock_openai_client.audio.transcriptions.create.side_effect = RateLimitError("API rate limit exceeded", response=MagicMock(), body=None)

        result = await audio_processor.process_audio_file(file_path, "test.mp3")

        assert isinstance(result, MediaProcessingError)
        assert "OpenAI API error" in result.error_message

    @pytest.mark.asyncio
    @patch('backend_logic.audio_processor.magic.from_file')
    async def test_retry_logic_on_api_failure(self, mock_magic, audio_processor, mock_openai_client, temp_audio_file):
        """Test the retry behavior when the API fails intermittently."""
        mock_magic.return_value = 'audio/mpeg'
        file_path = temp_audio_file()

        # Fail twice, then succeed
        side_effects = [
            RateLimitError("Attempt 1", response=MagicMock(), body=None),
            RateLimitError("Attempt 2", response=MagicMock(), body=None),
            MagicMock(text="Successful on third try")
        ]
        mock_openai_client.audio.transcriptions.create.side_effect = side_effects

        result = await audio_processor.process_audio_file(file_path, "test.mp3")
        
        assert isinstance(result, TranscriptedMedia)
        assert result.transcript == "Successful on third try"
        assert mock_openai_client.audio.transcriptions.create.call_count == 3

    @pytest.mark.asyncio
    async def test_temporary_file_cleanup(self, audio_processor):
        """Test that temporary files created during processing are cleaned up."""
        # Mock Streamlit UploadedFile
        mock_uploaded_file = MagicMock()
        mock_uploaded_file.getvalue.return_value = b"some audio data"
        
        # Patch tempfile.NamedTemporaryFile to track the temp file path
        with patch('tempfile.NamedTemporaryFile') as mock_tempfile:
            # Create a mock file object to be returned by the context manager
            mock_file_object = MagicMock()
            mock_file_object.name = "path/to/temp_file.mp3"
            # __enter__ should return the mock file object
            mock_tempfile.return_value.__enter__.return_value = mock_file_object
            
            # Make sure we can check if the file exists
            with patch('os.path.exists') as mock_exists:
                # First check is before processing, second is after cleanup
                mock_exists.side_effect = [True, False] 
                
                with patch('os.unlink') as mock_unlink:
                    await audio_processor.process_audio_from_streamlit(mock_uploaded_file, "test.mp3")
                    # Ensure unlink was called on the correct temporary file
                    mock_unlink.assert_called_once_with(mock_file_object.name)