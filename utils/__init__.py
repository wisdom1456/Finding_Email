"""Utility modules for the application."""
from __future__ import annotations

from .api_optimizer import OpenAIOptimizer
from .async_streamlit import AsyncStreamlit, ParallelDocumentProcessor
from .cache_manager import CacheManager, DocumentCache
from .logging_config import get_logger, setup_logging
from .pii_sanitizer import PIISanitizer
from .security import secure_filename, validate_file_content, validate_file_size


__all__ = [
    # API optimization
    "OpenAIOptimizer",
    # Async utilities
    "AsyncStreamlit",
    "ParallelDocumentProcessor",
    # Caching
    "CacheManager",
    "DocumentCache",
    # Security
    "secure_filename",
    "validate_file_size",
    "validate_file_content",
    # PII handling
    "PIISanitizer",
    # Logging
    "setup_logging",
    "get_logger"
]
