from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

import markdown2
from legal_portal.config.default import get_openai_config
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
    """Simplified service for generating HTML content using a single master prompt."""

    def __init__(self, client: OpenAI, config: Dict[str, Any]):
        self.client = client
        self.config = config

    def _load_prompt_template(self) -> str:
        """Loads the prompt template from a file."""
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "findings_letter_prompt.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Prompt template file not found at: {prompt_path}")
            raise ValueError(f"Findings letter prompt template not found at {prompt_path}")

    def generate_html_letter(self, intake_data: str, document_summaries: str) -> str:
        """Generate HTML letter content using the single master prompt."""
        logger.info("Starting HTML letter generation using master prompt")
        try:
            prompt_template = self._load_prompt_template()

            formatted_prompt = prompt_template.format(
                intake_data=intake_data, document_summaries=document_summaries
            )

            logger.info("Making OpenAI request with master prompt for Markdown generation using gpt-4o.")
            markdown_response = self._make_openai_request(formatted_prompt, model="gpt-4o")

            if not markdown_response or not markdown_response.strip():
                error_msg = "OpenAI returned empty response for Markdown generation"
                logger.error(error_msg)
                raise ValueError(error_msg)

            logger.info("Converting Markdown response to HTML")
            html_content = self._convert_markdown_to_html(markdown_response)

            logger.info(
                "Successfully generated HTML letter",
                extra={"html_length": len(html_content)},
            )
            return html_content

        except Exception as e:
            logger.exception("Unexpected error in HTML letter generation")
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
            wrapped_html = f'<div class="legal-letter">\\n{html_content}\\n</div>'

            # Ensure proper HTML structure
            if not wrapped_html.startswith("<html"):
                wrapped_html = f"<html>\\n<body>\\n{wrapped_html}\\n</body>\\n</html>"

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
            return "<html><body><p>Error converting document to HTML.</p></body></html>"

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
        cleaned = re.sub(r"^```markdown\\s*", "", response_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"^```\\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        # Remove any HTML tags that might have been included accidentally
        cleaned = re.sub(r"<[^>]+>", "", cleaned)

        return cleaned

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

        # GPT-5 models use different parameter names
        is_gpt5 = config["model"].startswith("gpt-5")

        request_params = {
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
        }

        # GPT-5 models use max_completion_tokens and don't support custom temperature
        if is_gpt5:
            request_params["max_completion_tokens"] = config["max_tokens"]
            # GPT-5 only supports temperature=1 (default), so don't set it
        else:
            request_params["temperature"] = config["temperature"]
            request_params["max_tokens"] = config["max_tokens"]

        response = self.client.with_options(
            timeout=config["timeout"], max_retries=config["max_retries"]
        ).chat.completions.create(**request_params)

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
