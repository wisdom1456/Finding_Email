from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from typing import Any

import magic
import vertexai
from google.api_core.exceptions import GoogleAPICallError, RetryError
from google.cloud import speech, storage
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)
from vertexai.generative_models import GenerativeModel, Part

from legal_portal.core.data_models import (
    CriminalEvidenceCategory,
    CriminalEvidenceItem,
    CriminalVideoAnalysis,
    EnhancedVideoInsight,
    FileMetadata,
    MediaProcessingError,
    TimeRange,
    VideoInsight,
)


class VideoProcessingError(Exception):
    """Custom exception for video processing errors."""


class VideoProcessor:
    """Handles video file processing and analysis using Google Cloud Vertex AI
    and Speech-to-Text. Enhanced with criminal law analysis capabilities.
    """

    def __init__(
        self,
        project_id: str | None = None,
        bucket_name: str | None = None,
        temp_folder: str = "temp-videos",
        skip_initialization: bool = False,
    ) -> None:
        from legal_portal.config.default import get_settings

        settings = get_settings()

        self.project_id = project_id or settings.gcp_project_id
        self.bucket_name = bucket_name or settings.gcp_bucket_name
        self.temp_folder = temp_folder
        self.enabled = False
        self.storage_client = None
        self.speech_client = None
        self.vertex_model = None

        # Allow skipping initialization for applications without video processing needs
        if skip_initialization:
            logger.info("VIDEO PROCESSOR: Skipping Google Cloud initialization (skip_initialization=True)")
            return

        # Check if Google Cloud configuration is available
        if not settings.video_processing_enabled:
            logger.warning(
                "VIDEO PROCESSOR: Google Cloud credentials not configured. Video processing will be disabled."
            )
            logger.info(
                "VIDEO PROCESSOR: To enable video processing, set the following environment variables:"
            )
            logger.info("  - GCP_PROJECT_ID: Your Google Cloud Project ID")
            logger.info("  - GCP_BUCKET_NAME: Your Google Cloud Storage bucket name")
            logger.info("  - GOOGLE_APPLICATION_CREDENTIALS: Path to your service account JSON file")
            return

        if not self.project_id or not self.bucket_name:
            logger.warning(
                "VIDEO PROCESSOR: GCP_PROJECT_ID and GCP_BUCKET_NAME are required for video processing."
            )
            return

        # Try to initialize Google Cloud clients
        try:
            # Check if credentials file exists if specified
            if settings.google_application_credentials:
                import os

                if not os.path.exists(settings.google_application_credentials):
                    logger.warning(
                        f"VIDEO PROCESSOR: Credentials file not found: {settings.google_application_credentials}"
                    )
                    logger.info(
                        "VIDEO PROCESSOR: Video processing will be disabled. Other document processing features remain available."
                    )
                    return

            vertexai.init(project=self.project_id, location="us-central1")
            self.storage_client = storage.Client(project=self.project_id)
            self.speech_client = speech.SpeechClient()
            self.vertex_model = GenerativeModel("gemini-2.5-flash")
            self.enabled = True
            logger.info(
                "VIDEO PROCESSOR: ✅ Google Cloud clients initialized successfully. Video processing is enabled."
            )
        except Exception as e:
            logger.warning(f"VIDEO PROCESSOR: Failed to initialize Google Cloud clients: {e}")
            logger.info(
                "VIDEO PROCESSOR: Video processing will be disabled. Other document processing features remain available."
            )
            # Don't raise an exception - allow the application to continue without video processing

        self.supported_formats = {
            "video/mp4",
            "video/quicktime",
            "video/x-msvideo",
            "video/webm",
            "video/x-flv",
            "video/3gpp",
        }

        self.max_file_size = 2 * 1024 * 1024 * 1024  # 2GB in bytes

        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self) -> None:
        if not self.enabled or not self.storage_client:
            return

        try:
            logger.debug(f"VIDEO PROCESSOR: 🔍 Checking bucket existence: {self.bucket_name}")
            bucket = self.storage_client.bucket(self.bucket_name)
            if not bucket.exists():
                logger.info(f"VIDEO PROCESSOR: 📝 Creating bucket: {self.bucket_name}")
                self.storage_client.create_bucket(self.bucket_name)
                logger.info("VIDEO PROCESSOR: ✅ Bucket created successfully")
            else:
                logger.info(f"VIDEO PROCESSOR: ✅ Using existing bucket: {self.bucket_name}")
        except Exception as e:
            logger.warning(f"VIDEO PROCESSOR: Could not access or create storage bucket: {e}")
            self.enabled = False

    def _validate_video_file(self, file_path: str, file_name: str) -> None:
        if not os.path.exists(file_path):
            msg = f"Video file not found: {file_name}"
            raise VideoProcessingError(msg)

        if os.path.getsize(file_path) > self.max_file_size:
            msg = f"Video file '{file_name}' exceeds 2GB size limit."
            raise VideoProcessingError(msg)

        try:
            mime_type = magic.from_file(file_path, mime=True)
        except Exception as e:
            msg = f"Could not determine MIME type for {file_name}: {e}"
            raise VideoProcessingError(msg)

        if mime_type not in self.supported_formats:
            msg = f"Unsupported video format for '{file_name}'. Detected: {mime_type}"
            raise VideoProcessingError(msg)

    def _upload_to_cloud_storage(self, file_path: str, file_name: str) -> str:
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            unique_name = f"{self.temp_folder}/{uuid.uuid4()}-{os.path.basename(file_name)}"
            blob = bucket.blob(unique_name)

            logger.info(f"VIDEO PROCESSOR: Uploading {file_name} to gs://{self.bucket_name}/{unique_name}")
            blob.upload_from_filename(file_path)
            gcs_uri = f"gs://{self.bucket_name}/{unique_name}"
            logger.info(f"VIDEO PROCESSOR: ✅ Successfully uploaded to {gcs_uri}")
            return gcs_uri
        except Exception as e:
            msg = f"Failed to upload '{file_name}' to GCS: {e}"
            raise VideoProcessingError(msg)

    def _get_criminal_analysis_prompt(self) -> str:
        """Generate specialized prompt for criminal law video analysis.
        Focuses on the 16 specific criminal evidence categories.
        """
        return """Analyze this criminal law video evidence and extract timestamped evidence segments for the following 16 categories. Return a JSON response with the structure below.

CRIMINAL EVIDENCE CATEGORIES TO ANALYZE:
1. Driving Pattern & Reason for Stop
2. Emergency Lights & Vehicle Pullover
3. Initial Roadside Approach & Observations
4. Preliminary Questioning & Admissions
5. Exit Order & Pre-Test Observations
6. Field Sobriety Tests
7. Portable Breath Test
8. Arrest Decision & Handcuffing
9. Miranda Warnings & Custodial Interrogation
10. Implied Consent & Chemical Test Request
11. Chemical Test Administration
12. Transport to Station/Jail
13. Booking & Processing
14. Right to Counsel & Phone Calls
15. Post-Booking Observation & Medical
16. Vehicle Tow & Inventory Search

ANALYSIS REQUIREMENTS:
- Identify precise timestamps for each category found in the video
- Assess constitutional compliance (4th, 5th, 6th Amendment issues)
- Evaluate evidence strength and legal significance
- Note procedural violations or constitutional concerns
- Provide detailed observations for legal analysis

REQUIRED JSON STRUCTURE:
{
  "evidence_items": [
    {
      "category": "Driving Pattern & Reason for Stop",
      "time_range": {
        "start_time": "MM:SS",
        "end_time": "MM:SS",
        "confidence": 0.95
      },
      "description": "Detailed description of what occurs during this time period",
      "key_observations": ["Specific observation 1", "Specific observation 2"],
      "legal_significance": "Why this evidence matters for the case outcome",
      "constitutional_issues": ["Potential 4th Amendment violation", "Procedural concern"],
      "evidence_strength": "strong"
    }
  ],
  "timeline_summary": "Chronological summary of events captured in the video",
  "constitutional_compliance_overview": "Overall assessment of constitutional compliance",
  "missing_categories": ["categories not found in video"]
}

EVIDENCE STRENGTH VALUES: Use only "strong", "moderate", or "weak"
TIMESTAMPS: Use MM:SS or HH:MM:SS format
CONSTITUTIONAL FOCUS: Emphasize 4th Amendment (search/seizure), 5th Amendment (self-incrimination), 6th Amendment (counsel) issues"""

    def _get_standard_analysis_prompt(self) -> str:
        """Generate standard prompt for non-criminal video analysis."""
        return """Analyze the provided video for a legal case and generate a structured JSON output with:
        1. "summary": A concise summary of the video's content.
        2. "timeline": A timeline of key events with timestamps.
        3. "objects": A list of significant objects detected with timestamps.
        4. "content_moderation": A summary of any sensitive content.
        """

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=10, max=300),
        retry=retry_if_exception_type((GoogleAPICallError, RetryError, Exception)),
    )
    async def _analyze_with_vertex_ai(
        self, gcs_uri: str, file_name: str, is_criminal_case: bool = False
    ) -> dict[str, Any]:
        try:
            logger.info(f"VIDEO PROCESSOR: Starting Vertex AI analysis for {file_name} ({gcs_uri})")
            if is_criminal_case:
                logger.info(f"VIDEO PROCESSOR: Using enhanced criminal law analysis for {file_name}")

            video_file = Part.from_uri(uri=gcs_uri, mime_type="video/mp4")
            prompt = (
                self._get_criminal_analysis_prompt()
                if is_criminal_case
                else self._get_standard_analysis_prompt()
            )

            response = self.vertex_model.generate_content([video_file, prompt])
            logger.info(f"VIDEO PROCESSOR: ✅ Vertex AI analysis completed for {file_name}")
            return self._parse_json_response(response.text)
        except (GoogleAPICallError, RetryError) as e:
            error_message = str(e)
            # Handle Google Cloud service agent provisioning specifically
            if "Service agents are being provisioned" in error_message:
                logger.info(
                    f"VIDEO PROCESSOR: ⏳ Google Cloud service agents still provisioning for {file_name}. This is a one-time setup process."
                )
                logger.info("VIDEO PROCESSOR: 🔄 Will retry with exponential backoff (up to 5 minutes)...")
                raise  # Let tenacity handle the retry
            msg = f"Vertex AI API call failed for '{file_name}': {e}"
            raise VideoProcessingError(msg)
        except Exception as e:
            error_message = str(e)
            # Handle Google Cloud service agent provisioning for generic exceptions too
            if "Service agents are being provisioned" in error_message:
                logger.info(
                    f"VIDEO PROCESSOR: ⏳ Google Cloud service agents still provisioning for {file_name}. This is a one-time setup process."
                )
                logger.info("VIDEO PROCESSOR: 🔄 Will retry with exponential backoff (up to 5 minutes)...")
                raise  # Let tenacity handle the retry
            msg = f"Vertex AI analysis failed for '{file_name}': {e}"
            raise VideoProcessingError(msg)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((GoogleAPICallError, RetryError)),
    )
    async def _transcribe_with_speech_to_text(self, gcs_uri: str, file_name: str) -> str:
        try:
            logger.info(f"VIDEO PROCESSOR: Starting audio transcription for {file_name} ({gcs_uri})")

            # Check if this is a video file - Speech-to-Text API requires pure audio
            file_extension = os.path.splitext(file_name)[1].lower()
            if file_extension in [".mov", ".mp4", ".avi", ".mkv", ".webm"]:
                logger.info(
                    f"VIDEO PROCESSOR: ⚠️  Skipping direct audio transcription for video file {file_name}"
                )
                logger.info(
                    "VIDEO PROCESSOR: Note: Speech-to-Text API requires pure audio files, not video containers"
                )
                return "Audio transcription not available for video files. Consider using Vertex AI's video analysis capabilities."

            audio = speech.RecognitionAudio(uri=gcs_uri)

            # Configure for audio files with automatic encoding detection
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,  # Let Google detect encoding
                language_code="en-US",
                enable_automatic_punctuation=True,
                enable_word_time_offsets=True,  # Useful for analysis
            )

            operation = self.speech_client.long_running_recognize(config=config, audio=audio)
            response = operation.result(timeout=600)
            transcript = "".join(result.alternatives[0].transcript for result in response.results)
            logger.info(f"VIDEO PROCESSOR: ✅ Transcription completed for {file_name}")
            return transcript
        except (GoogleAPICallError, RetryError) as e:
            error_msg = str(e)
            if "bad encoding" in error_msg or "Invalid recognition" in error_msg:
                logger.info(
                    f"VIDEO PROCESSOR: ⚠️  Audio transcription not supported for this file format: {file_name}"
                )
                return "Audio transcription not supported for this file format. Video analysis available via Vertex AI."
            msg = f"Speech-to-Text API call failed for '{file_name}': {e}"
            raise VideoProcessingError(msg)
        except Exception as e:
            error_msg = str(e)
            if "bad encoding" in error_msg or "Invalid recognition" in error_msg:
                logger.info(
                    f"VIDEO PROCESSOR: ⚠️  Audio transcription not supported for this file format: {file_name}"
                )
                return "Audio transcription not supported for this file format. Video analysis available via Vertex AI."
            msg = f"Speech-to-Text failed for '{file_name}': {e}"
            raise VideoProcessingError(msg)

    def _parse_json_response(self, response_text: str) -> dict[str, Any]:
        try:
            clean_response = response_text.strip().replace("```json", "").replace("```", "")
            return json.loads(clean_response)
        except (json.JSONDecodeError, AttributeError):
            return {
                "error": "Failed to parse JSON from model.",
                "raw_response": response_text,
            }

    def _parse_criminal_analysis(self, analysis_result: dict[str, Any]) -> CriminalVideoAnalysis | None:
        """Parse criminal analysis response into structured CriminalVideoAnalysis model."""
        try:
            if "error" in analysis_result:
                logger.info("VIDEO PROCESSOR: ⚠️ Criminal analysis parsing skipped due to API error")
                return None

            evidence_items = []
            raw_evidence_items = analysis_result.get("evidence_items", [])

            for item_data in raw_evidence_items:
                try:
                    # Parse time range
                    time_range_data = item_data.get("time_range", {})
                    time_range = TimeRange(
                        start_time=time_range_data.get("start_time", "00:00"),
                        end_time=time_range_data.get("end_time", "00:00"),
                        confidence=float(time_range_data.get("confidence", 0.5)),
                    )

                    # Parse criminal evidence category
                    category_name = item_data.get("category", "")
                    category = None
                    for cat in CriminalEvidenceCategory:
                        if cat.value == category_name:
                            category = cat
                            break

                    if not category:
                        logger.info(f"VIDEO PROCESSOR: ⚠️ Unknown criminal evidence category: {category_name}")
                        continue

                    # Create criminal evidence item
                    evidence_item = CriminalEvidenceItem(
                        category=category,
                        time_range=time_range,
                        description=item_data.get("description", ""),
                        key_observations=item_data.get("key_observations", []),
                        legal_significance=item_data.get("legal_significance", ""),
                        constitutional_issues=item_data.get("constitutional_issues", []),
                        evidence_strength=item_data.get("evidence_strength", "moderate").lower(),
                    )
                    evidence_items.append(evidence_item)
                except Exception as e:
                    logger.error(f"VIDEO PROCESSOR: ⚠️ Failed to parse evidence item: {e}")
                    continue

            # Parse missing categories
            missing_categories = []
            raw_missing = analysis_result.get("missing_categories", [])
            for missing_name in raw_missing:
                for cat in CriminalEvidenceCategory:
                    if cat.value == missing_name:
                        missing_categories.append(cat)
                        break

            return CriminalVideoAnalysis(
                evidence_items=evidence_items,
                timeline_summary=analysis_result.get("timeline_summary", ""),
                constitutional_compliance_overview=analysis_result.get(
                    "constitutional_compliance_overview", ""
                ),
                missing_categories=missing_categories,
            )
        except Exception as e:
            logger.error(f"VIDEO PROCESSOR: ⚠️ Failed to parse criminal analysis: {e}")
            return None

    def _delete_from_cloud_storage(self, gcs_uri: str) -> None:
        try:
            bucket_name, blob_name = gcs_uri.replace("gs://", "").split("/", 1)
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            if blob.exists():
                logger.info(f"VIDEO PROCESSOR: Deleting {gcs_uri} from GCS.")
                blob.delete()
        except Exception as e:
            logger.info(f"VIDEO PROCESSOR: Warning - Failed to delete {gcs_uri} from GCS: {e}")

    async def process_video_file(
        self, file_path: str, file_name: str, is_criminal_case: bool = False
    ) -> VideoInsight | EnhancedVideoInsight | MediaProcessingError:
        # Check if video processing is enabled
        if not self.enabled:
            return MediaProcessingError(
                source="VideoProcessor",
                file_name=file_name,
                error_message="Video processing is disabled. Google Cloud credentials are not configured.",
                error_type="ConfigurationError",
            )

        gcs_uri = None
        try:
            logger.debug(f"VIDEO PROCESSOR: Processing video file: {file_name}")
            if is_criminal_case:
                logger.info(f"VIDEO PROCESSOR: Criminal case analysis enabled for {file_name}")

            self._validate_video_file(file_path, file_name)
            metadata = FileMetadata(
                filename=file_name,
                content_type=magic.from_file(file_path, mime=True),
                size=os.path.getsize(file_path),
            )
            gcs_uri = self._upload_to_cloud_storage(file_path, file_name)

            analysis_task = self._analyze_with_vertex_ai(gcs_uri, file_name, is_criminal_case)
            transcription_task = self._transcribe_with_speech_to_text(gcs_uri, file_name)

            analysis_result, transcription_result = await asyncio.gather(analysis_task, transcription_task)

            insights = {"vertex_analysis": analysis_result}

            # Safely extract and normalize data from the analysis_result dictionary
            labels = analysis_result.get("labels", [])
            raw_objects = analysis_result.get("objects", [])
            text_annotations = analysis_result.get("text_annotations", [])
            duration = analysis_result.get("duration")
            confidence = analysis_result.get("confidence")

            # Extract object names from Vertex AI's structured object data
            objects = []
            if isinstance(raw_objects, list):
                for obj in raw_objects:
                    if isinstance(obj, dict):
                        # Extract the object name from structured data
                        object_name = obj.get("object", str(obj))
                        timestamps = obj.get("timestamps", [])
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

            # For criminal cases, return EnhancedVideoInsight with criminal analysis
            if is_criminal_case:
                criminal_analysis = self._parse_criminal_analysis(analysis_result)
                return EnhancedVideoInsight(
                    file_name=file_name,
                    insights=insights,
                    transcript=transcription_result,
                    metadata=metadata,
                    labels=labels,
                    objects=objects,
                    text_annotations=text_annotations,
                    duration=duration,
                    confidence=confidence,
                    criminal_analysis=criminal_analysis,
                    is_criminal_case=True,
                )
            # For non-criminal cases, return standard VideoInsight
            return VideoInsight(
                file_name=file_name,
                insights=insights,
                transcript=transcription_result,
                metadata=metadata,
                labels=labels,
                objects=objects,
                text_annotations=text_annotations,
                duration=duration,
                confidence=confidence,
            )
        except Exception as e:
            return MediaProcessingError(
                source="VideoProcessor",
                file_name=file_name,
                error_message=str(e),
                error_type=type(e).__name__,
            )
        finally:
            if gcs_uri:
                self._delete_from_cloud_storage(gcs_uri)

    async def process_video_from_streamlit(
        self, uploaded_file, file_name: str, is_criminal_case: bool = False
    ) -> VideoInsight | EnhancedVideoInsight | MediaProcessingError:
        # Check if video processing is enabled
        if not self.enabled:
            return MediaProcessingError(
                source="VideoProcessor",
                file_name=file_name,
                error_message="Video processing is disabled. Google Cloud credentials are not configured.",
                error_type="ConfigurationError",
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
            temp_path = temp_file.name
            temp_file.write(uploaded_file.getvalue())

        try:
            return await self.process_video_file(temp_path, file_name, is_criminal_case)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


async def process_video(
    file_path: str,
    document_type,
    file_name: str,
    project_id: str,
    bucket_name: str,
    is_criminal_case: bool = False,
) -> VideoInsight | EnhancedVideoInsight:
    if not project_id or not bucket_name:
        msg = "Google Cloud project_id and bucket_name are required."
        raise VideoProcessingError(msg)
    processor = VideoProcessor(project_id=project_id, bucket_name=bucket_name)
    result = await processor.process_video_file(file_path, file_name, is_criminal_case)
    if isinstance(result, MediaProcessingError):
        msg = f"Video processing failed: {result.error_message}"
        raise VideoProcessingError(msg)
    return result
