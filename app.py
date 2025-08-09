from __future__ import annotations

import asyncio

import streamlit as st

from backend_logic.main_processor import process_case_documents
from backend_logic.utils import handle_file_uploads
from backend_logic.utils.logging_config import setup_logging, get_module_logger
from components.ui_components import (
    case_information_form,
    file_upload_section,
    results_display_section,
)

# Initialize logging
logger = get_module_logger(__name__)


# --- Session State Initialization ---
def initialize_session_state():
    """Initializes the session state with default values."""
    # Define default values for all session state variables
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
        "appendix": None,
        "processing_status": "idle",  # idle, active, completed, failed
        "processing_error": None,
        "cost_estimate": None,
        "cost_summary": None,
        "current_processing_cost": 0.0,
        "cost_session_id": None,
    }
    
    # Initialize any missing session state variables
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def start_analysis():
    """Handles the start analysis button click."""
    logger.info("Analysis start requested")
    
    intake_form = st.session_state.get("intake_form")
    case_documents = st.session_state.get("case_documents", [])

    if not intake_form:
        logger.warning("Analysis start failed: no intake form provided")
        st.error("An intake form is required to start the analysis.")
        return

    logger.info(
        "Starting document analysis",
        extra={
            "intake_form": intake_form.name if hasattr(intake_form, 'name') else str(type(intake_form)),
            "case_documents_count": len(case_documents)
        }
    )

    # Run the async processing function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_case_documents())
        logger.info("Document analysis completed successfully")
    except Exception as e:
        logger.exception("Document analysis failed", extra={"error_type": type(e).__name__})
        raise
    finally:
        loop.close()


# --- Main Application ---
def main():
    """Main function for the Streamlit application."""
    # Set up structured logging at application startup
    setup_logging(level="INFO", enable_console=True)
    logger.info("Legal Document Analysis Portal starting up")
    
    st.set_page_config(page_title="Legal Document Analysis Portal", layout="wide")

    initialize_session_state()
    logger.debug("Session state initialized")

    st.title("Legal Document Analysis Portal")

    case_information_form()

    tab1, tab2 = st.tabs(["Upload & Process", "Results"])

    with tab1:
        if st.session_state.processing_status in ["idle", "failed", "completed"]:
            file_upload_section()

            if (st.session_state.get("uploaded_files") and
                handle_file_uploads() and
                st.button("Start Analysis")):
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
