import base64
from typing import List
from openai import OpenAI
from utils.data_models import CombinedAnalysis, EmailResponse, FindingsLetter, DownloadLink

class EmailGenerator:
    """
    Service to generate a professional findings letter and format it for multiple outputs.
    """
    def __init__(self, client: OpenAI):
        """
        Initializes the EmailGenerator with the OpenAI client.
        """
        self.client = client

    def generate_findings_letter(self, analysis: CombinedAnalysis) -> EmailResponse:
        """
        Generates a findings letter, creates downloadable files, and returns a structured response.
        """
        prompt = self._build_email_prompt(analysis)
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            findings_content = response.choices[0].message.content
            
            # Simple parsing of the response, assuming "Subject:" and "Body:" markers
            subject = findings_content.split("Subject:")[1].split("Body:")[0].strip()
            body = findings_content.split("Body:")[1].strip()
            
            findings_letter = FindingsLetter(
                subject=subject,
                body=body,
                recipients=[analysis.intake_analysis.client_name] if analysis.intake_analysis.client_name else []
            )
            
            download_links = self._create_downloadable_files(findings_letter, analysis)
            
            return EmailResponse(
                findings_letter=findings_letter,
                download_links=download_links
            )
            
        except Exception as e:
            print(f"Error generating findings letter: {e}")
            # Fallback to a simpler response in case of an error
            findings_letter = FindingsLetter(
                subject=f"Legal Analysis Findings - {analysis.intake_analysis.client_name}",
                body="Could not generate findings letter. Please review the case documents.",
                recipients=[analysis.intake_analysis.client_name] if analysis.intake_analysis.client_name else []
            )
            download_links = self._create_downloadable_files(findings_letter, analysis)
            return EmailResponse(
                findings_letter=findings_letter,
                download_links=download_links,
            )

    def _build_email_prompt(self, analysis: CombinedAnalysis) -> str:
        """
        Builds the prompt for the AI to generate the findings letter.
        """
        case_summaries = "\n".join([f"- {ca.document_title}: {ca.summary}" for ca in analysis.case_analyses])
        key_entities = ", ".join(list(set(entity for ca in analysis.case_analyses for entity in ca.key_entities)))
        timeline_events = "\n".join([f"- {event['date']}: {event['description']}" for ca in analysis.case_analyses for event in ca.timeline_events])

        return f"""
        Generate a professional findings letter based on the following case analysis.
        The output should be structured with a clear "Subject:" and "Body:".

        Client Name: {analysis.intake_analysis.client_name}
        Attorney Name: {analysis.intake_analysis.attorney_name}
        Case Summary: {analysis.intake_analysis.case_summary}
        Key Facts from Intake: {', '.join(analysis.intake_analysis.key_facts)}
        
        Summaries of Case Documents:
        {case_summaries}
        
        Key Entities from Documents: {key_entities}
        Timeline of Events:
        {timeline_events}

        Please generate the email now.
        """

    def _create_downloadable_files(self, letter: FindingsLetter, analysis: CombinedAnalysis) -> List[DownloadLink]:
        """
        Creates downloadable files in .eml and .txt formats.
        """
        client_name = analysis.intake_analysis.client_name or "client"
        # EML format
        eml_content = f"Subject: {letter.subject}\n\n{letter.body}"
        eml_base64 = base64.b64encode(eml_content.encode()).decode()
        
        # TXT format
        txt_base64 = base64.b64encode(letter.body.encode()).decode()

        return [
            DownloadLink(file_name=f"Findings_{client_name}.eml", url=f"data:message/rfc822;base64,{eml_base64}"),
            DownloadLink(file_name=f"Analysis_{client_name}.txt", url=f"data:text/plain;base64,{txt_base64}"),
        ]