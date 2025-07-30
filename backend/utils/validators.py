from typing import Dict, Any
from pydantic import ValidationError
from utils.data_models import IntakeAnalysis, CaseAnalysis

def validate_intake_analysis(data: Dict[str, Any]) -> IntakeAnalysis:
    """
    Validates the raw dictionary for intake form analysis.
    """
    try:
        return IntakeAnalysis(**data)
    except ValidationError as e:
        # Add logging here for production
        print(f"IntakeAnalysis validation error: {e}")
        raise ValueError("Failed to validate intake analysis data.") from e

def validate_case_analysis(data: Dict[str, Any]) -> CaseAnalysis:
    """
    Validates the raw dictionary for case document analysis.
    """
    try:
        return CaseAnalysis(**data)
    except ValidationError as e:
        # Add logging here for production
        print(f"CaseAnalysis validation error: {e}")
        raise ValueError("Failed to validate case analysis data.") from e
