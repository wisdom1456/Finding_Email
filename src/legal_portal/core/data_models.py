from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, validator

from legal_portal.core.constants import DEFAULT_JURISDICTION, DEFAULT_MODEL, FALLBACK_MODEL

# Re-export moved models for backward compatibility
from legal_portal.core.models.enums import *  # noqa: F401,F403
from legal_portal.core.models.party_models import *  # noqa: F401,F403
from legal_portal.core.models.letter_models import *  # noqa: F401,F403
from legal_portal.core.models.document_models import *  # noqa: F401,F403
from legal_portal.core.models.analysis_models import *  # noqa: F401,F403


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


class ChatMessageRequest(BaseModel):
    """API request payload for chatting about a case."""

    case_id: Optional[str] = None  # Optional for streaming endpoint (gets case from analysis_id)
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

    @validator("document", pre=True)
    def reject_boolean_document(cls, v):
        """Reject boolean values in document name (from LLM/JSONB)."""
        if isinstance(v, bool):
            return "Unknown Document"
        return v

    @validator("document_id", pre=True)
    def reject_boolean_document_id(cls, v):
        """Reject boolean values in document_id."""
        if isinstance(v, bool):
            return None
        return v
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
    main_letter: str = Field(description="HTML content of the generated findings email")
    main_letter_with_citations: Optional[str] = Field(
        default=None, description="HTML content of the findings email with citations"
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
    generated_letters: Dict[str, Any] = Field(default_factory=dict)

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
    """User preferences for AI model selection and document handling."""

    document_analysis: str = FALLBACK_MODEL
    letter_generation: str = DEFAULT_MODEL
    case_chat: str = FALLBACK_MODEL
    multi_stage_analysis: str = DEFAULT_MODEL
    blacklisted_documents: List[str] = Field(default_factory=list)

    # Document processing preferences
    auto_skip_failed: bool = False
    max_retry_attempts: int = 2
    chunk_max_tokens: int = 50000


class ReasoningConfig(BaseModel):
    """Reasoning effort settings for different operations (GPT-5 family)."""

    document_analysis: str = "none"
    letter_generation: str = "low"
    case_chat: str = "none"
    multi_stage_analysis: str = "medium"


class VerbosityConfig(BaseModel):
    """Verbosity settings for different operations (GPT-5 family)."""

    document_analysis: str = "medium"
    letter_generation: str = "high"
    case_chat: str = "low"
    multi_stage_analysis: str = "medium"


class StageProgress(BaseModel):
    """Progress information for a specific analysis stage."""

    id: str  # 'doc_summary', 'fact_matrix', 'issue_mapping', 'deep_analysis'
    name: str
    status: Literal["pending", "active", "completed", "error"]
    progress: int = 0  # 0-100 within stage
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    extracted: Optional[dict] = None  # {"type": "parties", "count": 4, "preview": [...]}


class DocumentProgress(BaseModel):
    """Progress information for an individual document."""

    id: str
    name: str
    status: Literal["pending", "processing", "completed", "error"]


class StatsProgress(BaseModel):
    """Real-time statistics for the analysis process."""

    elapsed_seconds: float
    estimated_remaining: Optional[float] = None
    tokens_used: int = 0
    model: str = DEFAULT_MODEL


class EnhancedProgressEvent(BaseModel):
    """Enriched progress event for the AI Command Center."""

    type: Literal["progress", "stage", "document", "stats", "completed", "error", "stream"]
    timestamp: str

    # Legacy fields (kept for backwards compatibility)
    message: Optional[str] = None
    phase: Optional[str] = None
    percent: Optional[int] = None
    docs_processed: Optional[List[str]] = None
    sub_step: Optional[str] = None

    # New structured fields
    stage: Optional[StageProgress] = None
    document: Optional[DocumentProgress] = None
    stats: Optional[StatsProgress] = None

    # For streaming responses
    token: Optional[str] = None
    stream_id: Optional[str] = None


class ProfileUpdate(BaseModel):
    """User profile update payload."""

    full_name: Optional[str] = None
    phone: Optional[str] = None
    firm_name: Optional[str] = None
    firm_address: Optional[str] = None
    ai_preferences: Optional[AIPreferences] = None
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
    ai_preferences: Optional[AIPreferences] = None
    bar_number: Optional[str] = None
    email_signature: Optional[str] = None
    default_demand_deadline: Optional[str] = None
    default_jurisdiction: Optional[str] = DEFAULT_JURISDICTION
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
    model_used: str = DEFAULT_MODEL

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


class MultiStageAnalysisResult(BaseModel):
    """Complete result from multi-stage analysis pipeline."""

    fact_matrix: FactMatrix
    issue_map: LegalIssueMap
    deep_analysis: DeepAnalysis
    letter_structure: LetterStructure
    gap_analysis: Optional["GapAnalysisResult"] = Field(
        default=None, description="Gap and inconsistency analysis"
    )
    verified_statutes: List[Dict[str, Any]] = Field(default_factory=list)  # From statute service
    processing_time_seconds: float
    stage_timings: Dict[str, float] = Field(default_factory=dict)  # Time per stage
    opposing_parties: List[Party] = Field(default_factory=list)
    original_documents: Optional[Dict[str, str]] = None  # NEW: Store raw content for letter generation
    document_registry: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Authoritative document registry with authority tiers/execution metadata.",
    )

