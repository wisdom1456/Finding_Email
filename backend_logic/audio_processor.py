import os
import tempfile
from typing import Union
from openai import OpenAI, RateLimitError, APIError, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import magic

from backend.utils.data_models import (
    TranscriptedMedia,
    MediaProcessingError,
    FileMetadata
)


class AudioProcessingError(Exception):
    """Custom exception for audio processing errors."""
    pass


class AudioProcessor:
    """
    Handles audio file processing and transcription using OpenAI Whisper.
    Follows the existing system patterns of direct function calls and error handling.
    """
    
    def __init__(self, openai_client: OpenAI):
        self.openai_client = openai_client
        
        # Supported audio formats (matching OpenAI Whisper supported formats)
        self.supported_formats = {
            'audio/mpeg',      # MP3
            'audio/mp4',       # M4A
            'audio/wav',       # WAV
            'audio/webm',      # WEBM
            'audio/x-flac',    # FLAC
            'audio/flac',      # FLAC (alternative MIME type)
            'audio/ogg',       # OGG
        }
        
        # File size limit (25MB for Whisper API)
        self.max_file_size = 25 * 1024 * 1024  # 25MB in bytes
    
    def _validate_audio_file(self, file_path: str, file_name: str) -> None:
        """
        Validates audio file format and size.
        
        Args:
            file_path: Path to the audio file
            file_name: Original filename for error reporting
            
        Raises:
            AudioProcessingError: If file is invalid
        """
        # Check file exists
        if not os.path.exists(file_path):
            raise AudioProcessingError(f"Audio file not found: {file_name}")
        
        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size > self.max_file_size:
            raise AudioProcessingError(
                f"Audio file '{file_name}' is too large ({file_size / 1024 / 1024:.1f}MB). "
                f"Maximum size is {self.max_file_size / 1024 / 1024}MB."
            )
        
        # Check MIME type
        try:
            mime_type = magic.from_file(file_path, mime=True)
            if mime_type not in self.supported_formats:
                # Check file extension as fallback
                file_ext = os.path.splitext(file_name)[1].lower()
                if file_ext not in ['.mp3', '.m4a', '.wav', '.webm', '.flac', '.ogg']:
                    raise AudioProcessingError(
                        f"Unsupported audio format for '{file_name}'. "
                        f"Supported formats: MP3, M4A, WAV, WEBM, FLAC, OGG"
                    )
        except Exception as e:
            print(f"AUDIO PROCESSOR: Warning - Could not detect MIME type for {file_name}: {e}")
            # Allow processing to continue with file extension check
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RateLimitError, APIError, APITimeoutError)),
    )
    async def _transcribe_with_whisper(self, file_path: str, file_name: str) -> dict:
        """
        Transcribes audio using OpenAI Whisper API with retry logic.
        
        Args:
            file_path: Path to the audio file
            file_name: Original filename for error reporting
            
        Returns:
            Dict containing transcription results
            
        Raises:
            AudioProcessingError: If transcription fails after retries
        """
        try:
            print(f"AUDIO PROCESSOR: Starting transcription for {file_name}")
            
            with open(file_path, 'rb') as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json"
                )
            
            print(f"AUDIO PROCESSOR: ✅ Successfully transcribed {file_name}")
            return response.model_dump() if hasattr(response, 'model_dump') else dict(response)

        except (RateLimitError, APIError, APITimeoutError) as e:
            error_msg = f"OpenAI API error for '{file_name}': {type(e).__name__} - {e}. Retrying..."
            print(f"AUDIO PROCESSOR: ❌ {error_msg}")
            raise
        except Exception as e:
            error_msg = f"Whisper transcription failed for '{file_name}': {type(e).__name__} - {e}"
            print(f"AUDIO PROCESSOR: ❌ {error_msg}")
            raise AudioProcessingError(error_msg)
    
    async def process_audio_file(self, file_path: str, file_name: str) -> Union[TranscriptedMedia, MediaProcessingError]:
        """
        Processes a single audio file and returns transcription results.
        
        Args:
            file_path: Path to the audio file
            file_name: Original filename
            
        Returns:
            TranscriptedMedia on success, MediaProcessingError on failure
        """
        try:
            print(f"AUDIO PROCESSOR: Processing audio file: {file_name}")
            
            # Validate the audio file
            self._validate_audio_file(file_path, file_name)
            
            # Get file metadata
            file_size = os.path.getsize(file_path)
            try:
                mime_type = magic.from_file(file_path, mime=True)
            except:
                mime_type = "audio/unknown"
            
            metadata = FileMetadata(
                filename=file_name,
                content_type=mime_type,
                size=file_size
            )
            
            # Transcribe the audio
            transcription_result = await self._transcribe_with_whisper(file_path, file_name)
            
            # Extract information from the response
            transcript = transcription_result.get('text', '')
            duration = transcription_result.get('duration')
            language = transcription_result.get('language')
            
            # Calculate confidence score if segments are available
            confidence = None
            if 'segments' in transcription_result:
                segments = transcription_result['segments']
                if segments:
                    # Average confidence across all segments
                    confidences = [seg.get('avg_logprob', 0) for seg in segments if seg.get('avg_logprob')]
                    if confidences:
                        # Convert log probability to confidence percentage
                        confidence = min(100, max(0, (sum(confidences) / len(confidences) + 1) * 100))
            
            return TranscriptedMedia(
                file_name=file_name,
                transcript=transcript,
                duration=duration,
                language=language,
                confidence=confidence,
                metadata=metadata
            )
            
        except AudioProcessingError as e:
            return MediaProcessingError(
                source="AudioProcessor",
                file_name=file_name,
                error_message=str(e),
                error_type="AudioProcessingError"
            )
        except Exception as e:
            error_msg = f"Unexpected error processing audio file '{file_name}': {str(e)}"
            print(f"AUDIO PROCESSOR: ❌ {error_msg}")
            return MediaProcessingError(
                source="AudioProcessor",
                file_name=file_name,
                error_message=error_msg,
                error_type="UnexpectedError"
            )
    
    async def process_audio_from_streamlit(self, uploaded_file, file_name: str) -> Union[TranscriptedMedia, MediaProcessingError]:
        """
        Processes audio directly from Streamlit file upload.
        
        Args:
            uploaded_file: Streamlit UploadedFile object
            file_name: Original filename
            
        Returns:
            TranscriptedMedia on success, MediaProcessingError on failure
        """
        temp_path = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
                temp_path = temp_file.name
                temp_file.write(uploaded_file.getvalue())
            
            # Process the temporary file
            result = await self.process_audio_file(temp_path, file_name)
            return result
            
        except Exception as e:
            error_msg = f"Error processing Streamlit audio upload '{file_name}': {str(e)}"
            print(f"AUDIO PROCESSOR: ❌ {error_msg}")
            return MediaProcessingError(
                source="AudioProcessor",
                file_name=file_name,
                error_message=error_msg,
                error_type="StreamlitUploadError"
            )
        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    print(f"AUDIO PROCESSOR: Warning - Could not delete temp file {temp_path}: {e}")


# Convenience function for direct integration with existing file processing pipeline
async def process_audio(file_path: str, document_type, file_name: str, openai_client: OpenAI = None) -> TranscriptedMedia:
    """
    Convenience function for processing audio files in the existing file processing pipeline.
    
    Args:
        file_path: Path to the audio file
        document_type: DocumentType (for compatibility with existing processors)
        file_name: Original filename
        openai_client: OpenAI client instance
        
    Returns:
        TranscriptedMedia object with transcript content
        
    Note: This function is designed to integrate with the existing PROCESSOR_MAP pattern
    """
    if openai_client is None:
        raise AudioProcessingError("OpenAI client is required for audio processing")
    
    processor = AudioProcessor(openai_client)
    result = await processor.process_audio_file(file_path, file_name)
    
    if isinstance(result, MediaProcessingError):
        raise AudioProcessingError(f"Audio processing failed: {result.error_message}")
    
    return result