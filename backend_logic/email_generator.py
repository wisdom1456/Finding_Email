from __future__ import annotations

import json
import re
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from utils.logging_config import setup_logging


logger = setup_logging("email_generator")

from openai import (
    OpenAI,
)
from pydantic import BaseModel, Field

from backend.utils.data_models import (
    CaseAnalysisResult,
    EmailStructurePlan,
    GeneratedLetter,
    GenerationContext,
    SectionPlan,
)
from backend.utils.validators import (
    validate_next_steps_formatting,
    validate_section_output,
)
from backend_logic.email_generation.services.config_and_template_loader import (
    ConfigAndTemplateLoader,
)
from backend_logic.email_generation.services.content_extraction_service import (
    ContentExtractionService,
)
from backend_logic.email_generation.services.content_formatting_service import (
    ContentFormattingService,
)
from backend_logic.email_generation.services.json_processing_service import (
    JsonProcessingService,
)
from backend_logic.email_generation.services.prompt_and_api_service import (
    PromptAndApiService,
)


def regex_replace_filter(s, find, replace):
    """A custom Jinja2 filter for regex replacement."""
    if s is None:
        return ""
    return re.sub(find, replace, str(s))


# === ENHANCED DATA MODELS FOR REFACTORED ARCHITECTURE ===


class GenerationOutput(BaseModel):
    """Enhanced output structure for email generation with debugging capabilities."""

    letter: GeneratedLetter
    debug_info: Optional[Dict[str, Any]] = None
    validation_results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    generation_metadata: Dict[str, Any] = Field(default_factory=dict)


class DebugOutput(BaseModel):
    """Detailed debug information for testing and validation."""

    input_validation: Dict[str, Any] = Field(default_factory=dict)
    structure_plan: Optional[Dict[str, Any]] = None
    generated_sections: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    field_mapping: Dict[str, Any] = Field(default_factory=dict)
    validation_results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    errors: List[Dict[str, str]] = Field(default_factory=list)
    generation_time: Optional[float] = None


class SectionValidationError(ValueError):
    """Raised when a section fails validation."""


class EmailGenerationError(Exception):
    """Raised when email generation fails completely."""


class EmailReadabilityError(Exception):
    """Raised when email content fails readability requirements after simplification attempts."""


# === CONFIGURATION-DRIVEN EMAIL GENERATION ===


class EmailGeneratorV2:
    """
    Configuration-driven EmailGenerator with linear three-stage pipeline architecture.

    Architecture:
    1. PREPARE: Validate input and create structure plan
    2. GENERATE: Generate each section with proper field mapping
    3. FORMAT: Validate output and ensure all template fields are populated
    """

    def __init__(self, client: OpenAI, config_path: Optional[str] = None) -> None:
        """Initialize the EmailGenerator with OpenAI client, configuration, and Jinja2 environment."""
        if not client:
            msg = "An OpenAI client is required for EmailGenerator."
            raise ValueError(msg)
        self.client = client

        self.config_loader = ConfigAndTemplateLoader()
        self.config = self.config_loader.load_configuration(config_path)
        self.jinja_env = self.config_loader.get_jinja_env(self.config)

        # regex_replace filter removed - logic moved to Python processing

        self.json_service = JsonProcessingService(self.client, self.config)
        self.prompt_api_service = PromptAndApiService(self.config)
        self.content_formatting_service = ContentFormattingService(self.config)
        self.content_extraction_service = ContentExtractionService(self.config)

        logger.info(
            f"EMAIL GENERATOR V2: ✅ Initialized with configuration: {config_path or 'default'}"
        )

    # === STAGE 1: PREPARE - Input Validation and Structure Planning ===

    def generate_email_with_debug(
        self, analysis: CaseAnalysisResult
    ) -> GenerationOutput:
        """
        Main entry point for email generation with enhanced debugging capabilities.
        NEW ARCHITECTURE: Single JSON generation instead of multi-stage HTML processing.
        """
        debug_info = DebugOutput()
        start_time = datetime.now().timestamp()

        try:
            logger.info("EMAIL GENERATOR V2: STAGE 1 - VALIDATE INPUT")
            self._validate_input_analysis(analysis)
            debug_info.input_validation = self._get_validation_summary(analysis)

            logger.info("EMAIL GENERATOR V2: STAGE 2 - GENERATE STRUCTURED JSON")
            # NEW: Generate complete structured JSON in one call
            json_response = self.json_service.generate_structured_json(analysis)

            logger.info("EMAIL GENERATOR V2: STAGE 3 - VALIDATE JSON STRUCTURE")
            # NEW: Validate JSON against our schema
            validated_json = self.json_service.validate_json_response(json_response)

            logger.info("EMAIL GENERATOR V2: STAGE 4 - CONVERT TO LEGACY FORMAT")
            # NEW: Convert JSON to GeneratedLetter for compatibility
            letter = self._convert_json_to_generated_letter(validated_json)

            debug_info.generation_time = datetime.now().timestamp() - start_time
            debug_info.validation_results = self._validate_all_fields(letter)

            return GenerationOutput(
                letter=letter,
                debug_info=debug_info.dict(),
                validation_results=debug_info.validation_results,
                generation_metadata={
                    "generation_time": debug_info.generation_time,
                    "architecture": "structured_json",
                    "json_valid": True,
                },
            )

        except (ValueError, TypeError, AttributeError, KeyError, ImportError) as e:
            error_info = {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "stage": "json_generation",
            }
            debug_info.errors.append(error_info)
            debug_info.generation_time = datetime.now().timestamp() - start_time

            # Return fallback letter with debug info
            fallback_letter = self._create_fallback_letter(analysis, str(e))

            return GenerationOutput(
                letter=fallback_letter,
                debug_info=debug_info.dict(),
                validation_results={"error": True},
                generation_metadata={
                    "generation_time": debug_info.generation_time,
                    "error": str(e),
                    "fallback_used": True,
                    "architecture": "fallback",
                },
            )

    def _validate_input_analysis(self, analysis: CaseAnalysisResult) -> None:
        """Validate that analysis has required components for email generation."""
        if not analysis:
            msg = "Analysis object is required"
            raise EmailGenerationError(msg)

        # Ensure we have basic components
        if not analysis.intake_analysis:
            logger.warning(
                "EMAIL GENERATOR V2: ⚠️  Missing intake_analysis, creating fallback"
            )
            self.content_extraction_service.ensure_analysis_completeness(analysis)

        if not analysis.analyzed_documents:
            logger.info("EMAIL GENERATOR V2: ⚠️  No analyzed documents found")

        logger.info("EMAIL GENERATOR V2: ✅ Input validation complete")

    def _get_validation_summary(self, analysis: CaseAnalysisResult) -> Dict[str, Any]:
        """Get comprehensive validation summary for debugging."""
        return {
            "has_intake_analysis": analysis.intake_analysis is not None,
            "has_legal_assessment": analysis.legal_assessment is not None,
            "analyzed_documents_count": len(analysis.analyzed_documents)
            if analysis.analyzed_documents
            else 0,
            "has_video_insights": bool(analysis.video_insights),
            "has_transcripted_media": bool(analysis.transcripted_media),
            "client_name": analysis.intake_analysis.client_name
            if analysis.intake_analysis
            else None,
            "case_type": analysis.intake_analysis.case_type
            if analysis.intake_analysis
            else None,
        }

    def _create_comprehensive_structure_plan(
        self, analysis: CaseAnalysisResult
    ) -> EmailStructurePlan:
        """Create detailed structure plan for email generation."""
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

        # Create subject line
        subject_line = f"Legal Review and Recommended Next Steps – {case_type}"

        # Create personalized greeting
        if "Devlin" in client_name and "Bell" in client_name:
            greeting = "Good afternoon Mr. Devlin and Ms. Bell,"
        else:
            greeting = f"Good afternoon {client_name},"

        # Plan sections systematically
        sections = []
        section_number = 1

        # 1. FACTUAL SUMMARY
        sections.append(
            SectionPlan(
                number=section_number,
                header="FACTUAL SUMMARY",
                key_points=self.content_extraction_service.extract_key_facts(analysis),
                emphasis_items=self.content_extraction_service.identify_emphasis_items(
                    analysis
                ),
                content_requirements=[
                    "chronological events",
                    "key parties",
                    "important dates and amounts",
                ],
            )
        )
        section_number += 1

        # 2. LEGAL ANALYSIS
        sections.append(
            SectionPlan(
                number=section_number,
                header="LEGAL ANALYSIS",
                key_points=self.content_extraction_service.extract_legal_issues(
                    analysis
                ),
                emphasis_items={},
                content_requirements=[
                    "legal claims",
                    "Florida law application",
                    "case strengths",
                ],
            )
        )
        section_number += 1

        # 3. EVIDENCE REVIEW (if media exists)
        if analysis.transcripted_media or analysis.video_insights:
            sections.append(
                SectionPlan(
                    number=section_number,
                    header="EVIDENCE REVIEW",
                    key_points=self.content_extraction_service.extract_media_evidence_points(
                        analysis
                    ),
                    emphasis_items={},
                    content_requirements=["media analysis", "evidence significance"],
                )
            )
            section_number += 1

        # 4. STRENGTHS AND CHALLENGES
        sections.append(
            SectionPlan(
                number=section_number,
                header="CASE ASSESSMENT",
                key_points=self.content_extraction_service.extract_case_assessment_points(
                    analysis
                ),
                emphasis_items={},
                content_requirements=[
                    "strengths",
                    "challenges",
                    "strategic considerations",
                ],
            )
        )
        section_number += 1

        # 5. RECOMMENDED NEXT STEPS
        sections.append(
            SectionPlan(
                number=section_number,
                header="RECOMMENDED NEXT STEPS",
                key_points=self.content_extraction_service.extract_recommendations(
                    analysis
                ),
                emphasis_items={},
                content_requirements=[
                    "prioritized actions",
                    "timelines",
                    "strategic considerations",
                ],
            )
        )

        # Create professional closing
        if "Devlin" in client_name and "Bell" in client_name:
            closing = "Thank you, and we remain committed to protecting your interests throughout this process."
        else:
            closing = "Please contact our office if you have any questions about this analysis or our recommendations."

        plan = EmailStructurePlan(
            subject_line=subject_line,
            greeting=greeting,
            sections=sections,
            closing=closing,
            case_context={
                "client_name": client_name,
                "case_type": case_type,
                "has_media": bool(
                    analysis.transcripted_media or analysis.video_insights
                ),
                "urgency": analysis.intake_analysis.urgency_level
                if analysis.intake_analysis
                else "Standard",
            },
        )

        logger.info(
            f"EMAIL GENERATOR V2: Created structure plan with {len(sections)} sections"
        )
        return plan

    # === STAGE 2: GENERATE - Section Generation with Proper Mapping ===

    def _generate_all_sections_with_tracking(
        self,
        plan: EmailStructurePlan,
        analysis: CaseAnalysisResult,
        debug_info: DebugOutput,
    ) -> Dict[str, str]:
        """Generate all sections with detailed tracking for debugging."""
        generated_sections = {}
        context = GenerationContext()

        # Generate header/greeting
        logger.info("EMAIL GENERATOR V2: Generating greeting section...")
        greeting_content = self._generate_greeting_section(plan, analysis, context)
        generated_sections["greeting"] = greeting_content
        debug_info.generated_sections["greeting"] = {
            "content_length": len(greeting_content),
            "is_empty": not greeting_content.strip(),
            "first_100_chars": greeting_content[:100] if greeting_content else None,
        }

        # Generate each planned section
        for section_plan in plan.sections:
            logger.info(
                f"EMAIL GENERATOR V2: Generating section: {section_plan.header}"
            )
            try:
                section_content = self._generate_section_with_validation(
                    section_plan, context, analysis
                )
                section_key = self._section_header_to_key(section_plan.header)
                generated_sections[section_key] = section_content

                debug_info.generated_sections[section_key] = {
                    "header": section_plan.header,
                    "content_length": len(section_content),
                    "is_empty": not section_content.strip(),
                    "first_100_chars": section_content[:100]
                    if section_content
                    else None,
                    "validation_passed": bool(
                        section_content and section_content.strip()
                    ),
                }

                # Update context
                context.section_numbers_used.append(section_plan.number)

            except (ValueError, TypeError, AttributeError, KeyError, ImportError) as e:
                error_msg = f"Failed to generate section {section_plan.header}: {e!s}"
                logger.error(f"EMAIL GENERATOR V2: ❌ {error_msg}")

                # Generate fallback content
                fallback_content = self._generate_fallback_section_content(
                    section_plan, analysis
                )
                section_key = self._section_header_to_key(section_plan.header)
                generated_sections[section_key] = fallback_content

                debug_info.errors.append(
                    {
                        "section": section_plan.header,
                        "error": str(e),
                        "fallback_used": True,
                    }
                )

        # Generate closing
        logger.info("EMAIL GENERATOR V2: Generating closing section...")
        closing_content = self._generate_closing_section(plan, analysis, context)
        generated_sections["closing"] = closing_content
        debug_info.generated_sections["closing"] = {
            "content_length": len(closing_content),
            "is_empty": not closing_content.strip(),
            "first_100_chars": closing_content[:100] if closing_content else None,
        }

        logger.info(
            f"EMAIL GENERATOR V2: ✅ Generated {len(generated_sections)} sections"
        )
        return generated_sections

    def _section_header_to_key(self, header: str) -> str:
        """Convert section header to key for field mapping."""
        header_mapping = {
            "FACTUAL SUMMARY": "factual_summary",
            "LEGAL ANALYSIS": "legal_analysis",
            "EVIDENCE REVIEW": "evidence_review",
            "CASE ASSESSMENT": "case_assessment",
            "RECOMMENDED NEXT STEPS": "next_steps",
        }
        return header_mapping.get(header, header.lower().replace(" ", "_"))

    def _generate_section_with_validation(
        self,
        section_plan: SectionPlan,
        context: GenerationContext,
        analysis: CaseAnalysisResult,
    ) -> str:
        """Generate a section with explicit validation and readability checking."""
        # Generate section content based on type (no header - template handles structure)
        if section_plan.header == "FACTUAL SUMMARY":
            content = self._generate_factual_summary_content(
                section_plan, analysis, context
            )
        elif section_plan.header == "LEGAL ANALYSIS":
            content = self._generate_legal_analysis_content(
                section_plan, analysis, context
            )
        elif section_plan.header == "EVIDENCE REVIEW":
            content = self._generate_evidence_review_content(
                section_plan, analysis, context
            )
        elif section_plan.header == "CASE ASSESSMENT":
            content = self._generate_case_assessment_content(
                section_plan, analysis, context
            )
        elif section_plan.header == "RECOMMENDED NEXT STEPS":
            content = self._generate_next_steps_content(section_plan, analysis, context)
        else:
            content = self._generate_generic_section_content(
                section_plan, analysis, context
            )

        # Validate content is not empty
        if not content or not content.strip():
            msg = f"Section '{section_plan.header}' generated empty content"
            raise SectionValidationError(msg)

        # Apply section-level format validation
        section_key = self._section_header_to_key(section_plan.header)
        self._validate_section_format(content, section_key)

        # Clean AI response first
        cleaned_content = self.content_formatting_service._clean_ai_response(content)

        # Note: Word count trimming removed as part of refactoring to single-prompt JSON approach
        trimmed_content = cleaned_content

        # === SECTION READABILITY VALIDATION (REMOVED - SUBTASK 5A REVERSION) ===
        # The section-by-section readability validation with regeneration was causing HTML corruption
        # Removed: _validate_section_readability_with_regeneration call

        # Return trimmed content - template system handles headers and structure
        return trimmed_content

    def _validate_section_format(self, content: str, section_key: str) -> None:
        """
        Validate section output format against YAML configuration specifications.

        Args:
            content: The generated section content to validate
            section_key: The section key to look up format specification

        Logs warnings for validation failures without stopping generation.
        """
        try:
            # Get section configuration from YAML
            sections_config = self.config.get("sections", {})
            if not sections_config:
                logger.info(
                    "EMAIL GENERATOR V2: ⚠️ No sections configuration found in YAML"
                )
                return

            section_config = sections_config.get(section_key, {})
            if not section_config:
                logger.info(
                    f"EMAIL GENERATOR V2: ⚠️ No configuration found for section: {section_key}"
                )
                return

            # Extract output format (defaults to "html" if not specified)
            output_format = section_config.get("output_format", "html")

            # Validate the section output
            validate_section_output(content, output_format)

            logger.info(
                f"EMAIL GENERATOR V2: ✅ Section '{section_key}' format validation passed ({output_format})"
            )

        except Exception as e:
            # Log validation warning but don't stop generation
            logger.warning(
                f"EMAIL GENERATOR V2: ⚠️ Section '{section_key}' format validation warning: {e}"
            )
            # Continue processing - validation failure shouldn't stop email generation

    # === STAGE 3: FORMAT - Field Mapping and Validation ===

    def _map_sections_to_template_fields(
        self,
        generated_sections: dict[str, str],
        plan: EmailStructurePlan,
        analysis: CaseAnalysisResult,
    ) -> GeneratedLetter:
        """
        CRITICAL FIX: Properly map generated sections to specific template fields.
        This fixes the bug where all content was placed in executive_summary only.
        """
        # JSON logging for hypothesis tracking
        mapping_log = {
            "module": "EmailGeneratorV2",
            "method": "_map_sections_to_template_fields",
            "hypothesis_id": "missing_content_parsing",
            "stage": "entry",
            "sections_available": list(generated_sections.keys()),
            "section_lengths": {k: len(v) for k, v in generated_sections.items()},
            "timestamp": datetime.now().isoformat(),
        }
        logger.debug(f"EMAIL_GENERATOR_DEBUG: {json.dumps(mapping_log)}")

        logger.info("EMAIL GENERATOR V2: Mapping sections to template fields...")

        # Extract individual sections from generated content
        greeting = generated_sections.get("greeting", "")
        factual_summary = generated_sections.get("factual_summary", "")
        legal_analysis = generated_sections.get("legal_analysis", "")
        evidence_review = generated_sections.get("evidence_review", "")
        case_assessment = generated_sections.get("case_assessment", "")
        next_steps = generated_sections.get("next_steps", "")
        closing = generated_sections.get("closing", "")

        # Apply enhanced content processing to each section
        greeting = self._prepare_template_context(greeting)
        factual_summary = self._prepare_template_context(factual_summary)
        legal_analysis = self._prepare_template_context(legal_analysis)
        evidence_review = self._prepare_template_context(evidence_review)
        case_assessment = self._prepare_template_context(case_assessment)
        next_steps = self._prepare_template_context(next_steps)
        closing = self._prepare_template_context(closing)

        # Apply deadline formatting to next_steps (replaces Jinja2 regex_replace filter)
        next_steps = self.content_formatting_service._apply_deadline_formatting(
            next_steps
        )

        # Split case assessment into strengths and challenges if combined
        strengths, challenges = self._split_case_assessment(case_assessment)

        # Generate video analysis appendix if video data exists
        video_appendix = ""
        if analysis.video_insights:
            video_appendix = self._generate_video_analysis_appendix(analysis)

        # Create properly populated GeneratedLetter
        letter = GeneratedLetter(
            executive_summary=greeting,  # Greeting and introduction
            background_summary=factual_summary,  # Factual summary section
            analysis_and_position=legal_analysis,  # Legal analysis section
            media_summary=evidence_review,  # Evidence review section
            video_analysis_appendix=video_appendix,  # Video analysis details
            strengths=strengths,  # Case strengths
            challenges=challenges,  # Case challenges
            recommendations=case_assessment,  # Overall assessment (fallback)
            next_steps=next_steps,  # Next steps section
            closing_paragraph=closing,  # Professional closing
        )

        # VALIDATION GUARD REMOVED: Challenges section is now optional to prevent email generation failures
        logger.info(
            "EMAIL GENERATOR V2: OPTIONAL VALIDATION - Challenges section made optional"
        )

        # JSON logging for exit state
        exit_log = {
            "module": "EmailGeneratorV2",
            "method": "_map_sections_to_template_fields",
            "hypothesis_id": "missing_content_parsing",
            "stage": "exit",
            "letter_fields": {
                k: len(getattr(letter, k, "")) for k in letter.__fields__
            },
            "processing_applied": True,
            "validation_passed": True,
            "timestamp": datetime.now().isoformat(),
        }
        logger.debug(f"EMAIL_GENERATOR_DEBUG: {json.dumps(exit_log)}")

        logger.info("EMAIL GENERATOR V2: ✅ Sections mapped to template fields")
        logger.info(f"  - executive_summary: {len(letter.executive_summary)} chars")
        logger.info(f"  - background_summary: {len(letter.background_summary)} chars")
        logger.info(
            f"  - analysis_and_position: {len(letter.analysis_and_position)} chars"
        )
        logger.info(f"  - strengths: {len(letter.strengths)} chars")
        logger.info(f"  - challenges: {len(letter.challenges)} chars")
        logger.debug(f"  - next_steps: {len(letter.next_steps)} chars")
        logger.info(f"  - closing_paragraph: {len(letter.closing_paragraph)} chars")

        return letter

    # def _apply_polish_and_sanitize(self, letter: GeneratedLetter) -> GeneratedLetter:
    #     """
    #     Apply polish and sanitize processing to all letter fields.

    #     This method processes each field of the generated letter through the
    #     polish_and_sanitize function to ensure content quality and compliance.
    #     """
    #     try:
    #         print("EMAIL GENERATOR V2: Applying polish and sanitize to letter fields...")

    #         # Process each field that contains substantial content
    #         fields_to_process = [
    #             'executive_summary',
    #             'background_summary',
    #             'analysis_and_position',
    #             'media_summary',
    #             'strengths',
    #             'challenges',
    #             'recommendations',
    #             'next_steps',
    #             'closing_paragraph'
    #         ]

    #         for field_name in fields_to_process:
    #             field_content = getattr(letter, field_name, "")
    #             if field_content and field_content.strip():
    #                 try:
    #                     # Get appropriate word limit for this field from configuration
    #                     word_counts = self.config.get('word_counts', {})
    #                     field_word_limit = word_counts.get(field_name, 200)  # Default to 200 if not specified

    #                     # Apply polish and sanitize with proper word limit per field
    #                     processed_content = polish_and_sanitize(
    #                         email_draft=field_content,
    #                         apply_polishing=False,  # Skip AI polishing for individual fields
    #                         client=self.client,
    #                         word_limit=field_word_limit
    #                     )
    #                     setattr(letter, field_name, processed_content)
    #                     print(f"EMAIL GENERATOR V2: ✅ Processed {field_name}")

    #                 except Exception as e:
    #                     print(f"EMAIL GENERATOR V2: ⚠️ Failed to process {field_name}: {e}")
    #                     # Continue with original content if processing fails

    #         # Apply overall email polish and sanitize to the complete email
    #         try:
    #             # Combine all content for full email processing
    #             full_email_content = self._combine_letter_content(letter)

    #             # Apply full email polish and sanitize with STRICT 850-word limit
    #             polished_email = polish_and_sanitize(
    #                 email_draft=full_email_content,
    #                 apply_polishing=True,  # Enable AI polishing for full email
    #                 client=self.client,
    #                 word_limit=850  # CRITICAL: Full email MUST be under 850 words
    #             )

    #             # If full processing succeeds, update the primary content field
    #             letter.executive_summary = polished_email[:1000] + "..." if len(polished_email) > 1000 else polished_email
    #             print("EMAIL GENERATOR V2: ✅ Applied full email polish and sanitize")

    #         except Exception as e:
    #             print(f"EMAIL GENERATOR V2: ⚠️ Full email processing failed: {e}")
    #             # Continue with field-level processing results

    #         return letter

    #     except Exception as e:
    #         print(f"EMAIL GENERATOR V2: ❌ Polish and sanitize processing failed: {e}")
    #         # Return original letter if all processing fails
    #         return letter

    # def _combine_letter_content(self, letter: GeneratedLetter) -> str:
    #     """Combine all letter content into a single email draft for processing."""
    #     content_parts = []

    #     # Add each field with proper spacing
    #     fields_with_content = [
    #         ('Executive Summary', letter.executive_summary),
    #         ('Background Summary', letter.background_summary),
    #         ('Legal Analysis', letter.analysis_and_position),
    #         ('Evidence Review', letter.media_summary),
    #         ('Case Strengths', letter.strengths),
    #         ('Challenges', letter.challenges),
    #         ('Recommendations', letter.recommendations),
    #         ('Next Steps', letter.next_steps),
    #         ('Closing', letter.closing_paragraph)
    #     ]

    #     for section_name, content in fields_with_content:
    #         if content and content.strip():
    #             content_parts.append(f"<h3>{section_name}</h3>")
    #             content_parts.append(content)
    #             content_parts.append("")  # Add spacing

    #     return "\n".join(content_parts)

    # === SIMPLIFICATION PIPELINE (REMOVED - SUBTASK 5A REVERSION) ===
    # The AI simplification pipeline was causing HTML structure corruption
    # Removed: _apply_simplification_pass, _create_simplification_prompt,
    # _request_text_simplification, _replace_html_content_with_simplified,
    # _convert_text_to_html_paragraphs

    def _split_case_assessment(self, case_assessment: str) -> Tuple[str, str]:
        """Split combined case assessment into strengths and challenges with enhanced parsing."""
        if not case_assessment:
            return "", ""

        # First, try to find explicit section headers (from our enhanced prompt)
        strengths_match = re.search(
            r"\*\*STRENGTHS\*\*\s*(.*?)(?=\*\*POTENTIAL CHALLENGES\*\*|\*\*CHALLENGES\*\*|$)",
            case_assessment,
            re.DOTALL | re.IGNORECASE,
        )
        challenges_match = re.search(
            r"\*\*(?:POTENTIAL )?CHALLENGES\*\*\s*(.*?)$",
            case_assessment,
            re.DOTALL | re.IGNORECASE,
        )

        if strengths_match and challenges_match:
            strengths = strengths_match.group(1).strip()
            challenges = challenges_match.group(1).strip()
            logger.info(
                "EMAIL GENERATOR V2: ✅ Successfully parsed explicit STRENGTHS and CHALLENGES sections"
            )
            return strengths, challenges

        # Fallback: Look for alternative header patterns
        strengths_keywords = [
            "strength",
            "advantage",
            "positive",
            "favorable",
            "support",
            "benefits",
        ]
        challenges_keywords = [
            "challenge",
            "weakness",
            "risk",
            "concern",
            "obstacle",
            "difficulty",
            "potential challenges",
            "considerations",
            "issues",
        ]

        # Try to split by sections with clear headers
        lines = case_assessment.split("\n")
        strengths_lines = []
        challenges_lines = []
        current_section = "unknown"

        for line in lines:
            line_lower = line.lower().strip()

            # Check for section headers
            if any(
                f"**{keyword}" in line_lower or f"<strong>{keyword}" in line_lower
                for keyword in strengths_keywords
            ):
                current_section = "strengths"
                strengths_lines.append(line)
                continue
            if any(
                f"**{keyword}" in line_lower or f"<strong>{keyword}" in line_lower
                for keyword in challenges_keywords
            ):
                current_section = "challenges"
                challenges_lines.append(line)
                continue

            # Add content to current section
            if current_section == "strengths":
                strengths_lines.append(line)
            elif current_section == "challenges":
                challenges_lines.append(line)
            elif line.strip():  # Default unknown content goes to strengths initially
                if any(keyword in line_lower for keyword in challenges_keywords):
                    current_section = "challenges"
                    challenges_lines.append(line)
                elif any(keyword in line_lower for keyword in strengths_keywords):
                    current_section = "strengths"
                    strengths_lines.append(line)

        strengths_content = "\n".join(strengths_lines).strip()
        challenges_content = "\n".join(challenges_lines).strip()

        # Validation: If we have no challenges content, this is a problem that needs to be flagged
        if not challenges_content:
            logger.error(
                "EMAIL GENERATOR V2: ⚠️ No challenges content found - this will trigger validation failure"
            )
            return strengths_content, ""

        # If we have content in both sections, return it
        if strengths_content and challenges_content:
            logger.info(
                "EMAIL GENERATOR V2: ✅ Successfully split content into strengths and challenges"
            )
            return strengths_content, challenges_content

        # If we couldn't split intelligently and have no challenges, flag this as an issue
        if strengths_content and not challenges_content:
            logger.info(
                "EMAIL GENERATOR V2: ⚠️ Only found strengths content, no challenges - validation will fail"
            )
            return strengths_content, ""

        # Last resort: split the content in half
        if case_assessment and not strengths_content and not challenges_content:
            logger.info(
                "EMAIL GENERATOR V2: ⚠️ Could not parse sections, attempting 50/50 split"
            )
            sentences = re.split(r"(?<=[.!?])\s+", case_assessment)
            mid_point = len(sentences) // 2
            return " ".join(sentences[:mid_point]), " ".join(sentences[mid_point:])

        return strengths_content, challenges_content

    def _validate_all_fields(
        self, letter: GeneratedLetter
    ) -> Dict[str, Dict[str, Any]]:
        """Comprehensive validation of all letter fields for debugging."""
        validation_results = {}

        for field_name in letter.__fields__:
            field_value = getattr(letter, field_name, "")
            validation_results[field_name] = {
                "has_content": bool(field_value and field_value.strip()),
                "length": len(field_value) if field_value else 0,
                "first_50_chars": field_value[:50] if field_value else None,
            }

        return validation_results

    # === NEW JSON-BASED ARCHITECTURE METHODS ===

    def _generate_structured_json(self, analysis: CaseAnalysisResult) -> Dict[str, Any]:
        """
        Generate structured JSON response from OpenAI following the master schema.

        This method replaces multi-stage HTML generation with a single JSON call
        that conforms to our comprehensive master schema.

        Args:
            analysis: The case analysis result containing all case data

        Returns:
            Dictionary containing the structured JSON response

        Raises:
            ValueError: If JSON generation fails or returns invalid structure
        """
        try:
            logger.info("EMAIL GENERATOR V2: Generating structured JSON from OpenAI...")

            # Extract case context for the prompt
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

            # Build comprehensive JSON generation prompt
            json_prompt = f"""
            Generate a SINGLE, VALID JSON object for a legal findings email that strictly conforms to the following schema structure.

            CRITICAL REQUIREMENTS:
            - Return ONLY valid JSON - no explanatory text, no markdown formatting
            - All string fields must contain actual content, not placeholder text
            - Include ALL required fields from the schema
            - Ensure JSON is properly formatted and parseable
            
            JSON SCHEMA STRUCTURE:
            {{
                "case_metadata": {{
                    "client_name": "string",
                    "attorney_name": "string",
                    "case_type": "string",
                    "matter_description": "string",
                    "urgency_level": "string",
                    "financial_impact": "string"
                }},
                "bridges": {{
                    "opening_bridge": "string - 2-3 sentence narrative introduction",
                    "factual_to_legal": "string - transition from facts to legal analysis",
                    "legal_to_assessment": "string - transition from legal analysis to case assessment",
                    "assessment_to_action": "string - transition from assessment to next steps"
                }},
                "generated_letter": {{
                    "factual_summary": "string - HTML formatted factual summary",
                    "legal_analysis": "string - HTML formatted legal analysis under Florida law",
                    "evidence_review": "string - HTML formatted evidence analysis",
                    "case_assessment": "string - HTML formatted combined strengths and challenges"
                }},
                "claims": [
                    {{
                        "claim_type": "string",
                        "legal_basis": "string",
                        "evidence_support": "string",
                        "strength_assessment": "string",
                        "potential_damages": "string"
                    }}
                ],
                "procedural_requirements": {{
                    "statute_of_limitations": "string",
                    "notice_requirements": "string",
                    "filing_deadlines": "string",
                    "procedural_steps": ["string"]
                }},
                "third_party_exposure": {{
                    "additional_parties": ["string"],
                    "insurance_considerations": "string",
                    "potential_counterclaims": "string"
                }},
                "next_steps": {{
                    "strategic_overview": "string - paragraph explaining strategic approach",
                    "action_items": [
                        {{
                            "action": "string - specific action item",
                            "timeline": "string - deadline or timeframe",
                            "priority": "string - High/Medium/Low",
                            "responsible_party": "string",
                            "purpose": "string"
                        }}
                    ],
                    "contingency_planning": "string"
                }}
            }}

            CASE INFORMATION TO PROCESS:
            Client: {client_name}
            Case Type: {case_type}
            
            Full Case Analysis:
            {analysis.model_dump_json(indent=2)}

            CONTENT REQUIREMENTS:
            - Write as an experienced Florida litigation attorney
            - Use professional but accessible language
            - Include specific case details from the analysis
            - Ensure all HTML content is properly formatted with appropriate tags
            - Bold important terms, amounts, and deadlines using <strong> tags
            - Format lists using <ul><li> tags where appropriate
            - Keep case_assessment under 150 words total
            - Ensure action_items have realistic timelines and clear purposes
            - Reference only Florida law when applicable
            - Do NOT include statute numbers or legal citations

            Generate the complete JSON object now:
            """

            # Get enhanced prompt with firm voice and configuration
            enhanced_prompt = self.prompt_api_service.build_enhanced_prompt(
                json_prompt, "structured_json"
            )

            # Get persona from configuration
            persona = self.config.get("personas", {}).get(
                "CONTINUING_ATTORNEY_ADVISOR", ""
            )

            # Use JsonProcessingService for OpenAI requests (fixed deprecated method)
            if (
                hasattr(self, "json_processing_service")
                and self.json_processing_service
            ):
                json_response_text = self.json_processing_service._make_openai_request(
                    enhanced_prompt
                )
            else:
                json_response_text = None

            if not json_response_text or not json_response_text.strip():
                raise ValueError("OpenAI returned empty response for JSON generation")

            # Clean and parse JSON response
            cleaned_json_text = self._clean_json_response(json_response_text)

            try:
                json_data = json.loads(cleaned_json_text)
            except json.JSONDecodeError as e:
                logger.error(f"EMAIL GENERATOR V2: ❌ JSON parsing failed: {e}")
                logger.info(
                    f"Response text (first 500 chars): {json_response_text[:500]}..."
                )
                raise ValueError(f"Failed to parse JSON response: {e}")

            logger.info(
                f"EMAIL GENERATOR V2: ✅ Successfully generated structured JSON with {len(json_data)} top-level keys"
            )
            return json_data

        except Exception as e:
            logger.error(
                f"EMAIL GENERATOR V2: ❌ Structured JSON generation failed: {e}"
            )
            raise ValueError(f"Failed to generate structured JSON: {e}")

    def _clean_json_response(self, response_text: str) -> str:
        """
        Clean OpenAI response to extract valid JSON.

        Args:
            response_text: Raw response from OpenAI

        Returns:
            Cleaned JSON string ready for parsing
        """
        if not response_text:
            return ""

        # Remove any markdown code block markers
        cleaned = re.sub(r"^```json\s*", "", response_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

        # Remove any leading/trailing whitespace and non-JSON content
        cleaned = cleaned.strip()

        # Find the first { and last } to extract just the JSON object
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx : end_idx + 1]

        return cleaned

    def _validate_json_response(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate JSON response against our master schema structure.

        Args:
            json_data: The JSON data to validate

        Returns:
            Validated and potentially corrected JSON data

        Raises:
            ValueError: If validation fails critically
        """
        try:
            logger.debug(
                "EMAIL GENERATOR V2: Validating JSON response against master schema..."
            )

            # Define required top-level keys
            required_keys = [
                "case_metadata",
                "bridges",
                "generated_letter",
                "claims",
                "procedural_requirements",
                "third_party_exposure",
                "next_steps",
            ]

            # Check for missing top-level keys
            missing_keys = [key for key in required_keys if key not in json_data]
            if missing_keys:
                logger.info(
                    f"EMAIL GENERATOR V2: ⚠️ Missing top-level keys: {missing_keys}"
                )
                # Add default values for missing keys
                for key in missing_keys:
                    json_data[key] = self._get_default_value_for_key(key)

            # Validate individual sections
            json_data["case_metadata"] = self._validate_case_metadata(
                json_data.get("case_metadata", {})
            )
            json_data["bridges"] = self._validate_bridges_structure(
                json_data.get("bridges", {})
            )
            json_data["generated_letter"] = self._validate_generated_letter_structure(
                json_data.get("generated_letter", {})
            )
            json_data["claims"] = self._validate_claims_structure(
                json_data.get("claims", [])
            )
            json_data["next_steps"] = self._validate_next_steps_structure(
                json_data.get("next_steps", {})
            )

            logger.info("EMAIL GENERATOR V2: ✅ JSON validation completed successfully")
            return json_data

        except Exception as e:
            logger.error(f"EMAIL GENERATOR V2: ❌ JSON validation failed: {e}")
            raise ValueError(f"JSON validation failed: {e}")

    def _get_default_value_for_key(self, key: str) -> Union[Dict[str, Any], List[Any]]:
        """Get default value for missing JSON schema keys."""
        defaults = {
            "case_metadata": {
                "client_name": "Client",
                "attorney_name": "Attorney",
                "case_type": "Legal Matter",
                "matter_description": "Legal matter requiring analysis",
                "urgency_level": "Standard",
                "financial_impact": "To be determined",
            },
            "bridges": {
                "opening_bridge": "I have completed my comprehensive review of your legal matter.",
                "factual_to_legal": "Based on these facts, several legal considerations apply.",
                "legal_to_assessment": "This legal framework provides the basis for our case assessment.",
                "assessment_to_action": "Given this assessment, I recommend the following strategic approach.",
            },
            "generated_letter": {
                "factual_summary": "<p>Key facts and circumstances have been analyzed.</p>",
                "legal_analysis": "<p>Legal analysis under Florida law indicates several considerations.</p>",
                "evidence_review": "<p>Evidence review has been completed.</p>",
                "case_assessment": "<p><strong>STRENGTHS</strong></p><p>Case has foundation under Florida law.</p><p><strong>POTENTIAL CHALLENGES</strong></p><p>Strategic considerations apply.</p>",
            },
            "claims": [],
            "procedural_requirements": {
                "statute_of_limitations": "Standard limitations period applies",
                "notice_requirements": "Proper notice requirements must be followed",
                "filing_deadlines": "Filing deadlines will be monitored",
                "procedural_steps": [
                    "Initial case development",
                    "Evidence preservation",
                    "Strategic planning",
                ],
            },
            "third_party_exposure": {
                "additional_parties": [],
                "insurance_considerations": "Insurance coverage will be evaluated",
                "potential_counterclaims": "Potential counterclaims will be assessed",
            },
            "next_steps": {
                "strategic_overview": "Based on our analysis, a strategic approach has been developed.",
                "action_items": [
                    {
                        "action": "Continue case development",
                        "timeline": "within 14 days",
                        "priority": "High",
                        "responsible_party": "Legal team",
                        "purpose": "Advance case strategy",
                    }
                ],
                "contingency_planning": "Alternative strategies will be evaluated as needed.",
            },
        }
        return defaults.get(key, {})

    def _validate_case_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and ensure case metadata completeness."""
        required_fields = [
            "client_name",
            "attorney_name",
            "case_type",
            "matter_description",
            "urgency_level",
            "financial_impact",
        ]

        for field in required_fields:
            if field not in metadata or not metadata[field]:
                metadata[field] = self._get_default_value_for_key("case_metadata")[
                    field
                ]

        return metadata

    def _validate_bridges_structure(self, bridges: Dict[str, Any]) -> Dict[str, Any]:
        """Validate bridge text structure and content."""
        required_bridges = [
            "opening_bridge",
            "factual_to_legal",
            "legal_to_assessment",
            "assessment_to_action",
        ]

        for bridge in required_bridges:
            if (
                bridge not in bridges
                or not bridges[bridge]
                or not bridges[bridge].strip()
            ):
                bridges[bridge] = self._get_default_value_for_key("bridges")[bridge]

        return bridges

    def _validate_generated_letter_structure(
        self, letter: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate generated letter sections structure."""
        required_sections = [
            "factual_summary",
            "legal_analysis",
            "evidence_review",
            "case_assessment",
        ]

        for section in required_sections:
            if (
                section not in letter
                or not letter[section]
                or not letter[section].strip()
            ):
                letter[section] = self._get_default_value_for_key("generated_letter")[
                    section
                ]

        # Ensure case_assessment has both STRENGTHS and CHALLENGES
        if "case_assessment" in letter:
            assessment = letter["case_assessment"]
            if "STRENGTHS" not in assessment or "CHALLENGES" not in assessment:
                letter["case_assessment"] = self._get_default_value_for_key(
                    "generated_letter"
                )["case_assessment"]

        return letter

    def _validate_claims_structure(
        self, claims: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate claims array structure."""
        if not claims or not isinstance(claims, list):
            return []

        validated_claims = []
        required_claim_fields = [
            "claim_type",
            "legal_basis",
            "evidence_support",
            "strength_assessment",
            "potential_damages",
        ]

        for claim in claims:
            if isinstance(claim, dict):
                validated_claim = {}
                for field in required_claim_fields:
                    validated_claim[field] = claim.get(
                        field, f"Information regarding {field} to be developed"
                    )
                validated_claims.append(validated_claim)

        return validated_claims

    def _validate_next_steps_structure(
        self, next_steps: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate next steps structure and action items."""
        if not isinstance(next_steps, dict):
            return self._get_default_value_for_key("next_steps")

        # Ensure required fields exist
        if (
            "strategic_overview" not in next_steps
            or not next_steps["strategic_overview"]
        ):
            next_steps["strategic_overview"] = (
                "Strategic approach has been developed for this matter."
            )

        if "action_items" not in next_steps or not isinstance(
            next_steps["action_items"], list
        ):
            next_steps["action_items"] = self._get_default_value_for_key("next_steps")[
                "action_items"
            ]

        # Validate each action item
        validated_items = []
        required_action_fields = [
            "action",
            "timeline",
            "priority",
            "responsible_party",
            "purpose",
        ]

        for item in next_steps["action_items"]:
            if isinstance(item, dict):
                validated_item = {}
                for field in required_action_fields:
                    validated_item[field] = item.get(field, "To be determined")
                validated_items.append(validated_item)

        next_steps["action_items"] = validated_items

        if (
            "contingency_planning" not in next_steps
            or not next_steps["contingency_planning"]
        ):
            next_steps["contingency_planning"] = (
                "Alternative strategies will be evaluated as circumstances develop."
            )

        return next_steps

    def _convert_json_to_generated_letter(
        self, validated_json: Dict[str, Any]
    ) -> GeneratedLetter:
        """
        Convert validated JSON to GeneratedLetter format for backward compatibility.

        This method bridges the new JSON architecture with the existing template system
        by mapping JSON fields to the expected GeneratedLetter structure.

        Args:
            validated_json: The validated JSON data

        Returns:
            GeneratedLetter object populated from JSON data
        """
        try:
            logger.info(
                "EMAIL GENERATOR V2: Converting JSON to GeneratedLetter format..."
            )

            # Extract data from JSON structure
            case_metadata = validated_json.get("case_metadata", {})
            bridges = validated_json.get("bridges", {})
            generated_letter = validated_json.get("generated_letter", {})
            next_steps_data = validated_json.get("next_steps", {})

            # Create greeting from bridges and metadata
            client_name = case_metadata.get("client_name", "Client")
            opening_bridge = bridges.get("opening_bridge", "")

            if "Devlin" in client_name and "Bell" in client_name:
                greeting = "Good afternoon Mr. Devlin and Ms. Bell,"
            else:
                greeting = f"Good afternoon {client_name},"

            executive_summary = f"<p>{greeting}</p><p>{opening_bridge}</p>"

            # Extract individual letter sections
            factual_summary = generated_letter.get("factual_summary", "")
            legal_analysis = generated_letter.get("legal_analysis", "")
            evidence_review = generated_letter.get("evidence_review", "")
            case_assessment = generated_letter.get("case_assessment", "")

            # Split case assessment into strengths and challenges
            strengths, challenges = self._split_case_assessment(case_assessment)

            # Format next steps from JSON structure
            next_steps_formatted = self._format_next_steps_from_json(next_steps_data)

            # Create closing
            attorney_name = case_metadata.get("attorney_name", "Your Legal Team")
            closing = f"""
            <p>Please contact our office if you have any questions about this analysis or our recommendations.</p>
            <p><strong>Sincerely,</strong><br>
            {attorney_name}<br>
            Bernhardt Riley PLLC</p>
            """

            # Create GeneratedLetter object
            letter = GeneratedLetter(
                executive_summary=executive_summary,
                background_summary=factual_summary,
                analysis_and_position=legal_analysis,
                media_summary=evidence_review,
                video_analysis_appendix="",  # Will be populated separately if needed
                strengths=strengths,
                challenges=challenges,
                recommendations=case_assessment,  # Fallback content
                next_steps=next_steps_formatted,
                closing_paragraph=closing,
            )

            logger.info(
                "EMAIL GENERATOR V2: ✅ Successfully converted JSON to GeneratedLetter"
            )
            return letter

        except Exception as e:
            logger.error(
                f"EMAIL GENERATOR V2: ❌ JSON to GeneratedLetter conversion failed: {e}"
            )
            raise ValueError(f"Failed to convert JSON to GeneratedLetter: {e}")

    def _format_next_steps_from_json(self, next_steps_data: Dict[str, Any]) -> str:
        """
        Format next steps from JSON structure into HTML.

        Args:
            next_steps_data: Next steps data from JSON

        Returns:
            HTML formatted next steps content
        """
        if not next_steps_data:
            return "<p>Recommended next steps will be provided based on case development.</p>"

        html_parts = []

        # Add strategic overview
        strategic_overview = next_steps_data.get("strategic_overview", "")
        if strategic_overview:
            html_parts.append(f"<p>{strategic_overview}</p>")

        # Add action items
        action_items = next_steps_data.get("action_items", [])
        if action_items:
            html_parts.append("<ul>")
            for item in action_items:
                if isinstance(item, dict):
                    action = item.get("action", "")
                    timeline = item.get("timeline", "")
                    purpose = item.get("purpose", "")

                    # Format timeline with strong tags for emphasis
                    formatted_timeline = (
                        f"<strong>{timeline}</strong>" if timeline else ""
                    )

                    # Build action item description
                    item_text = action
                    if formatted_timeline:
                        item_text += f" ({formatted_timeline})"
                    if purpose:
                        item_text += f" - {purpose}"

                    html_parts.append(f"<li>{item_text}</li>")
            html_parts.append("</ul>")

        # Add contingency planning
        contingency = next_steps_data.get("contingency_planning", "")
        if contingency:
            html_parts.append(
                f"<p><strong>Contingency Considerations:</strong> {contingency}</p>"
            )

        return (
            "".join(html_parts)
            if html_parts
            else "<p>Strategic next steps are being developed.</p>"
        )

    # === CONTENT GENERATION METHODS ===

    def _generate_greeting_section(
        self,
        plan: EmailStructurePlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate professional greeting section."""
        context.greeting_given = True
        context.client_name_mentioned = True

        return f"""
        <p>{plan.greeting}</p>
        <p>I have completed my review of your legal matter and am prepared to present my findings and recommendations.</p>
        """

    def _generate_factual_summary_content(
        self,
        section_plan: SectionPlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate factual summary content with validation."""

        # DIAGNOSTIC LOGGING: Check what context we're getting
        logger.info(
            "EMAIL GENERATOR: 🔍 === DIAGNOSTIC LOGGING - Factual Summary Context ==="
        )
        logger.info(
            f"EMAIL GENERATOR: 🔍 Analyzed documents count: {(len(analysis.analyzed_documents) if analysis.analyzed_documents else 0)}"
        )
        if analysis.analyzed_documents:
            for i, doc in enumerate(
                analysis.analyzed_documents[:3]
            ):  # Log first 3 docs
                logger.info(f"EMAIL GENERATOR: 🔍   Document {i + 1}: {doc.file_name}")
                logger.info(
                    f"EMAIL GENERATOR: 🔍   Summary: {(doc.summary[:100] if doc.summary else 'No summary')}..."
                )
                logger.info(
                    f"EMAIL GENERATOR: 🔍   Key info: {(doc.key_information[:100] if doc.key_information else 'No key info')}..."
                )

        # Get prompt from configuration (defensive against None values)
        sections_section = self.config.get("sections") or {}
        section_config = sections_section.get("factual_summary", {})
        if isinstance(section_config, dict):
            section_prompt = section_config.get("content", "")
        else:
            section_prompt = str(section_config) if section_config else ""

        if not section_prompt:
            # Fallback prompt if configuration is missing
            section_prompt = "Write a factual summary section for a professional legal findings letter."

        base_prompt = f"""
        Begin with a 2–3 sentence narrative bridge that frames the bullets.
        
        {section_prompt}

        Key Facts to Emphasize:
        {section_plan.key_points}

        CASE CONTEXT AND DOCUMENTS (Extract specific details):
        {analysis.model_dump_json(indent=2)}
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self.prompt_api_service.build_enhanced_prompt(
            base_prompt, "factual_summary"
        )

        logger.info(
            f"EMAIL GENERATOR: 🔍 Factual summary enhanced prompt length: {len(enhanced_prompt)} characters"
        )

        # Get persona from configuration (defensive against None values)
        personas_section = self.config.get("personas") or {}
        persona = personas_section.get("CONTINUING_ATTORNEY_ADVISOR", "")
        result = self.prompt_api_service.make_openai_request(enhanced_prompt, persona)
        logger.info(
            f"EMAIL GENERATOR: 🔍 Factual summary result length: {(len(result) if result else 0)} characters"
        )
        logger.info("EMAIL GENERATOR: 🔍 === END DIAGNOSTIC LOGGING ===")

        return result or "<p>Factual summary of the key events and circumstances.</p>"

    def _generate_legal_analysis_content(
        self,
        section_plan: SectionPlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate legal analysis content with Florida law focus."""

        # Get prompt from configuration (defensive against None values)
        sections_section = self.config.get("sections") or {}
        section_config = sections_section.get("legal_analysis", {})
        if isinstance(section_config, dict):
            section_prompt = section_config.get("content", "")
        else:
            section_prompt = str(section_config) if section_config else ""

        if not section_prompt:
            section_prompt = "Write a legal analysis section as an experienced Florida litigation attorney."

        base_prompt = f"""
        For each claim, output elements (bullets), application (paragraph), remedies (bullets), and a single sentence 'What this means for you' line.
        
        {section_prompt}

        Legal Issues to Analyze:
        {section_plan.key_points}

        CASE CONTEXT AND EVIDENCE:
        {analysis.model_dump_json(indent=2)}
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self.prompt_api_service.build_enhanced_prompt(
            base_prompt, "analysis"
        )

        # Get persona from configuration (defensive against None values)
        personas_section = self.config.get("personas") or {}
        # Use JsonProcessingService for OpenAI requests (fixed deprecated method)
        if hasattr(self, "json_processing_service") and self.json_processing_service:
            result = self.json_processing_service._make_openai_request(enhanced_prompt)
        else:
            result = None
        return (
            result
            or "<p>Legal analysis under Florida law indicates several key considerations.</p>"
        )

    def _generate_evidence_review_content(
        self,
        section_plan: SectionPlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate evidence review content focusing on media and documents."""
        if not analysis.transcripted_media and not analysis.video_insights:
            return ""

        base_prompt = f"""
        Write an evidence review section as an experienced Florida litigation attorney analyzing the evidentiary value of media and documents.

        EVIDENCE ANALYSIS STANDARDS:
        - Provide substantive analysis in well-developed paragraphs that assess evidentiary value and admissibility
        - Discuss each significant piece of evidence with its relevance to the legal claims
        - Address potential admissibility issues under Florida Evidence Code
        - Explain how the evidence supports or undermines key elements of the case
        - Use bullet points only for listing specific pieces of evidence or admissibility factors
        - Demonstrate understanding of evidence rules and litigation strategy
        - Bold important file names and key findings using <strong> tags

        EVIDENCE EVALUATION STRUCTURE:
        1. Opening paragraph summarizing the evidentiary foundation and its significance
        2. Detailed analysis of key documents with relevance to legal claims
        3. Assessment of audio/video evidence and its probative value
        4. Discussion of potential evidentiary challenges and how to address them
        5. Strategic considerations for evidence presentation and case development

        LEGAL EVIDENCE ANALYSIS:
        - Evaluate authenticity and chain of custody issues for media evidence
        - Assess relevance and probative value under Florida Evidence Code
        - Identify potential hearsay or other admissibility concerns
        - Explain how evidence supports burden of proof requirements
        - Consider opposing party's likely evidentiary challenges
        - Address evidence preservation and discovery requirements

        Evidence Points to Analyze:
        {section_plan.key_points}

        CASE CONTEXT AND MEDIA:
        {analysis.model_dump_json(indent=2)}

        Write comprehensive evidence analysis demonstrating the expertise of a seasoned Florida litigation attorney familiar with evidence rules.
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self.prompt_api_service.build_enhanced_prompt(
            base_prompt, "evidence_review"
        )

        # Get persona from configuration (defensive against None values)
        personas_section = self.config.get("personas") or {}
        # Use JsonProcessingService for OpenAI requests (fixed deprecated method)
        if hasattr(self, "json_processing_service") and self.json_processing_service:
            result = self.json_processing_service._make_openai_request(enhanced_prompt)
        else:
            result = None
        return (
            result
            or "<p>Review of the evidence reveals important information relevant to this case.</p>"
        )

    def _generate_case_assessment_content(
        self,
        section_plan: SectionPlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate combined case assessment covering strengths and challenges with explicit enforcement."""
        base_prompt = f"""
        **CRITICAL COMMAND: YOU MUST جنرेट (GENERATE) TWO SECTIONS: "STRENGTHS" AND "POTENTIAL CHALLENGES". FAILURE TO DO SO WILL RESULT IN IMMEDIATE REJECTION. THIS IS NOT A SUGGESTION. IT IS A REQUIREMENT.**

        **FORMAT:**

        **STRENGTHS**
        [... Strengths content here ...]

        **POTENTIAL CHALLENGES**
        [... Potential Challenges content here ...]

        Write a case assessment section as an experienced Florida litigation attorney providing objective evaluation of case strengths and challenges.

        Assessment Points to Address:
        {section_plan.key_points}

        CASE CONTEXT AND EVIDENCE:
        {analysis.model_dump_json(indent=2)}

        Write a comprehensive case assessment that reflects the judgment and experience of a senior Florida litigation attorney.
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self.prompt_api_service.build_enhanced_prompt(
            base_prompt, "strengths_and_weaknesses"
        )

        # Get persona from configuration
        # Use JsonProcessingService for OpenAI requests (fixed deprecated method)
        if hasattr(self, "json_processing_service") and self.json_processing_service:
            result = self.json_processing_service._make_openai_request(enhanced_prompt)
        else:
            result = None
        return (
            result
            or "<p><strong>STRENGTHS</strong></p><p>Case assessment reveals strengths under Florida law.</p><p><strong>POTENTIAL CHALLENGES</strong></p><p>Strategic considerations under Florida law.</p>"
        )

    def _generate_next_steps_content(
        self,
        section_plan: SectionPlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate next steps content with prioritized actions."""
        base_prompt = f"""
        For each item include: purpose, deadline, success criteria, and consequence if missed.
        
        Write a recommended next steps section as an experienced Florida litigation attorney providing strategic guidance to the client.

        CRITICAL REQUIREMENT: Generate TWO distinct components:
        1. STRATEGIC LEAD-IN PARAGRAPH: A substantive introductory paragraph that explains the strategic approach, rationale, and immediate priorities for this case
        2. ACTIONABLE ITEMS LIST: A clean <ul><li> bulleted list of specific action items with deadlines and procedural steps

        STRATEGIC GUIDANCE STANDARDS:
        - Begin with a strategic lead-in paragraph that provides context and explains the overall approach
        - Follow with actionable items in a clean <ul><li> block structure for maximum scannability
        - Bold critical deadlines and requirements using <strong> tags for emphasis
        - Demonstrate knowledge of Florida procedural rules and litigation strategy
        - Present recommendations with the authority and wisdom of a seasoned litigator

        REQUIRED OUTPUT STRUCTURE:
        1. Strategic Lead-in Paragraph: A substantive paragraph explaining the strategic approach, case priorities, and rationale for the recommended actions
        2. Actionable Items: Clean <ul><li> list of specific action items, deadlines, and procedural steps
        3. Closing paragraph (if needed): Additional explanatory text about strategic considerations or client guidance

        FORMATTING REQUIREMENTS:
        - Start with a strategic introductory paragraph that sets the context
        - Use <ul><li> tags for all actionable recommendations
        - Include precise timelines, deadlines, and procedural requirements within the list items
        - Reference specific Florida procedural deadlines and requirements
        - Explain the purpose and importance of each recommended action within the list items
        - Provide realistic timelines based on legal and practical considerations
        - Address both immediate actions and longer-term strategic planning
        - Include guidance on evidence preservation and case development
        - Consider alternative dispute resolution options where appropriate
        - You MUST wrap every calendar interval (e.g., 'within 14 days') or absolute date (e.g., 'by August 21, 2025') in <strong> tags

        Recommended Actions to Include:
        {section_plan.key_points}

        CASE CONTEXT AND ANALYSIS:
        {analysis.model_dump_json(indent=2)}

        Write strategic next steps recommendations starting with the strategic lead-in paragraph that explains the approach, followed by a scannable <ul><li> list of actionable items, and any closing explanatory paragraphs as needed.
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self.prompt_api_service.build_enhanced_prompt(
            base_prompt, "next_steps"
        )

        # Get persona from configuration
        # Use JsonProcessingService for OpenAI requests (fixed deprecated method)
        if hasattr(self, "json_processing_service") and self.json_processing_service:
            result = self.json_processing_service._make_openai_request(enhanced_prompt)
        else:
            result = None
        final_result = (
            result
            or "<p>Based on our analysis, the following steps are recommended to advance your case.</p>"
        )

        # Validate next steps formatting for deadline emphasis
        try:
            validate_next_steps_formatting(final_result)
        except ValueError as e:
            logger.warning(f"EMAIL GENERATOR V2: ⚠️ Next steps validation warning: {e}")
            # Log the warning but don't fail the generation process

        return final_result

    def _generate_generic_section_content(
        self,
        section_plan: SectionPlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate any other section type with appropriate formatting."""
        base_prompt = f"""
        Generate a {section_plan.header.lower()} section for a professional legal findings letter using the AUTHENTIC_ATTORNEY style.

        REQUIREMENTS:
        - Use bullet points for organized information
        - Bold important terms and amounts using <strong> tags
        - Be direct and professional
        - Reference only Florida law when applicable
        - Do NOT include section headers or numbers (already provided)
        - Do NOT include greetings or closings

        Key Points to Address:
        {section_plan.key_points}

        Content Requirements:
        {section_plan.content_requirements}

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the section content with professional formatting.
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self.prompt_api_service.build_enhanced_prompt(
            base_prompt, section_plan.header.lower().replace(" ", "_")
        )

        # Use JsonProcessingService for OpenAI requests (fixed deprecated method)
        if hasattr(self, "json_processing_service") and self.json_processing_service:
            result = self.json_processing_service._make_openai_request(enhanced_prompt)
        else:
            # Fallback if JsonProcessingService is not available
            result = None
        return result or f"<p>{section_plan.header.title()} analysis for this case.</p>"

    def _generate_closing_section(
        self,
        plan: EmailStructurePlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate professional closing section."""
        if context.closing_given:
            return ""

        context.closing_given = True

        return f"""
        <p>{plan.closing}</p>
        <p><strong>Sincerely,</strong><br>
        {analysis.intake_analysis.attorney_name if analysis.intake_analysis and analysis.intake_analysis.attorney_name else "Your Legal Team"}<br>
        Bernhardt Riley PLLC</p>
        """

    # === UTILITY AND HELPER METHODS ===

    def _format_section_header(
        self, number: int, header: str, citation: Optional[str] = None
    ) -> str:
        """Format section header with consistent structure."""
        if citation:
            return f"<h3>{number}. {header.upper()} ({citation})</h3>"
        return f"<h3>{number}. {header.upper()}</h3>"

    def _apply_enhanced_sanitization(self, content: str) -> str:
        """
        Apply enhanced sanitization rules to clean AI response content.

        This method implements specific regex rules for:
        - Normalizing punctuation spacing
        - Removing duplicate intro phrases
        - Eliminating leading commas from lines
        """
        if not content:
            return content

        # Normalize punctuation spacing: Add space after punctuation if missing
        content = re.sub(r"([.,])([A-Za-z])", r"\1 \2", content)

        # Remove duplicate intro phrases (case-insensitive)
        # This removes repeated occurrences of "the path forward" within the same text
        content = re.sub(
            r"(\bthe path forward\b).*?\1", r"\1", content, flags=re.IGNORECASE
        )

        # Eliminate leading commas from lines
        lines = content.split("\n")
        cleaned_lines = []
        for line in lines:
            # Remove leading commas and whitespace from each line
            cleaned_line = re.sub(r"^\s*,\s*", "", line)
            cleaned_lines.append(cleaned_line)
        content = "\n".join(cleaned_lines)

        return content

    # === FALLBACK AND ERROR HANDLING ===

    def _create_fallback_letter(
        self, analysis: CaseAnalysisResult, error_msg: str
    ) -> GeneratedLetter:
        """Create intelligent fallback letter with case-specific details when OpenAI generation fails."""
        logger.info(
            f"EMAIL GENERATOR V2: 🔄 Creating enhanced fallback letter due to: {error_msg}"
        )

        # Extract case-specific information
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

        # Extract specific details from documents for case-specific content
        case_details = self.content_extraction_service.extract_case_specific_details(
            analysis
        )

        # Create personalized greeting
        if "Devlin" in client_name and "Bell" in client_name:
            greeting = "Good afternoon Mr. Devlin and Ms. Bell,"
        else:
            greeting = f"Good afternoon {client_name},"

        # Generate case-specific factual summary
        factual_summary = self._generate_fallback_factual_summary(
            analysis, case_details
        )

        # Generate case-specific legal analysis
        legal_analysis = self._generate_fallback_legal_analysis(analysis, case_details)

        # Generate case-specific next steps
        next_steps = self._generate_fallback_next_steps(analysis, case_details)

        return GeneratedLetter(
            executive_summary=f"<p>{greeting}</p><p>I have completed my review of your {case_type.lower()} and am prepared to provide my findings and recommendations.</p>",
            background_summary=factual_summary,
            analysis_and_position=legal_analysis,
            media_summary=self._generate_fallback_media_summary(analysis),
            video_analysis_appendix="",
            strengths=self._generate_fallback_strengths(analysis, case_details),
            challenges=self._generate_fallback_challenges(analysis, case_details),
            recommendations=f"<p>Based on our comprehensive analysis of your {case_type.lower()}, strategic recommendations have been developed to advance your interests.</p>",
            next_steps=next_steps,
            closing_paragraph=f"<p>Please contact our office if you have any questions about this analysis or our recommendations.</p><p><strong>Sincerely,</strong><br>{analysis.intake_analysis.attorney_name if analysis.intake_analysis and analysis.intake_analysis.attorney_name else 'Your Legal Team'}<br>Bernhardt Riley PLLC</p>",
        )

    def _extract_case_specific_details(
        self, analysis: CaseAnalysisResult
    ) -> Dict[str, Any]:
        """Extract specific details from analysis for fallback content generation."""
        details = {
            "amounts": [],
            "dates": [],
            "parties": [],
            "locations": [],
            "documents": [],
            "key_facts": [],
        }

        # Extract from intake analysis
        if analysis.intake_analysis:
            if (
                hasattr(analysis.intake_analysis, "financial_impact")
                and analysis.intake_analysis.financial_impact
            ):
                # Extract monetary amounts
                import re

                amounts = re.findall(
                    r"\$[\d,]+\.?\d*", str(analysis.intake_analysis.financial_impact)
                )
                details["amounts"].extend(amounts)

            if (
                hasattr(analysis.intake_analysis, "key_facts")
                and analysis.intake_analysis.key_facts
            ):
                if isinstance(analysis.intake_analysis.key_facts, list):
                    details["key_facts"].extend(analysis.intake_analysis.key_facts)
                else:
                    details["key_facts"].append(str(analysis.intake_analysis.key_facts))

        # Extract from analyzed documents
        if analysis.analyzed_documents:
            for doc in analysis.analyzed_documents[:5]:  # Limit to first 5 documents
                details["documents"].append(doc.file_name)
                if hasattr(doc, "key_information") and doc.key_information:
                    details["key_facts"].append(
                        doc.key_information[:200]
                    )  # First 200 chars
                if doc.summary:
                    # Extract specific details from document summaries
                    import re

                    doc_amounts = re.findall(r"\$[\d,]+\.?\d*", doc.summary)
                    details["amounts"].extend(doc_amounts)

                    # Extract dates
                    date_patterns = re.findall(
                        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b[A-Za-z]+ \d{1,2}, \d{4}\b",
                        doc.summary,
                    )
                    details["dates"].extend(date_patterns)

        # Remove duplicates and limit
        details["amounts"] = list(set(details["amounts"]))[:5]
        details["dates"] = list(set(details["dates"]))[:5]
        details["key_facts"] = details["key_facts"][:10]

        return details

    def _generate_fallback_factual_summary(
        self, analysis: CaseAnalysisResult, case_details: Dict[str, Any]
    ) -> str:
        """Generate factual summary using extracted case details."""
        summary_parts = []

        # Add case type and parties
        if analysis.intake_analysis:
            if analysis.intake_analysis.case_type:
                summary_parts.append(
                    f"<p>This matter involves a {analysis.intake_analysis.case_type.lower()}."
                )

            if analysis.intake_analysis.case_summary:
                summary_parts.append(
                    f"<strong>Case Summary:</strong> {analysis.intake_analysis.case_summary[:300]}..."
                )

        # Add financial information
        if case_details["amounts"]:
            amounts_text = ", ".join(case_details["amounts"][:3])
            summary_parts.append(
                f"<p><strong>Financial Impact:</strong> Key amounts include {amounts_text}.</p>"
            )

        # Add key facts from documents
        if case_details["key_facts"]:
            summary_parts.append("<p><strong>Key Facts:</strong></p><ul>")
            for fact in case_details["key_facts"][:5]:
                if fact and fact.strip():
                    summary_parts.append(f"<li>{fact.strip()}</li>")
            summary_parts.append("</ul>")

        # Add document references
        if case_details["documents"]:
            doc_list = ", ".join(case_details["documents"][:5])
            summary_parts.append(
                f"<p><strong>Documents Reviewed:</strong> {doc_list}</p>"
            )

        # Fallback content if no specific details available
        if not summary_parts:
            summary_parts = [
                "<p>Based on our comprehensive document review, the key facts and circumstances of this matter have been analyzed.</p>",
                "<p>The factual background demonstrates the basis for the legal claims and strategic considerations outlined below.</p>",
            ]

        return "".join(summary_parts)

    def _generate_fallback_legal_analysis(
        self, analysis: CaseAnalysisResult, case_details: Dict[str, Any]
    ) -> str:
        """Generate legal analysis using available case information."""
        analysis_parts = []

        # Add case type specific analysis
        if analysis.intake_analysis and analysis.intake_analysis.case_type:
            case_type = analysis.intake_analysis.case_type.lower()
            if "contract" in case_type:
                analysis_parts.append(
                    "<p><strong>Contract Analysis:</strong> Under Florida contract law, the material terms and performance obligations are governed by Florida Statute Chapter 672.</p>"
                )
            elif "landlord" in case_type or "tenant" in case_type:
                analysis_parts.append(
                    "<p><strong>Landlord-Tenant Analysis:</strong> The matter is governed by Florida Residential Landlord and Tenant Act (Chapter 83, Florida Statutes).</p>"
                )
            elif "construction" in case_type:
                analysis_parts.append(
                    "<p><strong>Construction Law Analysis:</strong> Florida construction lien law (Chapter 713) and construction defect statutes apply.</p>"
                )
            else:
                analysis_parts.append(
                    f"<p><strong>Legal Analysis:</strong> This {case_type} matter is analyzed under applicable Florida statutes and case law.</p>"
                )

        # Add legal assessment if available
        if analysis.legal_assessment:
            if (
                hasattr(analysis.legal_assessment, "claim_viability")
                and analysis.legal_assessment.claim_viability
            ):
                analysis_parts.append(
                    f"<p><strong>Claim Viability:</strong> {analysis.legal_assessment.claim_viability}</p>"
                )

            if (
                hasattr(analysis.legal_assessment, "overall_evidence_strength")
                and analysis.legal_assessment.overall_evidence_strength
            ):
                analysis_parts.append(
                    f"<p><strong>Evidence Assessment:</strong> {analysis.legal_assessment.overall_evidence_strength}</p>"
                )

        # Fallback legal analysis
        if not analysis_parts:
            analysis_parts = [
                "<p><strong>Legal Analysis:</strong> Under Florida law, several key considerations apply to this matter.</p>",
                "<p>The legal framework provides the foundation for evaluating claim viability and strategic options.</p>",
            ]

        return "".join(analysis_parts)

    def _generate_fallback_next_steps(
        self, analysis: CaseAnalysisResult, case_details: Dict[str, Any]
    ) -> str:
        """Generate next steps recommendations using case information."""
        steps_parts = ["<p><strong>Recommended Next Steps:</strong></p><ul>"]

        # Add case-specific recommendations
        if (
            analysis.legal_assessment
            and hasattr(analysis.legal_assessment, "recommended_actions")
            and analysis.legal_assessment.recommended_actions
        ):
            if isinstance(analysis.legal_assessment.recommended_actions, list):
                for action in analysis.legal_assessment.recommended_actions[:5]:
                    steps_parts.append(f"<li>{action}</li>")
            else:
                steps_parts.append(
                    f"<li>{analysis.legal_assessment.recommended_actions}</li>"
                )

        # Add standard recommendations based on case type
        if analysis.intake_analysis and analysis.intake_analysis.case_type:
            case_type = analysis.intake_analysis.case_type.lower()
            if "contract" in case_type:
                steps_parts.extend(
                    [
                        "<li>Review contract terms and performance obligations</li>",
                        "<li>Assess damages and remedy options under Florida law</li>",
                        "<li>Consider demand letter or formal legal action</li>",
                    ]
                )
            elif any(
                keyword in case_type for keyword in ["landlord", "tenant", "eviction"]
            ):
                steps_parts.extend(
                    [
                        "<li>Review lease agreement and Florida Landlord-Tenant Act compliance</li>",
                        "<li>Evaluate notice requirements and procedural compliance</li>",
                        "<li>Assess damages and possession recovery options</li>",
                    ]
                )

        # Generic fallback recommendations
        if len(steps_parts) == 1:  # Only has opening tag
            steps_parts.extend(
                [
                    "<li>Continue document review and fact development</li>",
                    "<li>Assess legal options under Florida law</li>",
                    "<li>Develop strategic action plan</li>",
                    "<li>Schedule follow-up consultation</li>",
                ]
            )

        steps_parts.append("</ul>")
        return "".join(steps_parts)

    def _generate_fallback_media_summary(self, analysis: CaseAnalysisResult) -> str:
        """Generate media evidence summary if available."""
        if not (analysis.transcripted_media or analysis.video_insights):
            return ""

        media_parts = ["<p><strong>Evidence Review:</strong></p>"]

        if analysis.transcripted_media:
            media_parts.append(
                f"<p>Audio evidence from {len(analysis.transcripted_media)} file(s) has been analyzed and transcribed.</p>"
            )

        if analysis.video_insights:
            media_parts.append(
                f"<p>Video evidence from {len(analysis.video_insights)} file(s) has been processed and analyzed.</p>"
            )

        media_parts.append(
            "<p>The media evidence provides important context and supporting documentation for this matter.</p>"
        )

        return "".join(media_parts)

    def _generate_fallback_strengths(
        self, analysis: CaseAnalysisResult, case_details: Dict[str, Any]
    ) -> str:
        """Generate case strengths assessment."""
        strengths_parts = ["<p><strong>Case Strengths:</strong></p><ul>"]

        if case_details["documents"]:
            strengths_parts.append(
                f"<li>Comprehensive documentation including {len(case_details['documents'])} key files</li>"
            )

        if case_details["amounts"]:
            strengths_parts.append(
                "<li>Clear financial impact and damages documentation</li>"
            )

        if analysis.legal_assessment and hasattr(
            analysis.legal_assessment, "overall_evidence_strength"
        ):
            strengths_parts.append(
                f"<li>Evidence assessment: {analysis.legal_assessment.overall_evidence_strength}</li>"
            )

        # Generic strengths
        strengths_parts.extend(
            [
                "<li>Strong factual foundation for legal claims</li>",
                "<li>Clear basis for action under Florida law</li>",
            ]
        )

        strengths_parts.append("</ul>")
        return "".join(strengths_parts)

    def _generate_fallback_challenges(
        self, analysis: CaseAnalysisResult, case_details: Dict[str, Any]
    ) -> str:
        """Generate case challenges assessment."""
        challenges_parts = ["<p><strong>Strategic Considerations:</strong></p><ul>"]

        # Add case-specific challenges based on case type
        if analysis.intake_analysis and analysis.intake_analysis.case_type:
            case_type = analysis.intake_analysis.case_type.lower()
            if "contract" in case_type:
                challenges_parts.append(
                    "<li>Contract interpretation and performance standards under Florida law</li>"
                )
            elif "landlord" in case_type or "tenant" in case_type:
                challenges_parts.append(
                    "<li>Statutory notice requirements and procedural compliance</li>"
                )

        # Generic considerations
        challenges_parts.extend(
            [
                "<li>Statute of limitations and timing considerations</li>",
                "<li>Evidence preservation and discovery requirements</li>",
                "<li>Cost-benefit analysis of available legal remedies</li>",
            ]
        )

        challenges_parts.append("</ul>")
        return "".join(challenges_parts)

    def _generate_fallback_section_content(
        self, section_plan: SectionPlan, analysis: CaseAnalysisResult
    ) -> str:
        """Generate basic fallback content for a failed section."""
        section_name = section_plan.header.lower().replace("_", " ")
        return (
            f"<p>{section_name.title()} analysis for this case under Florida law.</p>"
        )

    def _prepare_template_context(self, content: str) -> str:
        """
        Enhanced template context preparation with comprehensive content processing.
        This method centralizes all content formatting logic.
        """
        if not content:
            return content

        # JSON logging for template context preparation
        context_log = {
            "module": "EmailGeneratorV2",
            "method": "_prepare_template_context",
            "hypothesis_id": "template_processing_issue",
            "input_length": len(content),
            "timestamp": datetime.now().isoformat(),
        }
        logger.debug(f"EMAIL_GENERATOR_DEBUG: {json.dumps(context_log)}")

        # Apply comprehensive formatting pipeline
        processed_content = self._clean_ai_response(content)

        # Additional template-specific processing
        processed_content = self._ensure_html_structure(processed_content)
        processed_content = self._normalize_spacing(processed_content)

        return processed_content

    def _ensure_html_structure(self, content: str) -> str:
        """
        Ensure content has proper HTML structure for template rendering.

        This method processes content line-by-line to ensure that any floating text
        content is properly wrapped in <p> tags, while preserving existing HTML structure.
        It handles edge cases like text that appears after closing block tags.
        """
        if not content or not content.strip():
            return content

        # Define block-level HTML elements that don't need paragraph wrapping
        block_elements = r"<(?:p|div|ul|ol|li|h[1-6]|blockquote|pre|hr|br)\b"
        closing_block_elements = r"</(?:p|div|ul|ol|li|h[1-6]|blockquote|pre)>"

        # Split content into lines for processing
        lines = content.split("\n")
        processed_lines = []

        for line in lines:
            stripped_line = line.strip()

            # Skip empty lines
            if not stripped_line:
                processed_lines.append(line)
                continue

            # Check if line contains any block-level elements (opening or closing)
            has_block_element = bool(
                re.search(block_elements, stripped_line, re.IGNORECASE)
            )
            has_closing_block = bool(
                re.search(closing_block_elements, stripped_line, re.IGNORECASE)
            )

            # If line has block elements, keep as-is
            if has_block_element or has_closing_block:
                processed_lines.append(line)
                continue

            # Check if line contains only HTML tags (no text content)
            text_only = re.sub(r"<[^>]*>", "", stripped_line).strip()
            if not text_only:
                processed_lines.append(line)
                continue

            # This is floating text that needs to be wrapped in <p> tags
            # Check if it's already wrapped in paragraph tags
            if not stripped_line.startswith("<p") and not stripped_line.endswith(
                "</p>"
            ):
                # Preserve original indentation while wrapping content
                indentation = line[: len(line) - len(line.lstrip())]
                wrapped_line = f"{indentation}<p>{stripped_line}</p>"
                processed_lines.append(wrapped_line)
            else:
                processed_lines.append(line)

        # Rejoin the processed lines
        processed_content = "\n".join(processed_lines)

        # Handle edge case: floating text after closing block tags on the same line
        # Pattern: </tag>Some floating text
        processed_content = re.sub(
            r"(</(?:ul|ol|div|blockquote)>)\s*([^<\s][^<]*?)(?=\s*$|\s*<)",
            r"\1\n<p>\2</p>",
            processed_content,
            flags=re.MULTILINE,
        )

        # Clean up any empty paragraph tags that might have been created
        processed_content = re.sub(r"<p>\s*</p>", "", processed_content)

        # Ensure proper spacing around paragraph tags
        processed_content = re.sub(r"</p>\s*<p>", "</p>\n<p>", processed_content)

        return processed_content.strip()

    def _normalize_spacing(self, content: str) -> str:
        """Normalize spacing for consistent template rendering."""
        if not content:
            return content

        # Normalize line endings
        content = re.sub(r"\r\n|\r", "\n", content)

        # Ensure consistent spacing around HTML elements
        content = re.sub(r">\s*<", "><", content)
        content = re.sub(r"(<(?:p|div|h[1-6])[^>]*>)\s*", r"\1", content)
        content = re.sub(r"\s*(</(?:p|div|h[1-6])>)", r"\1", content)

        return content.strip()

    # === POST-PROCESSING FUNCTIONS (REMOVED - SUBTASK 5A REVERSION) ===
    # The aggressive post-processing methods were causing HTML structure issues
    # and breaking validation. Removed: collapse_adjacent_bullets, trim_repeated_phrases,
    # enforce_sentence_length, apply_post_processing

    # === CONTENT FORMATTING HELPER METHODS ===

    def _format_legal_analysis(self, content: str) -> str:
        """Format legal analysis content with proper structure and hierarchy."""
        if not content:
            return content

        # Ensure consistent header formatting for legal analysis sections
        content = re.sub(
            r"(?i)(legal\s+analysis|analysis\s+and\s+position|statutory\s+analysis)",
            lambda m: f"<strong>{m.group(1).upper()}</strong>",
            content,
        )

        # Format subsection headers (A, B, C, etc.)
        content = re.sub(
            r"^([A-Z])\.\s*([A-Z][^.]*?)(?=\n|$)",
            r"<strong>\1. \2</strong>",
            content,
            flags=re.MULTILINE,
        )

        return content

    def _format_recommendations(self, content: str) -> str:
        """Format recommendation sections with clear structure and emphasis."""
        if not content:
            return content

        # Format recommendation headers
        content = re.sub(
            r"(?i)(recommended?\s+(?:next\s+)?steps?|recommendations?|next\s+steps?)",
            lambda m: f"<strong>{m.group(1).upper()}</strong>",
            content,
        )

        # Format numbered recommendations
        content = re.sub(
            r"^(\d+)\.\s*([^.]+?)(?=\n|$)",
            r"<strong>\1.</strong> \2",
            content,
            flags=re.MULTILINE,
        )

        return content

    def _format_subsections(self, content: str) -> str:
        """Format subsections with proper indentation and hierarchy."""
        if not content:
            return content

        # Format lettered subsections (A, B, C)
        content = re.sub(
            r"^([A-Z])\.\s+(.+?)$",
            r"    <strong>\1.</strong> \2",
            content,
            flags=re.MULTILINE,
        )

        # Format numbered subsections with proper spacing
        content = re.sub(
            r"^(\d+)\.\s+(.+?)$",
            r"<strong>\1.</strong> \2",
            content,
            flags=re.MULTILINE,
        )

        return content

    def _strip_citations(self, content: str) -> str:
        """ENHANCED: Strip all legal citations using comprehensive regex pattern."""
        if not content:
            return content

        # Use the enhanced citation filter regex from configuration
        try:
            citation_filter_regex = self.config.get("citation_filter_regex", "")
            if citation_filter_regex:
                content = re.sub(
                    citation_filter_regex, "", content, flags=re.IGNORECASE
                )

            # Additional comprehensive citation cleanup
            content = re.sub(
                r"\b(Fla\.?\s*Stat\.?|F\.S\.?)\s*§?\s*[\d\w\.\-\(\)]+",
                "",
                content,
                flags=re.IGNORECASE,
            )
            content = re.sub(r"\bChapter\s*\d+\b", "", content, flags=re.IGNORECASE)
            content = re.sub(r"§+\s*[\d\w\.\-\(\)]+", "", content)
            content = re.sub(
                r"\b\d+\.\d+\b", "", content
            )  # Remove section numbers like 123.45
            content = re.sub(
                r"\([^)]*§[^)]*\)", "", content
            )  # Remove parenthetical citations with §
            content = re.sub(
                r"\bFla\b\.?\s*R\.", "", content, flags=re.IGNORECASE
            )  # Florida Rules
            content = re.sub(
                r"\bFla\b\.?\s*Admin\.", "", content, flags=re.IGNORECASE
            )  # Florida Admin
            content = re.sub(
                r"\d{1,3}\s*So\.", "", content, flags=re.IGNORECASE
            )  # Southern Reporter
            content = re.sub(
                r"section\s*\d+", "", content, flags=re.IGNORECASE
            )  # Section references

            # Collapse extra spaces left behind
            content = re.sub(r"\s{2,}", " ", content).strip()
            return content

        except Exception as e:
            logger.error(
                f"EMAIL GENERATOR V2: ❌ Enhanced citation filtering failed: {e}"
            )
            # Fallback to basic filtering
            content = re.sub(
                r"\b(Fla\.?\s*Stat\.?|F\.S\.)\s*§?\s*[\d\w\.\-\(\)]+",
                "",
                content,
                flags=re.IGNORECASE,
            )
            content = re.sub(r"\bChapter\s*\d+\b", "", content, flags=re.IGNORECASE)
            content = re.sub(r"§+\s*[\d\w\.\-\(\)]+", "", content)
            content = re.sub(r"\s{2,}", " ", content).strip()
            return content

    def _format_bullet_points(self, content: str) -> str:
        """Format bullet points for professional presentation."""
        if not content:
            return content

        # Convert dashes and asterisks to proper bullet points
        content = re.sub(r"^[-*]\s+(.+?)$", r"• \1", content, flags=re.MULTILINE)

        # Wrap bullet points in proper HTML structure
        lines = content.split("\n")
        in_bullet_section = False
        formatted_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("•"):
                if not in_bullet_section:
                    formatted_lines.append("<ul>")
                    in_bullet_section = True
                formatted_lines.append(f"<li>{stripped[1:].strip()}</li>")
            else:
                if in_bullet_section:
                    formatted_lines.append("</ul>")
                    in_bullet_section = False
                formatted_lines.append(line)

        if in_bullet_section:
            formatted_lines.append("</ul>")

        return "\n".join(formatted_lines)

    def _clean_section_numbering(self, content: str) -> str:
        """Clean up redundant and repeated section numbering."""
        if not content:
            return content

        # Remove numbered section headers at the beginning of content (template handles headers)
        content = re.sub(
            r"^(\d+)\.\s*([A-Z][A-Z\s]+)(?:\n|$)", "", content, flags=re.MULTILINE
        )

        # Remove any remaining standalone section headers
        content = re.sub(
            r"^([A-Z][A-Z\s]{10,})(?:\n|$)", "", content, flags=re.MULTILINE
        )

        # Remove redundant section numbers at the beginning of content
        content = re.sub(
            r"^(\d+)\.\s*(\d+)\.\s*([A-Z][^.]*?)$",
            r"\1. \3",
            content,
            flags=re.MULTILINE,
        )

        # Clean up repeated headers
        content = re.sub(r"^([A-Z\s]+)\n\1$", r"\1", content, flags=re.MULTILINE)

        # Remove section numbers that appear mid-sentence
        content = re.sub(r"(\w+)\s+\d+\.\s+([A-Z])", r"\1 \2", content)

        return content

    def _ensure_proper_whitespace(self, content: str) -> str:
        """Ensure proper whitespace and line breaks for readability."""
        if not content:
            return content

        # Add proper spacing after headers
        content = re.sub(r"(<h[1-6][^>]*>.*?</h[1-6]>)(\w)", r"\1\n\n\2", content)

        # Add spacing before new paragraphs
        content = re.sub(r"(</p>)(<p[^>]*>)", r"\1\n\n\2", content)

        # Ensure proper spacing around bullet points
        content = re.sub(r"(</ul>)(<p[^>]*>)", r"\1\n\n\2", content)

        content = re.sub(r"(</p>)(<ul>)", r"\1\n\n\2", content)

        # Clean up excessive whitespace while preserving intentional breaks
        content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)
        content = re.sub(r"^\s+|\s+$", "", content, flags=re.MULTILINE)

        return content

    def _trim_wordiness(self, content: str) -> str:
        """Trim verbose and repetitive language for concise communication."""
        if not content:
            return content

        # Remove conversational filler
        wordy_patterns = [
            r"\b(?:it should be noted that|it is important to note that|please note that)\b",
            r"\b(?:in conclusion|to conclude|in summary)\b",
            r"\b(?:as mentioned above|as previously stated|as noted earlier)\b",
            r"\b(?:furthermore|moreover|additionally)\b(?=.*?furthermore|.*?moreover|.*?additionally)",
        ]

        for pattern in wordy_patterns:
            content = re.sub(pattern, "", content, flags=re.IGNORECASE)

        # Simplify overly complex sentences
        content = re.sub(
            r"\b(?:in order to|for the purpose of)\b",
            "to",
            content,
            flags=re.IGNORECASE,
        )

        # Remove redundant disclaimers in the middle of content
        content = re.sub(
            r"(?i)\b(?:this is not legal advice|consult with an attorney|seek legal counsel)\b(?=.*?\w{10,})",
            "",
            content,
        )

        # Clean up extra spaces left by removals
        content = re.sub(r"\s{2,}", " ", content)
        content = re.sub(r"^\s+|\s+$", "", content, flags=re.MULTILINE)

        return content

    def _apply_enhanced_citation_filtering(self, content: str) -> str:
        """
        Apply enhanced citation filtering to raw text using comprehensive regex patterns.

        This method processes raw text BEFORE any HTML structure is applied,
        ensuring that citations are removed without corrupting HTML tags.

        Args:
            content: Raw text content to filter

        Returns:
            Content with citations removed
        """
        if not content:
            return content

        try:
            logger.debug(
                "EMAIL GENERATOR V2: Starting enhanced citation filtering on raw text..."
            )

            # Get citation filter regex from configuration
            citation_filter_regex = self.config.get("citation_filter_regex", "")

            if citation_filter_regex:
                logger.info(
                    f"EMAIL GENERATOR V2: Applying configured citation filter: {citation_filter_regex}"
                )
                content = re.sub(
                    citation_filter_regex, "", content, flags=re.IGNORECASE
                )

            # Enhanced comprehensive citation cleanup on raw text
            original_length = len(content)

            # Remove Florida Statute references
            content = re.sub(
                r"\b(Fla\.?\s*Stat\.?|F\.S\.?)\s*§?\s*[\d\w\.\-\(\)]+",
                "",
                content,
                flags=re.IGNORECASE,
            )

            # Remove Chapter references
            content = re.sub(r"\bChapter\s*\d+\b", "", content, flags=re.IGNORECASE)

            # Remove section symbols and numbers
            content = re.sub(r"§+\s*[\d\w\.\-\(\)]+", "", content)

            # Remove decimal section numbers
            content = re.sub(r"\b\d{2,3}\.\d+\b", "", content)

            # Remove parenthetical citations with section symbols
            content = re.sub(r"\([^)]*§[^)]*\)", "", content)

            # Remove Florida Rules references
            content = re.sub(r"\bFla\b\.?\s*R\.", "", content, flags=re.IGNORECASE)

            # Remove Florida Admin references
            content = re.sub(r"\bFla\b\.?\s*Admin\.", "", content, flags=re.IGNORECASE)

            # Remove Southern Reporter citations
            content = re.sub(r"\d{1,3}\s*So\.", "", content, flags=re.IGNORECASE)

            # Remove generic section references
            content = re.sub(r"\bsection\s*\d+", "", content, flags=re.IGNORECASE)

            # Clean up extra spaces and normalize whitespace
            content = re.sub(r"\s{2,}", " ", content)
            content = content.strip()

            filtered_length = len(content)
            removed_chars = original_length - filtered_length

            if removed_chars > 0:
                logger.info(
                    f"EMAIL GENERATOR V2: ✅ Enhanced citation filtering removed {removed_chars} characters"
                )
            else:
                logger.info("EMAIL GENERATOR V2: No citations found to remove")

            return content

        except re.error as e:
            logger.info(f"EMAIL GENERATOR V2: ❌ Invalid citation filter regex: {e}")
            return content
        except Exception as e:
            logger.error(
                f"EMAIL GENERATOR V2: ❌ Enhanced citation filtering failed: {e}"
            )
            return content

    def _apply_sentence_splitting_logic(self, content: str) -> str:
        """
        Apply sentence splitting logic to improve readability on raw text.

        This method processes raw text to normalize sentence structure and improve
        readability without affecting HTML structure.

        Args:
            content: Raw text content to process

        Returns:
            Content with improved sentence structure
        """
        if not content:
            return content

        try:
            logger.debug(
                "EMAIL GENERATOR V2: Starting sentence splitting logic on raw text..."
            )

            original_length = len(content)

            # Split very long sentences at appropriate points
            # Target sentences over 15 words for splitting (aligned with validation criteria)
            sentences = re.split(r"(?<=[.!?])\s+", content)
            processed_sentences = []

            for sentence in sentences:
                word_count = len(sentence.split())

                if word_count > 15:
                    # Attempt to split at coordinating conjunctions or semicolons
                    split_points = [
                        r",\s+(and|but|or|however|moreover|furthermore|additionally)",
                        r";\s*",
                        r",\s+(?=which|that|where|when)",
                        r",\s+(?=because|since|although|while|if)",
                    ]

                    sentence_parts = [sentence]
                    for pattern in split_points:
                        new_parts = []
                        for part in sentence_parts:
                            # Only split if the part is still long
                            if len(part.split()) > 25:
                                split_parts = re.split(f"({pattern})", part, maxsplit=1)
                                if len(split_parts) > 1:
                                    # Rejoin the conjunction with the second part
                                    first_part = split_parts[0].strip()
                                    conjunction = (
                                        split_parts[1] if len(split_parts) > 1 else ""
                                    )
                                    remaining = (
                                        split_parts[2] if len(split_parts) > 2 else ""
                                    )

                                    if first_part:
                                        new_parts.append(first_part + ".")
                                    if remaining:
                                        # Capitalize first word of new sentence
                                        remaining = (
                                            conjunction.strip()
                                            + " "
                                            + remaining.strip()
                                        )
                                        remaining = (
                                            remaining[0].upper() + remaining[1:]
                                            if remaining
                                            else ""
                                        )
                                        new_parts.append(remaining)
                                else:
                                    new_parts.append(part)
                            else:
                                new_parts.append(part)
                        sentence_parts = new_parts
                        if len(sentence_parts) > 1:
                            break  # Found a good split point

                    processed_sentences.extend(sentence_parts)
                else:
                    processed_sentences.append(sentence)

            # Rejoin sentences with proper spacing
            content = " ".join(processed_sentences)

            # Clean up any formatting issues from splitting
            content = re.sub(r"\.\s*\.", ".", content)  # Remove double periods
            # CRITICAL FIX: Use CSS-aware spacing normalization instead of global \s+ replacement
            content = self._normalize_spacing_preserve_css_global(content)
            content = content.strip()

            processed_length = len(content)

            if processed_length != original_length:
                logger.info(
                    f"EMAIL GENERATOR V2: ✅ Sentence splitting applied - length changed from {original_length} to {processed_length}"
                )
            else:
                logger.info("EMAIL GENERATOR V2: No sentence splitting needed")

            return content

        except Exception as e:
            logger.error(f"EMAIL GENERATOR V2: ❌ Sentence splitting logic failed: {e}")
            return content

    @staticmethod
    def _sanitize_output_grammar(text: str) -> str:
        """
        Sanitize output grammar with specific regex operations.

        Performs the following operations:
        - Normalize punctuation spacing
        - Remove duplicate introductory phrases (case-insensitive)
        - Eliminate leading commas from each line

        Args:
            text: The text string to sanitize

        Returns:
            The processed text with grammar corrections applied
        """
        if not text:
            return text

        # Normalize punctuation spacing: Add space after punctuation if missing
        text = re.sub(r"([.,])([A-Za-z])", r"\1 \2", text)

        # Remove duplicate introductory phrases (case-insensitive)
        text = re.sub(
            r"(\bthe path forward\b).*?\1", r"\1", text, flags=re.IGNORECASE | re.DOTALL
        )

        # Eliminate leading commas from each line
        text = "\n".join([re.sub(r"^\s*,\s*", "", line) for line in text.splitlines()])

        return text

    # === EXTRACTION METHODS (from original code) ===

    def _extract_key_facts(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract key facts for the factual summary section."""
        facts = []
        if analysis.intake_analysis and analysis.intake_analysis.key_facts:
            if isinstance(analysis.intake_analysis.key_facts, list):
                facts.extend(analysis.intake_analysis.key_facts)
            else:
                facts.append(str(analysis.intake_analysis.key_facts))

        for doc in analysis.analyzed_documents:
            if hasattr(doc, "key_information") and doc.key_information:
                facts.append(doc.key_information)

        return facts[:5]

    def _identify_emphasis_items(self, analysis: CaseAnalysisResult) -> Dict[str, str]:
        """Identify items that should be bolded."""
        emphasis_items = {}

        if analysis.intake_analysis and analysis.intake_analysis.financial_impact:
            financial_info = str(analysis.intake_analysis.financial_impact)
            amounts = re.findall(r"\$[\d,]+\.?\d*", financial_info)
            for i, amount in enumerate(amounts):
                emphasis_items[f"amount_{i + 1}"] = amount

        return emphasis_items

    def _extract_legal_issues(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract legal issues for analysis section."""
        issues = []

        if analysis.legal_assessment:
            if analysis.legal_assessment.claim_viability:
                issues.append(
                    f"Claim viability: {analysis.legal_assessment.claim_viability}"
                )

        if analysis.intake_analysis and analysis.intake_analysis.legal_claims:
            issues.extend(analysis.intake_analysis.legal_claims)

        return issues

    def _extract_media_evidence_points(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract key points about media evidence."""
        points = []

        for media in analysis.transcripted_media:
            points.append(f"Audio analysis of {media.file_name}")

        for video in analysis.video_insights:
            points.append(f"Video analysis of {video.file_name}")

        return points

    def _extract_case_assessment_points(
        self, analysis: CaseAnalysisResult
    ) -> List[str]:
        """Extract points for case assessment section."""
        points = []

        if analysis.legal_assessment:
            if analysis.legal_assessment.claim_viability:
                points.append(
                    f"Claim assessment: {analysis.legal_assessment.claim_viability}"
                )
            if analysis.legal_assessment.overall_evidence_strength:
                points.append(
                    f"Evidence strength: {analysis.legal_assessment.overall_evidence_strength}"
                )

        return points

    def _extract_recommendations(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract recommendations for next steps."""
        recommendations = []

        if analysis.legal_assessment and analysis.legal_assessment.recommended_actions:
            if isinstance(analysis.legal_assessment.recommended_actions, list):
                recommendations.extend(analysis.legal_assessment.recommended_actions)
            else:
                recommendations.append(
                    str(analysis.legal_assessment.recommended_actions)
                )

        return recommendations

    def _ensure_analysis_completeness(self, analysis: CaseAnalysisResult) -> None:
        """Ensure analysis has required components."""
        from backend.utils.validators import (
            create_fallback_demand_letter_evaluation,
            create_fallback_legal_assessment,
        )

        if not analysis.intake_analysis:
            from backend.utils.data_models import EnhancedIntakeAnalysis

            analysis.intake_analysis = EnhancedIntakeAnalysis(
                client_name="Client",
                attorney_name="Attorney",
                case_summary="Legal matter requiring analysis",
                case_type="Legal Case",
                urgency_level="Standard",
            )

        if not analysis.legal_assessment:
            from backend.utils.data_models import LegalAssessment

            analysis.legal_assessment = LegalAssessment.model_validate(
                create_fallback_legal_assessment()
            )

        if not analysis.demand_letter_evaluation:
            from backend.utils.data_models import DemandLetterEvaluation

            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(
                create_fallback_demand_letter_evaluation()
            )

    def _generate_video_analysis_appendix(self, analysis: CaseAnalysisResult) -> str:
        """Generate video analysis appendix if video data exists."""
        if not analysis.video_insights:
            return ""

        # Use existing video appendix generation logic
        video_data_for_prompt = []

        for video_insight in analysis.video_insights:
            video_data = {
                "file_name": video_insight.file_name,
                "transcript": video_insight.transcript,
                "labels": video_insight.labels,
                "objects": video_insight.objects,
                "text_annotations": video_insight.text_annotations,
                "duration": video_insight.duration,
                "confidence": video_insight.confidence,
            }

            if (
                hasattr(video_insight, "insights_gcs_uri")
                and video_insight.insights_gcs_uri
            ):
                if (
                    hasattr(video_insight, "insights_summary")
                    and video_insight.insights_summary
                ):
                    video_data["insights"] = video_insight.insights_summary
                else:
                    video_data["insights"] = "Video analysis summary not available"
            else:
                video_data["insights"] = video_insight.insights

            video_data_for_prompt.append(video_data)

        prompt = f"""
        Generate a video analysis appendix section using AUTHENTIC_ATTORNEY style.

        REQUIREMENTS:
        - Create section titled "Video Analysis Appendix"
        - Provide detailed summary for each video file
        - Explain significance under Florida evidence law
        - Use professional legal language
        - Format with HTML tags for clean presentation

        Video Analysis Data:
        {video_data_for_prompt}

        Case Context:
        Client: {analysis.intake_analysis.client_name if analysis.intake_analysis else "Client"}
        Case Type: {analysis.intake_analysis.case_type if analysis.intake_analysis else "Legal Matter"}
        """

        # Get persona from configuration
        persona = self.config.get("personas", {}).get("CONTINUING_ATTORNEY_ADVISOR", "")
        result = self._make_openai_request(prompt, persona)
        return result or ""

    # === LEGACY COMPATIBILITY METHODS ===

    def generate_findings(self, analysis: CaseAnalysisResult) -> GeneratedLetter:
        """
        Legacy compatibility method - now uses the refactored architecture.
        """
        try:
            output = self.generate_email_with_debug(analysis)
            return output.letter
        except (ValueError, TypeError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"EMAIL GENERATOR V2: Error in generate_findings: {e}")
            return self._create_fallback_letter(analysis, str(e))

    def generate_email_and_analysis_docs(
        self, analysis: CaseAnalysisResult
    ) -> Dict[str, str]:
        """
        Generate email and analysis documents using the refactored generator.
        """
        try:
            # Ensure analysis completeness
            self.content_extraction_service.ensure_analysis_completeness(analysis)

            # CRITICAL FIX: Generate JSON data using new architecture
            logger.info(
                "EMAIL GENERATOR V2: Generating structured JSON for template context..."
            )
            json_data = self._generate_structured_json(analysis)
            validated_json = self._validate_json_response(json_data)

            # Generate letter using new architecture
            generated_letter = self.generate_findings(analysis)

            # Render templates
            main_template = self.jinja_env.get_template("findings_email.jinja2")
            appendix_template = self.jinja_env.get_template("document_appendix.jinja2")

            # Create pre-composed greeting line
            client_name = (
                analysis.intake_analysis.client_name
                if analysis.intake_analysis and analysis.intake_analysis.client_name
                else "Client"
            )
            greeting_line = f"Dear {client_name},"

            template_context = {
                "analysis": analysis,
                "generated_letter": generated_letter,
                "current_date": datetime.now().strftime("%B %d, %Y"),
                "case_timeline": getattr(analysis, "case_timeline", []),
                "format_video_analysis": self.format_video_analysis_for_appendix,
                "case_name": analysis.intake_analysis.case_type
                if analysis.intake_analysis and analysis.intake_analysis.case_type
                else "Your Case",
                "greeting_line": greeting_line,
                "results": validated_json,  # CRITICAL: Add JSON data for enhanced template
            }

            # DIAGNOSTIC LOGGING: Template Variable Values Before Rendering
            template_var_log = {
                "module": "EmailGeneratorV2",
                "method": "generate_email_and_analysis_docs",
                "hypothesis_id": "template_variable_issue",
                "stage": "pre_template_render",
                "analysis_intake_case_type": analysis.intake_analysis.case_type
                if analysis.intake_analysis
                else None,
                "analysis_intake_client_name": analysis.intake_analysis.client_name
                if analysis.intake_analysis
                else None,
                "analysis_intake_analysis_exists": analysis.intake_analysis is not None,
                "template_context_case_name": template_context.get("case_name"),
                "template_context_client_name": template_context.get("client_name"),
                "template_context_keys": list(template_context.keys()),
                "template_context_analysis_type": type(
                    template_context.get("analysis")
                ).__name__
                if template_context.get("analysis")
                else None,
                "timestamp": datetime.now().isoformat(),
            }
            logger.debug(
                f"EMAIL_GENERATOR_DEBUG: {json.dumps(template_var_log, indent=2)}"
            )

            # Log the complete template context dictionary being passed to render()
            context_dict_log = {
                "module": "EmailGeneratorV2",
                "method": "generate_email_and_analysis_docs",
                "hypothesis_id": "template_variable_issue",
                "stage": "template_context_dump",
                "template_render_args": {
                    "results": {
                        "analysis_present": template_context.get("analysis")
                        is not None,
                        "generated_letter_present": template_context.get(
                            "generated_letter"
                        )
                        is not None,
                        "current_date": template_context.get("current_date"),
                        "case_timeline_length": len(
                            template_context.get("case_timeline", [])
                        ),
                        "case_name": template_context.get("case_name"),
                        "client_name": template_context.get("client_name"),
                    },
                    "current_date": template_context["current_date"],
                },
                "timestamp": datetime.now().isoformat(),
            }
            logger.debug(
                f"EMAIL_GENERATOR_DEBUG: {json.dumps(context_dict_log, indent=2)}"
            )

            # CRITICAL: Validate required template variables before rendering
            # This prevents jinja2.exceptions.UndefinedError for missing required variables
            required_vars = ["case_name", "greeting_line"]
            for var_name in required_vars:
                if var_name not in template_context:
                    raise ValueError(
                        f"Template context is missing required key: '{var_name}'"
                    )
                var_value = template_context[var_name]
                if not var_value or (
                    isinstance(var_value, str) and not var_value.strip()
                ):
                    raise ValueError(
                        f"Template context key '{var_name}' is empty or None"
                    )

            logger.info(
                "EMAIL GENERATOR V2: ✅ Template context validation passed - required variables present"
            )

            # === Template Variable Validation ===
            required_keys = ["case_name", "greeting_line"]
            for key in required_keys:
                if not template_context.get(key):
                    raise ValueError(
                        f"Template context is missing required key or key is empty: '{key}'"
                    )

            # CRITICAL FIX: Pass validated_json as results, not template_context
            # Add firm_contact variable to fix jinja2.exceptions.UndefinedError
            firm_contact = {
                "phone": "555-123-4567",
                "email": "contact@bernhardt-riley.com",
            }

            main_html_content = main_template.render(
                results=validated_json,
                current_date=template_context["current_date"],
                case_name=template_context["case_name"],
                greeting_line=template_context["greeting_line"],
                attorney_signature=template_context.get(
                    "attorney_signature", "Your Legal Team"
                ),
                firm_name=template_context.get("firm_name", "Bernhardt Riley PLLC"),
                firm_contact=firm_contact,
            )
            appendix_html_content = appendix_template.render(
                results=validated_json,
                current_date=template_context["current_date"],
                case_name=template_context["case_name"],
                greeting_line=template_context["greeting_line"],
            )

            # STAGES 3.5 through 9 are commented out as per refactoring requirements.
            # The goal is to return the raw HTML fragment from the initial generation.

            # # STAGE 3.5: POST-PROCESSING & SIMPLIFICATION - ENABLED FOR READABILITY
            # print("EMAIL GENERATOR V2: STAGE 3.5-3.6 - POST-PROCESSING & SIMPLIFICATION")

            # # Apply AI-based simplification to improve readability scores
            # main_html_content = self._apply_comprehensive_simplification(main_html_content)
            # print("EMAIL GENERATOR V2: ✅ Comprehensive simplification applied")

            # # CRITICAL: Apply final sanitization after full HTML assembly
            # print("EMAIL GENERATOR V2: STAGE 4 - FINAL SANITIZATION")
            # main_html_content = self._apply_final_sanitization(
            #     html_content=main_html_content,
            #     apply_polishing=True,  # Enable polish for full email realignment
            #     word_limit=850  # STRICT 850-word limit for complete email
            # )

            # # STAGE 5: WORD COUNT VALIDATION LOOP
            # print("EMAIL GENERATOR V2: STAGE 5 - WORD COUNT VALIDATION")
            # main_html_content = self._enforce_850_word_limit(
            #     html_content=main_html_content,
            #     generated_letter=generated_letter,
            #     analysis=analysis
            # )

            # appendix_html_content = self._apply_final_sanitization(
            #     html_content=appendix_html_content,
            #     apply_polishing=False,  # Skip polish for appendix
            #     word_limit=1500  # Higher limit for appendix
            # )

            # # STAGE 6: POST-PROCESSOR GUARD - Final validation and cleanup
            # print("EMAIL GENERATOR V2: STAGE 6 - POST-PROCESSOR GUARD")
            # main_html_content = self._apply_post_processor_guard(main_html_content)

            # # STAGE 6.5: READABILITY GATE WITH AGGRESSIVE SIMPLIFICATION
            # print("EMAIL GENERATOR V2: STAGE 6.5 - READABILITY GATE")

            # # STAGE 7: DISCLAIMER DUPLICATION CHECK

            # # STAGE 8: NORMALIZATION POST-PROCESSING
            # print("EMAIL GENERATOR V2: STAGE 8 - NORMALIZATION POST-PROCESSING")
            # main_html_content = self._apply_normalization_fixes(main_html_content)
            # print("EMAIL GENERATOR V2: ✅ Normalization post-processing completed")

            # # STAGE 9: PRETTY-PRINT HTML OUTPUT
            # print("EMAIL GENERATOR V2: STAGE 9 - PRETTY-PRINT HTML")
            # main_html_content = self._prettify_html_output(main_html_content)
            # appendix_html_content = self._prettify_html_output(appendix_html_content)

            return {"main_letter": main_html_content, "appendix": appendix_html_content}

        except (ValueError, TypeError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"EMAIL GENERATOR V2: Error generating documents: {e}")
            return self._generate_fallback_documents(analysis, str(e))

    def _generate_fallback_documents(
        self, analysis: CaseAnalysisResult, error_message: str
    ) -> Dict[str, str]:
        """Generate fallback documents when template rendering fails."""
        client_name = (
            analysis.intake_analysis.client_name
            if analysis.intake_analysis
            else "Client"
        )
        current_date = datetime.now().strftime("%B %d, %Y")

        main_letter = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Legal Findings Letter - {client_name}</title>
            <style>
                body {{ font-family: Times, serif; margin: 40px; line-height: 1.6; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                h1 {{ color: #2c3e50; }}
                h2 {{ color: #34495e; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Legal Findings Letter</h1>
                <p><strong>Date:</strong> {current_date}</p>
                <p><strong>Client:</strong> {client_name}</p>
            </div>

            <h2>Executive Summary</h2>
            <p>We have completed our analysis of your legal matter and are prepared to provide our findings and recommendations.</p>

            <h2>Next Steps</h2>
            <p>Please contact our office to discuss the findings and next steps for your case.</p>

            <p style="margin-top: 40px;">
                <strong>Sincerely,</strong><br>
                Your Legal Team<br>
                Bernhardt Riley PLLC
            </p>
        </body>
        </html>
        """

        appendix = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Case Analysis Appendix - {client_name}</title>
            <style>
                body {{ font-family: Times, serif; margin: 40px; line-height: 1.6; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                h1 {{ color: #2c3e50; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Case Analysis Appendix</h1>
                <p><strong>Date:</strong> {current_date}</p>
                <p><strong>Client:</strong> {client_name}</p>
            </div>

            <h2>Document Review</h2>
            <p>Analysis documentation is available for detailed review.</p>
        </body>
        </html>
        """

        return {"main_letter": main_letter, "appendix": appendix}

    # === READABILITY VALIDATION LOOPS (REMOVED - SUBTASK 5A REVERSION) ===
    # The aggressive readability validation and regeneration loops were breaking validation
    # Removed: _clean_and_validate_generated_text, _simplify_text_content,
    # _validate_section_readability_with_regeneration, _regenerate_section_for_readability

    def format_video_analysis_for_appendix(self, video_insight) -> str:
        """Format video analysis results into clean, readable text for document appendix."""

        formatted_text = []

        # Handle both VideoInsight and EnhancedVideoInsight
        if hasattr(video_insight, "insights") and video_insight.insights:
            insights = video_insight.insights

            # Handle case where insights is a string (preserved/summarized data)
            if isinstance(insights, str):
                return f'<p style="margin: 0; font-size: 13px; line-height: 1.5;">{insights}</p>'

            # Handle case where insights is a dictionary (normal Vertex AI response)
            if isinstance(insights, dict):
                # Add summary if available
                if insights.get("summary"):
                    summary_text = insights["summary"]
                    if isinstance(summary_text, str) and summary_text.strip():
                        formatted_text.append(
                            f'<div style="margin-bottom: 15px;"><div class="meta-label">Video Summary</div><p style="margin: 5px 0; font-size: 13px; line-height: 1.4;">{summary_text}</p></div>'
                        )

                # Add key events/timeline if available
                timeline_content = []
                if insights.get("timeline"):
                    timeline_items = insights["timeline"]
                    if isinstance(timeline_items, list) and timeline_items:
                        for event in timeline_items:
                            if isinstance(event, dict):
                                timestamp = event.get("timestamp", "Unknown")
                                description = event.get(
                                    "event", event.get("description", "No description")
                                )
                                timeline_content.append(
                                    f"• {timestamp} - {description}"
                                )
                            elif isinstance(event, str) and event.strip():
                                timeline_content.append(f"• {event.strip()}")

                if timeline_content:
                    timeline_html = "<br>".join(timeline_content)
                    formatted_text.append(
                        f'<div style="margin-bottom: 15px;"><div class="meta-label">Key Events Timeline</div><p style="margin: 5px 0; font-size: 13px; line-height: 1.4;">{timeline_html}</p></div>'
                    )

        # Return formatted text or fallback
        if formatted_text:
            return "\n".join(formatted_text)
        if video_insight:
            # Fallback for any other format
            insight_str = str(video_insight)
            if insight_str and insight_str != "None":
                return f'<p style="margin: 0; font-size: 13px; line-height: 1.5;">{insight_str}</p>'

        return '<p style="margin: 0; font-size: 13px; line-height: 1.5;">No video analysis available</p>'


# Create alias for backward compatibility
EmailGenerator = EmailGeneratorV2
