"""Google Cloud Vision API client for OCR text extraction."""

from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Optional

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# Try to import Google Cloud Vision
GOOGLE_VISION_AVAILABLE = False
try:
    from google.cloud import vision
    from google.oauth2 import service_account

    GOOGLE_VISION_AVAILABLE = True
    logger.info("Google Cloud Vision SDK available")
except ImportError:
    logger.warning("Google Cloud Vision SDK not available - OCR will fall back to GPT-4o Vision")


class GoogleVisionClient:
    """Handle Google Cloud Vision API interactions for OCR."""

    def __init__(self):
        """Initialize Google Cloud Vision client.

        Supports multiple authentication methods:
        1. GOOGLE_APPLICATION_CREDENTIALS_JSON env var (base64-encoded JSON key)
        2. GOOGLE_APPLICATION_CREDENTIALS env var (path to JSON key file)
        3. Default application credentials (for GCP-hosted environments)
        """
        self.client = None
        self._initialized = False
        self._credentials_validated = False  # Cache validation result

        if not GOOGLE_VISION_AVAILABLE:
            logger.warning("Google Cloud Vision SDK not installed")
            return

        try:
            # Method 1: Base64-encoded credentials JSON (for Vercel/serverless)
            creds_json_b64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
            if creds_json_b64:
                logger.info("Found GOOGLE_APPLICATION_CREDENTIALS_JSON env var, attempting to parse...")
                try:
                    # Decode base64 to get JSON string
                    creds_json = base64.b64decode(creds_json_b64).decode("utf-8")
                    logger.debug(f"Base64 decoded, JSON length: {len(creds_json)} chars")

                    # Parse JSON to dict
                    creds_dict = json.loads(creds_json)
                    logger.debug(f"JSON parsed, project_id: {creds_dict.get('project_id', 'N/A')}")

                    # Create credentials object
                    credentials = service_account.Credentials.from_service_account_info(creds_dict)
                    logger.debug("Service account credentials created")

                    # Create Vision client
                    self.client = vision.ImageAnnotatorClient(credentials=credentials)
                    self._initialized = True
                    logger.info(
                        f"Google Vision client initialized with base64 credentials "
                        f"(project: {creds_dict.get('project_id', 'unknown')})"
                    )
                    return
                except Exception as e:
                    logger.error(f"Failed to parse GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")
                    # Log more details for debugging
                    if creds_json_b64:
                        logger.debug(f"Env var length: {len(creds_json_b64)} chars")
                        logger.debug(f"First 50 chars: {creds_json_b64[:50]}...")

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
        return get_vision_client()

    @property
    def is_available(self) -> bool:
        """Check if the client is properly initialized and ready."""
        return GOOGLE_VISION_AVAILABLE and self._initialized and self.client is not None

    def validate_credentials(self, force: bool = False) -> tuple[bool, str]:
        """Test that credentials work by making a minimal API call.

        Args:
        ----
            force: If True, re-validate even if already validated

        Returns:
        -------
            Tuple of (success: bool, message: str)

        """
        if not self.is_available:
            return False, "Client not initialized"

        # Return cached result if already validated (avoid repeated API calls)
        if self._credentials_validated and not force:
            logger.debug("Using cached credential validation result")
            return True, "Credentials valid (cached)"

        try:
            # Create a minimal 1x1 white PNG image for testing
            # This is a valid PNG that won't return text but will validate auth
            minimal_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
                b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
                b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )

            logger.info("Testing Google Vision API credentials...")
            image = vision.Image(content=minimal_png)

            # Add timeout to the validation call

            # Note: since this is a synchronous call in a class method,
            # we should ideally use a thread pool or a signal-based timeout,
            # but for simplicity in this utility we'll just log and rely on the
            # higher-level timeouts in the processor.
            # However, the Google SDK usually has its own internal timeouts.
            response = self.client.text_detection(image=image)

            # Check for API-level errors
            if response.error.message:
                # "Request contains an invalid argument" on a dummy image actually
                # proves credentials worked - the API processed our request and
                # just didn't like the tiny test image. This is a SUCCESS.
                if "invalid argument" in response.error.message.lower():
                    logger.info("✅ Google Vision credentials validated (API connection successful)")
                    self._credentials_validated = True
                    return True, "Credentials valid"

                # Other errors are real failures
                error_msg = f"API error: {response.error.message}"
                logger.error(f"Google Vision credential validation failed: {error_msg}")
                return False, error_msg

            logger.info("✅ Google Vision credentials validated successfully")
            self._credentials_validated = True
            return True, "Credentials valid"

        except Exception as e:
            error_msg = str(e)
            # Check if the exception message indicates the API was reached
            # but rejected the image (still means credentials are valid)
            if "invalid argument" in error_msg.lower():
                logger.info("✅ Google Vision credentials validated (API connection successful)")
                self._credentials_validated = True
                return True, "Credentials valid"

            logger.error(f"Google Vision credential validation failed: {error_msg}")
            return False, error_msg

    # Google Vision API has a 40MB payload limit
    PAYLOAD_SIZE_LIMIT = 40 * 1024 * 1024  # 40MB

    def extract_text_from_image(self, image_bytes: bytes) -> str:
        """Extract text from image bytes using Google Cloud Vision OCR.

        Args:
        ----
            image_bytes: Raw image bytes (PNG, JPEG, etc.)

        Returns:
        -------
            Extracted text string, or empty string on failure

        Raises:
        ------
            ValueError: If image exceeds Google Vision's 40MB payload limit

        """
        if not self.is_available:
            logger.warning("Google Vision client not available")
            return ""

        # Check payload size before sending to API
        if len(image_bytes) > self.PAYLOAD_SIZE_LIMIT:
            size_mb = len(image_bytes) / (1024 * 1024)
            error_msg = f"Image size ({size_mb:.1f}MB) exceeds Google Vision limit (40MB)"
            logger.error(error_msg)
            raise ValueError(error_msg)

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

        except ValueError:
            # Re-raise size limit errors for caller to handle
            raise
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


@lru_cache(maxsize=1)
def get_vision_client() -> GoogleVisionClient:
    """Get the singleton GoogleVisionClient instance."""
    return GoogleVisionClient()
