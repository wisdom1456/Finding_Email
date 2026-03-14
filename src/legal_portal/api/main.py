"""FastAPI main application entry point.

This module defines the FastAPI application with CORS configuration,
middleware, and core routes for the Legal Document Analysis Portal.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from legal_portal.api.middleware.error_handler import register_app_error_handler
from legal_portal.api.rate_limiter import limiter
from legal_portal.api.routes import (
    analysis,
    cases,
    chat_routes,
    clio,
    corpus,
    document_status_routes,
    gap_routes,
    documents,
    health,
    intake,
    profile,
    progress,
    settings,
)
from legal_portal.utils.logging_config import setup_logging

# Load environment variables from .env file
load_dotenv()

# Setup logging with enhanced observability
setup_logging(app_name="legal-portal-api")
logger = logging.getLogger(__name__)

# Rate limiter is imported from rate_limiter.py module


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Legal Document Analysis API...")

    # Initialize connections, load configs, etc.
    # Verify environment variables
    required_env_vars = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "OPENAI_API_KEY"]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")
    else:
        logger.info("All required environment variables are set")

    yield

    # Shutdown
    logger.info("Shutting down Legal Document Analysis API...")


# Initialize FastAPI application
app = FastAPI(
    title="Legal Document Analysis API",
    description="Backend API for analyzing legal documents and generating findings emails",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter to app state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
register_app_error_handler(app)

# CORS configuration
# Get allowed origins from environment variable or use defaults
cors_origins_env = os.getenv("CORS_ORIGINS", "")
if cors_origins_env:
    # Parse comma-separated origins from environment
    allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
else:
    # Default origins for development
    allowed_origins = [
        "http://localhost:5173",  # SvelteKit dev
        "http://127.0.0.1:5173",  # SvelteKit dev (IP)
    ]

    # Add Vercel URL if available (production/preview deployments)
    vercel_url = os.getenv("VERCEL_URL")
    if vercel_url:
        # Add both https and http versions
        allowed_origins.append(f"https://{vercel_url}")
        allowed_origins.append(f"http://{vercel_url}")
        logger.info(f"Added Vercel URL to CORS origins: {vercel_url}")

logger.info(f"CORS configured with origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "message": "Internal server error",
            "detail": str(exc) if app.debug else "An error occurred",
        },
    )


# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(cases.router, prefix="/api/cases", tags=["cases"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(chat_routes.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(document_status_routes.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(gap_routes.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(progress.router, prefix="/api", tags=["progress"])
app.include_router(clio.router, prefix="/api", tags=["clio"])
app.include_router(intake.router, prefix="/api", tags=["intake"])
app.include_router(profile.router, prefix="/api", tags=["profile"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(corpus.router, prefix="/api/corpus", tags=["corpus"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Legal Document Analysis API", "version": "1.0.0", "status": "running"}
