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


class DocumentStatus(str, Enum):
    """Refined status for document extraction and verification."""

    READY = "ready"  # Extracted successfully, high quality
    NEEDS_REVIEW = "needs_review"  # Extracted but low quality or needs attention
    EXTRACTION_FAILED = "extraction_failed"  # File exists, but text extraction failed
    DOWNLOAD_FAILED = "download_failed"  # File never successfully downloaded from source
    CORRUPTED = "corrupted"  # File exists but appears damaged or unreadable
    SKIPPED = "skipped"  # Explicitly excluded from analysis by user or system
    PENDING = "pending"  # Waiting for processing


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
    document_id: Optional[str] = None  # NEW: Link back to database record
    page_count: Optional[int] = None
    extraction_method: Optional[str] = None
    extraction_quality: Optional[str] = None  # "high", "medium", "low"
    extraction_error: Optional[str] = None  # NEW: Record extraction errors
    ocr_provider: Optional[str] = None  # NEW: Record which OCR provider was used
    extracted_at: datetime = Field(default_factory=datetime.now)
    status: DocumentStatus = DocumentStatus.READY


class SkippedDocument(BaseModel):
    """Represents a document that was skipped during analysis."""

    document_id: str
    file_name: str
    reason: str
    error_type: str  # e.g., "DOWNLOAD_FAILED", "CORRUPTED", "EMPTY"
    recommendation: str


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


class ContractClause(BaseModel):
    """A specific clause or section from a contract."""

    clause_id: Optional[str] = Field(default=None, description="Section number or ID")
    description: str = Field(description="Summary of the clause content")
    snippet: Optional[str] = Field(default=None, description="Verbatim text snippet")


class DocumentDate(BaseModel):
    """Date extracted from a document."""

    date: str = Field(description="YYYY-MM-DD or Month DD, YYYY")
    event: str = Field(description="Description of the event")
    source: Optional[str] = Field(default=None, description="Page or section reference")


class DocumentAmount(BaseModel):
    """Monetary amount extracted from a document."""

    amount: str = Field(description="Formatted amount (e.g. $1,000.00)")
    description: str = Field(description="What the amount represents")
    source: Optional[str] = Field(default=None, description="Page or section reference")


class StructuredData(BaseModel):
    """Structured data extracted from a document."""

    parties: List[str] = Field(default_factory=list, description="List of parties mentioned")
    dates: List[DocumentDate] = Field(default_factory=list, description="Key dates found")
    amounts: List[DocumentAmount] = Field(default_factory=list, description="Monetary amounts found")
    contract_clauses: List[ContractClause] = Field(default_factory=list, description="Key contract clauses")


class DocumentSummaryStructured(BaseModel):
    """Structured summary of a document for AI analysis.

    This model ensures consistent, complete extraction of legal facts.
    """

    document_name: str
    document_type: str = Field(description="E.g., contract, disclosure, correspondence, evidence")

    # Detailed narrative fields (New Schema)
    executive_summary: Optional[str] = Field(default=None, description="High-level overview of the document")
    key_content: Optional[str] = Field(
        default=None, description="Comprehensive narrative of important information"
    )
    important_details: List[str] = Field(
        default_factory=list, description="Critical info, risks, conflicts, or requirements"
    )
    legal_significance: Optional[str] = Field(default=None, description="Why this document matters legally")

    # Evidence & Citations (NEW)
    key_quotes: List[str] = Field(
        default_factory=list, description="Verbatim excerpts from the document that serve as evidence"
    )
    statute_citations: List[str] = Field(
        default_factory=list, description="Relevant Florida statutes (e.g., 'Fla. Stat. § 713.06')"
    )

    # Structured data container
    structured_data: Optional[StructuredData] = Field(
        default=None, description="Organized data points (dates, amounts, parties)"
    )

    # Legacy fields (kept for compatibility, optional)
    parties: List[str] = Field(default_factory=list)
    key_dates: List[KeyDate] = Field(default_factory=list)
    key_amounts: List[KeyAmount] = Field(default_factory=list)
    issues_identified: List[str] = Field(default_factory=list)

    relevance_to_case: str = Field(
        default="Relevance to be determined", description="How this document relates to the client's claims"
    )
    extraction_quality: str = Field(
        default="high", description="Quality of source text: 'high', 'medium', or 'low'"
    )
    extraction_notes: Optional[str] = Field(
        default=None, description="Any issues with source text (e.g., 'Extracted via OCR, may have errors')"
    )

    class Config:
        """Pydantic configuration for DocumentSummaryStructured."""

        extra = "ignore"  # Allow extra fields from AI response without error


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


class LetterType(str, Enum):
    """Types of letters that can be generated."""

    FINDINGS = "findings"
    DEMAND = "demand"


class DemandLetterRequest(BaseModel):
    """API request payload for generating a demand letter."""

    case_id: str
    target_party_name: str
    demand_amount: Optional[float] = None
    demand_deadline: str = "10 business days"
    specific_demands: List[str] = Field(default_factory=list)
    attorney_name: Optional[str] = None
    firm_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    client_name: Optional[str] = None


class ChatMessageRequest(BaseModel):
    """API request payload for chatting about a case."""

    case_id: str
    message: str


class ChatMessageResponse(BaseModel):
    """API response payload for case chat."""

    response: str
    context_used: Dict[str, Any] = Field(default_factory=dict)


class FinalAnalysis(BaseModel):
    """Captures final recommendations and next steps for the client."""

    case_summary: Optional[str] = None
    recommendations: Optional[str] = None
    next_steps: List[str] = Field(default_factory=list)


class QualityScore(BaseModel):
    """Quality assessment for extracted content."""

    document: str = Field(description="The name of the document being assessed")
    document_id: Optional[str] = Field(default=None, description="Database ID of the document")
    score: float = Field(ge=0.0, le=10.0, description="Quality score from 0-10")
    has_meaningful_content: bool = Field(description="Text contains actual information vs. noise")
    is_complete: bool = Field(description="Document appears complete (not truncated)")
    confidence_level: str = Field(description="'high', 'medium', or 'low'")
    extraction_method: Optional[str] = Field(
        default=None,
        description="Method used: PyMuPDF, pypdf, Google Cloud Vision, GPT-4o Vision, text_fallback",
    )
    ocr_provider: Optional[str] = Field(
        default=None, description="OCR provider if used: google_vision, openai, None"
    )
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
    processed_documents: List[ProcessedDocument] = Field(
        default_factory=list
    )  # NEW: For persisting extraction results
    skipped_documents: List[SkippedDocument] = Field(
        default_factory=list
    )  # NEW: Documents auto-skipped during analysis

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
    artifacts: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Stored artifact metadata (paths, content types, signed URLs) and context data",
    )
    opposing_parties: List[Party] = Field(default_factory=list)
    multi_stage_result: Optional[Dict[str, Any]] = None
    generated_letters: Dict[str, str] = Field(default_factory=dict)

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


class AIPreferences(BaseModel):
    """User preferences for AI model selection per operation type."""

    document_analysis: str = "gpt-4o"
    letter_generation: str = "gpt-4o"
    case_chat: str = "gpt-4o"
    multi_stage_analysis: str = "gpt-4o"


class ProfileUpdate(BaseModel):
    """User profile update payload."""

    full_name: Optional[str] = None
    phone: Optional[str] = None
    firm_name: Optional[str] = None
    firm_address: Optional[str] = None
    ai_preferences: Optional[Dict[str, str]] = None
    bar_number: Optional[str] = None
    email_signature: Optional[str] = None
    default_demand_deadline: Optional[str] = None
    default_jurisdiction: Optional[str] = None


class ProfileResponse(BaseModel):
    """User profile response payload."""

    id: str
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    firm_name: Optional[str] = None
    firm_address: Optional[str] = None
    ai_preferences: Optional[Dict[str, str]] = None
    bar_number: Optional[str] = None
    email_signature: Optional[str] = None
    default_demand_deadline: Optional[str] = None
    default_jurisdiction: Optional[str] = "Florida"
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


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


# ============================================================================
# Multi-Stage Analysis Models (NEW - 2025-11-21)
# ============================================================================


class Party(BaseModel):
    """Party involved in the case."""

    name: str
    role: str  # "Client", "Opposing Party", "Contractor", "Landlord", "Tenant", etc.
    contact_info: Optional[str] = None
    first_mentioned_in: Optional[str] = None  # Source document
    is_opposing_party: bool = False
    entity_type: Optional[str] = None  # "individual", "LLC", "corporation", "government", etc.


class Event(BaseModel):
    """Chronological event in the case timeline."""

    date: Optional[Union[datetime, str]] = None  # Allow null if date is unknown
    description: str
    source_document: str
    significance: Optional[str] = None  # Why this event matters legally
    supporting_evidence: List[str] = Field(default_factory=list)


class FinancialItem(BaseModel):
    """Financial transaction or amount in the case."""

    amount: float
    description: str  # "Contract price", "Payment made", "Damages claimed"
    date: Optional[Union[datetime, str]] = None
    source_document: str
    payment_type: Optional[str] = None  # "paid", "owed", "claimed", "estimated"
    category: Optional[str] = None  # "contract_price", "payment_made", etc.


class KeyDocument(BaseModel):
    """Important document in the case."""

    document_name: str
    document_type: str  # "Contract", "Notice", "Correspondence", "Evidence"
    date: Optional[Union[datetime, str]] = None
    significance: str  # Why this document matters


class PropertyInfo(BaseModel):
    """Property details for real estate cases."""

    address: str
    property_type: Optional[str] = None  # "Residential", "Commercial"
    additional_details: Dict[str, Any] = Field(default_factory=dict)


class FactMatrix(BaseModel):
    """Structured facts extracted from case documents."""

    parties: List[Party]
    timeline: List[Event]
    financial_data: List[FinancialItem]
    key_documents: List[KeyDocument]
    preliminary_issues: List[str]  # Initial legal issues identified
    property_details: Optional[PropertyInfo] = None
    extraction_notes: Optional[str] = None  # Any caveats or quality issues


class LegalIssue(BaseModel):
    """A potential legal issue or cause of action."""

    issue_name: str  # e.g., "Implied Warranty Breach"
    category: str = "unknown"  # "contract", "tort", "statutory", "procedural"
    elements: List[str] = Field(default_factory=list)  # Legal elements that must be proven
    potential_remedies: List[str] = Field(default_factory=list)
    florida_statute_references: List[str] = Field(default_factory=list)  # e.g., ["§83.51", "Chapter 558"]
    confidence: str = "moderate"  # "strong", "moderate", "weak"


class ProceduralStep(BaseModel):
    """A procedural requirement that must be met."""

    requirement: str  # Description of what must be done
    deadline: Optional[str] = None  # When it must be done
    statute_basis: Optional[str] = None  # Legal basis for requirement
    consequences_if_missed: Optional[str] = None  # What happens if not done


class LegalIssueMap(BaseModel):
    """Map of all legal issues identified in the case."""

    primary_issues: List[LegalIssue] = Field(default_factory=list)
    secondary_issues: List[LegalIssue] = Field(default_factory=list)
    relevant_statutes: List[str] = Field(default_factory=list)  # Statute numbers to query corpus
    procedural_requirements: List[ProceduralStep] = Field(default_factory=list)
    case_complexity: str = "moderate"  # "simple" | "moderate" | "complex"
    complexity_reasoning: Optional[str] = None  # Why this complexity level
    statutory_framework: Optional[str] = None  # Summary of governing law


class IssueAnalysis(BaseModel):
    """Detailed analysis of a single legal issue."""

    issue_name: str
    legal_standard: str  # Plain English explanation of the law
    fact_application: str  # How facts meet/don't meet the standard
    statute_analysis: Optional[str] = None  # Analysis with verified statute citations
    case_law_support: Optional[str] = None  # If applicable
    remedies_available: List[str]
    procedural_requirements: Optional[str] = None  # Integrated into analysis
    confidence_level: str  # "strong" | "moderate" | "weak"
    supporting_evidence: List[str] = Field(default_factory=list)  # Key evidence supporting this claim


class RiskAssessment(BaseModel):
    """Assessment of risks and challenges."""

    major_risks: List[str]
    risk_mitigation_steps: List[str]
    statute_of_limitations_concerns: Optional[str] = None
    evidence_gaps: List[str] = Field(default_factory=list)


class CriticalDeadline(BaseModel):
    """A critical deadline that must be met."""

    deadline_date: Optional[Union[datetime, str]] = None
    description: str
    consequence_if_missed: str
    urgency: str  # "critical", "important", "normal"
    statute_basis: Optional[str] = None


class EvidenceAssessment(BaseModel):
    """Assessment of evidence strength."""

    strong_evidence: List[str]
    weak_evidence: List[str]
    missing_evidence: List[str]
    overall_strength: str  # "strong", "moderate", "weak"


class DeepAnalysis(BaseModel):
    """Comprehensive legal analysis of all identified issues."""

    issue_analyses: List[IssueAnalysis]
    risk_assessment: RiskAssessment
    deadline_tracking: List[CriticalDeadline]
    evidence_strength: EvidenceAssessment
    overall_case_strength: str  # "strong", "moderate", "weak"
    key_strengths: List[str] = Field(default_factory=list)
    key_challenges: List[str] = Field(default_factory=list)
    # Case viability assessment
    is_viable: bool = Field(default=True, description="Whether the case has sufficient legal merit to pursue")
    viability_reasoning: Optional[str] = Field(
        default=None, description="Explanation for the viability assessment, especially if not viable"
    )
    recommend_demand_letter: bool = Field(
        default=True, description="Whether a demand letter is recommended as a next step"
    )


class LetterStructure(BaseModel):
    """Guidance for how to structure the findings letter."""

    style: str  # "simple_bullets" | "numbered_findings" | "hybrid"
    intro: str  # "Here are the key points of our analysis:" OR "Key Findings"
    issue_format: str  # "bullet_paragraphs" | "numbered_sections_with_headers" | "bullets_with_subheadings"
    reasoning: Optional[str] = None  # Why this structure was chosen


class MultiStageAnalysisResult(BaseModel):
    """Complete result from multi-stage analysis pipeline."""

    fact_matrix: FactMatrix
    issue_map: LegalIssueMap
    deep_analysis: DeepAnalysis
    letter_structure: LetterStructure
    verified_statutes: List[Dict[str, Any]] = Field(default_factory=list)  # From statute service
    processing_time_seconds: float
    stage_timings: Dict[str, float] = Field(default_factory=dict)  # Time per stage
    opposing_parties: List[Party] = Field(default_factory=list)


class CompletenessReport(BaseModel):
    """Report on letter completeness."""

    issues_addressed: List[str]
    issues_missing: List[str]
    statutes_cited: List[str]
    statutes_missing: List[str]
    completeness_score: float  # 0-1
    recommendation: str  # "complete" | "needs_revision"
    warnings: List[str] = Field(default_factory=list)
