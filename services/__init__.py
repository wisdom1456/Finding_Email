"""Modular service components for document processing."""
# Email generation services
from .configuration_manager import ConfigurationManager
from .text_processing_service import TextProcessingService
from .json_architecture_service import JSONArchitectureService
from .template_rendering_service import TemplateRenderingService
from .content_generation_service import ContentGenerationService
from .openai_integration_service import OpenAIIntegrationService
from .fallback_generation_service import FallbackGenerationService
from .json_processing_service import JsonProcessingService
from .content_extraction_service import ContentExtractionService
from .content_formatting_service import ContentFormattingService
from .prompt_and_api_service import PromptAndApiService

# Processing services
from .audio_processor import AudioProcessor
from .video_processor import VideoProcessor

__all__ = [
    # Email generation services
    'ConfigurationManager',
    'TextProcessingService',
    'JSONArchitectureService', 
    'TemplateRenderingService',
    'ContentGenerationService',
    'OpenAIIntegrationService',
    'FallbackGenerationService',
    'JsonProcessingService',
    'ContentExtractionService',
    'ContentFormattingService',
    'PromptAndApiService',
    # Processing services
    'AudioProcessor',
    'VideoProcessor'
]