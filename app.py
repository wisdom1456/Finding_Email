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
                files = [
                    ('intake_form', (intake_form.name, intake_form.getvalue(), intake_form.type)),
                ]
                for doc in case_documents:
                    files.append(('case_documents', (doc.name, doc.getvalue(), doc.type)))
                
                response = requests.post(f"{BACKEND_URL}/v1/analysis/full-pipeline", files=files)
                response.raise_for_status()
                
                st.session_state.final_results = response.json()
                st.success("Documents processed successfully!")
            except requests.exceptions.RequestException as e:
                st.error(f"An error occurred: {e}")

def results_display_section():
    """Displays the final results and download links."""
    if st.session_state.final_results:
        st.header("Results")
        results = st.session_state.final_results
        
        # Check for and display errors
        if results.get("errors"):
            st.error("The following errors occurred during processing:")
            for error in results["errors"]:
                st.json(error) # Pretty-print the error details
        
        # Display analysis and email if they exist
        if results.get("analysis"):
            st.subheader("Case Analysis")
            st.json(results["analysis"]) # Pretty-print the analysis

        if results.get("email") and results["email"].get("findings_letter"):
            st.subheader("Findings Letter")
            letter = results["email"]["findings_letter"]
            st.text_area("Subject", value=letter.get("header", {}).get("case_reference", "N/A"), height=70)
            
            # Reconstruct the body for display
            body_parts = [
                letter.get("background_summary", ""),
                letter.get("review_summary", ""),
                "Potential Challenges:",
                "\n".join([f"- {c.get('description', '')}" for c in letter.get("assessment_challenges", [])]),
                "Recommended Next Steps:",
                "\n".join([f"- {step}" for step in letter.get("next_steps_recommendations", [])])
            ]
            full_body = "\n\n".join(filter(None, body_parts))
            st.text_area("Body", value=full_body, height=400)

        if results.get("email") and results["email"].get("download_links"):
            st.subheader("Downloads")
            for link in results["email"]["download_links"]:
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