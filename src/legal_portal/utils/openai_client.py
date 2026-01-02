"""OpenAI API client and interaction handling for AI analysis components."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, AsyncGenerator

import httpx
import openai
from openai import OpenAI, AsyncOpenAI

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class OpenAIClient:
    """Handles all OpenAI API interactions and response processing."""

    def __init__(self, user_preferences: Optional[Dict[str, str]] = None):
        """Initialize OpenAI client with proper timeout and connection settings.

        Args:
        ----
            user_preferences: Optional dict of user AI model preferences by operation type
                             e.g., {"document_analysis": "gpt-4o", "letter_generation": "gpt-4o"}

        """
        # Configure HTTP client with appropriate timeouts for cloud environments
        timeout = httpx.Timeout(
            connect=10.0,  # Connection timeout
            read=60.0,  # Read timeout
            write=30.0,  # Write timeout
            pool=120.0,  # Pool timeout
        )
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)

        # Sync client
        http_client = httpx.Client(timeout=timeout, limits=limits)
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client, max_retries=3)

        # Async client for streaming and parallel processing
        async_http_client = httpx.AsyncClient(timeout=timeout, limits=limits)
        self.async_client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"), http_client=async_http_client, max_retries=3
        )

        self.default_model = "gpt-5.2"
        self.fallback_model = "gpt-5-mini"
        self.max_retries = 3
        self.base_retry_delay = 2  # Base delay in seconds for exponential backoff

        # Store user preferences for model selection
        self.user_preferences = user_preferences or {}

    def get_preferred_model(self, operation_type: str, fallback: str = "gpt-4o") -> str:
        """Get the user's preferred model for a specific operation type.

        Args:
        ----
            operation_type: Type of operation (e.g., "document_analysis", "letter_generation")
            fallback: Fallback model if no preference is set

        Returns:
        -------
            Model name to use

        """
        return self.user_preferences.get(operation_type, fallback)

    def _extract_json_content(self, content: str) -> str:
        """Intelligently extract a JSON string from the API response.

        Handles both plain JSON and JSON wrapped in Markdown code blocks.
        """
        # Check for plain JSON
        if content.strip().startswith("{") or content.strip().startswith("["):
            return content

        # Primary regex for JSON in markdown block
        primary_match = re.search(r"```(?:json)?\s*([\{\[][^`]*[\}\]])\s*```", content, re.DOTALL)
        if primary_match:
            return primary_match.group(1)

        # Fallback regex for simpler markdown block
        fallback_match = re.search(r"```\s*([\{\[][^`]*[\}\]])\s*```", content, re.DOTALL)
        if fallback_match:
            return fallback_match.group(1)

        return content

    def analyze_with_prompt(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send prompt to OpenAI and get analysis response."""
        model = model or self.default_model

        logger.info(f"OPENAI CLIENT: 🤖 Starting analysis with {model}")
        logger.info(f"OPENAI CLIENT: 🤖   - Temperature: {temperature}")
        logger.info(f"OPENAI CLIENT: 🤖   - Max tokens: {max_tokens or 'default'}")

        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a legal analysis expert. Provide thorough, accurate, and "
                                "professional analysis based on the provided information."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                content = response.choices[0].message.content

                # Track usage
                usage = response.usage
                logger.info("OPENAI CLIENT: 📊 API usage:")
                logger.info(f"OPENAI CLIENT: 📊   - Prompt tokens: {usage.prompt_tokens:,}")
                logger.info(f"OPENAI CLIENT: 📊   - Completion tokens: {usage.completion_tokens:,}")
                logger.info(f"OPENAI CLIENT: 📊   - Total tokens: {usage.total_tokens:,}")

                return {
                    "success": True,
                    "content": content,
                    "model_used": model,
                    "usage": {
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "total_tokens": usage.total_tokens,
                    },
                    "attempt": attempt + 1,
                }

            except openai.RateLimitError as e:
                logger.error(
                    f"OPENAI CLIENT: ⚠️  Rate limit error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    # Exponential backoff: 2s, 4s, 8s...
                    delay = self.base_retry_delay * (2**attempt)
                    logger.warning(f"OPENAI CLIENT: ⏳ Waiting {delay}s before retry...")
                    time.sleep(delay)
                else:
                    return self._create_error_response("Rate limit exceeded", e)

            except openai.APIError as e:
                logger.error(f"OPENAI CLIENT: ❌ API error (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    delay = self.base_retry_delay * (2**attempt)
                    logger.warning(f"OPENAI CLIENT: ⏳ Waiting {delay}s before retry...")
                    time.sleep(delay)
                else:
                    return self._create_error_response("API error", e)

            except Exception as e:
                logger.error(
                    f"OPENAI CLIENT: ❌ Unexpected error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt < self.max_retries - 1:
                    delay = self.base_retry_delay * (2**attempt)
                    logger.warning(f"OPENAI CLIENT: ⏳ Waiting {delay}s before retry...")
                    time.sleep(delay)
                else:
                    return self._create_error_response("Unexpected error", e)

        return self._create_error_response("Max retries exceeded", None)

    def analyze_with_fallback(
        self,
        prompt: str,
        primary_model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Analyze with primary model, fall back to secondary if needed."""
        primary_model = primary_model or self.default_model

        logger.info(f"OPENAI CLIENT: 🔄 Attempting analysis with primary model: {primary_model}")

        # Try primary model
        result = self.analyze_with_prompt(prompt, primary_model, temperature, max_tokens)

        if result["success"]:
            return result

        # Try fallback model
        logger.error(f"OPENAI CLIENT: 🔄 Primary model failed, trying fallback: {self.fallback_model}")

        fallback_result = self.analyze_with_prompt(prompt, self.fallback_model, temperature, max_tokens)

        if fallback_result["success"]:
            fallback_result["fallback_used"] = True
            fallback_result["primary_model_attempted"] = primary_model
            return fallback_result

        # Both failed
        logger.error("OPENAI CLIENT: ❌ Both primary and fallback models failed")
        return self._create_error_response("Both models failed", None)

    def parse_json_response(self, content: str) -> Dict[str, Any]:
        """Parse a JSON response from a string.

        Intelligently handles plain JSON or JSON embedded in a Markdown code block.
        Returns a standardized response format like other OpenAI client methods.
        """
        if not content:
            logger.warning("Attempted to parse empty content.")
            return {"success": False, "error": "Empty content provided", "data": None}

        extracted_content = self._extract_json_content(content)

        try:
            parsed_data = json.loads(extracted_content)
            return {"success": True, "data": parsed_data, "error": None}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON after extraction: {e}")
            logger.debug(f"Content that failed parsing: {extracted_content[:500]}")  # Log first 500 chars
            return {"success": False, "error": f"JSON decode error: {e}", "data": None}

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Estimate cost of API call based on token usage."""
        # Pricing as of 2025 (prices per 1K tokens)
        pricing = {
            "gpt-5.2": {"input": 0.01, "output": 0.03},
            "gpt-5.2-pro": {"input": 0.015, "output": 0.045},
            "gpt-5-mini": {"input": 0.0001, "output": 0.0004},
            "gpt-4o": {"input": 0.005, "output": 0.015},
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-32k": {"input": 0.06, "output": 0.12},
        }

        if model not in pricing:
            logger.info(f"OPENAI CLIENT: ⚠️  Unknown model for cost estimation: {model}")
            return 0.0

        model_pricing = pricing[model]
        input_cost = (prompt_tokens / 1000) * model_pricing["input"]
        output_cost = (completion_tokens / 1000) * model_pricing["output"]
        total_cost = input_cost + output_cost

        logger.info("OPENAI CLIENT: 💰 Estimated cost:")
        logger.info(f"OPENAI CLIENT: 💰   - Input: ${input_cost:.4f}")
        logger.info(f"OPENAI CLIENT: 💰   - Output: ${output_cost:.4f}")
        logger.info(f"OPENAI CLIENT: 💰   - Total: ${total_cost:.4f}")

        return total_cost

    def validate_api_key(self) -> bool:
        """Validate that OpenAI API key is properly configured."""
        try:
            # Make a minimal API call to test the key
            self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=1,
            )
            logger.info("OPENAI CLIENT: ✅ API key validation successful")
            return True
        except Exception as e:
            logger.error(f"OPENAI CLIENT: ❌ API key validation failed: {e}")
            return False

    def get_available_models(self) -> List[str]:
        """Get list of available models."""
        try:
            models = self.client.models.list()
            model_names = [model.id for model in models.data if "gpt" in model.id.lower()]
            logger.info(f"OPENAI CLIENT: 📋 Available GPT models: {len(model_names)}")
            return sorted(model_names)
        except Exception as e:
            logger.error(f"OPENAI CLIENT: ❌ Failed to get available models: {e}")
            return [self.default_model, self.fallback_model]

    def create_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Provide standard interface for chat completions across all services.

        This is the single unified method for making OpenAI chat completion requests.
        All services should use this method instead of calling the SDK directly.

        Args:
        ----
            model: Model to use (e.g., "gpt-4o", "gpt-4o-mini")
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate (None for model default)
            response_format: Optional dict to specify response format (e.g., {"type": "json_object"})

        Returns:
        -------
            Dictionary with:
                - content: The text response from the model
                - usage: Dict with prompt_tokens, completion_tokens, total_tokens
                - model: The model used

        Raises:
        ------
            Exception: On API errors (logged internally)

        """
        try:
            logger.info(
                f"Making chat completion request with {model}",
                extra={
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "message_count": len(messages),
                },
            )

            # Build request parameters
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }

            if max_tokens is not None:
                request_params["max_tokens"] = max_tokens

            if response_format is not None:
                request_params["response_format"] = response_format

            # Make the API call
            response = self.client.chat.completions.create(**request_params)

            content = response.choices[0].message.content
            usage = response.usage

            logger.info(
                "Chat completion successful",
                extra={
                    "model": model,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "response_length": len(content) if content else 0,
                },
            )

            return {
                "content": content,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "model": model,
            }

        except openai.RateLimitError as e:
            logger.error(f"Rate limit error: {e}")
            raise
        except openai.APIError as e:
            logger.error(f"API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in chat completion: {e}")
            raise

    async def create_chat_completion_async(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Async version of create_chat_completion for parallel processing.

        Args:
        ----
            model: Model to use (e.g., "gpt-4o", "gpt-4o-mini")
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate (None for model default)
            response_format: Optional dict to specify response format (e.g., {"type": "json_object"})

        Returns:
        -------
            Dictionary with:
                - content: The text response from the model
                - usage: Dict with prompt_tokens, completion_tokens, total_tokens
                - model: The model used

        Raises:
        ------
            Exception: On API errors (logged internally)

        """
        try:
            logger.info(
                f"Making async chat completion request with {model}",
                extra={
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "message_count": len(messages),
                },
            )

            # Build request parameters
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }

            if max_tokens is not None:
                request_params["max_tokens"] = max_tokens

            if response_format is not None:
                request_params["response_format"] = response_format

            # Make the API call
            response = await self.async_client.chat.completions.create(**request_params)

            content = response.choices[0].message.content
            usage = response.usage

            logger.info(
                "Async chat completion successful",
                extra={
                    "model": model,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "response_length": len(content) if content else 0,
                },
            )

            return {
                "content": content,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "model": model,
            }

        except openai.RateLimitError as e:
            logger.error(f"Async rate limit error: {e}")
            raise
        except openai.APIError as e:
            logger.error(f"Async API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in async chat completion: {e}")
            raise

    async def create_chat_completion_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion tokens.

        Args:
        ----
            model: Model to use (e.g., "gpt-4o", "gpt-4o-mini")
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate (None for model default)

        Yields:
        ------
            Tokens as they are generated by the model.

        """
        try:
            logger.info(f"Starting async chat stream with {model}")

            stream = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Error in async chat stream: {e}")
            raise

    def create_response(
        self,
        model: str,
        input: str,
        instructions: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        verbosity: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a response using Chat Completions API with GPT-5.2 parameters.
        
        Uses Chat Completions API with GPT-5.2 specific parameters:
        - reasoning_effort: Controls reasoning depth (none, low, medium, high, xhigh)
        - verbosity: Controls output length (low, medium, high)
        - max_output_tokens: Maximum output tokens (replaces max_tokens for GPT-5)
        """
        try:
            logger.info(
                f"Making GPT-5 Chat Completions request with {model}",
                extra={
                    "model": model,
                    "reasoning_effort": reasoning_effort,
                    "verbosity": verbosity,
                },
            )

            # Build messages from input and instructions
            messages = []
            if instructions:
                messages.append({"role": "system", "content": instructions})
            messages.append({"role": "user", "content": input})

            # Build request parameters for Chat Completions API
            request_params = {
                "model": model,
                "messages": messages,
            }

            # GPT-5.2 uses extra_body for new parameters not yet in SDK
            extra_body = {}
            
            # Add reasoning_effort for GPT-5 models
            if reasoning_effort:
                extra_body["reasoning_effort"] = reasoning_effort
            
            # Add verbosity for GPT-5 models
            if verbosity:
                extra_body["verbosity"] = verbosity
            
            # Use max_output_tokens for GPT-5 models (not max_tokens)
            if max_output_tokens:
                extra_body["max_output_tokens"] = max_output_tokens
            
            if extra_body:
                request_params["extra_body"] = extra_body

            # Make the API call using Chat Completions
            response = self.client.chat.completions.create(**request_params)

            content = response.choices[0].message.content
            usage = response.usage

            logger.info(
                "GPT-5 Chat Completions call successful",
                extra={
                    "model": model,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
            )

            return {
                "content": content,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "model": model,
            }

        except Exception as e:
            logger.error(f"Error in GPT-5 Chat Completions call: {e}")
            raise

    async def create_response_async(
        self,
        model: str,
        input: str,
        instructions: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        verbosity: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Async version of create_response using Chat Completions API with GPT-5.2 parameters."""
        try:
            logger.info(f"Making async GPT-5 Chat Completions request with {model}")

            # Build messages from input and instructions
            messages = []
            if instructions:
                messages.append({"role": "system", "content": instructions})
            messages.append({"role": "user", "content": input})

            request_params = {
                "model": model,
                "messages": messages,
            }

            # GPT-5.2 uses extra_body for new parameters
            extra_body = {}
            
            if reasoning_effort:
                extra_body["reasoning_effort"] = reasoning_effort
            
            if verbosity:
                extra_body["verbosity"] = verbosity
            
            if max_output_tokens:
                extra_body["max_output_tokens"] = max_output_tokens
            
            if extra_body:
                request_params["extra_body"] = extra_body

            response = await self.async_client.chat.completions.create(**request_params)

            content = response.choices[0].message.content
            usage = response.usage

            return {
                "content": content,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "model": model,
            }

        except Exception as e:
            logger.error(f"Error in async GPT-5 Chat Completions call: {e}")
            raise

    async def create_response_stream(
        self,
        model: str,
        input: str,
        instructions: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        verbosity: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens using Chat Completions API with GPT-5.2 parameters."""
        try:
            logger.info(f"Starting async GPT-5 Chat Completions stream with {model}")

            # Build messages from input and instructions
            messages = []
            if instructions:
                messages.append({"role": "system", "content": instructions})
            messages.append({"role": "user", "content": input})

            request_params = {
                "model": model,
                "messages": messages,
                "stream": True,
            }

            # GPT-5.2 uses extra_body for new parameters
            extra_body = {}
            
            if reasoning_effort:
                extra_body["reasoning_effort"] = reasoning_effort
            
            if verbosity:
                extra_body["verbosity"] = verbosity
            
            if extra_body:
                request_params["extra_body"] = extra_body

            stream = await self.async_client.chat.completions.create(**request_params)

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Error in async Chat Completions stream: {e}")
            raise

    def _create_error_response(self, error_type: str, exception: Optional[Exception]) -> Dict[str, Any]:
        """Create standardized error response."""
        return {
            "success": False,
            "error": error_type,
            "content": None,
            "exception": str(exception) if exception else None,
            "model_used": None,
            "usage": None,
        }

    def analyze_intake_form(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Analyze intake form with specific settings."""
        logger.info("OPENAI CLIENT: 📝 Analyzing intake form")
        return self.analyze_with_fallback(
            prompt=prompt,
            primary_model=model or self.default_model,
            temperature=0.1,
            max_tokens=1500,
        )

    def analyze_case_documents(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Analyze case documents with specific settings."""
        logger.info("OPENAI CLIENT: 📄 Analyzing case documents")
        return self.analyze_with_fallback(
            prompt=prompt,
            primary_model=model or self.default_model,
            temperature=0.2,
            max_tokens=2000,
        )

    def summarize_media(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Summarize media content with specific settings."""
        logger.info("OPENAI CLIENT: 🎥 Summarizing media content")
        return self.analyze_with_fallback(
            prompt=prompt,
            primary_model=model or self.default_model,
            temperature=0.3,
            max_tokens=1000,
        )

    def generate_final_assessment(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Generate final assessment with specific settings."""
        logger.info("OPENAI CLIENT: 📊 Generating final assessment")
        return self.analyze_with_fallback(
            prompt=prompt,
            primary_model=model or self.default_model,
            temperature=0.1,
            max_tokens=3000,
        )
