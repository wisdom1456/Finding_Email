"""
Content Generation Service

Handles section-specific content generation for legal emails and documents.
This service is responsible for:
- Orchestrating content generation for different sections
- Coordinating between OpenAI service and other components
- Managing content flow and dependencies
- Handling section-specific logic and formatting

This replaces content generation methods from the original EmailGeneratorV2 class.
"""

from typing import Dict, Any, Optional, List
import logging
from .openai_integration_service import OpenAIIntegrationService
from .json_architecture_service import JSONArchitectureService
from .text_processing_service import TextProcessingService

logger = logging.getLogger(__name__)


class ContentGenerationService:
    """
    Orchestrates content generation for different sections of legal documents.
    
    This service coordinates the generation of various content sections,
    managing the flow between AI generation, processing, and structuring.
    """
    
    def __init__(self, openai_service: OpenAIIntegrationService,
                 json_service: JSONArchitectureService,
                 text_service: TextProcessingService):
        """
        Initialize the content generation service.
        
        Args:
            openai_service: Service for AI content generation
            json_service: Service for JSON operations
            text_service: Service for text processing
        """
        self.openai_service = openai_service
        self.json_service = json_service
        self.text_service = text_service
        
        # Content generation pipeline stages
        self.pipeline_stages = [
            'PREPARE',
            'GENERATE', 
            'FORMAT'
        ]
        
        # Required content sections
        self.content_sections = [
            'factual_summary',
            'legal_analysis',
            'evidence_review', 
            'recommendations'
        ]
    
    def generate_email_and_analysis_docs(self, case_data: Dict[str, Any],
                                       config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Generate complete email and analysis documents.
        
        Main orchestration method that coordinates the entire content generation
        process from raw case data to structured legal documents.
        
        Args:
            case_data: Raw case information and context
            config: Optional configuration parameters
            
        Returns:
            Complete generated document structure
        """
        logger.info("Starting email and analysis document generation")
        
        try:
            # Stage 1: PREPARE - Prepare and validate input data
            prepared_data = self._prepare_case_data(case_data, config)
            
            # Stage 2: GENERATE - Generate content for each section
            generated_content = self._generate_all_sections(prepared_data)
            
            # Stage 3: FORMAT - Process and format the generated content
            formatted_content = self._format_generated_content(generated_content)
            
            logger.info("Email and analysis document generation completed successfully")
            return formatted_content
            
        except Exception as e:
            logger.error(f"Error in content generation pipeline: {e}")
            return self._create_error_response(str(e), case_data)
    
    def generate_factual_summary_content(self, case_data: Dict[str, Any]) -> str:
        """
        Generate factual summary content for the case.
        
        Args:
            case_data: Case information and context
            
        Returns:
            Generated factual summary content
        """
        logger.info("Generating factual summary content")
        
        try:
            # Use OpenAI service to generate content
            raw_content = self.openai_service.generate_factual_summary(case_data)
            
            # Process the generated content
            processed_content = self.text_service.clean_ai_response(raw_content)
            formatted_content = self.text_service.format_legal_content(processed_content)
            
            return formatted_content
            
        except Exception as e:
            logger.error(f"Error generating factual summary: {e}")
            return f"[Error generating factual summary: {e}]"
    
    def generate_legal_analysis_content(self, case_data: Dict[str, Any]) -> str:
        """
        Generate legal analysis content for the case.
        
        Args:
            case_data: Case information and context
            
        Returns:
            Generated legal analysis content
        """
        logger.info("Generating legal analysis content")
        
        try:
            # Use OpenAI service to generate content
            raw_content = self.openai_service.generate_legal_analysis(case_data)
            
            # Process the generated content
            processed_content = self.text_service.clean_ai_response(raw_content)
            formatted_content = self.text_service.format_legal_content(processed_content)
            
            return formatted_content
            
        except Exception as e:
            logger.error(f"Error generating legal analysis: {e}")
            return f"[Error generating legal analysis: {e}]"
    
    def generate_evidence_review_content(self, case_data: Dict[str, Any]) -> str:
        """
        Generate evidence review content for the case.
        
        Args:
            case_data: Case information and context
            
        Returns:
            Generated evidence review content
        """
        logger.info("Generating evidence review content")
        
        try:
            # Use OpenAI service to generate content
            raw_content = self.openai_service.generate_evidence_review(case_data)
            
            # Process the generated content
            processed_content = self.text_service.clean_ai_response(raw_content)
            formatted_content = self.text_service.format_legal_content(processed_content)
            
            return formatted_content
            
        except Exception as e:
            logger.error(f"Error generating evidence review: {e}")
            return f"[Error generating evidence review: {e}]"
    
    def generate_recommendations_content(self, case_data: Dict[str, Any]) -> str:
        """
        Generate recommendations content for the case.
        
        Args:
            case_data: Case information and context
            
        Returns:
            Generated recommendations content
        """
        logger.info("Generating recommendations content")
        
        try:
            # Use OpenAI service to generate content
            raw_content = self.openai_service.generate_recommendations(case_data)
            
            # Process the generated content
            processed_content = self.text_service.clean_ai_response(raw_content)
            formatted_content = self.text_service.format_legal_content(processed_content)
            
            return formatted_content
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return f"[Error generating recommendations: {e}]"
    
    def _prepare_case_data(self, case_data: Dict[str, Any], 
                          config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Prepare and validate case data for content generation.
        
        Args:
            case_data: Raw case data
            config: Optional configuration
            
        Returns:
            Prepared and validated case data
        """
        prepared_data = case_data.copy()
        
        # Add default values for missing fields
        if 'case_id' not in prepared_data:
            prepared_data['case_id'] = 'unknown'
        
        if 'case_type' not in prepared_data:
            prepared_data['case_type'] = 'general'
        
        # Add configuration if provided
        if config:
            prepared_data['generation_config'] = config
        
        # Add metadata
        prepared_data['metadata'] = prepared_data.get('metadata', {})
        prepared_data['metadata']['pipeline_stage'] = 'PREPARE'
        
        logger.info(f"Case data prepared for generation: {prepared_data.get('case_id', 'unknown')}")
        return prepared_data
    
    def _generate_all_sections(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate content for all required sections.
        
        Args:
            case_data: Prepared case data
            
        Returns:
            Generated content for all sections
        """
        logger.info("Generating content for all sections")
        
        generated_content = {}
        
        # Generate each section
        for section in self.content_sections:
            try:
                if section == 'factual_summary':
                    content = self.generate_factual_summary_content(case_data)
                elif section == 'legal_analysis':
                    content = self.generate_legal_analysis_content(case_data)
                elif section == 'evidence_review':
                    content = self.generate_evidence_review_content(case_data)
                elif section == 'recommendations':
                    content = self.generate_recommendations_content(case_data)
                else:
                    content = f"[{section.replace('_', ' ').title()} content not implemented]"
                
                generated_content[section] = content
                logger.info(f"Successfully generated {section}")
                
            except Exception as e:
                logger.error(f"Error generating {section}: {e}")
                generated_content[section] = f"[Error generating {section}: {e}]"
        
        # Add metadata
        generated_content['metadata'] = {
            'pipeline_stage': 'GENERATE',
            'sections_generated': len([s for s in generated_content.keys() if s != 'metadata']),
            'generation_timestamp': None  # Could be set by caller
        }
        
        return generated_content
    
    def _format_generated_content(self, generated_content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and structure the generated content.
        
        Args:
            generated_content: Raw generated content
            
        Returns:
            Formatted and structured content
        """
        logger.info("Formatting generated content")
        
        try:
            # Validate and structure using JSON service
            structured_content = self.json_service.validate_json_response(generated_content)
            
            # Convert to letter format
            letter_content = self.json_service.convert_json_to_generated_letter(structured_content)
            
            # Create final response
            formatted_response = {
                'structured_data': structured_content,
                'letter_content': letter_content,
                'metadata': {
                    'pipeline_stage': 'FORMAT',
                    'format_timestamp': None,
                    'content_length': len(letter_content),
                    'sections_count': len(structured_content) - 1  # Excluding metadata
                }
            }
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error formatting content: {e}")
            return self._create_error_response(f"Formatting error: {e}", generated_content)
    
    def _create_error_response(self, error_message: str, 
                             original_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create an error response with fallback content.
        
        Args:
            error_message: Error description
            original_data: Original data that caused the error
            
        Returns:
            Error response with fallback content
        """
        logger.warning(f"Creating error response: {error_message}")
        
        error_response = {
            'structured_data': {
                'factual_summary': f"[Content generation error: {error_message}]",
                'legal_analysis': "[Legal analysis not available due to generation error]",
                'evidence_review': "[Evidence review not available due to generation error]", 
                'recommendations': "[Recommendations not available due to generation error]",
                'metadata': {
                    'pipeline_stage': 'ERROR',
                    'error_message': error_message,
                    'has_error': True
                }
            },
            'letter_content': f"Error generating document content: {error_message}",
            'metadata': {
                'pipeline_stage': 'ERROR',
                'error_message': error_message,
                'has_error': True
            }
        }
        
        return error_response
    
    def get_generation_status(self) -> Dict[str, Any]:
        """
        Get the current status of the content generation service.
        
        Returns:
            Service status information
        """
        return {
            'service_name': 'ContentGenerationService',
            'pipeline_stages': self.pipeline_stages,
            'content_sections': self.content_sections,
            'is_configured': all([
                self.openai_service is not None,
                self.json_service is not None,
                self.text_service is not None
            ])
        }