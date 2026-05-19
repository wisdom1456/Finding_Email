"""Streaming analysis parse helpers extracted from analysis_core route module.

Pure functions for parsing streaming analysis markdown content, extracting
embedded JSON, currency parsing, and section extraction.
"""

import json
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# JSON schema for structured extraction via API (strict mode)
_EXTRACTION_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "case_structured_data",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "practice_area": {"type": "string"},
                "case_strength": {"type": "string"},
                "recommended_letter_type": {"type": "string"},
                "parties": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "entity_type": {"type": "string"},
                        },
                        "required": ["name", "role", "entity_type"],
                        "additionalProperties": False,
                    },
                },
                "key_dates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                            "event": {"type": "string"},
                        },
                        "required": ["date", "event"],
                        "additionalProperties": False,
                    },
                },
                "primary_issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "category": {"type": "string"},
                            "strength": {"type": "string"},
                            "statutes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["name", "category", "strength", "statutes"],
                        "additionalProperties": False,
                    },
                },
                "financial_summary": {
                    "type": "object",
                    "properties": {
                        "total_claimed": {"type": "string"},
                        "documented_damages": {"type": "string"},
                        "financial_items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "amount": {"type": "string"},
                                    "description": {"type": "string"},
                                    "category": {"type": "string"},
                                    "payment_type": {"type": "string"},
                                },
                                "required": ["amount", "description", "category", "payment_type"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["total_claimed", "documented_damages", "financial_items"],
                    "additionalProperties": False,
                },
            },
            "required": [
                "practice_area",
                "case_strength",
                "recommended_letter_type",
                "parties",
                "key_dates",
                "primary_issues",
                "financial_summary",
            ],
            "additionalProperties": False,
        },
    },
}


async def extract_structured_data_via_api(
    markdown_content: str,
    jurisdiction: str = "Florida",
) -> Dict[str, Any]:
    """Extract structured data from analysis markdown via a separate API call.

    Layer 2 fallback: called when the embedded JSON block is missing from the
    streaming analysis output. Uses gpt-5-mini with strict JSON schema to
    guarantee valid, schema-conformant output.

    Returns {} on any failure so callers can fall through to Layer 3.
    """
    from legal_portal.utils.openai_client import OpenAIClient

    try:
        client = OpenAIClient()
        response = await client.create_chat_completion_async(
            model="gpt-5.4-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract structured data from a legal case analysis. "
                        "Return valid JSON matching the required schema. "
                        f"Jurisdiction: {jurisdiction}."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Extract the following structured data from this legal analysis markdown:\n"
                        "- practice_area, case_strength, recommended_letter_type\n"
                        "- parties (name, role, entity_type)\n"
                        "- key_dates (date, event)\n"
                        "- primary_issues (name, category, strength, statutes[])\n"
                        "- financial_summary (total_claimed, documented_damages)\n\n"
                        f"Analysis:\n{markdown_content}"
                    ),
                },
            ],
            max_tokens=2000,
            response_format=_EXTRACTION_JSON_SCHEMA,
        )

        content = response.get("content", "")
        if not content:
            logger.warning("[STREAM:EXTRACTION] API extraction returned empty content")
            return {}

        # Check finish_reason if available
        finish_reason = response.get("finish_reason")
        if finish_reason == "length":
            logger.warning(
                "[STREAM:EXTRACTION] API extraction hit token limit (finish_reason=length), "
                "output may be incomplete"
            )
            return {}

        structured_data = json.loads(content)
        logger.info(
            f"[STREAM:EXTRACTION] API extraction succeeded | "
            f"keys={list(structured_data.keys())}"
        )
        return structured_data

    except json.JSONDecodeError as e:
        logger.error(f"[STREAM:EXTRACTION] API extraction JSON parse error: {e}")
        return {}
    except Exception as e:
        logger.error(f"[STREAM:EXTRACTION] API extraction failed: {e}")
        return {}


def _convert_statute_recommendations_recursive(obj: Any) -> Any:
    """Recursively convert any StatuteRecommendation dataclass objects to dicts.

    This function walks through the entire data structure (dicts, lists, nested structures)
    and converts any StatuteRecommendation instances to dictionaries for JSON serialization.

    Args:
        obj: The object to scan and convert (can be dict, list, or any other type)

    Returns:
        The same structure with all StatuteRecommendation objects converted to dicts

    """
    from dataclasses import asdict

    from legal_portal.services.shared.statute_recommendation_service import StatuteRecommendation

    # If it's a StatuteRecommendation instance, convert it
    if isinstance(obj, StatuteRecommendation):
        return asdict(obj)

    # If it's a dict, recursively process values
    if isinstance(obj, dict):
        return {key: _convert_statute_recommendations_recursive(value) for key, value in obj.items()}

    # If it's a list, recursively process items
    if isinstance(obj, list):
        return [_convert_statute_recommendations_recursive(item) for item in obj]

    # If it's a tuple, convert to list, process, and convert back (or keep as list)
    if isinstance(obj, tuple):
        return tuple(_convert_statute_recommendations_recursive(item) for item in obj)

    # For any other type, return as-is
    return obj


def _parse_currency(value) -> float:
    """Parse currency string like '$1,234.56' to float.

    Handles various formats:
    - "$1,234.56" -> 1234.56
    - "1234.56" -> 1234.56
    - 1234.56 -> 1234.56
    - None -> 0.0
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove $, commas, and whitespace
        cleaned = value.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
    return 0.0


def _extract_embedded_json(content: str) -> dict:
    """Extract the structured JSON block from streaming analysis markdown.

    The JSON is embedded in a ```json code fence at the end of the markdown.
    """
    import re

    # Look for JSON code block
    json_pattern = r"```json\s*\n(.*?)\n```"
    match = re.search(json_pattern, content, re.DOTALL)

    if not match:
        logger.warning("[STREAM] No embedded JSON found in streaming analysis")
        return {}

    try:
        json_str = match.group(1).strip()
        structured_data = json.loads(json_str)
        logger.info(f"[STREAM] Extracted structured data: {list(structured_data.keys())}")
        return structured_data
    except json.JSONDecodeError as e:
        logger.error(f"[STREAM] Failed to parse embedded JSON: {e}")
        return {}


def _extract_section(content: str, section_name: str) -> str:
    """Extract a section from markdown content."""
    import re
    pattern = rf"## {section_name}\n(.*?)(?=\n## |$)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _extract_list_items(content: str, section_name: str) -> List[str]:
    """Extract list items from a section."""
    import re
    section = _extract_section(content, section_name)
    if not section:
        return []
    # Find bullet points or numbered items
    items = re.findall(r"[-*•]\s*(.+?)(?=\n[-*•]|\n\n|$)", section, re.MULTILINE)
    return [item.strip() for item in items if item.strip()]
