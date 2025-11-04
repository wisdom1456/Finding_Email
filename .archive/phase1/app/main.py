from __future__ import annotations

import asyncio
import os
import uuid

import streamlit as st
from legal_portal.services.main_processor import process_case_documents
from legal_portal.utils.helpers import handle_file_uploads

# Simplified logging
from legal_portal.utils.logging_config import setup_logging
from legal_portal.utils.structured_logger import request_id_var, session_id_var, user_id_var

from app.components.ui_components import (
    case_information_form,
    file_upload_section,
    results_display_section,
)

# Initialize logging
setup_logging(app_name="legal-portal", level=os.getenv("LOG_LEVEL", "INFO"))


# --- Session State Initialization ---
def initialize_session_state():
    """Initialize the session state with default values."""
    defaults = {
        "case_info": {
            "clientName": "",
            "attorneyName": "",
            "caseReference": "",
        },
        "uploaded_files": [],
        "intake_form": None,
        "case_documents": [],
        "final_results": None,
        "main_letter": None,
        "document_review": None,
        "case_analysis": None,
        "processing_status": "idle",  # idle, active, completed, failed
        "processing_error": None,
    }

    # Initialize any missing session state variables
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


# --- Main Application ---
def main():
    """Run the main Streamlit application."""
    st.set_page_config(
        page_title="Legal Document Analysis Portal",
        layout="wide",
        menu_items={"About": "Legal Document Analysis Portal - Simplified Edition"},
    )

    initialize_session_state()

    st.title("⚖️ Legal Document Analysis Portal")
    st.caption("AI-Powered Legal Document Analysis")

    case_information_form()

    tab1, tab2 = st.tabs(["Upload & Process", "Results"])

    with tab1:
        if st.session_state.processing_status in ["idle", "failed", "completed"]:
            file_upload_section()

            if (
                st.session_state.get("uploaded_files")
                and handle_file_uploads()
                and st.button("Start Analysis", type="primary")
            ):
                intake_form = st.session_state.get("intake_form")
                if not intake_form:
                    st.error("An intake form is required to start the analysis.")
                else:
                    # Set up context for logging/tracing
                    request_id_var.set(str(uuid.uuid4()))
                    user_id_var.set("default_user")
                    session_id_var.set(
                        st.session_state.session_id if "session_id" in st.session_state else str(uuid.uuid4())
                    )

                    # Run the async processing function
                    st.session_state.processing_status = "active"
                    st.info("⚡ Analysis is currently in progress...")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # This function will need to be updated to return the new outputs
                        loop.run_until_complete(process_case_documents())
                    except Exception as e:
                        st.session_state.processing_status = "failed"
                        st.session_state.processing_error = str(e)
                        st.error(f"An error occurred during analysis: {e}")
                    finally:
                        loop.close()
                        st.rerun()

        elif st.session_state.processing_status == "active":
            st.info("⚡ Analysis is currently in progress...")

        # Show any processing errors
        if st.session_state.processing_status == "failed" and st.session_state.processing_error:
            st.error(f"Processing failed: {st.session_state.processing_error}")

    with tab2:
        if st.session_state.final_results:
            results_display_section()
        else:
            st.info("No results available. Please upload documents and start the analysis first.")


if __name__ == "__main__":
    main()
