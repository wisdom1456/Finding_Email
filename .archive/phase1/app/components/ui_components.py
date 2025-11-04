"""UI components for the Legal Document Analysis Portal."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


def case_information_form():
    """Render the case information form in the sidebar."""
    st.sidebar.header("Case Information")

    # Test Data Button
    st.sidebar.subheader("🧪 Quick Test")
    if st.sidebar.button(
        "🚀 Load Devlin Test Case",
        help="Loads test case data and files - manual analysis start required",
    ):
        load_devlin_test_case()
        return

    st.sidebar.text("---")

    st.session_state.case_info["clientName"] = st.sidebar.text_input(
        "Client Name", value=st.session_state.case_info["clientName"]
    )
    st.session_state.case_info["attorneyName"] = st.sidebar.text_input(
        "Attorney Name", value=st.session_state.case_info["attorneyName"]
    )
    st.session_state.case_info["caseReference"] = st.sidebar.text_input(
        "Case Reference", value=st.session_state.case_info["caseReference"]
    )


def load_devlin_test_case():
    """Load the Devlin test case data and files (manual analysis start required)."""
    try:
        # Set default case information
        st.session_state.case_info = {
            "clientName": "Erik Devlin",
            "attorneyName": "Bernhardt Riley",
            "caseReference": "Devlin v. LLW Construction - Contractor Dispute",
        }

        # Define test data path
        test_folder = Path(
            "test_data/Devlin, Erik [MetLife]/Shared Folder with Client/Shared with Bernhardt Riley"
        )

        if not test_folder.exists():
            st.sidebar.error(f"Test folder not found: {test_folder}")
            return

        # Load files from test directory
        uploaded_files = []
        supported_extensions = {
            ".pdf",
            ".docx",
            ".eml",
            ".txt",
            ".jpg",
            ".jpeg",
            ".png",
            ".mp3",
            ".m4a",
            ".wav",
            ".mp4",
            ".mov",
            ".avi",
        }

        for file_path in test_folder.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                # Create a mock uploaded file object
                try:
                    with open(file_path, "rb") as f:
                        file_content = f.read()

                    # Determine MIME type based on file extension
                    extension = file_path.suffix.lower()
                    mime_type_map = {
                        ".pdf": "application/pdf",
                        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        ".eml": "message/rfc822",
                        ".txt": "text/plain",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".png": "image/png",
                        ".mp3": "audio/mpeg",
                        ".m4a": "audio/mp4",
                        ".wav": "audio/wav",
                        ".mp4": "video/mp4",
                        ".mov": "video/quicktime",
                        ".avi": "video/x-msvideo",
                    }

                    # Create a proper mock file object that simulates Streamlit UploadedFile
                    class MockFile:
                        def __init__(self, name, content, mime_type):
                            self.name = name
                            self._content = content
                            self.type = mime_type
                            self.size = len(content)

                        def read(self, size=-1):
                            return self._content if size == -1 else self._content[:size]

                        def getvalue(self):
                            return self._content

                        def seek(self, offset, whence=0):
                            # Mock seek method - not actually used but may be expected
                            pass

                    mock_file = MockFile(
                        file_path.name,
                        file_content,
                        mime_type_map.get(extension, "application/octet-stream"),
                    )

                    uploaded_files.append(mock_file)
                except Exception as e:
                    st.sidebar.warning(f"Could not load {file_path.name}: {e}")

        if uploaded_files:
            st.session_state.uploaded_files = uploaded_files
            st.sidebar.success(f"✅ Loaded {len(uploaded_files)} test files and case information")
            st.sidebar.info("📋 Ready for analysis - click 'Start Analysis' when ready")
        else:
            st.sidebar.error("No supported files found in test directory")

    except Exception as e:
        st.sidebar.error(f"Error loading test case: {e}")


def file_upload_section():
    """Handle the file upload section, allowing folder uploads."""
    st.header("Upload Case Folder")
    uploaded_files = st.file_uploader(
        "Select a folder or multiple files (TXT, PDF, DOCX, DOC, PNG, JPG, EML, CSV files)",
        type=[
            "txt",
            "pdf",
            "docx",
            "doc",
            "png",
            "jpg",
            "jpeg",
            "eml",
            "csv",
        ],
        accept_multiple_files=True,
    )
    if uploaded_files:
        st.session_state.uploaded_files = uploaded_files


def results_display_section():
    """Display the final results and download links."""
    if st.session_state.get("final_results"):
        st.header("Results")

        # Display the main findings letter
        if st.session_state.get("main_letter"):
            st.subheader("Findings Letter")

            # Display the letter directly without cleaning citations
            components.html(st.session_state.main_letter, height=800, scrolling=True, width=None)

            # Provide download buttons
            st.subheader("Download Options")
            col1, col2, col3 = st.columns(3)
            _display_download_buttons(col1, col2, col3)
        else:
            st.info("The findings letter is being generated.")

        # Display any errors that occurred
        if st.session_state.get("errors"):
            st.error("Errors occurred during processing:")
            for error in st.session_state.errors:
                st.warning(f"**{error.source}**: {error.error_message}")


def _display_download_buttons(col1, col2, col3):
    """Display download buttons for the findings letter, document review, and case analysis."""
    # Get client name for filename
    client_name = "Client"
    if (
        st.session_state.get("final_results")
        and st.session_state.final_results.intake_analysis
        and st.session_state.final_results.intake_analysis.client_name
    ):
        client_name_raw = st.session_state.final_results.intake_analysis.client_name
        client_name = "".join(c for c in client_name_raw if c.isalnum() or c in " _-").rstrip()

    with col1:
        # Download button for main findings letter as HTML
        try:
            main_letter_bytes = st.session_state.main_letter.encode("utf-8")
            st.download_button(
                label="📧 Findings Letter",
                data=main_letter_bytes,
                file_name=f"Findings_Letter_{client_name}.html",
                mime="text/html",
                help="Download the findings letter in HTML format.",
            )
        except Exception as e:
            st.error(f"Error creating findings letter download: {e}")

    with col2:
        # Download button for document review
        try:
            # Assuming document review is stored in session state
            if st.session_state.get("document_review"):
                doc_review_bytes = st.session_state.document_review.encode("utf-8")
                st.download_button(
                    label="📄 Document Review",
                    data=doc_review_bytes,
                    file_name=f"Document_Review_{client_name}.txt",
                    mime="text/plain",
                    help="Download the document review.",
                )
        except Exception as e:
            st.error(f"Error creating document review download: {e}")

    with col3:
        # Download button for case analysis
        try:
            # Assuming case analysis is stored in session state as JSON
            if st.session_state.get("case_analysis"):
                case_analysis_str = json.dumps(st.session_state.case_analysis, indent=2)
                case_analysis_bytes = case_analysis_str.encode("utf-8")
                st.download_button(
                    label="⚖️ Case Analysis",
                    data=case_analysis_bytes,
                    file_name=f"Case_Analysis_{client_name}.json",
                    mime="application/json",
                    help="Download the case analysis.",
                )
        except Exception as e:
            st.error(f"Error creating case analysis download: {e}")
