"""
Utility functions for the Legal Document Analysis Portal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

from backend_logic.cost_estimator import CostEstimator


if TYPE_CHECKING:
    from backend.utils.data_models import CostEstimate


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
        self.PHASE_ALLOCATIONS = {
            "document_processing": (0, 15),  # 15% - File processing
            "intake_analysis": (15, 25),  # 10% - Single intake analysis
            "case_analysis": (25, 75),  # 50% - Bulk of processing (size-based)
            "final_assessment": (75, 85),  # 10% - Final legal assessment
            "email_generation": (85, 100),  # 15% - Email generation
        }
        
        # Enhanced phase descriptions
        self.PHASE_DESCRIPTIONS = {
            "document_processing": {
                "title": "📄 Processing Documents",
                "description": "Extracting content and preparing files for analysis",
                "estimated_duration": 30  # seconds
            },
            "intake_analysis": {
                "title": "📋 Analyzing Intake Form",
                "description": "Extracting client information and case details",
                "estimated_duration": 45
            },
            "case_analysis": {
                "title": "🔍 Analyzing Case Documents",
                "description": "AI analysis of legal documents and evidence",
                "estimated_duration": 180  # Most time-consuming phase
            },
            "final_assessment": {
                "title": "⚖️ Legal Assessment",
                "description": "Generating comprehensive legal evaluation",
                "estimated_duration": 60
            },
            "email_generation": {
                "title": "📧 Generating Findings Letter",
                "description": "Creating professional findings letter",
                "estimated_duration": 45
            }
        }

    def set_phase(self, phase_name: str, detail: str = "") -> None:
        """Set the current processing phase with enhanced tracking."""
        import time
        
        # Record phase transition
        if self.current_phase:
            phase_duration = time.time() - self.phase_start_time
            self.phase_history.append({
                "phase": self.current_phase,
                "duration": phase_duration,
                "completed": True
            })
        
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

    def update_progress(
        self, phase_name: str, progress_within_phase: float, detail: str = ""
    ) -> None:
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
            self.phase_history.append({
                "phase": phase_name,
                "duration": phase_duration,
                "completed": True
            })
        
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
                        time_str = f"{int(estimated_remaining / 60)}m {int(estimated_remaining % 60)}s remaining"
                    status_text += f" • {time_str}"
        
        self.status_text.text(status_text)
        
        # Enhanced detail text with helpful information
        if detail:
            # Add processing tips for long phases
            if self.current_phase == "case_analysis" and "Analyzing" in detail:
                detail += "\n💡 Tip: Analysis time depends on document complexity and length"
            elif self.current_phase == "final_assessment":
                detail += "\n💡 Generating comprehensive legal recommendations..."
                
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
            "total_phases": len(self.PHASE_ALLOCATIONS)
        }


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
            value=f"${float(cost_estimate.estimated_cost):.4f}",
            help=f"Confidence: {cost_estimate.breakdown.get('confidence', 0.8):.0%}",
        )

    with col2:
        st.metric(
            label="Confidence Level",
            value=f"{cost_estimate.breakdown.get('confidence', 0.8):.0%}",
            help="Based on file size analysis and processing patterns",
        )

    # Detailed breakdown in expander
    if st.expander("View Cost Breakdown"):
        st.write("**Cost Breakdown:**")
        breakdown_data = []
        for category, cost in cost_estimate.breakdown.items():
            if category != 'confidence':  # Skip confidence, it's not a cost
                breakdown_data.append({
                    "Category": category.replace('_', ' ').title(),
                    "Estimated Cost": f"${float(cost):.4f}"
                })
        
        if breakdown_data:
            st.dataframe(breakdown_data, use_container_width=True)
        else:
            st.info("No detailed breakdown available")


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

        DocumentProcessor()

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
                <p><strong>Source File:</strong> {doc.file_name}</p>
                <p><strong>Document Type:</strong> {doc.document_type}</p>
                <p><strong>Summary:</strong> {doc.summary}</p>
                <p><strong>Key Information:</strong> {getattr(doc, 'key_information', 'Not available')}</p>
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
