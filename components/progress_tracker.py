"""
Component for tracking processing status.
"""
import streamlit as st

def progress_tracker():
    """
    Displays the current processing status.
    Placeholder for future implementation.
    """
    status = st.session_state.get('processing_status', {})
    st.write(f"**Stage:** {status.get('stage', 'N/A')}")
    st.progress(status.get('progress', 0))
    
    errors = status.get('errors', [])
    if errors:
        st.error("Errors occurred during processing:")
        for error in errors:
            st.write(f"- {error}")