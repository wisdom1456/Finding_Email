"""Modular service components for document processing."""
# Email generation services
# Processing services
from __future__ import annotations

from .audio_processor import AudioProcessor
from .configuration_manager import ConfigurationManager
from .content_extraction_service import ContentExtractionService
from .content_formatting_service import ContentFormattingService
from .content_generation_service import ContentGenerationService
from .fallback_generation_service import FallbackGenerationService
from .json_architecture_service import JSONArchitectureService
from .json_processing_service import JsonProcessingService
from .openai_integration_service import OpenAIIntegrationService
from .prompt_and_api_service import PromptAndApiService
from .template_rendering_service import TemplateRenderingService
from .text_processing_service import TextProcessingService
from .video_processor import VideoProcessor


__all__ = [
    # Email generation services
    "ConfigurationManager",
    "TextProcessingService",
    "JSONArchitectureService",
    "TemplateRenderingService",
    "ContentGenerationService",
    "OpenAIIntegrationService",
    "FallbackGenerationService",
    "JsonProcessingService",
    "ContentExtractionService",
    "ContentFormattingService",
    "PromptAndApiService",
    # Processing services
    "AudioProcessor",
    "VideoProcessor"
]
