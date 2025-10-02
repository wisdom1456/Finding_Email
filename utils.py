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

        # Extract timeline from analyzed documents
        case_timeline = []
        if case_analysis_result.analyzed_documents:
            for doc in case_analysis_result.analyzed_documents:
                if hasattr(doc, "timeline_events") and doc.timeline_events:
                    for event in doc.timeline_events:
                        case_timeline.append(
                            {
                                "date": event.get("date", "Unknown"),
                                "event": event.get("description", "Event recorded"),
                                "source": getattr(doc, "file_name", None)
                                or getattr(doc, "filename", "Unknown"),
                            }
                        )

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
                .subsection {{ margin-left: 20px; margin-bottom: 15px; }}
                .list-item {{ margin-bottom: 8px; padding-left: 10px; border-left: 3px solid #3498db; }}
                .party-box {{ border: 1px solid #ddd; padding: 10px; margin-bottom: 10px; background-color: #f8f9fa; }}
                .assessment-box {{ border: 1px solid #27ae60; padding: 15px; margin-bottom: 15px; background-color: #e8f8f5; }}
                .warning-box {{ border: 1px solid #e74c3c; padding: 15px; margin-bottom: 15px; background-color: #fadbd8; }}
                .timeline {{ margin: 20px 0; }}
                .timeline-item {{ position: relative; padding: 15px 20px; margin-bottom: 15px; border-left: 3px solid #3498db; background-color: #f8f9fa; }}
                .timeline-date {{ font-weight: bold; color: #2c3e50; margin-bottom: 5px; }}
                .timeline-source {{ font-size: 0.9em; color: #7f8c8d; margin-top: 5px; font-style: italic; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Comprehensive Case Analysis</h1>
                <p><strong>Client:</strong> {client_name}</p>
                <p><strong>Case Type:</strong> {case_type}</p>
            </div>

            <div class="section">
                <h2>Case Overview</h2>
                <p>{getattr(case_analysis_result.intake_analysis, 'case_summary', 'No case summary available') if case_analysis_result.intake_analysis else 'No intake analysis available'}</p>
            </div>
        """

        # Add Timeline section if available
        if case_timeline:
            html_content += """
            <div class="section">
                <h2>📅 Case Timeline</h2>
                <div class="timeline">
            """
            for event in case_timeline:
                html_content += f"""
                <div class="timeline-item">
                    <div class="timeline-date">{event['date']}</div>
                    <div>{event['event']}</div>
                    <div class="timeline-source">Source: {event['source']}</div>
                </div>
                """
            html_content += """
                </div>
            </div>
            """

        # Add Key Facts section
        if case_analysis_result.intake_analysis and hasattr(
            case_analysis_result.intake_analysis, "key_facts"
        ):
            key_facts = getattr(case_analysis_result.intake_analysis, "key_facts", [])
            if key_facts:
                html_content += """
            <div class="section">
                <h2>Key Facts</h2>
                <div class="subsection">
                """
                for fact in key_facts:
                    html_content += f'<div class="list-item">• {fact}</div>'
                html_content += """
                </div>
            </div>
                """

        # Add Parties Involved section
        if case_analysis_result.intake_analysis and hasattr(
            case_analysis_result.intake_analysis, "parties_involved"
        ):
            parties = getattr(case_analysis_result.intake_analysis, "parties_involved", [])
            if parties:
                html_content += """
            <div class="section">
                <h2>Parties Involved</h2>
                <div class="subsection">
                """
                for party in parties:
                    party_name = getattr(party, "name", "Unknown")
                    party_role = getattr(party, "role", "Unknown Role")
                    html_content += f"""
                <div class="party-box">
                    <strong>{party_name}</strong> - {party_role}
                </div>
                    """
                html_content += """
                </div>
            </div>
                """

        # Add Legal Issues Identified section
        if case_analysis_result.intake_analysis and hasattr(
            case_analysis_result.intake_analysis, "legal_claims"
        ):
            legal_claims = getattr(case_analysis_result.intake_analysis, "legal_claims", [])
            if legal_claims:
                html_content += """
            <div class="section">
                <h2>Legal Issues Identified</h2>
                <div class="subsection">
                """
                for claim in legal_claims:
                    html_content += f'<div class="list-item">• {claim}</div>'
                html_content += """
                </div>
            </div>
                """

        # Add Financial Impact section
        if case_analysis_result.intake_analysis and hasattr(
            case_analysis_result.intake_analysis, "financial_impact"
        ):
            financial_impact = getattr(case_analysis_result.intake_analysis, "financial_impact", "")
            if financial_impact:
                html_content += f"""
            <div class="section">
                <h2>Financial Impact</h2>
                <p>{financial_impact}</p>
            </div>
                """

        # Add Client Priorities section
        if case_analysis_result.intake_analysis and hasattr(
            case_analysis_result.intake_analysis, "client_priorities"
        ):
            priorities = getattr(case_analysis_result.intake_analysis, "client_priorities", [])
            if priorities:
                html_content += """
            <div class="section">
                <h2>Client Priorities</h2>
                <div class="subsection">
                """
                for priority in priorities:
                    html_content += f'<div class="list-item">• {priority}</div>'
                html_content += """
                </div>
            </div>
                """

        # Add Desired Outcomes section
        if case_analysis_result.intake_analysis and hasattr(
            case_analysis_result.intake_analysis, "desired_outcomes"
        ):
            outcomes = getattr(case_analysis_result.intake_analysis, "desired_outcomes", [])
            if outcomes:
                html_content += """
            <div class="section">
                <h2>Desired Outcomes</h2>
                <div class="subsection">
                """
                for outcome in outcomes:
                    html_content += f'<div class="list-item">• {outcome}</div>'
                html_content += """
                </div>
            </div>
                """

        # Add Legal Assessment section
        html_content += """
            <div class="section">
                <h2>Legal Assessment</h2>
        """

        if case_analysis_result.legal_assessment:
            claim_viability = getattr(
                case_analysis_result.legal_assessment, "claim_viability", "Not assessed"
            )
            evidence_strength = getattr(
                case_analysis_result.legal_assessment, "overall_evidence_strength", "Not assessed"
            )

            html_content += f"""
                <div class="assessment-box">
                    <p><strong>Claim Viability:</strong> {claim_viability}</p>
                    <p><strong>Evidence Strength:</strong> {evidence_strength}</p>
                </div>
            """

            # Add potential challenges
            potential_challenges = getattr(case_analysis_result.legal_assessment, "potential_challenges", "")
            if potential_challenges:
                html_content += f"""
                <div class="warning-box">
                    <h3>Potential Challenges</h3>
                    <p>{potential_challenges}</p>
                </div>
                """

            # Add recommended actions
            recommended_actions = getattr(case_analysis_result.legal_assessment, "recommended_actions", [])
            if recommended_actions:
                html_content += """
                <h3>Recommended Actions</h3>
                <div class="subsection">
                """
                for action in recommended_actions:
                    html_content += f'<div class="list-item">• {action}</div>'
                html_content += """
                </div>
                """

            # Add urgency assessment
            urgency = getattr(case_analysis_result.legal_assessment, "urgency_assessment", "")
            if urgency:
                html_content += f"""
                <p><strong>Urgency Assessment:</strong> {urgency}</p>
                """
        else:
            html_content += "<p>Legal assessment is in progress.</p>"

        html_content += """
            </div>
        """

        # Add Final Analysis and Recommendations section
        if case_analysis_result.final_analysis:
            final_analysis = case_analysis_result.final_analysis

            # Add recommendations
            recommendations = getattr(final_analysis, "recommendations", "")
            if recommendations:
                html_content += f"""
            <div class="section">
                <h2>Recommendations</h2>
                <p>{recommendations}</p>
            </div>
                """

            # Add next steps
            next_steps = getattr(final_analysis, "next_steps", [])
            if next_steps:
                html_content += """
            <div class="section">
                <h2>Next Steps</h2>
                <div class="subsection">
                """
                for step in next_steps:
                    html_content += f'<div class="list-item">• {step}</div>'
                html_content += """
                </div>
            </div>
                """

        # Add document reference summary (brief)
        if case_analysis_result.analyzed_documents:
            doc_count = len(case_analysis_result.analyzed_documents)
            html_content += f"""
            <div class="section">
                <h2>Document Review Summary</h2>
                <p><em>{doc_count} document(s) were analyzed in support of this case analysis. Detailed document reviews are available in the separate Document Appendix.</em></p>
            </div>
            """

        html_content += """
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
