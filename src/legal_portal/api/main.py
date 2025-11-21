"""FastAPI main application entry point.

This module defines the FastAPI application with CORS configuration,
middleware, and core routes for the Legal Document Analysis Portal.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load environment variables from .env file
load_dotenv()

from legal_portal.api.routes import analysis, cases, clio, documents, health, intake


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    print("🚀 Starting Legal Document Analysis API...")

    # Initialize connections, load configs, etc.
    # For now, we'll just verify environment variables
    required_env_vars = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "OPENAI_API_KEY"]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print(f"⚠️  Warning: Missing environment variables: {', '.join(missing_vars)}")

    yield

    # Shutdown
    print("🛑 Shutting down Legal Document Analysis API...")


# Initialize FastAPI application
app = FastAPI(
    title="Legal Document Analysis API",
    description="Backend API for analyzing legal documents and generating findings letters",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
# TODO: Configure allowed origins for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production with specific domains
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
app.include_router(clio.router, prefix="/api", tags=["clio"])
app.include_router(intake.router, prefix="/api", tags=["intake"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Legal Document Analysis API", "version": "1.0.0", "status": "running"}
