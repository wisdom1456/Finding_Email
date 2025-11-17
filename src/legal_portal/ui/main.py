"""Main Streamlit UI for the Legal Document Analysis Portal."""

from __future__ import annotations

import asyncio
import os
import queue
import shutil
import tempfile
import threading
import time
from pathlib import Path

import streamlit as st

# NOTE: analysis.engine is old/experimental code - using main_processor instead
from legal_portal.services.file_compression_service import FileCompressionService
from legal_portal.services.main_processor import process_case_documents
from legal_portal.ui.components.ui_components import (
    case_information_form,
    file_upload_section,
    results_display_section,
)
from legal_portal.utils.logging_config import get_module_logger, setup_logging

# Initialize logging
setup_logging(app_name="legal-portal", level=os.getenv("LOG_LEVEL", "INFO"))
logger = get_module_logger(__name__)

# PIN Authentication
APP_PIN = os.getenv("APP_ACCESS_PIN", "0101")


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
        "main_letter_with_citations": None,
        "document_review": None,
        "case_analysis": None,
        "quality_report": None,  # For the new quality report tab
        "processing_status": "idle",  # idle, active, completed, failed
        "processing_error": None,
        "processing_thread": None,
        "processing_progress": "",  # Current processing step
        "processing_start_time": None,
        "result_queue": None,  # Thread-safe queue for results
        "session_temp_dir": None,  # For temporary file processing
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
    intake_form_path, case_document_paths, case_info, review_data, result_queue: queue.Queue
):
    """Run document processing in a background thread using asyncio.

    Uses a thread-safe queue to communicate the final result back to the UI.

    Args:
    ----
        intake_form_path: File path to the intake form
        case_document_paths: List of file paths to case documents
        case_info: Case metadata dictionary
        review_data: Review data dictionary
        result_queue: Thread-safe queue for results

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

        # Process documents using the main processor
        final_report = loop.run_until_complete(
            process_case_documents(
                intake_form_path=intake_form_path,
                case_document_paths=case_document_paths,
                case_info=case_info,
                review_data=review_data,
                progress_callback=send_progress,
            )
        )

        # Send ONE final message to the queue
        result_queue.put({"type": "completed", "result": final_report})
        print("DEBUG [Background Thread]: Sent completion to queue")

    except Exception as e:
        # Send error through queue
        error_msg = str(e)

        # Provide more helpful error messages for common issues
        if "APITimeoutError" in error_msg or "Request timed out" in error_msg:
            error_msg = (
                "OpenAI API timeout - The AI service took too long to respond. "
                "This usually means the model is overloaded. "
                "Please try again in a few minutes."
            )
        elif "RetryError" in error_msg:
            error_msg = (
                "Multiple API failures - The AI service failed after several "
                "retry attempts. Please check your internet connection and try again."
            )

        result_queue.put({"type": "failed", "error": error_msg})
        print(f"DEBUG [Background Thread]: Sent exception to queue: {error_msg}")

    finally:
        # Clean up the event loop
        loop.close()

        # Clean up the temporary directory
        if st.session_state.get("session_temp_dir"):
            try:
                shutil.rmtree(st.session_state.session_temp_dir)
                logger.info(f"Successfully cleaned up temp directory: {st.session_state.session_temp_dir}")
                st.session_state.session_temp_dir = None
            except Exception as e:
                logger.error(f"Failed to clean up temp directory. Error: {e}")


def prepare_files_for_analysis(uploaded_files, compress_flag):
    """Save uploaded files and compress them if needed.

    Saves uploaded files to a temporary directory, compresses them if needed,
    and returns a list of final file paths for intake and case documents.

    Args:
    ----
        uploaded_files: List of Streamlit UploadedFile objects
        compress_flag: Boolean indicating whether to compress large files

    Returns:
    -------
        Tuple of (intake_path, case_document_paths)

    """
    if "session_temp_dir" not in st.session_state or not st.session_state.session_temp_dir:
        # Create a unique, secure temporary directory for this session
        st.session_state.session_temp_dir = tempfile.mkdtemp(prefix="legal_portal_")
        logger.info(f"Created temporary directory: {st.session_state.session_temp_dir}")

    temp_dir = st.session_state.session_temp_dir
    final_file_paths = []
    compressor = FileCompressionService() if compress_flag else None

    with st.spinner("Preparing and compressing files..."):
        for uploaded_file in uploaded_files:
            try:
                # Save the file to the temporary directory
                temp_file_path = os.path.join(temp_dir, uploaded_file.name)
                with open(temp_file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # If compression is enabled, process the file
                if compressor:
                    # The process_file method handles the size check and compression in-place
                    final_path = compressor.process_file(temp_file_path)
                else:
                    final_path = temp_file_path

                final_file_paths.append(final_path)

            except Exception as e:
                logger.error(f"Failed to prepare file {uploaded_file.name}. Error: {e}")
                # Optionally, alert the user
                st.warning(f"Could not process file: {uploaded_file.name}. It will be skipped.")

    # Separate intake form from other documents based on the final file paths
    intake_path = None
    case_document_paths = []
    for path in final_file_paths:
        if "intake" in Path(path).name.lower():
            intake_path = path
        else:
            case_document_paths.append(path)

    return intake_path, case_document_paths


# --- PIN Authentication Check ---
def check_authentication():
    """Check if user is authenticated with PIN."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("🔒 Legal Portal Access")
        st.markdown("### Enter PIN to Continue")

        pin_input = st.text_input(
            "Access PIN", type="password", max_chars=4, help="Enter the 4-digit PIN to access the portal"
        )

        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("🔓 Unlock", use_container_width=True):
                if pin_input == APP_PIN:
                    st.session_state.authenticated = True
                    st.success("✅ Access granted!")
                    st.rerun()
                else:
                    st.error("❌ Incorrect PIN. Please try again.")

        st.stop()


# --- Main Application ---
def main():
    """Run the Streamlit application."""
    # --- Page Configuration ---
    st.set_page_config(
        page_title="Bernhardt Riley | Document Analysis Portal",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Check Authentication First ---
    check_authentication()

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
                        "⚠️ Failed to extract information from intake form. "
                        "You can manually enter the details in the review screen."
                    )
                    qa_pairs = []

                # Derive all other data from Q&A pairs (no additional AI calls)
                logger.info("Deriving structured data from Q&A pairs")
                client_name = extract_client_name_from_qa(qa_pairs)
                intake_data = build_structured_display_from_qa(qa_pairs)
                practice_areas = identify_relevant_practice_areas_from_qa(qa_pairs)

                logger.info(
                    f"Successfully processed intake: {len(qa_pairs)} Q&A pairs, "
                    f"client: '{client_name}', {len(practice_areas)} practice areas"
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

    # --- New File Preparation Workflow ---
    if not st.session_state.get("uploaded_files"):
        st.error("No files were uploaded. Processing stopped.")
        st.session_state.processing_status = "failed"
        return

    # Prepare files, compressing if the user opted in
    intake_form_path, case_document_paths = prepare_files_for_analysis(
        st.session_state.uploaded_files, st.session_state.get("compress_files", False)
    )

    if not intake_form_path:
        st.error("Could not find or process the intake form. Processing stopped.")
        st.session_state.processing_status = "failed"
        # Clean up the directory if processing fails early
        if st.session_state.get("session_temp_dir"):
            shutil.rmtree(st.session_state.session_temp_dir)
        return

    # Store the paths in session_state for the background thread
    st.session_state.intake_form_path = intake_form_path
    st.session_state.case_document_paths = case_document_paths
    # --- End of New Workflow ---

    # Create a queue for the thread to send results back
    result_queue = queue.Queue()
    st.session_state.result_queue = result_queue

    # Start the background thread with file paths
    thread = threading.Thread(
        target=run_processing_in_background,
        args=(
            st.session_state.intake_form_path,
            st.session_state.case_document_paths,
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
                st.session_state.final_results = result
                st.session_state.document_review = result.document_summaries
                st.session_state.case_analysis = result.case_analysis
                st.session_state.main_letter = result.main_letter  # Store findings letter
                st.session_state.main_letter_with_citations = (
                    result.main_letter_with_citations
                )  # Store cited letter

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
