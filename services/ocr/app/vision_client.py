import json
import logging

from google.cloud import vision
from google.oauth2 import service_account

from .config import Settings
from .models import VisionAPIError

logger = logging.getLogger(__name__)


class StrictVisionClient:
    """Google Vision client. Hard-fails on init and on every call.
    No fallbacks. No empty-string returns on API errors."""

    def __init__(self, settings: Settings):
        try:
            creds_dict = json.loads(settings.google_credentials_json)
            self.project_id = creds_dict.get("project_id", "unknown")
            credentials = (
                service_account.Credentials.from_service_account_info(
                    creds_dict
                )
            )
            self._client = vision.ImageAnnotatorClient(
                credentials=credentials
            )
            self._initialized = True
            logger.info(
                "StrictVisionClient initialized "
                f"(project: {self.project_id})"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize Google Vision client: {e}"
            ) from e

    @property
    def is_ready(self) -> bool:
        return self._initialized and self._client is not None

    def extract_text(
        self, image_bytes: bytes, max_image_bytes: int
    ) -> str:
        """Extract text via document_text_detection.
        Raises VisionAPIError on failure.
        Returns "" for blank pages (not an error)."""
        if len(image_bytes) > max_image_bytes:
            raise VisionAPIError(
                f"Image size ({len(image_bytes)}) exceeds "
                f"limit ({max_image_bytes})"
            )

        image = vision.Image(content=image_bytes)
        response = self._client.document_text_detection(image=image)

        if response.error.message:
            raise VisionAPIError(
                f"Vision API error: {response.error.message}"
            )

        if response.full_text_annotation:
            return response.full_text_annotation.text
        if response.text_annotations:
            return response.text_annotations[0].description
        return ""  # Blank page - not an error
