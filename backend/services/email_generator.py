import base64
import re
from typing import List, Optional
from openai import OpenAI
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateError
from datetime import datetime
from backend.utils.data_models import (
    CombinedAnalysis,
    EmailResponse,
    EnhancedFindingsLetter,
    DownloadLink,
    AnalysisError
)

class EmailGenerator:
    """Service to generate a professional findings letter and format it for multiple outputs."""
    def __init__(self, client: OpenAI):
        """Initializes the EmailGenerator with an OpenAI client and Jinja2 environment."""
        if not client:
            raise ValueError("An OpenAI client is required for EmailGenerator.")
        self.client = client
        self.jinja_env = Environment(
            loader=FileSystemLoader("backend/assets/templates"),
            autoescape=select_autoescape(['html', 'xml'])
        )

    def generate_email_and_analysis_docs(self, analysis: CombinedAnalysis) -> EmailResponse:
        """
        Generates a findings letter, a detailed case analysis document, and formats them for multiple outputs.
        """
        try:
            # Generate AI-powered findings letter
            findings_letter_model = self._generate_letter_content_from_ai(analysis)
            if not findings_letter_model:
                analysis.errors.append(AnalysisError(source="EmailGenerator", error_message="AI failed to generate letter content."))
                return EmailResponse(findings_letter=None, download_links=[], case_analysis_text=None)

            # Render HTML from Jinja2 template
            template = self.jinja_env.get_template("findings_email.jinja2")
            html_content = template.render(letter=findings_letter_model)

            # Format the detailed case analysis text document
            case_analysis_text = self._format_case_analysis(analysis)

            # Create downloadable files (.eml for email, .txt for analysis)
            download_links = self._create_downloadable_files(
                html_content=html_content,
                case_analysis_text=case_analysis_text,
                analysis_obj=analysis
            )
            
            return EmailResponse(
                findings_letter=findings_letter_model,
                download_links=download_links,
                case_analysis_text=case_analysis_text
            )
        except TemplateError as e:
            error_message = f"Jinja2 template error: {e}"
            analysis.errors.append(AnalysisError(source="EmailGenerator", error_message=error_message))
            return EmailResponse(findings_letter=None, download_links=[], case_analysis_text=None)
        except Exception as e:
            error_message = f"An unexpected error occurred in EmailGenerator: {e}"
            analysis.errors.append(AnalysisError(source="EmailGenerator", error_message=error_message))
            return EmailResponse(findings_letter=None, download_links=[], case_analysis_text=None)

    def _generate_letter_content_from_ai(self, analysis: CombinedAnalysis) -> Optional[EnhancedFindingsLetter]:
        """Uses AI to generate the full content of the findings letter."""
        prompt = self._build_findings_letter_prompt(analysis)
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}],
                response_format={"type": "json_object"}
            )
            # Assuming the response is a JSON string that can be parsed into the model
            if response.choices and response.choices[0].message.content:
                json_content = response.choices[0].message.content
                return EnhancedFindingsLetter.model_validate_json(json_content)
            return None
        except Exception as e:
            print(f"Error calling OpenAI for letter generation: {e}")
            return None

    def _build_findings_letter_prompt(self, analysis: CombinedAnalysis) -> str:
        """Builds the comprehensive prompt for generating the findings letter."""
        return (
            "SYSTEM\n"
            "You are a senior litigation attorney drafting a client-facing findings letter.\n"
            "Return **one—and only one—valid JSON object** that conforms exactly to the\n"
            "EnhancedFindingsLetter schema supplied below.\n"
            "• Do **NOT** wrap the JSON in markdown fences.\n"
            "• Do **NOT** add, rename, or delete keys.\n"
            "• Do **NOT** emit explanatory text, comments, or markdown—only the JSON.\n\n"
            "==========================\n"
            "INPUT DATA (read-only)\n"
            f"{{analysis.model_dump_json(indent=2)}}\n"
            "==========================\n\n"
            "==========================\n"
            "SCHEMA: EnhancedFindingsLetter\n"
            "{\n"
            '  "header": {\n'
            '    "date":                "YYYY-MM-DD",\n'
            '    "client_name":         "Client Name",\n'
            '    "client_address":      "Client Address",\n'
            '    "case_reference":      "Case Reference"\n'
            "  },\n"
            '  "reviewed_documents":    ["Document 1 Title"],\n'
            '  "background_summary":    "…",\n'
            '  "review_summary":        "…",\n'
            '  "assessment_challenges": [{\n'
            '    "category":            "Challenge Category",\n'
            '    "description":         "Challenge Description",\n'
            '    "mitigation_strategy": "Mitigation Strategy",\n'
            '    "confidence_score":    0.00\n'
            "  }],\n"
            '  "next_steps_recommendations": ["Recommendation 1"],\n'
            '  "demand_letter_section": {\n'
            '    "is_appropriate":      true,\n'
            '    "reasoning":           "…",\n'
            '    "potential_outcomes":  ["Outcome 1"],\n'
            '    "relevant_statutes":   ["Statute 1"]\n'
            "  },\n"
            '  "footer": {\n'
            '    "attorney_name":       "Attorney Name",\n'
            '    "firm_name":           "Firm Name",\n'
            '    "firm_address":        "Firm Address",\n'
            '    "contact_info":        "Contact Info"\n'
            "  }\n"
            "}\n"
            "==========================\n\n"
            "CONSTRUCTION RULES\n"
            "1. **Header**\n"
            "   • \"date\": today’s date (America/Chicago) in ISO-8601.\n"
            "   • \"client_name\": pull from `intake_analysis.client_name` (if absent, use \"Client\").\n"
            "   • \"client_address\": placeholder \"TBD\".\n"
            "   • \"case_reference\": format “BR-[client-initials]-[YYYYMMDD]”.\n\n"
            "2. **reviewed_documents**\n"
            "   • Populate with each `case_analyses[i].document_title`, preserving order.\n\n"
            "3. **background_summary**\n"
            "   • Start from `intake_analysis.case_summary`.\n"
            "   • Enrich with key facts (timeline, parties, amounts) and asserted legal claims.\n"
            "   • 150–250 words; one coherent paragraph.\n\n"
            "4. **review_summary**\n"
            "   • **Synthesize**, don’t list. Merge insights from every\n"
            "     `case_analyses[i].summary` into a cohesive narrative (120–200 words).\n\n"
            "5. **assessment_challenges**\n"
            "   • For every `legal_assessment.potential_challenges[*]` create an object:\n"
            "     – \"category\": copy the challenge type.\n"
            "     – \"description\": concise (≤40 words).\n"
            "     – \"mitigation_strategy\": from `challenge.mitigation` or craft logically.\n"
            "     – \"confidence_score\": map `challenge.risk_level` → float\n"
            "       (High = 0.85, Med = 0.60, Low = 0.30).\n"
            "   • Sort descending by confidence_score.\n\n"
            "6. **next_steps_recommendations**\n"
            "   • List all `legal_assessment.recommended_actions[*]` in plain-English, each ≤25 words.\n\n"
            "7. **demand_letter_section**\n"
            "   • Mirror `demand_letter_evaluation.is_appropriate`.\n"
            "   • If false, keep \"is_appropriate\": false and set other sub-fields to empty strings/arrays.\n"
            "   • If true, fill all sub-fields:\n"
            "     – \"reasoning\": paraphrase `demand_letter_evaluation.reason`.\n"
            "     – \"potential_outcomes\": bullet every `demand_letter_evaluation.outcomes[*]\\`.\n"
            "     – \"relevant_statutes\": cite statute numbers/titles (no full text).\n\n"
            "8. **footer**\n"
            "   • \"attorney_name\": `intake_analysis.attorney`.\n"
            "   • \"firm_name\": placeholder \"Bernhardt Riley PLLC\".\n"
            "   • \"firm_address\": placeholder \"TBD\".\n"
            "   • \"contact_info\": placeholder \"Tel: (000) 000-0000 | email@example.com\".\n\n"
            "VALIDATION\n"
            "• Ensure the final output parses as JSON.\n"
            "• All strings must be double-quoted.\n"
            "• confidence_score must be numeric (two decimals).\n\n"
            "BEGIN."
        )

    def _format_case_analysis(self, analysis: CombinedAnalysis) -> str:
        """Formats the combined analysis into a human-readable text document."""
        doc_lines = ["# Case Analysis & AI-Generated Insights"]

        # 1. Intake Analysis Section
        if analysis.intake_analysis:
            doc_lines.append("\n## Intake Analysis")
            ia = analysis.intake_analysis
            doc_lines.append(f"- **Client Name:** {ia.client_name or 'N/A'}")
            doc_lines.append(f"- **Attorney Name:** {ia.attorney_name or 'N/A'}")
            doc_lines.append(f"- **Case Type:** {ia.case_type or 'N/A'}")
            doc_lines.append(f"- **Urgency:** {ia.urgency_level or 'N/A'}")
            doc_lines.append(f"\n**Case Summary:**\n{ia.case_summary or 'No summary provided.'}")
            doc_lines.append(f"\n**Priorities:**\n" + "\n".join(f"  - {p}" for p in ia.client_priorities) if ia.client_priorities else "  - N/A")
            doc_lines.append(f"\n**Desired Outcomes:**\n" + "\n".join(f"  - {o}" for o in ia.desired_outcomes) if ia.desired_outcomes else "  - N/A")

        # 2. Individual Document Analysis Section
        doc_lines.append("\n## Individual Document Analysis")
        if analysis.case_analyses:
            for i, doc_analysis in enumerate(analysis.case_analyses):
                doc_lines.append(f"\n### {i+1}. {doc_analysis.document_title or 'Untitled Document'}")
                doc_lines.append(f"**Source Document:** {doc_analysis.document_title or 'N/A'}")
                doc_lines.append(f"**Summary:** {doc_analysis.summary or 'No summary available.'}")
                if doc_analysis.timeline_events:
                    doc_lines.append("**Key Events:**")
                    for event in doc_analysis.timeline_events:
                        doc_lines.append(f"  - **{event.get('date', 'Date N/A')}:** {event.get('description', 'N/A')} (Source: {doc_analysis.document_title})")
        else:
            doc_lines.append("No individual documents were analyzed.")

        # 3. Final Legal Assessment Section
        if analysis.legal_assessment:
            doc_lines.append("\n## Final Legal Assessment")
            la = analysis.legal_assessment
            doc_lines.append(f"- **Claim Viability:** {la.claim_viability or 'Not assessed.'}")
            doc_lines.append(f"- **Overall Evidence Strength:** {la.overall_evidence_strength or 'Not assessed.'}")
            if la.potential_challenges:
                doc_lines.append("**Potential Challenges:**")
                for chal in la.potential_challenges:
                    doc_lines.append(f"  - **{chal.category}:** {chal.description} (Confidence: {chal.confidence_score * 100}%)")
            if la.recommended_actions:
                doc_lines.append("**Recommended Actions:**\n" + "\n".join(f"  - {act}" for act in la.recommended_actions))

        # 4. Demand Letter Evaluation Section
        if analysis.demand_letter_evaluation:
            doc_lines.append("\n## Demand Letter Evaluation")
            dle = analysis.demand_letter_evaluation
            eval_text = "Recommended" if dle.is_appropriate else "Not Recommended"
            doc_lines.append(f"- **Evaluation:** {eval_text}")
            doc_lines.append(f"- **Reasoning:** {dle.reasoning or 'No reasoning provided.'}")
        
        return "\n".join(doc_lines)

    def _create_downloadable_files(self, html_content: str, case_analysis_text: str, analysis_obj: CombinedAnalysis) -> List[DownloadLink]:
        """Creates downloadable files: .eml for the findings letter and .txt for the case analysis."""
        client_name = "client"
        if analysis_obj.intake_analysis and analysis_obj.intake_analysis.client_name:
            client_name_raw = analysis_obj.intake_analysis.client_name
            client_name = "".join(c for c in client_name_raw if c.isalnum() or c in " _-").rstrip()

        # 1. EML format for the findings letter
        subject = f"Legal Findings for {client_name}"
        eml_content = f"Subject: {subject}\nContent-Type: text/html\n\n{html_content}"
        eml_base64 = base64.b64encode(eml_content.encode()).decode()
        
        # 2. TXT format for the case analysis document
        txt_base64 = base64.b64encode(case_analysis_text.encode()).decode()

        return [
            DownloadLink(file_name=f"Findings_{client_name}.eml", url=f"data:message/rfc822;base64,{eml_base64}"),
            DownloadLink(file_name="Case Analysis.txt", url=f"data:text/plain;base64,{txt_base64}"),
        ]