from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

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
    file_type: FileType
    metadata: FileMetadata
    page_count: Optional[int] = None
    extraction_method: Optional[str] = None
    extraction_quality: Optional[str] = None  # "high", "medium", "low"
    extracted_at: datetime = Field(default_factory=datetime.now)


class ProcessingError(BaseModel):
    """Represents an error that occurred during processing."""

    source: str
    error_type: str
    error_message: str
    timestamp: datetime = Field(default_factory=datetime.now)


class AnalysisError(BaseModel):
    """Lightweight error object returned to the UI when a step fails."""

    source: str
    error_message: str
    error_type: Optional[str] = None
    details: Optional[Any] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class AIAnalysisError(Exception):
    """Custom exception for AI analysis failures."""

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.details = details


# ============================================================================
# Structured Summary Models (for enhanced AI output)
# ============================================================================


class KeyDate(BaseModel):
    """Represents a significant date in the case."""

    date: str = Field(description="Date in YYYY-MM-DD format or 'Month DD, YYYY'")
    event: str = Field(description="What happened on this date")
    source_document: Optional[str] = None


class KeyAmount(BaseModel):
    """Represents a monetary amount in the case."""

    amount: str = Field(description="Formatted as $XXX,XXX.XX")
    description: str = Field(description="What this amount represents")
    source_document: Optional[str] = None


class DocumentSummaryStructured(BaseModel):
    """Structured summary of a document for AI analysis.

    This model ensures consistent, complete extraction of legal facts.
    """

    document_name: str
    document_type: str = Field(description="E.g., contract, disclosure, correspondence, evidence")
    parties: List[str] = Field(
        default_factory=list, description="All parties mentioned (people, companies, entities)"
    )
    key_dates: List[KeyDate] = Field(
        default_factory=list, description="Important dates (purchase, breach, notice, deadline)"
    )
    key_amounts: List[KeyAmount] = Field(
        default_factory=list, description="Monetary amounts (purchase price, damages, fees)"
    )
    issues_identified: List[str] = Field(
        default_factory=list, description="Legal problems, violations, or concerns found"
    )
    relevance_to_case: str = Field(description="How this document relates to the client's claims")
    extraction_quality: str = Field(
        default="high", description="Quality of source text: 'high', 'medium', or 'low'"
    )
    extraction_notes: Optional[str] = Field(
        default=None, description="Any issues with source text (e.g., 'Extracted via OCR, may have errors')"
    )

    class Config:
        """Pydantic configuration for DocumentSummaryStructured."""

        json_schema_extra = {
            "example": {
                "document_name": "Property_Disclosure_Form.pdf",
                "document_type": "Seller Disclosure",
                "parties": ["Miguel Velasco", "Rachael Taft", "William Lichtenstein"],
                "key_dates": [{"date": "2024-02-29", "event": "Property purchase"}],
                "key_amounts": [{"amount": "$590,000.00", "description": "Purchase price"}],
                "issues_identified": [
                    "Seller answered 'I don't know' to flood history questions",
                    "Property located in special flood hazard area",
                ],
                "relevance_to_case": "Shows seller failed to disclose known flood risks",
                "extraction_quality": "high",
            }
        }


class PartyInvolved(BaseModel):
    """Represents an individual or organization involved in the matter."""

    name: str
    role: str
    relationship: Optional[str] = None
    contact_information: Optional[str] = None


class EnhancedIntakeAnalysis(BaseModel):
    """Rich intake analysis used by the new AI pipeline."""

    client_name: Optional[str] = None
    attorney_name: Optional[str] = None
    case_summary: Optional[str] = None
    case_type: Optional[str] = None
    urgency_level: Optional[str] = None
    client_priorities: List[str] = Field(default_factory=list)
    desired_outcomes: List[str] = Field(default_factory=list)
    key_facts: List[str] = Field(default_factory=list)
    parties_involved: List[PartyInvolved] = Field(default_factory=list)
    financial_impact: Optional[str] = None
    legal_claims: List[str] = Field(default_factory=list)
    timeline_events: List[Dict[str, Any]] = Field(default_factory=list)


class DemandLetterEvaluation(BaseModel):
    """Determines whether a demand letter is an appropriate next step."""

    is_appropriate: bool = True
    reasoning: str = ""
    potential_outcomes: List[str] = Field(default_factory=list)
    relevant_statutes: List[str] = Field(default_factory=list)


class FinalAnalysis(BaseModel):
    """Captures final recommendations and next steps for the client."""

    case_summary: Optional[str] = None
    recommendations: Optional[str] = None
    next_steps: List[str] = Field(default_factory=list)


class QualityScore(BaseModel):
    """Quality assessment for extracted content."""

    document: str = Field(description="The name of the document being assessed")
    score: float = Field(ge=0.0, le=10.0, description="Quality score from 0-10")
    has_meaningful_content: bool = Field(description="Text contains actual information vs. noise")
    is_complete: bool = Field(description="Document appears complete (not truncated)")
    confidence_level: str = Field(description="'high', 'medium', or 'low'")
    issues: List[str] = Field(default_factory=list, description="Any quality concerns")
    recommendations: List[str] = Field(
        default_factory=list, description="Suggested improvements or follow-ups"
    )


class CaseAnalysisSummary(BaseModel):
    """High-level case analysis for display on results page.

    This represents the synthesized case-level insights that are shown
    in the Case Analysis section of the UI.
    """

    case_summary: str = Field(description="120-200 word executive summary of the case")
    practice_area: str = Field(
        description="Primary practice area (e.g., 'Construction Law', 'Consumer Protection')"
    )
    key_issues: List[str] = Field(description="List of 3-7 key legal issues identified")
    relevant_statutes: List[Dict[str, str]] = Field(
        description="List of {statute: 'Fla. Stat. § XXX', relevance: 'Why it applies'}"
    )
    additional_details: Optional[str] = Field(default=None, description="Any additional important details")


class ProcessingResult(BaseModel):
    """Result of the complete document processing workflow.

    This is the model returned by the decoupled process_case_documents function.
    """

    # Core outputs
    main_letter: str = Field(description="HTML content of the generated findings letter")
    main_letter_with_citations: Optional[str] = Field(
        default=None, description="HTML content of the findings letter with citations"
    )
    document_summaries: str = Field(description="Text summaries of all analyzed documents")
    case_analysis: str = Field(description="Detailed case analysis content")
    quality_report: Optional[List[Dict[str, Any]]] = None  # NEW: For quality report

    # Metadata
    status: str = Field(description="Processing status: 'completed', 'partial', or 'failed'")
    processing_time_seconds: Optional[float] = None
    processed_at: datetime = Field(default_factory=datetime.now)

    # Optional details
    intake_content: Optional[str] = None
    document_count: int = 0
    errors: List[ProcessingError] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list, description="Non-critical warnings for user awareness")
    citation_summary: Optional[Dict[str, Any]] = Field(
        default=None, description="Summary stats for citation tracking"
    )
    citation_appendix: Optional[str] = Field(
        default=None, description="HTML appendix listing citations and source documents"
    )
    citation_map: Optional[Dict[str, Any]] = Field(
        default=None, description="Full citation map structure for diagnostics"
    )
    statute_validation: Optional[Dict[str, Any]] = Field(
        default=None, description="Results from statute validation service"
    )
    qa_warnings: Optional[List[str]] = Field(
        default=None, description="Lightweight QA heuristics output for reviewer awareness"
    )
    artifacts: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Stored artifact metadata (paths, content types, signed URLs)",
    )

    class Config:
        """Pydantic configuration for ProcessingResult."""

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
    potential_challenges: Union[str, List[str], None] = None
    recommended_actions: List[str] = Field(default_factory=list)
    demand_letter_appropriate: Optional[bool] = None
    urgency_assessment: Optional[str] = None


class CaseAnalysisResult(BaseModel):
    """Complete case analysis result (legacy format)."""

    intake_analysis: Optional[Union[EnhancedIntakeAnalysis, IntakeAnalysis]] = None
    analyzed_documents: List[AnalyzedDocument] = Field(default_factory=list)
    legal_assessment: Optional[LegalAssessment] = None
    demand_letter_evaluation: Optional[DemandLetterEvaluation] = None
    final_analysis: Optional[FinalAnalysis] = None
    errors: List[ProcessingError] = Field(default_factory=list)


class ServiceCost(BaseModel):
    """Cost breakdown for a specific service operation."""

    service_name: str
    cost: float
    operation_type: str
    details: Optional[dict] = None
    units_consumed: Optional[int] = None
    unit_type: Optional[str] = None
    rate_per_unit: Optional[float] = None
    total_cost: Optional[float] = None
    file_name: Optional[str] = None


class ActualCosts(BaseModel):
    """Total actual costs for all processing operations."""

    total_actual_cost: float
    service_costs: List[ServiceCost] = Field(default_factory=list)


class TranscriptedMedia(BaseModel):
    """Transcribed audio/media file."""

    file_name: str
    transcript: str
    duration: Optional[float] = None  # Duration in seconds


class VideoInsight(BaseModel):
    """Video analysis insights."""

    file_name: str
    duration: Optional[float] = None
    insights: Optional[str] = None
    labels: Optional[List[str]] = None
    objects: Optional[List[str]] = None
    metadata: Optional[FileMetadata] = None


class EnhancedVideoInsight(VideoInsight):
    """Enhanced video insight with criminal analysis."""

    is_criminal_case: bool = False
    criminal_analysis: Optional[str] = None


class CostEstimate(BaseModel):
    """Estimated cost for processing."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model_used: str = "gpt-4"

    model_config = {"protected_namespaces": ()}  # Allow 'model_' prefix


# ============================================================================
# CLIO Integration Models
# ============================================================================


class ClioContact(BaseModel):
    """Person or organization in CLIO."""

    id: int
    name: str
    type: str  # "Person", "Company"
    email: Optional[str] = None
    phone: Optional[str] = None


class ClioMatter(BaseModel):
    """CLIO matter with rich metadata."""

    id: int
    display_number: str
    description: str
    client_name: str
    practice_area: Optional[str] = None
    status: str
    open_date: datetime
    close_date: Optional[datetime] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class ClioCommunication(BaseModel):
    """Email or communication with metadata."""

    id: int
    subject: str
    date: datetime
    sender: ClioContact
    recipients: List[ClioContact]
    body: str
    communication_type: str  # "Email", "PhoneCall", "Letter"
    matter_id: int


class ClioMatterContext(BaseModel):
    """Rich context for letter generation."""

    matter_summary: str
    timeline: List[Dict[str, Any]]  # Chronological events
    party_relationships: Dict[str, str]  # name -> role
    communication_statistics: Dict[str, Any]
    key_dates: List[Dict[str, Any]]
    communication_gaps: List[str]  # Notable silences


class ClioImportResult(BaseModel):
    """Complete import result with metadata."""

    matter: ClioMatter
    communications_imported: int
    documents_imported: int
    notes_imported: int
    contacts: List[ClioContact]
    matter_context: ClioMatterContext
    auto_populated_qa: List[Dict[str, str]]
    errors: List[str]
    date_range: Optional[tuple[datetime, datetime]] = None
    total_file_size_bytes: int = 0
    import_duration_seconds: float = 0
