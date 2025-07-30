"""
Custom file uploader component.
"""
import streamlit as st

def file_uploader(label, type, key, accept_multiple_files=False):
    """
    Renders a file uploader component.
    Placeholder for a more complex custom component in the future.
    """
    uploaded_files = st.file_uploader(
        label=label,
        type=type,
        key=key,
        accept_multiple_files=accept_multiple_files
    )
    
    if uploaded_files:
        if accept_multiple_files:
            st.session_state['uploaded_files']['case_documents'] = uploaded_files
        else:
            st.session_state['uploaded_files']['intake_form'] = uploaded_files
    
    return uploaded_files