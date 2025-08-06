from __future__ import annotations

import asyncio

import streamlit as st
from backend_logic.main_processor import process_case_documents
from backend_logic.utils import handle_file_uploads
from components.ui_components import (
    case_information_form,
    file_upload_section,
    results_display_section,
)


# --- Session State Initialization ---
def initialize_session_state():
    """Initializes the session state with default values."""
    if "case_info" not in st.session_state:
        st.session_state.case_info = {
            "clientName": "",
            "attorneyName": "",
            "caseReference": "",
        }
    if "uploaded_files" not in st.session_state:
        st.session_state.uploaded_files = []
    if "intake_form" not in st.session_state:
        st.session_state.intake_form = None
    if "case_documents" not in st.session_state:
        st.session_state.case_documents = []
    if "final_results" not in st.session_state:
        st.session_state.final_results = None
    if "main_letter" not in st.session_state:
        st.session_state.main_letter = None
    if "appendix" not in st.session_state:
        st.session_state.appendix = None
    if "processing_status" not in st.session_state:
        st.session_state.processing_status = "idle"  # idle, active, completed, failed
    if "processing_error" not in st.session_state:
        st.session_state.processing_error = None

    # Cost tracking session state
    if "cost_estimate" not in st.session_state:
        st.session_state.cost_estimate = None
    if "cost_summary" not in st.session_state:
        st.session_state.cost_summary = None
    if "current_processing_cost" not in st.session_state:
        st.session_state.current_processing_cost = 0.0
    if "cost_session_id" not in st.session_state:
        st.session_state.cost_session_id = None


def start_analysis():
    """Handles the start analysis button click."""
    intake_form = st.session_state.get("intake_form")
    st.session_state.get("case_documents", [])

    if not intake_form:
        st.error("An intake form is required to start the analysis.")
        return

    # Run the async processing function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_case_documents())
    finally:
        loop.close()


# --- Main Application ---
def main():
    """Main function for the Streamlit application."""
    st.set_page_config(page_title="Legal Document Analysis Portal", layout="wide")

    initialize_session_state()

    st.title("Legal Document Analysis Portal")

    case_information_form()

    tab1, tab2 = st.tabs(["Upload & Process", "Results"])

    with tab1:
        if st.session_state.processing_status in ["idle", "failed", "completed"]:
            file_upload_section()

            if st.session_state.get("uploaded_files"):
                if handle_file_uploads():
                    if st.button("Start Analysis"):
                        start_analysis()

        elif st.session_state.processing_status == "active":
            st.info("Analysis is currently in progress. Please wait...")

        # Show any processing errors
        if (
            st.session_state.processing_status == "failed"
            and st.session_state.processing_error
        ):
            st.error(f"Processing failed: {st.session_state.processing_error}")

    with tab2:
        if st.session_state.final_results:
            results_display_section()
        else:
            st.info(
                "No results available. Please upload documents and start the analysis first."
            )


if __name__ == "__main__":
    main()
