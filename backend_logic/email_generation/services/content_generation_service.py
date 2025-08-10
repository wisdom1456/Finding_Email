"""
Content Generation Service - REFACTORED

Simplified service for content generation using the new single master prompt approach.
This service has been refactored to:
- Use a single master prompt instead of multi-step JSON processing
- Inject CaseAnalysisResult directly into the master prompt
- Generate HTML directly without complex section-by-section processing
- Remove dependencies on deleted YAML configuration keys

This replaces the complex multi-prompt pipeline with a streamlined single-call approach.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from backend.utils.data_models import CaseAnalysisResult


logger = logging.getLogger(__name__)


class ContentGenerationService:
    """
    Simplified content generation service using single master prompt approach.

    This refactored service coordinates content generation using the new architecture:
    - Single master prompt instead of multiple AI calls
    - Direct HTML generation
    - Simplified error handling and fallback mechanisms
    """

    def __init__(
        self,
        json_processing_service,
        openai_service=None,
        json_service=None,
        text_service=None,
    ):
        """
        Initialize the simplified content generation service.

        Args:
            json_processing_service: The refactored JsonProcessingService for HTML generation
            openai_service: Legacy parameter (deprecated)
            json_service: Legacy parameter (deprecated)
            text_service: Legacy parameter (deprecated)
        """
        self.json_processing_service = json_processing_service

        # Legacy parameters kept for backward compatibility
        if openai_service or json_service or text_service:
            logger.warning(
                "Legacy service parameters are deprecated. "
                "Only json_processing_service is used in the new architecture."
            )

        self.openai_service = openai_service
        self.json_service = json_service
        self.text_service = text_service

    def generate_email_and_analysis_docs(
        self, case_analysis: CaseAnalysisResult, config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate complete email and analysis documents using the new single-prompt approach.

        This is the main orchestration method that uses the simplified architecture
        to generate legal document content directly as HTML.

        Args:
            case_analysis: Complete case analysis result from document processing
            config: Optional configuration parameters (largely unused in new approach)

        Returns:
            Complete generated document structure with HTML content
        """
        logger.info(
            "Starting email and analysis document generation with new architecture"
        )

        try:
            # Use the refactored JsonProcessingService to generate HTML directly
            html_content = self.json_processing_service.generate_html_letter(
                case_analysis
            )

            if not html_content:
                raise ValueError("HTML generation returned empty content")

            # Create response structure compatible with existing interfaces
            result = {
                "letter_content": html_content,
                "generated_letter": html_content,  # For backward compatibility
                "metadata": {
                    "architecture": "single_master_prompt",
                    "generation_method": "direct_html",
                    "content_length": len(html_content),
                    "has_error": False,
                    "is_fallback": False,
                },
            }

            logger.info("Email and analysis document generation completed successfully")
            return result

        except Exception as e:
            logger.error(f"Error in simplified content generation: {e}")
            return self._create_error_response(str(e), case_analysis)

    def _create_error_response(
        self, error_message: str, case_analysis: CaseAnalysisResult = None
    ) -> Dict[str, Any]:
        """
        Create an error response with fallback content.

        Args:
            error_message: Error description
            case_analysis: Original case analysis that caused the error

        Returns:
            Error response with fallback content
        """
        logger.warning(f"Creating error response: {error_message}")

        # Extract basic info for fallback
        client_name = "Client"
        case_type = "Legal Matter"

        if case_analysis and case_analysis.intake_analysis:
            client_name = case_analysis.intake_analysis.client_name or client_name
            case_type = case_analysis.intake_analysis.case_type or case_type

        fallback_html = f"""<html>
<body>
<p>We have completed our initial review of your {case_type.lower()} matter. Due to a technical issue during document generation, we are providing this preliminary communication.</p>

<p>Our analysis is currently being finalized and we will provide a comprehensive findings letter within 24 hours. Based on our initial review, your matter requires immediate attention and strategic consideration.</p>

<p><strong>Immediate Next Steps:</strong></p>
<ul>
<li>We will contact you within 24 hours with detailed findings</li>
<li>Please preserve all relevant documents and communications</li>
<li>Do not take any action regarding this matter until we provide guidance</li>
</ul>

<p>If you have urgent questions or concerns, please contact our office immediately. We are committed to providing you with thorough legal guidance.</p>
</body>
</html>"""

        return {
            "letter_content": fallback_html,
            "generated_letter": fallback_html,
            "metadata": {
                "architecture": "single_master_prompt",
                "generation_method": "error_fallback",
                "error_message": error_message,
                "has_error": True,
                "is_fallback": True,
            },
        }

    # Legacy methods kept for backward compatibility
    def generate_factual_summary_content(self, case_data: Dict[str, Any]) -> str:
        """
        DEPRECATED: Legacy method for backward compatibility.
        Use generate_email_and_analysis_docs() instead.
        """
        logger.warning(
            "generate_factual_summary_content() is deprecated. "
            "Use generate_email_and_analysis_docs() with CaseAnalysisResult instead."
        )
        return "[Legacy method - use new architecture]"

    def generate_legal_analysis_content(self, case_data: Dict[str, Any]) -> str:
        """
        DEPRECATED: Legacy method for backward compatibility.
        Use generate_email_and_analysis_docs() instead.
        """
        logger.warning(
            "generate_legal_analysis_content() is deprecated. "
            "Use generate_email_and_analysis_docs() with CaseAnalysisResult instead."
        )
        return "[Legacy method - use new architecture]"

    def generate_evidence_review_content(self, case_data: Dict[str, Any]) -> str:
        """
        DEPRECATED: Legacy method for backward compatibility.
        Use generate_email_and_analysis_docs() instead.
        """
        logger.warning(
            "generate_evidence_review_content() is deprecated. "
            "Use generate_email_and_analysis_docs() with CaseAnalysisResult instead."
        )
        return "[Legacy method - use new architecture]"

    def generate_recommendations_content(self, case_data: Dict[str, Any]) -> str:
        """
        DEPRECATED: Legacy method for backward compatibility.
        Use generate_email_and_analysis_docs() instead.
        """
        logger.warning(
            "generate_recommendations_content() is deprecated. "
            "Use generate_email_and_analysis_docs() with CaseAnalysisResult instead."
        )
        return "[Legacy method - use new architecture]"

    def get_generation_status(self) -> Dict[str, Any]:
        """
        Get the current status of the content generation service.

        Returns:
            Service status information
        """
        return {
            "service_name": "ContentGenerationService",
            "architecture": "single_master_prompt",
            "generation_method": "direct_html",
            "legacy_methods_available": True,
            "is_configured": self.json_processing_service is not None,
            "deprecated_services": {
                "openai_service": self.openai_service is not None,
                "json_service": self.json_service is not None,
                "text_service": self.text_service is not None,
            },
        }
