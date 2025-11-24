"""Utility functions for the Legal Document Analysis Portal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import streamlit as st
from legal_portal.utils.logging_config import get_module_logger

if TYPE_CHECKING:
    pass

logger = get_module_logger(__name__)


class ProgressTracker:
    """Enhanced progress tracking with size-based calculations and detailed feedback."""

    def __init__(self, progress_bar, status_text, detail_text):
        self.progress_bar = progress_bar
        self.status_text = status_text
        self.detail_text = detail_text
        self.current_progress = 0.0

        # Enhanced tracking attributes
        import time

        self.start_time = time.time()
        self.current_phase = None
        self.phase_start_time = None
        self.estimated_total_time = None
        self.phase_history = []

        # Progress allocation for different phases
        # Legacy phases (kept for backwards compatibility)
        self.PHASE_ALLOCATIONS = {
            "document_processing": (0, 15),  # 15% - File processing
            "intake_analysis": (15, 25),  # 10% - Single intake analysis
            "case_analysis": (25, 75),  # 50% - Bulk of processing (size-based)
            "final_assessment": (75, 85),  # 10% - Final legal assessment
            "email_generation": (85, 100),  # 15% - Email generation
            # NEW: Multi-stage analysis phases
            "fact_extraction": (15, 30),  # 15% - Extract structured facts
            "issue_mapping": (30, 42),  # 12% - Map legal issues
            "deep_analysis": (42, 75),  # 33% - Deep legal analysis (most time)
            "letter_generation": (75, 92),  # 17% - Generate letter
            "final_review": (92, 100),  # 8% - Final quality review
        }

        # Enhanced phase descriptions
        self.PHASE_DESCRIPTIONS = {
            "document_processing": {
                "title": "📄 Processing Documents",
                "description": "Extracting content and preparing files for analysis",
                "estimated_duration": 30,  # seconds
            },
            "intake_analysis": {
                "title": "📋 Analyzing Intake Form",
                "description": "Extracting client information and case details",
                "estimated_duration": 45,
            },
            "case_analysis": {
                "title": "🔍 Analyzing Case Documents",
                "description": "AI analysis of legal documents and evidence",
                "estimated_duration": 180,  # Most time-consuming phase
            },
            "final_assessment": {
                "title": "⚖️ Legal Assessment",
                "description": "Generating comprehensive legal evaluation",
                "estimated_duration": 60,
            },
            "email_generation": {
                "title": "📧 Generating Findings Letter",
                "description": "Creating professional findings letter",
                "estimated_duration": 45,
            },
            # NEW: Multi-stage analysis phase descriptions
            "fact_extraction": {
                "title": "🔍 Stage 1/4: Fact Extraction",
                "description": "Extracting key facts, timeline, and parties from documents",
                "estimated_duration": 40,
                "tips": "Building structured fact foundation for legal analysis",
            },
            "issue_mapping": {
                "title": "⚖️ Stage 2/4: Legal Issue Mapping",
                "description": "Identifying applicable legal issues and Florida statutes",
                "estimated_duration": 35,
                "tips": "Querying Florida legal corpus for verified statutes",
            },
            "deep_analysis": {
                "title": "📊 Stage 3/4: Deep Legal Analysis",
                "description": "Performing comprehensive analysis with statute verification",
                "estimated_duration": 90,  # Most time-consuming stage
                "tips": "This is the most detailed stage - analyzing each legal issue thoroughly",
            },
            "letter_generation": {
                "title": "✍️ Stage 4/4: Letter Generation",
                "description": "Generating attorney-quality findings letter",
                "estimated_duration": 50,
                "tips": "Adapting structure to case complexity",
            },
            "final_review": {
                "title": "✅ Final Review",
                "description": "Reviewing completeness and formatting",
                "estimated_duration": 20,
                "tips": "Quality checks and citation verification",
            },
        }

    def set_phase(self, phase_name: str, detail: str = "") -> None:
        """Set the current processing phase with enhanced tracking."""
        import time

        # Record phase transition
        if self.current_phase:
            phase_duration = time.time() - self.phase_start_time
            self.phase_history.append(
                {
                    "phase": self.current_phase,
                    "duration": phase_duration,
                    "completed": True,
                }
            )

        self.current_phase = phase_name
        self.phase_start_time = time.time()
        start_pct, _ = self.PHASE_ALLOCATIONS[phase_name]
        self.current_progress = start_pct

        # Calculate estimated total time if this is first phase
        if not self.estimated_total_time:
            self.estimated_total_time = sum(
                desc["estimated_duration"] for desc in self.PHASE_DESCRIPTIONS.values()
            )

        phase_info = self.PHASE_DESCRIPTIONS.get(phase_name, {})
        title = phase_info.get("title", phase_name.replace("_", " ").title())
        description = phase_info.get("description", detail)

        self.update_display(title, description, show_time_estimate=True)

    def update_progress(self, phase_name: str, progress_within_phase: float, detail: str = "") -> None:
        """Update progress within a specific phase (0.0 to 1.0) with enhanced feedback."""
        start_pct, end_pct = self.PHASE_ALLOCATIONS[phase_name]
        phase_range = end_pct - start_pct
        self.current_progress = start_pct + (progress_within_phase * phase_range)

        phase_info = self.PHASE_DESCRIPTIONS.get(phase_name, {})
        title = phase_info.get("title", phase_name.replace("_", " ").title())

        # Enhanced detail with sub-progress
        if progress_within_phase > 0:
            enhanced_detail = f"{detail} ({progress_within_phase:.1%} of phase)"
        else:
            enhanced_detail = detail or phase_info.get("description", "")

        self.update_display(title, enhanced_detail, show_time_estimate=True)

    def complete_phase(self, phase_name: str, detail: str = "") -> None:
        """Mark a phase as complete with timing information."""
        import time

        if self.current_phase == phase_name and self.phase_start_time:
            phase_duration = time.time() - self.phase_start_time
            self.phase_history.append({"phase": phase_name, "duration": phase_duration, "completed": True})

        _, end_pct = self.PHASE_ALLOCATIONS[phase_name]
        self.current_progress = end_pct

        phase_info = self.PHASE_DESCRIPTIONS.get(phase_name, {})
        title = phase_info.get("title", phase_name.replace("_", " ").title())
        completion_detail = f"✅ {detail}" if detail else "✅ Phase completed successfully"

        self.update_display(f"{title} - Complete", completion_detail, show_time_estimate=True)

    def update_display(self, status: str, detail: str = "", show_time_estimate: bool = False) -> None:
        """Update the UI display elements with enhanced information."""
        import time

        # Update progress bar
        self.progress_bar.progress(self.current_progress / 100.0)

        # Enhanced status with time estimation
        elapsed_time = time.time() - self.start_time
        status_text = f"**{status}** ({self.current_progress:.1f}%)"

        if show_time_estimate and self.estimated_total_time:
            if self.current_progress > 5:  # Only show estimates after some progress
                estimated_remaining = (elapsed_time / (self.current_progress / 100)) - elapsed_time
                if estimated_remaining > 0:
                    if estimated_remaining < 60:
                        time_str = f"{int(estimated_remaining)}s remaining"
                    else:
                        time_str = (
                            f"{int(estimated_remaining / 60)}m {int(estimated_remaining % 60)}s remaining"
                        )
                    status_text += f" • {time_str}"

        self.status_text.text(status_text)

        # Enhanced detail text with helpful information
        if detail:
            # Add processing tips for long phases (legacy)
            if self.current_phase == "case_analysis" and "Analyzing" in detail:
                detail += "\n💡 Tip: Analysis time depends on document complexity and length"
            elif self.current_phase == "final_assessment":
                detail += "\n💡 Generating comprehensive legal recommendations..."

            # Add tips for multi-stage analysis phases
            phase_info = self.PHASE_DESCRIPTIONS.get(self.current_phase, {})
            tips = phase_info.get("tips")
            if tips:
                detail += f"\n💡 {tips}"

            self.detail_text.text(detail)

    def get_progress_summary(self) -> dict:
        """Get comprehensive progress summary for debugging or logging."""
        import time

        return {
            "current_progress": self.current_progress,
            "current_phase": self.current_phase,
            "elapsed_time": time.time() - self.start_time,
            "estimated_total_time": self.estimated_total_time,
            "phase_history": self.phase_history,
            "phases_completed": len([p for p in self.phase_history if p["completed"]]),
            "total_phases": len(self.PHASE_ALLOCATIONS),
        }


def calculate_document_sizes(files: List) -> Dict[str, int]:
    """Calculate sizes of uploaded files for progress tracking."""
    sizes = {}
    for file in files:
        try:
            if hasattr(file, "size"):
                sizes[file.name] = file.size
            else:
                # Fallback: estimate size from content
                content = file.getvalue() if hasattr(file, "getvalue") else b""
                sizes[file.name] = len(content)
        except (AttributeError, TypeError, UnicodeDecodeError):
            # Default size if calculation fails
            sizes[file.name] = 1024  # 1KB default
    return sizes


def generate_case_analysis_html(analysis_result):
    """Generate a professionally formatted HTML case analysis document."""
    from datetime import datetime

    # Get client information
    client_name = "Client"
    attorney_name = "Attorney"
    if analysis_result.intake_analysis:
        client_name = analysis_result.intake_analysis.client_name or "Client"
        attorney_name = analysis_result.intake_analysis.attorney_name or "Attorney"

    current_date = datetime.now().strftime("%B %d, %Y")

    # Start building the HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Case Analysis - {client_name}</title>
        <style>
            body {{
                font-family: 'Times New Roman', Times, serif;
                line-height: 1.6;
                margin: 40px;
                color: #333;
                background-color: #fff;
            }}
            .header {{
                text-align: center;
                margin-bottom: 40px;
                padding-bottom: 20px;
                border-bottom: 2px solid #2c3e50;
            }}
            .header h1 {{
                color: #2c3e50;
                margin-bottom: 10px;
                font-size: 28px;
            }}
            .header p {{
                margin: 5px 0;
                font-size: 16px;
            }}
            .section {{
                margin: 30px 0;
                padding: 20px;
                border-left: 4px solid #3498db;
                background-color: #f8f9fa;
            }}
            .section h2 {{
                color: #2c3e50;
                margin-top: 0;
                margin-bottom: 15px;
                font-size: 22px;
                border-bottom: 1px solid #bdc3c7;
                padding-bottom: 5px;
            }}
            .section h3 {{
                color: #34495e;
                margin-top: 20px;
                margin-bottom: 10px;
                font-size: 18px;
            }}
            .metadata {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .metadata-item {{
                background-color: #ecf0f1;
                padding: 15px;
                border-radius: 5px;
                border-left: 4px solid #3498db;
            }}
            .metadata-item strong {{
                color: #2c3e50;
                display: block;
                margin-bottom: 5px;
            }}
            .document-list {{
                background-color: #fff;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 15px;
                margin: 15px 0;
            }}
            .document-item {{
                margin: 10px 0;
                padding: 10px;
                background-color: #f8f9fa;
                border-left: 3px solid #3498db;
            }}
            .document-item h4 {{
                margin: 0 0 5px 0;
                color: #2c3e50;
            }}
            .document-item p {{
                margin: 5px 0;
                font-size: 14px;
            }}
            .footer {{
                margin-top: 50px;
                padding-top: 20px;
                border-top: 1px solid #bdc3c7;
                text-align: center;
                font-size: 14px;
                color: #7f8c8d;
            }}
            @media print {{
                body {{ margin: 20px; }}
                .section {{ break-inside: avoid; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Comprehensive Case Analysis Report</h1>
            <p><strong>Date:</strong> {current_date}</p>
            <p><strong>Client:</strong> {client_name}</p>
            <p><strong>Attorney:</strong> {attorney_name}</p>
        </div>
    """

    # Add intake analysis section
    if analysis_result.intake_analysis:
        ia = analysis_result.intake_analysis
        html_content += f"""
        <div class="section">
            <h2>Client Intake Analysis</h2>
            <div class="metadata">
                <div class="metadata-item">
                    <strong>Case Type:</strong>
                    {ia.case_type or "Not specified"}
                </div>
                <div class="metadata-item">
                    <strong>Urgency Level:</strong>
                    {ia.urgency_level or "Standard"}
                </div>
            </div>
            <h3>Case Summary</h3>
            <p>{ia.case_summary or "No summary provided."}</p>

            <h3>Client Priorities</h3>
            <ul>
        """
        if ia.client_priorities:
            for priority in ia.client_priorities:
                html_content += f"<li>{priority}</li>"
        else:
            html_content += "<li>No specific priorities identified</li>"

        html_content += "</ul><h3>Desired Outcomes</h3><ul>"

        if ia.desired_outcomes:
            for outcome in ia.desired_outcomes:
                html_content += f"<li>{outcome}</li>"
        else:
            html_content += "<li>No specific outcomes identified</li>"

        html_content += "</ul></div>"

    # Add analyzed documents section
    if analysis_result.analyzed_documents:
        html_content += """
        <div class="section">
            <h2>Document Analysis</h2>
            <div class="document-list">
        """

        for i, doc in enumerate(analysis_result.analyzed_documents, 1):
            html_content += f"""
            <div class="document-item">
                <h4>{i}. {doc.inferred_title or "Untitled Document"}</h4>
                <p><strong>Source File:</strong> {doc.file_name}</p>
                <p><strong>Document Type:</strong> {doc.document_type}</p>
                <p><strong>Summary:</strong> {doc.summary}</p>
                <p><strong>Key Information:</strong> {getattr(doc, "key_information", "Not available")}</p>
                <p><strong>Relevance to Case:</strong> {doc.relevance_to_case}</p>
            </div>
            """

        html_content += "</div></div>"

    # Add legal assessment section
    if analysis_result.legal_assessment:
        la = analysis_result.legal_assessment
        html_content += f"""
        <div class="section">
            <h2>Legal Assessment</h2>
            <div class="metadata">
                <div class="metadata-item">
                    <strong>Claim Viability:</strong>
                    {la.claim_viability or "Not assessed"}
                </div>
                <div class="metadata-item">
                    <strong>Overall Evidence Strength:</strong>
                    {la.overall_evidence_strength or "Not assessed"}
                </div>
            </div>

            <h3>Potential Challenges</h3>
            <ul>
        """

        if la.potential_challenges:
            for challenge in la.potential_challenges:
                html_content += f"<li>{challenge}</li>"
        else:
            html_content += "<li>No specific challenges identified</li>"

        html_content += "</ul><h3>Recommended Actions</h3><ul>"

        if la.recommended_actions:
            for action in la.recommended_actions:
                html_content += f"<li>{action}</li>"
        else:
            html_content += "<li>No specific actions recommended</li>"

        html_content += "</ul></div>"

    # Add any errors or processing notes
    if analysis_result.errors:
        html_content += """
        <div class="section">
            <h2>Processing Notes</h2>
        """
        for error in analysis_result.errors:
            html_content += f"<p><strong>{error.source}:</strong> {error.error_message}</p>"
        html_content += "</div>"

    # Close the HTML
    html_content += f"""
        <div class="footer">
            <p>Generated by Legal Document Analysis Portal on {current_date}</p>
            <p>Bernhardt Riley PLLC</p>
        </div>
    </body>
    </html>
    """

    return html_content


def identify_relevant_practice_areas_from_qa(qa_pairs: list[dict]) -> list[str]:
    """Use AI to analyze Q&A pairs and identify the 5 most relevant practice areas.

    Returns a list of practice area strings.
    """
    # Convert Q&A pairs to text for analysis
    qa_text = "\n".join([f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}" for qa in qa_pairs])

    return identify_relevant_practice_areas(qa_text)


def identify_relevant_practice_areas(intake_content: str) -> list[str]:
    """Use AI to analyze the intake form and identify the 5 most relevant practice areas.

    Returns a list of practice area strings.
    """
    import json

    from legal_portal.utils.openai_client import OpenAIClient

    # Comprehensive list of practice areas
    all_practice_areas = [
        "Breach of Contract (Construction)",
        "Breach of Contract (General)",
        "Breach of Contract (Employment)",
        "Breach of Contract (Real Estate)",
        "Landlord/Tenant (Habitability)",
        "Landlord/Tenant (Eviction)",
        "Landlord/Tenant (Lease Dispute)",
        "Landlord/Tenant (Security Deposit)",
        "Real Estate (Failure to Disclose)",
        "Real Estate (Title Dispute)",
        "Real Estate (Boundary Dispute)",
        "Real Estate (Zoning/Land Use)",
        "Property Damage",
        "Personal Injury (Premises Liability)",
        "Personal Injury (Auto Accident)",
        "Personal Injury (Medical Malpractice)",
        "Employment (Wrongful Termination)",
        "Employment (Discrimination)",
        "Employment (Harassment)",
        "Employment (Wage Dispute)",
        "Employment (Retaliation)",
        "HOA Dispute",
        "Consumer Protection",
        "Debt Collection Defense",
        "Insurance Claim (Denial)",
        "Insurance Claim (Bad Faith)",
        "Business Dispute",
        "Partnership Dispute",
        "Intellectual Property",
        "Family Law (Custody)",
        "Family Law (Divorce)",
        "Estate Planning",
        "Probate",
        "Criminal Defense",
        "Civil Rights Violation",
        "Defamation/Libel",
        "Fraud",
        "Negligence",
        "Product Liability",
    ]

    prompt = f"""Analyze the following intake form and identify the 5 most relevant practice areas \
from the list provided.

INTAKE FORM:
{intake_content}

AVAILABLE PRACTICE AREAS:
{chr(10).join([f"- {area}" for area in all_practice_areas])}

Return ONLY a JSON object with this structure:
{{
    "practice_areas": ["area1", "area2", "area3", "area4", "area5"]
}}

Select exactly 5 practice areas that are most relevant to the client's legal issue. \
Order them from most relevant to least relevant.
"""

    try:
        client = OpenAIClient()
        response = client.create_chat_completion(
            model="gpt-4o-mini",  # Use mini for faster response
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a legal intake specialist. Analyze intake forms and "
                        "identify relevant practice areas."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.3,
        )

        content = response["content"].strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

        result = json.loads(content)
        practice_areas = result.get("practice_areas", [])

        # Add "Other" as a fallback option
        practice_areas.append("Other")

        logger.info(f"AI identified practice areas: {practice_areas}")
        return practice_areas

    except Exception as e:
        logger.error(f"Failed to identify practice areas via AI: {e}")
        # Return a reasonable default list
        return [
            "Landlord/Tenant (Habitability)",
            "Real Estate (Failure to Disclose)",
            "Breach of Contract (General)",
            "Property Damage",
            "Consumer Protection",
            "Other",
        ]


def parse_intake_form_with_ai(intake_content: str) -> dict:
    """Use AI to extract structured data from the intake form.

    Returns a dict with client names, case summary, parties, and other key info.
    This is much more robust than regex and adapts to form changes automatically.
    """
    import json

    from legal_portal.utils.openai_client import OpenAIClient

    prompt = f"""Extract key information from this legal intake form and return structured JSON.

INTAKE FORM:
{intake_content}

Return ONLY a JSON object with this exact structure:
{{
    "client_name_1": "First and last name of primary client, or empty string if not found",
    "client_name_2": "First and last name of second client/spouse, or empty string if not found",
    "case_summary": "Brief summary of the legal issue from the form",
    "parties": [
        {{"name": "Party name", "relationship": "Their relationship to client"}},
        {{"name": "Party name", "relationship": "Their relationship to client"}}
    ],
    "desired_outcome": "What the client wants to achieve",
    "urgency_level": "Critical/Very Important/Important/Not Urgent/Just Inquiry",
    "additional_fields": {{
        "field_1_name": "field_1_value",
        "field_2_name": "field_2_value",
        "field_3_name": "field_3_value",
        "field_4_name": "field_4_value",
        "field_5_name": "field_5_value"
    }}
}}

IMPORTANT:
- Extract actual names filled in the form, not placeholder text like "(First Name, Last Name)"
- If a field is blank or not found, use empty string or empty array
- For additional_fields: capture any other important information from the form that doesn't fit \
the standard fields above
- Use descriptive field names (e.g., "attorney_name", "case_number", "referral_source", "budget", \
"deadline_date")
- Only populate additional_fields with actual data present in the form
- If no additional fields exist, return an empty object for additional_fields
"""

    try:
        client = OpenAIClient()
        response = client.create_chat_completion(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a legal intake specialist. Extract structured data from "
                        "intake forms with high accuracy."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.1,  # Low temperature for consistency
        )

        content = response["content"].strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

        result = json.loads(content)
        logger.info(f"AI extracted intake data: {result}")
        return result

    except Exception as e:
        logger.error(f"Failed to parse intake form with AI: {e}")
        # Return empty structure on failure
        return {
            "client_name_1": "",
            "client_name_2": "",
            "case_summary": "",
            "parties": [],
            "desired_outcome": "",
            "urgency_level": "",
            "additional_fields": {},
        }


def extract_client_name_from_qa(qa_pairs: list[dict]) -> str:
    """Extract client name(s) from Q&A pairs.

    Looks for questions like "Client Name 1", "Client Name 2", etc.
    If multiple names are found, they are joined with ' and '.
    """
    client_names = []

    for qa in qa_pairs:
        question = qa.get("question", "").lower()
        answer = qa.get("answer", "").strip()

        if not answer:
            continue

        # Look for client name questions
        if "client name" in question:
            client_names.append(answer)

    if not client_names:
        logger.warning("Could not extract client name from Q&A pairs.")
        return ""

    final_name = " and ".join(client_names)
    logger.info(f"Extracted client name from Q&A: '{final_name}'")
    return final_name


def build_structured_display_from_qa(qa_pairs: list[dict]) -> dict:
    """Build structured display data from Q&A pairs for the summary expander.

    Maps common questions to structured fields.
    """
    structured = {
        "client_name_1": "",
        "client_name_2": "",
        "case_summary": "",
        "parties": [],
        "desired_outcome": "",
        "urgency_level": "",
        "additional_fields": {},
    }

    for qa in qa_pairs:
        question = qa.get("question", "").lower()
        answer = qa.get("answer", "").strip()

        if not answer:
            continue

        # Map questions to structured fields
        if "client name 1" in question:
            structured["client_name_1"] = answer
        elif "client name 2" in question:
            structured["client_name_2"] = answer
        elif "brief summary" in question or "legal issue" in question:
            structured["case_summary"] = answer
        elif "desired outcome" in question:
            structured["desired_outcome"] = answer
        elif "urgency" in question or "classify your urgency" in question:
            structured["urgency_level"] = answer
        elif "party" in question:
            # Parse party information (e.g., "Party 1: John Smith (Relationship: Contractor)")
            # Try to extract name and relationship
            if "(" in answer and "relationship" in answer.lower():
                # Format: "Name (Relationship: Role)"
                parts = answer.split("(")
                name = parts[0].strip()
                relationship = parts[1].replace(")", "").replace("Relationship:", "").strip()
            else:
                name = answer
                relationship = "Unknown"

            structured["parties"].append({"name": name, "relationship": relationship})
        else:
            # Add to additional fields
            field_key = question.replace("?", "").replace(":", "").strip()
            structured["additional_fields"][field_key] = answer

    logger.info(f"Built structured display from {len(qa_pairs)} Q&A pairs")
    return structured


def parse_client_name_from_intake(intake_content: str) -> str:
    """Extract client name(s) from the intake form using AI.

    DEPRECATED: Use extract_client_name_from_qa() instead.
    If two client names are found, they are joined with ' and '.
    """
    intake_data = parse_intake_form_with_ai(intake_content)

    client_names = []
    if intake_data.get("client_name_1"):
        client_names.append(intake_data["client_name_1"])
    if intake_data.get("client_name_2"):
        client_names.append(intake_data["client_name_2"])

    if not client_names:
        logger.warning("Could not extract client name from intake form.")
        return ""

    final_name = " and ".join(client_names)
    logger.info(f"Extracted client name: '{final_name}'")
    return final_name


def parse_intake_form_qa_pairs(intake_content: str) -> list[dict]:
    """Use AI to extract question-answer pairs from the intake form.

    Returns a list of Q&A objects: [{"question": "...", "answer": "..."}].

    This function:
    - Extracts both explicit questions and labeled fields as Q&A
    - Preserves multi-paragraph answers
    - Skips empty/blank fields
    - Handles various form layouts (paragraphs, labeled fields, checkboxes)
    - Automatically deduplicates questions
    - Returns empty list on failure for graceful degradation
    """
    import json

    from legal_portal.utils.openai_client import OpenAIClient

    prompt = f"""Extract all question-answer pairs from this legal intake form and return them as a JSON array.

INTAKE FORM:
{intake_content}

Return ONLY a JSON array of objects with this structure:
[
    {{"question": "Brief question text", "answer": "Complete answer from the form"}},
    {{"question": "Brief question text", "answer": "Complete answer from the form"}}
]

CRITICAL: FORM STRUCTURE PATTERNS

This intake form may have one of these structures:

**PATTERN A - Questions with Immediate Answers:**
```
Client Name 1: John Smith
Client Name 2: Jane Smith
```

**PATTERN B - Questions at Top, Answers at Bottom:**
```
[TOP OF FORM]
Client Name 1: (First Name, Last Name):
Client Name 2: (First Name, Last Name):
Please provide a brief summary...
Party 1: ___________ Relationship: ___________

[BOTTOM OF FORM - ACTUAL DATA]
John Smith
Jane Smith
We are seeking legal assistance regarding...
William Jones, Seller of Property
```

For PATTERN B forms:
1. Identify field labels from the top section (look for colons, underscores, or placeholder text in parentheses)
2. Find the corresponding filled values from the bottom section by matching:
   - Sequential order (1st field → 1st value, 2nd field → 2nd value)
   - Logical context (a "Party 1" field followed by "Relationship" gets matched to a person name)
3. Match questions to answers even if they're separated by blank lines or form structure

EXTRACTION RULES:
1. Extract both explicit questions AND labeled fields as Q&A pairs
2. For labeled fields, clean up the question:
   - "Client Name 1: (First Name, Last Name):" → Question: "Client Name 1"
   - Remove placeholder text, colons, and underscores
3. For multi-line questions, keep the question text but preserve multi-paragraph answers
4. Skip any fields where NO ACTUAL DATA was provided (only placeholders remain)
5. For checkbox responses, convert to text (e.g., "Critical - Deadline of March 15, 2024")
6. Keep questions concise but answers complete and contextual
7. Remove duplicate questions - if same question appears twice, keep only the first occurrence
8. When you find a Party/Relationship pair, combine them: \
"Party 1: John Smith (Relationship: Contractor)"

EXAMPLES:

**Pattern A (Immediate Answers):**
- Input: "Client Name 1: John Smith"
- Output: {{"question": "Client Name 1", "answer": "John Smith"}}

**Pattern B (Separated Structure):**
- Input Top: "Client Name 1: (First Name, Last Name):"
- Input Bottom: "Balaji Badam"
- Output: {{"question": "Client Name 1", "answer": "Balaji Badam"}}

- Input Top: "Please provide a brief summary of the legal issue..."
- Input Bottom: "We own the investment property at 811 Gate Run Rd..."
- Output: {{"question": "Please provide a brief summary of the legal issue", \
"answer": "We own the investment property at 811 Gate Run Rd..."}}

**Skip These:**
- "Client Name 1: (First Name, Last Name):" with NO corresponding value in bottom section
- Empty fields with only placeholders or blank lines

Return 10-30 Q&A pairs typically, depending on form completeness. If the form follows Pattern B, \
carefully match each labeled field to its corresponding value from the data section."""

    try:
        client = OpenAIClient()
        response = client.create_chat_completion(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a legal intake specialist. Extract question-answer pairs from "
                        "intake forms with high accuracy. You excel at matching form field labels "
                        "(at the top) with their corresponding filled values (which may appear at the "
                        "bottom). Always return valid JSON arrays only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.1,  # Low temperature for consistency
        )

        content = response["content"].strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (``` markers)
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
            # Also handle ```json specifically
            content = content.replace("```json", "").replace("```", "").strip()

        result = json.loads(content)

        # Validate structure
        if not isinstance(result, list):
            logger.error(f"Q&A extraction returned non-list: {type(result)}")
            return []

        # Filter and validate Q&A pairs
        valid_pairs = []
        seen_questions = set()

        for item in result:
            if not isinstance(item, dict):
                continue

            question = item.get("question", "").strip()
            answer = item.get("answer", "").strip()

            # Skip if missing question or answer
            if not question or not answer:
                continue

            # Skip if answer is just placeholder text
            if answer.lower() in ["n/a", "na", "none", "not provided", "(first name, last name)"]:
                continue

            # Skip duplicate questions (case-insensitive)
            question_lower = question.lower()
            if question_lower in seen_questions:
                continue

            seen_questions.add(question_lower)
            valid_pairs.append({"question": question, "answer": answer})

        logger.info(f"AI extracted {len(valid_pairs)} Q&A pairs from intake form")

        # Debug logging for troubleshooting
        if len(valid_pairs) < 3:
            logger.warning(
                f"Very few Q&A pairs extracted ({len(valid_pairs)}). Raw result count: {len(result) if isinstance(result, list) else 'N/A'}"
            )
            logger.debug(f"Raw AI response (first 1000 chars): {content[:1000]}")

        return valid_pairs

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from Q&A extraction: {e}")
        logger.error(f"Response content (first 1000 chars): {content[:1000]}")
        return []
    except Exception as e:
        logger.error(f"Failed to extract Q&A pairs from intake form: {e}", exc_info=True)
        return []


def group_images_intelligently(images: list, max_per_group: int = 3) -> list:
    """Group images intelligently based on filename similarity and upload patterns.

    This grouping strategy enables batch Vision API processing while maintaining
    context awareness between related images.

    Args:
    ----
        images: List of image files (with .name attribute)
        max_per_group: Maximum images per group (default 3)

    Returns:
    -------
        List of image groups: [[img1, img2, img3], [img4, img5], ...]

    Grouping criteria:
    - Similar filenames (sequential numbers, common prefixes)
    - File size similarity (same source likely produces similar file sizes)
    - Max group size to prevent token overflow

    """
    if not images:
        return []

    if len(images) <= max_per_group:
        # All images fit in one group
        return [images]

    groups = []
    current_group = []

    # Sort images by filename for better grouping
    sorted_images = sorted(images, key=lambda img: img.name if hasattr(img, "name") else str(img))

    for img in sorted_images:
        # Get filename without extension for comparison
        img_name = img.name if hasattr(img, "name") else str(img)
        base_name = img_name.rsplit(".", 1)[0] if "." in img_name else img_name

        # If current group is empty, start new group
        if not current_group:
            current_group.append(img)
            continue

        # Check if this image should be in current group
        should_group = False

        # Get previous image name
        prev_img_name = (
            current_group[-1].name if hasattr(current_group[-1], "name") else str(current_group[-1])
        )
        prev_base_name = prev_img_name.rsplit(".", 1)[0] if "." in prev_img_name else prev_img_name

        # Check for sequential numbering (e.g., image_1, image_2, image_3)
        import re

        curr_match = re.search(r"(\d+)$", base_name)
        prev_match = re.search(r"(\d+)$", prev_base_name)

        if curr_match and prev_match:
            curr_num = int(curr_match.group(1))
            prev_num = int(prev_match.group(1))
            # Check if numbers are sequential and prefix is same
            prefix_curr = base_name[: curr_match.start()]
            prefix_prev = prev_base_name[: prev_match.start()]

            if prefix_curr == prefix_prev and abs(curr_num - prev_num) <= 2:
                should_group = True

        # Check for common prefix (at least 50% similarity)
        if not should_group:
            min_len = min(len(base_name), len(prev_base_name))
            if min_len > 0:
                common_prefix_len = 0
                for i in range(min_len):
                    if base_name[i] == prev_base_name[i]:
                        common_prefix_len += 1
                    else:
                        break

                similarity = common_prefix_len / max(len(base_name), len(prev_base_name))
                if similarity >= 0.5:
                    should_group = True

        # Add to current group or start new group
        if should_group and len(current_group) < max_per_group:
            current_group.append(img)
        else:
            # Start new group
            groups.append(current_group)
            current_group = [img]

    # Add the last group
    if current_group:
        groups.append(current_group)

    logger.info(f"Grouped {len(images)} images into {len(groups)} batches: {[len(g) for g in groups]}")
    return groups


def handle_file_uploads():
    """Identify intake documents from uploaded files and prompt for clarification.

    Returns True if analysis can proceed, False otherwise.

    SECURITY: This function now includes comprehensive security validations:
    - Path traversal prevention
    - File size enforcement (100MB limit)
    - Content type validation with magic number detection
    - Secure filename sanitization
    """
    from legal_portal.utils.security import (
        ALLOWED_EXTENSIONS,
        MAX_FILE_SIZE,
        secure_filename,
        validate_file_content,
        validate_file_size,
    )

    uploaded_files = st.session_state.get("uploaded_files", [])
    if not uploaded_files:
        st.error("Please upload at least one document.")
        return False

    # Enhanced file validation with comprehensive security checks
    valid_files = []
    total_size = 0

    for uploaded_file in uploaded_files:
        try:
            # Read file data for validation
            file_data = uploaded_file.read()
            # Reset file position for later processing
            uploaded_file.seek(0)

            # 1. Check file size
            try:
                validate_file_size(file_data, MAX_FILE_SIZE)
                file_size = len(file_data)
                total_size += file_size
            except ValueError as e:
                st.error(f"❌ {uploaded_file.name}: {e!s}")
                logger.error(
                    "File size validation failed",
                    extra={
                        "file_name": uploaded_file.name,
                        "file_size": len(file_data),
                        "max_size": MAX_FILE_SIZE,
                        "validation_issue": "file_size_exceeded",
                    },
                )
                continue

            # 2. Sanitize filename (prevent path traversal)
            original_name = uploaded_file.name
            sanitized_name = secure_filename(original_name)

            if sanitized_name != original_name:
                logger.warning(
                    "Filename sanitized for security",
                    extra={
                        "original_name": original_name,
                        "sanitized_name": sanitized_name,
                        "validation_issue": "filename_sanitized",
                    },
                )
                # Update the filename for display purposes
                st.info(f"📝 Filename '{original_name}' sanitized to '{sanitized_name}' for security")

            # 3. Validate file content with magic number detection
            try:
                mime_type, file_ext = validate_file_content(file_data, sanitized_name)

                # File passed all security validations
                valid_files.append(uploaded_file)
                logger.info(
                    "File security validation passed",
                    extra={
                        "file_name": sanitized_name,
                        "original_name": original_name,
                        "file_size": file_size,
                        "mime_type": mime_type,
                        "extension": file_ext,
                    },
                )

            except ValueError as e:
                st.error(f"❌ {uploaded_file.name}: {e!s}")
                logger.error(
                    "File content validation failed",
                    extra={
                        "file_name": uploaded_file.name,
                        "error": str(e),
                        "validation_issue": "content_validation_failed",
                    },
                )
                continue

        except Exception as e:
            logger.error(
                "Unexpected error during file validation",
                extra={
                    "file_name": uploaded_file.name,
                    "error": str(e),
                    "validation_issue": "unexpected_validation_error",
                },
            )
            st.error(f"❌ {uploaded_file.name}: Unexpected error during validation. Please try again.")
            continue

    # Check total upload size
    if total_size > MAX_FILE_SIZE:
        total_mb = total_size / (1024 * 1024)
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        st.error(
            f"Total upload size ({total_mb:.2f}MB) exceeds maximum allowed ({max_mb:.2f}MB). "
            f"Please reduce the number or size of files."
        )
        logger.error(
            "Total upload size exceeded",
            extra={
                "total_size": total_size,
                "max_size": MAX_FILE_SIZE,
                "validation_issue": "total_size_exceeded",
            },
        )
        return False

    # If no valid files remain, return False
    if not valid_files:
        logger.warning(
            "No valid files after security validation",
            extra={"total_uploaded": len(uploaded_files), "valid_files": 0},
        )
        st.error(
            f"No valid files found. Please upload files with allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
        return False

    # Update session state with only valid files
    st.session_state.uploaded_files = valid_files
    logger.info(
        "File security validation completed",
        extra={
            "total_uploaded": len(uploaded_files),
            "valid_files": len(valid_files),
            "rejected_files": len(uploaded_files) - len(valid_files),
            "total_size": total_size,
        },
    )

    intake_docs = [f for f in valid_files if "intake" in f.name.lower()]

    intake_selected = False

    if len(intake_docs) == 1:
        st.session_state.intake_form = intake_docs[0]
        st.session_state.case_documents = [f for f in uploaded_files if f != intake_docs[0]]
        st.info(f"Automatically detected '{intake_docs[0].name}' as the intake form.")
        intake_selected = True
    elif len(intake_docs) > 1:
        st.warning("Multiple possible intake forms found.")
        selected_intake_name = st.selectbox(
            "Please select the correct intake form:", [f.name for f in intake_docs]
        )
        st.session_state.intake_form = next(f for f in intake_docs if f.name == selected_intake_name)
        st.session_state.case_documents = [f for f in uploaded_files if f != st.session_state.intake_form]
        intake_selected = True
    else:  # No intake docs found
        st.warning("No intake form automatically detected.")
        selected_intake_name = st.selectbox(
            "Please select the intake form from the uploaded documents:",
            [f.name for f in uploaded_files],
        )
        if selected_intake_name:
            st.session_state.intake_form = next(f for f in uploaded_files if f.name == selected_intake_name)
            st.session_state.case_documents = [f for f in uploaded_files if f != st.session_state.intake_form]
            intake_selected = True

    if intake_selected and st.session_state.intake_form:
        return True

    return False
