from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

import markdown2
from legal_portal.config.default import get_openai_config
from legal_portal.core.data_models import CaseAnalysisResult
from legal_portal.services.citation_tracking_service import CitationTrackingService
from legal_portal.utils.logging_config import get_module_logger
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger = get_module_logger(__name__)


class JsonProcessingService:
    """Simplified service for generating HTML content using the new single master prompt.

    This refactored service aligns with the new architectural approach:
    - Uses a single, authoritative master prompt
    - Injects CaseAnalysisResult directly into the prompt
    - Generates HTML directly instead of multi-step JSON processing
    - Removes complex multi-prompt chaining logic
    """

    def __init__(self, client: OpenAI, config: Dict[str, Any]):
        self.client = client
        self.config = config
        self.citation_service = CitationTrackingService()

    def generate_html_letter(self, analysis: CaseAnalysisResult) -> str:
        """Generate HTML letter content using the single master prompt.

        This replaces the old generate_structured_json method with a simplified
        approach that directly generates the final HTML letter.

        Args:
        ----
            analysis: Complete case analysis result

        Returns:
        -------
            Generated HTML letter content

        """
        import json
        from datetime import datetime

        # DEBUG LOG: Entry point for hypothesis #1
        entry_debug_log = {
            "module": "JsonProcessingService",
            "method": "generate_html_letter",
            "hypothesis_id": "exception_handling_fallback",
            "stage": "entry",
            "timestamp": datetime.now().isoformat(),
            "analysis_provided": analysis is not None,
            "has_intake_analysis": analysis.intake_analysis is not None if analysis else False,
            "has_legal_assessment": analysis.legal_assessment is not None if analysis else False,
            "config_available": self.config is not None,
        }
        logger.info(f"HYPOTHESIS_DEBUG: {json.dumps(entry_debug_log)}")

        try:
            logger.info("Starting HTML letter generation using master prompt")

            # Extract client information from analysis
            client_name = analysis.intake_analysis.client_name if analysis.intake_analysis else "Client"
            case_type = analysis.intake_analysis.case_type if analysis.intake_analysis else "Legal Matter"

            logger.info(
                "Processing case information",
                extra={
                    "client_name": client_name,
                    "case_type": case_type,
                    "has_intake_analysis": analysis.intake_analysis is not None,
                },
            )

            # CAPTURE DATA: Save the final analysis data to JSON file
            try:
                os.makedirs("validation_output", exist_ok=True)
                final_analysis_data = analysis.model_dump_json(indent=2)

                with open("validation_output/final_analysis_data.json", "w", encoding="utf-8") as f:
                    f.write(final_analysis_data)
                logger.info(
                    "Saved final analysis data to file",
                    extra={
                        "file_path": "validation_output/final_analysis_data.json",
                        "data_size": len(final_analysis_data),
                    },
                )
            except Exception as save_error:
                logger.warning(
                    "Failed to save analysis data to file",
                    extra={
                        "error": str(save_error),
                        "error_type": type(save_error).__name__,
                    },
                )

            # Get the master prompt from configuration
            master_prompt = self.config.get("master_prompt")

            # DEBUG LOG: Master prompt configuration check for hypothesis #1
            config_debug_log = {
                "module": "JsonProcessingService",
                "method": "generate_html_letter",
                "hypothesis_id": "exception_handling_fallback",
                "stage": "master_prompt_config_check",
                "timestamp": datetime.now().isoformat(),
                "master_prompt_exists": master_prompt is not None,
                "master_prompt_length": len(master_prompt) if master_prompt else 0,
                "config_keys": list(self.config.keys()) if self.config else [],
                "config_available": self.config is not None,
            }
            logger.info(f"HYPOTHESIS_DEBUG: {json.dumps(config_debug_log)}")

            if not master_prompt:
                # DEBUG LOG: Missing master prompt - this will trigger fallback
                missing_prompt_log = {
                    "module": "JsonProcessingService",
                    "method": "generate_html_letter",
                    "hypothesis_id": "exception_handling_fallback",
                    "stage": "master_prompt_missing",
                    "timestamp": datetime.now().isoformat(),
                    "error": "Master prompt not found in configuration",
                    "will_trigger_fallback": True,
                }
                logger.error(f"HYPOTHESIS_DEBUG: {json.dumps(missing_prompt_log)}")
                raise ValueError("Master prompt not found in configuration")

            # Enhance master prompt with citation tracking instructions
            enhanced_prompt = self.citation_service.enhance_master_prompt_with_citations(master_prompt)

            # Prepare data for master prompt template
            # The template expects analysis object with attributes, not JSON string
            # Exclude original_content AND verbose fields to prevent token overflow
            # For letter generation, we only need concise summaries
            analysis_data = analysis.model_dump(
                exclude={
                    "analyzed_documents": {
                        "__all__": {
                            "original_content",  # Full document text (too large)
                            "detailed_findings",  # 500-800 words per doc (redundant with summary)
                            "evidence_points",  # Detailed evidence list (covered in key_facts)
                            "key_points",  # Often empty or redundant
                            "citations",  # Often empty or redundant
                            "metadata",  # Technical metadata not needed for letter
                        }
                    }
                }
            )

            # Create analysis object that template can access with dot notation
            class AnalysisProxy:
                def __init__(self, data):
                    self.client_name = data.get("intake_analysis", {}).get("client_name", client_name)
                    self.matter_name = data.get("intake_analysis", {}).get("case_summary", case_type)
                    self._raw_data = data  # Already has original_content excluded
                    # Store full documents separately for optional access
                    self._full_documents = analysis.analyzed_documents

                @property
                def practice_area(self):
                    return self._raw_data.get("practice_area")

                @property
                def legal_issues(self):
                    return self._raw_data.get("legal_issues")

                @property
                def recommended_next_steps(self):
                    return self._raw_data.get("recommended_next_steps")

                @property
                def jurisdiction(self):
                    return self._raw_data.get("jurisdiction")

                @property
                def include_appendix(self):
                    return self._raw_data.get("include_appendix", False)

                @property
                def firm_name(self):
                    # The AI's JSON output might not contain 'firm_name'.
                    # Provide a reliable default value if it's missing.
                    return self._raw_data.get("firm_name", "Bernhardt Riley PLLC")

                @property
                def analyzed_documents_with_content(self):
                    """Returns analyzed documents with their full original content for reference.

                    Use this property when the prompt needs access to full document text.
                    By default, the serialized data excludes original_content to prevent token overflow.
                    """
                    return self._full_documents

                def model_dump_json(self, indent=2):
                    import json

                    return json.dumps(self._raw_data, indent=indent)

                def __str__(self):
                    """Return JSON serialized data when object is used in string context."""
                    import json

                    return json.dumps(self._raw_data, indent=2)

                def __repr__(self):
                    """Return JSON serialized data for debugging."""
                    return self.__str__()

            analysis_proxy = AnalysisProxy(analysis_data)

            # Find example letter content or provide placeholder
            example_letter_content = self.config.get(
                "example_letter_content",
                "[Example letter content not configured - using template guidelines]",
            )

            # Inject case analysis with proper data structure for template
            formatted_prompt = enhanced_prompt.format(
                analysis=analysis_proxy, example_letter_content=example_letter_content
            )

            logger.debug(
                "Master prompt formatted",
                extra={
                    "prompt_length": len(formatted_prompt),
                    "template_length": len(master_prompt),
                },
            )

            # CAPTURE PROMPT: Save the fully constructed prompt to text file
            try:
                with open("validation_output/final_prompt.txt", "w", encoding="utf-8") as f:
                    f.write(formatted_prompt)
                logger.info(
                    "Saved formatted prompt to file",
                    extra={
                        "file_path": "validation_output/final_prompt.txt",
                        "prompt_length": len(formatted_prompt),
                    },
                )
            except Exception as save_error:
                logger.warning(
                    "Failed to save prompt to file",
                    extra={
                        "error": str(save_error),
                        "error_type": type(save_error).__name__,
                    },
                )

            logger.info("Making OpenAI request with master prompt for Markdown generation")
            markdown_response = self._make_openai_request(formatted_prompt)

            # DEBUG LOG: Raw OpenAI response for hypothesis #1 and #2
            raw_response_debug_log = {
                "module": "JsonProcessingService",
                "method": "generate_html_letter",
                "hypothesis_id": "openai_api_response_issue",
                "stage": "raw_openai_response",
                "timestamp": datetime.now().isoformat(),
                "markdown_response_received": markdown_response is not None,
                "markdown_response_length": len(markdown_response) if markdown_response else 0,
                "markdown_response_type": type(markdown_response).__name__ if markdown_response else "None",
                "markdown_response_preview": markdown_response[:500] if markdown_response else None,
                "markdown_response_stripped": bool(markdown_response and markdown_response.strip())
                if markdown_response
                else False,
            }
            logger.info(f"HYPOTHESIS_DEBUG: {json.dumps(raw_response_debug_log)}")

            # CAPTURE RAW RESPONSE: Save the raw OpenAI response to file
            try:
                with open("validation_output/raw_openai_response.txt", "w", encoding="utf-8") as f:
                    f.write(str(markdown_response) if markdown_response else "None")
                logger.info(
                    "Saved raw OpenAI response to file",
                    extra={
                        "file_path": "validation_output/raw_openai_response.txt",
                        "response_length": len(str(markdown_response)) if markdown_response else 0,
                    },
                )
            except Exception as save_error:
                logger.warning(
                    "Failed to save raw OpenAI response to file",
                    extra={
                        "error": str(save_error),
                        "error_type": type(save_error).__name__,
                    },
                )

            # DEBUG LOG: OpenAI response validation for hypothesis #2
            response_debug_log = {
                "module": "JsonProcessingService",
                "method": "generate_html_letter",
                "hypothesis_id": "exception_handling_fallback",
                "stage": "openai_response_check",
                "timestamp": datetime.now().isoformat(),
                "markdown_response_received": markdown_response is not None,
                "markdown_response_length": len(markdown_response) if markdown_response else 0,
                "markdown_response_stripped": bool(markdown_response and markdown_response.strip())
                if markdown_response
                else False,
                "will_raise_error": not (markdown_response and markdown_response.strip()),
            }
            logger.info(f"HYPOTHESIS_DEBUG: {json.dumps(response_debug_log)}")

            if not markdown_response or not markdown_response.strip():
                error_msg = "OpenAI returned empty response for Markdown generation"
                logger.error(f"Empty OpenAI response detected: {error_msg}")
                raise ValueError(error_msg)

            # CAPTURE MARKDOWN: Save the raw Markdown response to file
            try:
                with open("validation_output/raw_markdown_response.md", "w", encoding="utf-8") as f:
                    f.write(str(markdown_response) if markdown_response else "")
                logger.info(
                    "Saved raw Markdown response to file",
                    extra={
                        "file_path": "validation_output/raw_markdown_response.md",
                        "response_length": len(str(markdown_response)) if markdown_response else 0,
                    },
                )
            except Exception as save_error:
                logger.warning(
                    "Failed to save raw Markdown response to file",
                    extra={
                        "error": str(save_error),
                        "error_type": type(save_error).__name__,
                    },
                )

            # Convert Markdown to HTML using the new converter
            logger.info("Converting Markdown response to HTML")
            validated_html = self._convert_markdown_to_html(markdown_response)

            # Validate the converted HTML structure
            validated_html = self._validate_html_structure(validated_html)

            # Create citation map for the generated letter
            citation_map = self.citation_service.create_citation_map(analysis, validated_html)

            # Save citation map for appendix generation
            try:
                citation_export = self.citation_service.export_citation_map("json")
                with open("validation_output/citation_map.json", "w", encoding="utf-8") as f:
                    f.write(citation_export)
                logger.info("Citation map saved to validation_output/citation_map.json")
            except Exception as save_error:
                logger.warning(f"Failed to save citation map: {save_error}")

            # DEBUG LOG: Final HTML content before return for hypothesis #3 and #7
            final_html_debug_log = {
                "module": "JsonProcessingService",
                "method": "generate_html_letter",
                "hypothesis_id": "return_value_processing_issue",
                "stage": "final_html_before_return",
                "timestamp": datetime.now().isoformat(),
                "validated_html_length": len(validated_html),
                "validated_html_not_empty": bool(validated_html and validated_html.strip()),
                "validated_html_preview": validated_html[:500] if validated_html else None,
                "client_name": client_name,
                "case_type": case_type,
            }
            logger.info(f"HYPOTHESIS_DEBUG: {json.dumps(final_html_debug_log)}")

            # CAPTURE FINAL HTML: Save the final validated HTML to file
            try:
                with open("validation_output/final_validated_html.html", "w", encoding="utf-8") as f:
                    f.write(validated_html if validated_html else "")
                logger.info(
                    "Saved final validated HTML to file",
                    extra={
                        "file_path": "validation_output/final_validated_html.html",
                        "html_length": len(validated_html) if validated_html else 0,
                    },
                )
            except Exception as save_error:
                logger.warning(
                    "Failed to save final validated HTML to file",
                    extra={
                        "error": str(save_error),
                        "error_type": type(save_error).__name__,
                    },
                )

            logger.info(
                "Successfully generated HTML letter with citations",
                extra={
                    "html_length": len(validated_html),
                    "client_name": client_name,
                    "case_type": case_type,
                    "citation_count": len(citation_map.citations),
                    "citation_coverage": citation_map.metadata.get("citation_coverage", 0),
                },
            )
            return validated_html

        except ValueError as e:
            # Handle specific case where OpenAI returns empty response
            if "OpenAI returned empty response" in str(e):
                logger.error(
                    "OpenAI API returned empty response - this may be temporary",
                    extra={
                        "client_name": client_name,
                        "case_type": case_type,
                        "error_type": type(e).__name__,
                        "should_retry": True,
                    },
                )
                # Re-raise for potential retry logic at higher level
                raise e
            else:
                # Other ValueError issues are configuration/data problems - use fallback
                logger.exception(
                    "Configuration or data validation error - using fallback",
                    extra={
                        "client_name": client_name,
                        "case_type": case_type,
                        "error_type": type(e).__name__,
                    },
                )
                return self._generate_fallback_html(client_name, case_type, str(e))

        except (KeyError, AttributeError, TypeError) as e:
            # Data structure or configuration issues - use fallback
            logger.exception(
                "Data structure or configuration issue - using fallback",
                extra={
                    "client_name": client_name,
                    "case_type": case_type,
                    "error_type": type(e).__name__,
                },
            )
            return self._generate_fallback_html(client_name, case_type, str(e))

        except Exception as e:
            # Unexpected errors - log thoroughly and re-raise for proper handling
            logger.exception(
                "Unexpected error in HTML letter generation",
                extra={
                    "client_name": client_name,
                    "case_type": case_type,
                    "error_type": type(e).__name__,
                    "should_investigate": True,
                },
            )
            # Re-raise unexpected errors instead of silently falling back
            raise e

    def _convert_markdown_to_html(self, markdown_content: str) -> str:
        """Convert Markdown content to clean HTML.

        Args:
        ----
            markdown_content: Markdown text from OpenAI response

        Returns:
        -------
            Well-formatted HTML content

        """
        if not markdown_content:
            return ""

        # Clean the markdown content first - remove any code fences or extra formatting
        cleaned_markdown = self._clean_markdown_response(markdown_content)

        # Configure markdown2 with appropriate extras for legal documents
        extras = [
            "fenced-code-blocks",
            "tables",
            "break-on-newline",
            "cuddled-lists",
            "metadata",
            "smarty-pants",
        ]

        try:
            # Convert markdown to HTML
            html_content = markdown2.markdown(cleaned_markdown, extras=extras)

            # Wrap in a legal-letter container div for styling consistency
            wrapped_html = f'<div class="legal-letter">\n{html_content}\n</div>'

            # Ensure proper HTML structure
            if not wrapped_html.startswith("<html"):
                wrapped_html = f"<html>\n<body>\n{wrapped_html}\n</body>\n</html>"

            logger.debug(
                "Successfully converted Markdown to HTML",
                extra={
                    "markdown_length": len(cleaned_markdown),
                    "html_length": len(wrapped_html),
                    "method": "_convert_markdown_to_html",
                },
            )

            return wrapped_html

        except Exception as e:
            logger.error(
                "Failed to convert Markdown to HTML",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "markdown_preview": cleaned_markdown[:200] if cleaned_markdown else None,
                    "method": "_convert_markdown_to_html",
                },
            )
            # Return a fallback HTML structure if conversion fails
            return self._generate_minimal_fallback_html()

    def _clean_markdown_response(self, response_text: str) -> str:
        """Clean OpenAI response to extract valid Markdown.

        Args:
        ----
            response_text: Raw OpenAI response

        Returns:
        -------
            Cleaned Markdown content

        """
        if not response_text:
            return ""

        # Remove any code fences that might wrap the content
        cleaned = re.sub(r"^```markdown\s*", "", response_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        # Remove any HTML tags that might have been included accidentally
        cleaned = re.sub(r"<[^>]+>", "", cleaned)

        return cleaned

    def _clean_html_response(self, response_text: str) -> str:
        """Clean OpenAI response to extract valid HTML.

        NOTE: This method is deprecated in favor of Markdown processing.
        Kept for backward compatibility.

        Args:
        ----
            response_text: Raw OpenAI response

        Returns:
        -------
            Cleaned HTML content

        """
        if not response_text:
            return ""

        # Remove markdown code fences if present
        cleaned = re.sub(r"^```html\s*", "", response_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        # Extract HTML if wrapped in tags
        html_start = cleaned.find("<html")
        html_end = cleaned.rfind("</html>")

        if html_start != -1 and html_end != -1 and html_end > html_start:
            cleaned = cleaned[html_start : html_end + 7]  # Include </html>
        elif "<body>" in cleaned:
            # If no <html> tags but has <body>, extract body content
            body_start = cleaned.find("<body>")
            body_end = cleaned.rfind("</body>")
            if body_start != -1 and body_end != -1:
                body_content = cleaned[body_start + 6 : body_end]
                cleaned = f"<html><body>{body_content}</body></html>"

        return cleaned

    def _validate_html_structure(self, html_content: str) -> str:
        """Validate HTML structure and ensure basic compliance.

        Args:
        ----
            html_content: HTML content to validate

        Returns:
        -------
            Validated HTML content

        """
        if not html_content:
            return self._generate_minimal_fallback_html()

        # Ensure basic HTML structure
        if not html_content.startswith("<html"):
            if "<body>" in html_content:
                html_content = f"<html>{html_content}</html>"
            else:
                html_content = f"<html><body>{html_content}</body></html>"

        # Ensure closing tags
        if "<html>" in html_content and "</html>" not in html_content:
            html_content += "</html>"

        if "<body>" in html_content and "</body>" not in html_content:
            html_content = html_content.replace("</html>", "</body></html>")

        return html_content

    def _generate_fallback_html(self, client_name: str, case_type: str, error_message: str) -> str:
        """Generate fallback HTML content when main generation fails.

        Args:
        ----
            client_name: Client name
            case_type: Case type
            error_message: Error description

        Returns:
        -------
            Fallback HTML content

        """
        return f"""<html>
<body>
<p>We have completed our review of your {case_type.lower()} matter. Due to a
technical issue during document generation, we are providing this preliminary
communication.</p>

<p>We are currently analyzing the details of your case and will provide a
comprehensive findings letter within 24 hours. Our initial review indicates
that your matter requires immediate attention and strategic consideration.</p>

<p><strong>Immediate Next Steps:</strong></p>
<ul>
<li>We will contact you within 24 hours with a detailed analysis</li>
<li>Please preserve all relevant documents and communications</li>
<li>Do not take any action regarding this matter until we provide guidance</li>
</ul>

<p>If you have urgent questions or concerns, please contact our office
immediately. We are committed to providing you with thorough legal guidance
and will resolve this technical issue promptly.</p>

<p>Thank you for your patience as we ensure you receive the most accurate and
comprehensive legal analysis possible.</p>
</body>
</html>"""

    def _generate_minimal_fallback_html(self) -> str:
        """Generate minimal fallback HTML when all else fails."""
        return """<html>
<body>
<p>We are currently preparing your legal analysis and will contact you shortly with detailed findings.</p>
<p>Please contact our office if you have any immediate concerns.</p>
</body>
</html>"""

    def _prepare_request_config(self, model: Optional[str] = None) -> Dict[str, Any]:
        """Prepare OpenAI request configuration.

        Args:
        ----
            model: Optional model override

        Returns:
        -------
            Configuration dictionary for OpenAI request

        """
        logger.debug(
            "Preparing OpenAI request configuration",
            extra={
                "method": "_prepare_request_config",
                "hypothesis_id": "configuration_setup",
                "stage": "entry",
                "model_provided": model is not None,
            },
        )

        config = get_openai_config()
        final_model = model or config["model"]

        request_config = {
            "model": final_model,
            "timeout": config["timeout"],
            "max_retries": config["max_retries"],
            "temperature": config["temperature"],
            "max_tokens": config["max_tokens"],
        }

        logger.debug(
            "Request configuration prepared",
            extra={
                "method": "_prepare_request_config",
                "hypothesis_id": "configuration_setup",
                "stage": "exit",
                "model": final_model,
                "temperature": request_config["temperature"],
                "max_tokens": request_config["max_tokens"],
            },
        )

        return request_config

    def _execute_openai_request(self, config: Dict[str, Any], prompt: str) -> Any:
        """Execute the core OpenAI API request.

        Args:
        ----
            config: Request configuration
            prompt: Prompt to send

        Returns:
        -------
            OpenAI response object

        """
        logger.debug(
            "Executing OpenAI API request",
            extra={
                "method": "_execute_openai_request",
                "hypothesis_id": "api_execution",
                "stage": "entry",
                "prompt_length": len(prompt),
                "model": config["model"],
            },
        )

        response = self.client.with_options(
            timeout=config["timeout"], max_retries=config["max_retries"]
        ).chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
        )

        logger.debug(
            "OpenAI API request executed successfully",
            extra={
                "method": "_execute_openai_request",
                "hypothesis_id": "api_execution",
                "stage": "exit",
                "model": config["model"],
                "response_received": response is not None,
            },
        )

        return response

    def _handle_retryable_errors(self, error: Exception, context: Dict[str, Any]) -> None:
        """Handle retryable OpenAI errors that should trigger retry logic."""
        error_type = type(error).__name__

        logger.warning(
            f"Retryable OpenAI error encountered: {error_type}",
            extra={
                "method": "_handle_retryable_errors",
                "hypothesis_id": "retryable_error_handling",
                "error_type": error_type,
                "error_details": str(error),
                "model": context.get("model"),
                "will_retry": True,
            },
        )

        # Re-raise to trigger tenacity retry logic
        raise error

    def _handle_authentication_errors(self, error: Exception, context: Dict[str, Any]) -> None:
        """Handle authentication-related OpenAI errors."""
        error_type = type(error).__name__

        logger.error(
            f"Authentication error: {error_type}",
            extra={
                "method": "_handle_authentication_errors",
                "hypothesis_id": "authentication_error_handling",
                "error_type": error_type,
                "error_details": str(error),
                "model": context.get("model"),
                "requires_api_key_check": True,
            },
        )

    def _handle_client_errors(self, error: Exception, context: Dict[str, Any]) -> None:
        """Handle client-side OpenAI errors."""
        error_type = type(error).__name__

        logger.error(
            f"Client error: {error_type}",
            extra={
                "method": "_handle_client_errors",
                "hypothesis_id": "client_error_handling",
                "error_type": error_type,
                "error_details": str(error),
                "model": context.get("model"),
                "prompt_start": context.get("prompt", "")[:200],
            },
        )

    def _handle_server_errors(self, error: Exception, context: Dict[str, Any]) -> None:
        """Handle server-side OpenAI errors."""
        error_type = type(error).__name__
        request_id = getattr(error, "request_id", "unknown")
        status_code = getattr(error, "status_code", "unknown")

        logger.error(
            f"Server error: {error_type}",
            extra={
                "method": "_handle_server_errors",
                "hypothesis_id": "server_error_handling",
                "error_type": error_type,
                "status_code": status_code,
                "request_id": request_id,
                "model": context.get("model"),
            },
        )

    def _handle_unexpected_errors(self, error: Exception, context: Dict[str, Any]) -> None:
        """Handle unexpected errors during OpenAI requests."""
        error_type = type(error).__name__

        logger.error(
            f"Unexpected error: {error_type}",
            extra={
                "method": "_handle_unexpected_errors",
                "hypothesis_id": "unexpected_error_handling",
                "error_type": error_type,
                "error_details": str(error),
                "model": context.get("model"),
                "prompt_start": context.get("prompt", "")[:200],
            },
        )

    def _validate_openai_response(self, response: Any, context: Dict[str, Any]) -> Optional[str]:
        """Validate OpenAI response and extract content.

        Args:
        ----
            response: OpenAI response object
            context: Request context for logging

        Returns:
        -------
            Response content or None if invalid

        """
        logger.debug(
            "Validating OpenAI response",
            extra={
                "method": "_validate_openai_response",
                "hypothesis_id": "response_validation",
                "stage": "entry",
                "model": context.get("model"),
            },
        )

        request_id = getattr(response, "_request_id", "unknown")
        content = response.choices[0].message.content

        if not content or not content.strip():
            logger.error(
                "OpenAI returned empty content",
                extra={
                    "method": "_validate_openai_response",
                    "hypothesis_id": "response_validation",
                    "request_id": request_id,
                    "model": context.get("model"),
                    "content_empty": True,
                },
            )
            return None

        logger.info(
            "OpenAI response validated successfully",
            extra={
                "method": "_validate_openai_response",
                "hypothesis_id": "response_validation",
                "stage": "exit",
                "request_id": request_id,
                "response_length": len(content),
                "model": context.get("model"),
            },
        )

        return content

    def get_citation_map(self):
        """Get the current citation map from the citation service.

        Returns
        -------
            Current CitationMap or None if not available

        """
        return self.citation_service.current_citation_map if self.citation_service else None

    def get_citation_summary(self) -> Dict[str, Any]:
        """Get citation summary for the current letter.

        Returns
        -------
            Citation summary dictionary

        """
        return self.citation_service.get_citation_summary() if self.citation_service else {}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type(
            (
                RateLimitError,
                APIError,
                APITimeoutError,
                APIConnectionError,
                InternalServerError,
            )
        ),
    )
    def _make_openai_request(self, prompt: str, model: Optional[str] = None) -> Optional[str]:
        """Make OpenAI API request with comprehensive error handling following OpenAI best practices."""
        logger.debug(
            "OpenAI API request initiated",
            extra={
                "method": "_make_openai_request",
                "hypothesis_id": "openai_api_failure",
                "stage": "entry",
                "prompt_length": len(prompt),
                "model_provided": model is not None,
                "config_available": self.config is not None,
            },
        )

        # Prepare request configuration
        config = self._prepare_request_config(model)
        context = {"model": config["model"], "prompt": prompt}

        logger.info(
            "Making OpenAI request",
            extra={
                "method": "_make_openai_request",
                "hypothesis_id": "openai_api_failure",
                "model": config["model"],
                "prompt_length": len(prompt),
                "temperature": config["temperature"],
                "max_tokens": config["max_tokens"],
            },
        )

        try:
            # Execute the API request
            response = self._execute_openai_request(config, prompt)

            # Validate and return response content
            return self._validate_openai_response(response, context)

        except (
            APIConnectionError,
            RateLimitError,
            APITimeoutError,
            APIError,
            InternalServerError,
        ) as e:
            self._handle_retryable_errors(e, context)
        except (AuthenticationError, PermissionDeniedError) as e:
            self._handle_authentication_errors(e, context)
            return None
        except (BadRequestError, UnprocessableEntityError) as e:
            self._handle_client_errors(e, context)
            return None
        except APIStatusError as e:
            self._handle_server_errors(e, context)
            return None
        except (ValueError, TypeError, AttributeError, KeyError, OSError) as e:
            self._handle_unexpected_errors(e, context)
            return None
