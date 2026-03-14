"""Enumerations for legal_portal domain models."""
from __future__ import annotations

from enum import Enum

__all__ = [
    "DocumentType",
    "DocumentStatus",
    "FileType",
    "GroupType",
    "LetterType",
    "GapSeverity",
    "GapCategory",
    "CaseRecommendationCategory",
    "ConfidenceLevel",
    "RecommendedLetterType",
]


class DocumentType(str, Enum):
    """Valid document types for processing."""

    INTAKE_FORM = "intake_form"
    CASE_DOCUMENT = "case_document"
    EVIDENCE = "evidence"
    CORRESPONDENCE = "correspondence"
    CONTRACT = "contract"
    LEGAL_BRIEF = "legal_brief"
    OTHER = "other"


class DocumentStatus(str, Enum):
    """Refined status for document extraction and verification."""

    READY = "ready"  # Extracted successfully, high quality
    NEEDS_REVIEW = "needs_review"  # Extracted but low quality or needs attention
    EXTRACTION_FAILED = "extraction_failed"  # File exists, but text extraction failed
    DOWNLOAD_FAILED = "download_failed"  # File never successfully downloaded from source
    CORRUPTED = "corrupted"  # File exists but appears damaged or unreadable
    SKIPPED = "skipped"  # Explicitly excluded from analysis by user or system
    PENDING = "pending"  # Waiting for processing
    DUPLICATE = "duplicate"  # Duplicate of another document in the case


class FileType(str, Enum):
    """Supported file types for document processing."""

    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    DOC = "application/msword"
    TXT = "text/plain"
    CSV = "text/csv"
    EML = "message/rfc822"
    IMAGE = "image/generic"  # Generic image type
    JPG = "image/jpeg"
    PNG = "image/png"
    GIF = "image/gif"
    BMP = "image/bmp"
    TIFF = "image/tiff"


class GroupType(str, Enum):
    """Types of document groups. Only high-confidence types are auto-detected."""
    # --- First rollout (high confidence) ---
    EMAIL_THREAD = "email_thread"
    CONTRACT_FAMILY = "contract_family"
    PHOTO_SEQUENCE = "photo_sequence"
    BANK_STATEMENTS = "bank_statements"
    # --- Deferred (validation needed) ---
    CREDIT_CARD_STATEMENTS = "credit_card_statements"
    MEDICAL_RECORDS = "medical_records"
    FINANCIAL_REPORTS = "financial_reports"
    INSURANCE_CLAIMS = "insurance_claims"
    TEXT_MESSAGES = "text_messages"
    REAL_ESTATE_PACKAGE = "real_estate_package"
    GENERIC = "generic"


class LetterType(str, Enum):
    """Types of letters that can be generated."""

    FINDINGS = "findings"
    DEMAND = "demand"


class GapSeverity(str, Enum):
    """Severity levels for identified gaps."""

    CRITICAL = "critical"  # Case-breaking gaps
    HIGH = "high"  # Significant impact
    MEDIUM = "medium"  # Notable concern
    LOW = "low"  # Minor issue


class GapCategory(str, Enum):
    """Categories of gaps that can be identified."""

    MISSING_DOCUMENT = "missing_document"
    FACTUAL_CONTRADICTION = "factual_contradiction"
    TIMELINE_GAP = "timeline_gap"
    UNVERIFIABLE_CLAIM = "unverifiable_claim"
    HALLUCINATION_RISK = "hallucination_risk"
    INCOMPLETE_INFO = "incomplete_info"


class CaseRecommendationCategory(str, Enum):
    """Categories for case recommendations based on gap analysis."""

    STRONG_CASE = "strong_case"  # Proceed with demand letter
    NEEDS_DOCUMENTATION = "needs_documentation"  # Pause, request docs
    SETTLEMENT_RECOMMENDED = "settlement_recommended"  # Negotiate
    NOT_VIABLE = "not_viable"  # Decline


class ConfidenceLevel(str, Enum):
    """Confidence levels for recommendations."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecommendedLetterType(str, Enum):
    """Types of letters that can be recommended based on case analysis."""

    PROCEED = "proceed"  # Engagement letter
    REQUEST_DOCUMENTS = "request_documents"
    SETTLEMENT_ADVISORY = "settlement_advisory"
    DECLINATION = "declination"
    FINDINGS = "findings"  # Standard findings
    DEMAND = "demand"  # Standard demand
