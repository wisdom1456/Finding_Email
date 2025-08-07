"""
Media processing and analysis functionality for AI components.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

# Optional imports with fallback handling
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("MEDIA PROCESSOR: ⚠️  OpenCV (cv2) not available - video processing will use fallback methods")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("MEDIA PROCESSOR: ⚠️  NumPy not available - advanced video analysis will be limited")

try:
    from google.cloud import videointelligence, storage
    GOOGLE_CLOUD_AVAILABLE = True
except ImportError:
    GOOGLE_CLOUD_AVAILABLE = False
    print("MEDIA PROCESSOR: ⚠️  Google Cloud libraries not available - using local processing only")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("MEDIA PROCESSOR: ⚠️  PIL not available - image processing will be limited")


class MediaProcessor:
    """Handles media file processing and analysis."""

    def __init__(self):
        """Initialize MediaProcessor."""
        self.supported_video_formats = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv'}
        self.supported_image_formats = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}

    def process_video_with_google_api(self, file_path: str, file_name: str) -> Dict[str, Any]:
        """Process video using Google Cloud Video Intelligence API."""
        print(f"MEDIA PROCESSOR: 🎥 Processing video: {file_name}")
        
        if not GOOGLE_CLOUD_AVAILABLE:
            print("MEDIA PROCESSOR: ⚠️  Google Cloud not available, using fallback analysis")
            return self._create_fallback_video_analysis(file_path, file_name)
        
        try:
            # Initialize the client
            client = videointelligence.VideoIntelligenceServiceClient()
            
            # Upload to GCS bucket for processing
            bucket_name = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET")
            if not bucket_name:
                print("MEDIA PROCESSOR: ⚠️  Google Cloud Storage bucket not configured")
                return self._create_fallback_video_analysis(file_path, file_name)
            
            gcs_uri = self._upload_to_gcs(file_path, file_name, bucket_name)
            if not gcs_uri:
                return self._create_fallback_video_analysis(file_path, file_name)
            
            # Configure analysis features
            features = [
                videointelligence.Feature.LABEL_DETECTION,
                videointelligence.Feature.OBJECT_TRACKING,
                videointelligence.Feature.TEXT_DETECTION,
                videointelligence.Feature.SPEECH_TRANSCRIPTION,
            ]
            
            # Speech transcription config
            config = videointelligence.SpeechTranscriptionConfig(
                language_code="en-US",
                enable_automatic_punctuation=True,
            )
            
            # Create the request
            request = videointelligence.AnnotateVideoRequest(
                input_uri=gcs_uri,
                features=features,
                video_context=videointelligence.VideoContext(
                    speech_transcription_config=config,
                ),
            )
            
            print(f"MEDIA PROCESSOR: 🔄 Starting Google Video Intelligence analysis for {file_name}")
            operation = client.annotate_video(request=request)
            
            # Wait for operation to complete
            print(f"MEDIA PROCESSOR: ⏳ Waiting for analysis to complete...")
            result = operation.result(timeout=300)  # 5 minute timeout
            
            # Parse results
            analysis_result = self._parse_video_intelligence_results(result, file_name)
            
            # Clean up GCS file
            self._cleanup_gcs_file(gcs_uri, bucket_name)
            
            return analysis_result
            
        except Exception as e:
            print(f"MEDIA PROCESSOR: ❌ Google Video Intelligence error: {e}")
            return self._create_fallback_video_analysis(file_path, file_name)

    def _upload_to_gcs(self, file_path: str, file_name: str, bucket_name: str) -> Optional[str]:
        """Upload file to Google Cloud Storage."""
        if not GOOGLE_CLOUD_AVAILABLE:
            print("MEDIA PROCESSOR: ⚠️  Google Cloud Storage not available")
            return None
            
        try:
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            
            # Create a unique blob name
            blob_name = f"video_analysis/{file_name}"
            blob = bucket.blob(blob_name)
            
            print(f"MEDIA PROCESSOR: ☁️  Uploading {file_name} to GCS...")
            blob.upload_from_filename(file_path)
            
            gcs_uri = f"gs://{bucket_name}/{blob_name}"
            print(f"MEDIA PROCESSOR: ✅ Upload complete: {gcs_uri}")
            return gcs_uri
            
        except Exception as e:
            print(f"MEDIA PROCESSOR: ❌ GCS upload error: {e}")
            return None

    def _cleanup_gcs_file(self, gcs_uri: str, bucket_name: str) -> None:
        """Clean up uploaded file from GCS."""
        if not GOOGLE_CLOUD_AVAILABLE:
            print("MEDIA PROCESSOR: ⚠️  Google Cloud Storage not available for cleanup")
            return
            
        try:
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob_name = gcs_uri.replace(f"gs://{bucket_name}/", "")
            blob = bucket.blob(blob_name)
            blob.delete()
            print(f"MEDIA PROCESSOR: 🗑️  Cleaned up GCS file: {blob_name}")
        except Exception as e:
            print(f"MEDIA PROCESSOR: ⚠️  GCS cleanup error: {e}")

    def _parse_video_intelligence_results(self, result, file_name: str) -> Dict[str, Any]:
        """Parse Google Video Intelligence API results."""
        insights = {
            "labels": [],
            "objects": [],
            "text_annotations": [],
            "transcript": "",
            "analysis_method": "google_video_intelligence"
        }
        
        # Extract labels
        for annotation in result.annotation_results[0].segment_label_annotations:
            for entity in annotation.entity.description:
                if entity not in insights["labels"]:
                    insights["labels"].append(entity)
        
        # Extract objects
        for annotation in result.annotation_results[0].object_annotations:
            entity = annotation.entity.description
            if entity not in insights["objects"]:
                insights["objects"].append(entity)
        
        # Extract text
        for annotation in result.annotation_results[0].text_annotations:
            for text_segment in annotation.segments:
                text = text_segment.segment.start_time_offset.total_seconds()
                insights["text_annotations"].append({
                    "text": annotation.text,
                    "start_time": text
                })
        
        # Extract transcript
        transcript_parts = []
        if result.annotation_results[0].speech_transcriptions:
            for transcription in result.annotation_results[0].speech_transcriptions:
                for alternative in transcription.alternatives:
                    transcript_parts.append(alternative.transcript)
        
        insights["transcript"] = " ".join(transcript_parts)
        
        print(f"MEDIA PROCESSOR: 📊 Google Video Intelligence analysis complete for {file_name}")
        print(f"MEDIA PROCESSOR: 📊   - Labels: {len(insights['labels'])}")
        print(f"MEDIA PROCESSOR: 📊   - Objects: {len(insights['objects'])}")
        print(f"MEDIA PROCESSOR: 📊   - Text annotations: {len(insights['text_annotations'])}")
        print(f"MEDIA PROCESSOR: 📊   - Transcript length: {len(insights['transcript'])} chars")
        
        return {
            "file_name": file_name,
            "insights": insights,
            "labels": insights["labels"],
            "objects": insights["objects"],
            "text_annotations": insights["text_annotations"],
            "transcript": insights["transcript"]
        }

    def _create_fallback_video_analysis(self, file_path: str, file_name: str) -> Dict[str, Any]:
        """Create fallback video analysis using local processing."""
        print(f"MEDIA PROCESSOR: 🔄 Using fallback local analysis for {file_name}")
        
        try:
            # Get basic video metadata
            cap = cv2.VideoCapture(file_path)
            
            if not cap.isOpened():
                print(f"MEDIA PROCESSOR: ❌ Could not open video file: {file_path}")
                return self._create_empty_video_analysis(file_name)
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            
            # Sample frames for basic analysis
            frame_samples = self._sample_video_frames(cap, num_samples=5)
            
            cap.release()
            
            # Basic content detection
            basic_analysis = self._analyze_frame_samples(frame_samples)
            
            insights = {
                "duration_seconds": duration,
                "fps": fps,
                "frame_count": frame_count,
                "analysis_method": "local_opencv",
                **basic_analysis
            }
            
            print(f"MEDIA PROCESSOR: 📊 Local analysis complete for {file_name}")
            print(f"MEDIA PROCESSOR: 📊   - Duration: {duration:.1f}s")
            print(f"MEDIA PROCESSOR: 📊   - Frames: {frame_count}")
            
            return {
                "file_name": file_name,
                "insights": insights,
                "labels": basic_analysis.get("labels", []),
                "objects": basic_analysis.get("objects", []),
                "text_annotations": [],
                "transcript": ""
            }
            
        except Exception as e:
            print(f"MEDIA PROCESSOR: ❌ Fallback analysis error: {e}")
            return self._create_empty_video_analysis(file_name)

    def _sample_video_frames(self, cap, num_samples: int = 5) -> List[np.ndarray]:
        """Sample frames from video for analysis."""
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        samples = []
        
        if frame_count < num_samples:
            num_samples = frame_count
        
        for i in range(num_samples):
            frame_number = int((i / (num_samples - 1)) * (frame_count - 1)) if num_samples > 1 else 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            
            ret, frame = cap.read()
            if ret:
                samples.append(frame)
        
        return samples

    def _analyze_frame_samples(self, frames: List[np.ndarray]) -> Dict[str, Any]:
        """Perform basic analysis on frame samples."""
        if not frames:
            return {"labels": [], "objects": []}
        
        # Basic color and content analysis
        avg_brightness = []
        colors_detected = []
        
        for frame in frames:
            # Calculate average brightness
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = np.mean(gray)
            avg_brightness.append(brightness)
            
            # Basic color detection
            dominant_color = self._get_dominant_color(frame)
            colors_detected.append(dominant_color)
        
        # Generate basic labels based on analysis
        labels = []
        overall_brightness = np.mean(avg_brightness)
        
        if overall_brightness < 50:
            labels.append("dark_content")
        elif overall_brightness > 200:
            labels.append("bright_content")
        else:
            labels.append("normal_lighting")
        
        # Add color-based labels
        if any("blue" in color for color in colors_detected):
            labels.append("blue_tones")
        if any("red" in color for color in colors_detected):
            labels.append("red_tones")
        
        return {
            "labels": labels,
            "objects": ["video_content"],  # Generic object
            "brightness_analysis": {
                "average": float(overall_brightness),
                "range": [float(min(avg_brightness)), float(max(avg_brightness))]
            }
        }

    def _get_dominant_color(self, frame: np.ndarray) -> str:
        """Get dominant color from frame."""
        # Resize frame for faster processing
        small_frame = cv2.resize(frame, (50, 50))
        
        # Calculate color channels
        b, g, r = cv2.split(small_frame)
        avg_b, avg_g, avg_r = np.mean(b), np.mean(g), np.mean(r)
        
        # Determine dominant color
        if avg_r > avg_g and avg_r > avg_b:
            return "red_dominant"
        elif avg_g > avg_r and avg_g > avg_b:
            return "green_dominant"
        elif avg_b > avg_r and avg_b > avg_g:
            return "blue_dominant"
        else:
            return "neutral_tones"

    def _create_empty_video_analysis(self, file_name: str) -> Dict[str, Any]:
        """Create empty video analysis result."""
        return {
            "file_name": file_name,
            "insights": {
                "error": "Could not analyze video file",
                "analysis_method": "failed"
            },
            "labels": [],
            "objects": [],
            "text_annotations": [],
            "transcript": ""
        }

    def process_image(self, file_path: str, file_name: str) -> Dict[str, Any]:
        """Process image file for basic analysis."""
        print(f"MEDIA PROCESSOR: 🖼️  Processing image: {file_name}")
        
        try:
            with Image.open(file_path) as img:
                # Get basic image properties
                width, height = img.size
                mode = img.mode
                format_name = img.format
                
                # Convert to RGB for analysis
                if mode != 'RGB':
                    img = img.convert('RGB')
                
                # Basic color analysis
                colors = img.getcolors(maxcolors=256*256*256)
                dominant_colors = sorted(colors, key=lambda x: x[0], reverse=True)[:5] if colors else []
                
                insights = {
                    "width": width,
                    "height": height,
                    "mode": mode,
                    "format": format_name,
                    "dominant_colors": [color[1] for color in dominant_colors],
                    "analysis_method": "pillow"
                }
                
                # Generate basic labels
                labels = [f"{mode.lower()}_image", f"{format_name.lower()}_format"]
                if width > height:
                    labels.append("landscape_orientation")
                elif height > width:
                    labels.append("portrait_orientation")
                else:
                    labels.append("square_orientation")
                
                print(f"MEDIA PROCESSOR: 📊 Image analysis complete for {file_name}")
                print(f"MEDIA PROCESSOR: 📊   - Dimensions: {width}x{height}")
                print(f"MEDIA PROCESSOR: 📊   - Format: {format_name}")
                
                return {
                    "file_name": file_name,
                    "insights": insights,
                    "labels": labels,
                    "objects": ["image_content"],
                    "text_annotations": [],
                    "transcript": ""
                }
                
        except Exception as e:
            print(f"MEDIA PROCESSOR: ❌ Image processing error: {e}")
            return {
                "file_name": file_name,
                "insights": {"error": f"Could not process image: {e}"},
                "labels": [],
                "objects": [],
                "text_annotations": [],
                "transcript": ""
            }

    def is_supported_video(self, file_path: str) -> bool:
        """Check if file is a supported video format."""
        _, ext = os.path.splitext(file_path.lower())
        return ext in self.supported_video_formats

    def is_supported_image(self, file_path: str) -> bool:
        """Check if file is a supported image format."""
        _, ext = os.path.splitext(file_path.lower())
        return ext in self.supported_image_formats