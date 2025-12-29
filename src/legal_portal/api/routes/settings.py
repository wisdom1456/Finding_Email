"""Settings API routes."""

from fastapi import APIRouter
from pydantic import BaseModel

from legal_portal.config.default import settings

router = APIRouter()


class UploadLimitsResponse(BaseModel):
    """Upload limits configuration."""

    max_file_size_mb: int
    compression_threshold_mb: float


class SettingsResponse(BaseModel):
    """System settings response."""

    upload_limits: UploadLimitsResponse


@router.get("/limits", response_model=UploadLimitsResponse)
async def get_upload_limits():
    """Get current upload size limits.

    Returns
    -------
        Current max file size and compression threshold in MB

    """
    return UploadLimitsResponse(
        max_file_size_mb=settings.max_file_size_mb, compression_threshold_mb=settings.compression_threshold_mb
    )


@router.get("/", response_model=SettingsResponse)
async def get_settings():
    """Get all system settings.

    Returns
    -------
        System settings including upload limits

    """
    return SettingsResponse(
        upload_limits=UploadLimitsResponse(
            max_file_size_mb=settings.max_file_size_mb,
            compression_threshold_mb=settings.compression_threshold_mb,
        )
    )
