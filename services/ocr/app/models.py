from typing import Literal, Optional

from pydantic import BaseModel


class OCRPageResult(BaseModel):
    page: int
    text: str
    error: Optional[str] = None


class OCRResponse(BaseModel):
    provider: Literal["google_vision"] = "google_vision"
    file_type: Literal["pdf", "image"]
    page_count: int
    pages: list[OCRPageResult]
    full_text: str
    latency_ms: float
    warnings: list[str] = []
    errors: list[str] = []
    trace_id: str


class VisionAPIError(Exception):
    """Google Vision API failure. No recovery."""
    pass
