from __future__ import annotations

import asyncio
import os
import re
from typing import List, Optional, Tuple, AsyncGenerator, Dict

import markdown2
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from legal_portal.core.data_models import ProcessingError
from legal_portal.utils.logging_config import get_module_logger
from legal_portal.utils.openai_client import OpenAIClient
from legal_portal.utils.diagnostic_logger import DiagnosticLogger

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

    JURISDICTION_CONFIG = {
        "Florida": {
            "name": "Florida",
            "name_upper": "FLORIDA",
            "statute_example": "Fla. Stat. § 718.116",
            "statute_citation_prefix": "Florida Statute §",
            "statute_citation_short_prefix": "Fla. Stat. §",
            "guidance_file": "florida_guidance.md",
        },
        "New Mexico": {
            "name": "New Mexico",
            "name_upper": "NEW MEXICO",
            "statute_example": "N.M. Stat. Ann. § 57-12-2",
            "statute_citation_prefix": "N.M. Stat. Ann. §",
            "statute_citation_short_prefix": "NMSA 1978 §",
            "guidance_file": "new_mexico_guidance.md",
        },
    }

    def _load_prompt_template(self, jurisdiction: str = "Florida") -> str:
        """Load the prompt template from a file and inject jurisdiction-specific guidance."""
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "findings_letter_prompt.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()

            # Dynamically load jurisdiction-specific guidance
            guidance_file_name = self.JURISDICTION_CONFIG.get(jurisdiction, {}).get("guidance_file")
            jurisdiction_specific_guidance = ""
            if guidance_file_name:
                guidance_path = os.path.join(
                    os.path.dirname(__file__), "..", "prompts", "jurisdiction_guidance", guidance_file_name
                )
                if os.path.exists(guidance_path):
                    with open(guidance_path, "r", encoding="utf-8") as f_guidance:
                        jurisdiction_specific_guidance = f_guidance.read()
                else:
                    logger.warning(f"Jurisdiction-specific guidance file not found: {guidance_path}")
            else:
                logger.warning(f"No guidance file configured for jurisdiction: {jurisdiction}")

            # Get jurisdiction-specific citation prefixes for prompt formatting
            juris_config = self.JURISDICTION_CONFIG.get(jurisdiction, self.JURISDICTION_CONFIG["Florida"])
            jurisdiction_name = juris_config["name"]
            jurisdiction_name_upper = juris_config["name_upper"]
            statute_citation_prefix = juris_config["statute_citation_prefix"]
            statute_citation_short_prefix = juris_config["statute_citation_short_prefix"]
            statute_example = juris_config["statute_example"]

            # Format the template with dynamic values
            # We use double braces for placeholders that should remain for the second formatting pass
            return template.format(
                jurisdiction=jurisdiction,
                jurisdiction_name=jurisdiction_name,
                jurisdiction_name_upper=jurisdiction_name_upper,
                jurisdiction_statute_citation_prefix=statute_citation_prefix,
                jurisdiction_statute_citation_short_prefix=statute_citation_short_prefix,
                jurisdiction_statute_example=statute_example,
                jurisdiction_specific_guidance=jurisdiction_specific_guidance,
                # Other placeholders will be filled by the calling function
                qa_context="{qa_context}",
                intake_data="{intake_data}",
                document_summaries="{document_summaries}",
                quality_context="{quality_context}",
                statute_context="{statute_context}",
                attorney_name="{attorney_name}",
                attorney_title="{attorney_title}",
                firm_name="{firm_name}",
                contact_phone="{contact_phone}",
                contact_email="{contact_email}",
                clio_matter_context="{clio_matter_context}",
            )
        except FileNotFoundError as e:
            logger.error(f"Prompt template file not found at: {prompt_path}")
            raise ValueError(f"Findings letter prompt template not found at {prompt_path}") from e

    def generate_html_letter(
        self, intake_data: str, document_summaries: str, jurisdiction: str = "Florida"
    ) -> str:
        """Generate HTML letter content using the single master prompt."""
        logger.info(f"Starting HTML letter generation for {jurisdiction} using master prompt")
        try:
            prompt_template = self._load_prompt_template(jurisdiction=jurisdiction)

            formatted_prompt = prompt_template.format(
                intake_data=intake_data,
                document_summaries=document_summaries,
                # Provide empty values for other placeholders to avoid KeyError
                qa_context="",
                quality_context="",
                statute_context="",
                attorney_name="Attorney",
                attorney_title="Partner",
                firm_name="",
                contact_phone="",
                contact_email="",
                clio_matter_context="",
            )

            logger.info(f"Making OpenAI request with master prompt for {jurisdiction} using gpt-4o.")
            markdown_response = self._make_openai_request_responses_api(
                formatted_prompt, 
                model="gpt-4o",
                reasoning_effort="low",
                verbosity="high"
            )

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
        jurisdiction: str = "Florida",  # Added jurisdiction parameter
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
            statute_context: Context about relevant statutes for the case
            clio_matter_context: Rich context from CLIO matter including timeline,
                party relationships, communication patterns
            jurisdiction: State jurisdiction (e.g., "Florida", "New Mexico")

        Returns:
        -------
            HTML letter content

        """
        logger.info(f"Generating letter for {jurisdiction} from structured JSON input")

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

        # Load enhanced prompt template with jurisdiction-specific guidance pre-injected
        prompt_template = self._load_prompt_template(jurisdiction=jurisdiction)

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
        if not contact_phone:
            contact_phone = "(727) 275-9575" if jurisdiction == "Florida" else "(505) 555-0199"
        contact_email_value = contact_email if contact_email else "[EMAIL PLACEHOLDER]"

        # Keep statute context separate for prominence in prompt
        statute_context_formatted = statute_context if statute_context else ""

        # Only append CLIO context to quality_context
        full_quality_context = quality_context
        if clio_matter_context:
            full_quality_context = f"{full_quality_context}\n\n{clio_matter_context}"
            logger.info("Added CLIO matter context to letter generation prompt")

        # Format prompt with JSON input and signature variables
        # Note: _load_prompt_template already formatted jurisdiction-specific fields
        prompt = prompt_template.format(
            qa_context=qa_context,
            intake_data=intake_content[:5000],
            document_summaries=document_summaries_json,  # Pass JSON directly
            quality_context=full_quality_context,
            statute_context=statute_context_formatted,  # Prominent statute context
            attorney_name=attorney_name,
            attorney_title="Senior Partner",  # Default title
            firm_name=firm_name,
            contact_phone=contact_phone,
            contact_email=contact_email_value,
            clio_matter_context=clio_matter_context,
        )

        logger.info("Making OpenAI request for letter generation from JSON")

        loop = asyncio.get_running_loop()
        markdown_response = await loop.run_in_executor(
            None,  # Use the default thread pool executor
            self._make_openai_request_responses_api,
            prompt,
            "gpt-4o",  # model
            "low",  # reasoning_effort
            "high",  # verbosity
            12000,  # max_output_tokens
            (  # instructions
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
        jurisdiction: str = "Florida",  # Added jurisdiction parameter
        diag_logger: Optional[DiagnosticLogger] = None,
        original_documents: Optional[Dict[str, str]] = None, # NEW: Explicit raw content
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
            jurisdiction: State jurisdiction (e.g., "Florida", "New Mexico")

        Returns:
        -------
            HTML letter content

        """
        # All cases now use natural_flow format - no structure override needed
        # The analyzer always returns natural_flow regardless of complexity
        num_issues = len(legal_analysis.issue_analyses)
        logger.info(
            f"Generating natural flow letter for {jurisdiction} with {num_issues} issues",
            extra={"structure": "natural_flow", "issues": num_issues, "jurisdiction": jurisdiction},
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

        # Load enhanced prompt template with jurisdiction-specific guidance pre-injected
        prompt_template = self._load_prompt_template(jurisdiction=jurisdiction)

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
        if not contact_phone:
            contact_phone = "(727) 275-9575" if jurisdiction == "Florida" else "(505) 555-0199"
        contact_email_value = contact_email if contact_email else "[EMAIL PLACEHOLDER]"

        # Format structured analysis for prompt
        structured_context = self._format_multi_stage_context(
            fact_matrix, legal_analysis, structure_guidance, verified_statutes,
            original_documents=original_documents
        )

        # Build statute context
        statute_context = ""
        if verified_statutes:
            statute_prefix = "FLORIDA" if jurisdiction == "Florida" else "NEW MEXICO"
            statute_context = f"\n\nVERIFIED {statute_prefix} STATUTES:\n\n"
            for statute in verified_statutes:
                statute_context += f"{statute['citation']}: {statute['title']}\n"
                statute_context += f"Summary: {statute['summary']}\n"
                statute_context += f"Relevance: {statute['relevance']}\n\n"

        # Combine contexts
        full_quality_context = quality_context
        if clio_matter_context:
            full_quality_context = f"{full_quality_context}\n\n{clio_matter_context}"

        # Add structure instruction before the closing
        structure_instruction = self._create_structure_instruction(structure_guidance)

        # Format prompt
        # Note: _load_prompt_template already formatted jurisdiction-specific fields
        prompt = prompt_template.format(
            qa_context=qa_context,
            intake_data=intake_content[:5000],
            document_summaries=structured_context,  # Use structured analysis instead of raw summaries
            quality_context=full_quality_context,
            statute_context=statute_context,
            attorney_name=attorney_name,
            attorney_title="Senior Partner",
            firm_name=firm_name,
            contact_phone=contact_phone,
            contact_email=contact_email_value,
            clio_matter_context=clio_matter_context,
        )

        # Add structure instruction before the closing
        prompt = f"{prompt}\n\n{structure_instruction}"

        logger.info("Making OpenAI request for adaptive letter generation")

        loop = asyncio.get_running_loop()
        markdown_response = await loop.run_in_executor(
            None,
            self._make_openai_request_responses_api,
            prompt,
            "gpt-4o",
            "low",
            "high",
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

        # Stage 5: Log Final Letter
        if diag_logger:
            diag_logger.log_stage("stage5_final_letter", html_content, {
                "jurisdiction": jurisdiction,
                "num_issues": num_issues,
                "attorney_name": attorney_name
            })

        logger.info(
            "Successfully generated natural flow letter",
            extra={"html_length": len(html_content), "structure": "natural_flow"},
        )

        return html_content

    async def stream_findings_letter_adaptive(
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
        jurisdiction: str = "Florida",
        original_documents: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream adaptive findings letter generation.

        Note: This bypasses the formatting polish pass for real-time delivery.
        """
        # Format structured analysis for prompt
        structured_context = self._format_multi_stage_context(
            fact_matrix, legal_analysis, structure_guidance, verified_statutes,
            original_documents=original_documents
        )

        # Build statute context
        statute_context = ""
        if verified_statutes:
            statute_prefix = "FLORIDA" if jurisdiction == "Florida" else "NEW MEXICO"
            statute_context = f"\n\nVERIFIED {statute_prefix} STATUTES:\n\n"
            for statute in verified_statutes:
                statute_context += f"{statute['citation']}: {statute['title']}\n"
                statute_context += f"Summary: {statute['summary']}\n"
                statute_context += f"Relevance: {statute['relevance']}\n\n"

        # Combine contexts
        full_quality_context = quality_context
        if clio_matter_context:
            full_quality_context = f"{full_quality_context}\n\n{clio_matter_context}"

        # Load enhanced prompt template
        prompt_template = self._load_prompt_template(jurisdiction=jurisdiction)

        # Signature details
        attorney_name = attorney_name or "Senior Partner"
        contact_phone = contact_phone or ("(727) 275-9575" if jurisdiction == "Florida" else "(505) 555-0199")
        contact_email_value = contact_email or "[EMAIL PLACEHOLDER]"

        # Format prompt
        prompt = prompt_template.format(
            qa_context=confirmed_qa_pairs or "No user-confirmed Q&A pairs available.",
            intake_data=intake_content[:5000],
            document_summaries=structured_context,
            quality_context=full_quality_context,
            statute_context=statute_context,
            attorney_name=attorney_name,
            attorney_title="Senior Partner",
            firm_name=firm_name or "",
            contact_phone=contact_phone,
            contact_email=contact_email_value,
            clio_matter_context=clio_matter_context,
        )

        # Add structure instruction
        structure_instruction = self._create_structure_instruction(structure_guidance)
        prompt = f"{prompt}\n\n{structure_instruction}"

        logger.info(f"Streaming adaptive findings letter for {jurisdiction}")
        
        async for token in self.client.create_response_stream(
            model="gpt-4o",
            instructions=(
                "You are a senior legal writing assistant. Generate an attorney-quality "
                "findings letter following the adaptive structure guidance provided."
            ),
            input=prompt,
            reasoning_effort="low",
            verbosity="high",
        ):
            yield token

    def _format_multi_stage_context(
        self, fact_matrix, legal_analysis, structure_guidance, verified_statutes, original_documents: Optional[Dict[str, str]] = None
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
        context += (
            f"Financial Data: "
            f"{json.dumps([f.model_dump() for f in fact_matrix.financial_data], default=str, indent=2)}\n\n"
        )

        # Original Documents (Enabled for Quality Debugging)
        if original_documents:
            context += "--- FULL DOCUMENT CONTENT (for precision and citations) ---\n"
            for filename, content in original_documents.items():
                context += f"\nDOCUMENT: {filename}\n"
                # Limit to first 10k chars to avoid extreme token counts
                doc_content = content[:10000]
                if len(content) > 10000:
                    doc_content += "\n... [truncated for brevity]"
                context += f"{doc_content}\n"
            context += "--- END DOCUMENT CONTENT ---\n\n"

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

        # Case Viability Assessment
        context += "\n--- CASE VIABILITY ASSESSMENT ---\n"
        context += f"IS_VIABLE: {legal_analysis.is_viable}\n"
        context += f"RECOMMEND_DEMAND_LETTER: {legal_analysis.recommend_demand_letter}\n"
        if legal_analysis.viability_reasoning:
            context += f"VIABILITY_REASONING: {legal_analysis.viability_reasoning}\n"

        return context

    def _create_structure_instruction(self, structure_guidance) -> str:
        """Create structure instruction based on letter structure guidance."""
        instructions = "\n\nSTRUCTURE GUIDANCE:\n\n"

        # All cases now use natural flow format - no formal section headers
        instructions += """Use NATURAL FLOW format (REQUIRED):

**CRITICAL - The letter should read like professional correspondence, NOT a legal memo.**

**STRUCTURE:**
1. Warm greeting: "Good afternoon [Name]," or "Good morning [Name],"
2. Opening: Documents reviewed + property address + primary concern in plain English
3. Factual narrative: 2-3 paragraphs describing what happened (NO formal "FACTUAL SUMMARY" header)
4. Transition: "Here are the key points of our analysis:"
5. Legal points as flowing bullet paragraphs (each bullet is a complete paragraph, NO bold headers)
6. Recommendations paragraph: "Based on the above, a negotiated resolution..."
7. Protective checklist if client needs to take action (with explanations)
8. Call to action: "Please let us know if you would like us to proceed..."
9. Signature and disclaimer

**PROHIBITED:**
- Do NOT use formal section headers like "FACTUAL SUMMARY" or "RECOMMENDED ACTION"
- Do NOT use bold issue titles in bullets (like "**Implied Warranty**:")
- Do NOT use "Key Findings" intro
- Do NOT use numbered sections for legal issues (2., 3., 4.)

**REQUIRED - PLAIN LANGUAGE:**
- Every legal term must be explained in plain English
- Use "What this means for you:" or similar to explain practical impact
- Use analogies clients understand ("like a hold on your property")

**REQUIRED structure example:**
```
Good afternoon Mr. Devlin and Ms. Bell,

I hope you are doing well. I wanted to follow up with a summary of our
findings after reviewing [documents], regarding your property at [address].

As discussed, the primary concern is [plain English statement of issue].

Based on our review, we understand that [2-3 paragraphs of facts without formal headers]...

Here are the key points of our analysis:

- Under Florida law, there's a protection called an "implied warranty" -- this
means contractors are legally required to do competent work, even if your
contract doesn't say so. In your case, [application]. What this means for
you: [practical impact].

- Before you can sue a contractor in Florida, you must follow a process under
Chapter 558. Think of it as a required 'cool-down period.' [explanation].
For you, this means [practical impact].

- You received a Notice to Owner -- this is a warning that [explanation in
plain English]. Here's why this matters: [consequence chain]. This is
preventable if we act now.

Based on the above, a negotiated resolution would likely be your most
efficient path forward. [Specific recommendations with timeline].

If you decide to [action], here's what you need to do:
- [Step with explanation of why]
- [Step with explanation of why]

Please let us know if you would like us to proceed with [action], or whether
you would prefer that we first set a phone call to discuss.

Thank you,
[Signature]

[Disclaimer]
```
"""

        instructions += f"\n\nAdditional context: {structure_guidance.reasoning}\n"

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
        """Make OpenAI API request with comprehensive error handling (legacy Chat Completions API)."""
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
    def _make_openai_request_responses_api(
        self,
        prompt: str,
        model: Optional[str] = "gpt-4o",
        reasoning_effort: Optional[str] = "low",
        verbosity: Optional[str] = "high",
        max_output_tokens: int = 12000,
        instructions: str = None,
    ) -> Optional[str]:
        """Make OpenAI API request using Responses API with reasoning and verbosity controls."""
        # Default instructions
        if instructions is None:
            instructions = "You are a helpful assistant designed to output JSON."

        logger.info(
            "Making Responses API request",
            extra={
                "method": "_make_openai_request_responses_api",
                "model": model,
                "prompt_length": len(prompt),
                "reasoning_effort": reasoning_effort,
                "verbosity": verbosity,
                "max_output_tokens": max_output_tokens,
            },
        )

        try:
            response_dict = self.client.create_response(
                model=model,
                input=prompt,
                instructions=instructions,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
                max_output_tokens=max_output_tokens,
            )
            return response_dict["content"]
        except Exception as e:
            logger.exception(f"An error occurred during the Responses API request: {e}")
            # Depending on desired behavior, you might want to return None or re-raise
            return None
