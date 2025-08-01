import base64
import re
import os
from typing import List, Optional, Dict, Any
from openai import OpenAI, RateLimitError, APIError, APITimeoutError
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from ..utils.data_models import (
    CaseAnalysisResult,
    EmailResponse,
    EnhancedFindingsLetter,
    DownloadLink,
    AnalysisError,
    AnalyzedDocument,
    LegalAssessment,
    DemandLetterEvaluation,
    FindingsHeader,
    FindingsFooter,
    QualityScore,
    GeneratedLetter,
)
from .quality_validator import QualityValidator

# Constants
CLIENT_DIRECTED_PERSONA = """
You are a senior litigation attorney at a prestigious law firm, writing a formal findings letter TO YOUR CLIENT.

MANDATORY INSTRUCTIONS:
1.  **Direct Address:** Every sentence must be written in the second person ('you', 'your'). Start the letter with 'Dear [Client Name],' and maintain this direct address throughout.
2.  **Client-Centric Language:** You MUST write as if speaking directly to the client.
    *   CORRECT: "You have a strong case because your evidence shows..."
    *   INCORRECT: "The client has a strong case because their evidence shows..."
3.  **Professional Tone:** Maintain an authoritative, confident, and client-centered tone. Explain complex legal concepts clearly and provide actionable guidance. Your analysis should be comprehensive and accessible, demonstrating legal expertise while empowering your client's decision-making.
"""

CONTINUING_LETTER_PERSONA = """
MANDATORY INSTRUCTION: You are an attorney CONTINUING a findings letter that is already in progress. DO NOT add any greetings (like "Dear Client"), closings, or signatures. You must continue the letter seamlessly from the previous section. Your tone must remain consistent with a formal legal document directed to a client, using the second person ('you', 'your').
"""

STRICT_FORMAT_ENFORCEMENT = """
CRITICAL FORMATTING REQUIREMENTS:
1.  **HTML Only:** Use ONLY HTML tags for all formatting. Never use Markdown (`**bold**`, `*italic*`).
2.  **Clean Output:** Generate clean HTML suitable for direct client presentation. DO NOT include `'''html'''` or any other code fences in your response.
3.  **Paragraphs, Not Lists:** Generate flowing, narrative paragraphs wrapped in `<p>` tags unless a list is explicitly requested.
"""

NARRATIVE_PARAGRAPH_ENFORCEMENT = """
MANDATORY REQUIREMENT: The entire output for this section MUST be written as flowing narrative paragraphs, with each paragraph enclosed in `<p>` tags. You are FORBIDDEN from using numbered lists, bullet points, or `<ol>` and `<li>` tags. Combine all points into a cohesive narrative using transitional phrases. Failure to comply will result in an error.
"""

# Legacy constant maintained for backward compatibility
SENIOR_ATTORNEY_PERSONA = CLIENT_DIRECTED_PERSONA + "\n\n" + STRICT_FORMAT_ENFORCEMENT

class EmailGenerator:
    """Service to generate a professional findings letter and format it for multiple outputs using a multi-stage generation process."""

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

    def _clean_ai_response(self, content: str) -> str:
        """Enhanced post-processing to clean AI responses of markdown, malformed HTML, and other artifacts."""
        if not content:
            return ""
            
        # Strip markdown code fences with various language hints
        cleaned = re.sub(r'^```[a-zA-Z]*\n?', '', content, flags=re.MULTILINE)
        cleaned = re.sub(r'```$', '', cleaned, flags=re.MULTILINE)
        
        # Remove markdown formatting that might have leaked through
        cleaned = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', cleaned)  # **bold** -> <strong>
        cleaned = re.sub(r'\*(.*?)\*', r'<em>\1</em>', cleaned)  # *italic* -> <em>
        
        # Fix common HTML formatting issues
        cleaned = re.sub(r'<p>\s*<p>', '<p>', cleaned)  # Remove duplicate opening <p> tags
        cleaned = re.sub(r'</p>\s*</p>', '</p>', cleaned)  # Remove duplicate closing </p> tags
        cleaned = re.sub(r'<p>\s*</p>', '', cleaned)  # Remove empty paragraphs
        
        # Ensure proper paragraph wrapping for content that might be missing tags
        if cleaned and not cleaned.strip().startswith('<'):
            # If content doesn't start with an HTML tag, wrap in paragraphs
            paragraphs = cleaned.split('\n\n')
            cleaned_paragraphs = []
            for para in paragraphs:
                para = para.strip()
                if para and not para.startswith('<'):
                    cleaned_paragraphs.append(f'<p>{para}</p>')
                elif para:
                    cleaned_paragraphs.append(para)
            cleaned = '\n'.join(cleaned_paragraphs)
        
        # Clean up excessive whitespace
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)  # Multiple newlines to double
        cleaned = cleaned.strip()
        
        print(f"EMAIL GENERATOR DEBUG: Cleaned AI response length: {len(cleaned)}")
        
        return cleaned

    def generate_findings(self, analysis: CaseAnalysisResult) -> GeneratedLetter:
        """
        Main function to generate the structured GeneratedLetter using multi-stage generation process.
        """
        try:
            # Step 1: Generate executive summary with the initial client-directed persona
            executive_summary = self._clean_ai_response(
                self._generate_executive_summary(analysis, persona=CLIENT_DIRECTED_PERSONA)
            )
            
            # Step 2: Generate all subsequent sections with the continuing persona
            background_summary = self._clean_ai_response(
                self._generate_background_summary(analysis, persona=CONTINUING_LETTER_PERSONA)
            )
            analysis_and_position = self._clean_ai_response(
                self._generate_analysis_section(analysis, persona=CONTINUING_LETTER_PERSONA)
            )
            strengths = self._clean_ai_response(
                self._generate_strengths(analysis, persona=CONTINUING_LETTER_PERSONA)
            )
            challenges = self._clean_ai_response(
                self._generate_challenges(analysis, persona=CONTINUING_LETTER_PERSONA)
            )
            recommendations = self._clean_ai_response(
                self._generate_recommendations(analysis, persona=CONTINUING_LETTER_PERSONA)
            )
            next_steps = self._clean_ai_response(
                self._generate_next_steps(analysis, persona=CONTINUING_LETTER_PERSONA)
            )
            closing_paragraph = self._clean_ai_response(
                self._generate_closing_paragraph(analysis, persona=CONTINUING_LETTER_PERSONA)
            )

            # Assemble the final GeneratedLetter
            return GeneratedLetter(
                executive_summary=executive_summary,
                background_summary=background_summary,
                analysis_and_position=analysis_and_position,
                strengths=strengths,
                challenges=challenges,
                recommendations=recommendations,
                next_steps=next_steps,
                closing_paragraph=closing_paragraph
            )
            
        except Exception as e:
            print(f"Error in generate_findings: {e}")
            # Return a basic structure with error messages
            return GeneratedLetter(
                executive_summary="<p>Error generating executive summary.</p>",
                background_summary="<p>Error generating background summary.</p>",
                analysis_and_position="<p>Error generating analysis section.</p>",
                strengths="<p>Error generating strengths assessment.</p>",
                challenges="<p>Error generating challenges assessment.</p>",
                recommendations="<p>Error generating recommendations.</p>",
                next_steps="<p>Error generating next steps.</p>",
                closing_paragraph="<p>We remain committed to advancing your interests and achieving the best possible outcome for your case.</p>"
            )

    def generate_email_and_analysis_docs(self, analysis: CaseAnalysisResult) -> Dict[str, str]:
        """
        Generates two separate HTML documents: main letter and appendix.
        Returns a dictionary with 'main_letter' and 'appendix' keys.
        """
        try:
            # DEBUG: Log the data structure being passed to templates
            print(f"EMAIL GENERATOR DEBUG: Starting template rendering")
            print(f"EMAIL GENERATOR DEBUG: Analysis has intake_analysis: {analysis.intake_analysis is not None}")
            if analysis.intake_analysis:
                print(f"EMAIL GENERATOR DEBUG: Client name: {analysis.intake_analysis.client_name}")
                print(f"EMAIL GENERATOR DEBUG: Attorney name: {analysis.intake_analysis.attorney_name}")
                print(f"EMAIL GENERATOR DEBUG: Case summary length: {len(analysis.intake_analysis.case_summary or '') if analysis.intake_analysis.case_summary else 0}")

            # Generate the structured letter using the new process
            generated_letter = self.generate_findings(analysis)
            
            # DEBUG: Log generated letter structure
            print(f"EMAIL GENERATOR DEBUG: Generated letter sections:")
            print(f"  - Executive summary length: {len(generated_letter.executive_summary) if generated_letter.executive_summary else 0}")
            print(f"  - Background summary length: {len(generated_letter.background_summary) if generated_letter.background_summary else 0}")
            print(f"  - Analysis section length: {len(generated_letter.analysis_and_position) if generated_letter.analysis_and_position else 0}")
            
            # Step 2: Render main letter HTML from Jinja2 template
            main_template = self.jinja_env.get_template("findings_email.jinja2")
            template_context = {
                'analysis': analysis,
                'generated_letter': generated_letter,
                'current_date': datetime.now().strftime('%B %d, %Y')
            }
            print(f"EMAIL GENERATOR DEBUG: Rendering main template with context keys: {list(template_context.keys())}")
            main_html_content = main_template.render(results=template_context, current_date=template_context['current_date'])
            print(f"EMAIL GENERATOR DEBUG: Main template rendered successfully, length: {len(main_html_content)}")

            # Step 3: Render appendix HTML from Jinja2 template
            appendix_template = self.jinja_env.get_template("document_appendix.jinja2")
            appendix_html_content = appendix_template.render(results=template_context, current_date=template_context['current_date'])
            print(f"EMAIL GENERATOR DEBUG: Appendix template rendered successfully, length: {len(appendix_html_content)}")

            return {
                "main_letter": main_html_content,
                "appendix": appendix_html_content
            }
            
        except TemplateError as e:
            error_message = f"Jinja2 template error: {e}"
            analysis.errors.append(AnalysisError(source="EmailGenerator", error_message=error_message))
            return {
                "main_letter": f"<html><body><h1>Template Error</h1><p>{error_message}</p></body></html>",
                "appendix": f"<html><body><h1>Template Error</h1><p>{error_message}</p></body></html>"
            }
        except Exception as e:
            error_message = f"An unexpected error occurred in EmailGenerator: {e}"
            analysis.errors.append(AnalysisError(source="EmailGenerator", error_message=error_message))
            return {
                "main_letter": f"<html><body><h1>Error</h1><p>{error_message}</p></body></html>",
                "appendix": f"<html><body><h1>Error</h1><p>{error_message}</p></body></html>"
            }

    def generate_email_and_analysis_docs_legacy(self, analysis: CaseAnalysisResult) -> EmailResponse:
        """
        Legacy method maintained for backward compatibility.
        Orchestrates the multi-step generation of a findings letter and related documents.
        """
        try:
            # Generate the structured letter using the new process
            generated_letter = self.generate_findings(analysis)
            
            # Step 2: Assemble the final letter model (legacy format)
            findings_letter_model = self._assemble_professional_letter_from_generated(
                analysis=analysis,
                generated_letter=generated_letter
            )
            
            if not findings_letter_model:
                analysis.errors.append(AnalysisError(source="EmailGenerator", error_message="Failed to assemble the final findings letter."))
                return EmailResponse(findings_letter=None, download_links=[], case_analysis_text="Error: Could not generate findings letter.")

            # Step 3: Validate the quality of the generated letter
            quality_score = self.quality_validator.validate_findings_letter(findings_letter_model)

            # Step 4: Render HTML from Jinja2 template
            template = self.jinja_env.get_template("findings_email.jinja2")
            html_content = template.render(results={'analysis': analysis, 'generated_letter': generated_letter})

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
    def _make_openai_request(self, prompt: str, persona: str, model: str = "gpt-4o") -> Optional[str]:
        """Makes a request to the OpenAI API with retry logic, using a specified persona."""
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
            print(f"OpenAI API Error: {e}. Retrying...")
            raise
        except Exception as e:
            print(f"An unexpected error occurred during OpenAI request: {e}")
            return None

    def _generate_executive_summary(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates a professional executive summary with HTML formatting."""
        prompt = f"""
        Analyze the provided case data and draft a concise, professional executive summary (2-3 sentences) for the beginning of a findings letter. This is the first section, so it should include the greeting 'Dear {analysis.intake_analysis.client_name},'.

        Your summary must:
        - Be professional, confident, and clear.
        - Focus on the key findings and recommendations.
        - Use sophisticated legal language appropriate for client communications.
        - Be formatted as HTML paragraphs using `<p>` tags.
        - Address the client directly using 'you' and 'your'.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the HTML-formatted executive summary text.
        """
        result = self._make_openai_request(prompt, persona)
        return result or "<p>Executive summary could not be generated.</p>"

    def _generate_background_summary(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates background summary from intake analysis with HTML formatting."""
        prompt = f"""
        Based on the intake analysis provided, create a professional background summary that provides context for the legal matter. This section continues the letter.

        Your summary should:
        - Provide essential context from the client intake.
        - Summarize the key facts and circumstances.
        - Set the stage for the legal analysis that follows.
        - Use professional, client-appropriate language, addressing the client as 'you'.
        - Be formatted as HTML paragraphs using `<p>` tags.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the HTML-formatted background summary text.
        """
        result = self._make_openai_request(prompt, persona)
        return result or "<p>Background summary could not be generated.</p>"

    def _generate_analysis_section(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates comprehensive legal analysis and position with HTML formatting."""
        prompt = f"""
        Convert the document analysis data into sophisticated, flowing legal prose that presents our analysis and legal position for your case.

        Your analysis should:
        - Transform the structured data into elegant, professional legal prose.
        - Present a coherent legal analysis and your legal position.
        - Demonstrate legal expertise and strategic thinking.
        - Use sophisticated legal language while remaining accessible to you.
        - Be formatted as multiple HTML paragraphs using `<p>` tags.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the HTML-formatted analysis and legal position text.
        """
        result = self._make_openai_request(prompt, persona)
        return result or "<p>Legal analysis and position could not be generated.</p>"

    def _generate_strengths(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates case strengths assessment with HTML formatting."""
        prompt = f"""
        Based on the case analysis, identify and articulate the key strengths of your position in sophisticated legal prose.

        Your strengths assessment should:
        - Identify the most compelling aspects of your case.
        - Present each strength in sophisticated, flowing legal prose.
        - Demonstrate confidence in your position.
        - Use professional legal language, focusing on evidence, legal precedent, and strategic advantages.
        - Be formatted as HTML paragraphs using `<p>` tags.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the HTML-formatted strengths assessment text.
        """
        result = self._make_openai_request(prompt, persona)
        return result or "<p>Case strengths assessment could not be generated.</p>"

    def _generate_challenges(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates potential challenges assessment with HTML formatting."""
        prompt = f"""
        Based on the case analysis, identify and address potential challenges or risks to your position in sophisticated legal prose.

        Your challenges assessment should:
        - Honestly assess potential weaknesses or risks.
        - Present challenges in a balanced, professional manner.
        - Demonstrate strategic awareness and preparedness.
        - Suggest how challenges might be addressed or mitigated.
        - Be formatted as HTML paragraphs using `<p>` tags.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the HTML-formatted challenges assessment text.
        """
        result = self._make_openai_request(prompt, persona)
        return result or "<p>Challenges assessment could not be generated.</p>"

    def _generate_recommendations(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates strategic recommendations as flowing narrative paragraphs."""
        prompt = f"""
        {NARRATIVE_PARAGRAPH_ENFORCEMENT}

        Based on the comprehensive case analysis, formulate clear, actionable strategic recommendations for YOUR case in flowing narrative prose.

        Your recommendations must:
        - Be written as continuous, flowing paragraphs that read like a professional letter.
        - Connect ideas with transitional phrases to create a cohesive narrative.
        - Address YOU directly throughout (e.g., "We recommend that you...", "Your best course of action...").
        - Use sophisticated legal language while maintaining readability.
        - Be formatted ONLY with `<p>` tags—absolutely NO list tags.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate strategic recommendations as flowing, professional narrative paragraphs. NO LISTS.
        """
        result = self._make_openai_request(prompt, persona)
        return result or "<p>Strategic recommendations could not be generated.</p>"

    def _generate_next_steps(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates immediate next steps as flowing narrative paragraphs."""
        prompt = f"""
        {NARRATIVE_PARAGRAPH_ENFORCEMENT}

        Based on the case analysis and strategic recommendations, identify the immediate next steps for YOUR case in flowing narrative prose.

        Your next steps must:
        - Be written as continuous, flowing paragraphs addressing YOU directly.
        - Connect actions with transitional phrases to create a coherent narrative.
        - Include specific timelines woven naturally into the prose.
        - Present a logical sequence of actions without using list formatting.
        - Be formatted ONLY with `<p>` tags—absolutely NO list tags.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate immediate next steps as flowing, professional narrative paragraphs. NO LISTS.
        """
        result = self._make_openai_request(prompt, persona)
        return result or "<p>Next steps could not be generated.</p>"

    def _generate_closing_paragraph(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates a professional closing paragraph for the findings letter."""
        prompt = f"""
        Based on the comprehensive case analysis, create a professional closing paragraph that concludes the findings letter appropriately.

        Your closing paragraph should:
        - Provide a confident, professional conclusion to the findings letter.
        - Reinforce our firm's commitment to your case.
        - Invite your questions and ongoing communication.
        - Be formatted as HTML paragraphs using `<p>` tags.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the HTML-formatted closing paragraph text.
        """
        result = self._make_openai_request(prompt, persona)
        return result or "<p>We remain committed to advancing your interests and achieving the best possible outcome for your case. Please contact our office with any questions or concerns.</p>"

    def _assemble_professional_letter_from_generated(self, analysis: CaseAnalysisResult, generated_letter: GeneratedLetter) -> Optional[EnhancedFindingsLetter]:
        """Assembles the final EnhancedFindingsLetter model from the new GeneratedLetter structure."""
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
            
            # Combine the new generated content into the legacy format
            combined_review_summary = f"""
            {generated_letter.analysis_and_position}
            
            <h3>Strengths of Your Case</h3>
            {generated_letter.strengths}
            
            <h3>Potential Challenges</h3>
            {generated_letter.challenges}
            """
            
            letter = EnhancedFindingsLetter(
                header=header,
                reviewed_documents=[doc.inferred_title for doc in analysis.analyzed_documents if doc.inferred_title],
                background_summary=generated_letter.background_summary,
                review_summary=combined_review_summary,
                assessment_challenges=analysis.legal_assessment.potential_challenges if analysis.legal_assessment else [],
                next_steps_recommendations=analysis.legal_assessment.recommended_actions if analysis.legal_assessment else [],
                demand_letter_section=analysis.demand_letter_evaluation,
                footer=footer
            )
            return letter
        except Exception as e:
            print(f"Error assembling professional letter from generated content: {e}")
            return None


    def _format_case_analysis(self, analysis: CaseAnalysisResult) -> str:
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
        
        doc_lines.append("\n## Document Review Appendix")
        if analysis.analyzed_documents:
            for i, doc in enumerate(analysis.analyzed_documents):
                doc_lines.append(f"\n### {i+1}. {doc.inferred_title or 'Untitled Document'}")
                doc_lines.append(f"**Source File:** {doc.filename}")
                doc_lines.append(f"**Document Type:** {doc.document_type}")
                doc_lines.append(f"**Summary:** {doc.summary}")
                doc_lines.append(f"**Key Information:**\n{doc.key_information}")
                doc_lines.append(f"**Relevance to Case:** {doc.relevance_to_case}")
        else:
            doc_lines.append("No individual documents were analyzed.")

        if analysis.legal_assessment:
            la = analysis.legal_assessment
            doc_lines.append("\n## Final Legal Assessment")
            doc_lines.append(f"- **Claim Viability:** {la.claim_viability or 'Not assessed.'}")
            doc_lines.append(f"- **Overall Evidence Strength:** {la.overall_evidence_strength or 'Not assessed.'}")

        return "\n".join(doc_lines)

    def _create_downloadable_files(self, html_content: str, case_analysis_text: str, analysis_obj: CaseAnalysisResult) -> List[DownloadLink]:
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