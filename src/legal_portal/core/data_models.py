from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

# ============================================================================
# Enumerations
# ============================================================================


class DocumentType(str, Enum):
    """Valid document types for processing."""

    INTAKE_FORM = "intake_form"
    CASE_DOCUMENT = "case_document"
    EVIDENCE = "evidence"
    CORRESPONDENCE = "correspondence"
    CONTRACT = "contract"
    LEGAL_BRIEF = "legal_brief"
    OTHER = "other"


class FileType(str, Enum):
    """Supported file types for document processing."""

    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    DOC = "application/msword"
    TXT = "text/plain"
    CSV = "text/csv"
    EML = "message/rfc822"
    JPG = "image/jpeg"
    PNG = "image/png"
    GIF = "image/gif"
    BMP = "image/bmp"
    TIFF = "image/tiff"


# ============================================================================
# Data Models
# ============================================================================


class FileMetadata(BaseModel):
    """Metadata about a processed file."""

    file_name: str
    file_type: FileType
    file_size: int
    uploaded_at: datetime = Field(default_factory=datetime.now)
    processing_time_ms: Optional[float] = None

    model_config = {"populate_by_name": True}

    def __init__(self, **data):
        """Override to handle legacy field names (filename -> file_name, size -> file_size)."""
        # Map legacy field names to new names
        if "filename" in data and "file_name" not in data:
            data["file_name"] = data.pop("filename")
        if "size" in data and "file_size" not in data:
            data["file_size"] = data.pop("size")

        # Ensure file_type is set if not provided (use a default)
        if "file_type" not in data:
            # Try to infer from file_name extension
            file_name = data.get("file_name", "")
            if file_name.lower().endswith(".pdf"):
                data["file_type"] = FileType.PDF
            elif file_name.lower().endswith((".docx",)):
                data["file_type"] = FileType.DOCX
            elif file_name.lower().endswith(".doc"):
                data["file_type"] = FileType.DOC
            elif file_name.lower().endswith(".txt"):
                data["file_type"] = FileType.TXT
            elif file_name.lower().endswith((".png",)):
                data["file_type"] = FileType.PNG
            elif file_name.lower().endswith((".jpg", ".jpeg")):
                data["file_type"] = FileType.JPG
            elif file_name.lower().endswith(".csv"):
                data["file_type"] = FileType.CSV
            elif file_name.lower().endswith(".eml"):
                data["file_type"] = FileType.EML
            else:
                data["file_type"] = FileType.PDF  # Default fallback

        super().__init__(**data)


class ProcessedDocument(BaseModel):
    """Represents a document after content extraction."""

    file_name: str
    content: str
    document_type: DocumentType
    metadata: FileMetadata
    page_count: Optional[int] = None
    extraction_method: Optional[str] = None
    extracted_at: datetime = Field(default_factory=datetime.now)


class ProcessingError(BaseModel):
    """Represents an error that occurred during processing."""

    source: str
    error_type: str
    error_message: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ProcessingResult(BaseModel):
    """Result of the complete document processing workflow.

    This is the model returned by the decoupled process_case_documents function.
    """

    # Core outputs
    main_letter: str = Field(description="HTML content of the generated findings letter")
    document_summaries: str = Field(description="Text summaries of all analyzed documents")
    case_analysis: str = Field(description="Detailed case analysis content")

    # Metadata
    status: str = Field(description="Processing status: 'completed', 'partial', or 'failed'")
    processing_time_seconds: Optional[float] = None
    processed_at: datetime = Field(default_factory=datetime.now)

    # Optional details
    intake_content: Optional[str] = None
    document_count: int = 0
    errors: List[ProcessingError] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "main_letter": "<html>...</html>",
                "document_summaries": "Document 1: ...",
                "case_analysis": "Analysis of case...",
                "status": "completed",
                "document_count": 5,
                "errors": [],
            }
        }


# ============================================================================
# Legacy Models (for compatibility)
# ============================================================================


class IntakeAnalysis(BaseModel):
    """Analysis results from the intake form."""

    client_name: Optional[str] = None
    attorney_name: Optional[str] = None
    case_type: Optional[str] = None
    case_summary: Optional[str] = None
    urgency_level: Optional[str] = None
    client_priorities: List[str] = Field(default_factory=list)
    desired_outcomes: List[str] = Field(default_factory=list)


class AnalyzedDocument(BaseModel):
    """Analysis results for a single document."""

    file_name: str
    document_type: str
    inferred_title: Optional[str] = None
    summary: str
    relevance_to_case: str
    key_information: Optional[str] = None


class LegalAssessment(BaseModel):
    """Legal assessment of the case."""

    claim_viability: Optional[str] = None
    overall_evidence_strength: Optional[str] = None
    potential_challenges: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)


class CaseAnalysisResult(BaseModel):
    """Complete case analysis result (legacy format)."""

    intake_analysis: Optional[IntakeAnalysis] = None
    analyzed_documents: List[AnalyzedDocument] = Field(default_factory=list)
    legal_assessment: Optional[LegalAssessment] = None
    errors: List[ProcessingError] = Field(default_factory=list)


class ServiceCost(BaseModel):
    """Cost breakdown for a specific service operation."""

    service_name: str
    cost: float
    operation_type: str
    details: Optional[dict] = None


class CostEstimate(BaseModel):
    """Estimated cost for processing."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model_used: str = "gpt-4"

    model_config = {"protected_namespaces": ()}  # Allow 'model_' prefix
