from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

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

from backend.utils.data_models import CaseAnalysisResult
from backend_logic.config import get_openai_config
from utils.logging_config import get_module_logger


logger = get_module_logger(__name__)


class JsonProcessingService:
    """
    Simplified service for generating HTML content using the new single master prompt.

    This refactored service aligns with the new architectural approach:
    - Uses a single, authoritative master prompt
    - Injects CaseAnalysisResult directly into the prompt
    - Generates HTML directly instead of multi-step JSON processing
    - Removes complex multi-prompt chaining logic
    """

    def __init__(self, client: OpenAI, config: Dict[str, Any]):
        self.client = client
        self.config = config

    def generate_html_letter(self, analysis: CaseAnalysisResult) -> str:
        """
        Generate HTML letter content using the single master prompt.

        This replaces the old generate_structured_json method with a simplified
        approach that directly generates the final HTML letter.

        Args:
            analysis: Complete case analysis result

        Returns:
            Generated HTML letter content
        """
        try:
            logger.info("Starting HTML letter generation using master prompt")

            # Extract client information from analysis
            client_name = (
                analysis.intake_analysis.client_name
                if analysis.intake_analysis
                else "Client"
            )
            case_type = (
                analysis.intake_analysis.case_type
                if analysis.intake_analysis
                else "Legal Matter"
            )

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

                with open(
                    "validation_output/final_analysis_data.json", "w", encoding="utf-8"
                ) as f:
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
            if not master_prompt:
                raise ValueError("Master prompt not found in configuration")

            # Inject case analysis directly into the master prompt
            formatted_prompt = master_prompt.format(
                client_name=client_name,
                case_type=case_type,
                analysis=analysis.model_dump_json(indent=2),
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
                with open(
                    "validation_output/final_prompt.txt", "w", encoding="utf-8"
                ) as f:
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

            logger.info("Making OpenAI request with master prompt")
            html_response = self._make_openai_request(formatted_prompt)

            if not html_response or not html_response.strip():
                raise ValueError("OpenAI returned empty response for HTML generation")

            # Clean and validate the HTML response
            cleaned_html = self._clean_html_response(html_response)
            validated_html = self._validate_html_structure(cleaned_html)

            logger.info(
                "Successfully generated HTML letter",
                extra={
                    "html_length": len(validated_html),
                    "client_name": client_name,
                    "case_type": case_type,
                },
            )
            return validated_html

        except Exception as e:
            logger.exception(
                "HTML letter generation failed",
                extra={
                    "client_name": client_name,
                    "case_type": case_type,
                    "error_type": type(e).__name__,
                },
            )
            return self._generate_fallback_html(client_name, case_type, str(e))

    def _clean_html_response(self, response_text: str) -> str:
        """
        Clean OpenAI response to extract valid HTML.

        Args:
            response_text: Raw OpenAI response

        Returns:
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
        """
        Validate HTML structure and ensure basic compliance.

        Args:
            html_content: HTML content to validate

        Returns:
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

    def _generate_fallback_html(
        self, client_name: str, case_type: str, error_message: str
    ) -> str:
        """
        Generate fallback HTML content when main generation fails.

        Args:
            client_name: Client name
            case_type: Case type
            error_message: Error description

        Returns:
            Fallback HTML content
        """
        return f"""<html>
<body>
<p>We have completed our review of your {case_type.lower()} matter. Due to a technical issue during document generation, we are providing this preliminary communication.</p>

<p>We are currently analyzing the details of your case and will provide a comprehensive findings letter within 24 hours. Our initial review indicates that your matter requires immediate attention and strategic consideration.</p>

<p><strong>Immediate Next Steps:</strong></p>
<ul>
<li>We will contact you within 24 hours with a detailed analysis</li>
<li>Please preserve all relevant documents and communications</li>
<li>Do not take any action regarding this matter until we provide guidance</li>
</ul>

<p>If you have urgent questions or concerns, please contact our office immediately. We are committed to providing you with thorough legal guidance and will resolve this technical issue promptly.</p>

<p>Thank you for your patience as we ensure you receive the most accurate and comprehensive legal analysis possible.</p>
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
        """
        Prepare OpenAI request configuration.

        Args:
            model: Optional model override

        Returns:
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
        """
        Execute the core OpenAI API request.

        Args:
            config: Request configuration
            prompt: Prompt to send

        Returns:
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

    def _handle_retryable_errors(
        self, error: Exception, context: Dict[str, Any]
    ) -> None:
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

    def _handle_authentication_errors(
        self, error: Exception, context: Dict[str, Any]
    ) -> None:
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

    def _handle_unexpected_errors(
        self, error: Exception, context: Dict[str, Any]
    ) -> None:
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

    def _validate_openai_response(
        self, response: Any, context: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate OpenAI response and extract content.

        Args:
            response: OpenAI response object
            context: Request context for logging

        Returns:
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
    def _make_openai_request(
        self, prompt: str, model: Optional[str] = None
    ) -> Optional[str]:
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
