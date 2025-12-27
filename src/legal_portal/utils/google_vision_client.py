"""Google Cloud Vision API client for OCR text extraction."""

from __future__ import annotations

import base64
import json
import os
from typing import Optional

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# Try to import Google Cloud Vision
GOOGLE_VISION_AVAILABLE = False
try:
    from google.cloud import vision
    from google.oauth2 import service_account

    GOOGLE_VISION_AVAILABLE = True
    logger.debug("Google Cloud Vision SDK available")
except ImportError:
    logger.warning("Google Cloud Vision SDK not available - OCR will fall back to GPT-4o Vision")


class GoogleVisionClient:
    """Handle Google Cloud Vision API interactions for OCR."""

    _instance: Optional["GoogleVisionClient"] = None

    def __init__(self):
        """Initialize Google Cloud Vision client.

        Supports multiple authentication methods:
        1. GOOGLE_APPLICATION_CREDENTIALS_JSON env var (base64-encoded JSON key)
        2. GOOGLE_APPLICATION_CREDENTIALS env var (path to JSON key file)
        3. Default application credentials (for GCP-hosted environments)
        """
        self.client = None
        self._initialized = False

        if not GOOGLE_VISION_AVAILABLE:
            logger.warning("Google Cloud Vision SDK not installed")
            return

        try:
            # Method 1: Base64-encoded credentials JSON (for Vercel/serverless)
            creds_json_b64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
            if creds_json_b64:
                try:
                    creds_json = base64.b64decode(creds_json_b64).decode("utf-8")
                    creds_dict = json.loads(creds_json)
                    credentials = service_account.Credentials.from_service_account_info(creds_dict)
                    self.client = vision.ImageAnnotatorClient(credentials=credentials)
                    self._initialized = True
                    logger.info("Google Vision client initialized with base64 credentials")
                    return
                except Exception as e:
                    logger.warning(f"Failed to parse GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")

            # Method 2: Credentials file path
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path and os.path.exists(creds_path):
                self.client = vision.ImageAnnotatorClient()
                self._initialized = True
                logger.info("Google Vision client initialized with credentials file")
                return

            # Method 3: Default credentials (ADC)
            try:
                self.client = vision.ImageAnnotatorClient()
                self._initialized = True
                logger.info("Google Vision client initialized with default credentials")
            except Exception as e:
                logger.warning(f"Failed to initialize with default credentials: {e}")

        except Exception as e:
            logger.error(f"Failed to initialize Google Vision client: {e}")

    @classmethod
    def get_instance(cls) -> "GoogleVisionClient":
        """Get singleton instance of the client."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_available(self) -> bool:
        """Check if the client is properly initialized and ready."""
        return GOOGLE_VISION_AVAILABLE and self._initialized and self.client is not None

    def extract_text_from_image(self, image_bytes: bytes) -> str:
        """Extract text from image bytes using Google Cloud Vision OCR.

        Args:
        ----
            image_bytes: Raw image bytes (PNG, JPEG, etc.)

        Returns:
        -------
            Extracted text string, or empty string on failure

        """
        if not self.is_available:
            logger.warning("Google Vision client not available")
            return ""

        try:
            image = vision.Image(content=image_bytes)

            # Use document_text_detection for better results on documents
            # (handles dense text, columns, tables better than text_detection)
            response = self.client.document_text_detection(image=image)

            if response.error.message:
                logger.error(f"Google Vision API error: {response.error.message}")
                return ""

            # Get full text annotation (preserves layout better)
            if response.full_text_annotation:
                return response.full_text_annotation.text

            # Fallback to text_annotations if full_text not available
            if response.text_annotations:
                return response.text_annotations[0].description

            return ""

        except Exception as e:
            logger.error(f"Error extracting text with Google Vision: {e}")
            return ""

    def extract_text_from_image_async(self, image_bytes: bytes) -> str:
        """Call extract_text_from_image synchronously for compatibility.

        Note: For true async, use asyncio.to_thread or run_in_threadpool.
        """
        return self.extract_text_from_image(image_bytes)

    def batch_extract_text(self, image_bytes_list: list[bytes]) -> list[str]:
        """Extract text from multiple images.

        Args:
        ----
            image_bytes_list: List of image bytes

        Returns:
        -------
            List of extracted text strings (same order as input)

        """
        results = []
        for image_bytes in image_bytes_list:
            text = self.extract_text_from_image(image_bytes)
            results.append(text)
        return results

    def estimate_cost(self, num_pages: int) -> float:
        """Estimate cost for OCR processing.

        Google Cloud Vision pricing (as of 2024):
        - First 1000 units/month: Free
        - Units 1001-5M: $1.50 per 1000 units
        - Units 5M+: $0.60 per 1000 units

        Args:
        ----
            num_pages: Number of pages/images to process

        Returns:
        -------
            Estimated cost in USD

        """
        # Assuming past free tier
        cost_per_1000 = 1.50
        return (num_pages / 1000) * cost_per_1000
