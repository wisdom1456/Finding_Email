#!/usr/bin/env python3
"""
Shared Utility Service
Consolidates common functionality across email generation services to reduce code duplication
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Union

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)


logger = logging.getLogger(__name__)


class SharedUtilityService:
    """
    Centralized utility service providing common functionality for email generation services.

    This service consolidates:
    - OpenAI error handling patterns
    - Structured logging utilities
    - Data validation helpers
    - Common service operations
    """

    def __init__(self):
        """Initialize the shared utility service"""
        self.service_name = "SharedUtilityService"

    def log_service_activity(
        self, method: str, stage: str, hypothesis_id: str, level: str = "info", **kwargs
    ) -> None:
        """
        Standardized logging for service activities with consistent structure

        Args:
            method: Name of the calling method
            stage: Current stage (entry, exit, processing, error)
            hypothesis_id: Identifier for tracking related operations
            level: Log level (debug, info, warning, error)
            **kwargs: Additional context fields
        """
        log_data = {
            "method": method,
            "stage": stage,
            "hypothesis_id": hypothesis_id,
            "timestamp": time.time(),
            **kwargs,
        }

        # Create message based on stage
        if stage == "entry":
            message = f"Entering {method}"
        elif stage == "exit":
            message = f"Exiting {method}"
        elif stage == "error":
            message = f"Error in {method}"
        else:
            message = f"{method} - {stage}"

        # Log at appropriate level
        getattr(logger, level.lower(), logger.info)(message, extra=log_data)

    def handle_openai_errors(
        self,
        error: Exception,
        context: Dict[str, Any],
        method: str = "unknown_method",
        re_raise: bool = False,
    ) -> Optional[str]:
        """
        Centralized OpenAI error handling with consistent logging and classification

        Args:
            error: The exception that was raised
            context: Context information (model, prompt details, etc.)
            method: Name of the calling method for logging
            re_raise: Whether to re-raise retryable errors for retry logic

        Returns:
            Error classification string or None
        """
        error_type = type(error).__name__

        # Retryable errors - typically temporary issues
        if isinstance(
            error,
            (
                APIConnectionError,
                RateLimitError,
                APITimeoutError,
                APIError,
                InternalServerError,
            ),
        ):
            self._handle_retryable_errors(error, context, method)
            if re_raise:
                raise error
            return "retryable"

        # Authentication errors - configuration issues
        if isinstance(error, (AuthenticationError, PermissionDeniedError)):
            self._handle_authentication_errors(error, context, method)
            return "authentication"

        # Client errors - bad request format or parameters
        if isinstance(error, (BadRequestError, UnprocessableEntityError)):
            self._handle_client_errors(error, context, method)
            return "client"

        # Server errors - API status issues
        if isinstance(error, APIStatusError):
            self._handle_server_errors(error, context, method)
            return "server"

        # Unexpected errors - programming or system issues
        self._handle_unexpected_errors(error, context, method)
        return "unexpected"

    def _handle_retryable_errors(
        self, error: Exception, context: Dict[str, Any], method: str
    ) -> None:
        """Handle retryable OpenAI errors that should trigger retry logic"""
        error_type = type(error).__name__

        logger.warning(
            f"Retryable OpenAI error encountered: {error_type}",
            extra={
                "method": method,
                "hypothesis_id": "retryable_error_handling",
                "error_type": error_type,
                "error_details": str(error),
                "model": context.get("model"),
                "will_retry": True,
                "service": self.service_name,
            },
        )

    def _handle_authentication_errors(
        self, error: Exception, context: Dict[str, Any], method: str
    ) -> None:
        """Handle authentication-related OpenAI errors"""
        error_type = type(error).__name__

        logger.error(
            f"Authentication error: {error_type}",
            extra={
                "method": method,
                "hypothesis_id": "authentication_error_handling",
                "error_type": error_type,
                "error_details": str(error),
                "model": context.get("model"),
                "requires_api_key_check": True,
                "service": self.service_name,
            },
        )

    def _handle_client_errors(
        self, error: Exception, context: Dict[str, Any], method: str
    ) -> None:
        """Handle client-side OpenAI errors"""
        error_type = type(error).__name__

        logger.error(
            f"Client error: {error_type}",
            extra={
                "method": method,
                "hypothesis_id": "client_error_handling",
                "error_type": error_type,
                "error_details": str(error),
                "model": context.get("model"),
                "prompt_start": context.get("prompt", "")[:200],
                "service": self.service_name,
            },
        )

    def _handle_server_errors(
        self, error: Exception, context: Dict[str, Any], method: str
    ) -> None:
        """Handle server-side OpenAI errors"""
        error_type = type(error).__name__
        request_id = getattr(error, "request_id", "unknown")
        status_code = getattr(error, "status_code", "unknown")

        logger.error(
            f"Server error: {error_type}",
            extra={
                "method": method,
                "hypothesis_id": "server_error_handling",
                "error_type": error_type,
                "status_code": status_code,
                "request_id": request_id,
                "model": context.get("model"),
                "service": self.service_name,
            },
        )

    def _handle_unexpected_errors(
        self, error: Exception, context: Dict[str, Any], method: str
    ) -> None:
        """Handle unexpected errors during OpenAI requests"""
        error_type = type(error).__name__

        logger.error(
            f"Unexpected error: {error_type}",
            extra={
                "method": method,
                "hypothesis_id": "unexpected_error_handling",
                "error_type": error_type,
                "error_details": str(error),
                "model": context.get("model"),
                "prompt_start": context.get("prompt", "")[:200],
                "service": self.service_name,
            },
        )

    def validate_required_keys(
        self, data: Dict[str, Any], required_keys: List[str], context_name: str = "data"
    ) -> bool:
        """
        Validate that all required keys are present in a dictionary

        Args:
            data: Dictionary to validate
            required_keys: List of required key names
            context_name: Name of the data context for error messages

        Returns:
            True if all keys are present, False otherwise
        """
        missing_keys = []
        for key in required_keys:
            if key not in data or data[key] is None:
                missing_keys.append(key)

        if missing_keys:
            logger.error(
                f"Missing required keys in {context_name}",
                extra={
                    "method": "validate_required_keys",
                    "hypothesis_id": "data_validation",
                    "missing_keys": missing_keys,
                    "required_keys": required_keys,
                    "available_keys": list(data.keys()),
                    "context_name": context_name,
                    "service": self.service_name,
                },
            )
            return False

        logger.debug(
            f"All required keys present in {context_name}",
            extra={
                "method": "validate_required_keys",
                "hypothesis_id": "data_validation",
                "required_keys": required_keys,
                "context_name": context_name,
                "service": self.service_name,
            },
        )
        return True

    def validate_non_empty_string(self, value: Any, field_name: str) -> bool:
        """
        Validate that a value is a non-empty string

        Args:
            value: Value to validate
            field_name: Name of the field for error messages

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(value, str) or not value.strip():
            logger.error(
                f"Invalid {field_name}: must be a non-empty string",
                extra={
                    "method": "validate_non_empty_string",
                    "hypothesis_id": "data_validation",
                    "field_name": field_name,
                    "value_type": type(value).__name__,
                    "value_length": len(str(value)) if value else 0,
                    "service": self.service_name,
                },
            )
            return False
        return True

    def validate_positive_number(
        self, value: Any, field_name: str, allow_zero: bool = False
    ) -> bool:
        """
        Validate that a value is a positive number

        Args:
            value: Value to validate
            field_name: Name of the field for error messages
            allow_zero: Whether to allow zero as a valid value

        Returns:
            True if valid, False otherwise
        """
        try:
            num_value = float(value)
            if allow_zero:
                is_valid = num_value >= 0
                requirement = "non-negative"
            else:
                is_valid = num_value > 0
                requirement = "positive"

            if not is_valid:
                logger.error(
                    f"Invalid {field_name}: must be a {requirement} number",
                    extra={
                        "method": "validate_positive_number",
                        "hypothesis_id": "data_validation",
                        "field_name": field_name,
                        "value": value,
                        "requirement": requirement,
                        "allow_zero": allow_zero,
                        "service": self.service_name,
                    },
                )
                return False
            return True

        except (ValueError, TypeError):
            logger.error(
                f"Invalid {field_name}: must be a numeric value",
                extra={
                    "method": "validate_positive_number",
                    "hypothesis_id": "data_validation",
                    "field_name": field_name,
                    "value": value,
                    "value_type": type(value).__name__,
                    "service": self.service_name,
                },
            )
            return False

    def sanitize_prompt(self, prompt: str, max_length: Optional[int] = None) -> str:
        """
        Sanitize and optionally truncate a prompt for safe processing

        Args:
            prompt: Input prompt to sanitize
            max_length: Maximum allowed length (None for no limit)

        Returns:
            Sanitized prompt string
        """
        if not isinstance(prompt, str):
            logger.warning(
                "Non-string prompt provided, converting to string",
                extra={
                    "method": "sanitize_prompt",
                    "hypothesis_id": "prompt_sanitization",
                    "original_type": type(prompt).__name__,
                    "service": self.service_name,
                },
            )
            prompt = str(prompt)

        # Strip whitespace
        prompt = prompt.strip()

        # Truncate if necessary
        if max_length and len(prompt) > max_length:
            original_length = len(prompt)
            prompt = prompt[:max_length]
            logger.info(
                f"Prompt truncated from {original_length} to {max_length} characters",
                extra={
                    "method": "sanitize_prompt",
                    "hypothesis_id": "prompt_sanitization",
                    "original_length": original_length,
                    "truncated_length": len(prompt),
                    "max_length": max_length,
                    "service": self.service_name,
                },
            )

        return prompt

    def create_request_context(
        self,
        method: str,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Create a standardized context dictionary for request operations

        Args:
            method: Name of the calling method
            model: Model being used
            prompt: Prompt being processed
            **kwargs: Additional context fields

        Returns:
            Context dictionary with standardized fields
        """
        context = {
            "method": method,
            "timestamp": time.time(),
            "service": self.service_name,
            **kwargs,
        }

        if model:
            context["model"] = model
        if prompt:
            context["prompt"] = prompt
            context["prompt_length"] = len(prompt)

        return context


# Create a singleton instance for shared use
shared_utils = SharedUtilityService()
