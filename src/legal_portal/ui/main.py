"""Main Streamlit UI for the Legal Document Analysis Portal."""

from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
import uuid

import streamlit as st
from legal_portal.services.main_processor import process_case_documents
from legal_portal.ui.components.ui_components import (
    case_information_form,
    file_upload_section,
    results_display_section,
)
from legal_portal.utils.helpers import handle_file_uploads
from legal_portal.utils.logging_config import setup_logging
from legal_portal.utils.structured_logger import request_id_var, session_id_var, user_id_var

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
        "processing_thread": None,
        "processing_progress": "",  # Current processing step
        "processing_start_time": None,
        "result_queue": None,  # Thread-safe queue for results
    }

    # Initialize any missing session state variables
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def run_processing_in_background(intake_form, case_documents, result_queue: queue.Queue):
    """Run the document processing in a background thread using asyncio.
    Uses a thread-safe queue to communicate the final result back to the UI.
    """
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the async processing function to get the final result
        result = loop.run_until_complete(
            process_case_documents(
                intake_form=intake_form,
                case_documents=case_documents,
                case_info=st.session_state.get("case_info"),
            )
        )

        # Send ONE final message to the queue
        if result.status == "completed":
            result_queue.put({"type": "completed", "result": result})
            print(
                f"DEBUG [Background Thread]: Sent completion to queue (main_letter length={len(result.main_letter)})"
            )
        else:
            result_queue.put(
                {
                    "type": "failed",
                    "error": f"Processing failed with status: {result.status}",
                    "result": result,
                }
            )
            print(f"DEBUG [Background Thread]: Sent failure to queue (status={result.status})")

    except Exception as e:
        # Send error through queue
        error_msg = str(e)

        # Provide more helpful error messages for common issues
        if "APITimeoutError" in error_msg or "Request timed out" in error_msg:
            error_msg = "OpenAI API timeout - The AI service took too long to respond. This usually means the model is overloaded. Please try again in a few minutes."
        elif "RetryError" in error_msg:
            error_msg = "Multiple API failures - The AI service failed after several retry attempts. Please check your internet connection and try again."

        result_queue.put({"type": "failed", "error": error_msg})
        print(f"DEBUG [Background Thread]: Sent exception to queue: {error_msg}")

    finally:
        # Clean up the event loop
        loop.close()


def start_analysis():
    """Start the document analysis in a background thread."""
    intake_form = st.session_state.get("intake_form")
    case_documents = st.session_state.get("case_documents", [])

    if not intake_form:
        st.error("An intake form is required to start the analysis.")
        return

    # Case documents are optional - intake form alone is sufficient
    if not case_documents:
        st.info("📝 Note: Processing intake form only (no additional case documents provided).")

    # Set up context for logging/tracing
    request_id_var.set(str(uuid.uuid4()))
    user_id_var.set("default_user")
    session_id_var.set(st.session_state.session_id if "session_id" in st.session_state else str(uuid.uuid4()))

    # Update status to active
    st.session_state.processing_status = "active"
    st.session_state.processing_error = None
    import time

    st.session_state.processing_start_time = time.time()
    st.session_state.last_refresh_time = time.time()

    # Create thread-safe queue
    result_queue = queue.Queue()
    st.session_state.result_queue = result_queue

    # Start processing in a background thread
    thread = threading.Thread(
        target=run_processing_in_background,
        args=(intake_form, case_documents, result_queue),
        daemon=True,
    )
    thread.start()

    # Store the thread reference
    st.session_state.processing_thread = thread


# --- Main Application ---
def main():
    """Run the main Streamlit application."""
    st.set_page_config(
        page_title="Legal Document Analysis Portal",
        layout="wide",
        menu_items={"About": "Legal Document Analysis Portal - Enhanced Edition"},
    )

    initialize_session_state()

    st.title("⚖️ Legal Document Analysis Portal")
    st.caption("AI-Powered Legal Document Analysis")

    case_information_form()

    tab1, tab2 = st.tabs(["Upload & Process", "Results"])

    with tab1:
        result_queue = st.session_state.get("result_queue")

        # State-driven UI updates
        if st.session_state.processing_status == "active":
            # 1. Check queue for the final result FIRST
            if result_queue:
                try:
                    message = result_queue.get_nowait()
                    if message["type"] == "completed":
                        # Update state to 'completed' and rerun
                        st.session_state.processing_status = "completed"
                        result = message["result"]
                        elapsed = time.time() - st.session_state.processing_start_time
                        st.session_state.processing_progress = (
                            f"✅ Analysis completed in {elapsed:.1f} seconds!"
                        )
                        st.session_state.main_letter = result.main_letter
                        st.session_state.document_review = result.document_summaries
                        st.session_state.case_analysis = result.case_analysis
                        st.session_state.final_results = {"status": result.status}
                        print(
                            f"DEBUG [UI Thread]: ✅ COMPLETION RECEIVED! main_letter length={len(result.main_letter)}"
                        )
                        st.rerun()
                    elif message["type"] == "failed":
                        # Update state to 'failed' and rerun
                        st.session_state.processing_status = "failed"
                        st.session_state.processing_error = message["error"]
                        print(f"DEBUG [UI Thread]: ❌ FAILURE RECEIVED: {message['error']}")
                        st.rerun()
                except queue.Empty:
                    # No message yet, continue to show progress UI
                    pass

            # 2. If still active, show the "in progress" UI
            if st.session_state.processing_status == "active":
                with st.status("⚡ Analysis in Progress", expanded=True):
                    # Show elapsed time
                    if st.session_state.processing_start_time:
                        elapsed = time.time() - st.session_state.processing_start_time
                        minutes = int(elapsed // 60)
                        seconds = int(elapsed % 60)
                        time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                        st.write(f"**Time Elapsed:** {time_str}")

                    st.write("💡 The UI remains responsive while processing continues in the background.")
                    st.progress(0.5)  # Shows activity

                # 3. Schedule the next check
                time.sleep(1)
                st.rerun()

        # Show upload section when not actively processing
        elif st.session_state.processing_status in ["idle", "failed", "completed"]:
            if st.session_state.processing_status == "completed":
                st.success(st.session_state.processing_progress)

            file_upload_section()

            if st.session_state.get("uploaded_files") and handle_file_uploads():
                if st.button("Start Analysis", type="primary"):
                    start_analysis()
                    st.rerun()

        # Show any processing errors
        if st.session_state.processing_status == "failed" and st.session_state.processing_error:
            st.error(f"Processing failed: {st.session_state.processing_error}")

            # Add a reset button to try again
            if st.button("Reset and Try Again"):
                # Reset relevant state variables
                st.session_state.processing_status = "idle"
                st.session_state.processing_error = None
                st.session_state.uploaded_files = []
                st.session_state.intake_form = None
                st.session_state.case_documents = []
                st.rerun()

    with tab2:
        if st.session_state.final_results:
            results_display_section()
        else:
            st.info("No results available. Please upload documents and start the analysis first.")


if __name__ == "__main__":
    main()
