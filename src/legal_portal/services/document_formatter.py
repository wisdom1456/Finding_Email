"""Document Formatter Service - Converts JSON data to user-friendly HTML documents."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class DocumentFormatterService:
    """Formats JSON data into user-friendly HTML documents for display and download."""

    @staticmethod
    def format_document_review(document_summaries_json: str, client_name: str = "Client") -> str:
        """Format document summaries JSON into a readable HTML document review.

        Args:
        ----
            document_summaries_json: JSON string containing document summaries
            client_name: Client name for the header

        Returns:
        -------
            Formatted HTML string

        """
        logger.info(f"Formatting document review for client: '{client_name}'")
        try:
            # Parse JSON if it's a string
            if isinstance(document_summaries_json, str):
                summaries = json.loads(document_summaries_json)
            else:
                summaries = document_summaries_json

            if not isinstance(summaries, list):
                summaries = [summaries]

            current_date = datetime.now().strftime("%B %d, %Y")

            html_parts = [
                DocumentFormatterService._get_html_header("Document Review", client_name),
                f"""
                <div class="document-header">
                    <h1>Document Review</h1>
                    <div class="meta-info">
                        <p><strong>Client:</strong> {client_name}</p>
                        <p><strong>Date:</strong> {current_date}</p>
                        <p><strong>Total Documents:</strong> {len(summaries)}</p>
                    </div>
                </div>
                <hr class="section-divider">
                """,
            ]

            # Format each document
            for idx, summary in enumerate(summaries, 1):
                html_parts.append(DocumentFormatterService._format_single_document(summary, idx))

            html_parts.append(DocumentFormatterService._get_html_footer())

            return "\n".join(html_parts)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse document summaries JSON: {e}")
            return DocumentFormatterService._format_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error formatting document review: {e}")
            return DocumentFormatterService._format_error(str(e))

    @staticmethod
    def format_case_analysis(case_analysis_json: str, client_name: str = "Client") -> str:
        """Format case analysis JSON into a readable HTML case analysis document.

        Args:
        ----
            case_analysis_json: JSON string containing case analysis
            client_name: Client name for the header

        Returns:
        -------
            Formatted HTML string

        """
        logger.info(f"Formatting case analysis for client: '{client_name}'")
        try:
            # Parse JSON if it's a string
            if isinstance(case_analysis_json, str):
                analysis = json.loads(case_analysis_json)
            else:
                analysis = case_analysis_json

            if not isinstance(analysis, list):
                analysis = [analysis]

            current_date = datetime.now().strftime("%B %d, %Y")

            html_parts = [
                DocumentFormatterService._get_html_header("Case Analysis", client_name),
                f"""
                <div class="document-header">
                    <h1>Case Analysis</h1>
                    <div class="meta-info">
                        <p><strong>Client:</strong> {client_name}</p>
                        <p><strong>Date:</strong> {current_date}</p>
                    </div>
                </div>
                <hr class="section-divider">
                """,
            ]

            # Extract all parties, dates, and amounts across documents
            all_parties = set()
            all_dates = []
            all_amounts = []
            all_issues = []

            for doc in analysis:
                if isinstance(doc, dict):
                    all_parties.update(doc.get("parties", []))
                    all_dates.extend(doc.get("key_dates", []))
                    all_amounts.extend(doc.get("key_amounts", []))
                    all_issues.extend(doc.get("issues_identified", []))

            # Executive Summary
            html_parts.append(
                """
                <div class="executive-summary">
                    <h2>Executive Summary</h2>
            """
            )

            if all_parties:
                html_parts.append(
                    f"""
                    <div class="summary-section">
                        <h3>Parties Involved</h3>
                        <ul class="party-list">
                            {''.join(f'<li>{party}</li>' for party in sorted(all_parties))}
                        </ul>
                    </div>
                """
                )

            if all_dates:
                html_parts.append(
                    """
                    <div class="summary-section">
                        <h3>Key Timeline</h3>
                        <ul class="timeline-list">
                """
                )
                # Sort dates if possible
                sorted_dates = sorted(all_dates, key=lambda x: x.get("date", ""))

                # Deduplicate dates based on date + event combination
                seen = set()
                unique_dates = []
                for date_info in sorted_dates:
                    date = date_info.get("date", "Unknown date")
                    event = date_info.get("event", "")
                    # Create a unique key from date and event
                    date_event_key = f"{date}|{event}"
                    if date_event_key not in seen:
                        seen.add(date_event_key)
                        unique_dates.append(date_info)

                for date_info in unique_dates:
                    date = date_info.get("date", "Unknown date")
                    event = date_info.get("event", "")
                    source = date_info.get("source_document", "")
                    html_parts.append(
                        f"""
                        <li>
                            <strong>{date}:</strong> {event}
                            {f'<span class="source">({source})</span>' if source else ''}
                        </li>
                    """
                    )
                html_parts.append("</ul></div>")

            if all_amounts:
                html_parts.append(
                    """
                    <div class="summary-section">
                        <h3>Key Amounts</h3>
                        <ul class="amount-list">
                """
                )
                for amount_info in all_amounts:
                    amount = amount_info.get("amount", "")
                    description = amount_info.get("description", "")
                    source = amount_info.get("source_document", "")
                    html_parts.append(
                        f"""
                        <li>
                            <strong>{amount}:</strong> {description}
                            {f'<span class="source">({source})</span>' if source else ''}
                        </li>
                    """
                    )
                html_parts.append("</ul></div>")

            if all_issues:
                html_parts.append(
                    """
                    <div class="summary-section issues-section">
                        <h3>Issues Identified</h3>
                        <ul class="issue-list">
                """
                )
                # Remove duplicates while preserving order
                seen = set()
                unique_issues = []
                for issue in all_issues:
                    if issue not in seen:
                        seen.add(issue)
                        unique_issues.append(issue)

                for issue in unique_issues:
                    html_parts.append(f"<li>{issue}</li>")
                html_parts.append("</ul></div>")

            html_parts.append("</div>")  # End executive summary

            # Detailed Document Analysis
            html_parts.append(
                """
                <hr class="section-divider">
                <h2>Detailed Document Analysis</h2>
            """
            )

            for idx, doc in enumerate(analysis, 1):
                if isinstance(doc, dict):
                    html_parts.append(DocumentFormatterService._format_single_document(doc, idx))

            html_parts.append(DocumentFormatterService._get_html_footer())

            return "\n".join(html_parts)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse case analysis JSON: {e}")
            return DocumentFormatterService._format_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error formatting case analysis: {e}")
            return DocumentFormatterService._format_error(str(e))

    @staticmethod
    def format_quality_report(quality_results: List[Dict[str, Any]]) -> str:
        """Format the document quality validation results into an HTML report."""
        if not quality_results:
            return "<h2>No quality report generated.</h2>"

        # Define CSS for the report with light background for dark mode compatibility
        styles = """
        <style>
            html, body {
                background-color: #ffffff !important;
                margin: 0;
                padding: 0;
            }
            .quality-report-container {
                font-family: sans-serif;
                margin: 20px;
                color: #333;
                background-color: #ffffff;
            }
            .quality-report-container h2 {
                color: #333;
                border-bottom: 2px solid #ddd;
                padding-bottom: 10px;
            }
            .quality-report-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
                background-color: #ffffff;
            }
            .quality-report-table th, .quality-report-table td {
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
                color: #333;
                background-color: #ffffff;
            }
            .quality-report-table th {
                background-color: #f7f7f7 !important;
                font-weight: bold;
                color: #333 !important;
            }
            .quality-level-high { color: #28a745; font-weight: bold; }
            .quality-level-medium { color: #ff9800; font-weight: bold; }
            .quality-level-low { color: #dc3545; font-weight: bold; }
            .quality-report-table tr:nth-child(even) { background-color: #f9f9f9 !important; }
            .quality-report-table tr:nth-child(odd) { background-color: #ffffff !important; }
        </style>
        """

        html = f"<html><head><meta charset='UTF-8'>{styles}</head><body>"
        html += "<div class='quality-report-container'>"
        html += "<h2>Document Quality & Integrity Report</h2>"

        # --- Summary Section ---
        total_docs = len(quality_results)
        low_quality_count = sum(1 for r in quality_results if r.get("confidence_level") == "low")
        medium_quality_count = sum(1 for r in quality_results if r.get("confidence_level") == "medium")
        high_quality_count = sum(1 for r in quality_results if r.get("confidence_level") == "high")

        html += f"<p><strong>Total Documents Processed:</strong> {total_docs}</p>"
        html += f"<p><strong>High Quality:</strong> {high_quality_count} documents</p>"
        html += f"<p><strong>Medium Quality:</strong> {medium_quality_count} documents</p>"
        html += f"<p><strong>Low Quality:</strong> {low_quality_count} documents</p>"

        # --- Table Section ---
        html += "<table class='quality-report-table'>"
        html += (
            "<thead><tr><th>Filename</th><th>Confidence</th><th>Score</th>"
            "<th>Issues</th><th>Recommendations</th></tr></thead>"
        )
        html += "<tbody>"

        for result in quality_results:
            confidence_level = result.get("confidence_level", "unknown")
            quality_class = f"quality-level-{confidence_level}"
            issues_html = (
                "<ul>" + "".join([f"<li>{issue}</li>" for issue in result.get("issues", [])]) + "</ul>"
                if result.get("issues")
                else "None"
            )
            recommendations_html = (
                "<ul>" + "".join([f"<li>{rec}</li>" for rec in result.get("recommendations", [])]) + "</ul>"
                if result.get("recommendations")
                else "None"
            )

            html += f"""
            <tr>
                <td>{result.get('document', 'Unknown')}</td>
                <td class='{quality_class}'>{confidence_level.upper()}</td>
                <td>{result.get('score', 0):.1f}/10</td>
                <td>{issues_html}</td>
                <td>{recommendations_html}</td>
            </tr>
            """

        html += "</tbody></table>"
        html += "</div></body></html>"

        return html

    @staticmethod
    def _format_single_document(doc_data: Dict[str, Any], index: int) -> str:
        """Format a single document summary into HTML.

        Args:
        ----
            doc_data: Dictionary containing document data
            index: Document number

        Returns:
        -------
            HTML string for the document

        """
        doc_name = doc_data.get("document_name", f"Document {index}")
        doc_type = doc_data.get("document_type", "Unknown")
        parties = doc_data.get("parties", [])
        key_dates = doc_data.get("key_dates", [])
        key_amounts = doc_data.get("key_amounts", [])
        issues = doc_data.get("issues_identified", [])
        relevance = doc_data.get("relevance_to_case", "")
        extraction_quality = doc_data.get("extraction_quality", "unknown")
        extraction_notes = doc_data.get("extraction_notes")

        quality_badge = {
            "high": '<span class="quality-badge quality-high">High Quality</span>',
            "medium": '<span class="quality-badge quality-medium">Medium Quality</span>',
            "low": '<span class="quality-badge quality-low">Low Quality</span>',
        }.get(extraction_quality, "")

        html = f"""
        <div class="document-section">
            <div class="document-title">
                <h3>Document {index}: {doc_name}</h3>
                {quality_badge}
            </div>
            <p class="document-type"><strong>Type:</strong> {doc_type}</p>
        """

        if extraction_notes:
            html += f"""
            <div class="extraction-note">
                <strong>Note:</strong> {extraction_notes}
            </div>
            """

        if parties:
            html += """
            <div class="subsection">
                <h4>Parties Mentioned</h4>
                <ul>
            """
            for party in parties:
                html += f"<li>{party}</li>"
            html += "</ul></div>"

        if key_dates:
            html += """
            <div class="subsection">
                <h4>Key Dates</h4>
                <ul>
            """
            for date_info in key_dates:
                date = date_info.get("date", "")
                event = date_info.get("event", "")
                html += f"<li><strong>{date}:</strong> {event}</li>"
            html += "</ul></div>"

        if key_amounts:
            html += """
            <div class="subsection">
                <h4>Key Amounts</h4>
                <ul>
            """
            for amount_info in key_amounts:
                amount = amount_info.get("amount", "")
                description = amount_info.get("description", "")
                html += f"<li><strong>{amount}:</strong> {description}</li>"
            html += "</ul></div>"

        if issues:
            html += """
            <div class="subsection issues-subsection">
                <h4>Issues Identified</h4>
                <ul>
            """
            for issue in issues:
                html += f"<li>{issue}</li>"
            html += "</ul></div>"

        if relevance:
            html += f"""
            <div class="subsection relevance-section">
                <h4>Relevance to Case</h4>
                <p>{relevance}</p>
            </div>
            """

        html += "</div>"
        return html

    @staticmethod
    def _get_html_header(title: str, client_name: str) -> str:
        """Get HTML header with styles.

        Args:
        ----
            title: Document title
            client_name: Client name

        Returns:
        -------
            HTML header string

        """
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {client_name}</title>
    <style>
        body {{
            font-family: 'Times New Roman', Times, serif;
            line-height: 1.6;
            color: #000000;
            background-color: #ffffff;
            margin: 0;
            padding: 40px;
            max-width: 1000px;
            margin: 0 auto;
        }}

        .document-header {{
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 3px solid #2c3e50;
        }}

        .document-header h1 {{
            color: #2c3e50;
            font-size: 32px;
            margin-bottom: 20px;
            font-weight: bold;
        }}

        .meta-info {{
            font-size: 16px;
            color: #34495e;
        }}

        .meta-info p {{
            margin: 8px 0;
        }}

        h2 {{
            color: #2c3e50;
            font-size: 24px;
            margin-top: 40px;
            margin-bottom: 20px;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}

        h3 {{
            color: #34495e;
            font-size: 20px;
            margin-top: 30px;
            margin-bottom: 15px;
        }}

        h4 {{
            color: #34495e;
            font-size: 16px;
            margin-top: 20px;
            margin-bottom: 10px;
            font-weight: bold;
        }}

        .section-divider {{
            border: 0;
            border-top: 2px solid #bdc3c7;
            margin: 40px 0;
        }}

        .executive-summary {{
            background-color: #f8f9fa;
            padding: 30px;
            border-left: 5px solid #3498db;
            margin: 30px 0;
            border-radius: 5px;
        }}

        .summary-section {{
            margin: 25px 0;
        }}

        .document-section {{
            background-color: #ffffff;
            padding: 25px;
            margin: 25px 0;
            border: 1px solid #ddd;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .document-title {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}

        .document-type {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 20px;
        }}

        .subsection {{
            margin: 20px 0;
        }}

        .issues-subsection {{
            background-color: #fff3cd;
            padding: 15px;
            border-left: 4px solid #ffc107;
            border-radius: 3px;
        }}

        .relevance-section {{
            background-color: #d1ecf1;
            padding: 15px;
            border-left: 4px solid #17a2b8;
            border-radius: 3px;
        }}

        .issues-section {{
            background-color: #fff3cd;
            padding: 20px;
            border-left: 4px solid #ffc107;
            border-radius: 3px;
        }}

        .extraction-note {{
            background-color: #f0f0f0;
            padding: 10px;
            margin: 10px 0;
            border-left: 3px solid #95a5a6;
            font-style: italic;
            font-size: 14px;
        }}

        ul {{
            margin: 10px 0;
            padding-left: 30px;
        }}

        li {{
            margin: 8px 0;
        }}

        .party-list li {{
            display: inline-block;
            background-color: #e8f4f8;
            padding: 5px 12px;
            margin: 5px;
            border-radius: 15px;
            font-size: 14px;
        }}

        .timeline-list li {{
            margin: 12px 0;
            padding-left: 10px;
        }}

        .amount-list li {{
            margin: 12px 0;
            padding-left: 10px;
        }}

        .issue-list li {{
            margin: 10px 0;
            padding-left: 10px;
        }}

        .source {{
            color: #7f8c8d;
            font-size: 12px;
            font-style: italic;
            margin-left: 5px;
        }}

        .quality-badge {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
        }}

        .quality-high {{
            background-color: #d4edda;
            color: #155724;
        }}

        .quality-medium {{
            background-color: #fff3cd;
            color: #856404;
        }}

        .quality-low {{
            background-color: #f8d7da;
            color: #721c24;
        }}

        @media print {{
            body {{
                padding: 20px;
            }}

            .document-section {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
"""

    @staticmethod
    def _get_html_footer() -> str:
        """Get HTML footer.

        Returns
        -------
            HTML footer string

        """
        return """
</body>
</html>
"""

    @staticmethod
    def format_findings_letter(letter_html: str, client_name: str = "Client") -> str:
        """Format findings letter HTML with professional legal document styling.

        Args:
        ----
            letter_html: AI-generated letter HTML content
            client_name: Client name for the header

        Returns:
        -------
            Fully-formatted HTML with professional styling

        """
        logger.info(f"Formatting findings letter for client: '{client_name}'")
        try:
            # Clean the input HTML - remove any existing html/body tags
            cleaned_content = letter_html
            cleaned_content = re.sub(r"<!DOCTYPE[^>]*>", "", cleaned_content, flags=re.IGNORECASE)
            cleaned_content = re.sub(r"<html[^>]*>|</html>", "", cleaned_content, flags=re.IGNORECASE)
            cleaned_content = re.sub(
                r"<head>.*?</head>", "", cleaned_content, flags=re.IGNORECASE | re.DOTALL
            )
            cleaned_content = re.sub(r"<body[^>]*>|</body>", "", cleaned_content, flags=re.IGNORECASE)
            cleaned_content = cleaned_content.strip()

            # Build the professionally formatted letter
            formatted_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Findings Letter - {client_name}</title>
    <style>
        html, body {{
            background-color: #ffffff !important;
            color: #000000 !important;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Times New Roman', Times, serif;
            line-height: 1.8;
            color: #000000;
            background-color: #ffffff;
            padding: 60px 80px;
            max-width: 1000px;
            margin: 0 auto;
        }}

        /* Headings */
        h1 {{
            color: #1a1a1a;
            font-size: 28px;
            margin-top: 40px;
            margin-bottom: 20px;
            font-weight: bold;
            border-bottom: 3px solid #2c3e50;
            padding-bottom: 12px;
        }}

        h2 {{
            color: #2c3e50;
            font-size: 22px;
            margin-top: 35px;
            margin-bottom: 18px;
            font-weight: bold;
            border-bottom: 2px solid #3498db;
            padding-bottom: 8px;
        }}

        h3 {{
            color: #34495e;
            font-size: 18px;
            margin-top: 28px;
            margin-bottom: 14px;
            font-weight: bold;
        }}

        h4 {{
            color: #34495e;
            font-size: 16px;
            margin-top: 22px;
            margin-bottom: 12px;
            font-weight: bold;
        }}

        /* Paragraphs and text */
        p {{
            margin: 18px 0;
            text-align: justify;
            text-justify: inter-word;
            max-width: 85ch;
            hyphens: auto;
            -webkit-hyphens: auto;
            -ms-hyphens: auto;
        }}

        /* Lists - Enhanced for readability */
        ul, ol {{
            margin: 14px 0;
            padding-left: 40px;
            line-height: 2.0;
        }}

        li {{
            margin: 12px 0;
        }}

        /* Nested lists for action items */
        ul ul, ol ul {{
            margin-top: 8px;
            padding-left: 30px;
        }}

        /* Action item sections - make them stand out */
        h3 + p, h3 + ul {{
            margin-top: 10px;
        }}

        /* "What this means" or explanatory paragraphs */
        .explanation {{
            background-color: #f8f9fa;
            padding: 15px;
            margin: 15px 0;
            border-left: 4px solid #3498db;
            font-style: normal;
        }}

        /* Strong and emphasis */
        strong {{
            font-weight: bold;
            color: #1a1a1a;
        }}

        em {{
            font-style: italic;
        }}

        /* Horizontal rules */
        hr {{
            border: 0;
            border-top: 2px solid #bdc3c7;
            margin: 40px 0;
        }}

        /* Call to action box */
        .call-to-action {{
            background-color: #e8f4f8;
            border-left: 5px solid #3498db;
            padding: 25px;
            margin: 35px 0;
            border-radius: 5px;
        }}

        /* Disclaimer box */
        .disclaimer {{
            background-color: #f8f9fa;
            border-left: 5px solid #95a5a6;
            padding: 20px;
            margin: 35px 0;
            border-radius: 5px;
            font-size: 14px;
            font-style: italic;
            color: #555;
        }}

        /* Strengths/Challenges sections */
        .strengths-section {{
            background-color: #d4edda;
            border-left: 5px solid #28a745;
            padding: 20px;
            margin: 25px 0;
            border-radius: 5px;
        }}

        .challenges-section {{
            background-color: #fff3cd;
            border-left: 5px solid #ffc107;
            padding: 20px;
            margin: 25px 0;
            border-radius: 5px;
        }}

        /* Tables */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}

        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}

        th {{
            background-color: #f2f2f2;
            font-weight: bold;
        }}

        /* Blockquotes */
        blockquote {{
            border-left: 4px solid #ccc;
            margin: 20px 0;
            padding-left: 20px;
            font-style: italic;
            color: #555;
        }}

        /* Citation links (for cited version) */
        sup a {{
            color: #0066cc !important;
            text-decoration: none;
            font-size: 0.85em;
        }}

        sup a:hover {{
            text-decoration: underline;
        }}

        /* Section dividers */
        .section-divider {{
            border: 0;
            border-top: 2px solid #bdc3c7;
            margin: 40px 0;
        }}

        /* Print styles */
        @media print {{
            body {{
                padding: 40px;
                font-size: 12pt;
            }}

            h1 {{
                page-break-after: avoid;
                font-size: 20pt;
            }}

            h2 {{
                page-break-after: avoid;
                font-size: 16pt;
            }}

            h3, h4 {{
                page-break-after: avoid;
                font-size: 14pt;
            }}

            .call-to-action, .disclaimer, .strengths-section, .challenges-section {{
                page-break-inside: avoid;
            }}

            ul, ol {{
                page-break-inside: avoid;
            }}
        }}

        /* Responsive design */
        @media (max-width: 768px) {{
            body {{
                padding: 30px 20px;
            }}

            h1 {{
                font-size: 24px;
            }}

            h2 {{
                font-size: 20px;
            }}

            h3 {{
                font-size: 16px;
            }}
        }}
    </style>
</head>
<body>
    {cleaned_content}
</body>
</html>
"""

            logger.info("Successfully formatted findings letter with professional styling")
            return formatted_html

        except Exception as e:
            logger.error(f"Error formatting findings letter: {e}")
            return DocumentFormatterService._format_error(str(e))

    @staticmethod
    def _format_error(error_message: str) -> str:
        """Format an error message into HTML.

        Args:
        ----
            error_message: Error message to display

        Returns:
        -------
            HTML error string

        """
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            padding: 40px;
            background-color: #fff;
            color: #000;
        }}
        .error {{
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 20px;
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <div class="error">
        <h2>Error Formatting Document</h2>
        <p>{error_message}</p>
    </div>
</body>
</html>
"""
