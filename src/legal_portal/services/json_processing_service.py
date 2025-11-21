from __future__ import annotations

import asyncio
import os
import re
from typing import List, Optional, Tuple

import markdown2
from legal_portal.core.data_models import ProcessingError
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger = get_module_logger(__name__)


class JsonProcessingService:
    """Handles interaction with OpenAI for processing structured data."""

    def __init__(self, client: OpenAIClient, config: dict):
        """Initialize the service.

        Args:
        ----
            client: An instance of the custom OpenAIClient wrapper.
            config: Configuration dictionary.

        """
        self.client = client
        self.config = config

    async def process_documents_to_json(self, prompt: str) -> Tuple[Optional[str], List[ProcessingError]]:
        """Process a prompt to get a JSON response from OpenAI asynchronously.

        Args:
        ----
            prompt: The prompt to send to the OpenAI API.

        Returns:
        -------
            A tuple containing the JSON response string and a list of any processing errors.

        """
        try:
            loop = asyncio.get_running_loop()
            # Run the synchronous _make_openai_request in a separate thread
            response_content = await loop.run_in_executor(
                None,  # Use the default thread pool executor
                self._make_openai_request,
                prompt,
            )

            if response_content:
                # Successfully received content, return it with no errors
                return response_content, []
            else:
                # OpenAI returned an empty response
                error_message = "OpenAI returned an empty or null response."
                logger.error(error_message)
                error = ProcessingError(
                    source="JsonProcessingService",
                    error_type="APIError",
                    error_message=error_message,
                )
                return None, [error]

        except Exception as e:
            logger.exception(f"An unexpected error occurred in process_documents_to_json: {e}")
            error = ProcessingError(
                source="JsonProcessingService",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            return None, [error]

    def _load_prompt_template(self) -> str:
        """Load the prompt template from a file."""
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "findings_letter_prompt.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError as e:
            logger.error(f"Prompt template file not found at: {prompt_path}")
            raise ValueError(f"Findings letter prompt template not found at {prompt_path}") from e

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

    async def generate_findings_letter_from_json(
        self,
        intake_content: str,
        document_summaries_json: str,
        quality_context: str = "",
        attorney_name: str = None,
        firm_name: str = None,
        confirmed_qa_pairs: list = None,
        contact_phone: str = None,
        contact_email: str = None,
        statute_context: str = "",
        clio_matter_context: str = "",
    ) -> str:
        """Generate findings letter from structured JSON summaries.

        Args:
        ----
            intake_content: Extracted text from intake form
            document_summaries_json: JSON string of structured DocumentSummaryStructured objects
            quality_context: Formatted quality assessment results
            attorney_name: Attorney name for signature (optional, will extract from intake if not provided)
            firm_name: Firm name for signature (optional, will extract from intake if not provided)
            confirmed_qa_pairs: User-confirmed question-answer pairs from intake form review
            contact_phone: Contact phone for letter footer (optional, uses placeholder if not provided)
            contact_email: Contact email for letter footer
                (optional, uses placeholder if not provided)
            statute_context: Context about relevant Florida statutes for the case
            clio_matter_context: Rich context from CLIO matter including timeline,
                party relationships, communication patterns

        Returns:
        -------
            HTML letter content

        """
        logger.info("Generating letter from structured JSON input")

        # Format Q&A pairs for prompt context
        qa_context = ""
        if confirmed_qa_pairs:
            qa_context = "USER-CONFIRMED INTAKE QUESTIONS & ANSWERS:\n\n"
            for i, qa in enumerate(confirmed_qa_pairs, 1):
                question = qa.get("question", "N/A")
                answer = qa.get("answer", "N/A")
                qa_context += f"{i}. Q: {question}\n   A: {answer}\n\n"
            logger.info(f"Including {len(confirmed_qa_pairs)} user-confirmed Q&A pairs in letter generation")
        else:
            qa_context = "No user-confirmed Q&A pairs available."
            logger.info("No confirmed Q&A pairs provided for letter generation")

        # Load enhanced prompt template
        template_content = self._load_prompt_template()

        # Extract attorney name from intake if not provided
        if not attorney_name:
            import re

            attorney_match = re.search(r'"attorney_name":\s*"([^"]+)"', intake_content, re.IGNORECASE)
            if not attorney_match:
                attorney_match = re.search(r'"attorneyName":\s*"([^"]+)"', intake_content)
            attorney_name = attorney_match.group(1) if attorney_match else "Senior Partner"

        if not firm_name:
            import re

            firm_match = re.search(r'"firm_name":\s*"([^"]+)"', intake_content, re.IGNORECASE)
            firm_name = firm_match.group(1) if firm_match else ""

        # Use provided contact info or fallback to defaults/placeholders
        contact_phone_value = contact_phone if contact_phone else "(727) 275-9575"
        contact_email_value = contact_email if contact_email else "[EMAIL PLACEHOLDER]"

        logger.info(
            f"Contact info for letter: phone={'provided' if contact_phone else 'default'}, "
            f"email={'provided' if contact_email else 'placeholder'}"
        )

        # Keep statute context separate for prominence in prompt
        statute_context_formatted = statute_context if statute_context else ""

        # Only append CLIO context to quality_context
        full_quality_context = quality_context
        if clio_matter_context:
            full_quality_context = f"{full_quality_context}\n\n{clio_matter_context}"
            logger.info("Added CLIO matter context to letter generation prompt")

        if statute_context_formatted:
            logger.info("Statute context will be prominently placed in prompt")

        # Format prompt with JSON input and signature variables
        prompt = template_content.format(
            qa_context=qa_context,  # NEW: User-confirmed Q&A pairs
            intake_data=intake_content[:5000],
            document_summaries=document_summaries_json,  # Pass JSON directly
            quality_context=full_quality_context,
            statute_context=statute_context_formatted,  # Prominent statute context
            attorney_name=attorney_name,
            attorney_title="Senior Partner",  # Default title
            firm_name=firm_name,
            contact_phone=contact_phone_value,
            contact_email=contact_email_value,
            clio_matter_context=clio_matter_context,  # CLIO context for enhanced letter generation
        )

        logger.info("Making OpenAI request for letter generation from JSON")

        loop = asyncio.get_running_loop()
        markdown_response = await loop.run_in_executor(
            None,  # Use the default thread pool executor
            self._make_openai_request,
            prompt,
            "gpt-4o",  # model
            0.3,  # temperature
            12000,  # max_tokens
            (  # system_message
                "You are a senior legal writing assistant helping to draft professional "
                "client findings letters. Follow the template structure exactly and "
                "provide comprehensive, well-reasoned legal analysis."
            ),
        )

        if not markdown_response or not markdown_response.strip():
            raise ValueError("OpenAI returned empty response for letter generation")

        # Convert to HTML
        html_content = self._convert_markdown_to_html(markdown_response)

        logger.info("Successfully generated letter from JSON", extra={"html_length": len(html_content)})

        return html_content

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

        cleaned = response_text.strip()

        # Remove code fences with language specifiers (```html, ```markdown, etc.)
        # Match opening fence with optional language specifier at start
        cleaned = re.sub(r"^\s*```(?:html|markdown|md)?\s*\n?", "", cleaned, flags=re.MULTILINE)

        # Remove closing code fences
        cleaned = re.sub(r"\n?\s*```\s*$", "", cleaned, flags=re.MULTILINE)

        # Clean up any remaining stray code fences (in case of multiple wrappings)
        cleaned = re.sub(r"```(?:html|markdown|md)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?\s*```", "", cleaned)

        cleaned = cleaned.strip()

        # DO NOT remove HTML tags - the AI should be generating markdown, not HTML
        # The markdown will be converted to HTML later
        # If the AI accidentally includes some HTML, markdown2 will handle it gracefully

        return cleaned

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
        self,
        prompt: str,
        model: Optional[str] = "gpt-4o",
        temperature: float = 0.3,
        max_tokens: int = 12000,
        system_message: str = None,
    ) -> Optional[str]:
        """Make OpenAI API request with comprehensive error handling following OpenAI best practices."""
        # Default system message for JSON output (document analysis)
        if system_message is None:
            system_message = "You are a helpful assistant designed to output JSON."

        logger.info(
            "Making OpenAI request",
            extra={
                "method": "_make_openai_request",
                "hypothesis_id": "openai_api_failure",
                "model": model,
                "prompt_length": len(prompt),
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

        try:
            response_dict = self.client.create_chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response_dict["content"]
        except Exception as e:
            logger.exception(f"An error occurred during the OpenAI request: {e}")
            # Depending on desired behavior, you might want to return None or re-raise
            return None
