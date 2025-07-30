"""
Component for displaying the final results.
"""
import streamlit as st
import base64
from backend.utils.data_models import EmailResponse

def results_display():
    """
    Displays the generated findings letter and download links in a professional format.
    """
    if 'final_results' in st.session_state:
        results: EmailResponse = st.session_state.final_results
        
        st.subheader("🎉 Findings Generation Complete")
        st.markdown("---")
        
        # Display Findings Letter Preview
        st.subheader("Findings Letter Preview")
        with st.expander("Click to view the generated findings letter"):
            st.markdown(f"**Subject:** {results.findings_letter.subject}")
            st.markdown("---")
            st.text_area(
                "Letter Body",
                results.findings_letter.body,
                height=400,
                key="findings_letter_preview"
            )
            
        # Display Download Links
        st.subheader("Download Your Files")
        st.markdown("Your findings have been formatted for multiple platforms:")
        
        cols = st.columns(len(results.download_links))
        for i, link in enumerate(results.download_links):
            with cols[i]:
                # The data for the download button needs to be decoded from the base64 URL
                file_data = base64.b64decode(link.url.split(",")[1])
                st.download_button(
                    label=f"📥 Download .{link.file_name.split('.')[-1]}",
                    data=file_data,
                    file_name=link.file_name,
                    mime=_get_mime_type(link.file_name),
                    use_container_width=True,
                )

def _get_mime_type(file_name: str) -> str:
    """
    Returns the appropriate MIME type for a given file extension.
    """
    if file_name.endswith(".eml"):
        return "message/rfc822"
    elif file_name.endswith(".txt"):
        return "text/plain"
    elif file_name.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"