"""
JSON Architecture Service - DEPRECATED

This service is deprecated as part of the architectural refactoring to use a single
master prompt approach. The functionality has been absorbed into the simplified
JsonProcessingService which now generates HTML directly.

MIGRATION NOTES:
- generate_structured_json() -> JsonProcessingService.generate_html_letter()
- validate_json_response() -> No longer needed (HTML validation in JsonProcessingService)
- convert_json_to_generated_letter() -> No longer needed (direct HTML generation)

This file is kept for backward compatibility during the transition period.
"""

from __future__ import annotations

import logging
from typing import Any, Dict


logger = logging.getLogger(__name__)


class JSONArchitectureService:
    """
    DEPRECATED: Legacy JSON architecture service.

    This service has been deprecated in favor of the new single-prompt approach.
    Use JsonProcessingService.generate_html_letter() instead.
    """

    def __init__(self):
        """Initialize the deprecated JSON architecture service."""
        logger.warning(
            "JSONArchitectureService is deprecated. "
            "Use JsonProcessingService.generate_html_letter() instead."
        )
        self.required_sections = [
            "factual_summary",
            "legal_analysis",
            "evidence_review",
            "recommendations",
        ]

    def generate_structured_json(self, ai_response: str) -> Dict[str, Any]:
        """
        DEPRECATED: Use JsonProcessingService.generate_html_letter() instead.

        This method is no longer supported in the new architecture.
        """
        logger.error(
            "generate_structured_json() is deprecated. "
            "Use JsonProcessingService.generate_html_letter() for direct HTML generation."
        )
        return self._create_deprecation_fallback()

    def validate_json_response(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        DEPRECATED: JSON validation is no longer needed with direct HTML generation.

        This method is no longer supported in the new architecture.
        """
        logger.error(
            "validate_json_response() is deprecated. "
            "HTML validation is handled in JsonProcessingService."
        )
        return (
            json_data
            if isinstance(json_data, dict)
            else self._create_deprecation_fallback()
        )

    def convert_json_to_generated_letter(
        self, json_data: Dict[str, Any], template_content: str = None
    ) -> str:
        """
        DEPRECATED: Direct HTML generation has replaced JSON-to-letter conversion.

        This method is no longer supported in the new architecture.
        """
        logger.error(
            "convert_json_to_generated_letter() is deprecated. "
            "Use JsonProcessingService.generate_html_letter() for direct HTML generation."
        )
        return "[DEPRECATED: Use JsonProcessingService.generate_html_letter() instead]"

    def _create_deprecation_fallback(self) -> Dict[str, Any]:
        """Create a fallback response indicating deprecation."""
        return {
            "error": "JSONArchitectureService is deprecated",
            "migration_note": "Use JsonProcessingService.generate_html_letter() instead",
            "deprecated_sections": {
                section: f"[{section.replace('_', ' ').title()} - Use new architecture]"
                for section in self.required_sections
            },
            "metadata": {
                "is_deprecated": True,
                "replacement_service": "JsonProcessingService",
            },
        }
