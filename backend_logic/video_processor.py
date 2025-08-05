import asyncio
import os
import tempfile
import uuid
import json
from typing import Optional, Union, List, Dict, Any

from google.api_core.exceptions import GoogleAPICallError, RetryError
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.cloud import storage
from google.cloud import speech
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import magic

from backend.utils.data_models import (
    VideoInsight,
    MediaProcessingError,
    FileMetadata,
    FileType
)


class VideoProcessingError(Exception):
    """Custom exception for video processing errors."""
    pass


class VideoProcessor:
    """
    Handles video file processing and analysis using Google Cloud Vertex AI
    and Speech-to-Text.
    """
    
    def __init__(self, project_id: Optional[str] = None, bucket_name: Optional[str] = None, temp_folder: str = "temp-videos"):
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self.bucket_name = bucket_name or os.getenv("GCP_BUCKET_NAME")

        if not self.project_id or not self.bucket_name:
            raise VideoProcessingError("GCP_PROJECT_ID and GCP_BUCKET_NAME must be set in environment variables.")

        self.temp_folder = temp_folder
        
        try:
            vertexai.init(project=self.project_id, location="us-central1")
            self.storage_client = storage.Client(project=self.project_id)
            self.speech_client = speech.SpeechClient()
            self.vertex_model = GenerativeModel("gemini-2.5-flash")
            print("VIDEO PROCESSOR: Vertex AI and other Google Cloud clients initialized successfully.")
        except Exception as e:
            raise VideoProcessingError(f"Failed to initialize Google Cloud clients: {e}")

        self.supported_formats = {
            'video/mp4', 'video/quicktime', 'video/x-msvideo',
            'video/webm', 'video/x-flv', 'video/3gpp',
        }
        
        self.max_file_size = 2 * 1024 * 1024 * 1024  # 2GB in bytes
        
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self) -> None:
        try:
            print(f"VIDEO PROCESSOR: 🔍 Checking bucket existence: {self.bucket_name}")
            bucket = self.storage_client.bucket(self.bucket_name)
            if not bucket.exists():
                print(f"VIDEO PROCESSOR: 📝 Creating bucket: {self.bucket_name}")
                self.storage_client.create_bucket(self.bucket_name)
                print(f"VIDEO PROCESSOR: ✅ Bucket created successfully")
            else:
                print(f"VIDEO PROCESSOR: ✅ Using existing bucket: {self.bucket_name}")
        except Exception as e:
            raise VideoProcessingError(f"Could not access or create storage bucket: {e}")
    
    def _validate_video_file(self, file_path: str, file_name: str) -> None:
        if not os.path.exists(file_path):
            raise VideoProcessingError(f"Video file not found: {file_name}")
        
        if os.path.getsize(file_path) > self.max_file_size:
            raise VideoProcessingError(f"Video file '{file_name}' exceeds 2GB size limit.")
        
        try:
            mime_type = magic.from_file(file_path, mime=True)
        except Exception as e:
            raise VideoProcessingError(f"Could not determine MIME type for {file_name}: {e}")

        if mime_type not in self.supported_formats:
            raise VideoProcessingError(f"Unsupported video format for '{file_name}'. Detected: {mime_type}")
    
    def _upload_to_cloud_storage(self, file_path: str, file_name: str) -> str:
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            unique_name = f"{self.temp_folder}/{uuid.uuid4()}-{os.path.basename(file_name)}"
            blob = bucket.blob(unique_name)
            
            print(f"VIDEO PROCESSOR: Uploading {file_name} to gs://{self.bucket_name}/{unique_name}")
            blob.upload_from_filename(file_path)
            gcs_uri = f"gs://{self.bucket_name}/{unique_name}"
            print(f"VIDEO PROCESSOR: ✅ Successfully uploaded to {gcs_uri}")
            return gcs_uri
        except Exception as e:
            raise VideoProcessingError(f"Failed to upload '{file_name}' to GCS: {e}")

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=10, max=300), retry=retry_if_exception_type((GoogleAPICallError, RetryError, Exception)))
    async def _analyze_with_vertex_ai(self, gcs_uri: str, file_name: str) -> Dict[str, Any]:
        try:
            print(f"VIDEO PROCESSOR: Starting Vertex AI analysis for {file_name} ({gcs_uri})")
            video_file = Part.from_uri(uri=gcs_uri, mime_type="video/mp4")
            prompt = """Analyze the provided video for a legal case and generate a structured JSON output with:
            1. "summary": A concise summary of the video's content.
            2. "timeline": A timeline of key events with timestamps.
            3. "objects": A list of significant objects detected with timestamps.
            4. "content_moderation": A summary of any sensitive content.
            """
            response = self.vertex_model.generate_content([video_file, prompt])
            print(f"VIDEO PROCESSOR: ✅ Vertex AI analysis completed for {file_name}")
            return self._parse_json_response(response.text)
        except (GoogleAPICallError, RetryError) as e:
            error_message = str(e)
            # Handle Google Cloud service agent provisioning specifically
            if "Service agents are being provisioned" in error_message:
                print(f"VIDEO PROCESSOR: ⏳ Google Cloud service agents still provisioning for {file_name}. This is a one-time setup process.")
                print(f"VIDEO PROCESSOR: 🔄 Will retry with exponential backoff (up to 5 minutes)...")
                raise  # Let tenacity handle the retry
            raise VideoProcessingError(f"Vertex AI API call failed for '{file_name}': {e}")
        except Exception as e:
            error_message = str(e)
            # Handle Google Cloud service agent provisioning for generic exceptions too
            if "Service agents are being provisioned" in error_message:
                print(f"VIDEO PROCESSOR: ⏳ Google Cloud service agents still provisioning for {file_name}. This is a one-time setup process.")
                print(f"VIDEO PROCESSOR: 🔄 Will retry with exponential backoff (up to 5 minutes)...")
                raise  # Let tenacity handle the retry
            raise VideoProcessingError(f"Vertex AI analysis failed for '{file_name}': {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10), retry=retry_if_exception_type((GoogleAPICallError, RetryError)))
    async def _transcribe_with_speech_to_text(self, gcs_uri: str, file_name: str) -> str:
        try:
            print(f"VIDEO PROCESSOR: Starting audio transcription for {file_name} ({gcs_uri})")
            
            # Check if this is a video file - Speech-to-Text API requires pure audio
            file_extension = os.path.splitext(file_name)[1].lower()
            if file_extension in ['.mov', '.mp4', '.avi', '.mkv', '.webm']:
                print(f"VIDEO PROCESSOR: ⚠️  Skipping direct audio transcription for video file {file_name}")
                print(f"VIDEO PROCESSOR: Note: Speech-to-Text API requires pure audio files, not video containers")
                return "Audio transcription not available for video files. Consider using Vertex AI's video analysis capabilities."
            
            audio = speech.RecognitionAudio(uri=gcs_uri)
            
            # Configure for audio files with automatic encoding detection
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,  # Let Google detect encoding
                language_code="en-US",
                enable_automatic_punctuation=True,
                enable_word_time_offsets=True  # Useful for analysis
            )
            
            operation = self.speech_client.long_running_recognize(config=config, audio=audio)
            response = operation.result(timeout=600)
            transcript = "".join(result.alternatives[0].transcript for result in response.results)
            print(f"VIDEO PROCESSOR: ✅ Transcription completed for {file_name}")
            return transcript
        except (GoogleAPICallError, RetryError) as e:
            error_msg = str(e)
            if "bad encoding" in error_msg or "Invalid recognition" in error_msg:
                print(f"VIDEO PROCESSOR: ⚠️  Audio transcription not supported for this file format: {file_name}")
                return "Audio transcription not supported for this file format. Video analysis available via Vertex AI."
            raise VideoProcessingError(f"Speech-to-Text API call failed for '{file_name}': {e}")
        except Exception as e:
            error_msg = str(e)
            if "bad encoding" in error_msg or "Invalid recognition" in error_msg:
                print(f"VIDEO PROCESSOR: ⚠️  Audio transcription not supported for this file format: {file_name}")
                return "Audio transcription not supported for this file format. Video analysis available via Vertex AI."
            raise VideoProcessingError(f"Speech-to-Text failed for '{file_name}': {e}")
            
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        try:
            clean_response = response_text.strip().replace("```json", "").replace("```", "")
            return json.loads(clean_response)
        except (json.JSONDecodeError, AttributeError) as e:
            return {"error": "Failed to parse JSON from model.", "raw_response": response_text}

    def _delete_from_cloud_storage(self, gcs_uri: str) -> None:
        try:
            bucket_name, blob_name = gcs_uri.replace("gs://", "").split("/", 1)
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            if blob.exists():
                print(f"VIDEO PROCESSOR: Deleting {gcs_uri} from GCS.")
                blob.delete()
        except Exception as e:
            print(f"VIDEO PROCESSOR: Warning - Failed to delete {gcs_uri} from GCS: {e}")

    async def process_video_file(self, file_path: str, file_name: str) -> Union[VideoInsight, MediaProcessingError]:
        gcs_uri = None
        try:
            print(f"VIDEO PROCESSOR: Processing video file: {file_name}")
            self._validate_video_file(file_path, file_name)
            metadata = FileMetadata(filename=file_name, content_type=magic.from_file(file_path, mime=True), size=os.path.getsize(file_path))
            gcs_uri = self._upload_to_cloud_storage(file_path, file_name)
            
            analysis_task = self._analyze_with_vertex_ai(gcs_uri, file_name)
            transcription_task = self._transcribe_with_speech_to_text(gcs_uri, file_name)
            
            analysis_result, transcription_result = await asyncio.gather(analysis_task, transcription_task)
            
            insights = {"vertex_analysis": analysis_result}

            # Safely extract and normalize data from the analysis_result dictionary
            labels = analysis_result.get('labels', [])
            raw_objects = analysis_result.get('objects', [])
            text_annotations = analysis_result.get('text_annotations', [])
            duration = analysis_result.get('duration')
            confidence = analysis_result.get('confidence')

            # Extract object names from Vertex AI's structured object data
            objects = []
            if isinstance(raw_objects, list):
                for obj in raw_objects:
                    if isinstance(obj, dict):
                        # Extract the object name from structured data
                        object_name = obj.get('object', str(obj))
                        timestamps = obj.get('timestamps', [])
                        if timestamps:
                            objects.append(f"{object_name} ({', '.join(timestamps)})")
                        else:
                            objects.append(object_name)
                    elif isinstance(obj, str):
                        objects.append(obj)
                    else:
                        objects.append(str(obj))
            else:
                objects = raw_objects if isinstance(raw_objects, list) else []

            # Ensure labels and text_annotations are string lists
            if not isinstance(labels, list):
                labels = []
            labels = [str(label) for label in labels]
            
            if not isinstance(text_annotations, list):
                text_annotations = []
            text_annotations = [str(annotation) for annotation in text_annotations]

            return VideoInsight(
                file_name=file_name,
                insights=insights,
                transcript=transcription_result,
                metadata=metadata,
                labels=labels,
                objects=objects,
                text_annotations=text_annotations,
                duration=duration,
                confidence=confidence
            )
        except Exception as e:
            return MediaProcessingError(source="VideoProcessor", file_name=file_name, error_message=str(e), error_type=type(e).__name__)
        finally:
            if gcs_uri:
                self._delete_from_cloud_storage(gcs_uri)

    async def process_video_from_streamlit(self, uploaded_file, file_name: str) -> Union[VideoInsight, MediaProcessingError]:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
            temp_path = temp_file.name
            temp_file.write(uploaded_file.getvalue())
        
        try:
            return await self.process_video_file(temp_path, file_name)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

async def process_video(file_path: str, document_type, file_name: str, project_id: str, bucket_name: str) -> VideoInsight:
    if not project_id or not bucket_name:
        raise VideoProcessingError("Google Cloud project_id and bucket_name are required.")
    processor = VideoProcessor(project_id=project_id, bucket_name=bucket_name)
    result = await processor.process_video_file(file_path, file_name)
    if isinstance(result, MediaProcessingError):
        raise VideoProcessingError(f"Video processing failed: {result.error_message}")
    return result