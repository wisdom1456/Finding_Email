"""HTTPX client for calling the Cloud Run OCR service."""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class OCRServiceError(Exception):
    """OCR service unreachable or returned non-200."""
    pass


class OCRProviderError(Exception):
    """Response provider doesn't match expected."""
    pass


class OCRServiceClient:
    """Async client for the Cloud Run OCR microservice."""

    _instance: Optional["OCRServiceClient"] = None

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = httpx.Timeout(
            connect=10.0,
            read=120.0,
            write=30.0,
            pool=180.0,
        )
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout
            )
        return self._client

    async def extract_text(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> dict:
        """Send file to OCR service.
        Retries up to 3 times on transient failures.
        Returns parsed JSON response dict."""
        client = await self._get_client()
        last_error: Optional[str] = None

        for attempt in range(3):
            try:
                response = await client.post(
                    f"{self.base_url}/ocr",
                    files={
                        "file": (
                            filename, file_bytes, content_type,
                        ),
                    },
                    headers={
                        "Authorization": f"Bearer {self.token}",
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    provider = data.get("provider")
                    if provider != "google_vision":
                        raise OCRProviderError(
                            f"Expected google_vision, "
                            f"got {provider}"
                        )
                    return data

                if response.status_code in (502, 503, 504):
                    last_error = (
                        f"HTTP {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(
                            1 * (attempt + 1)
                        )
                        continue

                raise OCRServiceError(
                    f"OCR service returned "
                    f"{response.status_code}: "
                    f"{response.text[:500]}"
                )

            except (
                httpx.TimeoutException,
                httpx.ConnectError,
            ) as e:
                last_error = (
                    f"{type(e).__name__}: {e}"
                )
                if attempt < 2:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue

        raise OCRServiceError(
            f"OCR service unavailable after 3 attempts: "
            f"{last_error}"
        )

    async def health_check(self) -> dict:
        """Check OCR service health. No auth required."""
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/health"
        )
        return response.json()

    @classmethod
    def get_instance(cls) -> "OCRServiceClient":
        """Get or create singleton instance."""
        if cls._instance is None:
            from legal_portal.config.default import (
                get_settings,
            )
            settings = get_settings()
            if not settings.ocr_service_url:
                raise OCRServiceError(
                    "OCR_SERVICE_URL must be set "
                    "when OCR_REMOTE_ENABLED=true"
                )
            if not settings.ocr_service_token:
                raise OCRServiceError(
                    "OCR_SERVICE_TOKEN must be set "
                    "when OCR_REMOTE_ENABLED=true"
                )
            cls._instance = cls(
                settings.ocr_service_url,
                settings.ocr_service_token,
            )
        return cls._instance


def get_ocr_client() -> OCRServiceClient:
    """Convenience function for getting the singleton."""
    return OCRServiceClient.get_instance()
