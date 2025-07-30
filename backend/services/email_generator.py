import base64
from typing import Dict, Any

class EmailGenerator:
    def create_findings_email(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        # This service will generate the final email findings letter,
        # create the downloadable files (.eml and .txt),
        # and return them in the format the frontend expects.

        case_info = analysis_result.get("case_info", {})
        client_name = case_info.get("clientName", "Client")
        attorney_name = case_info.get("attorneyName", "Attorney")
        case_reference = case_info.get("caseReference", "CASE-001")
        summary = analysis_result.get("summary", "No summary available.")

        # Create EML content
        eml_content = f"""From: {attorney_name} <no-reply@bernhardt-riley.com>
To: {client_name}
Subject: Legal Analysis Findings - {case_reference}

{summary}
"""
        eml_base64 = base64.b64encode(eml_content.encode()).decode()

        # Create TXT content
        txt_content = summary
        txt_base64 = base64.b64encode(txt_content.encode()).decode()

        return {
            "downloadLinks": {
                "findingsLetter": f"data:message/rfc822;base64,{eml_base64}",
                "caseAnalysis": f"data:text/plain;base64,{txt_base64}",
            },
            "emailDetails": {
                "emlFileName": f"Findings_{case_reference}.eml",
                "txtFileName": f"Analysis_{case_reference}.txt",
            },
        }