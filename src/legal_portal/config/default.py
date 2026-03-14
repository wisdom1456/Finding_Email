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
        "gpt-5.4",
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
    # DOCUMENT GROUPING FEATURE FLAGS (phased rollout)
    # ==================================================

    enable_group_detection: bool = Field(
        False,
        alias="ENABLE_GROUP_DETECTION",
        description="Phase A: detect document groups and log metrics only, no behavior change",
    )

    enable_group_summarization: bool = Field(
        False,
        alias="ENABLE_GROUP_SUMMARIZATION",
        description="Phase B: generate group summaries alongside individual ones",
    )

    enable_group_context: bool = Field(
        False,
        alias="ENABLE_GROUP_CONTEXT",
        description="Phase C: use group summaries in context building",
    )

    enable_group_persistence: bool = Field(
        False,
        alias="ENABLE_GROUP_PERSISTENCE",
        description="Phase D: persist document groups to database",
    )

    # ==================================================
    # LETTER GENERATION FEATURE FLAGS
    # ==================================================

    letter_stream_schema_v2: bool = Field(
        True,
        alias="LETTER_STREAM_SCHEMA_V2",
        description="Enable v2 SSE schema for letter streaming endpoints.",
    )

    letter_quality_lint_enabled: bool = Field(
        True,
        alias="LETTER_QUALITY_LINT_ENABLED",
        description="Enable deterministic quality lint checks for generated letters.",
    )

    letter_conditional_repair_enabled: bool = Field(
        True,
        alias="LETTER_CONDITIONAL_REPAIR_ENABLED",
        description="Enable conditional repair pass when lint validation fails.",
    )

    letter_strategy_enabled: bool = Field(
        True,
        alias="LETTER_STRATEGY_ENABLED",
        description="Enable structured pre-draft strategy layer for findings and demand letters.",
    )

    letter_quality_critic_enabled: bool = Field(
        True,
        alias="LETTER_QUALITY_CRITIC_ENABLED",
        description="Enable section-level quality critic pass before constrained repair.",
    )

    letter_polish_enabled: bool = Field(
        True,
        alias="LETTER_POLISH_ENABLED",
        description="Enable final polish pass for generated letters.",
    )

    letter_term_micro_explainers_enabled: bool = Field(
        True,
        alias="LETTER_TERM_MICRO_EXPLAINERS_ENABLED",
        description="Require first-use legal term micro-explainers in letter quality checks.",
    )

    recommendation_stream_enabled: bool = Field(
        True,  # Changed from False to enable streaming and prevent network timeouts
        alias="RECOMMENDATION_STREAM_ENABLED",
        description="Enable progressive streaming endpoint for recommendation letters.",
    )

    letter_internal_budget_seconds: int = Field(
        240,
        alias="LETTER_INTERNAL_BUDGET_SECONDS",
        description="Internal end-to-end budget for streaming letter generation.",
    )

    letter_context_budget_seconds: int = Field(
        20,
        alias="LETTER_CONTEXT_BUDGET_SECONDS",
        description="Context-build phase budget for streaming letter generation.",
    )

    letter_draft_budget_seconds: int = Field(
        160,
        alias="LETTER_DRAFT_BUDGET_SECONDS",
        description="Draft generation phase budget for streaming letter generation.",
    )

    letter_lint_budget_seconds: int = Field(
        20,
        alias="LETTER_LINT_BUDGET_SECONDS",
        description="Lint-validation phase budget for streaming letter generation.",
    )

    letter_repair_budget_seconds: int = Field(
        30,
        alias="LETTER_REPAIR_BUDGET_SECONDS",
        description="Repair phase budget for streaming letter generation.",
    )

    letter_finalize_budget_seconds: int = Field(
        10,
        alias="LETTER_FINALIZE_BUDGET_SECONDS",
        description="Finalization/persistence phase budget for streaming letter generation.",
    )

    letter_stream_heartbeat_seconds: int = Field(
        5,
        alias="LETTER_STREAM_HEARTBEAT_SECONDS",
        description="Interval in seconds for SSE heartbeats during silent stream intervals.",
    )

    letter_strategy_budget_seconds: int = Field(
        30,
        alias="LETTER_STRATEGY_BUDGET_SECONDS",
        description="Maximum time budget for strategy generation step.",
    )

    letter_critic_budget_seconds: int = Field(
        20,
        alias="LETTER_CRITIC_BUDGET_SECONDS",
        description="Maximum time budget for quality critic step.",
    )

    letter_polish_timeout_seconds: int = Field(
        55,
        alias="LETTER_POLISH_TIMEOUT_SECONDS",
        description="Hard timeout for the polish pass. Inference always attempted; falls back to draft on timeout.",
    )

    # ==================================================
    # DOCUMENT PROCESSING CONFIGURATION
    # ==================================================

    max_tokens_per_batch: int = Field(
        50000,
        alias="MAX_TOKENS_PER_BATCH",
        description="Maximum tokens per batch when processing documents with AI",
    )

    duplicate_similarity_threshold: float = Field(
        0.85,
        alias="DUPLICATE_SIMILARITY_THRESHOLD",
        description="Similarity threshold (0.0-1.0) for detecting near-duplicate documents",
    )

    min_file_size_for_content: int = Field(
        500000,
        alias="MIN_FILE_SIZE_FOR_CONTENT",
        description="Minimum file size in bytes to consider a file as having content (500KB default)",
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

    max_image_dimension: int = Field(
        3000,
        alias="MAX_IMAGE_DIMENSION",
        description="Maximum dimension (width or height) for images in pixels. Larger images are resized down.",
    )

    png_to_jpeg_threshold_mb: float = Field(
        5.0,
        alias="PNG_TO_JPEG_THRESHOLD_MB",
        description="PNG files larger than this (MB) are converted to JPEG for faster processing and smaller size",
    )

    image_hard_cap_mb: float = Field(
        5.0,
        alias="IMAGE_HARD_CAP_MB",
        description="Maximum output size for compressed images in MB. Images exceeding this are re-compressed more aggressively.",
    )

    # ==================================================
    # OCR SERVICE CONFIGURATION
    # ==================================================

    ocr_remote_enabled: bool = Field(
        False,
        alias="OCR_REMOTE_ENABLED",
        description=(
            "Route OCR to Cloud Run service. "
            "Set to true once Cloud Run is deployed and validated."
        ),
    )

    ocr_remote_required: bool = Field(
        True,
        alias="OCR_REMOTE_REQUIRED",
        description=(
            "If remote OCR fails, raise error (no local fallback). "
            "Only set to false as emergency kill switch."
        ),
    )

    ocr_service_url: str = Field(
        "",
        alias="OCR_SERVICE_URL",
        description="Cloud Run OCR service URL.",
    )

    ocr_service_token: str = Field(
        "",
        alias="OCR_SERVICE_TOKEN",
        description="Shared secret for OCR service auth.",
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

    @field_validator("max_image_dimension")
    @classmethod
    def validate_max_image_dimension(cls, v):
        """Validate max image dimension is reasonable."""
        if not 500 <= v <= 10000:
            msg = "Max image dimension must be between 500 and 10000 pixels"
            raise ValueError(msg)
        return v

    @field_validator("png_to_jpeg_threshold_mb")
    @classmethod
    def validate_png_to_jpeg_threshold(cls, v):
        """Validate PNG to JPEG threshold is reasonable."""
        if not 0.5 <= v <= 50:
            msg = "PNG to JPEG threshold must be between 0.5 and 50 MB"
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
    """Check if running in production environment (Vercel or Railway)."""
    import os
    return os.getenv("VERCEL_ENV") == "production" or settings.railway_static_url is not None


def get_openai_api_key() -> str:
    """Get the OpenAI API key with validation."""
    if not settings.openai_api_key:
        msg = "OPENAI_API_KEY is required but not set. Please check your .env file or environment variables."
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
