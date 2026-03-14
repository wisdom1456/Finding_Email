"""Centralized exception hierarchy for the Legal Portal.

All application-specific exceptions inherit from AppError.
Each subclass carries an HTTP status code and optional structured context.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    """Base exception for all application errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}
        if error_code is not None:
            self.error_code = error_code

    def to_log_dict(self) -> Dict[str, Any]:
        """Return a dict suitable for structured logging."""
        return {
            "error_type": type(self).__name__,
            "error_code": self.error_code,
            "error_message": self.message,
            "context": self.context,
        }


class ValidationError(AppError):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class AuthorizationError(AppError):
    status_code = 403
    error_code = "AUTHORIZATION_ERROR"


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class ExternalServiceError(AppError):
    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"


class TransientDatabaseError(AppError):
    status_code = 503
    error_code = "TRANSIENT_DATABASE_ERROR"


class AnalysisPipelineError(AppError):
    status_code = 500
    error_code = "ANALYSIS_PIPELINE_ERROR"
