"""
OpenAI Integration Service

Handles all OpenAI API interactions for email generation.
This service is responsible for:
- Making requests to OpenAI API
- Building and managing prompts for different content sections
- Handling API errors, retries, and rate limiting
- Managing API configuration and parameters

This replaces OpenAI-related methods from the original EmailGeneratorV2 class.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import openai

from .shared_utils import shared_utils


logger = logging.getLogger(__name__)


@dataclass
class OpenAIRequest:
    """Data class for OpenAI request parameters."""

    prompt: str
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    system_message: Optional[str] = None


class OpenAIIntegrationService:
    """
    Manages all OpenAI API interactions for email generation.

    This service centralizes AI operations, making it easier to manage
    API keys, handle errors, and implement rate limiting.
    """

    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4"):
        """
        Initialize the OpenAI integration service.

        Args:
            api_key: OpenAI API key (optional, can use environment variable)
            default_model: Default model to use for requests
        """
        self.api_key = api_key
        self.default_model = default_model
        self.max_retries = 3
        self.retry_delay = 1.0

        # Set up OpenAI client
        if api_key:
            openai.api_key = api_key

        # Request tracking for rate limiting
        self.request_timestamps = []
        self.max_requests_per_minute = 50  # Conservative limit

    def make_openai_request(self, request: OpenAIRequest) -> str:
        """
        Make a request to OpenAI API with error handling and retries.

        Args:
            request: OpenAI request parameters

        Returns:
            Generated content from OpenAI
        """
        # Check rate limiting
        self._enforce_rate_limit()

        for attempt in range(self.max_retries):
            try:
                # Prepare messages
                messages = []

                if request.system_message:
                    messages.append(
                        {"role": "system", "content": request.system_message}
                    )

                messages.append({"role": "user", "content": request.prompt})

                # Make API call
                response = openai.ChatCompletion.create(
                    model=request.model or self.default_model,
                    messages=messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )

                # Extract content
                content = response.choices[0].message.content

                # Track successful request
                self.request_timestamps.append(time.time())

                logger.info(f"OpenAI request successful on attempt {attempt + 1}")
                return content.strip()

            except openai.error.RateLimitError as e:
                logger.warning(f"Rate limit hit on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))

            except openai.error.APIError as e:
                logger.error(f"OpenAI API error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

        # All retries failed
        logger.error("All OpenAI request attempts failed")
        return "Error generating content. Please try again later."

    def build_enhanced_prompt(
        self,
        base_prompt: str,
        case_context: Dict[str, Any],
        section_type: str = "general",
    ) -> str:
        """
        Build an enhanced prompt with context and section-specific instructions.

        Args:
            base_prompt: Base prompt text
            case_context: Context information about the case
            section_type: Type of section being generated

        Returns:
            Enhanced prompt with context
        """
        # Section-specific instructions
        section_instructions = {
            "factual_summary": "Focus on objective facts and timeline. Avoid legal conclusions.",
            "legal_analysis": "Provide detailed legal analysis with relevant statutes and case law.",
            "evidence_review": "Systematically review and evaluate available evidence.",
            "recommendations": "Provide clear, actionable recommendations based on analysis.",
        }

        # Build enhanced prompt
        enhanced_parts = []

        # Add section-specific instructions
        if section_type in section_instructions:
            enhanced_parts.append(
                f"SECTION FOCUS: {section_instructions[section_type]}"
            )
            enhanced_parts.append("")

        # Add case context if available
        if case_context:
            enhanced_parts.append("CASE CONTEXT:")
            for key, value in case_context.items():
                if value and key != "raw_content":  # Skip empty values and raw content
                    enhanced_parts.append(f"- {key.replace('_', ' ').title()}: {value}")
            enhanced_parts.append("")

        # Add the main prompt
        enhanced_parts.append("INSTRUCTIONS:")
        enhanced_parts.append(base_prompt)

        # Add formatting requirements
        enhanced_parts.append("")
        enhanced_parts.append("OUTPUT REQUIREMENTS:")
        enhanced_parts.append("- Use clear, professional language")
        enhanced_parts.append("- Structure content with proper paragraphs")
        enhanced_parts.append("- Focus on clarity and readability")
        enhanced_parts.append("- Avoid unnecessary legal jargon")

        return "\n".join(enhanced_parts)

    def generate_factual_summary(self, case_data: Dict[str, Any]) -> str:
        """
        Generate factual summary content using OpenAI.

        Args:
            case_data: Case information and context

        Returns:
            Generated factual summary
        """
        base_prompt = """
        Create a clear, objective factual summary based on the provided case information.
        The summary should include:
        - Key dates and timeline
        - Parties involved
        - Relevant factual circumstances
        - Important events or incidents
        
        Focus only on facts, not legal analysis or opinions.
        """

        enhanced_prompt = self.build_enhanced_prompt(
            base_prompt, case_data, "factual_summary"
        )

        request = OpenAIRequest(
            prompt=enhanced_prompt,
            model=self.default_model,
            temperature=0.5,  # Lower temperature for factual content
            system_message="You are a legal professional creating objective factual summaries.",
        )

        return self.make_openai_request(request)

    def generate_legal_analysis(self, case_data: Dict[str, Any]) -> str:
        """
        Generate legal analysis content using OpenAI.

        Args:
            case_data: Case information and context

        Returns:
            Generated legal analysis
        """
        base_prompt = """
        Provide a comprehensive legal analysis of the case based on the factual summary.
        The analysis should include:
        - Applicable laws and regulations
        - Relevant legal precedents
        - Analysis of legal issues and claims
        - Strengths and weaknesses of the case
        
        Provide detailed legal reasoning and cite relevant authorities where applicable.
        """

        enhanced_prompt = self.build_enhanced_prompt(
            base_prompt, case_data, "legal_analysis"
        )

        request = OpenAIRequest(
            prompt=enhanced_prompt,
            model=self.default_model,
            temperature=0.6,
            system_message="You are an experienced attorney providing legal analysis.",
        )

        return self.make_openai_request(request)

    def generate_evidence_review(self, case_data: Dict[str, Any]) -> str:
        """
        Generate evidence review content using OpenAI.

        Args:
            case_data: Case information and context

        Returns:
            Generated evidence review
        """
        base_prompt = """
        Conduct a systematic review of the available evidence in this case.
        The review should include:
        - Documentary evidence analysis
        - Witness testimony evaluation
        - Physical evidence assessment
        - Evidence strengths and limitations
        - Additional evidence needs
        
        Provide objective evaluation of evidence quality and relevance.
        """

        enhanced_prompt = self.build_enhanced_prompt(
            base_prompt, case_data, "evidence_review"
        )

        request = OpenAIRequest(
            prompt=enhanced_prompt,
            model=self.default_model,
            temperature=0.5,
            system_message="You are a legal professional conducting evidence review.",
        )

        return self.make_openai_request(request)

    def generate_recommendations(self, case_data: Dict[str, Any]) -> str:
        """
        Generate recommendations content using OpenAI.

        Args:
            case_data: Case information and context

        Returns:
            Generated recommendations
        """
        base_prompt = """
        Based on the factual summary, legal analysis, and evidence review, provide clear
        recommendations for this case. Include:
        - Immediate action items
        - Case strategy recommendations
        - Risk assessment and mitigation
        - Next steps and timeline
        - Alternative approaches to consider
        
        Provide practical, actionable recommendations that can be implemented.
        """

        enhanced_prompt = self.build_enhanced_prompt(
            base_prompt, case_data, "recommendations"
        )

        request = OpenAIRequest(
            prompt=enhanced_prompt,
            model=self.default_model,
            temperature=0.7,
            system_message="You are a senior attorney providing strategic recommendations.",
        )

        return self.make_openai_request(request)

    def _enforce_rate_limit(self):
        """
        Enforce rate limiting to avoid hitting API limits.
        """
        current_time = time.time()

        # Remove timestamps older than 1 minute
        self.request_timestamps = [
            ts for ts in self.request_timestamps if current_time - ts < 60
        ]

        # Check if we're at the limit
        if len(self.request_timestamps) >= self.max_requests_per_minute:
            sleep_time = 60 - (current_time - self.request_timestamps[0])
            if sleep_time > 0:
                logger.info(
                    f"Rate limit approaching, sleeping for {sleep_time:.2f} seconds"
                )
                time.sleep(sleep_time)

    def update_api_key(self, new_api_key: str):
        """
        Update the OpenAI API key.

        Args:
            new_api_key: New API key to use
        """
        self.api_key = new_api_key
        openai.api_key = new_api_key
        logger.info("OpenAI API key updated")

    def update_default_model(self, new_model: str):
        """
        Update the default model to use for requests.

        Args:
            new_model: New default model name
        """
        self.default_model = new_model
        logger.info(f"Default model updated to: {new_model}")
