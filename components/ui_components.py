"""
UI Components for the Legal Document Analysis Portal.
"""
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

def case_information_form():
    """Renders the case information form in the sidebar."""
    st.sidebar.header("Case Information")
    st.session_state.case_info["clientName"] = st.sidebar.text_input(
        "Client Name", value=st.session_state.case_info["clientName"]
    )
    st.session_state.case_info["attorneyName"] = st.sidebar.text_input(
        "Attorney Name", value=st.session_state.case_info["attorneyName"]
    )
    st.session_state.case_info["caseReference"] = st.sidebar.text_input(
        "Case Reference", value=st.session_state.case_info["caseReference"]
    )


def file_upload_section():
    """Handles the file upload section, allowing folder uploads."""
    st.header("Upload Case Folder")
    uploaded_files = st.file_uploader(
        "Select a folder or multiple files "
        "(PDF, DOCX, EML, TXT, JPG, PNG, MP3, M4A, WAV, MP4, MOV, AVI)",
        type=[
            "pdf",
            "docx",
            "eml",
            "txt",
            "jpg",
            "jpeg",
            "png",
            "mp3",
            "m4a",
            "wav",
            "mp4",
            "mov",
            "avi",
        ],
        accept_multiple_files=True,
    )
    if uploaded_files:
        st.session_state.uploaded_files = uploaded_files


def results_display_section():
    """Displays the final results and download links."""
    if st.session_state.final_results:
        st.header("Results")

        # Display cost summary first if available
        if st.session_state.cost_summary:
            from components.budget_sheet import BudgetSheetComponent
            budget_component = BudgetSheetComponent()

            # Create tabs for results organization
            tab1, tab2, tab3 = st.tabs(
                ["📄 Documents", "💰 Cost Analysis", "📊 Detailed Breakdown"]
            )

            with tab1:
                # Check if we have the new two-document format
                if st.session_state.main_letter and st.session_state.appendix:
                    # Display the main findings letter inline using components.html for complete HTML documents
                    st.subheader("Findings Letter")
                    components.html(
                        st.session_state.main_letter, height=800, scrolling=True
                    )

                    # Provide separate download buttons for all documents
                    st.subheader("Download Options")

                    col1, col2, col3 = st.columns(3)
                    _display_download_buttons(col1, col2, col3)
                else:
                    st.info("Results are available but in an unexpected format.")

            with tab2:
                # Display budget summary and charts
                budget_component.display_budget_summary(st.session_state.cost_summary)
                budget_component.display_cost_breakdown_chart(
                    st.session_state.cost_summary
                )
                budget_component.display_variance_analysis(
                    st.session_state.cost_summary
                )

            with tab3:
                # Display detailed cost tables and export options
                budget_component.display_detailed_cost_tables(
                    st.session_state.cost_summary
                )
                budget_component.create_export_buttons(st.session_state.cost_summary)

        # Original display without cost tracking
        elif st.session_state.main_letter and st.session_state.appendix:
            # Display the main findings letter inline using components.html for complete HTML documents
            st.subheader("Findings Letter")
            components.html(
                st.session_state.main_letter, height=800, scrolling=True
            )

            # Provide separate download buttons for all documents
            st.subheader("Download Options")

            col1, col2, col3 = st.columns(3)
            _display_download_buttons(col1, col2, col3)
        else:
            st.info("Results are available but in an unexpected format.")

        # Display any errors that occurred during processing
        if st.session_state.final_results.errors:
            st.subheader("Processing Notes")
            for error in st.session_state.final_results.errors:
                st.warning(f"**{error.source}**: {error.error_message}")


def _display_download_buttons(col1, col2, col3):
    """Helper function to display download buttons for the three document types."""
    with col1:
        # Download button for main findings letter as HTML
        try:
            main_letter_bytes = st.session_state.main_letter.encode("utf-8")

            # Get client name for filename
            client_name = "Client"
            if (
                st.session_state.final_results.intake_analysis
                and st.session_state.final_results.intake_analysis.client_name
            ):
                client_name_raw = (
                    st.session_state.final_results.intake_analysis.client_name
                )
                client_name = "".join(
                    c for c in client_name_raw if c.isalnum() or c in " _-"
                ).rstrip()

            st.download_button(
                label="📧 Findings Letter",
                data=main_letter_bytes,
                file_name=f"Findings_Letter_{client_name}.html",
                mime="text/html",
                help="Professional findings letter in HTML format",
            )
        except Exception as e:
            st.error(f"Error creating findings letter download: {e}")

    with col2:
        # Download button for document appendix as HTML
        try:
            appendix_bytes = st.session_state.appendix.encode("utf-8")

            # Get client name for filename
            client_name = "Client"
            if (
                st.session_state.final_results.intake_analysis
                and st.session_state.final_results.intake_analysis.client_name
            ):
                client_name_raw = (
                    st.session_state.final_results.intake_analysis.client_name
                )
                client_name = "".join(
                    c for c in client_name_raw if c.isalnum() or c in " _-"
                ).rstrip()

            st.download_button(
                label="📎 Document Appendix",
                data=appendix_bytes,
                file_name=f"Document_Appendix_{client_name}.html",
                mime="text/html",
                help="Supporting document analysis in HTML format",
            )
        except Exception as e:
            st.error(f"Error creating appendix download: {e}")

    with col3:
        # Download button for case analysis as HTML
        try:
            from backend_logic.utils import generate_case_analysis_html
            # Generate the HTML case analysis document
            case_analysis_html = generate_case_analysis_html(
                st.session_state.final_results
            )
            case_analysis_bytes = case_analysis_html.encode("utf-8")

            # Get client name for filename
            client_name = "Client"
            if (
                st.session_state.final_results.intake_analysis
                and st.session_state.final_results.intake_analysis.client_name
            ):
                client_name_raw = (
                    st.session_state.final_results.intake_analysis.client_name
                )
                client_name = "".join(
                    c for c in client_name_raw if c.isalnum() or c in " _-"
                ).rstrip()

            st.download_button(
                label="📄 Case Analysis",
                data=case_analysis_bytes,
                file_name=f"Case_Analysis_{client_name}.html",
                mime="text/html",
                help="Comprehensive case analysis in HTML format",
            )
        except Exception as e:
            st.error(f"Error creating case analysis download: {e}")