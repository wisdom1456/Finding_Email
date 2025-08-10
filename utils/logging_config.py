"""
Centralized Logging Configuration for Legal Document Analysis Portal

This module implements structured logging using loguru with:
- Service-aware context injection
- Environment-based configuration
- Log rotation and retention
- JSON serialization for production
- Security-aware PII sanitization for legal data

Based on Sequential Thinking MCP analysis, this combines:
- Hypothesis 1: Centralized Logger Factory Pattern
- Hypothesis 2: Service-Aware Context Injection
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger


class LoggingConfig:
    """Centralized logging configuration for the Legal Document Analysis Portal."""

    # Service names from the service-oriented architecture
    KNOWN_SERVICES = {
        # Core service-oriented architecture services
        "configuration_manager",
        "text_processing_service",
        "json_architecture_service",
        "template_rendering_service",
        "openai_integration_service",
        "content_generation_service",
        "fallback_generation_service",
        # Backend logic services
        "main_processor",
        "video_processor",
        "ai_analyzer",
        "email_generator",
        "email_generator_v2",
        "cost_session_manager",
        "audio_processor",
        "async_processor",
        # AI services
        "openai_client",
        "token_manager",
        "timeline_analyzer",
        # File processors
        "docx_processor",
        "pdf_processor",
        "txt_processor",
        "eml_processor",
        "image_processor",
        # Backend utilities
        "quality_validator",
        "validators",
        # Analysis tools
        "import_analyzer",
        "redundant_logic_analyzer",
        "parallelization_analyzer",
        "dead_code_analyzer",
        # Testing utilities
        "quick_validation_test",
        "test_framework",
        "semantic_analyzer",
        # Application services
        "streamlit_app",
        "cost_tracker",
        "config_manager",
        "media_processor",
    }

    # PII patterns for legal data sanitization
    PII_PATTERNS = [
        (r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", "[CLIENT_NAME]"),  # Person names
        (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),  # SSN
        (r"\b\d{4}-\d{4}-\d{4}-\d{4}\b", "[CARD_NUM]"),  # Credit card
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),  # Email
        (r"\b\d{3}-\d{3}-\d{4}\b", "[PHONE]"),  # Phone
    ]

    def __init__(self):
        """Initialize logging configuration."""
        self.environment = os.getenv("ENVIRONMENT", "development").lower()
        self.log_level = os.getenv("LOG_LEVEL", self._get_default_level()).upper()
        self.enable_json = os.getenv("LOG_JSON", "false").lower() == "true"
        self.enable_pii_sanitization = (
            os.getenv("LOG_SANITIZE_PII", "true").lower() == "true"
        )

        # Ensure logs directory exists
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)

        # Remove default logger to start fresh
        logger.remove()

        # Configure based on environment
        self._configure_logging()

    def _get_default_level(self) -> str:
        """Get default log level based on environment."""
        env_levels = {
            "development": "DEBUG",
            "testing": "INFO",
            "staging": "INFO",
            "production": "INFO",
        }
        return env_levels.get(self.environment, "INFO")

    def _sanitize_pii(self, message: str) -> str:
        """Sanitize PII from log messages for legal compliance."""
        if not self.enable_pii_sanitization:
            return message

        sanitized = message
        for pattern, replacement in self.PII_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized)
        return sanitized

    def _format_log_record(self, record: dict) -> str:
        """Custom formatter that applies PII sanitization."""
        # Sanitize the message
        if self.enable_pii_sanitization:
            record["message"] = self._sanitize_pii(record["message"])

        # Format based on environment
        if self.environment == "production":
            # Minimal format for production
            return "{time:YYYY-MM-DD HH:mm:ss.SSS Z} | {level: <8} | {name: <20} | {message}\n{exception}"
        # Detailed format for development
        return "{time:YYYY-MM-DD HH:mm:ss.SSS Z} | {level: <8} | {name: <20} | {name}:{function}:{line} | {message}\n{exception}"

    def _configure_logging(self) -> None:
        """Configure loguru based on environment and settings."""

        # Console handler - always present for development visibility
        if self.environment in ["development", "testing"]:
            logger.add(
                sys.stderr,
                level=self.log_level,
                format=self._format_log_record,
                colorize=True,
                backtrace=True,
                diagnose=True,
                filter=lambda record: record["extra"].get("service", "unknown")
                != "test_suppressed",
            )

        # File handler with rotation - structured logging
        log_file = self.logs_dir / "app.log"
        logger.add(
            str(log_file),
            level=self.log_level,
            format=self._format_log_record,
            rotation="10 MB",  # Rotate when log reaches 10 MB
            retention="30 days",  # Keep logs for 30 days
            compression="zip",  # Compress rotated logs
            backtrace=True,
            diagnose=self.environment != "production",  # Disable diagnose in production
            enqueue=True,  # Thread-safe logging
            serialize=self.enable_json,  # JSON serialization if requested
        )

        # Error-specific file handler
        error_log_file = self.logs_dir / "errors.log"
        logger.add(
            str(error_log_file),
            level="ERROR",
            format=self._format_log_record,
            rotation="5 MB",
            retention="90 days",  # Keep error logs longer
            compression="zip",
            backtrace=True,
            diagnose=True,
            enqueue=True,
            filter=lambda record: record["level"].no >= 40,  # ERROR and CRITICAL only
        )

        # Service-specific log files in development
        if self.environment == "development":
            for service in self.KNOWN_SERVICES:
                service_log_file = self.logs_dir / f"{service}.log"
                logger.add(
                    str(service_log_file),
                    level="DEBUG",
                    format=self._format_log_record,
                    rotation="2 MB",
                    retention="7 days",
                    compression="zip",
                    filter=lambda record, svc=service: record["extra"].get("service")
                    == svc,
                )

    def get_logger(self, service_name: str, **context: Any) -> Any:
        """
        Get a logger instance with service-specific context.

        Args:
            service_name: Name of the service requesting the logger
            **context: Additional context to bind to all log messages

        Returns:
            Configured logger instance with bound context
        """
        # Validate service name
        if service_name not in self.KNOWN_SERVICES:
            logger.warning(
                f"Unknown service name: {service_name}. Consider adding to KNOWN_SERVICES."
            )

        # Create context with service name and additional context
        log_context = {"service": service_name, **context}

        # Return logger with bound context
        return logger.bind(**log_context)

    def get_module_logger(self, module_name: str, **context: Any) -> Any:
        """
        Get a logger for a specific module with automatic service detection.

        Args:
            module_name: __name__ of the calling module
            **context: Additional context to bind

        Returns:
            Configured logger with inferred service context
        """
        # Infer service name from module path
        service_name = self._infer_service_name(module_name)
        return self.get_logger(service_name, module=module_name, **context)

    def _infer_service_name(self, module_name: str) -> str:
        """Infer service name from module path."""
        module_path_mapping = {
            "backend.email_generator": "email_generator_v2",
            "backend.ai_analyzer": "ai_analyzer",
            "backend_logic.email_generation.services.configuration_manager": "configuration_manager",
            "backend_logic.email_generation.services.text_processing_service": "text_processing_service",
            "backend_logic.email_generation.services.json_architecture_service": "json_architecture_service",
            "backend_logic.email_generation.services.template_rendering_service": "template_rendering_service",
            "backend_logic.email_generation.services.openai_integration_service": "openai_integration_service",
            "backend_logic.email_generation.services.content_generation_service": "content_generation_service",
            "backend_logic.email_generation.services.fallback_generation_service": "fallback_generation_service",
            "app": "streamlit_app",
            "main": "main_processor",
        }

        # Check exact matches first
        if module_name in module_path_mapping:
            return module_path_mapping[module_name]

        # Check partial matches
        for module_prefix, service in module_path_mapping.items():
            if module_name.startswith(module_prefix):
                return service

        # Default to unknown service
        return "unknown_service"


# Global configuration instance
_logging_config: Optional[LoggingConfig] = None


def initialize_logging() -> LoggingConfig:
    """
    Initialize the global logging configuration.

    Returns:
        The initialized LoggingConfig instance
    """
    global _logging_config
    if _logging_config is None:
        _logging_config = LoggingConfig()
    return _logging_config


def get_logger(service_name: str, **context: Any) -> Any:
    """
    Get a service-specific logger instance.

    Args:
        service_name: Name of the service
        **context: Additional context to bind

    Returns:
        Configured logger instance
    """
    if _logging_config is None:
        initialize_logging()
    return _logging_config.get_logger(service_name, **context)


def get_module_logger(module_name: str = None, **context: Any) -> Any:
    """
    Get a logger for the calling module.

    Args:
        module_name: Module name (defaults to caller's __name__)
        **context: Additional context to bind

    Returns:
        Configured logger instance
    """
    if _logging_config is None:
        initialize_logging()

    # Auto-detect module name if not provided
    if module_name is None:
        import inspect

        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back
            module_name = caller_frame.f_globals.get("__name__", "unknown_module")
        finally:
            del frame

    return _logging_config.get_module_logger(module_name, **context)


# Convenience function for quick setup
def setup_logging(service_name: str = None, **context: Any) -> Any:
    """
    Quick setup function for services that need a logger.

    Args:
        service_name: Service name (auto-detected if not provided)
        **context: Additional context

    Returns:
        Configured logger instance
    """
    initialize_logging()

    if service_name:
        return get_logger(service_name, **context)
    return get_module_logger(**context)


# Export commonly used logger patterns
__all__ = [
    "LoggingConfig",
    "get_logger",
    "get_module_logger",
    "initialize_logging",
    "setup_logging",
]
