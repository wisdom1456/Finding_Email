from __future__ import annotations

import json
import os
import re
import traceback
from datetime import datetime
from typing import Any

import yaml
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape
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
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from backend.utils.data_models import (
    CaseAnalysisResult,
    EmailStructurePlan,
    GeneratedLetter,
    GenerationContext,
    SectionPlan,
)
from backend.utils.validators import validate_next_steps_formatting, validate_section_output
from backend_logic.config import get_openai_config
from backend_logic.quality_validator import QualityValidator
from backend.quality_validator import polish_and_sanitize


# === ENHANCED DATA MODELS FOR REFACTORED ARCHITECTURE ===


class GenerationOutput(BaseModel):
    """Enhanced output structure for email generation with debugging capabilities."""

    letter: GeneratedLetter
    debug_info: dict[str, Any] | None = None
    validation_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    generation_metadata: dict[str, Any] = Field(default_factory=dict)


class DebugOutput(BaseModel):
    """Detailed debug information for testing and validation."""

    input_validation: dict[str, Any] = Field(default_factory=dict)
    structure_plan: dict[str, Any] | None = None
    generated_sections: dict[str, dict[str, Any]] = Field(default_factory=dict)
    field_mapping: dict[str, Any] = Field(default_factory=dict)
    validation_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    errors: list[dict[str, str]] = Field(default_factory=list)
    generation_time: float | None = None


class SectionValidationError(ValueError):
    """Raised when a section fails validation."""


class EmailGenerationError(Exception):
    """Raised when email generation fails completely."""


# === CONFIGURATION-DRIVEN EMAIL GENERATION ===


class EmailGeneratorV2:
    """
    Configuration-driven EmailGenerator with linear three-stage pipeline architecture.

    Architecture:
    1. PREPARE: Validate input and create structure plan
    2. GENERATE: Generate each section with proper field mapping
    3. FORMAT: Validate output and ensure all template fields are populated
    """

    def __init__(self, client: OpenAI, config_path: str | None = None) -> None:
        """Initialize the EmailGenerator with OpenAI client, configuration, and Jinja2 environment."""
        if not client:
            msg = "An OpenAI client is required for EmailGenerator."
            raise ValueError(msg)
        self.client = client

        # Load configuration
        self.config = self._load_configuration(config_path)
        
        # Initialize template environment with robust path resolution
        template_dir = self._find_template_directory()
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

        self.quality_validator = QualityValidator()

        print(f"EMAIL GENERATOR V2: ✅ Initialized with configuration: {config_path or 'default'}")

    def _load_configuration(self, config_path: str | None = None) -> dict[str, Any]:
        """Load configuration from YAML file."""
        # JSON logging for Hypothesis 2 (Configuration Loading Failure) - Entry
        config_log_entry = {
            "module": "EmailGeneratorV2",
            "method": "_load_configuration",
            "hypothesis_id": "config_loading_failure",
            "stage": "entry",
            "config_path_provided": config_path,
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_entry)}")
        
        if config_path is None:
            # Default to universal_legal_config.yaml for all case types
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = current_dir
            
            # Navigate up until we find the project root
            while project_root != "/" and not (
                os.path.exists(os.path.join(project_root, "app.py"))
                and os.path.exists(os.path.join(project_root, "backend"))
            ):
                project_root = os.path.dirname(project_root)
            
            if project_root == "/":
                project_root = os.getcwd()
            
            config_path = os.path.join(project_root, "backend", "config", "templates", "universal_legal_config.yaml")
        
        # JSON logging for file existence check
        file_exists = os.path.exists(config_path)
        config_log_file_check = {
            "module": "EmailGeneratorV2",
            "method": "_load_configuration",
            "hypothesis_id": "config_loading_failure",
            "stage": "file_check",
            "config_path": config_path,
            "file_exists": file_exists,
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_file_check)}")
        
        if not file_exists:
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # JSON logging for successful config parsing
            config_keys = list(config.keys()) if config else []
            config_log_success = {
                "module": "EmailGeneratorV2",
                "method": "_load_configuration",
                "hypothesis_id": "config_loading_failure",
                "stage": "parsing_success",
                "config_keys": config_keys,
                "config_is_none": config is None,
                "config_type": type(config).__name__,
                "timestamp": datetime.now().isoformat()
            }
            print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_success)}")
            
            print(f"EMAIL GENERATOR V2: Configuration loaded from: {config_path}")
            return config
        except yaml.YAMLError as e:
            # JSON logging for YAML parsing failure
            config_log_yaml_error = {
                "module": "EmailGeneratorV2",
                "method": "_load_configuration",
                "hypothesis_id": "config_loading_failure",
                "stage": "yaml_error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_yaml_error)}")
            
            msg = f"Failed to parse YAML configuration: {e}"
            raise ValueError(msg) from e
        except Exception as e:
            # JSON logging for general loading failure
            config_log_general_error = {
                "module": "EmailGeneratorV2",
                "method": "_load_configuration",
                "hypothesis_id": "config_loading_failure",
                "stage": "general_error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_general_error)}")
            
            msg = f"Failed to load configuration: {e}"
            raise RuntimeError(msg) from e

    def _find_template_directory(self) -> str:
        """Find template directory using configuration or fallback path resolution."""
        # Try to use template_path from configuration
        if hasattr(self, 'config') and self.config and 'template_path' in self.config:
            template_path = self.config['template_path']
            # If template_path is relative, make it relative to project root
            if not os.path.isabs(template_path):
                current_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = current_dir
                
                while project_root != "/" and not (
                    os.path.exists(os.path.join(project_root, "app.py"))
                    and os.path.exists(os.path.join(project_root, "backend"))
                ):
                    project_root = os.path.dirname(project_root)
                
                if project_root == "/":
                    project_root = os.getcwd()
                
                template_dir = os.path.dirname(os.path.join(project_root, template_path))
            else:
                template_dir = os.path.dirname(template_path)
        else:
            # Fallback to default template directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = current_dir

            # Navigate up until we find the project root
            while project_root != "/" and not (
                os.path.exists(os.path.join(project_root, "app.py"))
                and os.path.exists(os.path.join(project_root, "backend"))
            ):
                project_root = os.path.dirname(project_root)

            if project_root == "/":
                project_root = os.getcwd()

            template_dir = os.path.join(project_root, "backend", "assets", "templates")

        if not os.path.exists(template_dir):
            msg = f"Template directory not found: {template_dir}"
            raise FileNotFoundError(msg)

        # Verify required templates exist
        required_templates = ["findings_email.jinja2", "document_appendix.jinja2"]
        available_files = os.listdir(template_dir)
        missing_templates = [t for t in required_templates if t not in available_files]
        if missing_templates:
            msg = f"Required templates missing: {missing_templates}"
            raise FileNotFoundError(msg)

        print(f"EMAIL GENERATOR V2: Template directory: {template_dir}")
        return template_dir

    # === STAGE 1: PREPARE - Input Validation and Structure Planning ===

    def generate_email_with_debug(
        self, analysis: CaseAnalysisResult
    ) -> GenerationOutput:
        """
        Main entry point for email generation with enhanced debugging capabilities.
        Implements the three-stage pipeline: Prepare -> Generate -> Format
        """
        debug_info = DebugOutput()
        start_time = datetime.now().timestamp()

        try:
            # STAGE 1: PREPARE
            print("EMAIL GENERATOR V2: STAGE 1 - PREPARE")
            self._validate_input_analysis(analysis)
            debug_info.input_validation = self._get_validation_summary(analysis)

            structure_plan = self._create_comprehensive_structure_plan(analysis)
            debug_info.structure_plan = (
                structure_plan.dict() if structure_plan else None
            )

            # STAGE 2: GENERATE
            print("EMAIL GENERATOR V2: STAGE 2 - GENERATE")
            generated_sections = self._generate_all_sections_with_tracking(
                structure_plan, analysis, debug_info
            )

            # STAGE 3: FORMAT
            print("EMAIL GENERATOR V2: STAGE 3 - FORMAT")
            letter = self._map_sections_to_template_fields(
                generated_sections, structure_plan, analysis
            )
            
            # STAGE 3.5: POLISH AND SANITIZE
            print("EMAIL GENERATOR V2: STAGE 3.5 - POLISH AND SANITIZE")
            letter = self._apply_polish_and_sanitize(letter)
            
            self._validate_generated_letter(letter)

            debug_info.generation_time = datetime.now().timestamp() - start_time
            debug_info.validation_results = self._validate_all_fields(letter)

            return GenerationOutput(
                letter=letter,
                debug_info=debug_info.dict(),
                validation_results=debug_info.validation_results,
                generation_metadata={
                    "generation_time": debug_info.generation_time,
                    "sections_generated": len(generated_sections),
                    "plan_sections": len(structure_plan.sections)
                    if structure_plan
                    else 0,
                },
            )

        except (ValueError, TypeError, AttributeError, KeyError, ImportError) as e:
            error_info = {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "stage": "unknown",
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
                },
            )

    def _validate_input_analysis(self, analysis: CaseAnalysisResult) -> None:
        """Validate that analysis has required components for email generation."""
        if not analysis:
            msg = "Analysis object is required"
            raise EmailGenerationError(msg)

        # Ensure we have basic components
        if not analysis.intake_analysis:
            print("EMAIL GENERATOR V2: ⚠️  Missing intake_analysis, creating fallback")
            self._ensure_analysis_completeness(analysis)

        if not analysis.analyzed_documents:
            print("EMAIL GENERATOR V2: ⚠️  No analyzed documents found")

        print("EMAIL GENERATOR V2: ✅ Input validation complete")

    def _get_validation_summary(self, analysis: CaseAnalysisResult) -> dict[str, Any]:
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
                key_points=self._extract_key_facts(analysis),
                emphasis_items=self._identify_emphasis_items(analysis),
                content_requirements=[
                    "chronological events",
                    "key parties",
                    "important dates and amounts",
                ],
            )
        )
        section_number += 1

        # 2. LEGAL ANALYSIS
        legal_citation = self._determine_legal_citation(analysis)
        sections.append(
            SectionPlan(
                number=section_number,
                header="LEGAL ANALYSIS",
                legal_citation=legal_citation,
                key_points=self._extract_legal_issues(analysis),
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
                    key_points=self._extract_media_evidence_points(analysis),
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
                key_points=self._extract_case_assessment_points(analysis),
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
                key_points=self._extract_recommendations(analysis),
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

        print(
            f"EMAIL GENERATOR V2: Created structure plan with {len(sections)} sections"
        )
        return plan

    # === STAGE 2: GENERATE - Section Generation with Proper Mapping ===

    def _generate_all_sections_with_tracking(
        self,
        plan: EmailStructurePlan,
        analysis: CaseAnalysisResult,
        debug_info: DebugOutput,
    ) -> dict[str, str]:
        """Generate all sections with detailed tracking for debugging."""
        generated_sections = {}
        context = GenerationContext()

        # Generate header/greeting
        print("EMAIL GENERATOR V2: Generating greeting section...")
        greeting_content = self._generate_greeting_section(plan, analysis, context)
        generated_sections["greeting"] = greeting_content
        debug_info.generated_sections["greeting"] = {
            "content_length": len(greeting_content),
            "is_empty": not greeting_content.strip(),
            "first_100_chars": greeting_content[:100] if greeting_content else None,
        }

        # Generate each planned section
        for section_plan in plan.sections:
            print(f"EMAIL GENERATOR V2: Generating section: {section_plan.header}")
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
                print(f"EMAIL GENERATOR V2: ❌ {error_msg}")

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
        print("EMAIL GENERATOR V2: Generating closing section...")
        closing_content = self._generate_closing_section(plan, analysis, context)
        generated_sections["closing"] = closing_content
        debug_info.generated_sections["closing"] = {
            "content_length": len(closing_content),
            "is_empty": not closing_content.strip(),
            "first_100_chars": closing_content[:100] if closing_content else None,
        }

        print(f"EMAIL GENERATOR V2: ✅ Generated {len(generated_sections)} sections")
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
        """Generate a section with explicit validation."""
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

        # Return content only - template system handles headers and structure
        return self._clean_ai_response(content)

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
            sections_config = self.config.get('sections', {})
            if not sections_config:
                print(f"EMAIL GENERATOR V2: ⚠️ No sections configuration found in YAML")
                return
                
            section_config = sections_config.get(section_key, {})
            if not section_config:
                print(f"EMAIL GENERATOR V2: ⚠️ No configuration found for section: {section_key}")
                return
                
            # Extract output format (defaults to "html" if not specified)
            output_format = section_config.get('output_format', 'html')
            
            # Validate the section output
            validate_section_output(content, output_format)
            
            print(f"EMAIL GENERATOR V2: ✅ Section '{section_key}' format validation passed ({output_format})")
            
        except Exception as e:
            # Log validation warning but don't stop generation
            print(f"EMAIL GENERATOR V2: ⚠️ Section '{section_key}' format validation warning: {e}")
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
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(mapping_log)}")

        print("EMAIL GENERATOR V2: Mapping sections to template fields...")

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

        # JSON logging for exit state
        exit_log = {
            "module": "EmailGeneratorV2",
            "method": "_map_sections_to_template_fields",
            "hypothesis_id": "missing_content_parsing",
            "stage": "exit",
            "letter_fields": {k: len(getattr(letter, k, "")) for k in letter.__fields__},
            "processing_applied": True,
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(exit_log)}")

        print("EMAIL GENERATOR V2: ✅ Sections mapped to template fields")
        print(f"  - executive_summary: {len(letter.executive_summary)} chars")
        print(f"  - background_summary: {len(letter.background_summary)} chars")
        print(f"  - analysis_and_position: {len(letter.analysis_and_position)} chars")
        print(f"  - next_steps: {len(letter.next_steps)} chars")
        print(f"  - closing_paragraph: {len(letter.closing_paragraph)} chars")

        return letter

    def _apply_polish_and_sanitize(self, letter: GeneratedLetter) -> GeneratedLetter:
        """
        Apply polish and sanitize processing to all letter fields.
        
        This method processes each field of the generated letter through the
        polish_and_sanitize function to ensure content quality and compliance.
        """
        try:
            print("EMAIL GENERATOR V2: Applying polish and sanitize to letter fields...")
            
            # Process each field that contains substantial content
            fields_to_process = [
                'executive_summary',
                'background_summary',
                'analysis_and_position',
                'media_summary',
                'strengths',
                'challenges',
                'recommendations',
                'next_steps',
                'closing_paragraph'
            ]
            
            for field_name in fields_to_process:
                field_content = getattr(letter, field_name, "")
                if field_content and field_content.strip():
                    try:
                        # Get appropriate word limit for this field from configuration
                        word_counts = self.config.get('word_counts', {})
                        field_word_limit = word_counts.get(field_name, 200)  # Default to 200 if not specified
                        
                        # Apply polish and sanitize with proper word limit per field
                        processed_content = polish_and_sanitize(
                            email_draft=field_content,
                            apply_polishing=False,  # Skip AI polishing for individual fields
                            client=self.client,
                            word_limit=field_word_limit
                        )
                        setattr(letter, field_name, processed_content)
                        print(f"EMAIL GENERATOR V2: ✅ Processed {field_name}")
                        
                    except Exception as e:
                        print(f"EMAIL GENERATOR V2: ⚠️ Failed to process {field_name}: {e}")
                        # Continue with original content if processing fails
            
            # Apply overall email polish and sanitize to the complete email
            try:
                # Combine all content for full email processing
                full_email_content = self._combine_letter_content(letter)
                
                # Apply full email polish and sanitize with STRICT 850-word limit
                polished_email = polish_and_sanitize(
                    email_draft=full_email_content,
                    apply_polishing=True,  # Enable AI polishing for full email
                    client=self.client,
                    word_limit=850  # CRITICAL: Full email MUST be under 850 words
                )
                
                # If full processing succeeds, update the primary content field
                letter.executive_summary = polished_email[:1000] + "..." if len(polished_email) > 1000 else polished_email
                print("EMAIL GENERATOR V2: ✅ Applied full email polish and sanitize")
                
            except Exception as e:
                print(f"EMAIL GENERATOR V2: ⚠️ Full email processing failed: {e}")
                # Continue with field-level processing results
            
            return letter
            
        except Exception as e:
            print(f"EMAIL GENERATOR V2: ❌ Polish and sanitize processing failed: {e}")
            # Return original letter if all processing fails
            return letter

    def _combine_letter_content(self, letter: GeneratedLetter) -> str:
        """Combine all letter content into a single email draft for processing."""
        content_parts = []
        
        # Add each field with proper spacing
        fields_with_content = [
            ('Executive Summary', letter.executive_summary),
            ('Background Summary', letter.background_summary),
            ('Legal Analysis', letter.analysis_and_position),
            ('Evidence Review', letter.media_summary),
            ('Case Strengths', letter.strengths),
            ('Challenges', letter.challenges),
            ('Recommendations', letter.recommendations),
            ('Next Steps', letter.next_steps),
            ('Closing', letter.closing_paragraph)
        ]
        
        for section_name, content in fields_with_content:
            if content and content.strip():
                content_parts.append(f"<h3>{section_name}</h3>")
                content_parts.append(content)
                content_parts.append("")  # Add spacing
        
        return "\n".join(content_parts)

    def _enforce_850_word_limit(self, html_content: str, generated_letter: GeneratedLetter, analysis: CaseAnalysisResult) -> str:
        """
        Enforce the 850-word limit by iteratively reducing the longest section until under the limit.
        
        Args:
            html_content: The fully assembled HTML content
            generated_letter: The generated letter object with individual sections
            analysis: The case analysis result for regeneration context
            
        Returns:
            HTML content that is at or below 850 words
        """
        max_iterations = 5
        iteration = 0
        
        print(f"EMAIL GENERATOR V2: Starting 850-word limit enforcement")
        
        while iteration < max_iterations:
            # Strip HTML tags and count words
            plain_text = self._strip_html_tags(html_content)
            word_count = len(plain_text.split())
            
            print(f"EMAIL GENERATOR V2: Iteration {iteration + 1}, current word count: {word_count}")
            
            if word_count <= 850:
                print(f"EMAIL GENERATOR V2: ✅ Word count within limit: {word_count} words")
                return html_content
            
            # Find the longest section
            longest_section_key = self._identify_longest_section(generated_letter)
            if not longest_section_key:
                print("EMAIL GENERATOR V2: ⚠️ Could not identify longest section, breaking loop")
                break
                
            print(f"EMAIL GENERATOR V2: Longest section identified: {longest_section_key}")
            
            # Calculate reduced word target (reduce by 15% or at least 25 words)
            current_section_content = getattr(generated_letter, longest_section_key, "")
            current_section_words = len(self._strip_html_tags(current_section_content).split())
            word_reduction = max(25, int(current_section_words * 0.15))
            new_word_target = max(50, current_section_words - word_reduction)  # Minimum 50 words
            
            print(f"EMAIL GENERATOR V2: Reducing {longest_section_key} from {current_section_words} to {new_word_target} words")
            
            # Regenerate the longest section with reduced word count
            regenerated_content = self._regenerate_section_with_reduced_words(
                section_key=longest_section_key,
                word_target=new_word_target,
                analysis=analysis
            )
            
            if regenerated_content:
                # Update the generated letter object
                setattr(generated_letter, longest_section_key, regenerated_content)
                
                # Re-render the full HTML
                html_content = self._rerender_full_html(generated_letter, analysis)
                print(f"EMAIL GENERATOR V2: ✅ Regenerated {longest_section_key} and re-rendered HTML")
            else:
                print(f"EMAIL GENERATOR V2: ⚠️ Failed to regenerate {longest_section_key}")
                break
                
            iteration += 1
        
        # Final word count check
        final_plain_text = self._strip_html_tags(html_content)
        final_word_count = len(final_plain_text.split())
        
        if final_word_count > 850:
            print(f"EMAIL GENERATOR V2: ⚠️ Still over limit after {max_iterations} iterations: {final_word_count} words")
        else:
            print(f"EMAIL GENERATOR V2: ✅ Final word count: {final_word_count} words")
            
        return html_content

    def _strip_html_tags(self, html_content: str) -> str:
        """Strip HTML tags to get plain text for word counting."""
        import re
        if not html_content:
            return ""
        
        # Remove HTML tags
        clean = re.sub('<.*?>', '', html_content)
        # Remove extra whitespace
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()

    def _identify_longest_section(self, letter: GeneratedLetter) -> str | None:
        """Identify the section with the most words."""
        section_word_counts = {}
        
        # Define sections that can be shortened (exclude closing/greeting)
        shortenable_sections = [
            'background_summary',
            'analysis_and_position',
            'media_summary',
            'strengths',
            'challenges',
            'recommendations',
            'next_steps'
        ]
        
        for section_key in shortenable_sections:
            content = getattr(letter, section_key, "")
            if content and content.strip():
                word_count = len(self._strip_html_tags(content).split())
                section_word_counts[section_key] = word_count
        
        if not section_word_counts:
            return None
            
        # Return the section with the most words
        longest_section = max(section_word_counts.items(), key=lambda x: x[1])
        return longest_section[0]

    def _regenerate_section_with_reduced_words(self, section_key: str, word_target: int, analysis: CaseAnalysisResult) -> str | None:
        """Regenerate a specific section with a reduced word count target."""
        try:
            # Map section keys to generation methods
            section_generators = {
                'background_summary': self._generate_factual_summary_content,
                'analysis_and_position': self._generate_legal_analysis_content,
                'media_summary': self._generate_evidence_review_content,
                'strengths': self._generate_case_assessment_content,
                'challenges': self._generate_case_assessment_content,
                'recommendations': self._generate_case_assessment_content,
                'next_steps': self._generate_next_steps_content
            }
            
            generator_method = section_generators.get(section_key)
            if not generator_method:
                print(f"EMAIL GENERATOR V2: ⚠️ No generator method found for section: {section_key}")
                return None
            
            # Create a temporary section plan with reduced word target
            section_plan = SectionPlan(
                number=1,
                header=section_key.replace('_', ' ').title(),
                key_points=[],
                emphasis_items={},
                content_requirements=[]
            )
            
            # Temporarily update word counts configuration for this section
            original_word_counts = self.config.get('word_counts', {}).copy()
            self.config['word_counts'][section_key] = word_target
            
            # Generate the section with reduced word count
            context = GenerationContext()
            regenerated_content = generator_method(section_plan, analysis, context)
            
            # Restore original word counts
            self.config['word_counts'] = original_word_counts
            
            return regenerated_content
            
        except Exception as e:
            print(f"EMAIL GENERATOR V2: ❌ Error regenerating section {section_key}: {e}")
            return None

    def _rerender_full_html(self, letter: GeneratedLetter, analysis: CaseAnalysisResult) -> str:
        """Re-render the full HTML content after updating a section."""
        try:
            # Get the template
            main_template = self.jinja_env.get_template("findings_email.jinja2")
            
            # Prepare template context
            template_context = {
                "analysis": analysis,
                "generated_letter": letter,
                "current_date": datetime.now().strftime("%B %d, %Y"),
                "case_timeline": getattr(analysis, "case_timeline", []),
                "format_video_analysis": self.format_video_analysis_for_appendix,
                "case_name": analysis.intake_analysis.case_type if analysis.intake_analysis and analysis.intake_analysis.case_type else "Your Case",
                "client_name": analysis.intake_analysis.client_name if analysis.intake_analysis and analysis.intake_analysis.client_name else "Client",
            }
            
            # Render template
            html_content = main_template.render(
                results=template_context,
                current_date=template_context["current_date"]
            )
            
            return html_content
            
        except Exception as e:
            print(f"EMAIL GENERATOR V2: ❌ Error re-rendering HTML: {e}")
            # Return a simple concatenation as fallback
            return self._combine_letter_content(letter)

    def _apply_final_sanitization(
        self, html_content: str, apply_polishing: bool = False, word_limit: int = 850
    ) -> str:
        """
        Apply final sanitization pass after full HTML assembly.
        
        This method implements the core requirements:
        1. Filter citations using configured regex pattern
        2. Apply polish_and_sanitize function from quality_validator
        3. Optional AI polish step for tone realignment
        
        Args:
            html_content: The fully assembled HTML content
            apply_polishing: Whether to apply AI polishing for tone realignment
            word_limit: Maximum word count for the content
            
        Returns:
            Sanitized and polished HTML content
        """
        if not html_content or not html_content.strip():
            print("EMAIL GENERATOR V2: ⚠️ Empty HTML content provided for sanitization")
            return html_content
        
        try:
            print(f"EMAIL GENERATOR V2: Starting final sanitization (polishing: {apply_polishing}, limit: {word_limit})")
            
            # Step 1: Apply citation filter using regex from configuration
            citation_filtered_html = self._apply_citation_filter_to_html(html_content)
            
            # Step 2: Apply polish_and_sanitize from quality_validator module
            sanitized_html = polish_and_sanitize(
                email_draft=citation_filtered_html,
                apply_polishing=apply_polishing,
                client=self.client,
                word_limit=word_limit
            )
            
            print("EMAIL GENERATOR V2: ✅ Final sanitization completed successfully")
            return sanitized_html
            
        except Exception as e:
            print(f"EMAIL GENERATOR V2: ❌ Final sanitization failed: {e}")
            # Return original content if sanitization fails to prevent data loss
            return html_content

    def _apply_citation_filter_to_html(self, html_content: str) -> str:
        """
        Apply citation filter regex to strip "§" or "Fla. Stat." references from HTML.
        
        Uses the citation_filter_regex from configuration to remove legal citations
        while preserving HTML structure.
        
        Args:
            html_content: HTML content to filter
            
        Returns:
            HTML content with citations removed
        """
        if not html_content:
            return html_content
        
        try:
            # Get citation filter regex from configuration
            citation_filter_regex = self.config.get('citation_filter_regex', '')
            
            if not citation_filter_regex:
                print("EMAIL GENERATOR V2: ⚠️ No citation_filter_regex found in configuration")
                return html_content
            
            print(f"EMAIL GENERATOR V2: Applying citation filter: {citation_filter_regex}")
            
            # Apply citation filter using re.sub with case-insensitive matching
            filtered_html = re.sub(
                citation_filter_regex,
                "",
                html_content,
                flags=re.IGNORECASE
            )
            
            # Clean up any double spaces left by removals
            filtered_html = re.sub(r'\s+', ' ', filtered_html)
            
            # Count removals for logging
            original_length = len(html_content)
            filtered_length = len(filtered_html)
            
            if filtered_length < original_length:
                removed_chars = original_length - filtered_length
                print(f"EMAIL GENERATOR V2: Citation filter removed {removed_chars} characters")
            else:
                print("EMAIL GENERATOR V2: Citation filter found no matches to remove")
            
            return filtered_html.strip()
            
        except re.error as e:
            print(f"EMAIL GENERATOR V2: ❌ Invalid citation filter regex: {e}")
            return html_content
        except Exception as e:
            print(f"EMAIL GENERATOR V2: ❌ Citation filtering failed: {e}")
            return html_content

    def _apply_post_processor_guard(self, html_content: str) -> str:
        """
        Apply final validation and cleanup step to the email generation process.
        
        This implements the post-processor guard with:
        1. Strip stray citations using regex
        2. Get plain text for word count using BeautifulSoup
        3. Assert total word count <= 850 words
        
        Args:
            html_content: The final HTML content to validate
            
        Returns:
            Sanitized and validated HTML content
            
        Raises:
            AssertionError: If word count exceeds 850 words
        """
        if not html_content:
            return html_content
            
        try:
            print("EMAIL GENERATOR V2: STAGE 6 - POST-PROCESSOR GUARD")
            
            # 1. Strip stray citations
            html_content = re.sub(r"(Fla\.?\s*Stat\.?|§|Chapter\s*\d+)", "", html_content)
            print("EMAIL GENERATOR V2: ✅ Stripped stray citations")
            
            # 2. Get plain text for word count
            plain_text = BeautifulSoup(html_content, "html.parser").get_text()
            
            # 3. Assert total word count
            word_count = len(plain_text.split())
            print(f"EMAIL GENERATOR V2: Final word count: {word_count} words")
            
            assert word_count <= 850, f"Letter too long ({word_count} words)—regenerate largest section."
            
            print("EMAIL GENERATOR V2: ✅ Post-processor guard validation passed")
            return html_content
            
        except AssertionError:
            # Re-raise assertion errors for word count violations
            raise
        except Exception as e:
            print(f"EMAIL GENERATOR V2: ❌ Post-processor guard failed: {e}")
            # Return original content if processing fails to prevent data loss
            return html_content

    def _split_case_assessment(self, case_assessment: str) -> tuple[str, str]:
        """Split combined case assessment into strengths and challenges."""
        if not case_assessment:
            return "", ""

        # Look for headers that indicate strengths vs challenges
        strengths_keywords = [
            "strength",
            "advantage",
            "positive",
            "favorable",
            "support",
        ]
        challenges_keywords = ["challenge", "weakness", "risk", "concern", "obstacle"]

        # Simple split based on content patterns
        lines = case_assessment.split("\n")
        strengths_lines = []
        challenges_lines = []
        current_section = "unknown"

        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in strengths_keywords):
                current_section = "strengths"
            elif any(keyword in line_lower for keyword in challenges_keywords):
                current_section = "challenges"

            if current_section == "strengths":
                strengths_lines.append(line)
            elif current_section == "challenges":
                challenges_lines.append(line)

        # If we couldn't split intelligently, put everything in strengths
        if not strengths_lines and not challenges_lines:
            return case_assessment, ""

        return "\n".join(strengths_lines), "\n".join(challenges_lines)

    def _validate_generated_letter(self, letter: GeneratedLetter) -> None:
        """Validate that generated letter has all required fields populated."""
        required_fields = [
            "executive_summary",
            "background_summary",
            "analysis_and_position",
            "next_steps",
            "closing_paragraph",
        ]

        empty_fields = []
        for field in required_fields:
            value = getattr(letter, field, "")
            if not value or not value.strip():
                empty_fields.append(field)

        if empty_fields:
            msg = f"Required fields are empty: {', '.join(empty_fields)}"
            raise EmailGenerationError(msg)

        print("EMAIL GENERATOR V2: ✅ Letter validation passed")

    def _validate_all_fields(
        self, letter: GeneratedLetter
    ) -> dict[str, dict[str, Any]]:
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
        print(
            "EMAIL GENERATOR: 🔍 === DIAGNOSTIC LOGGING - Factual Summary Context ==="
        )
        print(
            f"EMAIL GENERATOR: 🔍 Analyzed documents count: {len(analysis.analyzed_documents) if analysis.analyzed_documents else 0}"
        )
        if analysis.analyzed_documents:
            for i, doc in enumerate(
                analysis.analyzed_documents[:3]
            ):  # Log first 3 docs
                print(f"EMAIL GENERATOR: 🔍   Document {i + 1}: {doc.file_name}")
                print(
                    f"EMAIL GENERATOR: 🔍   Summary: {doc.summary[:100] if doc.summary else 'No summary'}..."
                )
                print(
                    f"EMAIL GENERATOR: 🔍   Key info: {doc.key_information[:100] if doc.key_information else 'No key info'}..."
                )

        # Get prompt from configuration (defensive against None values)
        sections_section = self.config.get('sections') or {}
        section_config = sections_section.get('factual_summary', {})
        if isinstance(section_config, dict):
            section_prompt = section_config.get('content', '')
        else:
            section_prompt = str(section_config) if section_config else ''
        
        if not section_prompt:
            # Fallback prompt if configuration is missing
            section_prompt = "Write a factual summary section for a professional legal findings letter."

        base_prompt = f"""
        {section_prompt}

        Key Facts to Emphasize:
        {section_plan.key_points}

        CASE CONTEXT AND DOCUMENTS (Extract specific details):
        {analysis.model_dump_json(indent=2)}
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self._build_enhanced_prompt(base_prompt, 'factual_summary')

        print(
            f"EMAIL GENERATOR: 🔍 Factual summary enhanced prompt length: {len(enhanced_prompt)} characters"
        )
        
        # Get persona from configuration (defensive against None values)
        personas_section = self.config.get('personas') or {}
        persona = personas_section.get('CONTINUING_LEGAL_ADVISOR', '')
        result = self._make_openai_request(enhanced_prompt, persona)
        print(
            f"EMAIL GENERATOR: 🔍 Factual summary result length: {len(result) if result else 0} characters"
        )
        print("EMAIL GENERATOR: 🔍 === END DIAGNOSTIC LOGGING ===")

        return result or "<p>Factual summary of the key events and circumstances.</p>"

    def _generate_legal_analysis_content(
        self,
        section_plan: SectionPlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate legal analysis content with Florida law focus."""
        
        # Get prompt from configuration (defensive against None values)
        sections_section = self.config.get('sections') or {}
        section_config = sections_section.get('legal_analysis', {})
        if isinstance(section_config, dict):
            section_prompt = section_config.get('content', '')
        else:
            section_prompt = str(section_config) if section_config else ''
        
        if not section_prompt:
            section_prompt = "Write a legal analysis section as an experienced Florida litigation attorney."

        base_prompt = f"""
        {section_prompt}

        Legal Issues to Analyze:
        {section_plan.key_points}

        Primary Legal Citation: {section_plan.legal_citation or "Florida Statutes (applicable provisions)"}

        CASE CONTEXT AND EVIDENCE:
        {analysis.model_dump_json(indent=2)}
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self._build_enhanced_prompt(base_prompt, 'analysis')

        # Get persona from configuration (defensive against None values)
        personas_section = self.config.get('personas') or {}
        persona = personas_section.get('CONTINUING_LEGAL_ADVISOR', '')
        result = self._make_openai_request(enhanced_prompt, persona)
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
        enhanced_prompt = self._build_enhanced_prompt(base_prompt, 'evidence_review')

        # Get persona from configuration (defensive against None values)
        personas_section = self.config.get('personas') or {}
        persona = personas_section.get('CONTINUING_LEGAL_ADVISOR', '')
        result = self._make_openai_request(enhanced_prompt, persona)
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
        """Generate combined case assessment covering strengths and challenges."""
        base_prompt = f"""
        Write a case assessment section as an experienced Florida litigation attorney providing objective evaluation of case strengths and challenges.

        CASE ASSESSMENT STANDARDS:
        - Provide balanced, objective analysis in substantive paragraphs that demonstrate legal expertise
        - Address case strengths first, followed by potential challenges and strategic considerations
        - Base assessment on Florida law standards, evidence requirements, and litigation realities
        - Use professional legal judgment to evaluate claim viability and litigation prospects
        - Discuss both the legal merits and practical considerations for pursuing the matter
        - Use bullet points only for listing specific strengths or challenges (not for general explanations)
        - Demonstrate the analytical depth expected from a seasoned litigator

        ASSESSMENT STRUCTURE:
        1. Opening paragraph providing overall case evaluation
        2. Detailed analysis of case strengths with supporting legal rationale
        3. Honest assessment of potential challenges and how they might be addressed
        4. Strategic considerations for case development and resolution
        5. Professional opinion on the path forward based on Florida law and litigation experience

        PROFESSIONAL EVALUATION CRITERIA:
        - Evidence quality and admissibility under Florida evidence rules
        - Statutory compliance and procedural requirements
        - Damages calculation and recovery prospects
        - Opposing party's likely defenses and counterclaims
        - Cost-benefit analysis of litigation versus alternative resolutions
        - Timeline considerations and statute of limitations issues

        Assessment Points to Address:
        {section_plan.key_points}

        CASE CONTEXT AND EVIDENCE:
        {analysis.model_dump_json(indent=2)}

        Write a comprehensive case assessment that reflects the judgment and experience of a senior Florida litigation attorney.
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self._build_enhanced_prompt(base_prompt, 'strengths_and_weaknesses')

        # Get persona from configuration
        persona = self.config.get('personas', {}).get('CONTINUING_LEGAL_ADVISOR', '')
        result = self._make_openai_request(enhanced_prompt, persona)
        return (
            result
            or "<p>Case assessment reveals both strengths and considerations under Florida law.</p>"
        )

    def _generate_next_steps_content(
        self,
        section_plan: SectionPlan,
        analysis: CaseAnalysisResult,
        context: GenerationContext,
    ) -> str:
        """Generate next steps content with prioritized actions."""
        base_prompt = f"""
        Write a recommended next steps section as an experienced Florida litigation attorney providing strategic guidance to the client.

        STRATEGIC GUIDANCE STANDARDS:
        - Keep the opening strategy paragraph that explains the strategic approach and rationale
        - Convert actionable items into a clean <ul><li> block structure for maximum scannability
        - Place any explanatory text in paragraphs above or below the bulleted list
        - Bold critical deadlines and requirements using <strong> tags for emphasis
        - Demonstrate knowledge of Florida procedural rules and litigation strategy
        - Present recommendations with the authority and wisdom of a seasoned litigator

        REQUIRED OUTPUT STRUCTURE:
        1. Opening paragraph: Substantive explanation of the strategic approach and immediate priorities
        2. Actionable items: Clean <ul><li> list of specific action items, deadlines, and procedural steps
        3. Closing paragraph (if needed): Additional explanatory text about strategic considerations or client guidance

        FORMATTING REQUIREMENTS:
        - Use <ul><li> tags for all actionable recommendations
        - Include precise timelines, deadlines, and procedural requirements within the list items
        - Reference specific Florida procedural deadlines and requirements
        - Explain the purpose and importance of each recommended action within the list items
        - Provide realistic timelines based on legal and practical considerations
        - Address both immediate actions and longer-term strategic planning
        - Include guidance on evidence preservation and case development
        - Consider alternative dispute resolution options where appropriate

        Recommended Actions to Include:
        {section_plan.key_points}

        CASE CONTEXT AND ANALYSIS:
        {analysis.model_dump_json(indent=2)}

        Write strategic next steps recommendations with the opening strategy paragraph, followed by a scannable <ul><li> list of actionable items, and any closing explanatory paragraphs as needed.
        """

        # Build enhanced prompt with firm voice, golden sample, and word limits
        enhanced_prompt = self._build_enhanced_prompt(base_prompt, 'next_steps')

        # Get persona from configuration
        persona = self.config.get('personas', {}).get('CONTINUING_LEGAL_ADVISOR', '')
        result = self._make_openai_request(enhanced_prompt, persona)
        final_result = (
            result
            or "<p>Based on our analysis, the following steps are recommended to advance your case.</p>"
        )
        
        # Validate next steps formatting for deadline emphasis
        try:
            validate_next_steps_formatting(final_result)
        except ValueError as e:
            print(f"EMAIL GENERATOR V2: ⚠️ Next steps validation warning: {e}")
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
        enhanced_prompt = self._build_enhanced_prompt(base_prompt, section_plan.header.lower().replace(" ", "_"))

        # Get persona from configuration
        persona = self.config.get('personas', {}).get('CONTINUING_LEGAL_ADVISOR', '')
        result = self._make_openai_request(enhanced_prompt, persona)
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
        self, number: int, header: str, citation: str | None = None
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
        content = re.sub(r'([.,])([A-Za-z])', r'\1 \2', content)
        
        # Remove duplicate intro phrases (case-insensitive)
        # This removes repeated occurrences of "the path forward" within the same text
        content = re.sub(r'(\bthe path forward\b).*?\1', r'\1', content, flags=re.IGNORECASE)
        
        # Eliminate leading commas from lines
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            # Remove leading commas and whitespace from each line
            cleaned_line = re.sub(r'^\s*,\s*', '', line)
            cleaned_lines.append(cleaned_line)
        content = '\n'.join(cleaned_lines)
        
        return content

    def _clean_ai_response(
        self, content: str, is_counter_intuitive: bool = False
    ) -> str:
        """Clean AI response with comprehensive formatting transformations."""
        if not content:
            return ""

        # Apply high-stakes advice protocol if needed (defensive against None values)
        if is_counter_intuitive:
            formatting_section = self.config.get('formatting') or {}
            protocol = formatting_section.get('high_stakes_advice_protocol', '')
            if protocol:
                content = f"{protocol}\n\n{content}"

        # Step 1: Remove markdown artifacts
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", content, flags=re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE)

        # Step 2: Apply enhanced sanitization rules
        cleaned = self._apply_enhanced_sanitization(cleaned)

        # Step 3: Apply comprehensive content processing
        cleaned = self._format_legal_analysis(cleaned)
        cleaned = self._format_recommendations(cleaned)
        cleaned = self._format_subsections(cleaned)
        cleaned = self._format_statutory_citations(cleaned)
        cleaned = self._format_bullet_points(cleaned)
        cleaned = self._clean_section_numbering(cleaned)
        cleaned = self._ensure_proper_whitespace(cleaned)
        cleaned = self._trim_wordiness(cleaned)

        # Step 3.5: Apply grammar sanitization
        cleaned = self._sanitize_output_grammar(cleaned)

        # Step 4: Convert markdown formatting
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", cleaned)
        cleaned = re.sub(r"\*(.*?)\*", r"<em>\1</em>", cleaned)

        # Step 5: Fix HTML formatting issues
        cleaned = re.sub(r"<p>\s*<p>", "<p>", cleaned)
        cleaned = re.sub(r"</p>\s*</p>", "</p>", cleaned)
        cleaned = re.sub(r"<p>\s*</p>", "", cleaned)

        # JSON logging for content processing
        processing_log = {
            "module": "EmailGeneratorV2",
            "method": "_clean_ai_response",
            "hypothesis_id": "string_concatenation_issues",
            "input_length": len(content) if content else 0,
            "output_length": len(cleaned) if cleaned else 0,
            "processing_steps_applied": [
                "apply_enhanced_sanitization", "format_legal_analysis", "format_recommendations", "format_subsections",
                "format_statutory_citations", "format_bullet_points", "clean_section_numbering",
                "ensure_proper_whitespace", "trim_wordiness"
            ],
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(processing_log)}")

        return cleaned.strip()

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
    def _build_enhanced_prompt(self, base_prompt: str, section_key: str) -> str:
        """
        Build enhanced prompt with firm voice, golden sample, word limits, and content restrictions.
        
        Args:
            base_prompt: The base prompt content
            section_key: The section key to look up word count limits
            
        Returns:
            Enhanced prompt string with all requirements
        """
        # Get firm voice and golden sample from configuration
        firm_voice = self.config.get('firm_voice', '')
        golden_sample = self.config.get('golden_sample', '')
        
        # Get word count for this section
        word_counts = self.config.get('word_counts', {})
        
        # Map user's section names to internal section keys
        section_mapping = {
            'analysis': 'legal_analysis',
            'strengths_and_weaknesses': 'case_assessment'
        }
        
        # Use mapped section key if available, otherwise use the provided section_key
        mapped_section_key = section_mapping.get(section_key, section_key)
        word_limit = word_counts.get(mapped_section_key, word_counts.get(section_key, None))
        
        # Get content restrictions
        content_rules = self.config.get('content_rules', [])
        
        # Build enhanced prompt following the exact structure requested
        enhanced_prompt = ""
        
        # Prepend firm voice directly (no label)
        if firm_voice:
            enhanced_prompt = f"{firm_voice}\n\n"
        
        # Add golden sample with exact format requested
        if golden_sample:
            enhanced_prompt += f"Below is our style exemplar:\n{golden_sample}\n\n"
        
        # Add section-specific instruction with word count
        if word_limit:
            enhanced_prompt += f"Draft the {section_key} for a client email (≤ {word_limit} words). Do not reference statutes, sections, or chapters.\n\n"
        
        # Add the base prompt
        enhanced_prompt += base_prompt
        
        # Add content restrictions if any
        if content_rules:
            restrictions = "\n".join([f"- {rule}" for rule in content_rules])
            enhanced_prompt = f"{enhanced_prompt}\n\nCONTENT RESTRICTIONS:\n{restrictions}"
        
        return enhanced_prompt

    def _make_openai_request(
        self, prompt: str, persona: str, model: str | None = None
    ) -> str | None:
        """Make OpenAI API request with comprehensive error handling following OpenAI best practices."""

        # JSON logging for Hypothesis 1 (OpenAI API Response Issues) - Entry
        api_log_entry = {
            "module": "EmailGeneratorV2",
            "method": "_make_openai_request",
            "hypothesis_id": "openai_api_failure",
            "stage": "entry",
            "prompt_length": len(prompt),
            "persona_length": len(persona),
            "model_provided": model,
            "config_available": self.config is not None,
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(api_log_entry)}")

        # Get configuration from centralized config
        config = get_openai_config()
        model = model or config["model"]

        print(f"EMAIL GENERATOR V2: 🔍 Making OpenAI request with model: {model}")
        print(f"EMAIL GENERATOR V2: 🔍 Prompt length: {len(prompt)} characters")

        # JSON logging for pre-request validation (defensive against None values)
        formatting_section = self.config.get('formatting') or {} if self.config else {}
        formatting_enforcement = formatting_section.get('strict_format_enforcement', '')
        api_log_pre_request = {
            "module": "EmailGeneratorV2",
            "method": "_make_openai_request",
            "hypothesis_id": "openai_api_failure",
            "stage": "pre_request",
            "model": model,
            "formatting_enforcement_available": bool(formatting_enforcement),
            "config_get_success": self.config is not None,
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(api_log_pre_request)}")

        try:
            # Configure request with timeout and retry settings per OpenAI documentation
            response = self.client.with_options(
                timeout=config["timeout"], max_retries=config["max_retries"]
            ).chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": f"{persona}\n\n{formatting_enforcement}",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=config["temperature"],
                max_tokens=config["max_tokens"],
            )

            # Log request ID for debugging (per OpenAI documentation)
            request_id = getattr(response, "_request_id", "unknown")
            print(f"EMAIL GENERATOR V2: 🔍 Request ID: {request_id}")

            content = response.choices[0].message.content
            print(
                f"EMAIL GENERATOR V2: ✅ OpenAI request successful, response length: {len(content) if content else 0}"
            )

            # JSON logging for post-response validation
            api_log_post_response = {
                "module": "EmailGeneratorV2",
                "method": "_make_openai_request",
                "hypothesis_id": "openai_api_failure",
                "stage": "post_response",
                "request_id": request_id,
                "content_is_none": content is None,
                "content_length": len(content) if content else 0,
                "content_is_empty_after_strip": not content.strip() if content else True,
                "timestamp": datetime.now().isoformat()
            }
            print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(api_log_post_response)}")

            if not content or not content.strip():
                print(
                    f"EMAIL GENERATOR V2: ❌ OpenAI returned empty content (Request ID: {request_id})"
                )
                
                # JSON logging for empty content scenario
                api_log_empty_content = {
                    "module": "EmailGeneratorV2",
                    "method": "_make_openai_request",
                    "hypothesis_id": "openai_api_failure",
                    "stage": "empty_content_exit",
                    "request_id": request_id,
                    "returning_none": True,
                    "timestamp": datetime.now().isoformat()
                }
                print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(api_log_empty_content)}")
                
                return None

            # JSON logging for successful exit
            api_log_success_exit = {
                "module": "EmailGeneratorV2",
                "method": "_make_openai_request",
                "hypothesis_id": "openai_api_failure",
                "stage": "success_exit",
                "request_id": request_id,
                "content_preview": content[:100] if content else None,
                "returning_none": False,
                "timestamp": datetime.now().isoformat()
            }
            print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(api_log_success_exit)}")

            return content

        except APIConnectionError as e:
            print(
                "EMAIL GENERATOR V2: ❌ API Connection Error: The server could not be reached"
            )
            print(f"EMAIL GENERATOR V2: 🔍 Underlying cause: {e.__cause__}")
            raise
        except RateLimitError as e:
            print(f"EMAIL GENERATOR V2: ❌ Rate Limit Error (429): {e}")
            print("EMAIL GENERATOR V2: 🔍 Backing off and retrying...")
            raise
        except AuthenticationError as e:
            print(f"EMAIL GENERATOR V2: ❌ Authentication Error (401): {e}")
            print("EMAIL GENERATOR V2: 🔍 Check OpenAI API key configuration")
            return None
        except PermissionDeniedError as e:
            print(f"EMAIL GENERATOR V2: ❌ Permission Denied (403): {e}")
            return None
        except BadRequestError as e:
            print(f"EMAIL GENERATOR V2: ❌ Bad Request (400): {e}")
            print(
                f"EMAIL GENERATOR V2: 🔍 Model: {model}, Prompt start: {prompt[:200]}..."
            )
            return None
        except UnprocessableEntityError as e:
            print(f"EMAIL GENERATOR V2: ❌ Unprocessable Entity (422): {e}")
            return None
        except APIStatusError as e:
            request_id = getattr(e, "request_id", "unknown")
            print(f"EMAIL GENERATOR V2: ❌ API Status Error: {e.status_code}")
            print(f"EMAIL GENERATOR V2: 🔍 Request ID: {request_id}")
            print(f"EMAIL GENERATOR V2: 🔍 Response: {e.response}")
            return None
        except APITimeoutError as e:
            print(f"EMAIL GENERATOR V2: ❌ Request Timeout: {e}")
            raise
        except APIError as e:
            print(f"EMAIL GENERATOR V2: ❌ General API Error: {e}")
            raise
        except (ValueError, TypeError, AttributeError, KeyError, OSError) as e:
            print(f"EMAIL GENERATOR V2: ❌ Unexpected error: {type(e).__name__}: {e}")
            print(
                f"EMAIL GENERATOR V2: 🔍 Model: {model}, Prompt start: {prompt[:200]}..."
            )
            return None

    # === FALLBACK AND ERROR HANDLING ===

    def _create_fallback_letter(
        self, analysis: CaseAnalysisResult, error_msg: str
    ) -> GeneratedLetter:
        """Create intelligent fallback letter with case-specific details when OpenAI generation fails."""
        print(
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
        case_details = self._extract_case_specific_details(analysis)

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
    ) -> dict[str, Any]:
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
                if hasattr(doc, 'key_information') and doc.key_information:
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
        self, analysis: CaseAnalysisResult, case_details: dict[str, Any]
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
        self, analysis: CaseAnalysisResult, case_details: dict[str, Any]
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
        self, analysis: CaseAnalysisResult, case_details: dict[str, Any]
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
        self, analysis: CaseAnalysisResult, case_details: dict[str, Any]
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
        self, analysis: CaseAnalysisResult, case_details: dict[str, Any]
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
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(context_log)}")

        # Apply comprehensive formatting pipeline
        processed_content = self._clean_ai_response(content)
        
        # Additional template-specific processing
        processed_content = self._ensure_html_structure(processed_content)
        processed_content = self._normalize_spacing(processed_content)
        
        return processed_content

    def _ensure_html_structure(self, content: str) -> str:
        """Ensure content has proper HTML structure for template rendering."""
        if not content:
            return content

        # Wrap content in paragraphs if not already wrapped
        if not re.search(r'<(?:p|div|ul|ol|h[1-6])\b', content, re.IGNORECASE):
            content = f"<p>{content}</p>"
        
        # Ensure proper paragraph breaks
        content = re.sub(r'\n\n+', '</p>\n\n<p>', content)
        
        return content

    def _normalize_spacing(self, content: str) -> str:
        """Normalize spacing for consistent template rendering."""
        if not content:
            return content

        # Normalize line endings
        content = re.sub(r'\r\n|\r', '\n', content)
        
        # Ensure consistent spacing around HTML elements
        content = re.sub(r'>\s*<', '><', content)
        content = re.sub(r'(<(?:p|div|h[1-6])[^>]*>)\s*', r'\1', content)
        content = re.sub(r'\s*(</(?:p|div|h[1-6])>)', r'\1', content)
        
        return content.strip()

    # === CONTENT FORMATTING HELPER METHODS ===

    def _format_legal_analysis(self, content: str) -> str:
        """Format legal analysis content with proper structure and hierarchy."""
        if not content:
            return content

        # Ensure consistent header formatting for legal analysis sections
        content = re.sub(
            r"(?i)(legal\s+analysis|analysis\s+and\s+position|statutory\s+analysis)",
            lambda m: f"<strong>{m.group(1).upper()}</strong>",
            content
        )
        
        # Format subsection headers (A, B, C, etc.)
        content = re.sub(
            r"^([A-Z])\.\s*([A-Z][^.]*?)(?=\n|$)",
            r"<strong>\1. \2</strong>",
            content,
            flags=re.MULTILINE
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
            content
        )
        
        # Format numbered recommendations
        content = re.sub(
            r"^(\d+)\.\s*([^.]+?)(?=\n|$)",
            r"<strong>\1.</strong> \2",
            content,
            flags=re.MULTILINE
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
            flags=re.MULTILINE
        )
        
        # Format numbered subsections with proper spacing
        content = re.sub(
            r"^(\d+)\.\s+(.+?)$",
            r"<strong>\1.</strong> \2",
            content,
            flags=re.MULTILINE
        )
        
        return content

    def _format_statutory_citations(self, content: str) -> str:
        """Format statutory citations cleanly and consistently."""
        if not content:
            return content

        # Format Florida statute citations
        content = re.sub(
            r"(?i)(florida\s+statutes?)\s+(?:section\s+|§\s*)?(\d+\.?\d*)",
            r"<strong>Fla. Stat. § \2</strong>",
            content
        )
        
        # Format chapter references
        content = re.sub(
            r"(?i)(florida\s+statutes?)\s+chapter\s+(\d+)",
            r"<strong>Fla. Stat. Chapter \2</strong>",
            content
        )
        
        # Clean up redundant citation patterns
        content = re.sub(
            r"<strong>Fla\.\s+Stat\.\s+§\s+([^<]+)</strong>\s*\([^)]*Florida\s+Statutes?[^)]*\)",
            r"<strong>Fla. Stat. § \1</strong>",
            content
        )
        
        return content

    def _format_bullet_points(self, content: str) -> str:
        """Format bullet points for professional presentation."""
        if not content:
            return content

        # Convert dashes and asterisks to proper bullet points
        content = re.sub(
            r"^[-*]\s+(.+?)$",
            r"• \1",
            content,
            flags=re.MULTILINE
        )
        
        # Wrap bullet points in proper HTML structure
        lines = content.split('\n')
        in_bullet_section = False
        formatted_lines = []
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('•'):
                if not in_bullet_section:
                    formatted_lines.append('<ul>')
                    in_bullet_section = True
                formatted_lines.append(f'<li>{stripped[1:].strip()}</li>')
            else:
                if in_bullet_section:
                    formatted_lines.append('</ul>')
                    in_bullet_section = False
                formatted_lines.append(line)
        
        if in_bullet_section:
            formatted_lines.append('</ul>')
        
        return '\n'.join(formatted_lines)

    def _clean_section_numbering(self, content: str) -> str:
        """Clean up redundant and repeated section numbering."""
        if not content:
            return content

        # Remove numbered section headers at the beginning of content (template handles headers)
        content = re.sub(
            r"^(\d+)\.\s*([A-Z][A-Z\s]+)(?:\n|$)",
            "",
            content,
            flags=re.MULTILINE
        )
        
        # Remove any remaining standalone section headers
        content = re.sub(
            r"^([A-Z][A-Z\s]{10,})(?:\n|$)",
            "",
            content,
            flags=re.MULTILINE
        )
        
        # Remove redundant section numbers at the beginning of content
        content = re.sub(
            r"^(\d+)\.\s*(\d+)\.\s*([A-Z][^.]*?)$",
            r"\1. \3",
            content,
            flags=re.MULTILINE
        )
        
        # Clean up repeated headers
        content = re.sub(
            r"^([A-Z\s]+)\n\1$",
            r"\1",
            content,
            flags=re.MULTILINE
        )
        
        # Remove section numbers that appear mid-sentence
        content = re.sub(
            r"(\w+)\s+\d+\.\s+([A-Z])",
            r"\1 \2",
            content
        )
        
        return content

    def _ensure_proper_whitespace(self, content: str) -> str:
        """Ensure proper whitespace and line breaks for readability."""
        if not content:
            return content

        # Add proper spacing after headers
        content = re.sub(
            r"(<h[1-6][^>]*>.*?</h[1-6]>)(\w)",
            r"\1\n\n\2",
            content
        )
        
        # Add spacing before new paragraphs
        content = re.sub(
            r"(</p>)(<p[^>]*>)",
            r"\1\n\n\2",
            content
        )
        
        # Ensure proper spacing around bullet points
        content = re.sub(
            r"(</ul>)(<p[^>]*>)",
            r"\1\n\n\2",
            content
        )
        
        content = re.sub(
            r"(</p>)(<ul>)",
            r"\1\n\n\2",
            content
        )
        
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
            flags=re.IGNORECASE
        )
        
        # Remove redundant disclaimers in the middle of content
        content = re.sub(
            r"(?i)\b(?:this is not legal advice|consult with an attorney|seek legal counsel)\b(?=.*?\w{10,})",
            "",
            content
        )
        
        # Clean up extra spaces left by removals
        content = re.sub(r"\s{2,}", " ", content)
        content = re.sub(r"^\s+|\s+$", "", content, flags=re.MULTILINE)
        
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
        text = re.sub(r'([.,])([A-Za-z])', r'\1 \2', text)
        
        # Remove duplicate introductory phrases (case-insensitive)
        text = re.sub(r'(\bthe path forward\b).*?\1', r'\1', text, flags=re.IGNORECASE | re.DOTALL)
        
        # Eliminate leading commas from each line
        text = '\n'.join([re.sub(r'^\s*,\s*', '', line) for line in text.splitlines()])
        
        return text

    # === EXTRACTION METHODS (from original code) ===

    def _extract_key_facts(self, analysis: CaseAnalysisResult) -> list[str]:
        """Extract key facts for the factual summary section."""
        facts = []
        if analysis.intake_analysis and analysis.intake_analysis.key_facts:
            if isinstance(analysis.intake_analysis.key_facts, list):
                facts.extend(analysis.intake_analysis.key_facts)
            else:
                facts.append(str(analysis.intake_analysis.key_facts))

        for doc in analysis.analyzed_documents:
            if hasattr(doc, 'key_information') and doc.key_information:
                facts.append(doc.key_information)

        return facts[:5]

    def _identify_emphasis_items(self, analysis: CaseAnalysisResult) -> dict[str, str]:
        """Identify items that should be bolded."""
        emphasis_items = {}

        if analysis.intake_analysis and analysis.intake_analysis.financial_impact:
            financial_info = str(analysis.intake_analysis.financial_impact)
            amounts = re.findall(r"\$[\d,]+\.?\d*", financial_info)
            for i, amount in enumerate(amounts):
                emphasis_items[f"amount_{i + 1}"] = amount

        return emphasis_items

    def _determine_legal_citation(self, analysis: CaseAnalysisResult) -> str | None:
        """Determine appropriate Florida statute citation."""
        if not analysis.intake_analysis:
            return None

        case_type = analysis.intake_analysis.case_type or ""
        case_type_lower = case_type.lower()

        citation_mapping = {
            "contract": "Fla. Stat. Chapter 672",
            "construction": "Fla. Stat. Chapter 558",
            "landlord": "Fla. Stat. Chapter 83",
            "tenant": "Fla. Stat. Chapter 83",
            "personal injury": "Fla. Stat. Chapter 768",
            "lien": "Fla. Stat. Chapter 713",
        }

        for key, citation in citation_mapping.items():
            if key in case_type_lower:
                return citation

        return None

    def _extract_legal_issues(self, analysis: CaseAnalysisResult) -> list[str]:
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

    def _extract_media_evidence_points(self, analysis: CaseAnalysisResult) -> list[str]:
        """Extract key points about media evidence."""
        points = []

        for media in analysis.transcripted_media:
            points.append(f"Audio analysis of {media.file_name}")

        for video in analysis.video_insights:
            points.append(f"Video analysis of {video.file_name}")

        return points

    def _extract_case_assessment_points(
        self, analysis: CaseAnalysisResult
    ) -> list[str]:
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

    def _extract_recommendations(self, analysis: CaseAnalysisResult) -> list[str]:
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
        persona = self.config.get('personas', {}).get('CONTINUING_LEGAL_ADVISOR', '')
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
            print(f"EMAIL GENERATOR V2: Error in generate_findings: {e}")
            return self._create_fallback_letter(analysis, str(e))

    def generate_email_and_analysis_docs(
        self, analysis: CaseAnalysisResult
    ) -> dict[str, str]:
        """
        Generate email and analysis documents using the refactored generator.
        """
        try:
            # Ensure analysis completeness
            self._ensure_analysis_completeness(analysis)

            # Generate letter using new architecture
            generated_letter = self.generate_findings(analysis)

            # Render templates
            main_template = self.jinja_env.get_template("findings_email.jinja2")
            appendix_template = self.jinja_env.get_template("document_appendix.jinja2")

            template_context = {
                "analysis": analysis,
                "generated_letter": generated_letter,
                "current_date": datetime.now().strftime("%B %d, %Y"),
                "case_timeline": getattr(analysis, "case_timeline", []),
                "format_video_analysis": self.format_video_analysis_for_appendix,
                "case_name": analysis.intake_analysis.case_type if analysis.intake_analysis and analysis.intake_analysis.case_type else "Your Case",
                "client_name": analysis.intake_analysis.client_name if analysis.intake_analysis and analysis.intake_analysis.client_name else "Client",
            }

            main_html_content = main_template.render(
                results=template_context, current_date=template_context["current_date"]
            )
            appendix_html_content = appendix_template.render(
                results=template_context, current_date=template_context["current_date"]
            )

            # CRITICAL: Apply final sanitization after full HTML assembly
            print("EMAIL GENERATOR V2: STAGE 4 - FINAL SANITIZATION")
            main_html_content = self._apply_final_sanitization(
                html_content=main_html_content,
                apply_polishing=True,  # Enable polish for full email realignment
                word_limit=850  # STRICT 850-word limit for complete email
            )
            
            # STAGE 5: WORD COUNT VALIDATION LOOP
            print("EMAIL GENERATOR V2: STAGE 5 - WORD COUNT VALIDATION")
            main_html_content = self._enforce_850_word_limit(
                html_content=main_html_content,
                generated_letter=generated_letter,
                analysis=analysis
            )
            
            appendix_html_content = self._apply_final_sanitization(
                html_content=appendix_html_content,
                apply_polishing=False,  # Skip polish for appendix
                word_limit=1500  # Higher limit for appendix
            )

            # STAGE 6: POST-PROCESSOR GUARD - Final validation and cleanup
            print("EMAIL GENERATOR V2: STAGE 6 - POST-PROCESSOR GUARD")
            main_html_content = self._apply_post_processor_guard(main_html_content)

            return {"main_letter": main_html_content, "appendix": appendix_html_content}

        except (ValueError, TypeError, AttributeError, KeyError, ImportError) as e:
            print(f"EMAIL GENERATOR V2: Error generating documents: {e}")
            return self._generate_fallback_documents(analysis, str(e))

    def format_video_analysis_for_appendix(self, video_insight) -> str:
        """Format video analysis for appendix (legacy compatibility)."""
        formatted_text = []

        if hasattr(video_insight, "insights") and video_insight.insights:
            insights = video_insight.insights

            if isinstance(insights, str):
                return f'<p style="margin: 0; font-size: 13px; line-height: 1.5;">{insights}</p>'

            if isinstance(insights, dict) and insights.get("summary"):
                formatted_text.append(
                    f"<div><strong>Summary:</strong> {insights['summary']}</div>"
                )

        return (
            "".join(formatted_text)
            if formatted_text
            else "<p>Video analysis details available.</p>"
        )

    def _generate_fallback_documents(
        self, analysis: CaseAnalysisResult, error_message: str
    ) -> dict[str, str]:
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


# Create alias for backward compatibility
EmailGenerator = EmailGeneratorV2
