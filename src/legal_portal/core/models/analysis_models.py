"""Analysis-related domain models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

from legal_portal.core.models.enums import (
    CaseRecommendationCategory,
    ConfidenceLevel,
    GapCategory,
    GapSeverity,
    RecommendedLetterType,
)

__all__ = [
    "Party",
    "Event",
    "FinancialItem",
    "KeyDocument",
    "PropertyInfo",
    "FactMatrix",
    "LegalIssue",
    "ProceduralStep",
    "LegalIssueMap",
    "IssueAnalysis",
    "RiskAssessment",
    "CriticalDeadline",
    "EvidenceAssessment",
    "DeepAnalysis",
    "CaseRecommendation",
    "GapItem",
    "BatchEvidence",
    "BatchFinding",
    "BatchGapReport",
    "GapAnalysisResult",
]


class _IgnoreExtra(BaseModel):
    """Base model that tolerates extra fields from stored LLM output."""

    model_config = {"extra": "ignore"}


class Party(_IgnoreExtra):
    """Party involved in the case."""

    name: str
    role: str  # "Client", "Opposing Party", "Contractor", "Landlord", "Tenant", etc.
    contact_info: Optional[str] = None
    first_mentioned_in: Optional[str] = None  # Source document
    is_opposing_party: bool = False
    entity_type: Optional[str] = None  # "individual", "LLC", "corporation", "government", etc.


class Event(_IgnoreExtra):
    """Chronological event in the case timeline."""

    date: Optional[Union[datetime, str]] = None  # Allow null if date is unknown
    description: str
    source_document: str = "Unknown"
    significance: Optional[str] = None  # Why this event matters legally
    supporting_evidence: List[str] = Field(default_factory=list)

    @field_validator("source_document", mode="before")
    @classmethod
    def _coerce_source_document(cls, v: Any) -> str:
        return str(v) if v is not None else "Unknown"


class FinancialItem(_IgnoreExtra):
    """Financial transaction or amount in the case."""

    amount: float
    description: str  # "Contract price", "Payment made", "Damages claimed"
    date: Optional[Union[datetime, str]] = None
    source_document: str = "Unknown"
    payment_type: Optional[str] = None  # "paid", "owed", "claimed", "estimated"
    category: Optional[str] = None  # "contract_price", "payment_made", etc.

    @field_validator("source_document", mode="before")
    @classmethod
    def _coerce_source_document(cls, v: Any) -> str:
        return str(v) if v is not None else "Unknown"


class KeyDocument(_IgnoreExtra):
    """Important document in the case."""

    document_name: str
    document_type: str  # "Contract", "Notice", "Correspondence", "Evidence"
    date: Optional[Union[datetime, str]] = None
    significance: str  # Why this document matters


class PropertyInfo(_IgnoreExtra):
    """Property details for real estate cases."""

    address: str
    property_type: Optional[str] = None  # "Residential", "Commercial"
    additional_details: Dict[str, Any] = Field(default_factory=dict)


class FactMatrix(_IgnoreExtra):
    """Structured facts extracted from case documents."""

    parties: List[Party]
    timeline: List[Event]
    financial_data: List[FinancialItem]
    key_documents: List[KeyDocument]
    preliminary_issues: List[str]  # Initial legal issues identified
    property_details: Optional[PropertyInfo] = None
    extraction_notes: Optional[str] = None  # Any caveats or quality issues


class LegalIssue(_IgnoreExtra):
    """A potential legal issue or cause of action."""

    issue_name: str  # e.g., "Implied Warranty Breach"
    category: str = "unknown"  # "contract", "tort", "statutory", "procedural"
    elements: List[str] = Field(default_factory=list)  # Legal elements that must be proven
    potential_remedies: List[str] = Field(default_factory=list)
    florida_statute_references: List[str] = Field(default_factory=list)  # e.g., ["§83.51", "Chapter 558"]
    confidence: str = "moderate"  # "strong", "moderate", "weak"


class ProceduralStep(_IgnoreExtra):
    """A procedural requirement that must be met."""

    requirement: str  # Description of what must be done
    deadline: Optional[str] = None  # When it must be done
    statute_basis: Optional[str] = None  # Legal basis for requirement
    consequences_if_missed: Optional[str] = None  # What happens if not done


class LegalIssueMap(_IgnoreExtra):
    """Map of all legal issues identified in the case."""

    primary_issues: List[LegalIssue] = Field(default_factory=list)
    secondary_issues: List[LegalIssue] = Field(default_factory=list)
    relevant_statutes: List[str] = Field(default_factory=list)  # Statute numbers to query corpus
    procedural_requirements: List[ProceduralStep] = Field(default_factory=list)
    case_complexity: str = "moderate"  # "simple" | "moderate" | "complex"
    complexity_reasoning: Optional[str] = None  # Why this complexity level
    statutory_framework: Optional[str] = None  # Summary of governing law


class IssueAnalysis(_IgnoreExtra):
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


class RiskAssessment(_IgnoreExtra):
    """Assessment of risks and challenges."""

    major_risks: List[str]
    risk_mitigation_steps: List[str]
    statute_of_limitations_concerns: Optional[str] = None
    evidence_gaps: List[str] = Field(default_factory=list)


class CriticalDeadline(_IgnoreExtra):
    """A critical deadline that must be met."""

    deadline_date: Optional[Union[datetime, str]] = None
    description: str
    consequence_if_missed: str
    urgency: str  # "critical", "important", "normal"
    statute_basis: Optional[str] = None


class EvidenceAssessment(_IgnoreExtra):
    """Assessment of evidence strength."""

    strong_evidence: List[str]
    weak_evidence: List[str]
    missing_evidence: List[str]
    overall_strength: str  # "strong", "moderate", "weak"


class DeepAnalysis(_IgnoreExtra):
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


class CaseRecommendation(_IgnoreExtra):
    """Recommendation generated from gap analysis results."""

    category: CaseRecommendationCategory
    confidence: ConfidenceLevel
    reasoning: str = Field(description="2-3 sentences explaining the recommendation")
    next_steps: List[str] = Field(description="Action items for the attorney")
    suggested_letter_type: RecommendedLetterType
    category_display_name: str = Field(description="UI-friendly label for the category")
    category_color: str = Field(description="Color code: green/yellow/orange/red")


class GapItem(_IgnoreExtra):
    """A specific gap or issue identified in the case."""

    gap_id: str = Field(description="Unique identifier for this gap")
    category: GapCategory = Field(description="Type of gap")
    severity: GapSeverity = Field(description="Severity level")
    title: str = Field(description="Brief description of the gap")
    description: str = Field(description="Detailed explanation of the gap")
    affected_issue: Optional[str] = Field(default=None, description="Which legal issue is affected")
    related_documents: List[str] = Field(
        default_factory=list, description="Documents related to this gap"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Steps to address this gap"
    )
    impact_on_case: str = Field(description="How this gap affects case viability or strategy")


class BatchEvidence(_IgnoreExtra):
    """Evidence category detected in a single map-phase batch."""

    category: str = Field(description="E.g., 'executed_contracts', 'payment_receipts'")
    document_ids: List[str] = Field(default_factory=list, description="Database UUIDs")
    status: str = Field(description="'present' | 'missing' | 'incomplete'")
    severity: Optional[str] = Field(
        default=None, description="Only for missing/incomplete: 'critical'/'high'/'medium'/'low'"
    )
    detail: str = Field(description="1-2 sentence explanation")


class BatchFinding(_IgnoreExtra):
    """A gap, contradiction, or concern found in a single map-phase batch."""

    category: str = Field(description="Maps to GapCategory values")
    severity: str = Field(description="'critical' / 'high' / 'medium' / 'low'")
    title: str
    description: str
    document_ids: List[str] = Field(default_factory=list, description="Database UUIDs of related docs")
    affected_issue: Optional[str] = None
    cross_batch_uncertain: bool = Field(
        default=False, description="May be resolved by another batch"
    )


class BatchGapReport(_IgnoreExtra):
    """Structured output from a single map-phase batch."""

    batch_id: str
    batch_label: str
    document_count: int
    evidence: List[BatchEvidence] = Field(
        default_factory=list, description="What's present, missing, or incomplete"
    )
    findings: List[BatchFinding] = Field(
        default_factory=list, description="Gaps, contradictions, concerns"
    )
    cross_batch_flags: List[str] = Field(
        default_factory=list,
        description="Max 5 structured flags, format: 'CHECK_BATCH:{label} FOR:{category}'",
    )


class GapAnalysisResult(_IgnoreExtra):
    """Complete gap analysis result."""

    total_gaps: int = Field(description="Total number of gaps identified")
    critical_count: int = Field(default=0, description="Number of critical gaps")
    high_count: int = Field(default=0, description="Number of high severity gaps")
    medium_count: int = Field(default=0, description="Number of medium severity gaps")
    low_count: int = Field(default=0, description="Number of low severity gaps")
    gaps_by_category: Dict[str, List[GapItem]] = Field(
        default_factory=dict, description="Gaps organized by category"
    )
    overall_completeness_score: float = Field(
        ge=0.0, le=100.0, description="Overall completeness score (0-100)"
    )
    attorney_summary: str = Field(
        description="Executive summary for attorney about case completeness"
    )
    reconciliation_notes: List[str] = Field(
        default_factory=list,
        description=(
            "System-generated reconciliation notes explaining deterministic post-processing "
            "adjustments applied after model output."
        ),
    )
    recommendation: Optional[CaseRecommendation] = Field(
        default=None, description="Case recommendation based on gap analysis"
    )
    map_reduce_metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Provenance metadata from map-reduce pipeline"
    )
    analysis_quality: Optional[str] = Field(
        default=None,
        description=(
            "Pipeline quality: 'full' | 'degraded_partial' | 'degraded_merge' | "
            "'fallback_single_pass' | None (single-pass path)"
        ),
    )
