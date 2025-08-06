"""
Utility functions for the Legal Document Analysis Portal.
"""
from __future__ import annotations

import streamlit as st
from backend_logic.cost_estimator import CostEstimator
from backend.utils.data_models import CostEstimate

class ProgressTracker:
    """Enhanced progress tracking with size-based calculations and detailed feedback."""

    def __init__(self, progress_bar, status_text, detail_text):
        self.progress_bar = progress_bar
        self.status_text = status_text
        self.detail_text = detail_text
        self.current_progress = 0.0

        # Progress allocation for different phases
        self.PHASE_ALLOCATIONS = {
            "document_processing": (0, 15),  # 15% - File processing
            "intake_analysis": (15, 25),  # 10% - Single intake analysis
            "case_analysis": (25, 75),  # 50% - Bulk of processing (size-based)
            "final_assessment": (75, 85),  # 10% - Final legal assessment
            "email_generation": (85, 100),  # 15% - Email generation
        }

    def set_phase(self, phase_name: str, detail: str = "") -> None:
        """Set the current processing phase."""
        start_pct, _ = self.PHASE_ALLOCATIONS[phase_name]
        self.current_progress = start_pct
        self.update_display(phase_name.replace("_", " ").title(), detail)

    def update_progress(
        self, phase_name: str, progress_within_phase: float, detail: str = ""
    ) -> None:
        """Update progress within a specific phase (0.0 to 1.0)."""
        start_pct, end_pct = self.PHASE_ALLOCATIONS[phase_name]
        phase_range = end_pct - start_pct
        self.current_progress = start_pct + (progress_within_phase * phase_range)
        self.update_display(phase_name.replace("_", " ").title(), detail)

    def complete_phase(self, phase_name: str, detail: str = "") -> None:
        """Mark a phase as complete."""
        _, end_pct = self.PHASE_ALLOCATIONS[phase_name]
        self.current_progress = end_pct
        self.update_display(phase_name.replace("_", " ").title() + " Complete", detail)

    def update_display(self, status: str, detail: str = "") -> None:
        """Update the UI display elements."""
        self.progress_bar.progress(self.current_progress / 100.0)
        self.status_text.text(f"**{status}** ({self.current_progress:.1f}%)")
        if detail:
            self.detail_text.text(detail)


def calculate_document_sizes(files: list) -> dict[str, int]:
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


def display_cost_estimation(cost_estimate: CostEstimate) -> None:
    """Display cost estimation before processing begins."""

    st.subheader("📊 Estimated Processing Costs")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="Total Estimated Cost",
            value=f"${float(cost_estimate.total_estimated_cost):.4f}",
            help=f"Confidence: {cost_estimate.confidence_level:.0%}",
        )

    with col2:
        st.metric(
            label="Confidence Level",
            value=f"{cost_estimate.confidence_level:.0%}",
            help="Based on file size analysis and processing patterns",
        )

    # Detailed breakdown in expander
    if st.expander("View Cost Breakdown"):
        if cost_estimate.estimated_document_costs:
            st.write("**Document Processing:**")
            doc_data = []
            for cost in cost_estimate.estimated_document_costs:
                doc_data.append(
                    {
                        "Service": cost.service_name,
                        "Operation": cost.operation_type,
                        "Units": f"{cost.units_consumed:,} {cost.unit_type}",
                        "Rate": f"${float(cost.rate_per_unit):.6f}",
                        "Cost": f"${float(cost.total_cost):.4f}",
                        "File": cost.file_name or "N/A",
                    }
                )
            st.dataframe(doc_data, use_container_width=True)

        if cost_estimate.estimated_media_costs:
            st.write("**Media Processing:**")
            media_data = []
            for cost in cost_estimate.estimated_media_costs:
                media_data.append(
                    {
                        "Service": cost.service_name,
                        "Operation": cost.operation_type,
                        "Units": f"{cost.units_consumed} {cost.unit_type}",
                        "Rate": f"${float(cost.rate_per_unit):.3f}",
                        "Cost": f"${float(cost.total_cost):.4f}",
                        "File": cost.file_name or "N/A",
                    }
                )
            st.dataframe(media_data, use_container_width=True)


def display_processing_cost_update(current_cost: float) -> None:
    """Display real-time cost updates during processing."""

    if current_cost > 0:
        st.sidebar.metric(
            label="Processing Cost",
            value=f"${current_cost:.4f}",
            help="Real-time cost accumulation",
        )


def generate_cost_estimate_for_files(files: list) -> CostEstimate | None:
    """Generate cost estimate for uploaded files."""
    try:
        cost_estimator = CostEstimator()
        from backend_logic.document_processor import DocumentProcessor
        doc_processor = DocumentProcessor()

        # Process files to get structured data for estimation
        processed_docs = []
        audio_files = []
        video_files = []

        for file in files:
            file_type = file.type.lower() if hasattr(file, "type") else ""
            file_name = file.name
            file_size = getattr(file, "size", 0)

            # Categorize files
            if "audio" in file_type:
                audio_files.append({"filename": file_name, "size": file_size})
            elif "video" in file_type:
                video_files.append({"filename": file_name, "size": file_size})
            else:
                # For documents, create minimal ProcessedDocument for estimation
                content = ""
                try:
                    if hasattr(file, "getvalue"):
                        content_bytes = file.getvalue()
                        if isinstance(content_bytes, bytes):
                            content = content_bytes.decode("utf-8", errors="ignore")
                        else:
                            content = str(content_bytes)
                except (UnicodeDecodeError, AttributeError):
                    # Use file size as proxy for content length
                    content = "x" * file_size  # Rough content estimation

                from backend.utils.data_models import (
                    DocumentType,
                    FileMetadata,
                    FileType,
                    ProcessedDocument,
                )

                processed_doc = ProcessedDocument(
                    file_name=file_name,
                    content=content,
                    file_type=FileType.PDF
                    if file_name.lower().endswith(".pdf")
                    else FileType.TXT,
                    document_type=DocumentType.CASE_DOCUMENT,
                    metadata=FileMetadata(filename=file_name, size=file_size),
                )
                processed_docs.append(processed_doc)

        # Generate cost estimate
        return cost_estimator.generate_cost_estimate(
            documents=processed_docs, audio_files=audio_files, video_files=video_files
        )


    except (ValueError, TypeError, AttributeError) as e:
        st.warning(f"Could not generate cost estimate: {e!s}")
        return None

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
                <p><strong>Source File:</strong> {doc.filename}</p>
                <p><strong>Document Type:</strong> {doc.document_type}</p>
                <p><strong>Summary:</strong> {doc.summary}</p>
                <p><strong>Key Information:</strong> {doc.key_information}</p>
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
            html_content += (
                f"<p><strong>{error.source}:</strong> {error.error_message}</p>"
            )
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

def handle_file_uploads():
    """
    Identifies intake documents from uploaded files and prompts for clarification.
    Shows cost estimation after file upload but before processing.
    Returns True if analysis can proceed, False otherwise.
    """
    uploaded_files = st.session_state.get("uploaded_files", [])
    if not uploaded_files:
        st.error("Please upload at least one document.")
        return False

    intake_docs = [f for f in uploaded_files if "intake" in f.name.lower()]

    intake_selected = False

    if len(intake_docs) == 1:
        st.session_state.intake_form = intake_docs[0]
        st.session_state.case_documents = [
            f for f in uploaded_files if f != intake_docs[0]
        ]
        st.info(f"Automatically detected '{intake_docs[0].name}' as the intake form.")
        intake_selected = True
    elif len(intake_docs) > 1:
        st.warning("Multiple possible intake forms found.")
        selected_intake_name = st.selectbox(
            "Please select the correct intake form:", [f.name for f in intake_docs]
        )
        st.session_state.intake_form = next(
            f for f in intake_docs if f.name == selected_intake_name
        )
        st.session_state.case_documents = [
            f for f in uploaded_files if f != st.session_state.intake_form
        ]
        intake_selected = True
    else:  # No intake docs found
        st.warning("No intake form automatically detected.")
        selected_intake_name = st.selectbox(
            "Please select the intake form from the uploaded documents:",
            [f.name for f in uploaded_files],
        )
        if selected_intake_name:
            st.session_state.intake_form = next(
                f for f in uploaded_files if f.name == selected_intake_name
            )
            st.session_state.case_documents = [
                f for f in uploaded_files if f != st.session_state.intake_form
            ]
            intake_selected = True

    # Show cost estimation after intake form is selected
    if intake_selected and st.session_state.intake_form:
        # Generate and display cost estimate
        if st.session_state.cost_estimate is None:
            with st.spinner("Generating cost estimate..."):
                cost_estimate = generate_cost_estimate_for_files(uploaded_files)
                if cost_estimate:
                    st.session_state.cost_estimate = cost_estimate

        # Display cost estimation if available
        if st.session_state.cost_estimate:
            display_cost_estimation(st.session_state.cost_estimate)

        return True

    return False