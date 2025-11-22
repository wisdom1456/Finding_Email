"""Configuration Management Module.

This module provides a type-safe, centralized configuration system using Pydantic.
All environment variables are defined here with proper validation and documentation.
"""

from __future__ import annotations

from typing import Dict, Optional, Union

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    This class provides type-safe access to all configuration values
    with automatic validation and helpful error messages.
    """

    # ==================================================
    # REQUIRED API KEYS
    # ==================================================

    openai_api_key: str = Field(
        ...,
        alias="OPENAI_API_KEY",
        description="OpenAI API key for AI analysis and email generation",
    )

    # ==================================================
    # GOOGLE CLOUD CONFIGURATION (Optional for Video Processing)
    # ==================================================

    gcp_project_id: Optional[str] = Field(
        None,
        alias="GCP_PROJECT_ID",
        description="Google Cloud Project ID for video analysis features",
    )

    gcp_bucket_name: Optional[str] = Field(
        None,
        alias="GCP_BUCKET_NAME",
        description="Google Cloud Storage bucket name for temporary video storage",
    )

    google_application_credentials: Optional[str] = Field(
        None,
        alias="GOOGLE_APPLICATION_CREDENTIALS",
        description="Path to Google Cloud service account JSON file",
    )

    # ==================================================
    # OPENAI CONFIGURATION
    # ==================================================

    openai_model: str = Field(
        "gpt-4o",
        alias="OPENAI_MODEL",
        description="OpenAI model to use for content generation",
    )

    openai_timeout: float = Field(
        30.0,
        alias="OPENAI_TIMEOUT",
        description="Timeout in seconds for OpenAI API requests",
    )

    openai_max_retries: int = Field(
        2,
        alias="OPENAI_MAX_RETRIES",
        description="Maximum number of retries for OpenAI API requests",
    )

    openai_temperature: float = Field(
        0.3,
        alias="OPENAI_TEMPERATURE",
        description="Temperature for OpenAI content generation (0.0-1.0)",
    )

    openai_max_tokens: int = Field(
        12000,
        alias="OPENAI_MAX_TOKENS",
        description="Maximum tokens for OpenAI responses",
    )

    # ==================================================
    # OUTPUT AND CACHE CONFIGURATION
    # ==================================================

    use_cache_for_outputs: bool = Field(
        True,
        alias="USE_CACHE_FOR_OUTPUTS",
        description="Store generated documents in cache instead of files (auto-cleanup after 24 hours)",
    )

    output_retention_hours: int = Field(
        24,
        alias="OUTPUT_RETENTION_HOURS",
        description="Number of hours to retain output files before cleanup",
    )

    debug_mode: bool = Field(
        False,
        alias="DEBUG_MODE",
        description="Enable debug mode (keeps diagnostic files, disables auto-cleanup)",
    )

    validation_output_dir: str = Field(
        "validation_output",
        alias="VALIDATION_OUTPUT_DIR",
        description="Directory for diagnostic output files",
    )

    # ==================================================
    # FLORIDA LEGAL CORPUS FEATURE FLAGS
    # ==================================================

    validate_citations: bool = Field(
        True,
        alias="VALIDATE_CITATIONS",
        description="Enable statute citation validation against Florida Legal Corpus",
    )

    suggest_statutes: bool = Field(
        True,
        alias="SUGGEST_STATUTES",
        description="Enable AI-powered Florida statute recommendations based on case facts",
    )

    corpus_coverage_warnings: bool = Field(
        True,
        alias="CORPUS_COVERAGE_WARNINGS",
        description="Show warnings when case type is outside corpus coverage areas",
    )

    use_multi_stage_analysis: bool = Field(
        True,
        alias="USE_MULTI_STAGE_ANALYSIS",
        description="Enable multi-stage analysis pipeline for enhanced letter quality (Fact Matrix → Issue Mapping → Deep Analysis → Structure Determination)",
    )

    # ==================================================
    # FILE COMPRESSION CONFIGURATION
    # ==================================================

    max_file_size_mb: int = Field(
        100,
        alias="MAX_FILE_SIZE_MB",
        description="Maximum file size for uploads and imports in MB",
    )

    compression_threshold_mb: float = Field(
        10.0,
        alias="COMPRESSION_THRESHOLD_MB",
        description="File size threshold in MB above which compression is applied",
    )

    pdf_compression_quality: str = Field(
        "ebook",
        alias="PDF_COMPRESSION_QUALITY",
        description="Ghostscript quality preset for PDF compression (screen, ebook, printer, prepress)",
    )

    image_compression_quality: int = Field(
        85,
        alias="IMAGE_COMPRESSION_QUALITY",
        description="JPEG quality for image compression (0-100)",
    )

    # ==================================================
    # OPTIONAL CONFIGURATION
    # ==================================================

    port: int = Field(
        8501,
        alias="PORT",
        description="Port number for the application (set by Railway in production)",
    )

    railway_static_url: Optional[str] = Field(
        None,
        alias="RAILWAY_STATIC_URL",
        description="Railway static URL (automatically set by Railway)",
    )

    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_key(cls, v):
        """Validate that OpenAI API key has the correct format."""
        if not v.startswith(("sk-", "sk-proj-")):
            msg = "OpenAI API key must start with 'sk-' or 'sk-proj-'"
            raise ValueError(msg)
        return v

    @field_validator("openai_temperature")
    @classmethod
    def validate_temperature(cls, v):
        """Validate that temperature is in valid range."""
        if not 0.0 <= v <= 2.0:
            msg = "OpenAI temperature must be between 0.0 and 2.0"
            raise ValueError(msg)
        return v

    @field_validator("openai_timeout")
    @classmethod
    def validate_timeout(cls, v):
        """Validate that timeout is positive."""
        if v <= 0:
            msg = "OpenAI timeout must be positive"
            raise ValueError(msg)
        return v

    @field_validator("compression_threshold_mb")
    @classmethod
    def validate_compression_threshold(cls, v):
        """Validate that compression threshold is positive and reasonable."""
        if v <= 0:
            msg = "Compression threshold must be positive"
            raise ValueError(msg)
        if v > 100:
            msg = "Compression threshold should not exceed 100MB"
            raise ValueError(msg)
        return v

    @field_validator("pdf_compression_quality")
    @classmethod
    def validate_pdf_quality(cls, v):
        """Validate PDF compression quality preset."""
        valid_presets = ["screen", "ebook", "printer", "prepress"]
        if v not in valid_presets:
            msg = f"PDF compression quality must be one of: {', '.join(valid_presets)}"
            raise ValueError(msg)
        return v

    @field_validator("image_compression_quality")
    @classmethod
    def validate_image_quality(cls, v):
        """Validate image compression quality."""
        if not 1 <= v <= 100:
            msg = "Image compression quality must be between 1 and 100"
            raise ValueError(msg)
        return v

    @field_validator("google_application_credentials")
    @classmethod
    def validate_credentials_file(cls, v, values):
        """Validate that the Google credentials file exists only when absolutely necessary.

        This validator is now very lenient to allow application startup without credentials.
        """
        # Skip validation if no value provided
        if not v:
            return v

        # Skip validation if file doesn't exist - we'll handle this at runtime when needed
        # This allows the application to start up without requiring the credentials file
        return v

    @property
    def has_google_cloud_config(self) -> bool:
        """Check if Google Cloud configuration is complete for video processing."""
        return all(
            [
                self.gcp_project_id,
                self.gcp_bucket_name,
                self.google_application_credentials,
            ]
        )

    @property
    def video_processing_enabled(self) -> bool:
        """Check if video processing features can be enabled."""
        return self.has_google_cloud_config

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",  # Ignore extra environment variables not defined in the model
    }


# Global settings instance
# This is the single source of truth for all configuration
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance.

    This function provides a way to access settings that can be easily
    mocked in tests or replaced with different configurations.

    Returns
    -------
        Settings: The configured settings instance

    """
    return settings


# Convenience functions for common configuration checks
def is_production() -> bool:
    """Check if running in production environment (Railway)."""
    return settings.railway_static_url is not None


def get_openai_api_key() -> str:
    """Get the OpenAI API key with validation."""
    if not settings.openai_api_key:
        msg = (
            "OPENAI_API_KEY is required but not set. " "Please check your .env file or environment variables."
        )
        raise ValueError(msg)
    return settings.openai_api_key


def get_google_cloud_config() -> tuple[str, str, str]:
    """Get Google Cloud configuration for video processing.

    Returns
    -------
        tuple: (project_id, bucket_name, credentials_path)

    Raises
    ------
        ValueError: If Google Cloud configuration is incomplete

    """
    if not settings.has_google_cloud_config:
        missing = []
        if not settings.gcp_project_id:
            missing.append("GCP_PROJECT_ID")
        if not settings.gcp_bucket_name:
            missing.append("GCP_BUCKET_NAME")
        if not settings.google_application_credentials:
            missing.append("GOOGLE_APPLICATION_CREDENTIALS")

        msg = (
            f"Incomplete Google Cloud configuration. Missing: {', '.join(missing)}. "
            "Video processing features will be disabled."
        )
        raise ValueError(msg)

    return (
        settings.gcp_project_id,
        settings.gcp_bucket_name,
        settings.google_application_credentials,
    )


def get_openai_config() -> Dict[str, Union[float, int, str]]:
    """Get OpenAI configuration for content generation.

    Returns
    -------
        dict: OpenAI configuration parameters

    """
    return {
        "model": settings.openai_model,
        "timeout": settings.openai_timeout,
        "max_retries": settings.openai_max_retries,
        "temperature": settings.openai_temperature,
        "max_tokens": settings.openai_max_tokens,
    }
