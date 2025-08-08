"""
Email Generation Module

This module provides a refactored, modular architecture for email generation,
replacing the monolithic EmailGeneratorV2 class with focused service components.

The main EmailGeneratorV2 class acts as a lightweight orchestrator that coordinates
specialized services, each with a single responsibility.

Architecture:
- ConfigurationManager: YAML configuration and template management
- TextProcessingService: Basic text cleanup (simplified, no complex simplification)
- JSONArchitectureService: Structured JSON operations
- TemplateRenderingService: Jinja2 template operations
- ContentGenerationService: Section-specific content orchestration
- OpenAIIntegrationService: AI API calls and prompt management
- FallbackGenerationService: Error recovery and fallback content
- EmailGeneratorV2: Lightweight orchestrator coordinating all services

Benefits:
- Single Responsibility Principle compliance
- Enhanced maintainability and testability
- Clear separation of concerns
- Simplified text processing (removed problematic simplification pipeline)
- Modular architecture enabling independent service development
"""

from .email_generator_v2 import EmailGeneratorV2

# Also export services for advanced usage
from .services import (
    ConfigurationManager,
    TextProcessingService,
    JSONArchitectureService,
    TemplateRenderingService,
    ContentGenerationService,
    OpenAIIntegrationService,
    FallbackGenerationService
)

__all__ = [
    'EmailGeneratorV2',
    'ConfigurationManager',
    'TextProcessingService',
    'JSONArchitectureService',
    'TemplateRenderingService',
    'ContentGenerationService',
    'OpenAIIntegrationService',
    'FallbackGenerationService'
]