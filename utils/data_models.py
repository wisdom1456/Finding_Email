"""
Data models for the Legal Document Analysis Portal.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

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
    file_type: FileType | None = None
    metadata: FileMetadata | None = None


class SavedDocument(BaseModel):
    """Represents a saved document."""

    file_path: str
    original_filename: str
    document_type: DocumentType
    metadata: FileMetadata | None = None


class AnalysisError(BaseModel):
    """Represents an error during analysis."""

    source: str
    file_name: str | None = None
    error_message: str
    details: str | None = None


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
    duration: float | None = None


class VideoInsight(BaseModel):
    """Video analysis insights."""

    file_name: str
    insights: str
    timestamp: datetime = Field(default_factory=datetime.now)


class AnalyzedDocument(BaseModel):
    """Analyzed case document."""

    file_name: str
    analysis: str
    key_points: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class IntakeAnalysis(BaseModel):
    """Analysis of intake form."""

    summary: str
    key_facts: list[str] = Field(default_factory=list)
    legal_issues: list[str] = Field(default_factory=list)


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
    client_priorities: list[str] = Field(default_factory=list)
    desired_outcomes: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    parties_involved: list[PartyInvolved] = Field(default_factory=list)
    financial_impact: str
    legal_claims: list[str] = Field(default_factory=list)

    # Legacy fields for backward compatibility
    summary: str | None = None
    legal_issues: list[str] | None = None
    timeline: str | None = None
    parties: list[str] | None = None

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
    demand_letter_appropriate: bool
    urgency_assessment: str


class DemandLetterEvaluation(BaseModel):
    """Evaluation for demand letter."""

    is_appropriate: bool
    reasoning: str
    potential_outcomes: list[str] = Field(default_factory=list)
    relevant_statutes: list[str] = Field(default_factory=list)


class FinalAnalysis(BaseModel):
    """Final analysis result."""

    case_summary: str
    recommendations: str
    next_steps: list[str] = Field(default_factory=list)


class CaseAnalysisResult(BaseModel):
    """Complete case analysis result."""

    intake_analysis: EnhancedIntakeAnalysis | None = None
    analyzed_documents: list[AnalyzedDocument] = Field(default_factory=list)
    legal_assessment: LegalAssessment | None = None
    demand_letter_evaluation: DemandLetterEvaluation | None = None
    final_analysis: FinalAnalysis | None = None
    transcripted_media: list[TranscriptedMedia] = Field(default_factory=list)
    video_insights: list[VideoInsight] = Field(default_factory=list)
    errors: list[AnalysisError] = Field(default_factory=list)


# Cost tracking models
class ServiceCost(BaseModel):
    """Cost for a specific service."""

    service_name: str
    cost: float
    details: str | None = None


class ActualCosts(BaseModel):
    """Actual costs incurred."""

    total_actual_cost: float
    service_costs: list[ServiceCost] = Field(default_factory=list)


class CostEstimate(BaseModel):
    """Cost estimate for processing."""

    estimated_cost: float
    breakdown: dict[str, float] = Field(default_factory=dict)


class CostSummary(BaseModel):
    """Summary of costs."""

    case_id: str
    cost_estimate: CostEstimate | None = None
    actual_costs: ActualCosts | None = None
    cost_variance: float | None = None


# Email generation models
class GeneratedLetter(BaseModel):
    """Generated letter content."""

    subject: str
    body: str
    attachments: list[str] = Field(default_factory=list)


class EnhancedFindingsLetter(BaseModel):
    """Enhanced findings letter."""

    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityScore(BaseModel):
    """Quality assessment score."""

    overall_score: float
    details: dict[str, float] = Field(default_factory=dict)


# Video processing models
class CriminalEvidenceCategory(str, Enum):
    """Categories for criminal evidence."""

    PHYSICAL_EVIDENCE = "physical_evidence"
    DOCUMENTARY = "documentary"
    TESTIMONIAL = "testimonial"


class EnhancedVideoInsight(BaseModel):
    """Enhanced video insights."""

    file_name: str
    insights: str
    categories: list[CriminalEvidenceCategory] = Field(default_factory=list)
    confidence_score: float | None = None


# Additional helper models
class CaseResults(BaseModel):
    """Results from case processing."""

    case_id: str
    analysis_result: CaseAnalysisResult
    generated_documents: dict[str, str] = Field(default_factory=dict)
    processing_time: float | None = None
