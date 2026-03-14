"""Centralized error handler for AppError exceptions.

Converts AppError subclasses to structured JSON. Sits alongside
the existing general_exception_handler and HTTPException handling.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from legal_portal.core.exceptions import AppError

logger = logging.getLogger(__name__)


def register_app_error_handler(app: FastAPI) -> None:
    """Register the AppError exception handler on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "AppError %s: %s", type(exc).__name__, exc.message,
                extra=exc.to_log_dict(),
            )
        else:
            logger.warning(
                "AppError %s: %s", type(exc).__name__, exc.message,
                extra=exc.to_log_dict(),
            )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": type(exc).__name__,
                "message": exc.message,
                "context": exc.context if exc.context else None,
            },
        )
