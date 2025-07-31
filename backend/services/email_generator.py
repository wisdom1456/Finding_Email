import base64
import re
import os
from typing import List, Optional, Dict, Any
from openai import OpenAI, RateLimitError, APIError, APITimeoutError
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from ..utils.data_models import (
    CombinedAnalysis,
    EmailResponse,
    EnhancedFindingsLetter,
    DownloadLink,
    AnalysisError,
    EnhancedCaseAnalysis,
    LegalAssessment,
    DemandLetterEvaluation,
    FindingsHeader,
    FindingsFooter,
    QualityScore,
)
from .quality_validator import QualityValidator

# Constants
SENIOR_ATTORNEY_PERSONA = """
You are a seasoned litigation attorney with 15+ years of experience at a respected law firm.
Your specialty areas include:
- Contract disputes and breach of contract claims
- Landlord-tenant law and property disputes
- Personal injury and negligence claims
- Insurance coverage disputes

Your communication style is:
- Confident and authoritative without being arrogant
- Client-focused with clear explanations of complex legal concepts
- Strategically minded, always considering long-term case implications
- Professional courtesy balanced with firm legal positions
- Precise legal language with appropriate citations when relevant

You draft findings letters that clients and opposing counsel respect for their thoroughness and legal acumen.
"""

class EmailGenerator:
    """Service to generate a professional findings letter and format it for multiple outputs."""

    def __init__(self, client: OpenAI):
        """Initializes the EmailGenerator with an OpenAI client and Jinja2 environment."""
        if not client:
            raise ValueError("An OpenAI client is required for EmailGenerator.")
        self.client = client
        
        # Construct an absolute path to the templates directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(script_dir, '..', 'assets', 'templates')
        
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        self.quality_validator = QualityValidator()

    def generate_email_and_analysis_docs(self, analysis: CombinedAnalysis) -> EmailResponse:
        """
        Orchestrates the multi-step generation of a findings letter and related documents.
        """
        try:
            # Step 1: Generate each section of the letter sequentially
            executive_summary = self._generate_executive_summary(analysis)
            legal_framework = self._generate_legal_framework(analysis)
            case_analysis_narrative = self._generate_case_analysis_narrative(analysis, legal_framework)
            strategic_recommendations = self._generate_strategic_recommendations(analysis, case_analysis_narrative)

            # Step 2: Assemble the final letter model
            findings_letter_model = self._assemble_professional_letter(
                analysis=analysis,
                executive_summary=executive_summary,
                legal_framework=legal_framework,
                case_analysis_narrative=case_analysis_narrative,
                strategic_recommendations=strategic_recommendations
            )
            
            if not findings_letter_model:
                analysis.errors.append(AnalysisError(source="EmailGenerator", error_message="Failed to assemble the final findings letter."))
                # You might want to return a more informative error message here
                return EmailResponse(findings_letter=None, download_links=[], case_analysis_text="Error: Could not generate findings letter.")

            # Step 3: Validate the quality of the generated letter
            quality_score = self.quality_validator.validate_findings_letter(findings_letter_model)

            # Step 4: Render HTML from Jinja2 template
            template = self.jinja_env.get_template("findings_email.jinja2")
            html_content = template.render(letter=findings_letter_model)

            # Step 5: Format the detailed case analysis text document
            case_analysis_text = self._format_case_analysis(analysis)

            # Step 6: Create downloadable files
            download_links = self._create_downloadable_files(
                html_content=html_content,
                case_analysis_text=case_analysis_text,
                analysis_obj=analysis
            )
            
            return EmailResponse(
                findings_letter=findings_letter_model,
                download_links=download_links,
                case_analysis_text=case_analysis_text,
                quality_score=quality_score
            )
        except TemplateError as e:
            error_message = f"Jinja2 template error: {e}"
            analysis.errors.append(AnalysisError(source="EmailGenerator", error_message=error_message))
            return EmailResponse(findings_letter=None, download_links=[], case_analysis_text=error_message)
        except Exception as e:
            error_message = f"An unexpected error occurred in EmailGenerator: {e}"
            analysis.errors.append(AnalysisError(source="EmailGenerator", error_message=error_message))
            return EmailResponse(findings_letter=None, download_links=[], case_analysis_text=error_message)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type((RateLimitError, APIError, APITimeoutError)))
    def _make_openai_request(self, prompt: str, model: str = "gpt-4o") -> Optional[str]:
        """Makes a request to the OpenAI API with retry logic."""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": SENIOR_ATTORNEY_PERSONA}, {"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except (RateLimitError, APIError, APITimeoutError) as e:
            print(f"OpenAI API Error: {e}. Retrying...")
            raise
        except Exception as e:
            print(f"An unexpected error occurred during OpenAI request: {e}")
            return None

    def _generate_executive_summary(self, analysis: CombinedAnalysis) -> str:
        """Generates a client-friendly executive summary."""
        prompt = f"""
        Analyze the provided case data and draft a concise, client-friendly executive summary (2-3 sentences) for a findings letter.

        Your summary must:
        - Be professional, confident, and clear.
        - Avoid legal jargon.
        - Focus on the client's perspective and the case's potential.
        - Use sophisticated but accessible language.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the text for the executive summary.
        """
        return self._make_openai_request(prompt) or "Executive summary could not be generated."

    def _generate_legal_framework(self, analysis: CombinedAnalysis) -> str:
        """Generates a client-friendly legal framework section."""
        prompt = f"""
        Based on the case type and summary, articulate the relevant legal framework in a client-friendly narrative.

        Your response should:
        - Explain the core legal principles in simple, professional terms.
        - Avoid overly technical jargon and case citations.
        - Structure the output as a clean, readable paragraph.

        Case Context:
        {analysis.model_dump_json(indent=2)}
        
        Generate only the text for the legal framework.
        """
        return self._make_openai_request(prompt) or "Legal framework could not be determined."

    def _generate_case_analysis_narrative(self, analysis: CombinedAnalysis, legal_framework: str) -> str:
        """Generates a client-friendly case analysis narrative."""
        prompt = f"""
        Synthesize the case facts and legal framework into a clear, client-friendly narrative.

        Instructions:
        - Structure with headings for **Our Analysis**, **Strengths of Your Case**, and **Potential Challenges**.
        - Explain the analysis in a way a non-lawyer can easily understand.
        - Maintain a professional, confident, and client-focused tone.
        - Ensure the output is a narrative, not a technical legal memo.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Established Legal Framework:
        {legal_framework}
        
        Generate only the text for the case analysis narrative.
        """
        return self._make_openai_request(prompt) or "Case analysis could not be generated."

    def _generate_strategic_recommendations(self, analysis: CombinedAnalysis, case_analysis_narrative: str) -> str:
        """Generates client-friendly strategic recommendations."""
        prompt = f"""
        Based on the analysis, formulate clear, scannable, and actionable strategic recommendations for the client.

        Instructions:
        - Present recommendations as a numbered list.
        - Use clear, imperative language (e.g., "We recommend you take the following actions...").
        - Keep each recommendation concise and easy to understand.
        - DO NOT use bullet points.

        Case Analysis Narrative:
        {case_analysis_narrative}
        
        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the text for the strategic recommendations, formatted as a numbered list.
        """
        return self._make_openai_request(prompt) or "Strategic recommendations could not be formulated."

    def _assemble_professional_letter(self, analysis: CombinedAnalysis, executive_summary: str, legal_framework: str, case_analysis_narrative: str, strategic_recommendations: str) -> Optional[EnhancedFindingsLetter]:
        """Assembles the final EnhancedFindingsLetter model from the generated components."""
        try:
            client_initials = "".join([name[0] for name in (analysis.intake_analysis.client_name or "Client").split()])
            case_reference = f"BR-{client_initials}-{datetime.now().strftime('%Y%m%d')}"
            
            header = FindingsHeader(
                date=datetime.now().strftime('%Y-%m-%d'),
                client_name=analysis.intake_analysis.client_name or "Client",
                case_reference=case_reference
            )

            footer = FindingsFooter(
                attorney_name=analysis.intake_analysis.attorney_name or "Assigned Attorney",
                firm_name="Bernhardt Riley PLLC",
                contact_info="Tel: (000) 000-0000 | email@example.com"
            )
            
            letter = EnhancedFindingsLetter(
                header=header,
                reviewed_documents=[doc.document_title for doc in analysis.case_analyses if doc.document_title],
                background_summary=analysis.intake_analysis.case_summary,
                review_summary=case_analysis_narrative,
                assessment_challenges=analysis.legal_assessment.potential_challenges if analysis.legal_assessment else [],
                next_steps_recommendations=analysis.legal_assessment.recommended_actions if analysis.legal_assessment else [],
                demand_letter_section=analysis.demand_letter_evaluation,
                footer=footer
            )
            return letter
        except Exception as e:
            print(f"Error assembling professional letter: {e}")
            return None

    def _format_case_analysis(self, analysis: CombinedAnalysis) -> str:
        """Formats the combined analysis into a human-readable text document."""
        doc_lines = ["# Case Analysis & AI-Generated Insights"]

        if analysis.intake_analysis:
            ia = analysis.intake_analysis
            doc_lines.extend([
                "\n## Intake Analysis",
                f"- **Client Name:** {ia.client_name or 'N/A'}",
                f"- **Attorney Name:** {ia.attorney_name or 'N/A'}",
                f"- **Case Type:** {ia.case_type or 'N/A'}",
                f"- **Urgency:** {ia.urgency_level or 'N/A'}",
                f"\n**Case Summary:**\n{ia.case_summary or 'No summary provided.'}",
                f"\n**Priorities:**\n" + ("\n".join(f"  - {p}" for p in ia.client_priorities) if ia.client_priorities else "  - N/A"),
                f"\n**Desired Outcomes:**\n" + ("\n".join(f"  - {o}" for o in ia.desired_outcomes) if ia.desired_outcomes else "  - N/A")
            ])
        
        doc_lines.append("\n## Individual Document Analysis")
        if analysis.case_analyses:
            for i, doc_analysis in enumerate(analysis.case_analyses):
                doc_lines.append(f"\n### {i+1}. {doc_analysis.document_title or 'Untitled Document'}")
                doc_lines.append(f"**Source Document:** {doc_analysis.document_title or 'N/A'}")
                doc_lines.append(f"**Summary:** {doc_analysis.summary or 'No summary available.'}")
                if doc_analysis.timeline_events:
                    doc_lines.append("**Key Events:**")
                    for event in doc_analysis.timeline_events:
                        doc_lines.append(f"  - **{event.get('date', 'Date N/A')}:** {event.get('event', 'N/A')} (Source: {doc_analysis.document_title})")
        else:
            doc_lines.append("No individual documents were analyzed.")

        if analysis.legal_assessment:
            la = analysis.legal_assessment
            doc_lines.append("\n## Final Legal Assessment")
            doc_lines.append(f"- **Claim Viability:** {la.claim_viability or 'Not assessed.'}")
            doc_lines.append(f"- **Overall Evidence Strength:** {la.overall_evidence_strength or 'Not assessed.'}")

        return "\n".join(doc_lines)

    def _create_downloadable_files(self, html_content: str, case_analysis_text: str, analysis_obj: CombinedAnalysis) -> List[DownloadLink]:
        """Creates downloadable files: .eml for the findings letter and .txt for the case analysis."""
        client_name = "client"
        if analysis_obj.intake_analysis and analysis_obj.intake_analysis.client_name:
            client_name_raw = analysis_obj.intake_analysis.client_name
            client_name = "".join(c for c in client_name_raw if c.isalnum() or c in " _-").rstrip()

        subject = f"Legal Findings for {client_name}"
        eml_content = f"Subject: {subject}\nContent-Type: text/html\n\n{html_content}"
        eml_base64 = base64.b64encode(eml_content.encode()).decode()
        txt_base64 = base64.b64encode(case_analysis_text.encode()).decode()

        return [
            DownloadLink(file_name=f"Findings_{client_name}.eml", url=f"data:message/rfc822;base64,{eml_base64}"),
            DownloadLink(file_name="Case Analysis.txt", url=f"data:text/plain;base64,{txt_base64}"),
        ]