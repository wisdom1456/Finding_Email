import streamlit as st
import requests
import json
import os
import time
import base64
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
BACKEND_URL = os.getenv('BACKEND_API_URL', 'http://localhost:8000')
API_TIMEOUT = 600  # 10 minutes for large document processing
POLLING_INTERVAL = 5 # 5 seconds

# --- API Endpoints ---
START_ANALYSIS_ENDPOINT = f"{BACKEND_URL}/api/v1/analysis/start-analysis"
STATUS_ENDPOINT = f"{BACKEND_URL}/api/v1/analysis/status"
RESULTS_ENDPOINT = f"{BACKEND_URL}/api/v1/analysis/results"


# --- Session State Initialization ---
def initialize_session_state():
    """Initializes the session state with default values."""
    if 'case_info' not in st.session_state:
        st.session_state.case_info = {"clientName": "", "attorneyName": "", "caseReference": ""}
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = {"intake_form": None, "case_documents": []}
    if 'final_results' not in st.session_state:
        st.session_state.final_results = None
    if 'main_letter' not in st.session_state:
        st.session_state.main_letter = None
    if 'appendix' not in st.session_state:
        st.session_state.appendix = None
    if 'processing_status' not in st.session_state:
        st.session_state.processing_status = 'idle'  # idle, active, completed, failed
    if 'task_id' not in st.session_state:
        st.session_state.task_id = None

# --- UI Components ---
def case_information_form():
    """Renders the case information form in the sidebar."""
    st.sidebar.header("Case Information")
    st.session_state.case_info['clientName'] = st.sidebar.text_input("Client Name", value=st.session_state.case_info['clientName'])
    st.session_state.case_info['attorneyName'] = st.sidebar.text_input("Attorney Name", value=st.session_state.case_info['attorneyName'])
    st.session_state.case_info['caseReference'] = st.sidebar.text_input("Case Reference", value=st.session_state.case_info['caseReference'])

def file_upload_section():
    """Handles the file upload section, allowing folder uploads."""
    st.header("Upload Case Folder")
    uploaded_files = st.file_uploader(
        "Select a folder or multiple files (PDF, DOCX, EML, TXT, JPG, PNG)",
        type=["pdf", "docx", "eml", "txt", "jpg", "jpeg", "png"],
        accept_multiple_files=True
    )
    if uploaded_files:
        st.session_state.uploaded_files = uploaded_files

def handle_file_uploads():
    """
    Identifies intake documents from uploaded files and prompts for clarification if needed.
    Returns True if analysis can proceed, False otherwise.
    """
    uploaded_files = st.session_state.get('uploaded_files', [])
    if not uploaded_files:
        st.error("Please upload at least one document.")
        return False

    intake_docs = [f for f in uploaded_files if "intake" in f.name.lower()]
    
    if len(intake_docs) == 1:
        st.session_state.intake_form = intake_docs[0]
        st.session_state.case_documents = [f for f in uploaded_files if f != intake_docs[0]]
        st.info(f"Automatically detected '{intake_docs[0].name}' as the intake form.")
        return True
    elif len(intake_docs) > 1:
        st.warning("Multiple possible intake forms found.")
        selected_intake_name = st.selectbox(
            "Please select the correct intake form:",
            [f.name for f in intake_docs]
        )
        st.session_state.intake_form = next(f for f in intake_docs if f.name == selected_intake_name)
        st.session_state.case_documents = [f for f in uploaded_files if f != st.session_state.intake_form]
        return True
    else: # No intake docs found
        st.warning("No intake form automatically detected.")
        selected_intake_name = st.selectbox(
            "Please select the intake form from the uploaded documents:",
            [f.name for f in uploaded_files]
        )
        if selected_intake_name:
            st.session_state.intake_form = next(f for f in uploaded_files if f.name == selected_intake_name)
            st.session_state.case_documents = [f for f in uploaded_files if f != st.session_state.intake_form]
            return True
    return False


def start_analysis():
    """Handles file processing with asynchronous request."""
    intake_form = st.session_state.get('intake_form')
    case_documents = st.session_state.get('case_documents')

    if not intake_form:
        st.error("An intake form is required to start the analysis.")
        return

    # Prepare files for upload
    files = [('intake_form', (intake_form.name, intake_form.getvalue(), intake_form.type))]
    for doc in case_documents:
        files.append(('case_documents', (doc.name, doc.getvalue(), doc.type)))

    try:
        response = requests.post(
            START_ANALYSIS_ENDPOINT,
            files=files,
            timeout=API_TIMEOUT
        )
        response.raise_for_status()
        
        result = response.json()
        st.session_state.task_id = result.get("task_id")
        st.session_state.processing_status = 'active'
        st.rerun()

    except requests.exceptions.RequestException as e:
        st.error(f"An error occurred during processing: {e}")
    except json.JSONDecodeError as e:
        st.error(f"Error parsing response: {e}")

def monitor_progress():
    """Polls for progress and updates the UI."""
    if st.session_state.task_id:
        st.info("Analysis in progress...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        doc_progress_text = st.empty()

        while st.session_state.processing_status == 'active':
            try:
                status_url = f"{STATUS_ENDPOINT}/{st.session_state.task_id}"
                response = requests.get(status_url, timeout=API_TIMEOUT)
                response.raise_for_status()
                status_data = response.json()

                progress = status_data.get("progress", 0)
                status = status_data.get("status", "processing")
                
                progress_bar.progress(progress / 100.0)
                status_text.text(f"Status: {status.capitalize()}")

                if status in ["pending", "processing"]:
                    total_docs = status_data.get("total_documents", 0)
                    current_doc = status_data.get("current_document", 0)
                    doc_name = status_data.get("current_document_name", "")
                    if total_docs > 0:
                        doc_progress_text.text(f"Processing document {current_doc}/{total_docs}: {doc_name}")
                
                elif status == "completed":
                    st.session_state.processing_status = 'completed'
                    st.success("Analysis complete!")
                    retrieve_and_display_results()
                    break

                elif status == "failed":
                    st.session_state.processing_status = 'failed'
                    error_message = status_data.get("error_message", "An unknown error occurred.")
                    st.error(f"Analysis failed: {error_message}")
                    break
                
                time.sleep(POLLING_INTERVAL)

            except requests.exceptions.RequestException as e:
                st.error(f"Error checking status: {e}")
                st.session_state.processing_status = 'failed'
                break

def retrieve_and_display_results():
    """Retrieves and displays the final analysis results."""
    if st.session_state.task_id:
        try:
            results_url = f"{RESULTS_ENDPOINT}/{st.session_state.task_id}"
            response = requests.get(results_url, timeout=API_TIMEOUT)
            response.raise_for_status()
            
            results = response.json()
            st.session_state.final_results = results
            
            # Parse new two-document format
            if isinstance(results, dict) and "main_letter" in results and "appendix" in results:
                st.session_state.main_letter = results["main_letter"]
                st.session_state.appendix = results["appendix"]
            else:
                # Fallback for legacy format
                st.session_state.main_letter = None
                st.session_state.appendix = None
            
            st.session_state.processing_status = 'completed'

        except requests.exceptions.RequestException as e:
            st.error(f"Failed to retrieve results: {e}")
            st.session_state.processing_status = 'failed'
        except json.JSONDecodeError as e:
            st.error(f"Error parsing results: {e}")


def results_display_section():
    """Displays the final results and download links."""
    if st.session_state.final_results:
        st.header("Results")
        
        # Check if we have the new two-document format
        if st.session_state.main_letter and st.session_state.appendix:
            # Display the main findings letter inline
            st.subheader("Findings Letter")
            st.markdown(st.session_state.main_letter, unsafe_allow_html=True)
            
            # Provide separate download buttons for both documents
            st.subheader("Download Options")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Download button for main findings letter
                try:
                    main_letter_bytes = st.session_state.main_letter.encode('utf-8')
                    st.download_button(
                        label="Download Findings Letter",
                        data=main_letter_bytes,
                        file_name="Findings Letter.eml",
                        mime="message/rfc822"
                    )
                except Exception as e:
                    st.error(f"Error creating findings letter download: {e}")
            
            with col2:
                # Download button for document appendix
                try:
                    appendix_bytes = st.session_state.appendix.encode('utf-8')
                    st.download_button(
                        label="Download Document Appendix",
                        data=appendix_bytes,
                        file_name="Document Appendix.eml",
                        mime="message/rfc822"
                    )
                except Exception as e:
                    st.error(f"Error creating appendix download: {e}")
                    
        else:
            # Fallback: Display legacy format if new format is not available
            results = st.session_state.final_results
            
            # Display analysis findings
            if results.get("analysis") and results["analysis"].get("findings_html"):
                st.subheader("Findings")
                st.markdown(results["analysis"]["findings_html"], unsafe_allow_html=True)

            # Display case analysis text
            if results.get("email") and results["email"].get("case_analysis_text"):
                st.subheader("Case Analysis")
                st.text_area("Analysis", value=results["email"]["case_analysis_text"], height=400)

            # Display download options
            if results.get("email") and results["email"].get("download_links"):
                st.subheader("Download Options")
                for link in results["email"]["download_links"]:
                    file_name = link.get("file_name", "download")
                    data_url = link.get("url", "")
                    
                    try:
                        mime_type, base64_data = data_url.split(",", 1)
                        file_content = base64.b64decode(base64_data)
                        
                        if file_name.endswith(".eml"):
                            label = "Download Findings Letter (.eml)"
                            mime = "message/rfc822"
                        elif file_name.endswith(".txt"):
                            label = "Download Case Analysis (.txt)"
                            mime = "text/plain"
                        else:
                            label = f"Download {file_name}"
                            mime = "application/octet-stream"
                        st.download_button(label=label, data=file_content, file_name=file_name, mime=mime)
                    except Exception as e:
                        st.error(f"Error processing download link for {file_name}: {e}")

# --- Main Application ---
def main():
    """Main function for the Streamlit application."""
    st.set_page_config(page_title="Legal Document Analysis Portal", layout="wide")
    
    initialize_session_state()
    
    st.title("Legal Document Analysis Portal")
    
    case_information_form()
    
    tab1, tab2 = st.tabs(["Upload & Process", "Results"])
    
    with tab1:
        if st.session_state.processing_status in ['idle', 'failed', 'completed']:
            file_upload_section()
            
            if st.session_state.get('uploaded_files'):
                if handle_file_uploads():
                    if st.button("Start Analysis"):
                        start_analysis()
        
        if st.session_state.processing_status == 'active':
            monitor_progress()

    with tab2:
        if st.session_state.final_results:
            results_display_section()
        else:
            st.info("No results available. Please upload documents and start the analysis first.")

if __name__ == "__main__":
    main()