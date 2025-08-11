"""Core business logic for Legal Document Analysis Portal."""
from __future__ import annotations

from .ai_analyzer import AIAnalyzer
from .document_processor import DocumentProcessor
from .email_generator import (  # Keep class name for compatibility
    EmailGeneratorV2,
    EmailReadabilityError,
)
from .main_processor import process_case_documents, process_case_documents_cli


__all__ = [
    "AIAnalyzer",
    "DocumentProcessor",
    "EmailGeneratorV2",
    "EmailReadabilityError",
    "process_case_documents",
    "process_case_documents_cli"
]
