import base64
import re
import os
from typing import List, Optional, Dict
from openai import OpenAI, RateLimitError, APIError, APITimeoutError
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from backend.utils.data_models import (
    CaseAnalysisResult,
    EmailResponse,
    EnhancedFindingsLetter,
    DownloadLink,
    AnalysisError,
    FindingsHeader,
    FindingsFooter,
    GeneratedLetter,
)
from backend_logic.quality_validator import QualityValidator

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
        
        # Use robust absolute path resolution that works from any execution context
        # Find project root by looking for characteristic files
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = current_dir
        
        # Navigate up until we find the project root (contains app.py and backend/ directory)
        while project_root != '/' and not (
            os.path.exists(os.path.join(project_root, 'app.py')) and
            os.path.exists(os.path.join(project_root, 'backend'))
        ):
            project_root = os.path.dirname(project_root)
        
        if project_root == '/':
            # Fallback: assume we're in the project root
            project_root = os.getcwd()
        
        # Construct template directory path from project root
        template_dir = os.path.join(project_root, 'backend', 'assets', 'templates')
        
        print(f"EMAIL GENERATOR: Project root: {project_root}")
        print(f"EMAIL GENERATOR: Template directory: {template_dir}")
        print(f"EMAIL GENERATOR: Template directory exists: {os.path.exists(template_dir)}")
        
        if not os.path.exists(template_dir):
            raise FileNotFoundError(f"Template directory not found: {template_dir}")
        
        # List available templates for verification
        available_files = os.listdir(template_dir)
        print(f"EMAIL GENERATOR: Available template files: {available_files}")
        
        # Verify required templates exist
        required_templates = ['findings_email.jinja2', 'document_appendix.jinja2']
        missing_templates = [t for t in required_templates if t not in available_files]
        if missing_templates:
            raise FileNotFoundError(f"Required templates missing: {missing_templates}")
        
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        print(f"EMAIL GENERATOR: ✅ Jinja2 environment initialized successfully")
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
            media_summary = self._clean_ai_response(
                self._generate_media_summary(analysis, persona=CONTINUING_LETTER_PERSONA)
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
            
            # Step 9: Generate video analysis appendix if video data is available
            video_analysis_appendix = self._clean_ai_response(
                self._generate_video_analysis_appendix(analysis, persona=CONTINUING_LETTER_PERSONA)
            )

            # Assemble the final GeneratedLetter
            return GeneratedLetter(
                executive_summary=executive_summary,
                background_summary=background_summary,
                analysis_and_position=analysis_and_position,
                media_summary=media_summary,
                video_analysis_appendix=video_analysis_appendix,
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
                media_summary="<p>Error generating media summary.</p>",
                video_analysis_appendix="",
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
        Implements graceful degradation to ensure documents are always generated.
        """
        try:
            # Ensure analysis has required components or create fallbacks
            self._ensure_analysis_completeness(analysis)
            
            # DEBUG: Log the data structure being passed to templates
            print(f"EMAIL GENERATOR: Starting template rendering")
            print(f"EMAIL GENERATOR: Analysis has intake_analysis: {analysis.intake_analysis is not None}")
            if analysis.intake_analysis:
                print(f"EMAIL GENERATOR: Client name: {analysis.intake_analysis.client_name}")
                print(f"EMAIL GENERATOR: Attorney name: {analysis.intake_analysis.attorney_name}")
                print(f"EMAIL GENERATOR: Case summary length: {len(analysis.intake_analysis.case_summary or '') if analysis.intake_analysis.case_summary else 0}")

            # Generate the structured letter using the new process (with built-in error handling)
            generated_letter = self.generate_findings(analysis)
            
            # DEBUG: Log generated letter structure
            print(f"EMAIL GENERATOR: Generated letter sections:")
            print(f"  - Executive summary length: {len(generated_letter.executive_summary) if generated_letter.executive_summary else 0}")
            print(f"  - Background summary length: {len(generated_letter.background_summary) if generated_letter.background_summary else 0}")
            print(f"  - Analysis section length: {len(generated_letter.analysis_and_position) if generated_letter.analysis_and_position else 0}")
            
            # Step 2: Render main letter HTML from Jinja2 template
            print(f"EMAIL GENERATOR: Attempting to load main template 'findings_email.jinja2'...")
            try:
                main_template = self.jinja_env.get_template("findings_email.jinja2")
                print(f"EMAIL GENERATOR: ✅ Main template loaded successfully")
            except Exception as e:
                print(f"EMAIL GENERATOR: ❌ Failed to load main template: {e}")
                # List available templates for debugging
                try:
                    available_templates = self.jinja_env.list_templates()
                    print(f"EMAIL GENERATOR: Available templates: {available_templates}")
                except Exception as list_error:
                    print(f"EMAIL GENERATOR: Could not list templates: {list_error}")
                raise
            
            template_context = {
                'analysis': analysis,
                'generated_letter': generated_letter,
                'current_date': datetime.now().strftime('%B %d, %Y')
            }
            print(f"EMAIL GENERATOR: Rendering main template with context keys: {list(template_context.keys())}")
            main_html_content = main_template.render(results=template_context, current_date=template_context['current_date'])
            print(f"EMAIL GENERATOR: ✅ Main template rendered successfully, length: {len(main_html_content)}")

            # Step 3: Render appendix HTML from Jinja2 template
            print(f"EMAIL GENERATOR: Attempting to load appendix template 'document_appendix.jinja2'...")
            try:
                appendix_template = self.jinja_env.get_template("document_appendix.jinja2")
                print(f"EMAIL GENERATOR: ✅ Appendix template loaded successfully")
            except Exception as e:
                print(f"EMAIL GENERATOR: ❌ Failed to load appendix template: {e}")
                raise
                
            appendix_html_content = appendix_template.render(results=template_context, current_date=template_context['current_date'])
            print(f"EMAIL GENERATOR: ✅ Appendix template rendered successfully, length: {len(appendix_html_content)}")

            return {
                "main_letter": main_html_content,
                "appendix": appendix_html_content
            }
            
        except TemplateError as e:
            error_message = f"Jinja2 template error: {e}"
            print(f"EMAIL GENERATOR: ❌ Template error: {error_message}")
            analysis.errors.append(AnalysisError(source="EmailGenerator", error_message=error_message))
            
            # Generate fallback documents that are still usable
            fallback_content = self._generate_fallback_documents(analysis, error_message)
            return fallback_content
            
        except Exception as e:
            error_message = f"An unexpected error occurred in EmailGenerator: {e}"
            print(f"EMAIL GENERATOR: ❌ Unexpected error: {error_message}")
            analysis.errors.append(AnalysisError(source="EmailGenerator", error_message=error_message))
            
            # Generate fallback documents that are still usable
            fallback_content = self._generate_fallback_documents(analysis, error_message)
            return fallback_content

    def _ensure_analysis_completeness(self, analysis: CaseAnalysisResult) -> None:
        """Ensures analysis has all required components for document generation."""
        from backend.utils.validators import create_fallback_legal_assessment, create_fallback_demand_letter_evaluation
        
        # Ensure we have an intake analysis
        if not analysis.intake_analysis:
            print("EMAIL GENERATOR: ⚠️  Missing intake_analysis, creating basic fallback")
            from backend.utils.data_models import EnhancedIntakeAnalysis
            analysis.intake_analysis = EnhancedIntakeAnalysis(
                client_name="Client",
                attorney_name="Attorney",
                case_summary="Legal matter requiring analysis",
                case_type="Legal Case",
                urgency_level="Standard"
            )
        
        # Ensure we have legal assessment
        if not analysis.legal_assessment:
            print("EMAIL GENERATOR: ⚠️  Missing legal_assessment, creating fallback")
            from backend.utils.data_models import LegalAssessment
            analysis.legal_assessment = LegalAssessment.model_validate(create_fallback_legal_assessment())
        
        # Ensure we have demand letter evaluation
        if not analysis.demand_letter_evaluation:
            print("EMAIL GENERATOR: ⚠️  Missing demand_letter_evaluation, creating fallback")
            from backend.utils.data_models import DemandLetterEvaluation
            analysis.demand_letter_evaluation = DemandLetterEvaluation.model_validate(create_fallback_demand_letter_evaluation())
        
        # Ensure we have at least one analyzed document
        if not analysis.analyzed_documents:
            print("EMAIL GENERATOR: ⚠️  No analyzed documents, creating placeholder")
            from backend.utils.data_models import AnalyzedDocument
            analysis.analyzed_documents = [
                AnalyzedDocument(
                    filename="case_documents.pdf",
                    document_type="Legal Documents",
                    inferred_title="Case Documentation",
                    summary="Legal documents provided for case analysis",
                    key_information="Documentation under review",
                    relevance_to_case="Supporting materials for legal analysis"
                )
            ]

    def _generate_fallback_documents(self, analysis: CaseAnalysisResult, error_message: str) -> Dict[str, str]:
        """Generates basic HTML documents when template rendering fails."""
        client_name = "Client"
        if analysis.intake_analysis and analysis.intake_analysis.client_name:
            client_name = analysis.intake_analysis.client_name
        
        current_date = datetime.now().strftime('%B %d, %Y')
        
        # Generate a basic but professional fallback letter
        main_letter = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Legal Findings Letter - {client_name}</title>
            <style>
                body {{ font-family: Times, serif; margin: 40px; line-height: 1.6; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .content {{ margin: 20px 0; }}
                .error-notice {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; margin: 20px 0; border-radius: 5px; }}
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
            
            <div class="content">
                <div class="error-notice">
                    <strong>Notice:</strong> This document was generated using fallback processing due to a system issue.
                    While all case information has been preserved, the formatting may be simplified.
                </div>
                
                <h2>Executive Summary</h2>
                <p>We have completed our analysis of your legal matter. Our review included examination of the provided
                documentation and assessment of your case's legal position.</p>
                
                <h2>Analysis Summary</h2>
                <p>Based on our review, we have assessed the merits of your case and identified potential legal strategies.
                Our analysis takes into account the relevant legal standards and the specific facts of your situation.</p>
                
                <h2>Recommendations</h2>
                <p>We recommend proceeding with a detailed strategy session to discuss the specific findings and
                develop an appropriate course of action for your case.</p>
                
                <h2>Next Steps</h2>
                <p>Please contact our office to schedule a follow-up meeting where we can discuss our findings in detail
                and answer any questions you may have about your case.</p>
                
                <p style="margin-top: 40px;">
                    <strong>Sincerely,</strong><br>
                    {analysis.intake_analysis.attorney_name if analysis.intake_analysis and analysis.intake_analysis.attorney_name else 'Your Legal Team'}<br>
                    Bernhardt Riley PLLC
                </p>
            </div>
        </body>
        </html>
        """
        
        # Generate a basic appendix
        appendix = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Case Analysis Appendix - {client_name}</title>
            <style>
                body {{ font-family: Times, serif; margin: 40px; line-height: 1.6; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .error-notice {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; margin: 20px 0; border-radius: 5px; }}
                h1 {{ color: #2c3e50; }}
                h2 {{ color: #34495e; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Case Analysis Appendix</h1>
                <p><strong>Date:</strong> {current_date}</p>
                <p><strong>Client:</strong> {client_name}</p>
            </div>
            
            <div class="error-notice">
                <strong>Notice:</strong> This appendix was generated using fallback processing.
                Detailed analysis information is preserved but may require manual review.
            </div>
            
            <h2>Document Review</h2>
            <p>The following documents were included in our analysis:</p>
            <ul>
                {"".join([f"<li>{doc.filename} - {doc.document_type}</li>" for doc in analysis.analyzed_documents]) if analysis.analyzed_documents else "<li>Case documents provided for review</li>"}
            </ul>
            
            <h2>Technical Details</h2>
            <p>For technical details about this case analysis, please contact our office directly.</p>
            
            <p><strong>Error Details (for internal reference):</strong> {error_message}</p>
        </body>
        </html>
        """
        
        print("EMAIL GENERATOR: ✅ Generated fallback documents successfully")
        return {
            "main_letter": main_letter,
            "appendix": appendix
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

    def _generate_media_summary(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates a summary of media analysis with HTML formatting."""
        if not analysis.transcripted_media and not analysis.video_insights:
            return ""

        prompt = f"""
        Based on the media analysis provided, create a professional summary of the key findings from audio and video files.

        Your summary should:
        - Integrate findings from both audio and video into a cohesive narrative.
        - Highlight crucial evidence, statements, or events from the media.
        - Explain the relevance of the media to the case.
        - Be formatted as HTML paragraphs using `<p>` tags.

        Case Context:
        {analysis.model_dump_json(indent=2)}

        Generate only the HTML-formatted media analysis summary text.
        """
        result = self._make_openai_request(prompt, persona)
        return result or "<p>Media analysis summary could not be generated.</p>"

    def _generate_video_analysis_appendix(self, analysis: CaseAnalysisResult, persona: str) -> str:
        """Generates a detailed video analysis appendix explaining the significance of video content to the case.
        
        Handles three scenarios as per video preservation plan:
        1. Full Insights: Use complete video.insights data
        2. Persisted Insights: Use video.insights_summary with truncation notice
        3. No Data: Graceful failure
        """
        if not analysis.video_insights:
            return ""

        # Prepare video data for prompt, handling different data scenarios
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
            
            # Check for persisted insights scenario (insights preserved due to token limits)
            if hasattr(video_insight, 'insights_gcs_uri') and video_insight.insights_gcs_uri:
                print(f"EMAIL GENERATOR: Using preserved insights summary for {video_insight.file_name}")
                has_preserved_data = True
                # Use the summary instead of full insights
                if hasattr(video_insight, 'insights_summary') and video_insight.insights_summary:
                    video_data["insights"] = video_insight.insights_summary
                    video_data["_data_source"] = "summary"  # Mark for truncation notice
                else:
                    video_data["insights"] = "Video analysis summary not available"
                    video_data["_data_source"] = "unavailable"
            else:
                # Full insights scenario - use complete data as before
                video_data["insights"] = video_insight.insights
                video_data["_data_source"] = "full"
            
            video_data_for_prompt.append(video_data)

        # Build the prompt with appropriate data
        prompt = f"""
        Based on the video analysis data provided, create a comprehensive "Video Analysis Appendix" section that provides detailed analysis of video evidence and its significance to the case.

        Your video analysis appendix must:
        - Create a section titled "Video Analysis Appendix" using an `<h4>` tag.
        - For each video file analyzed, provide a detailed summary of the video insights and any available transcript content.
        - Critically explain the significance of each video's content as it relates to the overall case context, including how it supports or challenges the client's position.
        - Connect video evidence to key facts, legal claims, and case strategy identified in the intake form and document analysis.
        - Analyze specific objects, labels, text annotations, and visual evidence captured in the videos and their legal relevance.
        - If transcripts are available, highlight key statements or dialogue and explain their importance to the case.
        - Use professional legal language appropriate for client communications.
        - Be formatted cleanly using HTML tags (`<p>`, `<h4>`, `<ul>`, `<li>`) for optimal presentation.
        - Address the client directly using 'you' and 'your' throughout the analysis.
        {
            "- Include a note that some video analysis content is summarized due to data size limitations where applicable."
            if has_preserved_data else ""
        }

        Available Video Analysis Data:
        {video_data_for_prompt}

        Overall Case Context for Relevance Analysis:
        Client Name: {analysis.intake_analysis.client_name if analysis.intake_analysis else "Not provided"}
        Case Type: {analysis.intake_analysis.case_type if analysis.intake_analysis else "Not provided"}
        Case Summary: {analysis.intake_analysis.case_summary if analysis.intake_analysis else "Not provided"}
        Legal Claims: {analysis.intake_analysis.legal_claims if analysis.intake_analysis else "Not provided"}

        Generate only the HTML-formatted video analysis appendix content, including the section header.
        """
        
        result = self._make_openai_request(prompt, persona)
        
        # If we have preserved data, add a notice to the result
        if has_preserved_data and result:
            truncation_notice = '<p><em>Note: Full analysis was truncated due to size. Summary is provided above.</em></p>'
            # Insert the notice after the header but before the main content
            if '<h4>' in result and '</h4>' in result:
                header_end = result.find('</h4>') + 5
                result = result[:header_end] + '\n' + truncation_notice + '\n' + result[header_end:]
            else:
                result = truncation_notice + '\n' + result
        
        return result or ""

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
        """Formats the combined analysis into a professional HTML document."""
        client_name = "Client"
        if analysis.intake_analysis and analysis.intake_analysis.client_name:
            client_name = analysis.intake_analysis.client_name
        
        current_date = datetime.now().strftime('%B %d, %Y')
        
        # Build the HTML document with professional styling
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Case Analysis Report - {client_name}</title>
            <style>
                body {{
                    font-family: 'Times New Roman', Times, serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 40px 20px;
                    background: #fff;
                }}
                
                .header {{
                    text-align: center;
                    border-bottom: 3px solid #2c3e50;
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                }}
                
                .header h1 {{
                    color: #2c3e50;
                    margin: 0;
                    font-size: 28px;
                    font-weight: bold;
                }}
                
                .header .subtitle {{
                    color: #7f8c8d;
                    font-size: 16px;
                    margin-top: 5px;
                }}
                
                .metadata {{
                    display: flex;
                    justify-content: space-between;
                    background: #f8f9fa;
                    padding: 15px;
                    border-left: 4px solid #3498db;
                    margin-bottom: 30px;
                    border-radius: 0 5px 5px 0;
                }}
                
                .metadata div {{
                    flex: 1;
                }}
                
                .metadata strong {{
                    color: #2c3e50;
                }}
                
                h2 {{
                    color: #2c3e50;
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 8px;
                    margin-top: 40px;
                    margin-bottom: 20px;
                    font-size: 20px;
                }}
                
                h3 {{
                    color: #34495e;
                    margin-top: 30px;
                    margin-bottom: 15px;
                    font-size: 16px;
                }}
                
                .info-grid {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 20px;
                    margin-bottom: 20px;
                }}
                
                .info-item {{
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                    border-left: 3px solid #e74c3c;
                }}
                
                .info-item strong {{
                    color: #2c3e50;
                    display: block;
                    margin-bottom: 5px;
                }}
                
                .case-summary {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 5px;
                    border-left: 4px solid #27ae60;
                    margin: 20px 0;
                }}
                
                .document-item {{
                    background: #fdfdfd;
                    border: 1px solid #e9ecef;
                    border-radius: 5px;
                    padding: 20px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                
                .document-header {{
                    background: #3498db;
                    color: white;
                    padding: 10px 15px;
                    margin: -20px -20px 15px -20px;
                    border-radius: 5px 5px 0 0;
                    font-weight: bold;
                }}
                
                .document-meta {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 15px;
                    margin-bottom: 15px;
                    padding: 10px;
                    background: #f8f9fa;
                    border-radius: 3px;
                }}
                
                .document-content {{
                    margin-top: 15px;
                }}
                
                .document-content h4 {{
                    color: #2c3e50;
                    margin-top: 20px;
                    margin-bottom: 10px;
                    font-size: 14px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                
                .document-content p {{
                    margin-bottom: 10px;
                    text-align: justify;
                }}
                
                .assessment-section {{
                    background: #fff3cd;
                    border: 1px solid #ffeaa7;
                    padding: 20px;
                    border-radius: 5px;
                    margin-top: 30px;
                }}
                
                .assessment-section h2 {{
                    color: #856404;
                    border-bottom: 2px solid #ffc107;
                }}
                
                .assessment-grid {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 20px;
                    margin-top: 15px;
                }}
                
                .assessment-item {{
                    background: white;
                    padding: 15px;
                    border-radius: 5px;
                    border-left: 3px solid #ffc107;
                }}
                
                ul {{
                    padding-left: 20px;
                }}
                
                li {{
                    margin-bottom: 8px;
                }}
                
                .no-content {{
                    color: #6c757d;
                    font-style: italic;
                    text-align: center;
                    padding: 20px;
                    background: #f8f9fa;
                    border-radius: 5px;
                }}
                
                @media print {{
                    body {{
                        padding: 20px;
                    }}
                    .header {{
                        border-bottom: 2px solid #000;
                    }}
                    h2 {{
                        border-bottom: 1px solid #000;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Case Analysis & AI-Generated Insights</h1>
                <div class="subtitle">Comprehensive Document Review Report</div>
            </div>
            
            <div class="metadata">
                <div><strong>Client:</strong> {client_name}</div>
                <div><strong>Date Generated:</strong> {current_date}</div>
                <div><strong>Report Type:</strong> Document Analysis</div>
            </div>
        """
        
        # Add intake analysis section
        if analysis.intake_analysis:
            ia = analysis.intake_analysis
            html_content += f"""
            <h2>Intake Analysis</h2>
            <div class="info-grid">
                <div class="info-item">
                    <strong>Client Name</strong>
                    {ia.client_name or 'N/A'}
                </div>
                <div class="info-item">
                    <strong>Attorney Name</strong>
                    {ia.attorney_name or 'N/A'}
                </div>
                <div class="info-item">
                    <strong>Case Type</strong>
                    {ia.case_type or 'N/A'}
                </div>
                <div class="info-item">
                    <strong>Urgency Level</strong>
                    {ia.urgency_level or 'N/A'}
                </div>
            </div>
            
            <div class="case-summary">
                <h3>Case Summary</h3>
                <p>{ia.case_summary or 'No summary provided.'}</p>
            </div>
            """
            
            if ia.client_priorities:
                html_content += f"""
                <h3>Client Priorities</h3>
                <ul>
                    {"".join(f"<li>{priority}</li>" for priority in ia.client_priorities)}
                </ul>
                """
            
            if ia.desired_outcomes:
                html_content += f"""
                <h3>Desired Outcomes</h3>
                <ul>
                    {"".join(f"<li>{outcome}</li>" for outcome in ia.desired_outcomes)}
                </ul>
                """
        
        # Add document review section
        html_content += """
        <h2>Document Review Appendix</h2>
        """
        
        if analysis.analyzed_documents:
            for i, doc in enumerate(analysis.analyzed_documents):
                html_content += f"""
                <div class="document-item">
                    <div class="document-header">
                        {i+1}. {doc.inferred_title or 'Untitled Document'}
                    </div>
                    
                    <div class="document-meta">
                        <div><strong>Source File:</strong> {doc.filename}</div>
                        <div><strong>Document Type:</strong> {doc.document_type}</div>
                    </div>
                    
                    <div class="document-content">
                        <h4>Summary</h4>
                        <p>{doc.summary}</p>
                        
                        <h4>Key Information</h4>
                        <p>{doc.key_information}</p>
                        
                        <h4>Relevance to Case</h4>
                        <p>{doc.relevance_to_case}</p>
                    </div>
                </div>
                """
        else:
            html_content += """
            <div class="no-content">
                No individual documents were analyzed.
            </div>
            """
        
        # Add legal assessment section
        if analysis.legal_assessment:
            la = analysis.legal_assessment
            html_content += f"""
            <div class="assessment-section">
                <h2>Final Legal Assessment</h2>
                <div class="assessment-grid">
                    <div class="assessment-item">
                        <strong>Claim Viability</strong>
                        <p>{la.claim_viability or 'Not assessed.'}</p>
                    </div>
                    <div class="assessment-item">
                        <strong>Overall Evidence Strength</strong>
                        <p>{la.overall_evidence_strength or 'Not assessed.'}</p>
                    </div>
                </div>
            </div>
            """
        
        html_content += """
        </body>
        </html>
        """
        
        return html_content

    def _create_downloadable_files(self, html_content: str, case_analysis_text: str, analysis_obj: CaseAnalysisResult) -> List[DownloadLink]:
        """Creates downloadable files: .eml for the findings letter and HTML for the case analysis."""
        client_name = "client"
        attorney_name = "Attorney"
        
        if analysis_obj.intake_analysis:
            if analysis_obj.intake_analysis.client_name:
                client_name_raw = analysis_obj.intake_analysis.client_name
                client_name = "".join(c for c in client_name_raw if c.isalnum() or c in " _-").rstrip()
            if analysis_obj.intake_analysis.attorney_name:
                attorney_name = analysis_obj.intake_analysis.attorney_name

        # Create proper .eml file with full email headers
        current_date = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
        if not current_date.endswith(' +0000'):  # Handle timezone if not present
            current_date = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        
        subject = f"Legal Findings Letter - {client_name}"
        
        # Create proper .eml content with MIME headers
        eml_content = f"""From: {attorney_name} <attorney@bernhardtriley.com>
To: {client_name} <client@example.com>
Subject: {subject}
Date: {current_date}
MIME-Version: 1.0
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 8bit
Message-ID: <{datetime.now().strftime('%Y%m%d%H%M%S')}.findings@bernhardtriley.com>
X-Mailer: Legal Document Analysis Portal

{html_content}"""

        # Create HTML case analysis document
        case_analysis_html = self._format_case_analysis(analysis_obj)
        
        eml_base64 = base64.b64encode(eml_content.encode('utf-8')).decode()
        html_base64 = base64.b64encode(case_analysis_html.encode('utf-8')).decode()

        return [
            DownloadLink(file_name=f"Findings_{client_name}.eml", url=f"data:message/rfc822;base64,{eml_base64}"),
            DownloadLink(file_name=f"Case_Analysis_{client_name}.html", url=f"data:text/html;base64,{html_base64}"),
        ]