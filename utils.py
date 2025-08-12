"""Utility functions for the Legal Document Analysis Portal UI components."""

from typing import Any


def generate_case_analysis_html(case_analysis_result: Any) -> str:
    """Generate HTML representation of the case analysis result.

    Args:
    ----
        case_analysis_result: The complete case analysis result

    Returns:
    -------
        HTML string containing the formatted case analysis

    """
    try:
        client_name = "Unknown Client"
        case_type = "Legal Matter"

        if case_analysis_result.intake_analysis:
            client_name = getattr(case_analysis_result.intake_analysis, "client_name", client_name)
            case_type = getattr(case_analysis_result.intake_analysis, "case_type", case_type)

        # Generate basic HTML structure
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Case Analysis - {client_name}</title>
            <style>
                body {{ font-family: 'Times New Roman', serif; line-height: 1.6; color: #333; margin: 40px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .section {{ margin-bottom: 25px; }}
                .section h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
                .document-item {{ border: 1px solid #ddd; margin-bottom: 15px; padding: 15px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Comprehensive Case Analysis</h1>
                <p><strong>Client:</strong> {client_name}</p>
                <p><strong>Case Type:</strong> {case_type}</p>
            </div>

            <div class="section">
                <h2>Intake Analysis Summary</h2>
                <p>{getattr(case_analysis_result.intake_analysis, 'case_summary', 'No summary available') if case_analysis_result.intake_analysis else 'No intake analysis available'}</p>
            </div>

            <div class="section">
                <h2>Document Analysis</h2>
        """

        # Add document analyses
        if case_analysis_result.analyzed_documents:
            for doc in case_analysis_result.analyzed_documents:
                filename = getattr(doc, "file_name", "Unknown Document")
                summary = getattr(doc, "summary", "No summary available")
                html_content += f"""
                <div class="document-item">
                    <h3>{filename}</h3>
                    <p><strong>Summary:</strong> {summary}</p>
                </div>
                """
        else:
            html_content += "<p>No documents were analyzed.</p>"

        html_content += """
            </div>

            <div class="section">
                <h2>Legal Assessment</h2>
        """

        # Add legal assessment if available
        if case_analysis_result.legal_assessment:
            html_content += f"<p><strong>Case Type:</strong> {getattr(case_analysis_result.legal_assessment, 'case_type', 'Not specified')}</p>"
            html_content += f"<p><strong>Claim Viability:</strong> {getattr(case_analysis_result.legal_assessment, 'claim_viability', 'Not assessed')}</p>"
            html_content += f"<p><strong>Evidence Strength:</strong> {getattr(case_analysis_result.legal_assessment, 'overall_evidence_strength', 'Not assessed')}</p>"
        else:
            html_content += "<p>Legal assessment is in progress.</p>"

        html_content += """
            </div>
        </body>
        </html>
        """

        return html_content

    except Exception as e:
        # Return a basic error page
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Case Analysis Error</title></head>
        <body>
            <h1>Case Analysis</h1>
            <p>Error generating case analysis: {str(e)}</p>
            <p>Please contact support if this issue persists.</p>
        </body>
        </html>
        """
