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
        "ui_step": "upload",  # 'upload', 'preparing_review', 'review', 'processing', 'results'
        "review_data": {},  # Holds data for the review screen
        "start_full_analysis": False,  # Flag to start background thread
        "editable_qa_pairs": [],  # For the Q&A editor in review screen
        "confirmed_qa_pairs": [],  # Final confirmed Q&A after user review
        # CLIO Integration state
        "clio_authenticated": False,
        "clio_access_token": None,
        "clio_refresh_token": None,
        "clio_token_expires_at": None,
        "clio_selected_matter": None,
        "clio_matter_skipped": False,  # User explicitly skipped CLIO
        "clio_imported_data": None,
        "clio_processed_docs": [],
        "clio_matter_context": None,
        "data_source": "manual",  # 'manual', 'clio', or 'hybrid'
        # Preparation stage
        "preparation_thread": None,
        "preparation_status": "idle",  # idle, active, completed, failed
        "preparation_queue": None,  # Queue for preparation progress updates
        "preparation_error": None,  # Error message if preparation fails
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


def run_preparation_in_background(
    uploaded_files, clio_matter, clio_access_token, preparation_queue: queue.Queue
):
    """Prepare review data in background: import CLIO + process intake.

    Args:
    ----
        uploaded_files: List of uploaded Streamlit file objects
        clio_matter: Selected CLIO matter (or None)
        clio_access_token: CLIO OAuth token (or None)
        preparation_queue: Queue for progress updates

    """
    try:
        # Create event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def send_progress(message, status="in_progress"):
            """Send progress update."""
            preparation_queue.put({"type": "progress", "message": message, "status": status})

        # Step 1: Import CLIO data if matter selected
        clio_imported_data = None
        clio_processed_docs = []
        clio_matter_context = None

        if clio_matter:
            send_progress("Importing communications from CLIO...")

            try:
                from legal_portal.services.clio_client import ClioClient
                from legal_portal.services.clio_data_transformer import ClioDataTransformer

                client = ClioClient(clio_access_token)

                # Fetch communications
                communications = client.get_communications(clio_matter.id)
                send_progress(f"✓ Imported {len(communications)} communications", "done")

                # Fetch notes
                send_progress("Importing notes from CLIO...")
                notes = client.get_notes(clio_matter.id)
                send_progress(f"✓ Imported {len(notes)} notes", "done")

                # Fetch documents (metadata only)
                send_progress("Fetching document list from CLIO...")
                documents = client.get_documents(clio_matter.id)
                send_progress(f"✓ Found {len(documents)} documents", "done")

                # Fetch contacts
                send_progress("Fetching contact information...")
                contact_ids = set()
                for comm in communications:
                    contact_ids.add(comm.sender.id)
                    contact_ids.update([r.id for r in comm.recipients])
                contacts = client.get_contacts(list(contact_ids)) if contact_ids else []
                send_progress(f"✓ Retrieved {len(contacts)} contacts", "done")

                # Transform data
                send_progress("Processing CLIO data...")
                transformer = ClioDataTransformer()
                clio_processed_docs, clio_imported_data = transformer.transform_clio_import(
                    clio_matter, communications, notes, documents, contacts
                )
                clio_matter_context = clio_imported_data.matter_context
                send_progress(f"✓ Processed {len(clio_processed_docs)} items from CLIO", "done")

                logger.info(f"CLIO import successful: {len(clio_processed_docs)} items")

            except Exception as e:
                error_msg = f"CLIO import failed: {str(e)}"
                logger.error(error_msg, exc_info=True)
                preparation_queue.put({"type": "clio_error", "error": error_msg})
                return  # Stop here - let user decide to retry or continue

        # Step 2: Process intake form
        send_progress("Analyzing intake form...")

        intake_files = [f for f in uploaded_files if "intake" in f.name.lower()]
        if not intake_files:
            preparation_queue.put(
                {
                    "type": "failed",
                    "error": "No intake form found. Please upload a file with 'intake' in the name.",
                }
            )
            return

        intake_file = intake_files[0]

        # Process intake with DocumentProcessor
        from legal_portal.core.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        processed_intake = loop.run_until_complete(
            processor.process_documents_from_streamlit([intake_file], intake_filenames=["intake"])
        )

        if not processed_intake:
            preparation_queue.put({"type": "failed", "error": "Failed to extract content from intake form."})
            return

        intake_content = processed_intake[0].content
        send_progress("✓ Intake form processed", "done")

        # Step 3: Parse intake with AI
        send_progress("Extracting information from intake...")

        from legal_portal.utils.helpers import (
            build_structured_display_from_qa,
            extract_client_name_from_qa,
            identify_relevant_practice_areas_from_qa,
            parse_intake_form_qa_pairs,
        )

        qa_pairs = parse_intake_form_qa_pairs(intake_content)

        if not qa_pairs:
            logger.warning("Failed to extract Q&A from intake")
            qa_pairs = []

        send_progress(f"✓ Extracted {len(qa_pairs)} Q&A pairs", "done")

        # Step 4: Merge CLIO Q&A if available
        if clio_imported_data:
            send_progress("Merging CLIO data with intake...")
            clio_qa = clio_imported_data.auto_populated_qa
            existing_questions = {qa["question"].lower() for qa in qa_pairs}

            added_count = 0
            for clio_qa_item in clio_qa:
                if clio_qa_item["question"].lower() not in existing_questions:
                    qa_pairs.append(clio_qa_item)
                    added_count += 1

            send_progress(f"✓ Added {added_count} Q&A pairs from CLIO", "done")
            logger.info(f"Merged {added_count} CLIO Q&A pairs")

        # Step 5: Derive final data
        send_progress("Finalizing preparation...")

        client_name = extract_client_name_from_qa(qa_pairs)
        intake_data = build_structured_display_from_qa(qa_pairs)
        practice_areas = identify_relevant_practice_areas_from_qa(qa_pairs)

        # Use CLIO client name if not found in intake
        if not client_name and clio_imported_data:
            client_name = clio_imported_data.matter.client_name

        # Determine data source
        if clio_imported_data:
            data_source = "hybrid"
            all_files = list(uploaded_files) + clio_processed_docs
        else:
            data_source = "manual"
            all_files = uploaded_files

        file_names = [f.name if hasattr(f, "name") else f.file_name for f in all_files]

        # Build review data
        review_data = {
            "client_name": client_name,
            "intake_content": intake_content,
            "uploaded_files": file_names,
            "suggested_practice_areas": practice_areas,
            "parsed_intake_data": intake_data,
            "intake_qa_pairs": qa_pairs,
        }

        # Send completion
        preparation_queue.put(
            {
                "type": "completed",
                "review_data": review_data,
                "data_source": data_source,
                "clio_imported_data": clio_imported_data,
                "clio_processed_docs": clio_processed_docs,
                "clio_matter_context": clio_matter_context,
                "all_files": all_files,
            }
        )

        logger.info("Preparation completed successfully")

    except Exception as e:
        error_msg = f"Preparation failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        preparation_queue.put({"type": "failed", "error": error_msg})
    finally:
        loop.close()


def show_preparation_screen():
    """Display preparation progress with granular feedback."""
    st.header("⚙️ Preparing Your Case...")

    # Check if thread is running
    if not st.session_state.preparation_thread or not st.session_state.preparation_thread.is_alive():
        # Thread finished or crashed
        st.session_state.preparation_status = "completed"

    # Create progress container
    progress_container = st.container()

    with progress_container:
        # Check queue for messages
        messages = []
        clio_error = None
        completion_data = None

        while st.session_state.preparation_queue and not st.session_state.preparation_queue.empty():
            try:
                msg = st.session_state.preparation_queue.get_nowait()

                if msg["type"] == "progress":
                    messages.append(msg)
                elif msg["type"] == "clio_error":
                    clio_error = msg["error"]
                    st.session_state.preparation_status = "clio_failed"
                elif msg["type"] == "completed":
                    completion_data = msg
                    st.session_state.preparation_status = "completed"
                elif msg["type"] == "failed":
                    st.session_state.preparation_error = msg["error"]
                    st.session_state.preparation_status = "failed"

            except queue.Empty:
                break

        # Display progress messages
        if messages:
            for msg in messages:
                status_icon = "✓" if msg.get("status") == "done" else "⏳"
                st.text(f"{status_icon} {msg['message']}")

        # Handle CLIO error with retry/skip options
        if st.session_state.preparation_status == "clio_failed":
            st.error(f"**CLIO Import Error:**\n\n{clio_error}")
            st.warning("You can retry the CLIO import or continue with manual files only.")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Retry CLIO Import", use_container_width=True):
                    # Reset and restart preparation
                    st.session_state.preparation_status = "idle"
                    st.session_state.preparation_error = None
                    st.rerun()

            with col2:
                if st.button("Continue with Manual Files Only", use_container_width=True):
                    # Clear CLIO matter and restart preparation
                    st.session_state.clio_selected_matter = None
                    st.session_state.clio_matter_skipped = True
                    st.session_state.preparation_status = "idle"
                    st.session_state.preparation_error = None
                    st.rerun()

        # Handle general failure
        elif st.session_state.preparation_status == "failed":
            st.error(f"**Preparation Failed:**\n\n{st.session_state.preparation_error}")

            if st.button("← Back to Upload"):
                st.session_state.ui_step = "upload"
                st.session_state.preparation_status = "idle"
                st.session_state.preparation_error = None
                st.rerun()

        # Handle completion
        elif st.session_state.preparation_status == "completed" and completion_data:
            st.success("✅ Preparation complete! Transitioning to review...")

            # Store results in session state
            review_data = completion_data["review_data"]

            # Add CLIO context to review_data so it's available in background thread
            if completion_data.get("clio_matter_context"):
                review_data["clio_matter_context"] = completion_data["clio_matter_context"]

            st.session_state.review_data = review_data
            st.session_state.data_source = completion_data["data_source"]
            st.session_state.clio_imported_data = completion_data.get("clio_imported_data")
            st.session_state.clio_processed_docs = completion_data.get("clio_processed_docs", [])
            st.session_state.clio_matter_context = completion_data.get("clio_matter_context")
            st.session_state.uploaded_files = completion_data["all_files"]

            # Transition to review
            st.session_state.ui_step = "review"
            st.rerun()

        # Still processing
        else:
            with st.spinner("Processing..."):
                time.sleep(0.5)
                st.rerun()


def handle_preparation_start():
    """Validate inputs and start the preparation background thread."""
    # Validate uploaded files
    if not st.session_state.get("uploaded_files"):
        st.error("Please upload files before proceeding.")
        return

    # Check for intake form
    uploaded_files = st.session_state.uploaded_files
    intake_files = [f for f in uploaded_files if "intake" in f.name.lower()]

    if not intake_files:
        st.error("Please upload an intake form (filename must contain 'intake').")
        return

    # Prepare for background processing
    clio_matter = st.session_state.get("clio_selected_matter")
    clio_token = st.session_state.get("clio_access_token")

    # Create queue for progress updates
    st.session_state.preparation_queue = queue.Queue()
    st.session_state.preparation_status = "active"
    st.session_state.preparation_error = None

    # Start background thread
    preparation_thread = threading.Thread(
        target=run_preparation_in_background,
        args=(uploaded_files, clio_matter, clio_token, st.session_state.preparation_queue),
        daemon=True,
    )
    preparation_thread.start()
    st.session_state.preparation_thread = preparation_thread

    # Transition to preparation screen
    st.session_state.ui_step = "preparing_review"
    st.rerun()


def prepare_files_for_analysis(uploaded_files, compress_flag):
    """Save uploaded files and compress them if needed.

    Handles both Streamlit UploadedFile objects and ProcessedDocument objects (from CLIO).
    Automatically extracts zip files and processes their contents.

    Args:
    ----
        uploaded_files: List of UploadedFile or ProcessedDocument objects
        compress_flag: Boolean indicating whether to compress large files

    Returns:
    -------
        Tuple of (intake_path, case_document_paths)

    """
    import zipfile

    from legal_portal.core.data_models import ProcessedDocument

    if "session_temp_dir" not in st.session_state or not st.session_state.session_temp_dir:
        # Create a unique, secure temporary directory for this session
        st.session_state.session_temp_dir = tempfile.mkdtemp(prefix="legal_portal_")
        logger.info(f"Created temporary directory: {st.session_state.session_temp_dir}")

    temp_dir = st.session_state.session_temp_dir
    final_file_paths = []
    compressor = FileCompressionService() if compress_flag else None

    # Define video and audio file extensions to skip
    video_audio_extensions = [
        ".mov",
        ".mp4",
        ".avi",
        ".mkv",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",  # Video
        ".mp3",
        ".wav",
        ".aac",
        ".flac",
        ".m4a",
        ".ogg",
        ".wma",
        ".aiff",  # Audio
    ]

    with st.spinner("Preparing and compressing files..."):
        for uploaded_file in uploaded_files:
            try:
                # Get file name for both types of objects
                file_name = getattr(uploaded_file, "name", None) or getattr(
                    uploaded_file, "file_name", "unknown"
                )

                # Skip video and audio files
                if any(file_name.lower().endswith(ext) for ext in video_audio_extensions):
                    logger.info(f"⏭️  Skipping video/audio file: {file_name}")
                    st.info(f"⏭️  Skipping video/audio file: {file_name}")
                    continue

                # Check if this is a ProcessedDocument (from CLIO) or UploadedFile
                if isinstance(uploaded_file, ProcessedDocument):
                    # This is already processed from CLIO - save its content to a temp file
                    file_name = uploaded_file.file_name
                    temp_file_path = os.path.join(temp_dir, file_name)

                    # Save the already-extracted content as text
                    with open(temp_file_path, "w", encoding="utf-8") as f:
                        f.write(uploaded_file.content)

                    # CLIO documents are already processed, no need to compress
                    final_file_paths.append(temp_file_path)
                    logger.info(f"Saved CLIO document: {file_name}")

                else:
                    # This is an UploadedFile - save and optionally compress
                    temp_file_path = os.path.join(temp_dir, uploaded_file.name)
                    with open(temp_file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    # Check if this is a zip file - extract it
                    if uploaded_file.name.lower().endswith(".zip"):
                        logger.info(f"📦 Extracting zip file: {uploaded_file.name}")

                        # Display zip file with yellow highlight
                        st.markdown(
                            f'<div style="background-color: #fff3cd; padding: 8px 12px; '
                            f'border-radius: 4px; margin: 8px 0; border-left: 4px solid #ffc107;">'
                            f'<span style="font-weight: 600;">📦 Extracting: {uploaded_file.name}</span>'
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                        try:
                            # Create subdirectory for this zip's contents
                            zip_extract_dir = os.path.join(
                                temp_dir, Path(uploaded_file.name).stem + "_extracted"
                            )
                            os.makedirs(zip_extract_dir, exist_ok=True)

                            # Extract zip file
                            with zipfile.ZipFile(temp_file_path, "r") as zip_ref:
                                zip_ref.extractall(zip_extract_dir)

                            # Force filesystem sync to prevent race conditions
                            # Increased delay to 500ms for more reliable extraction
                            await asyncio.sleep(0.5)

                            # Add extracted files to processing list (filtering out video/audio)
                            extracted_count = 0
                            skipped_count = 0
                            extracted_files_list = []
                            skipped_files_list = []

                            for root, _dirs, files in os.walk(zip_extract_dir):
                                for extracted_file in files:
                                    # Skip hidden files and system files
                                    if extracted_file.startswith(".") or extracted_file.startswith(
                                        "__MACOSX"
                                    ):
                                        continue

                                    # Skip video/audio files
                                    if any(
                                        extracted_file.lower().endswith(ext) for ext in video_audio_extensions
                                    ):
                                        logger.info(f"  ⏭️  Skipping video/audio: {extracted_file}")
                                        skipped_files_list.append(extracted_file)
                                        skipped_count += 1
                                        continue

                                    extracted_path = os.path.join(root, extracted_file)

                                    # Verify file exists before processing (filesystem sync check)
                                    if not os.path.isfile(extracted_path):
                                        logger.warning(
                                            f"Extracted file not found (filesystem sync issue?): {extracted_path}"
                                        )
                                        continue

                                    # Optionally compress extracted file
                                    if compressor:
                                        final_path = compressor.process_file(extracted_path)
                                    else:
                                        final_path = extracted_path

                                    final_file_paths.append(final_path)
                                    extracted_files_list.append(extracted_file)
                                    extracted_count += 1

                            # Display extracted files with indentation
                            if extracted_files_list:
                                for extracted_file in extracted_files_list[:5]:  # Show first 5
                                    st.markdown(
                                        f'<div style="padding: 2px 12px 2px 32px; color: #666; font-size: 0.9em;">'
                                        f"  ✓ ↳ {extracted_file}"
                                        f"</div>",
                                        unsafe_allow_html=True,
                                    )
                                if len(extracted_files_list) > 5:
                                    st.markdown(
                                        f'<div style="padding: 2px 12px 2px 32px; color: #666; font-size: 0.9em; font-style: italic;">'
                                        f"  ... and {len(extracted_files_list) - 5} more file(s)"
                                        f"</div>",
                                        unsafe_allow_html=True,
                                    )

                            # Show summary
                            logger.info(f"✅ Extracted {extracted_count} files from {uploaded_file.name}")
                            summary_parts = []
                            if extracted_count > 0:
                                summary_parts.append(
                                    f"{extracted_count} file(s) extracted and will be processed"
                                )
                            if skipped_count > 0:
                                summary_parts.append(f"{skipped_count} video/audio file(s) skipped")

                            st.markdown(
                                f'<div style="padding: 4px 12px 4px 32px; color: #28a745; font-size: 0.9em;">'
                                f"  ℹ️ {', '.join(summary_parts)}"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                            # Remove the original zip file
                            os.remove(temp_file_path)

                        except zipfile.BadZipFile:
                            logger.error(f"Invalid zip file: {uploaded_file.name}")
                            st.warning(f"⚠️ Could not extract {uploaded_file.name} - invalid zip file")
                        except Exception as e:
                            logger.error(f"Failed to extract zip file {uploaded_file.name}: {e}")
                            st.warning(f"⚠️ Could not extract {uploaded_file.name}: {str(e)}")

                    else:
                        # Regular file (not a zip) - process normally
                        # If compression is enabled, process the file
                        if compressor:
                            final_path = compressor.process_file(temp_file_path)
                        else:
                            final_path = temp_file_path

                        final_file_paths.append(final_path)

            except Exception as e:
                # Handle both types of file names
                file_name = getattr(uploaded_file, "name", None) or getattr(
                    uploaded_file, "file_name", "unknown"
                )
                logger.error(f"Failed to prepare file {file_name}. Error: {e}")
                st.warning(f"Could not process file: {file_name}. It will be skipped.")

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

    # Check for authentication token in query params (from OAuth redirect)
    query_params = st.query_params
    if "auth_token" in query_params and not st.session_state.authenticated:
        auth_token = query_params["auth_token"]
        # Validate token format (simple check)
        if auth_token and len(auth_token) == 32:
            st.session_state.authenticated = True
            st.session_state.auth_token = auth_token
            logger.info("Restored authentication from OAuth redirect")

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
                    # Generate authentication token
                    import secrets

                    auth_token = secrets.token_hex(16)
                    st.session_state.authenticated = True
                    st.session_state.auth_token = auth_token
                    st.success("✅ Access granted!")
                    st.rerun()
                else:
                    st.error("❌ Incorrect PIN. Please try again.")

        st.stop()

    # Generate auth token if not present (for existing sessions)
    if "auth_token" not in st.session_state:
        import secrets

        st.session_state.auth_token = secrets.token_hex(16)


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

        # Display practice area guidance
        with st.expander("ℹ️ Supported Practice Areas (Florida law only)", expanded=False):
            st.markdown(
                """
            **This application is optimized for Florida civil litigation matters only.**
            Federal claims and non-Florida jurisdictions are not currently supported.

            ### ✅ Covered Practice Areas:

            **1. Consumer Protection & Business Misconduct**
            - Contract disputes and breach claims (UCC Ch. 671-672)
            - Consumer protection violations (FDUTPA - Ch. 501 Part II)
            - Business organization disputes (Ch. 605 LLC, Ch. 607 Corp)
            - Timeshare disputes and related matters

            **2. Real Estate & Property Disputes**
            - Landlord-tenant disputes (Ch. 83)
            - Foreclosure defense and procedures (Ch. 702)
            - Property damage and insurance claims (Ch. 627)
            - Construction defects (Ch. 558)
            - Mechanic's liens (Ch. 713)

            **3. Civil Litigation & Administrative Law**
            - Statutes of limitation (Ch. 95)
            - Administrative procedure matters (Ch. 120)
            - Copyright matters (only insofar as Florida law intersects)
            - Attorney fees and sanctions (Ch. 57)

            **4. Selective Personal Injury**
            - Motorcycle accidents (Ch. 316 traffic law)
            - Limited medical malpractice matters (Ch. 766)

            ### ⚠️ Not Supported:
            - Federal claims or federal court matters
            - Criminal law
            - Immigration law
            - Bankruptcy (federal jurisdiction)
            - Patent/trademark law (federal jurisdiction)
            - Out-of-state matters

            **If your case involves federal law or multi-jurisdiction issues,
            please consult with the attorney before proceeding.**
            """
            )

        file_upload_section()

        # Show "Prepare for Review" button only if files are uploaded
        if st.session_state.get("uploaded_files") and len(st.session_state.uploaded_files) > 0:
            st.divider()
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("📋 Prepare for Review", use_container_width=True, type="primary"):
                    handle_preparation_start()

    elif st.session_state.ui_step == "preparing_review":
        # New preparation screen with granular progress
        show_preparation_screen()

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

                # DEBUG: Log what we received
                logger.info(f"DEBUG: Received result type: {type(result)}")
                logger.info(
                    f"DEBUG: Has main_letter: {hasattr(result, 'main_letter') if not isinstance(result, dict) else 'main_letter' in result}"
                )
                logger.info(
                    f"DEBUG: Has document_summaries: {hasattr(result, 'document_summaries') if not isinstance(result, dict) else 'document_summaries' in result}"
                )

                st.session_state.processing_status = "completed"
                st.session_state.ui_step = "results"
                st.session_state.final_results = result

                # Handle both dict and object formats
                if isinstance(result, dict):
                    st.session_state.document_review = result.get("document_summaries", "")
                    st.session_state.case_analysis = result.get("case_analysis", "")
                    st.session_state.main_letter = result.get("main_letter", "")
                    st.session_state.main_letter_with_citations = result.get("main_letter_with_citations", "")
                    logger.info(
                        f"DEBUG: Stored dict results - main_letter length: {len(result.get('main_letter', ''))}, doc_summaries length: {len(result.get('document_summaries', ''))}"
                    )
                else:
                    st.session_state.document_review = result.document_summaries
                    st.session_state.case_analysis = result.case_analysis
                    st.session_state.main_letter = result.main_letter  # Store findings email
                    st.session_state.main_letter_with_citations = (
                        result.main_letter_with_citations
                    )  # Store cited letter
                    logger.info(
                        f"DEBUG: Stored object results - main_letter length: {len(result.main_letter)}, doc_summaries length: {len(result.document_summaries)}"
                    )

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

    # Check if this is multi-stage analysis (new system)
    current_phase = progress_data.get("current_phase", "starting")
    is_multi_stage = current_phase in [
        "fact_extraction",
        "issue_mapping",
        "deep_analysis",
        "letter_generation",
        "final_review",
    ]

    if is_multi_stage:
        # Enhanced display for multi-stage analysis
        st.subheader("📊 Multi-Stage Analysis Progress")

        # Metrics row
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.metric("Current Stage", progress_data.get("message", "Processing..."))
        with col2:
            st.metric("Overall Progress", f"{progress_data.get('progress_percent', 0):.0f}%")
        with col3:
            if st.session_state.get("processing_start_time"):
                elapsed = time.time() - st.session_state.processing_start_time
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                st.metric("Time Elapsed", time_str)

        # Stage breakdown visual
        st.write("**Analysis Stages:**")

        # Define stages with their status
        stages_config = [
            ("Fact Extraction", "fact_extraction", "🔍"),
            ("Issue Mapping", "issue_mapping", "⚖️"),
            ("Legal Analysis", "deep_analysis", "📊"),
            ("Findings Email & Demand Letter", "letter_generation", "✍️"),
            ("Final Review", "final_review", "✅"),
        ]

        # Determine status for each stage
        stage_progress = progress_data.get("stages", {})

        for stage_name, stage_key, icon in stages_config:
            status = stage_progress.get(stage_name, "pending")

            if stage_key == current_phase:
                st.info(f"⏳ {icon} **{stage_name}** - In Progress")
            elif status == "completed" or (
                stages_config.index((stage_name, stage_key, icon))
                < [s[1] for s in stages_config].index(current_phase)
            ):
                st.success(f"✓ {icon} {stage_name}")
            else:
                st.text(f"○ {icon} {stage_name}")

        # Overall progress bar
        st.progress(progress_data.get("progress_percent", 0) / 100)

        # Refresh countdown
        st.caption(f"🔄 Next refresh: {seconds_until_refresh}s")

    else:
        # Legacy display for backwards compatibility
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

    # Show elapsed time (only for legacy mode, multi-stage already shows it in metrics)
    if not is_multi_stage and st.session_state.get("processing_start_time"):
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
