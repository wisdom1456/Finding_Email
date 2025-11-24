"""Prompt and API Service - DEPRECATED.

This service is deprecated as part of the architectural refactoring to use a single
master prompt approach. The complex prompt building functionality has been replaced
with direct master prompt injection in JsonProcessingService.

MIGRATION NOTES:
- build_enhanced_prompt() -> No longer needed (master prompt is used directly)
- Complex prompt enhancement -> Simplified to single master prompt
- YAML configuration dependencies removed

This file is kept for backward compatibility during the transition period.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class PromptAndApiService:
    """DEPRECATED: Legacy prompt building and API service.

    This service has been deprecated in favor of the new single-prompt approach.
    Use JsonProcessingService.generate_html_letter() instead.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the deprecated prompt and API service."""
        logger.warning(
            "PromptAndApiService is deprecated. Use JsonProcessingService.generate_html_letter() instead."
        )
        self.config = config or {}

    def build_enhanced_prompt(self, base_prompt: str, section_key: str) -> str:
        """DEPRECATED: Complex prompt building is no longer needed.

        The new architecture uses a single master prompt that includes all
        necessary instructions and formatting requirements.
        """
        logger.warning(
            "build_enhanced_prompt() is deprecated. "
            "The new architecture uses a single master prompt directly."
        )

        # Return the base prompt without enhancement since the new architecture
        # handles all prompt complexity in the master prompt
        return base_prompt or "[Deprecated - use new master prompt architecture]"

    def make_openai_request(self, prompt: str, persona: str = "") -> str:
        """DEPRECATED: Use JsonProcessingService._make_openai_request() instead.

        This method is no longer supported in the new architecture.
        """
        logger.error(
            "make_openai_request() is deprecated. Use JsonProcessingService._make_openai_request() instead."
        )

        return "[DEPRECATED: Use JsonProcessingService for OpenAI requests]"
