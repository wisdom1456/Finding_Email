"""Main Streamlit UI for the Legal Document Analysis Portal."""

from __future__ import annotations

import asyncio
import os
import queue
import threading
import time

import streamlit as st

from legal_portal.services.main_processor import process_case_documents
from legal_portal.ui.components.ui_components import (
    case_information_form,
    file_upload_section,
    results_display_section,
)
from legal_portal.utils.helpers import handle_file_uploads
from legal_portal.utils.logging_config import get_module_logger, setup_logging

# Initialize logging
setup_logging(app_name="legal-portal", level=os.getenv("LOG_LEVEL", "INFO"))
logger = get_module_logger(__name__)


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
        "quality_report": None,  # For the new quality report tab
        "processing_status": "idle",  # idle, active, completed, failed
        "processing_error": None,
        "processing_thread": None,
        "processing_progress": "",  # Current processing step
        "processing_start_time": None,
        "result_queue": None,  # Thread-safe queue for results
        "ui_step": "upload",  # 'upload', 'review', 'processing', 'results'
        "review_data": {},  # Holds data for the review screen
        "start_full_analysis": False,  # Flag to start background thread
        "editable_qa_pairs": [],  # For the Q&A editor in review screen
        "confirmed_qa_pairs": [],  # Final confirmed Q&A after user review
    }

    # Initialize any missing session state variables
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def run_processing_in_background(
    intake_form, case_documents, case_info, review_data, result_queue: queue.Queue
):
    """Run the document processing in a background thread using asyncio.
    Uses a thread-safe queue to communicate the final result back to the UI.
    """
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Create progress callback that uses the queue (thread-safe)
        def send_progress(message, docs_processed=None, phase="", percent=0):
            """Send progress update through queue."""
            result_queue.put(
                {
                    "type": "progress",
                    "message": message,
                    "documents_processed": docs_processed or [],
                    "current_phase": phase,
                    "progress_percent": percent,
                }
            )

        # Run the async processing function to get the final result
        result = loop.run_until_complete(
            process_case_documents(
                intake_form=intake_form,
                case_documents=case_documents,
                case_info=case_info,  # Use parameter, not session_state
                review_data=review_data,
                progress_callback=send_progress,  # Pass the callback
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


# --- Main Application ---
def main():
    """Main function to run the Streamlit application."""
    # --- Page Configuration ---
    st.set_page_config(
        page_title="Bernhardt Riley | Document Analysis Portal",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Initialize Session & Logging ---
    initialize_session_state()

    # --- Sidebar ---
    with st.sidebar:
        st.title("⚖️ Document Analysis Portal")
        st.info(
            "This tool provides an initial analysis of case documents. "
            "All outputs should be reviewed by a qualified attorney."
        )

        # Display case information form
        case_information_form()

    # --- Main Content ---
    if st.session_state.ui_step == "upload":
        st.header("Step 1: Upload Documents")
        file_upload_section()

        if st.button("Review Documents"):
            # This button now transitions to the review step
            # The actual processing happens after the review
            handle_review_transition()

    elif st.session_state.ui_step == "review":
        # This is the new review step
        # We need to import the new component for this
        from legal_portal.ui.components.ui_components import review_and_confirm_section

        review_and_confirm_section()

        # Check if the confirmation button was pressed in the review component
        if st.session_state.get("start_full_analysis"):
            handle_analysis_start()

    elif st.session_state.ui_step in ["processing", "completed", "failed", "results"]:
        # These steps are part of the active processing/results view

        # Handle background processing thread and results queue
        if st.session_state.processing_status == "active":
            check_processing_status()

        # Display results once completed
        if st.session_state.final_results:
            results_display_section()


def handle_review_transition():
    """Prepare for the review step by processing the intake form."""
    # Find intake form
    intake_uploads = [f for f in st.session_state.uploaded_files if "intake" in f.name.lower()]

    if not intake_uploads:
        st.error("An intake form must be uploaded to start the review.")
        return

    intake_file = intake_uploads[0]

    # Process just the intake file to get its content for review
    # This is a simplified, synchronous processing for the review step
    import asyncio

    from legal_portal.core.document_processor import DocumentProcessor

    try:
        processor = DocumentProcessor()
        # Use the async method to process the single intake file
        processed_docs = asyncio.run(
            processor.process_documents_from_streamlit([intake_file], intake_filenames=["intake"])
        )

        if not processed_docs:
            st.error("Failed to process the intake form.")
            return

        intake_content = processed_docs[0].content

        # Parse intake form with AI - SINGLE extraction using Q&A as source of truth
        from legal_portal.utils.helpers import (
            build_structured_display_from_qa,
            extract_client_name_from_qa,
            identify_relevant_practice_areas_from_qa,
            parse_intake_form_qa_pairs,
        )

        with st.spinner("Analyzing intake form and extracting information..."):
            try:
                # SINGLE AI CALL: Extract Q&A pairs only
                logger.info("Starting single Q&A extraction from intake form")
                qa_pairs = parse_intake_form_qa_pairs(intake_content)

                if not qa_pairs:
                    st.warning(
                        "⚠️ Failed to extract information from intake form. You can manually enter the details in the review screen."
                    )
                    qa_pairs = []

                # Derive all other data from Q&A pairs (no additional AI calls)
                logger.info("Deriving structured data from Q&A pairs")
                client_name = extract_client_name_from_qa(qa_pairs)
                intake_data = build_structured_display_from_qa(qa_pairs)
                practice_areas = identify_relevant_practice_areas_from_qa(qa_pairs)

                logger.info(
                    f"Successfully processed intake: {len(qa_pairs)} Q&A pairs, client: '{client_name}', {len(practice_areas)} practice areas"
                )

            except Exception as e:
                st.error(f"Failed to analyze intake form: {e}")
                logger.error(f"Intake analysis failed: {e}", exc_info=True)
                # Provide empty data so user can manually enter
                qa_pairs = []
                client_name = ""
                intake_data = {}
                practice_areas = ["Other"]

        # Store data for the review screen
        st.session_state.review_data = {
            "client_name": client_name,
            "intake_content": intake_content,
            "uploaded_files": [f.name for f in st.session_state.uploaded_files],
            "suggested_practice_areas": practice_areas,
            "parsed_intake_data": intake_data,  # Derived from Q&A
            "intake_qa_pairs": qa_pairs,  # Single source of truth
        }

        # Move to the review step
        st.session_state.ui_step = "review"
        st.rerun()

    except Exception as e:
        st.error(f"Failed to process intake form for review: {e}")


def handle_analysis_start():
    """Kick off the main background analysis thread."""
    st.session_state.processing_status = "active"
    st.session_state.ui_step = "processing"
    st.session_state.final_results = None  # Clear previous results

    # Validate and prepare uploaded files for processing
    # handle_file_uploads() accesses st.session_state.uploaded_files directly
    # and sets intake_form and case_documents in session_state
    files_ready = handle_file_uploads()

    if not files_ready or not st.session_state.get("intake_form"):
        st.error("Could not find the intake form. Processing stopped.")
        st.session_state.processing_status = "failed"
        return

    # Create a queue for the thread to send results back
    result_queue = queue.Queue()
    st.session_state.result_queue = result_queue

    # Start the background thread
    thread = threading.Thread(
        target=run_processing_in_background,
        args=(
            st.session_state.intake_form,
            st.session_state.case_documents,
            st.session_state.case_info,  # Pass case_info
            st.session_state.review_data,  # Pass review_data
            result_queue,
        ),
        daemon=True,
    )
    st.session_state.processing_thread = thread
    thread.start()

    st.session_state.start_full_analysis = False  # Reset flag

    # Initialize progress tracking
    st.session_state.current_progress = {
        "message": "Starting analysis...",
        "documents_processed": [],
        "current_phase": "initializing",
        "progress_percent": 0,
    }
    st.session_state.processing_start_time = time.time()
    st.session_state.last_refresh_time = time.time()

    st.rerun()


def check_processing_status():
    """Check status with auto-refresh (every 10 seconds) and progress updates."""
    st.header("Processing Documents...")

    # Initialize auto-refresh timer
    if "last_refresh_time" not in st.session_state:
        st.session_state.last_refresh_time = time.time()

    # Initialize progress state
    if "current_progress" not in st.session_state:
        st.session_state.current_progress = {
            "message": "Initializing...",
            "documents_processed": [],
            "current_phase": "starting",
            "progress_percent": 0,
        }

    # Calculate countdown
    time_since_refresh = time.time() - st.session_state.last_refresh_time
    seconds_until_refresh = max(0, 10 - int(time_since_refresh))

    # Poll queue for updates (non-blocking)
    try:
        while True:
            result_data = st.session_state.result_queue.get_nowait()

            if result_data["type"] == "progress":
                # Update progress in session state
                st.session_state.current_progress = result_data

            elif result_data["type"] == "completed":
                # Processing complete
                result = result_data["result"]
                st.session_state.processing_status = "completed"
                st.session_state.ui_step = "results"
                st.session_state.main_letter = result.main_letter
                st.session_state.main_letter_with_citations = (
                    result.main_letter_with_citations
                )  # NEW: Cited version
                st.session_state.document_review = result.document_summaries
                st.session_state.case_analysis = result.case_analysis
                st.session_state.quality_report = result.quality_report
                st.session_state.final_results = {"status": "completed"}

                # Cleanup
                if "current_progress" in st.session_state:
                    del st.session_state.current_progress
                if "last_refresh_time" in st.session_state:
                    del st.session_state.last_refresh_time

                st.rerun()

            elif result_data["type"] == "failed":
                # Handle failure
                st.session_state.processing_status = "failed"
                st.session_state.ui_step = "results"
                st.session_state.processing_error = result_data.get("error")

                # Cleanup
                if "current_progress" in st.session_state:
                    del st.session_state.current_progress
                if "last_refresh_time" in st.session_state:
                    del st.session_state.last_refresh_time

                st.error(f"Processing failed: {st.session_state.processing_error}")
                st.rerun()

    except queue.Empty:
        pass  # No new messages

    # Display current progress
    progress_data = st.session_state.current_progress

    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(f"**Status:** {progress_data.get('message', 'Processing...')}")
    with col2:
        st.write(f"🔄 Next refresh: **{seconds_until_refresh}s**")

    # Show progress bar
    if progress_data.get("progress_percent", 0) > 0:
        st.progress(progress_data["progress_percent"] / 100)
    else:
        st.progress(0, text="Starting...")

    # Show processed documents list
    docs_processed = progress_data.get("documents_processed", [])
    if docs_processed:
        with st.expander(f"📄 Documents Processed ({len(docs_processed)})", expanded=False):
            for doc in docs_processed:
                st.write(f"✓ {doc}")

    # Show elapsed time
    if st.session_state.get("processing_start_time"):
        elapsed = time.time() - st.session_state.processing_start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
        st.write(f"**Time Elapsed:** {time_str}")

    # Check if thread is still alive
    if not st.session_state.processing_thread.is_alive():
        if st.session_state.processing_status != "completed":
            st.error("Processing stopped unexpectedly.")
            st.session_state.processing_status = "failed"
            st.session_state.ui_step = "results"
            st.rerun()

    # Auto-refresh every 10 seconds
    if time_since_refresh >= 10:
        st.session_state.last_refresh_time = time.time()
        st.rerun()

    # Small sleep to update countdown
    time.sleep(1)
    st.rerun()


# --- Main Execution ---
if __name__ == "__main__":
    main()
