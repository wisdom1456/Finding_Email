"""
Email Generation Services

This module contains specialized service classes that handle specific responsibilities
of the email generation system, following the Single Responsibility Principle.

Each service is focused on a single concern and can be independently tested and maintained.
"""

from __future__ import annotations

from .configuration_manager import ConfigurationManager
from .content_generation_service import ContentGenerationService
from .fallback_generation_service import FallbackGenerationService
from .json_architecture_service import JSONArchitectureService
from .openai_integration_service import OpenAIIntegrationService
from .template_rendering_service import TemplateRenderingService
from .text_processing_service import TextProcessingService


__all__ = [
    "ConfigurationManager",
    "ContentGenerationService",
    "FallbackGenerationService",
    "JSONArchitectureService",
    "OpenAIIntegrationService",
    "TemplateRenderingService",
    "TextProcessingService",
]
