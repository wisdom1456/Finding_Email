"""Core business logic for Legal Document Analysis Portal."""
from .document_processor import DocumentProcessor
from .email_generator import EmailGeneratorV2, EmailReadabilityError  # Keep class name for compatibility
from .ai_analyzer import AIAnalyzer
from .main_processor import process_case_documents, process_case_documents_cli

__all__ = [
    'DocumentProcessor',
    'EmailGeneratorV2',
    'EmailReadabilityError',
    'AIAnalyzer',
    'process_case_documents',
    'process_case_documents_cli'
]