import streamlit as st
import requests
import json
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

def process_documents():
    """Handles file processing with synchronous request."""
    intake_form = st.session_state.uploaded_files.get('intake_form')
    case_documents = st.session_state.uploaded_files.get('case_documents')

    if not intake_form or not case_documents:
        st.error("Please upload both an intake form and at least one case document.")
        return

    # Prepare files for upload
    files = [
        ('intake_form', (intake_form.name, intake_form.getvalue(), intake_form.type)),
    ]
    for doc in case_documents:
        files.append(('case_documents', (doc.name, doc.getvalue(), doc.type)))
    
    # Show processing status
    with st.spinner("Processing documents... This may take a few minutes."):
        try:
            response = requests.post(
                f"{BACKEND_URL}/v1/analysis/full-pipeline", 
                files=files
            )
            response.raise_for_status()
            
            # Parse the response
            result = response.json()
            
            # Store results in session state
            st.session_state.final_results = result
            
            st.success("Documents processed successfully!")
            st.rerun()

        except requests.exceptions.RequestException as e:
            st.error(f"An error occurred during processing: {e}")
        except json.JSONDecodeError as e:
            st.error(f"Error parsing response: {e}")

def results_display_section():
    """Displays the final results and download links."""
    if st.session_state.final_results:
        st.header("Results")
        results = st.session_state.final_results
        
        # Display analysis findings
        if results.get("analysis") and results["analysis"].get("findings_html"):
            st.subheader("Findings")
            st.markdown(results["analysis"]["findings_html"], unsafe_allow_html=True)

        # Display case analysis text
        if results.get("email") and results["email"].get("case_analysis_text"):
            st.subheader("Case Analysis")
            st.text_area("Analysis", value=results["email"]["case_analysis_text"], height=400)

        # Display download options if available
        if results.get("email"):
            email_data = results["email"]
            if email_data.get("eml_content"):
                st.subheader("Download Options")
                
                # Email file download
                st.download_button(
                    label="Download Findings Letter (.eml)",
                    data=email_data["eml_content"],
                    file_name=f"findings_letter_{results.get('case_id', 'case')}.eml",
                    mime="message/rfc822"
                )
                
                # Text file download
                if email_data.get("case_analysis_text"):
                    st.download_button(
                        label="Download Case Analysis (.txt)",
                        data=email_data["case_analysis_text"],
                        file_name=f"case_analysis_{results.get('case_id', 'case')}.txt",
                        mime="text/plain"
                    )

# --- Main Application ---
def main():
    """Main function for the Streamlit application."""
    st.set_page_config(page_title="Legal Document Analysis Portal", layout="wide")
    
    initialize_session_state()
    
    st.title("Legal Document Analysis Portal")
    
    case_information_form()
    
    # Simple tab interface
    tab1, tab2 = st.tabs(["File Upload", "Results"])
    
    with tab1:
        file_upload_section()
        if st.button("Process Documents"):
            process_documents()

    with tab2:
        if st.session_state.final_results:
            results_display_section()
        else:
            st.info("No results available. Please upload and process documents first.")

if __name__ == "__main__":
    main()