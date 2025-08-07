"""
Configuration Management Module

This module provides a type-safe, centralized configuration system using Pydantic.
All environment variables are defined here with proper validation and documentation.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

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

    gcp_project_id: str | None = Field(
        None,
        alias="GCP_PROJECT_ID",
        description="Google Cloud Project ID for video analysis features",
    )

    gcp_bucket_name: str | None = Field(
        None,
        alias="GCP_BUCKET_NAME",
        description="Google Cloud Storage bucket name for temporary video storage",
    )

    google_application_credentials: str | None = Field(
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
        4000,
        alias="OPENAI_MAX_TOKENS",
        description="Maximum tokens for OpenAI responses",
    )

    # ==================================================
    # OPTIONAL CONFIGURATION
    # ==================================================

    port: int = Field(
        8501,
        alias="PORT",
        description="Port number for the application (set by Railway in production)",
    )

    railway_static_url: str | None = Field(
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

    @field_validator("google_application_credentials")
    @classmethod
    def validate_credentials_file(cls, v):
        """Validate that the Google credentials file exists if provided."""
        if v and not os.path.exists(v):
            msg = f"Google credentials file not found: {v}"
            raise ValueError(msg)
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
    """
    Get the global settings instance.

    This function provides a way to access settings that can be easily
    mocked in tests or replaced with different configurations.

    Returns:
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
            "OPENAI_API_KEY is required but not set. "
            "Please check your .env file or environment variables."
        )
        raise ValueError(msg)
    return settings.openai_api_key


def get_google_cloud_config() -> tuple[str, str, str]:
    """
    Get Google Cloud configuration for video processing.

    Returns:
        tuple: (project_id, bucket_name, credentials_path)

    Raises:
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


def get_openai_config() -> dict[str, float | int | str]:
    """
    Get OpenAI configuration for content generation.

    Returns:
        dict: OpenAI configuration parameters
    """
    return {
        "model": settings.openai_model,
        "timeout": settings.openai_timeout,
        "max_retries": settings.openai_max_retries,
        "temperature": settings.openai_temperature,
        "max_tokens": settings.openai_max_tokens,
    }
