"""
Email Generation Services

This module contains specialized service classes that handle specific responsibilities
of the email generation system, following the Single Responsibility Principle.

Each service is focused on a single concern and can be independently tested and maintained.
"""

from .configuration_manager import ConfigurationManager
from .text_processing_service import TextProcessingService
from .json_architecture_service import JSONArchitectureService
from .template_rendering_service import TemplateRenderingService
from .content_generation_service import ContentGenerationService
from .openai_integration_service import OpenAIIntegrationService
from .fallback_generation_service import FallbackGenerationService

__all__ = [
    'ConfigurationManager',
    'TextProcessingService', 
    'JSONArchitectureService',
    'TemplateRenderingService',
    'ContentGenerationService',
    'OpenAIIntegrationService',
    'FallbackGenerationService'
]