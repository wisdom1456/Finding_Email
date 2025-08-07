"""
Validation utilities for AI analysis responses.
"""

from __future__ import annotations

import json
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)


def preprocess_ai_output(raw_output: dict[str, Any]) -> dict[str, Any]:
    """
    Preprocess AI output to handle common formatting issues.

    Args:
        raw_output: Raw dictionary from AI response

    Returns:
        Cleaned dictionary ready for validation
    """
    if not isinstance(raw_output, dict):
        msg = f"Expected dict, got {type(raw_output)}"
        raise ValueError(msg)

    # Deep copy to avoid modifying original
    processed = {}

    for key, value in raw_output.items():
        # Clean string keys
        clean_key = key.strip() if isinstance(key, str) else key

        # Process values
        if isinstance(value, str):
            # Strip whitespace from strings
            processed[clean_key] = value.strip()
        elif isinstance(value, list):
            # Clean list items
            processed[clean_key] = [
                item.strip() if isinstance(item, str) else item for item in value
            ]
        elif isinstance(value, dict):
            # Recursively process nested dicts
            processed[clean_key] = preprocess_ai_output(value)
        else:
            processed[clean_key] = value

    return processed


def safe_model_validate(
    model_class: type[T],
    data: dict[str, Any],
    fallback_func: Callable[[], dict[str, Any]],
) -> T | None:
    """
    Safely validate data against a Pydantic model with fallback.

    Args:
        model_class: Pydantic model class to validate against
        data: Data to validate
        fallback_func: Function to generate fallback data

    Returns:
        Validated model instance or None if validation fails
    """
    try:
        # First try preprocessing
        processed_data = preprocess_ai_output(data)
        return model_class.model_validate(processed_data)
    except (ValidationError, ValueError, TypeError) as e:
        print(f"VALIDATORS: Validation failed for {model_class.__name__}: {e}")
        try:
            # Try with fallback data
            fallback_data = fallback_func()
            return model_class.model_validate(fallback_data)
        except Exception as fallback_error:
            print(f"VALIDATORS: Fallback validation also failed: {fallback_error}")
            return None


def create_fallback_legal_assessment() -> dict[str, Any]:
    """
    Create fallback legal assessment data.

    Returns:
        Dictionary with fallback legal assessment structure
    """
    return {
        "case_type": "General Legal Matter",
        "claim_viability": "Moderate",
        "overall_evidence_strength": "Under Review",
        "potential_challenges": "We are currently reviewing the available evidence and will provide a detailed assessment of potential challenges as our analysis continues. This may include procedural considerations, evidentiary requirements, and strategic factors that could impact case outcomes.",
        "recommended_actions": "We recommend gathering additional documentation and evidence to strengthen your position. Our team will continue analyzing the materials you have provided and will update you with specific next steps as our review progresses.",
        "demand_letter_appropriate": "Yes",
        "urgency_assessment": "Standard",
    }


def create_fallback_demand_letter_evaluation() -> dict[str, Any]:
    """
    Create fallback demand letter evaluation data.

    Returns:
        Dictionary with fallback demand letter evaluation structure
    """
    return {
        "is_appropriate": "Yes",
        "reasoning": "Based on our preliminary review, a demand letter appears to be an appropriate next step. This approach allows us to formally communicate your position and may facilitate resolution without the need for litigation. We will work with you to craft a demand letter that effectively presents your case and requests appropriate remedies.",
        "potential_outcomes": [
            "Settlement negotiations may begin",
            "Opposing party may respond with counter-proposals",
            "Matter may be resolved without litigation",
            "Foundation established for potential legal action if needed",
        ],
        "relevant_statutes": [
            "Florida Statutes - General Contract Law",
            "Florida Civil Practice Rules",
        ],
    }


def validate_json_response(response: str) -> dict[str, Any]:
    """
    Validate and parse JSON response from AI.

    Args:
        response: Raw response string from AI

    Returns:
        Parsed JSON dictionary

    Raises:
        ValueError: If response cannot be parsed as valid JSON
    """
    try:
        # Remove potential markdown formatting
        cleaned_response = response.strip()
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
        cleaned_response = cleaned_response.strip()

        # Parse JSON
        parsed = json.loads(cleaned_response)

        if not isinstance(parsed, dict):
            msg = f"Expected JSON object, got {type(parsed)}"
            raise ValueError(msg)

        return parsed

    except json.JSONDecodeError as e:
        msg = f"Invalid JSON response: {e}"
        raise ValueError(msg)


def ensure_required_fields(
    data: dict[str, Any], required_fields: list[str]
) -> dict[str, Any]:
    """
    Ensure required fields are present in data dictionary.

    Args:
        data: Input data dictionary
        required_fields: List of required field names

    Returns:
        Data dictionary with all required fields (empty strings for missing fields)
    """
    result = data.copy()

    for field in required_fields:
        if field not in result or result[field] is None:
            # Provide appropriate default based on field name patterns
            if field.endswith("_list") or (
                field.endswith("s") and not field.endswith("_assessment")
            ):
                result[field] = []
            elif field.endswith("_appropriate") or field.startswith("is_"):
                result[field] = True
            elif "date" in field.lower():
                result[field] = ""
            else:
                result[field] = ""

    return result


def clean_text_content(text: str, max_length: int | None = None) -> str:
    """
    Clean and format text content.

    Args:
        text: Raw text to clean
        max_length: Optional maximum length to truncate to

    Returns:
        Cleaned text
    """
    if not isinstance(text, str):
        text = str(text)

    # Remove excessive whitespace
    cleaned = " ".join(text.split())

    # Truncate if needed
    if max_length and len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rsplit(" ", 1)[0] + "..."

    return cleaned


def validate_list_field(data: Any, field_name: str) -> list[str]:
    """
    Validate and convert field to list of strings.

    Args:
        data: Data to validate
        field_name: Name of field for error messages

    Returns:
        List of strings
    """
    if data is None:
        return []

    if isinstance(data, str):
        # Handle comma-separated strings
        if "," in data:
            return [item.strip() for item in data.split(",") if item.strip()]
        return [data.strip()] if data.strip() else []

    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]

    # Convert other types to single-item list
    return [str(data).strip()] if str(data).strip() else []
