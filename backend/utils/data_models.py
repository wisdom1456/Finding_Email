"""
Data models for the Legal Document Analysis Portal.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# Enums
class DocumentType(str, Enum):
    """Type of document being processed."""

    INTAKE_FORM = "intake_form"
    CASE_DOCUMENT = "case_document"


class FileType(str, Enum):
    """Type of file format."""

    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    EML = "eml"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


# Basic data models
class FileMetadata(BaseModel):
    """Metadata for processed files."""

    filename: str
    size: int
    created_at: datetime = Field(default_factory=datetime.now)


class ProcessedDocument(BaseModel):
    """Represents a processed document."""

    file_name: str
    content: str
    document_type: DocumentType
    file_type: Optional[FileType] = None
    metadata: Optional[FileMetadata] = None


class SavedDocument(BaseModel):
    """Represents a saved document."""

    file_path: str
    original_filename: str
    document_type: DocumentType
    metadata: Optional[FileMetadata] = None


class AnalysisError(BaseModel):
    """Represents an error during analysis."""

    source: str
    file_name: Optional[str] = None
    error_message: str
    details: Optional[str] = None


class AIAnalysisError(Exception):
    """Exception raised for AI analysis errors."""


class MediaProcessingError(BaseModel):
    """Error during media processing."""

    source: str
    file_name: str
    error_message: str


class TranscriptedMedia(BaseModel):
    """Transcripted audio/video content."""

    file_name: str
    transcript: str
    duration: Optional[float] = None


class VideoInsight(BaseModel):
    """Video analysis insights."""

    file_name: str
    insights: str
    timestamp: datetime = Field(default_factory=datetime.now)


class AnalyzedDocument(BaseModel):
    """Analyzed case document."""

    file_name: str
    filename: Optional[str] = None  # Alias for file_name for backward compatibility
    document_type: Optional[str] = None
    inferred_title: Optional[str] = None
    analysis: Optional[str] = None
    summary: Optional[str] = None
    key_information: Optional[str] = None
    relevance_to_case: Optional[str] = None
    key_points: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None

    def model_post_init(self, __context: Any) -> None:
        """Post-init to handle backward compatibility."""
        # Ensure filename matches file_name for backward compatibility
        if not self.filename and self.file_name:
            self.filename = self.file_name
        elif self.filename and not self.file_name:
            self.file_name = self.filename


class IntakeAnalysis(BaseModel):
    """Analysis of intake form."""

    summary: str
    key_facts: List[str] = Field(default_factory=list)
    legal_issues: List[str] = Field(default_factory=list)


class PartyInvolved(BaseModel):
    """Party involved in the case."""

    name: str
    role: str


class EnhancedIntakeAnalysis(BaseModel):
    """Enhanced analysis of intake form."""

    client_name: str
    attorney_name: str
    case_summary: str
    case_type: str
    urgency_level: str
    client_priorities: List[str] = Field(default_factory=list)
    desired_outcomes: List[str] = Field(default_factory=list)
    key_facts: List[str] = Field(default_factory=list)
    parties_involved: List[PartyInvolved] = Field(default_factory=list)
    financial_impact: str
    legal_claims: List[str] = Field(default_factory=list)

    # Legacy fields for backward compatibility
    summary: Optional[str] = None
    legal_issues: Optional[List[str]] = None
    timeline: Optional[str] = None
    parties: Optional[List[str]] = None

    def model_post_init(self, __context: Any) -> None:
        """Post-init to handle backward compatibility."""
        # Map case_summary to summary for backward compatibility
        if not self.summary and self.case_summary:
            self.summary = self.case_summary

        # Map legal_claims to legal_issues for backward compatibility
        if not self.legal_issues and self.legal_claims:
            self.legal_issues = self.legal_claims

        # Map parties_involved to parties for backward compatibility
        if not self.parties and self.parties_involved:
            self.parties = [party.name for party in self.parties_involved]


class LegalAssessment(BaseModel):
    """Legal assessment of the case."""

    case_type: str
    claim_viability: str
    overall_evidence_strength: str
    potential_challenges: str
    recommended_actions: str
    demand_letter_appropriate: (
        bool  # Fixed: Changed from str to bool to match AI output
    )
    urgency_assessment: str


class DemandLetterEvaluation(BaseModel):
    """Evaluation for demand letter."""

    is_appropriate: bool  # Fixed: Changed from str to bool to match AI output
    reasoning: str
    potential_outcomes: List[str] = Field(default_factory=list)
    relevant_statutes: List[str] = Field(default_factory=list)


class FinalAnalysis(BaseModel):
    """Final analysis result."""

    case_summary: str
    recommendations: str
    next_steps: List[str] = Field(default_factory=list)


class CaseAnalysisResult(BaseModel):
    """Complete case analysis result."""

    intake_analysis: Optional[EnhancedIntakeAnalysis] = None
    analyzed_documents: List[AnalyzedDocument] = Field(default_factory=list)
    legal_assessment: Optional[LegalAssessment] = None
    demand_letter_evaluation: Optional[DemandLetterEvaluation] = None
    final_analysis: Optional[FinalAnalysis] = None
    findings_letter_content: Optional[FindingsLetterContent] = None
    transcripted_media: List[TranscriptedMedia] = Field(default_factory=list)
    video_insights: List[VideoInsight] = Field(default_factory=list)
    errors: List[AnalysisError] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Analysis result for testing and backward compatibility."""

    intake_analysis: Optional[IntakeAnalysis] = None
    analyzed_documents: List[AnalyzedDocument] = Field(default_factory=list)
    transcripted_media: List[TranscriptedMedia] = Field(default_factory=list)
    video_insights: List[VideoInsight] = Field(default_factory=list)
    errors: List[AnalysisError] = Field(default_factory=list)


# Cost tracking models
class ServiceCost(BaseModel):
    """Cost for a specific service."""

    service_name: str
    cost: float
    details: Optional[str] = None
    operation_type: Optional[str] = None
    units_consumed: Optional[int] = None
    unit_type: Optional[str] = None
    rate_per_unit: Optional[float] = None
    total_cost: Optional[float] = None
    file_name: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        """Post-init to handle backward compatibility."""
        if self.total_cost is None:
            self.total_cost = self.cost
        if self.units_consumed is None:
            self.units_consumed = 0
        if self.operation_type is None:
            self.operation_type = "N/A"


class ActualCosts(BaseModel):
    """Actual costs incurred."""

    total_actual_cost: float
    service_costs: List[ServiceCost] = Field(default_factory=list)
    document_analysis_costs: List[ServiceCost] = Field(default_factory=list)
    media_processing_costs: List[ServiceCost] = Field(default_factory=list)


class CostEstimate(BaseModel):
    """Cost estimate for processing."""

    estimated_cost: float
    breakdown: Dict[str, float] = Field(default_factory=dict)


class CostSummary(BaseModel):
    """Summary of costs."""

    case_id: str
    cost_estimate: Optional[CostEstimate] = None
    actual_costs: Optional[ActualCosts] = None
    cost_variance: Optional[float] = None
    cost_variance_percentage: Optional[float] = None


# Email generation models
class SectionPlan(BaseModel):
    """Plan for generating a specific section of the email."""

    number: int
    header: str
    key_points: List[str] = Field(default_factory=list)
    emphasis_items: Dict[str, str] = Field(default_factory=dict)
    content_requirements: List[str] = Field(default_factory=list)
    legal_citation: Optional[str] = None


class EmailStructurePlan(BaseModel):
    """Overall structure plan for email generation."""

    subject_line: str
    greeting: str
    sections: List[SectionPlan]
    closing: str
    case_context: Dict[str, Any] = Field(default_factory=dict)


class GenerationContext(BaseModel):
    """Context tracking for email generation process."""

    greeting_given: bool = False
    closing_given: bool = False
    client_name_mentioned: bool = False
    section_numbers_used: List[int] = Field(default_factory=list)
    current_section: Optional[str] = None


class GeneratedLetter(BaseModel):
    """Final generated letter with all sections."""

    executive_summary: str = ""
    background_summary: str = ""
    analysis_and_position: str = ""
    media_summary: str = ""
    video_analysis_appendix: str = ""
    strengths: str = ""
    challenges: str = ""
    recommendations: str = ""
    next_steps: str = ""
    closing_paragraph: str = ""


class LegacyGeneratedLetter(BaseModel):
    """Legacy generated letter content (for backward compatibility)."""

    subject: str
    body: str
    attachments: List[str] = Field(default_factory=list)


class EnhancedFindingsLetter(BaseModel):
    """Enhanced findings letter."""

    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QualityScore(BaseModel):
    """Quality assessment score."""

    overall_score: float
    details: Dict[str, float] = Field(default_factory=dict)


# Video processing models
class CriminalEvidenceCategory(str, Enum):
    """Categories for criminal evidence."""

    DRIVING_PATTERN_REASON_STOP = "Driving Pattern & Reason for Stop"
    EMERGENCY_LIGHTS_PULLOVER = "Emergency Lights & Vehicle Pullover"
    INITIAL_ROADSIDE_APPROACH = "Initial Roadside Approach & Observations"
    PRELIMINARY_QUESTIONING = "Preliminary Questioning & Admissions"
    EXIT_ORDER_PRE_TEST = "Exit Order & Pre-Test Observations"
    FIELD_SOBRIETY_TESTS = "Field Sobriety Tests"
    PORTABLE_BREATH_TEST = "Portable Breath Test"
    ARREST_DECISION_HANDCUFFING = "Arrest Decision & Handcuffing"
    MIRANDA_WARNINGS = "Miranda Warnings & Custodial Interrogation"
    IMPLIED_CONSENT_CHEMICAL_TEST = "Implied Consent & Chemical Test Request"
    CHEMICAL_TEST_ADMINISTRATION = "Chemical Test Administration"
    TRANSPORT_TO_STATION = "Transport to Station/Jail"
    BOOKING_PROCESSING = "Booking & Processing"
    RIGHT_TO_COUNSEL = "Right to Counsel & Phone Calls"
    POST_BOOKING_OBSERVATION = "Post-Booking Observation & Medical"
    VEHICLE_TOW_INVENTORY = "Vehicle Tow & Inventory Search"


class TimeRange(BaseModel):
    """Time range for video analysis."""

    start_time: str
    end_time: str
    confidence: float = 0.5


class CriminalEvidenceItem(BaseModel):
    """Criminal evidence item from video analysis."""

    category: CriminalEvidenceCategory
    time_range: TimeRange
    description: str
    key_observations: List[str] = Field(default_factory=list)
    legal_significance: str = ""
    constitutional_issues: List[str] = Field(default_factory=list)
    evidence_strength: str = "moderate"


class CriminalVideoAnalysis(BaseModel):
    """Complete criminal video analysis."""

    evidence_items: List[CriminalEvidenceItem] = Field(default_factory=list)
    timeline_summary: str = ""
    constitutional_compliance_overview: str = ""
    missing_categories: List[CriminalEvidenceCategory] = Field(default_factory=list)


class EnhancedVideoInsight(BaseModel):
    """Enhanced video insights."""

    file_name: str
    insights: Any
    transcript: str = ""
    metadata: Optional[FileMetadata] = None
    labels: List[str] = Field(default_factory=list)
    objects: List[str] = Field(default_factory=list)
    text_annotations: List[str] = Field(default_factory=list)
    duration: Optional[float] = None
    confidence: Optional[float] = None
    criminal_analysis: Optional[CriminalVideoAnalysis] = None
    is_criminal_case: bool = False


class FindingsLetterContent(BaseModel):
    """Complete structured content for the findings letter generated by AI in JSON mode."""

    factual_summary: str = Field(
        description="A comprehensive factual summary of the case including client information, case type, and key circumstances"
    )
    legal_analysis: str = Field(
        description="Detailed legal analysis including Florida law references, claim viability, and evidence strength assessment"
    )
    strengths_of_case: str = Field(
        description="Analysis of the strongest aspects of the client's position with specific supporting evidence"
    )
    challenges_and_risks: str = Field(
        description="Potential challenges, weaknesses, or risks that could impact the case outcome"
    )
    recommended_next_steps: str = Field(
        description="Specific actionable recommendations for how to proceed with the case"
    )
    demand_letter_analysis: str = Field(
        description="Assessment of whether a demand letter is appropriate and potential outcomes"
    )


# Additional helper models
class CaseResults(BaseModel):
    """Results from case processing."""

    case_id: str
    analysis_result: CaseAnalysisResult
    generated_documents: Dict[str, str] = Field(default_factory=dict)
    processing_time: Optional[float] = None
