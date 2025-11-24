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

    async def generate_findings_letter_adaptive(
        self,
        intake_content: str,
        fact_matrix,  # FactMatrix
        legal_analysis,  # DeepAnalysis
        structure_guidance,  # LetterStructure
        verified_statutes: list,
        attorney_name: str = None,
        firm_name: str = None,
        confirmed_qa_pairs: list = None,
        contact_phone: str = None,
        contact_email: str = None,
        quality_context: str = "",
        clio_matter_context: str = "",
    ) -> str:
        """Generate findings letter using multi-stage analysis results.

        This method uses structured analysis from MultiStageAnalyzer to generate
        an attorney-quality letter with adaptive structure based on case complexity.

        Args:
        ----
            intake_content: Extracted text from intake form
            fact_matrix: FactMatrix with structured facts from Stage 1
            legal_analysis: DeepAnalysis with comprehensive analysis from Stage 3
            structure_guidance: LetterStructure determining format from Stage 4
            verified_statutes: List of verified statutes from corpus
            attorney_name: Attorney name for signature
            firm_name: Firm name for signature
            confirmed_qa_pairs: User-confirmed Q&A pairs
            contact_phone: Contact phone number
            contact_email: Contact email
            quality_context: Quality assessment context
            clio_matter_context: CLIO matter context

        Returns:
        -------
            HTML letter content

        """
        # --- STRUCTURE OVERRIDE START ---
        # Robustness check: Ensure structure matches complexity rules (Updated Nov 2025)
        # This allows "Regenerate Letter" to work with updated logic without re-running analysis
        try:
            num_issues = len(legal_analysis.issue_analyses)
            current_style = structure_guidance.style

            # Check if using numbered format for 1-6 issues
            if current_style == "numbered_findings" and num_issues <= 6:
                # Check if truly complex procedures exist (excluding standard Chapter 558)
                has_complex_procedures = False
                for issue in legal_analysis.issue_analyses:
                    if issue.procedural_requirements:
                        for req in issue.procedural_requirements:
                            req_lower = req.requirement.lower()
                            if (
                                "chapter 558" in req_lower
                                or "60 day" in req_lower
                                or "pre-suit notice" in req_lower
                            ):
                                continue
                            has_complex_procedures = True
                            break
                    if has_complex_procedures:
                        break

                # If no truly complex procedures, FORCE simple bullets
                if not has_complex_procedures:
                    logger.warning(
                        f"Overriding letter structure from {current_style} to simple_bullets "
                        f"(Issues: {num_issues} <= 6, no complex procedures)"
                    )
                    structure_guidance.style = "simple_bullets"
                    structure_guidance.intro = "Here are the key points of our analysis:"
                    structure_guidance.issue_format = "bullet_paragraphs"
                    structure_guidance.reasoning = (
                        f"Auto-corrected: Simple/moderate case with {num_issues} issues"
                    )
        except Exception as e:
            logger.warning(f"Structure override check failed (using original): {e}")
        # --- STRUCTURE OVERRIDE END ---

        logger.info(
            f"Generating adaptive letter with {structure_guidance.style} structure",
            extra={"structure": structure_guidance.style, "issues": len(legal_analysis.issue_analyses)},
        )

        # Format Q&A pairs for prompt context
        qa_context = ""
        if confirmed_qa_pairs:
            qa_context = "USER-CONFIRMED INTAKE QUESTIONS & ANSWERS:\n\n"
            for i, qa in enumerate(confirmed_qa_pairs, 1):
                qa_context += f"{i}. Q: {qa.get('question', 'N/A')}\n   A: {qa.get('answer', 'N/A')}\n\n"
            logger.info(f"Including {len(confirmed_qa_pairs)} confirmed Q&A pairs")
        else:
            qa_context = "No user-confirmed Q&A pairs available."

        # Load enhanced prompt template
        template_content = self._load_prompt_template()

        # Extract attorney info if not provided
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

        # Contact info
        contact_phone_value = contact_phone if contact_phone else "(727) 275-9575"
        contact_email_value = contact_email if contact_email else "[EMAIL PLACEHOLDER]"

        # Format structured analysis for prompt
        structured_context = self._format_multi_stage_context(
            fact_matrix, legal_analysis, structure_guidance, verified_statutes
        )

        # Build statute context
        statute_context = ""
        if verified_statutes:
            statute_context = "\n\nVERIFIED FLORIDA STATUTES:\n\n"
            for statute in verified_statutes:
                statute_context += f"{statute['citation']}: {statute['title']}\n"
                statute_context += f"Summary: {statute['summary']}\n"
                statute_context += f"Relevance: {statute['relevance']}\n\n"

        # Combine contexts
        full_quality_context = quality_context
        if clio_matter_context:
            full_quality_context = f"{full_quality_context}\n\n{clio_matter_context}"

        # Add structure guidance to prompt
        structure_instruction = self._create_structure_instruction(structure_guidance)

        # Format prompt
        prompt = template_content.format(
            qa_context=qa_context,
            intake_data=intake_content[:5000],
            document_summaries=structured_context,  # Use structured analysis instead of raw summaries
            quality_context=full_quality_context,
            statute_context=statute_context,
            attorney_name=attorney_name,
            attorney_title="Senior Partner",
            firm_name=firm_name,
            contact_phone=contact_phone_value,
            contact_email=contact_email_value,
            clio_matter_context=clio_matter_context,
        )

        # Add structure instruction before the closing
        prompt = f"{prompt}\n\n{structure_instruction}"

        logger.info("Making OpenAI request for adaptive letter generation")

        loop = asyncio.get_running_loop()
        markdown_response = await loop.run_in_executor(
            None,
            self._make_openai_request,
            prompt,
            "gpt-4o",
            0.3,
            12000,
            (
                "You are a senior legal writing assistant. Generate an attorney-quality "
                "findings letter following the adaptive structure guidance provided."
            ),
        )

        if not markdown_response or not markdown_response.strip():
            raise ValueError("OpenAI returned empty response for adaptive letter generation")

        # --- FORMATTING POLISH PASS (Second AI Call) ---
        # Apply consistent formatting and layout
        logger.info("Applying formatting polish pass for consistency")
        try:
            # Try relative import first, then absolute
            try:
                from src.legal_portal.utils.letter_polish import LetterPolisher
            except ImportError:
                from legal_portal.utils.letter_polish import LetterPolisher

            polisher = LetterPolisher(self.client)
            polish_result = polisher.polish_letter(markdown_response)

            if polish_result["success"]:
                markdown_response = polish_result["polished_letter"]
                logger.info(
                    f"Formatting polish applied successfully. Changes: {len(polish_result['changes_made'])}",
                    extra={"changes": polish_result["changes_made"]},
                )
            else:
                logger.warning(
                    f"Formatting polish failed: {polish_result.get('error', 'Unknown')}. Using original."
                )
        except Exception as e:
            logger.warning(f"Formatting polish pass failed: {e}. Using original letter.")
        # --- END POLISH PASS ---

        # Convert to HTML
        html_content = self._convert_markdown_to_html(markdown_response)

        logger.info(
            "Successfully generated adaptive letter",
            extra={"html_length": len(html_content), "structure": structure_guidance.style},
        )

        return html_content

    def _format_multi_stage_context(
        self, fact_matrix, legal_analysis, structure_guidance, verified_statutes
    ) -> str:
        """Format multi-stage analysis results for letter generation prompt."""
        import json

        context = "MULTI-STAGE ANALYSIS RESULTS:\n\n"

        # Facts
        context += "FACT MATRIX:\n"
        context += (
            f"Parties: {json.dumps([p.model_dump() for p in fact_matrix.parties], default=str, indent=2)}\n"
        )
        context += (
            f"Timeline: {json.dumps([e.model_dump() for e in fact_matrix.timeline], default=str, indent=2)}\n"
        )
        context += f"Financial Data: {json.dumps([f.model_dump() for f in fact_matrix.financial_data], default=str, indent=2)}\n\n"

        # Legal Analysis
        context += "LEGAL ANALYSIS:\n"
        for analysis in legal_analysis.issue_analyses:
            context += f"\nISSUE: {analysis.issue_name}\n"
            context += f"Legal Standard: {analysis.legal_standard}\n"
            context += f"Application: {analysis.fact_application}\n"
            context += f"Remedies: {', '.join(analysis.remedies_available)}\n"
            if analysis.procedural_requirements:
                context += f"Procedural Requirements: {analysis.procedural_requirements}\n"
            context += f"Confidence: {analysis.confidence_level}\n"

        # Overall Assessment
        context += f"\nOVERALL CASE STRENGTH: {legal_analysis.overall_case_strength}\n"
        context += f"Key Strengths: {', '.join(legal_analysis.key_strengths)}\n"
        context += f"Key Challenges: {', '.join(legal_analysis.key_challenges)}\n"

        return context

    def _create_structure_instruction(self, structure_guidance) -> str:
        """Create structure instruction based on letter structure guidance."""
        instructions = "\n\nSTRUCTURE GUIDANCE:\n\n"

        if structure_guidance.style == "simple_bullets":
            instructions += """Use SIMPLE BULLET LIST format (REQUIRED):

**CRITICAL - You MUST follow this structure:**
1. Section 1: FACTUAL SUMMARY (numbered header)
2. Transition: "Here are the key points of our analysis:"
3. Each legal issue as a BULLET PARAGRAPH (•), NOT as numbered section (2., 3., 4.)
4. Section 2: RECOMMENDED ACTION & NEXT STEPS (final numbered header)

**PROHIBITED in this format:**
❌ Do NOT create sections 2., 3., 4., 5. for each legal issue
❌ Do NOT use "Key Findings" intro
❌ Do NOT use numbered headers for legal issues

**REQUIRED structure example:**
```
1. FACTUAL SUMMARY
[paragraphs]

Here are the key points of our analysis:

• **Implied Warranty & Construction Defects**: [paragraph]
• **Breach of Contract**: [paragraph]
• **Mechanic's Liens**: [paragraph]

2. RECOMMENDED ACTION & NEXT STEPS
[paragraphs]
```

This is a simple to moderate complexity case (1-6 issues)."""

        elif structure_guidance.style == "numbered_findings":
            instructions += """Use NUMBERED FINDINGS format (REQUIRED):

**CRITICAL - You MUST follow this structure:**
1. Section 1: FACTUAL SUMMARY (numbered header)
2. Transition: "Key Findings" (NOT "Here are the key points...")
3. Each legal issue gets its OWN NUMBERED SECTION (2., 3., 4., 5., etc.)
4. Final section: RECOMMENDED ACTION & NEXT STEPS

**REQUIRED in this format:**
✅ Each legal issue has dedicated numbered section with header
✅ Use "Key Findings" intro (not "Here are...")
✅ Include statute citations in headers where applicable

**REQUIRED structure example:**
```
1. FACTUAL SUMMARY
[paragraphs]

Key Findings

2. IMPLIED WARRANTY & CONSTRUCTION DEFECTS (Fla. Stat. Chapter 558)
[dedicated section]

3. BREACH OF CONTRACT
[dedicated section]

4. MECHANIC'S LIENS (Fla. Stat. § 713.06)
[dedicated section]

5. RECOMMENDED ACTION & NEXT STEPS
[paragraphs]
```

This is a complex case (5+ issues or unusual procedures) requiring detailed organization."""

        else:  # hybrid
            instructions += """Use HYBRID format:
- Start with: "Here are the key points of our analysis:"
- Use bullets with subheadings for organization
- Balance formality with accessibility"""

        instructions += f"\n\nReasoning: {structure_guidance.reasoning}\n"

        return instructions

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
