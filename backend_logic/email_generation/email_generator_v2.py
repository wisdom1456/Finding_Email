"""
EmailGeneratorV2 - Lightweight Orchestrator

This is the refactored EmailGeneratorV2 class that acts as a lightweight orchestrator
coordinating specialized services. This replaces the monolithic 5,466-line class
with a modular, maintainable architecture.

The class maintains backward compatibility while delegating responsibilities
to focused service components.
"""

import os
import logging
from typing import Dict, Any, Optional
from .services.configuration_manager import ConfigurationManager
from .services.text_processing_service import TextProcessingService
from .services.json_architecture_service import JSONArchitectureService
from .services.template_rendering_service import TemplateRenderingService
from .services.content_generation_service import ContentGenerationService
from .services.openai_integration_service import OpenAIIntegrationService
from .services.fallback_generation_service import FallbackGenerationService

logger = logging.getLogger(__name__)


class EmailGeneratorV2:
    """
    Lightweight orchestrator for email generation services.
    
    This refactored class coordinates specialized services to generate
    legal email content while maintaining backward compatibility with
    the original interface.
    
    Key improvements:
    - Modular service-oriented architecture
    - Single Responsibility Principle adherence
    - Simplified text processing (removed complex simplification pipeline)
    - Enhanced maintainability and testability
    - Clear separation of concerns
    """
    
    def __init__(self, config_path: Optional[str] = None, openai_api_key: Optional[str] = None):
        """
        Initialize the email generator with service dependencies.
        
        Args:
            config_path: Optional path to configuration file
            openai_api_key: Optional OpenAI API key
        """
        logger.info("Initializing EmailGeneratorV2 with modular architecture")
        
        # Initialize core services
        self.config_manager = ConfigurationManager(config_path)
        self.text_processor = TextProcessingService()
        self.json_service = JSONArchitectureService()
        
        # Initialize template service with directory from config
        template_dir = self.config_manager.get_template_directory()
        self.template_service = TemplateRenderingService(template_dir)
        
        # Initialize OpenAI service
        self.openai_service = OpenAIIntegrationService(
            api_key=openai_api_key,
            default_model="gpt-4"
        )
        
        # Initialize content generation service with dependencies
        self.content_service = ContentGenerationService(
            openai_service=self.openai_service,
            json_service=self.json_service,
            text_service=self.text_processor
        )
        
        # Initialize fallback service
        self.fallback_service = FallbackGenerationService()
        
        # Cache frequently accessed configuration
        self.config = self.config_manager.get_config()
        self.template_directory = template_dir
        
        # Set up OpenAI client if available (for backward compatibility)
        try:
            import openai
            if openai_api_key:
                openai.api_key = openai_api_key
            self.client = openai  # For backward compatibility
        except ImportError:
            logger.warning("OpenAI package not available")
            self.client = None
        
        logger.info("EmailGeneratorV2 initialization completed successfully")
    
    def generate_email_and_analysis_docs(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate complete email and analysis documents.
        
        Main entry point that orchestrates the entire generation process
        using the modular service architecture.
        
        Args:
            case_data: Case information and context
            
        Returns:
            Complete generated document structure
        """
        logger.info("Starting email and analysis document generation")
        
        try:
            # Validate configuration
            if not self.config_manager.is_configured():
                logger.warning("Configuration not fully loaded, using fallback")
                return self._generate_fallback_response(case_data, "Configuration incomplete")
            
            # Use content generation service to orchestrate the process
            result = self.content_service.generate_email_and_analysis_docs(
                case_data, 
                self.config
            )
            
            # Add template rendering if template is available
            if result.get('structured_data') and self.template_directory:
                try:
                    context = self.template_service.prepare_email_context(
                        result['structured_data']
                    )
                    
                    # Try to render with template if available
                    if self.template_service.template_exists('findings_email.jinja2'):
                        rendered_email = self.template_service.render_template(
                            'findings_email.jinja2', 
                            context
                        )
                        result['rendered_email'] = rendered_email
                
                except Exception as e:
                    logger.warning(f"Template rendering failed: {e}")
                    # Continue without template rendering
            
            return result
            
        except Exception as e:
            logger.error(f"Error in document generation: {e}")
            return self._generate_fallback_response(case_data, str(e))
    
    def _generate_structured_json(self, ai_response: str) -> Dict[str, Any]:
        """
        Generate structured JSON from AI response.
        
        Delegates to JSONArchitectureService.
        
        Args:
            ai_response: Raw AI response
            
        Returns:
            Structured JSON data
        """
        return self.json_service.generate_structured_json(ai_response)
    
    def _validate_json_response(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate JSON response structure.
        
        Delegates to JSONArchitectureService.
        
        Args:
            json_data: JSON data to validate
            
        Returns:
            Validated JSON structure
        """
        return self.json_service.validate_json_response(json_data)
    
    def _convert_json_to_generated_letter(self, json_data: Dict[str, Any]) -> str:
        """
        Convert JSON to formatted letter.
        
        Delegates to JSONArchitectureService.
        
        Args:
            json_data: Structured JSON data
            
        Returns:
            Formatted letter content
        """
        return self.json_service.convert_json_to_generated_letter(json_data)
    
    def _clean_ai_response(self, response: str) -> str:
        """
        Clean AI response text.
        
        Delegates to TextProcessingService (simplified version).
        
        Args:
            response: Raw AI response
            
        Returns:
            Cleaned text
        """
        return self.text_processor.clean_ai_response(response)
    
    def _prettify_html_output(self, html_content: str) -> str:
        """
        Prettify HTML output.
        
        Delegates to TextProcessingService.
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            Formatted HTML content
        """
        return self.text_processor.prettify_html_output(html_content)
    
    def format_video_analysis_for_appendix(self, video_analysis: str) -> str:
        """
        Format video analysis for appendix.
        
        Delegates to TemplateRenderingService.
        
        Args:
            video_analysis: Raw video analysis content
            
        Returns:
            Formatted video analysis
        """
        return self.template_service.format_video_analysis_for_appendix(video_analysis)
    
    def _make_openai_request(self, prompt: str, **kwargs) -> str:
        """
        Make OpenAI API request.
        
        Delegates to OpenAIIntegrationService.
        
        Args:
            prompt: Prompt text
            **kwargs: Additional parameters
            
        Returns:
            AI response
        """
        from .services.openai_integration_service import OpenAIRequest
        
        request = OpenAIRequest(
            prompt=prompt,
            model=kwargs.get('model', 'gpt-4'),
            temperature=kwargs.get('temperature', 0.7),
            max_tokens=kwargs.get('max_tokens'),
            system_message=kwargs.get('system_message')
        )
        
        return self.openai_service.make_openai_request(request)
    
    def _generate_factual_summary_content(self, case_data: Dict[str, Any]) -> str:
        """
        Generate factual summary content.
        
        Delegates to ContentGenerationService.
        
        Args:
            case_data: Case information
            
        Returns:
            Generated factual summary
        """
        return self.content_service.generate_factual_summary_content(case_data)
    
    def _generate_legal_analysis_content(self, case_data: Dict[str, Any]) -> str:
        """
        Generate legal analysis content.
        
        Delegates to ContentGenerationService.
        
        Args:
            case_data: Case information
            
        Returns:
            Generated legal analysis
        """
        return self.content_service.generate_legal_analysis_content(case_data)
    
    def _generate_evidence_review_content(self, case_data: Dict[str, Any]) -> str:
        """
        Generate evidence review content.
        
        Delegates to ContentGenerationService.
        
        Args:
            case_data: Case information
            
        Returns:
            Generated evidence review
        """
        return self.content_service.generate_evidence_review_content(case_data)
    
    def _generate_recommendations_content(self, case_data: Dict[str, Any]) -> str:
        """
        Generate recommendations content.
        
        Delegates to ContentGenerationService.
        
        Args:
            case_data: Case information
            
        Returns:
            Generated recommendations
        """
        return self.content_service.generate_recommendations_content(case_data)
    
    def _create_fallback_letter(self, case_data: Dict[str, Any] = None, 
                               error_context: str = None) -> str:
        """
        Create fallback letter content.
        
        Delegates to FallbackGenerationService.
        
        Args:
            case_data: Available case data
            error_context: Error context information
            
        Returns:
            Fallback letter content
        """
        return self.fallback_service.create_fallback_letter(case_data, error_context)
    
    def _generate_fallback_response(self, case_data: Dict[str, Any] = None,
                                  error_message: str = None) -> Dict[str, Any]:
        """
        Generate complete fallback response.
        
        Args:
            case_data: Available case data
            error_message: Error description
            
        Returns:
            Fallback response structure
        """
        fallback_content = self.fallback_service.create_error_recovery_content(
            error_message or "Unknown error", 
            case_data
        )
        
        letter_content = self.fallback_service.create_fallback_letter(
            case_data, 
            error_message
        )
        
        return {
            'structured_data': fallback_content,
            'letter_content': letter_content,
            'metadata': {
                'is_fallback': True,
                'error_message': error_message,
                'has_error': True
            }
        }
    
    # Backward compatibility methods
    def _load_configuration(self) -> None:
        """Reload configuration. Delegates to ConfigurationManager."""
        self.config_manager.reload_configuration()
        self.config = self.config_manager.get_config()
    
    def _find_template_directory(self) -> Optional[str]:
        """Find template directory. Delegates to ConfigurationManager."""
        return self.config_manager.get_template_directory()
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        Get status of all services.
        
        Returns:
            Status information for all services
        """
        return {
            'email_generator_v2': {
                'architecture': 'modular_services',
                'services_count': 7,
                'is_configured': self.config_manager.is_configured()
            },
            'configuration_manager': {
                'is_configured': self.config_manager.is_configured(),
                'template_directory': self.config_manager.get_template_directory()
            },
            'content_generation': self.content_service.get_generation_status(),
            'template_service': {
                'template_directory': self.template_service.template_directory,
                'available_templates': self.template_service.get_available_templates()
            },
            'fallback_service': {
                'available_strategies': self.fallback_service.error_recovery_strategies
            }
        }