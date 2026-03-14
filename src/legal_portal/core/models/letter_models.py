"""Letter-related domain models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from legal_portal.core.models.enums import LetterType  # noqa: F401

__all__ = [
    "DemandLetterEvaluation",
    "DemandLetterRequest",
    "EvidenceAnchorV1",
    "ClaimPlanV1",
    "DemandSpecV1",
    "LetterStrategyV1",
    "LetterStructure",
    "CompletenessReport",
    "LetterValidationWarning",
    "LetterValidationResult",
]


class DemandLetterEvaluation(BaseModel):
    """Determines whether a demand letter is an appropriate next step."""

    is_appropriate: bool = True
    reasoning: str = ""
    potential_outcomes: List[str] = Field(default_factory=list)
    relevant_statutes: List[str] = Field(default_factory=list)


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


class EvidenceAnchorV1(BaseModel):
    """Evidence anchor used to connect a claim to specific facts."""

    anchor_type: str = Field(
        description="Type of evidence anchor: document | date | amount | communication | party"
    )
    summary: str = Field(description="Short factual anchor summary")
    source_document: Optional[str] = Field(default=None, description="Document title or filename")
    source_date: Optional[str] = Field(default=None, description="Date tied to this anchor")
    amount: Optional[float] = Field(default=None, description="Amount tied to this anchor, if any")


class ClaimPlanV1(BaseModel):
    """Prioritized claim plan for a generated letter."""

    theory: str = Field(description="Claim or legal theory name")
    priority: int = Field(description="Priority rank (1 = strongest)")
    rationale: str = Field(description="Why this theory is prioritized")
    supporting_anchors: List[EvidenceAnchorV1] = Field(default_factory=list)


class DemandSpecV1(BaseModel):
    """Demand-letter specificity package."""

    targets: List[str] = Field(default_factory=list, description="Entities or individuals targeted")
    amount_mode: str = Field(
        default="tbd",
        description="fixed | tbd",
    )
    deadline: str = Field(default="10 business days")
    accounting_request: str = Field(
        default="Provide a written accounting of funds received and how they were used."
    )
    cure_ladder: List[str] = Field(default_factory=list, description="Escalation sequence if no compliance")
    preservation_language: str = Field(
        default="Preserve all records, communications, and accounting materials related to this matter."
    )


class LetterStrategyV1(BaseModel):
    """Structured pre-draft strategy object for findings and demand letters."""

    case_summary: str
    ranked_theories: List[ClaimPlanV1] = Field(default_factory=list)
    timeline_highlights: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    uncertainty_items: List[str] = Field(default_factory=list)
    recommended_sequence: List[str] = Field(default_factory=list)
    demand_spec: Optional[DemandSpecV1] = None


class LetterStructure(BaseModel):
    """Guidance for how to structure the findings email."""

    style: str  # "structured_professional"
    intro: str  # Section headers serve as intros; can be empty string
    issue_format: str  # "bold_titled_bullet_provisions"
    reasoning: Optional[str] = None  # Why this structure was chosen


class CompletenessReport(BaseModel):
    """Report on letter completeness."""

    issues_addressed: List[str]
    issues_missing: List[str]
    statutes_cited: List[str]
    statutes_missing: List[str]
    completeness_score: float  # 0-1
    recommendation: str  # "complete" | "needs_revision"
    warnings: List[str] = Field(default_factory=list)


class LetterValidationWarning(BaseModel):
    """A single validation warning for letter content."""

    warning_type: str = Field(description="Type of warning: amount_mismatch, date_mismatch, unhedged_claim, etc.")
    message: str = Field(description="Human-readable warning message")
    severity: str = Field(default="warning", description="Severity: warning, error, info")
    source_context: Optional[str] = Field(default=None, description="Context from source data if available")


class LetterValidationResult(BaseModel):
    """Result of validating a generated letter against source data."""

    is_valid: bool = Field(description="Whether the letter passed all validation checks")
    warnings: List[LetterValidationWarning] = Field(
        default_factory=list, description="List of validation warnings"
    )
    validation_timestamp: datetime = Field(description="When validation was performed")
    amounts_checked: int = Field(default=0, description="Number of amounts validated")
    dates_checked: int = Field(default=0, description="Number of dates validated")
    claims_checked: int = Field(default=0, description="Number of unverifiable claims checked")
