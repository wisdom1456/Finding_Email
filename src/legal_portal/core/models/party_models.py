"""Party-related domain models."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

__all__ = [
    "PartyInvolved",
    "EnhancedIntakeAnalysis",
]


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

    @validator("client_name", "attorney_name", "case_summary", "case_type", "urgency_level", pre=True)
    def reject_boolean_strings(cls, v):
        """Reject boolean values in string fields."""
        if isinstance(v, bool):
            return None
        return v
    client_priorities: List[str] = Field(default_factory=list)
    desired_outcomes: List[str] = Field(default_factory=list)
    key_facts: List[str] = Field(default_factory=list)
    parties_involved: List[PartyInvolved] = Field(default_factory=list)
    financial_impact: Optional[str] = None
    legal_claims: List[str] = Field(default_factory=list)
    timeline_events: List[Dict[str, Any]] = Field(default_factory=list)
