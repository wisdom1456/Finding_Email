import base64
import re
import os
import logging
import traceback
from typing import List, Optional, Dict, Any
from openai import OpenAI, RateLimitError, APIError, APITimeoutError
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from pydantic import BaseModel, Field

from backend.utils.data_models import (
    CaseAnalysisResult,
    EmailResponse,
    EnhancedFindingsLetter,
    DownloadLink,
    AnalysisError,
    FindingsHeader,
    FindingsFooter,
    GeneratedLetter,
    EmailStructurePlan,
    SectionPlan,
    GenerationContext,
)
from backend_logic.quality_validator import QualityValidator

# === ENHANCED DATA MODELS FOR REFACTORED ARCHITECTURE ===

class GenerationOutput(BaseModel):
    """Enhanced output structure for email generation with debugging capabilities."""
    letter: GeneratedLetter
    debug_info: Optional[Dict[str, Any]] = None
    validation_results: Dict[str, bool] = Field(default_factory=dict)
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
    pass

class EmailGenerationError(Exception):
    """Raised when email generation fails completely."""
    pass

# === AUTHENTIC ATTORNEY ADVISOR FRAMEWORK ===

CORE_DIRECTIVES = """
**CORE DIRECTIVES - Apply to ALL legal communications:**

1. **Direct Professional Tone:** Matter-of-fact communication without overselling the case
2. **Numbered Sections:** Use clear numbered sections with ALL CAPS headers (e.g., "1. FACTUAL SUMMARY")
3. **Bullet Points:** Use bullet points for key facts and organized information
4. **Concise Writing:** Be efficient and direct - avoid wordiness or repetitive language
5. **Florida Law Exclusive:** Reference ONLY Florida statutes, case law, and legal precedents
6. **Professional Realism:** Present facts and law objectively without artificial optimism
"""

HIGH_STAKES_ADVICE_PROTOCOL = """
**HIGH-STAKES ADVICE PROTOCOL** (Use ONLY when recommending counter-intuitive actions):

When legal strategy contradicts client expectations:
1. **Acknowledge the Complexity:** "This situation requires careful consideration..."
2. **Explain the Legal Reasoning:** Provide clear rationale using Florida law
3. **Present Supporting Evidence:** Reference specific Florida cases or statutes
4. **Outline Consequences:** Explain both action and inaction outcomes
5. **Professional Guidance:** "Based on our analysis under Florida law..."
"""

AUTHENTIC_ATTORNEY_ADVISOR = f"""
You are an AUTHENTIC_ATTORNEY_ADVISOR - a senior litigation attorney writing a professional legal analysis letter that mirrors the style of real attorney communications.

{CORE_DIRECTIVES}

**MANDATORY STYLE REQUIREMENTS:**
1. **Professional Greeting:** Use natural attorney language like "Good afternoon [Client Name]" or "Dear [Client Name]"
2. **Numbered Sections:** Format with numbered sections using ALL CAPS headers (1. FACTUAL SUMMARY, 2. LEGAL ANALYSIS, etc.)
3. **Direct Language:** Use direct, professional language without forced collaboration or artificial "we" statements
4. **Bullet Points:** Organize key information using bullet points for clarity
5. **Florida Law Focus:** Reference ONLY Florida statutes, case law, and legal precedents with proper legal citation format
6. **Matter-of-Fact Tone:** Present analysis objectively without overselling the strength of the case
7. **Single Professional Closing:** End with one professional closing, not repetitive signatures

**FORMATTING REQUIREMENT:** This is the OPENING section, so include appropriate professional greeting.
"""

CONTINUING_ATTORNEY_ADVISOR = f"""
You are an AUTHENTIC_ATTORNEY_ADVISOR CONTINUING a professional legal analysis letter.

{CORE_DIRECTIVES}

**MANDATORY STYLE REQUIREMENTS:**
1. **NO Greetings or Closings:** Continue seamlessly from previous section without additional greetings or signatures
2. **Consistent Professional Tone:** Maintain the established direct, matter-of-fact tone
3. **Numbered Section Format:** Continue the numbered section format with ALL CAPS headers
4. **Florida Law Focus:** Reference ONLY Florida statutes, case law, and legal precedents
5. **Bullet Points:** Use bullet points to organize information clearly
6. **Objective Analysis:** Present information factually without artificial enthusiasm or overselling

**CONTINUATION REQUIREMENT:** This section continues an existing letter - no new greetings or closings.
"""

STRICT_FORMAT_ENFORCEMENT = """
CRITICAL FORMATTING REQUIREMENTS:
1. **HTML Only:** Use ONLY HTML tags for all formatting. Never use Markdown (`**bold**`, `*italic*`).
2. **Clean Output:** Generate clean HTML suitable for direct client presentation. DO NOT include `'''html'''` or any other code fences in your response.
3. **Numbered Sections:** Use numbered sections with ALL CAPS headers (e.g., "1. FACTUAL SUMMARY").
4. **Bullet Points:** Use bullet points (`<ul>`, `<li>`) for organized information where appropriate.
5. **Professional Formatting:** Clean, efficient layout matching real attorney communications.
"""

class EmailGeneratorV2:
    """
    Refactored EmailGenerator with linear three-stage pipeline architecture.
    
    Architecture:
    1. PREPARE: Validate input and create structure plan
    2. GENERATE: Generate each section with proper field mapping
    3. FORMAT: Validate output and ensure all template fields are populated
    """

    def __init__(self, client: OpenAI):
        """Initialize the EmailGenerator with OpenAI client and Jinja2 environment."""
        if not client:
            raise ValueError("An OpenAI client is required for EmailGenerator.")
        self.client = client
        
        # Initialize template environment with robust path resolution
        template_dir = self._find_template_directory()
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        self.quality_validator = QualityValidator()
        
        print("EMAIL GENERATOR V2: ✅ Initialized with linear three-stage pipeline")

    def _find_template_directory(self) -> str:
        """Find template directory using robust path resolution."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = current_dir
        
        # Navigate up until we find the project root
        while project_root != '/' and not (
            os.path.exists(os.path.join(project_root, 'app.py')) and
            os.path.exists(os.path.join(project_root, 'backend'))
        ):
            project_root = os.path.dirname(project_root)
        
        if project_root == '/':
            project_root = os.getcwd()
        
        template_dir = os.path.join(project_root, 'backend', 'assets', 'templates')
        
        if not os.path.exists(template_dir):
            raise FileNotFoundError(f"Template directory not found: {template_dir}")
        
        # Verify required templates exist
        required_templates = ['findings_email.jinja2', 'document_appendix.jinja2']
        available_files = os.listdir(template_dir)
        missing_templates = [t for t in required_templates if t not in available_files]
        if missing_templates:
            raise FileNotFoundError(f"Required templates missing: {missing_templates}")
        
        print(f"EMAIL GENERATOR V2: Template directory: {template_dir}")
        return template_dir

    # === STAGE 1: PREPARE - Input Validation and Structure Planning ===

    def generate_email_with_debug(self, analysis: CaseAnalysisResult) -> GenerationOutput:
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
            debug_info.structure_plan = structure_plan.dict() if structure_plan else None
            
            # STAGE 2: GENERATE
            print("EMAIL GENERATOR V2: STAGE 2 - GENERATE")
            generated_sections = self._generate_all_sections_with_tracking(structure_plan, analysis, debug_info)
            
            # STAGE 3: FORMAT
            print("EMAIL GENERATOR V2: STAGE 3 - FORMAT")
            letter = self._map_sections_to_template_fields(generated_sections, structure_plan, analysis)
            self._validate_generated_letter(letter)
            
            debug_info.generation_time = datetime.now().timestamp() - start_time
            debug_info.validation_results = self._validate_all_fields(letter)
            
            return GenerationOutput(
                letter=letter,
                debug_info=debug_info.dict(),
                validation_results=debug_info.validation_results,
                generation_metadata={
                    'generation_time': debug_info.generation_time,
                    'sections_generated': len(generated_sections),
                    'plan_sections': len(structure_plan.sections) if structure_plan else 0
                }
            )
            
        except Exception as e:
            error_info = {
                'error': str(e),
                'traceback': traceback.format_exc(),
                'stage': 'unknown'
            }
            debug_info.errors.append(error_info)
            debug_info.generation_time = datetime.now().timestamp() - start_time
            
            # Return fallback letter with debug info
            fallback_letter = self._create_fallback_letter(analysis, str(e))
            
            return GenerationOutput(
                letter=fallback_letter,
                debug_info=debug_info.dict(),
                validation_results={'error': True},
                generation_metadata={
                    'generation_time': debug_info.generation_time,
                    'error': str(e),
                    'fallback_used': True
                }
            )

    def _validate_input_analysis(self, analysis: CaseAnalysisResult) -> None:
        """Validate that analysis has required components for email generation."""
        if not analysis:
            raise EmailGenerationError("Analysis object is required")
        
        # Ensure we have basic components
        if not analysis.intake_analysis:
            print("EMAIL GENERATOR V2: ⚠️  Missing intake_analysis, creating fallback")
            self._ensure_analysis_completeness(analysis)
        
        if not analysis.analyzed_documents:
            print("EMAIL GENERATOR V2: ⚠️  No analyzed documents found")
            
        print("EMAIL GENERATOR V2: ✅ Input validation complete")

    def _get_validation_summary(self, analysis: CaseAnalysisResult) -> Dict[str, Any]:
        """Get comprehensive validation summary for debugging."""
        return {
            'has_intake_analysis': analysis.intake_analysis is not None,
            'has_legal_assessment': analysis.legal_assessment is not None,
            'analyzed_documents_count': len(analysis.analyzed_documents) if analysis.analyzed_documents else 0,
            'has_video_insights': bool(analysis.video_insights),
            'has_transcripted_media': bool(analysis.transcripted_media),
            'client_name': analysis.intake_analysis.client_name if analysis.intake_analysis else None,
            'case_type': analysis.intake_analysis.case_type if analysis.intake_analysis else None
        }

    def _create_comprehensive_structure_plan(self, analysis: CaseAnalysisResult) -> EmailStructurePlan:
        """Create detailed structure plan for email generation."""
        client_name = analysis.intake_analysis.client_name if analysis.intake_analysis else "Client"
        case_type = analysis.intake_analysis.case_type if analysis.intake_analysis else "Legal Matter"
        
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
        sections.append(SectionPlan(
            number=section_number,
            header="FACTUAL SUMMARY",
            key_points=self._extract_key_facts(analysis),
            emphasis_items=self._identify_emphasis_items(analysis),
            content_requirements=["chronological events", "key parties", "important dates and amounts"]
        ))
        section_number += 1
        
        # 2. LEGAL ANALYSIS
        legal_citation = self._determine_legal_citation(analysis)
        sections.append(SectionPlan(
            number=section_number,
            header="LEGAL ANALYSIS",
            legal_citation=legal_citation,
            key_points=self._extract_legal_issues(analysis),
            emphasis_items={},
            content_requirements=["legal claims", "Florida law application", "case strengths"]
        ))
        section_number += 1
        
        # 3. EVIDENCE REVIEW (if media exists)
        if analysis.transcripted_media or analysis.video_insights:
            sections.append(SectionPlan(
                number=section_number,
                header="EVIDENCE REVIEW",
                key_points=self._extract_media_evidence_points(analysis),
                emphasis_items={},
                content_requirements=["media analysis", "evidence significance"]
            ))
            section_number += 1
        
        # 4. STRENGTHS AND CHALLENGES
        sections.append(SectionPlan(
            number=section_number,
            header="CASE ASSESSMENT",
            key_points=self._extract_case_assessment_points(analysis),
            emphasis_items={},
            content_requirements=["strengths", "challenges", "strategic considerations"]
        ))
        section_number += 1
        
        # 5. RECOMMENDED NEXT STEPS
        sections.append(SectionPlan(
            number=section_number,
            header="RECOMMENDED NEXT STEPS",
            key_points=self._extract_recommendations(analysis),
            emphasis_items={},
            content_requirements=["prioritized actions", "timelines", "strategic considerations"]
        ))
        
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
                "has_media": bool(analysis.transcripted_media or analysis.video_insights),
                "urgency": analysis.intake_analysis.urgency_level if analysis.intake_analysis else "Standard"
            }
        )
        
        print(f"EMAIL GENERATOR V2: Created structure plan with {len(sections)} sections")
        return plan

    # === STAGE 2: GENERATE - Section Generation with Proper Mapping ===

    def _generate_all_sections_with_tracking(self, plan: EmailStructurePlan, analysis: CaseAnalysisResult, debug_info: DebugOutput) -> Dict[str, str]:
        """Generate all sections with detailed tracking for debugging."""
        generated_sections = {}
        context = GenerationContext()
        
        # Generate header/greeting
        print("EMAIL GENERATOR V2: Generating greeting section...")
        greeting_content = self._generate_greeting_section(plan, analysis, context)
        generated_sections['greeting'] = greeting_content
        debug_info.generated_sections['greeting'] = {
            'content_length': len(greeting_content),
            'is_empty': not greeting_content.strip(),
            'first_100_chars': greeting_content[:100] if greeting_content else None
        }
        
        # Generate each planned section
        for section_plan in plan.sections:
            print(f"EMAIL GENERATOR V2: Generating section: {section_plan.header}")
            try:
                section_content = self._generate_section_with_validation(section_plan, context, analysis)
                section_key = self._section_header_to_key(section_plan.header)
                generated_sections[section_key] = section_content
                
                debug_info.generated_sections[section_key] = {
                    'header': section_plan.header,
                    'content_length': len(section_content),
                    'is_empty': not section_content.strip(),
                    'first_100_chars': section_content[:100] if section_content else None,
                    'validation_passed': bool(section_content and section_content.strip())
                }
                
                # Update context
                context.section_numbers_used.append(section_plan.number)
                
            except Exception as e:
                error_msg = f"Failed to generate section {section_plan.header}: {str(e)}"
                print(f"EMAIL GENERATOR V2: ❌ {error_msg}")
                
                # Generate fallback content
                fallback_content = self._generate_fallback_section_content(section_plan, analysis)
                section_key = self._section_header_to_key(section_plan.header)
                generated_sections[section_key] = fallback_content
                
                debug_info.errors.append({
                    'section': section_plan.header,
                    'error': str(e),
                    'fallback_used': True
                })
        
        # Generate closing
        print("EMAIL GENERATOR V2: Generating closing section...")
        closing_content = self._generate_closing_section(plan, analysis, context)
        generated_sections['closing'] = closing_content
        debug_info.generated_sections['closing'] = {
            'content_length': len(closing_content),
            'is_empty': not closing_content.strip(),
            'first_100_chars': closing_content[:100] if closing_content else None
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
            "RECOMMENDED NEXT STEPS": "next_steps"
        }
        return header_mapping.get(header, header.lower().replace(" ", "_"))

    def _generate_section_with_validation(self, section_plan: SectionPlan, context: GenerationContext, analysis: CaseAnalysisResult) -> str:
        """Generate a section with explicit validation."""
        # Build section header
        header = self._format_section_header(section_plan.number, section_plan.header, section_plan.legal_citation)
        
        # Generate section content based on type
        if section_plan.header == "FACTUAL SUMMARY":
            content = self._generate_factual_summary_content(section_plan, analysis, context)
        elif section_plan.header == "LEGAL ANALYSIS":
            content = self._generate_legal_analysis_content(section_plan, analysis, context)
        elif section_plan.header == "EVIDENCE REVIEW":
            content = self._generate_evidence_review_content(section_plan, analysis, context)
        elif section_plan.header == "CASE ASSESSMENT":
            content = self._generate_case_assessment_content(section_plan, analysis, context)
        elif section_plan.header == "RECOMMENDED NEXT STEPS":
            content = self._generate_next_steps_content(section_plan, analysis, context)
        else:
            content = self._generate_generic_section_content(section_plan, analysis, context)
        
        # Validate content is not empty
        if not content or not content.strip():
            raise SectionValidationError(f"Section '{section_plan.header}' generated empty content")
        
        full_section = header + "\n" + content
        return self._clean_ai_response(full_section)

    # === STAGE 3: FORMAT - Field Mapping and Validation ===

    def _map_sections_to_template_fields(self, generated_sections: Dict[str, str], plan: EmailStructurePlan, analysis: CaseAnalysisResult) -> GeneratedLetter:
        """
        CRITICAL FIX: Properly map generated sections to specific template fields.
        This fixes the bug where all content was placed in executive_summary only.
        """
        print("EMAIL GENERATOR V2: Mapping sections to template fields...")
        
        # Extract individual sections from generated content
        greeting = generated_sections.get('greeting', '')
        factual_summary = generated_sections.get('factual_summary', '')
        legal_analysis = generated_sections.get('legal_analysis', '')
        evidence_review = generated_sections.get('evidence_review', '')
        case_assessment = generated_sections.get('case_assessment', '')
        next_steps = generated_sections.get('next_steps', '')
        closing = generated_sections.get('closing', '')
        
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
            closing_paragraph=closing  # Professional closing
        )
        
        print("EMAIL GENERATOR V2: ✅ Sections mapped to template fields")
        print(f"  - executive_summary: {len(letter.executive_summary)} chars")
        print(f"  - background_summary: {len(letter.background_summary)} chars")
        print(f"  - analysis_and_position: {len(letter.analysis_and_position)} chars")
        print(f"  - next_steps: {len(letter.next_steps)} chars")
        print(f"  - closing_paragraph: {len(letter.closing_paragraph)} chars")
        
        return letter

    def _split_case_assessment(self, case_assessment: str) -> tuple[str, str]:
        """Split combined case assessment into strengths and challenges."""
        if not case_assessment:
            return "", ""
        
        # Look for headers that indicate strengths vs challenges
        strengths_keywords = ["strength", "advantage", "positive", "favorable", "support"]
        challenges_keywords = ["challenge", "weakness", "risk", "concern", "obstacle"]
        
        # Simple split based on content patterns
        lines = case_assessment.split('\n')
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
        
        return '\n'.join(strengths_lines), '\n'.join(challenges_lines)

    def _validate_generated_letter(self, letter: GeneratedLetter) -> None:
        """Validate that generated letter has all required fields populated."""
        required_fields = [
            'executive_summary',
            'background_summary', 
            'analysis_and_position',
            'next_steps',
            'closing_paragraph'
        ]
        
        empty_fields = []
        for field in required_fields:
            value = getattr(letter, field, '')
            if not value or not value.strip():
                empty_fields.append(field)
        
        if empty_fields:
            raise EmailGenerationError(f"Required fields are empty: {', '.join(empty_fields)}")
        
        print("EMAIL GENERATOR V2: ✅ Letter validation passed")

    def _validate_all_fields(self, letter: GeneratedLetter) -> Dict[str, Dict[str, Any]]:
        """Comprehensive validation of all letter fields for debugging."""
        validation_results = {}
        
        for field_name in letter.__fields__:
            field_value = getattr(letter, field_name, '')
            validation_results[field_name] = {
                'has_content': bool(field_value and field_value.strip()),
                'length': len(field_value) if field_value else 0,
                'first_50_chars': field_value[:50] if field_value else None
            }
        
        return validation_results

    # === CONTENT GENERATION METHODS ===

    def _generate_greeting_section(self, plan: EmailStructurePlan, analysis: CaseAnalysisResult, context: GenerationContext) -> str:
        """Generate professional greeting section."""
        context.greeting_given = True
        context.client_name_mentioned = True
        
        return f"""
        <p>{plan.greeting}</p>
        <p>I have completed my review of your legal matter and am prepared to present my findings and recommendations.</p>
        """

    def _generate_factual_summary_content(self, section_plan: SectionPlan, analysis: CaseAnalysisResult, context: GenerationContext) -> str:
        """Generate factual summary content with validation."""
        prompt = f"""
        Generate a factual summary section for a professional legal findings letter using the AUTHENTIC_ATTORNEY style.
        
        REQUIREMENTS:
        - Use bullet points for key facts
        - Bold important amounts, dates, and terms using <strong> tags
        - Be direct and matter-of-fact
        - Include specific details like dates, amounts, parties involved
        - Reference only Florida law when applicable
        - Do NOT include section headers or numbers (already provided)
        - Do NOT include greetings or closings
        
        Key Facts to Include:
        {section_plan.key_points}
        
        Case Context:
        Client: {analysis.intake_analysis.client_name if analysis.intake_analysis else 'Client'}
        Case Type: {analysis.intake_analysis.case_type if analysis.intake_analysis else 'Legal Matter'}
        
        Generate only the factual summary content with bullet points and proper emphasis.
        """
        
        result = self._make_openai_request(prompt, CONTINUING_ATTORNEY_ADVISOR)
        return result or "<p>Factual summary of the key events and circumstances.</p>"

    def _generate_legal_analysis_content(self, section_plan: SectionPlan, analysis: CaseAnalysisResult, context: GenerationContext) -> str:
        """Generate legal analysis content with Florida law focus."""
        prompt = f"""
        Generate a legal analysis section for a professional legal findings letter using the AUTHENTIC_ATTORNEY style.
        
        REQUIREMENTS:
        - Focus exclusively on Florida law and statutes
        - Use bullet points for legal issues
        - Bold key legal terms and citations using <strong> tags
        - Be objective and professional
        - Include claim viability assessment
        - Do NOT include section headers or numbers (already provided)
        - Do NOT include greetings or closings
        
        Legal Issues to Address:
        {section_plan.key_points}
        
        Legal Citation Reference: {section_plan.legal_citation or 'Florida Statutes (applicable provisions)'}
        
        Case Context:
        {analysis.model_dump_json(indent=2)}
        
        Generate only the legal analysis content with Florida law focus.
        """
        
        result = self._make_openai_request(prompt, CONTINUING_ATTORNEY_ADVISOR)
        return result or "<p>Legal analysis under Florida law indicates several key considerations.</p>"

    def _generate_evidence_review_content(self, section_plan: SectionPlan, analysis: CaseAnalysisResult, context: GenerationContext) -> str:
        """Generate evidence review content focusing on media and documents."""
        if not analysis.transcripted_media and not analysis.video_insights:
            return ""
            
        prompt = f"""
        Generate an evidence review section for a professional legal findings letter using the AUTHENTIC_ATTORNEY style.
        
        REQUIREMENTS:
        - Summarize key evidence findings
        - Use bullet points for different types of evidence
        - Bold important findings and file names using <strong> tags
        - Explain relevance to case under Florida evidence law
        - Do NOT include section headers or numbers (already provided)
        - Do NOT include greetings or closings
        
        Evidence Points to Cover:
        {section_plan.key_points}
        
        Case Context:
        {analysis.model_dump_json(indent=2)}
        
        Generate only the evidence review content with professional assessment.
        """
        
        result = self._make_openai_request(prompt, CONTINUING_ATTORNEY_ADVISOR)
        return result or "<p>Review of the evidence reveals important information relevant to this case.</p>"

    def _generate_case_assessment_content(self, section_plan: SectionPlan, analysis: CaseAnalysisResult, context: GenerationContext) -> str:
        """Generate combined case assessment covering strengths and challenges."""
        prompt = f"""
        Generate a case assessment section for a professional legal findings letter using the AUTHENTIC_ATTORNEY style.
        
        REQUIREMENTS:
        - Assess both strengths and potential challenges
        - Use bullet points for organized information
        - Bold important terms and citations using <strong> tags
        - Be objective and professional - don't oversell or minimize
        - Focus on Florida law standards
        - Do NOT include section headers or numbers (already provided)
        - Do NOT include greetings or closings
        
        Assessment Points to Address:
        {section_plan.key_points}
        
        Case Context:
        {analysis.model_dump_json(indent=2)}
        
        Generate only the case assessment content with balanced analysis.
        """
        
        result = self._make_openai_request(prompt, CONTINUING_ATTORNEY_ADVISOR)
        return result or "<p>Case assessment reveals both strengths and considerations under Florida law.</p>"

    def _generate_next_steps_content(self, section_plan: SectionPlan, analysis: CaseAnalysisResult, context: GenerationContext) -> str:
        """Generate next steps content with prioritized actions."""
        prompt = f"""
        Generate a recommended next steps section for a professional legal findings letter using the AUTHENTIC_ATTORNEY style.
        
        REQUIREMENTS:
        - Use bullet points for each recommended action
        - Prioritize actions in logical order
        - Bold important deadlines and requirements using <strong> tags
        - Include specific timelines where applicable
        - Focus on Florida law procedures
        - Be direct and actionable
        - Do NOT include section headers or numbers (already provided)
        - Do NOT include greetings or closings
        
        Recommended Actions:
        {section_plan.key_points}
        
        Case Context:
        {analysis.model_dump_json(indent=2)}
        
        Generate only the recommended next steps content with prioritized actions.
        """
        
        result = self._make_openai_request(prompt, CONTINUING_ATTORNEY_ADVISOR)
        return result or "<p>Based on our analysis, the following steps are recommended to advance your case.</p>"

    def _generate_generic_section_content(self, section_plan: SectionPlan, analysis: CaseAnalysisResult, context: GenerationContext) -> str:
        """Generate any other section type with appropriate formatting."""
        prompt = f"""
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
        
        result = self._make_openai_request(prompt, CONTINUING_ATTORNEY_ADVISOR)
        return result or f"<p>{section_plan.header.title()} analysis for this case.</p>"

    def _generate_closing_section(self, plan: EmailStructurePlan, analysis: CaseAnalysisResult, context: GenerationContext) -> str:
        """Generate professional closing section."""
        if context.closing_given:
            return ""
        
        context.closing_given = True
        
        return f"""
        <p>{plan.closing}</p>
        <p><strong>Sincerely,</strong><br>
        {analysis.intake_analysis.attorney_name if analysis.intake_analysis and analysis.intake_analysis.attorney_name else 'Your Legal Team'}<br>
        Bernhardt Riley PLLC</p>
        """

    # === UTILITY AND HELPER METHODS ===

    def _format_section_header(self, number: int, header: str, citation: str = None) -> str:
        """Format section header with consistent structure."""
        if citation:
            return f"<h3>{number}. {header.upper()} ({citation})</h3>"
        return f"<h3>{number}. {header.upper()}</h3>"

    def _clean_ai_response(self, content: str, is_counter_intuitive: bool = False) -> str:
        """Clean AI response with essential transformations."""
        if not content:
            return ""
            
        # Remove markdown artifacts
        cleaned = re.sub(r'^```[a-zA-Z]*\n?', '', content, flags=re.MULTILINE)
        cleaned = re.sub(r'```$', '', cleaned, flags=re.MULTILINE)
        
        # Convert markdown formatting
        cleaned = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', cleaned)
        cleaned = re.sub(r'\*(.*?)\*', r'<em>\1</em>', cleaned)
        
        # Fix HTML formatting issues
        cleaned = re.sub(r'<p>\s*<p>', '<p>', cleaned)
        cleaned = re.sub(r'</p>\s*</p>', '</p>', cleaned)
        cleaned = re.sub(r'<p>\s*</p>', '', cleaned)
        
        # Clean up excessive whitespace
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
        cleaned = cleaned.strip()
        
        return cleaned

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type((RateLimitError, APIError, APITimeoutError)))
    def _make_openai_request(self, prompt: str, persona: str, model: str = "gpt-4o") -> Optional[str]:
        """Make OpenAI API request with retry logic."""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": f"{persona}\n\n{STRICT_FORMAT_ENFORCEMENT}"},
                    {"role": "user", "content": prompt}
                ],
            )
            return response.choices[0].message.content
        except (RateLimitError, APIError, APITimeoutError) as e:
            print(f"EMAIL GENERATOR V2: OpenAI API Error: {e}. Retrying...")
            raise
        except Exception as e:
            print(f"EMAIL GENERATOR V2: Unexpected OpenAI error: {e}")
            return None

    # === FALLBACK AND ERROR HANDLING ===

    def _create_fallback_letter(self, analysis: CaseAnalysisResult, error_msg: str) -> GeneratedLetter:
        """Create basic fallback letter when generation fails."""
        client_name = analysis.intake_analysis.client_name if analysis.intake_analysis else "Client"
        
        return GeneratedLetter(
            executive_summary=f"<p>Dear {client_name},</p><p>I have completed my review of your legal matter.</p>",
            background_summary="<p>Based on our review, the following facts are relevant to this matter.</p>",
            analysis_and_position="<p>Legal analysis under Florida law indicates several key considerations.</p>",
            media_summary="<p>Review of available evidence and documentation.</p>",
            video_analysis_appendix="",
            strengths="<p>Analysis has identified strengths in this case under Florida law.</p>",
            challenges="<p>Several considerations require careful attention under Florida law.</p>",
            recommendations="<p>Based on comprehensive analysis, strategic recommendations follow.</p>",
            next_steps="<p>The following steps are recommended to advance your case.</p>",
            closing_paragraph="<p><strong>Sincerely,</strong><br>Your Legal Team<br>Bernhardt Riley PLLC</p>"
        )

    def _generate_fallback_section_content(self, section_plan: SectionPlan, analysis: CaseAnalysisResult) -> str:
        """Generate basic fallback content for a failed section."""
        section_name = section_plan.header.lower().replace("_", " ")
        return f"<p>{section_name.title()} analysis for this case under Florida law.</p>"

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
            if doc.key_information:
                facts.append(doc.key_information)
        
        return facts[:5]

    def _identify_emphasis_items(self, analysis: CaseAnalysisResult) -> Dict[str, str]:
        """Identify items that should be bolded."""
        emphasis_items = {}
        
        if analysis.intake_analysis and analysis.intake_analysis.financial_impact:
            financial_info = str(analysis.intake_analysis.financial_impact)
            amounts = re.findall(r'\$[\d,]+\.?\d*', financial_info)
            for i, amount in enumerate(amounts):
                emphasis_items[f"amount_{i+1}"] = amount
        
        return emphasis_items

    def _determine_legal_citation(self, analysis: CaseAnalysisResult) -> Optional[str]:
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
            "lien": "Fla. Stat. Chapter 713"
        }
        
        for key, citation in citation_mapping.items():
            if key in case_type_lower:
                return citation
                
        return None

    def _extract_legal_issues(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract legal issues for analysis section."""
        issues = []
        
        if analysis.legal_assessment:
            if analysis.legal_assessment.claim_viability:
                issues.append(f"Claim viability: {analysis.legal_assessment.claim_viability}")
                
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

    def _extract_case_assessment_points(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract points for case assessment section."""
        points = []
        
        if analysis.legal_assessment:
            if analysis.legal_assessment.claim_viability:
                points.append(f"Claim assessment: {analysis.legal_assessment.claim_viability}")
            if analysis.legal_assessment.overall_evidence_strength:
                points.append(f"Evidence strength: {analysis.legal_assessment.overall_evidence_strength}")
                
        return points

    def _extract_recommendations(self, analysis: CaseAnalysisResult) -> List[str]:
        """Extract recommendations for next steps."""
        recommendations = []
        
        if analysis.legal_assessment and analysis.legal_assessment.recommended_actions:
            if isinstance(analysis.legal_assessment.recommended_actions, list):
                recommendations.extend(analysis.legal_assessment.recommended_actions)
            else:
                recommendations.append(str(analysis.legal_assessment.recommended_actions))
                
        return recommendations

    def _ensure_analysis_completeness(self, analysis: CaseAnalysisResult) -> None:
        """Ensure analysis has required components."""
        from backend.utils.validators import create_fallback_legal_assessment, create_fallback_demand_letter_evaluation
        
        if not analysis.intake_analysis:
            from backend.utils.data_models import EnhancedIntakeAnalysis
            analysis.intake_analysis = EnhancedIntakeAnalysis(
                client_name="Client",
                attorney_name="Attorney",
                case_summary="Legal matter requiring analysis",
                case_type="Legal Case",
                urgency_level="Standard"
            )
        
        if not analysis.legal_assessment:
            from backend.utils.data_models import LegalAssessment
            analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
        
        if not analysis.demand_letter_evaluation:
            from backend.utils.data_models import DemandLetterEvaluation
            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())

    def _generate_video_analysis_appendix(self, analysis: CaseAnalysisResult) -> str:
        """Generate video analysis appendix if video data exists."""
        if not analysis.video_insights:
            return ""
        
        # Use existing video appendix generation logic
        video_data_for_prompt = []
        has_preserved_data = False
        
        for video_insight in analysis.video_insights:
            video_data = {
                "file_name": video_insight.file_name,
                "transcript": video_insight.transcript,
                "labels": video_insight.labels,
                "objects": video_insight.objects,
                "text_annotations": video_insight.text_annotations,
                "duration": video_insight.duration,
                "confidence": video_insight.confidence
            }
            
            if hasattr(video_insight, 'insights_gcs_uri') and video_insight.insights_gcs_uri:
                has_preserved_data = True
                if hasattr(video_insight, 'insights_summary') and video_insight.insights_summary:
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
        
        result = self._make_openai_request(prompt, CONTINUING_ATTORNEY_ADVISOR)
        return result or ""

    # === LEGACY COMPATIBILITY METHODS ===

    def generate_findings(self, analysis: CaseAnalysisResult) -> GeneratedLetter:
        """
        Legacy compatibility method - now uses the refactored architecture.
        """
        try:
            output = self.generate_email_with_debug(analysis)
            return output.letter
        except Exception as e:
            print(f"EMAIL GENERATOR V2: Error in generate_findings: {e}")
            return self._create_fallback_letter(analysis, str(e))

    def generate_email_and_analysis_docs(self, analysis: CaseAnalysisResult) -> Dict[str, str]:
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
                'analysis': analysis,
                'generated_letter': generated_letter,
                'current_date': datetime.now().strftime('%B %d, %Y'),
                'case_timeline': getattr(analysis, 'case_timeline', []),
                'format_video_analysis': self.format_video_analysis_for_appendix
            }
            
            main_html_content = main_template.render(results=template_context, current_date=template_context['current_date'])
            appendix_html_content = appendix_template.render(results=template_context, current_date=template_context['current_date'])
            
            return {
                "main_letter": main_html_content,
                "appendix": appendix_html_content
            }
            
        except Exception as e:
            print(f"EMAIL GENERATOR V2: Error generating documents: {e}")
            return self._generate_fallback_documents(analysis, str(e))

    def format_video_analysis_for_appendix(self, video_insight) -> str:
        """Format video analysis for appendix (legacy compatibility)."""
        formatted_text = []
        
        if hasattr(video_insight, 'insights') and video_insight.insights:
            insights = video_insight.insights
            
            if isinstance(insights, str):
                return f'<p style="margin: 0; font-size: 13px; line-height: 1.5;">{insights}</p>'
            
            if isinstance(insights, dict):
                if 'summary' in insights and insights['summary']:
                    formatted_text.append(f'<div><strong>Summary:</strong> {insights["summary"]}</div>')
        
        return ''.join(formatted_text) if formatted_text else '<p>Video analysis details available.</p>'

    def _generate_fallback_documents(self, analysis: CaseAnalysisResult, error_message: str) -> Dict[str, str]:
        """Generate fallback documents when template rendering fails."""
        client_name = analysis.intake_analysis.client_name if analysis.intake_analysis else "Client"
        current_date = datetime.now().strftime('%B %d, %Y')
        
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
        
        return {
            "main_letter": main_letter,
            "appendix": appendix
        }


# Create alias for backward compatibility
EmailGenerator = EmailGeneratorV2