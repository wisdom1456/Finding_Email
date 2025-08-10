"""
EmailGeneratorV2 - Refactored Orchestrator

This is the refactored EmailGeneratorV2 class that has been updated to work with the new
single master prompt architecture. Key changes:
- Uses simplified JsonProcessingService for direct HTML generation
- Removes dependencies on deleted YAML configuration keys
- Injects CaseAnalysisResult directly into the master prompt
- Maintains backward compatibility while using the new streamlined approach

This replaces the complex multi-prompt pipeline with a single, authoritative master prompt.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from openai import OpenAI

from backend.utils.data_models import CaseAnalysisResult
from utils.logging_config import setup_logging

from .services.configuration_manager import ConfigurationManager
from .services.content_generation_service import ContentGenerationService
from .services.fallback_generation_service import FallbackGenerationService
from .services.json_processing_service import JsonProcessingService
from .services.template_rendering_service import TemplateRenderingService
from .services.text_processing_service import TextProcessingService


logger = setup_logging("email_generator_v2")


logger = logging.getLogger(__name__)


class EmailGeneratorV2:
    """
    Refactored orchestrator for the new single master prompt architecture.

    This updated class coordinates the simplified services to generate legal email
    content using a single, authoritative master prompt instead of multiple AI calls.

    Key architectural improvements:
    - Single master prompt approach (no more multi-step JSON processing)
    - Direct HTML generation
    - Simplified error handling and fallback mechanisms
    - CaseAnalysisResult injection directly into master prompt
    - Removal of complex configuration dependencies
    """

    def __init__(
        self, config_path: Optional[str] = None, openai_api_key: Optional[str] = None
    ):
        """
        Initialize the email generator with refactored service dependencies.

        Args:
            config_path: Optional path to configuration file
            openai_api_key: OpenAI API key for content generation
        """
        logger.info(
            "Initializing EmailGeneratorV2 with refactored single-prompt architecture"
        )

        # Initialize core services
        self.config_manager = ConfigurationManager(config_path)
        self.text_processor = TextProcessingService()

        # Initialize template service with directory from config
        template_dir = self.config_manager.get_template_directory()
        self.template_service = TemplateRenderingService(template_dir)

        # Initialize OpenAI client
        self.openai_client = None
        if openai_api_key:
            try:
                self.openai_client = OpenAI(api_key=openai_api_key)
                logger.info("OpenAI client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")

        # Initialize the refactored JsonProcessingService for direct HTML generation
        self.config = self.config_manager.get_config()
        if self.openai_client and self.config:
            self.json_processing_service = JsonProcessingService(
                client=self.openai_client, config=self.config
            )
        else:
            logger.warning(
                "JsonProcessingService not initialized - missing OpenAI client or config"
            )
            self.json_processing_service = None

        # Initialize content generation service with refactored dependencies
        self.content_service = ContentGenerationService(
            json_processing_service=self.json_processing_service
        )

        # Initialize fallback service
        self.fallback_service = FallbackGenerationService()

        # Cache frequently accessed configuration
        self.template_directory = template_dir

        logger.info("EmailGeneratorV2 initialization completed with new architecture")

    def generate_email_and_analysis_docs(
        self, case_analysis: CaseAnalysisResult
    ) -> Dict[str, Any]:
        """
        Generate complete email and analysis documents using the new single-prompt approach.

        Main entry point that uses the refactored architecture to generate legal content
        directly as HTML using a single master prompt.

        Args:
            case_analysis: Complete case analysis result from document processing

        Returns:
            Complete generated document structure with HTML content
        """
        logger.info(
            "Starting email generation with new single master prompt architecture"
        )

        try:
            # Validate that we have the necessary services
            if not self.json_processing_service:
                logger.error("JsonProcessingService not available - falling back")
                return self._generate_fallback_response(
                    case_analysis, "Service initialization failed"
                )

            # Validate configuration
            if not self.config_manager.is_configured():
                logger.warning("Configuration not fully loaded, using fallback")
                return self._generate_fallback_response(
                    case_analysis, "Configuration incomplete"
                )

            # H2 DEBUG: Service method entry
            import json

            logger.debug(
                f"DEBUG_H2: {json.dumps({'module': 'email_generator_v2', 'hypothesis_id': 'H2', 'action': 'service_method_entry', 'line': 125, 'method': 'generate_email_and_analysis_docs'})}"
            )

            # Use the refactored content generation service for single-prompt approach
            result = self.content_service.generate_email_and_analysis_docs(
                case_analysis
            )

            # H2 DEBUG: Content service result analysis
            result_debug = {
                "module": "email_generator_v2",
                "hypothesis_id": "H2",
                "action": "content_service_result",
                "line": 126,
                "result_type": str(type(result)),
                "result_keys": list(result.keys())
                if isinstance(result, dict)
                else None,
                "has_letter_content": "letter_content" in result
                if isinstance(result, dict)
                else False,
                "letter_content_length": len(result.get("letter_content", ""))
                if isinstance(result, dict)
                else 0,
            }
            logger.debug(f"DEBUG_H2: {json.dumps(result_debug)}")

            # Add template rendering if template is available and result has content
            if result.get("letter_content") and self.template_directory:
                try:
                    # For the new architecture, the HTML is already generated
                    # Template rendering is optional for additional formatting
                    rendered_content = self._apply_optional_template_formatting(
                        result["letter_content"]
                    )
                    if rendered_content:
                        result["rendered_email"] = rendered_content
                        result["template_applied"] = True
                    else:
                        result["template_applied"] = False

                except Exception as e:
                    logger.warning(f"Optional template formatting failed: {e}")
                    result["template_applied"] = False

            # Add metadata about the new architecture
            result.setdefault("metadata", {}).update(
                {
                    "architecture_version": "single_master_prompt",
                    "generation_method": "direct_html",
                    "configuration_keys_used": ["master_prompt", "template_path"],
                    "deprecated_keys_removed": [
                        "sections",
                        "personas",
                        "firm_voice",
                        "normalization_rules",
                        "precision_rules",
                        "plain_english_mandate",
                        "citation_filter_regex",
                        "content_rules",
                        "word_counts",
                        "universal_sections_schema",
                        "claim_definitions",
                    ],
                }
            )

            logger.info("Email generation completed successfully with new architecture")
            return result

        except Exception as e:
            logger.error(f"Error in new architecture document generation: {e}")
            return self._generate_fallback_response(case_analysis, str(e))

    def _apply_optional_template_formatting(self, html_content: str) -> Optional[str]:
        """
        Apply optional template formatting to the generated HTML content.

        Args:
            html_content: Generated HTML content

        Returns:
            Optionally formatted content or None if formatting fails
        """
        import json
        from datetime import datetime

        try:
            # DEBUG LOGGING: Log the data flow to confirm the issue
            template_debug_log = {
                "module": "EmailGeneratorV2",
                "method": "_apply_optional_template_formatting",
                "hypothesis_id": "data_structure_mismatch",
                "stage": "template_rendering_entry",
                "html_content_type": type(html_content).__name__,
                "html_content_length": len(html_content) if html_content else 0,
                "html_content_preview": html_content[:200] if html_content else None,
                "template_exists": self.template_service.template_exists(
                    "findings_email.jinja2"
                ),
                "timestamp": datetime.now().isoformat(),
            }
            logger.debug(f"TEMPLATE_DEBUG: {json.dumps(template_debug_log, indent=2)}")

            # BYPASS TEMPLATE RENDERING ENTIRELY
            # The JsonProcessingService now returns complete HTML, so template rendering is no longer needed
            logger.info(
                "Bypassing Jinja2 template rendering - JsonProcessingService returns complete HTML"
            )

            bypass_log = {
                "module": "EmailGeneratorV2",
                "method": "_apply_optional_template_formatting",
                "hypothesis_id": "template_bypass_fix",
                "action": "bypassing_jinja2_template",
                "reason": "JsonProcessingService returns complete HTML",
                "html_returned_directly": True,
                "timestamp": datetime.now().isoformat(),
            }
            logger.debug(f"TEMPLATE_BYPASS: {json.dumps(bypass_log, indent=2)}")

            # Return the HTML content directly since it's already complete
            return html_content

        except Exception as e:
            logger.warning(f"Template formatting failed: {e}")
            return None

    def _generate_fallback_response(
        self, case_analysis: CaseAnalysisResult = None, error_message: str = None
    ) -> Dict[str, Any]:
        """
        Generate complete fallback response using the fallback service.

        Args:
            case_analysis: Available case analysis data
            error_message: Error description

        Returns:
            Fallback response structure
        """
        # Extract basic information for fallback
        case_data = {}
        if case_analysis and case_analysis.intake_analysis:
            case_data = {
                "client_name": case_analysis.intake_analysis.client_name,
                "case_type": case_analysis.intake_analysis.case_type,
            }

        fallback_content = self.fallback_service.create_error_recovery_content(
            error_message or "Unknown error", case_data
        )

        letter_content = self.fallback_service.create_fallback_letter(
            case_data, error_message
        )

        return {
            "letter_content": letter_content,
            "generated_letter": letter_content,  # For backward compatibility
            "structured_data": fallback_content,
            "metadata": {
                "architecture_version": "single_master_prompt",
                "generation_method": "fallback",
                "is_fallback": True,
                "error_message": error_message,
                "has_error": True,
            },
        }

    # Backward compatibility methods - simplified for new architecture
    def _load_configuration(self) -> None:
        """Reload configuration. Delegates to ConfigurationManager."""
        self.config_manager.reload_configuration()
        self.config = self.config_manager.get_config()

    def _find_template_directory(self) -> Optional[str]:
        """Find template directory. Delegates to ConfigurationManager."""
        return self.config_manager.get_template_directory()

    def get_service_status(self) -> Dict[str, Any]:
        """
        Get status of all services in the new architecture.

        Returns:
            Status information for all services
        """
        return {
            "email_generator_v2": {
                "architecture": "single_master_prompt_refactored",
                "version": "2.0_refactored",
                "services_count": 6,
                "is_configured": self.config_manager.is_configured(),
                "openai_client_available": self.openai_client is not None,
            },
            "configuration_manager": {
                "is_configured": self.config_manager.is_configured(),
                "template_directory": self.config_manager.get_template_directory(),
                "master_prompt_available": bool(self.config.get("master_prompt")),
            },
            "json_processing_service": {
                "available": self.json_processing_service is not None,
                "method": "direct_html_generation",
            },
            "content_generation": self.content_service.get_generation_status(),
            "template_service": {
                "template_directory": self.template_service.template_directory,
                "available_templates": self.template_service.get_available_templates(),
            },
            "fallback_service": {
                "available_strategies": self.fallback_service.error_recovery_strategies
            },
        }

    # Legacy method compatibility
    def generate_structured_json(self, analysis: CaseAnalysisResult) -> str:
        """
        DEPRECATED: Legacy method for backward compatibility.
        Use generate_email_and_analysis_docs() instead.
        """
        logger.warning(
            "generate_structured_json() is deprecated. "
            "Use generate_email_and_analysis_docs() for direct HTML generation."
        )

        # Return HTML content for backward compatibility
        result = self.generate_email_and_analysis_docs(analysis)
        return result.get("letter_content", "[Error generating content]")
