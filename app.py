import streamlit as st
import requests
from typing import List, Dict, Any

# --- Configuration ---
BACKEND_URL = "http://localhost:8000/api"

# --- Session State Initialization ---
def initialize_session_state():
    """Initializes the session state with default values."""
    if 'case_info' not in st.session_state:
        st.session_state.case_info = {"clientName": "", "attorneyName": "", "caseReference": ""}
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = {"intake_form": None, "case_documents": []}
    if 'processing_status' not in st.session_state:
        st.session_state.processing_status = {"stage": "pending", "progress": 0, "errors": []}
    if 'final_results' not in st.session_state:
        st.session_state.final_results = None

# --- UI Components ---
def case_information_form():
    """Renders the case information form in the sidebar."""
    st.sidebar.header("Case Information")
    st.session_state.case_info['clientName'] = st.sidebar.text_input("Client Name", value=st.session_state.case_info['clientName'])
    st.session_state.case_info['attorneyName'] = st.sidebar.text_input("Attorney Name", value=st.session_state.case_info['attorneyName'])
    st.session_state.case_info['caseReference'] = st.sidebar.text_input("Case Reference", value=st.session_state.case_info['caseReference'])

def file_upload_section():
    """Handles the file upload section."""
    st.header("File Upload")
    st.session_state.uploaded_files['intake_form'] = st.file_uploader("Upload Intake Form (PDF)", type=["pdf"])
    st.session_state.uploaded_files['case_documents'] = st.file_uploader("Upload Case Documents (PDF, DOCX, EML, TXT, JPG, PNG)", type=["pdf", "docx", "eml", "txt", "jpg", "jpeg", "png"], accept_multiple_files=True)

def process_files_button():
    """Renders the process files button and handles the API call."""
    if st.button("Process Documents"):
        with st.spinner("Processing documents..."):
            intake_form = st.session_state.uploaded_files.get('intake_form')
            case_documents = st.session_state.uploaded_files.get('case_documents')

            if not intake_form or not case_documents:
                st.error("Please upload both an intake form and at least one case document.")
                return

            try:
                # 1. Analyze Intake Form
                intake_files = {'intake_form': (intake_form.name, intake_form.getvalue(), intake_form.type)}
                intake_response = requests.post(f"{BACKEND_URL}/analyze-intake", files=intake_files)
                intake_response.raise_for_status()
                intake_analysis = intake_response.json()

                # 2. Analyze Case Documents
                case_doc_files = [('case_documents', (doc.name, doc.getvalue(), doc.type)) for doc in case_documents]
                case_docs_response = requests.post(f"{BACKEND_URL}/analyze-case-documents", files=case_doc_files)
                case_docs_response.raise_for_status()
                case_analyses = case_docs_response.json()

                # 3. Generate Findings Letter
                combined_analysis = {
                    "intake_analysis": intake_analysis,
                    "case_analyses": case_analyses
                }
                findings_response = requests.post(f"{BACKEND_URL}/generate-findings-letter", json=combined_analysis)
                findings_response.raise_for_status()
                
                st.session_state.final_results = findings_response.json()
                st.success("Documents processed successfully!")
            except requests.exceptions.RequestException as e:
                st.error(f"An error occurred: {e}")

def results_display_section():
    """Displays the final results and download links."""
    if st.session_state.final_results:
        st.header("Results")
        results = st.session_state.final_results
        st.subheader("Findings Letter")
        st.text_area("Subject", value=results['findings_letter']['subject'], height=70)
        st.text_area("Body", value=results['findings_letter']['body'], height=300)

        st.subheader("Downloads")
        for link in results['download_links']:
            st.markdown(f"[{link['file_name']}]({link['url']})", unsafe_allow_html=True)

# --- Main Application ---
def main():
    """Main function for the Streamlit application."""
    st.set_page_config(page_title="Legal Document Analysis Portal", layout="wide")
    
    initialize_session_state()
    
    st.title("Legal Document Analysis Portal")
    
    case_information_form()
    
    tab1, tab2, tab3 = st.tabs(["File Upload", "Processing Monitor", "Results & Download"])
    
    with tab1:
        file_upload_section()
        process_files_button()
        
    with tab2:
        st.info("Processing monitor is not yet implemented.", icon="ℹ️")

    with tab3:
        results_display_section()

if __name__ == "__main__":
    main()