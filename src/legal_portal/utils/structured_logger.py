"""Structured logging with observability features."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Optional

# Context variables for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")


def resolve_environment() -> str:
    """Determine the runtime environment from platform-provided variables.

    Priority: VERCEL_ENV > ENVIRONMENT > infer from VERCEL flag > default.
    Returns one of: 'production', 'preview', 'development'.
    """
    # Explicit override
    env = os.getenv("VERCEL_ENV")  # Vercel sets this automatically
    if env:
        return env
    env = os.getenv("ENVIRONMENT")
    if env:
        return env
    # If VERCEL flag is set but VERCEL_ENV is missing (shouldn't happen, safety net)
    if os.getenv("VERCEL"):
        return "production"
    return "development"


class LogLevel(Enum):
    """Log levels with numeric values."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    AUDIT = 60  # Custom level for audit logs


class StructuredLogger:
    """Enterprise structured logging with observability."""

    def __init__(self, name: str, level: str = "INFO"):
        """Initialize structured logger."""
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level))
        self.name = name

        # Remove default handlers
        self.logger.handlers = []

        # Add structured JSON handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        self.logger.addHandler(handler)

        # Add file handler for persistence (only if not in serverless environment)
        # Vercel/serverless functions have read-only filesystems except /tmp
        if not os.getenv("VERCEL") and not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
            try:
                log_dir = Path("logs")
                log_dir.mkdir(exist_ok=True)

                file_handler = logging.FileHandler(
                    log_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
                )
                file_handler.setFormatter(JSONFormatter())
                self.logger.addHandler(file_handler)
            except (OSError, PermissionError):
                # If we can't create log files, just use stdout (which is fine for serverless)
                pass

    def _get_context(self) -> Dict[str, Any]:
        """Get contextual information for logs."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "logger": self.name,
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
            "session_id": session_id_var.get(),
            "environment": resolve_environment(),
            "service": "legal-document-portal",
            "version": os.getenv("APP_VERSION", "1.0.0"),
            "host": os.getenv("HOSTNAME", "localhost"),
        }

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log error message with optional exception."""
        if exception:
            kwargs["exception"] = {
                "type": type(exception).__name__,
                "message": str(exception),
                "traceback": traceback.format_exc(),
            }
        self._log(LogLevel.ERROR, message, **kwargs)

    def exception(self, message: str, **kwargs):
        """Log exception with full traceback (compatible with standard logging)."""
        kwargs["exception"] = {"type": "Exception", "message": message, "traceback": traceback.format_exc()}
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self._log(LogLevel.CRITICAL, message, **kwargs)

    def audit(self, action: str, resource: str, outcome: str, **kwargs):
        """Log audit event for compliance."""
        audit_data = {"action": action, "resource": resource, "outcome": outcome, "audit": True, **kwargs}
        self._log(LogLevel.AUDIT, f"AUDIT: {action} on {resource}", **audit_data)

    def _log(self, level: LogLevel, message: str, **kwargs):
        """Log message internally with structured data."""
        log_data = {**self._get_context(), "level": level.name, "message": message, "data": kwargs}

        # Use appropriate logging level
        if level == LogLevel.AUDIT:
            self.logger.critical(json.dumps(log_data))
        else:
            self.logger.log(level.value, json.dumps(log_data))

    def performance(self, operation: str):
        """Provide decorator for performance logging."""

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                request_id = str(uuid.uuid4())
                request_id_var.set(request_id)

                self.info(f"Starting {operation}", operation=operation, function=func.__name__)

                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time

                    self.info(
                        f"Completed {operation}",
                        operation=operation,
                        function=func.__name__,
                        duration_ms=duration * 1000,
                        success=True,
                    )

                    # Send metrics
                    from legal_portal.core.metrics import MetricsCollector

                    MetricsCollector.record_timing(operation, duration)

                    return result

                except Exception as e:
                    duration = time.time() - start_time

                    self.error(
                        f"Failed {operation}",
                        exception=e,
                        operation=operation,
                        function=func.__name__,
                        duration_ms=duration * 1000,
                        success=False,
                    )

                    # Send error metrics
                    from legal_portal.core.metrics import MetricsCollector

                    MetricsCollector.record_error(operation)

                    raise

            return wrapper

        return decorator


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record):
        """Format log record as JSON."""
        # Parse the JSON message if it's already formatted
        try:
            if hasattr(record, "msg") and isinstance(record.msg, str):
                if record.msg.startswith("{"):
                    return record.msg
        except Exception:
            pass

        # Otherwise create JSON structure
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_data)
