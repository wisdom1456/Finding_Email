import streamlit as st
import streamlit.components.v1 as components
import asyncio
import os
from typing import Dict
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Backend logic imports - direct function calls
from backend_logic.document_processor import DocumentProcessor
from backend_logic.ai_analyzer import AIAnalyzer
from backend_logic.email_generator import EmailGenerator
from backend_logic.audio_processor import AudioProcessor
from backend_logic.video_processor import VideoProcessor
from backend.utils.data_models import (
    AnalysisError,
    AnalyzedDocument,
    DocumentType,
    TranscriptedMedia,
    VideoInsight,
    MediaProcessingError
)

# --- Configuration ---
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    st.error("OpenAI API key not found. Please set OPENAI_API_KEY in your environment variables.")
    st.stop()

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# --- Session State Initialization ---
def initialize_session_state():
    """Initializes the session state with default values."""
    if 'case_info' not in st.session_state:
        st.session_state.case_info = {"clientName": "", "attorneyName": "", "caseReference": ""}
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = []
    if 'intake_form' not in st.session_state:
        st.session_state.intake_form = None
    if 'case_documents' not in st.session_state:
        st.session_state.case_documents = []
    if 'final_results' not in st.session_state:
        st.session_state.final_results = None
    if 'main_letter' not in st.session_state:
        st.session_state.main_letter = None
    if 'appendix' not in st.session_state:
        st.session_state.appendix = None
    if 'processing_status' not in st.session_state:
        st.session_state.processing_status = 'idle'  # idle, active, completed, failed
    if 'processing_error' not in st.session_state:
        st.session_state.processing_error = None

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
        "Select a folder or multiple files (PDF, DOCX, EML, TXT, JPG, PNG, MP3, M4A, WAV, MP4, MOV, AVI)",
        type=["pdf", "docx", "eml", "txt", "jpg", "jpeg", "png", "mp3", "m4a", "wav", "mp4", "mov", "avi"],
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

class ProgressTracker:
    """Enhanced progress tracking with size-based calculations and detailed feedback."""
    
    def __init__(self, progress_bar, status_text, detail_text):
        self.progress_bar = progress_bar
        self.status_text = status_text
        self.detail_text = detail_text
        self.current_progress = 0.0
        
        # Progress allocation for different phases
        self.PHASE_ALLOCATIONS = {
            'document_processing': (0, 15),      # 15% - File processing
            'intake_analysis': (15, 25),         # 10% - Single intake analysis
            'case_analysis': (25, 75),           # 50% - Bulk of processing (size-based)
            'final_assessment': (75, 85),        # 10% - Final legal assessment
            'email_generation': (85, 100),       # 15% - Email generation
        }
        
    def set_phase(self, phase_name: str, detail: str = ""):
        """Set the current processing phase."""
        start_pct, _ = self.PHASE_ALLOCATIONS[phase_name]
        self.current_progress = start_pct
        self.update_display(phase_name.replace('_', ' ').title(), detail)
        
    def update_progress(self, phase_name: str, progress_within_phase: float, detail: str = ""):
        """Update progress within a specific phase (progress_within_phase should be 0.0 to 1.0)."""
        start_pct, end_pct = self.PHASE_ALLOCATIONS[phase_name]
        phase_range = end_pct - start_pct
        self.current_progress = start_pct + (progress_within_phase * phase_range)
        self.update_display(phase_name.replace('_', ' ').title(), detail)
        
    def complete_phase(self, phase_name: str, detail: str = ""):
        """Mark a phase as complete."""
        _, end_pct = self.PHASE_ALLOCATIONS[phase_name]
        self.current_progress = end_pct
        self.update_display(phase_name.replace('_', ' ').title() + " Complete", detail)
        
    def update_display(self, status: str, detail: str = ""):
        """Update the UI display elements."""
        self.progress_bar.progress(self.current_progress / 100.0)
        self.status_text.text(f"**{status}** ({self.current_progress:.1f}%)")
        if detail:
            self.detail_text.text(detail)

def calculate_document_sizes(files) -> Dict[str, int]:
    """Calculate sizes of uploaded files for progress tracking."""
    sizes = {}
    for file in files:
        try:
            if hasattr(file, 'size'):
                sizes[file.name] = file.size
            else:
                # Fallback: estimate size from content
                content = file.getvalue() if hasattr(file, 'getvalue') else b''
                sizes[file.name] = len(content)
        except Exception:
            # Default size if calculation fails
            sizes[file.name] = 1024  # 1KB default
    return sizes

async def process_case_documents():
    """
    Enhanced processing function with size-based progress tracking and detailed feedback.
    """
    try:
        st.session_state.processing_status = 'active'
        st.session_state.processing_error = None
        
        # Initialize processors
        doc_processor = DocumentProcessor()
        audio_processor = AudioProcessor(openai_client)
        # Securely retrieve and pass cloud credentials via environment variables
        video_processor = VideoProcessor()
        ai_analyzer = AIAnalyzer(openai_client, doc_processor)
        email_generator = EmailGenerator(openai_client)
        
        # Enhanced progress tracking setup
        progress_container = st.container()
        with progress_container:
            progress_bar = st.progress(0)
            status_text = st.empty()
            detail_text = st.empty()
            
        tracker = ProgressTracker(progress_bar, status_text, detail_text)
        
        # Calculate document sizes for progress tracking
        all_files = []
        if st.session_state.intake_form:
            all_files.append(st.session_state.intake_form)
        all_files.extend(st.session_state.case_documents)
        
        doc_sizes = calculate_document_sizes(all_files)
        total_size = sum(doc_sizes.values())
        case_doc_sizes = {name: size for name, size in doc_sizes.items()
                         if name != (st.session_state.intake_form.name if st.session_state.intake_form else None)}
        total_case_size = sum(case_doc_sizes.values())
        
        # Phase 1: Document Processing
        tracker.set_phase('document_processing', f"Processing {len(all_files)} files ({total_size/1024:.1f} KB total)")

        # Separate files by type
        doc_files = []
        audio_files = []
        video_files = []
        for f in all_files:
            file_type = f.type.lower()
            if 'audio' in file_type:
                audio_files.append(f)
            elif 'video' in file_type:
                video_files.append(f)
            else:
                doc_files.append(f)

        intake_filenames = [st.session_state.intake_form.name] if st.session_state.intake_form else []
        
        # Process documents, audio, and video in parallel
        doc_processing_task = doc_processor.process_documents_from_streamlit(doc_files, intake_filenames)
        audio_processing_task = asyncio.gather(*[audio_processor.process_audio_from_streamlit(f, f.name) for f in audio_files])
        video_processing_task = asyncio.gather(*[video_processor.process_video_from_streamlit(f, f.name) for f in video_files])

        processed_docs, processed_audio, processed_video = await asyncio.gather(
            doc_processing_task,
            audio_processing_task,
            video_processing_task
        )

        
        # Separate intake and case documents
        intake_doc = next(
            (doc for doc in processed_docs if doc.document_type == DocumentType.INTAKE_FORM),
            None
        )
        case_docs = [
            doc for doc in processed_docs if doc.document_type != DocumentType.INTAKE_FORM
        ]
        
        if not intake_doc:
            raise ValueError("Intake form is required but was not found after processing.")
        
        tracker.complete_phase('document_processing', f"Successfully processed {len(processed_docs) + len(processed_audio) + len(processed_video)} files")
        
        # Phase 2: Intake Analysis
        tracker.set_phase('intake_analysis', f"Analyzing intake form: {intake_doc.file_name}")
        
        analysis_result = await ai_analyzer.analyze_intake(intake_doc)
        
        if not analysis_result.intake_analysis:
            raise ValueError("Failed to analyze intake form.")
        
        tracker.complete_phase('intake_analysis', "Intake analysis completed")
        
        # Phase 3: Case Document Analysis (Size-based progress)
        if case_docs or processed_audio or processed_video:
            tracker.set_phase('case_analysis', f"Starting analysis of {len(case_docs)} documents, {len(processed_audio)} audio files, and {len(processed_video)} video files")
            
            processed_size = 0
            
            # Custom progress callback for document analysis
            async def analyze_with_progress():
                nonlocal processed_size
                results = []
                
                # Analyze documents
                for i, doc in enumerate(case_docs):
                    doc_size = case_doc_sizes.get(doc.file_name, 1024)
                    current_doc_progress = processed_size / total_case_size if total_case_size > 0 else (i / len(case_docs))
                    
                    tracker.update_progress(
                        'case_analysis',
                        current_doc_progress,
                        f"Processing {i+1}/{len(case_docs)}: {doc.file_name} ({doc_size/1024:.1f} KB)"
                    )
                    
                    result = await ai_analyzer._analyze_single_document(doc, analysis_result.intake_analysis)
                    results.append(result)
                    
                    processed_size += doc_size
                    final_progress = processed_size / total_case_size if total_case_size > 0 else ((i+1) / len(case_docs))
                    
                    tracker.update_progress(
                        'case_analysis',
                        final_progress,
                        f"Completed {i+1}/{len(case_docs)} documents"
                    )
                    
                    if i < len(case_docs) - 1:
                        await asyncio.sleep(3)
                
                # Add media results to the final analysis
                for item in processed_audio:
                    if isinstance(item, TranscriptedMedia):
                        analysis_result.transcripted_media.append(item)
                    elif isinstance(item, MediaProcessingError):
                        analysis_result.errors.append(AnalysisError(source=item.source, file_name=item.file_name, error_message=item.error_message))
                
                for item in processed_video:
                    if isinstance(item, VideoInsight):
                        analysis_result.video_insights.append(item)
                    elif isinstance(item, MediaProcessingError):
                        analysis_result.errors.append(AnalysisError(source=item.source, file_name=item.file_name, error_message=item.error_message))

                return results

            
            case_analysis_results = await analyze_with_progress()
            
            # Process results
            for res in case_analysis_results:
                if isinstance(res, AnalyzedDocument):
                    analysis_result.analyzed_documents.append(res)
                elif isinstance(res, AnalysisError):
                    analysis_result.errors.append(res)
            
            tracker.complete_phase('case_analysis', f"Analyzed {len(case_docs)} documents and {len(processed_audio) + len(processed_video)} media files successfully")
        else:
            tracker.complete_phase('case_analysis', "No case documents or media to analyze")
        
        # Phase 4: Final Assessment
        tracker.set_phase('final_assessment', "Performing comprehensive legal assessment")
        
        final_analysis = await ai_analyzer.perform_final_assessment(analysis_result)
        
        tracker.complete_phase('final_assessment', "Legal assessment completed")
        
        # Phase 5: Email Generation
        tracker.set_phase('email_generation', "Generating professional findings letter")
        
        email_docs = email_generator.generate_email_and_analysis_docs(final_analysis)
        
        tracker.complete_phase('email_generation', "Findings letter generated successfully")
        
        # Store results
        st.session_state.final_results = final_analysis
        st.session_state.main_letter = email_docs.get("main_letter", "")
        st.session_state.appendix = email_docs.get("appendix", "")
        st.session_state.processing_status = 'completed'
        
        # Final success message
        status_text.text("**Analysis Complete!** (100.0%)")
        detail_text.text(f"Successfully processed {len(all_files)} documents totaling {total_size/1024:.1f} KB")
        st.success("Document analysis completed successfully!")
        
        return True
        
    except Exception as e:
        st.session_state.processing_status = 'failed'
        st.session_state.processing_error = str(e)
        st.error(f"An error occurred during processing: {e}")
        return False

def start_analysis():
    """Handles the start analysis button click."""
    intake_form = st.session_state.get('intake_form')
    case_documents = st.session_state.get('case_documents', [])

    if not intake_form:
        st.error("An intake form is required to start the analysis.")
        return

    # Run the async processing function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_case_documents())
    finally:
        loop.close()

def generate_case_analysis_html(analysis_result):
    """Generate a professionally formatted HTML case analysis document."""
    from datetime import datetime
    
    # Get client information
    client_name = "Client"
    attorney_name = "Attorney"
    if analysis_result.intake_analysis:
        client_name = analysis_result.intake_analysis.client_name or "Client"
        attorney_name = analysis_result.intake_analysis.attorney_name or "Attorney"
    
    current_date = datetime.now().strftime('%B %d, %Y')
    
    # Start building the HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Case Analysis - {client_name}</title>
        <style>
            body {{
                font-family: 'Times New Roman', Times, serif;
                line-height: 1.6;
                margin: 40px;
                color: #333;
                background-color: #fff;
            }}
            .header {{
                text-align: center;
                margin-bottom: 40px;
                padding-bottom: 20px;
                border-bottom: 2px solid #2c3e50;
            }}
            .header h1 {{
                color: #2c3e50;
                margin-bottom: 10px;
                font-size: 28px;
            }}
            .header p {{
                margin: 5px 0;
                font-size: 16px;
            }}
            .section {{
                margin: 30px 0;
                padding: 20px;
                border-left: 4px solid #3498db;
                background-color: #f8f9fa;
            }}
            .section h2 {{
                color: #2c3e50;
                margin-top: 0;
                margin-bottom: 15px;
                font-size: 22px;
                border-bottom: 1px solid #bdc3c7;
                padding-bottom: 5px;
            }}
            .section h3 {{
                color: #34495e;
                margin-top: 20px;
                margin-bottom: 10px;
                font-size: 18px;
            }}
            .metadata {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .metadata-item {{
                background-color: #ecf0f1;
                padding: 15px;
                border-radius: 5px;
                border-left: 4px solid #3498db;
            }}
            .metadata-item strong {{
                color: #2c3e50;
                display: block;
                margin-bottom: 5px;
            }}
            .document-list {{
                background-color: #fff;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 15px;
                margin: 15px 0;
            }}
            .document-item {{
                margin: 10px 0;
                padding: 10px;
                background-color: #f8f9fa;
                border-left: 3px solid #3498db;
            }}
            .document-item h4 {{
                margin: 0 0 5px 0;
                color: #2c3e50;
            }}
            .document-item p {{
                margin: 5px 0;
                font-size: 14px;
            }}
            .footer {{
                margin-top: 50px;
                padding-top: 20px;
                border-top: 1px solid #bdc3c7;
                text-align: center;
                font-size: 14px;
                color: #7f8c8d;
            }}
            @media print {{
                body {{ margin: 20px; }}
                .section {{ break-inside: avoid; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Comprehensive Case Analysis Report</h1>
            <p><strong>Date:</strong> {current_date}</p>
            <p><strong>Client:</strong> {client_name}</p>
            <p><strong>Attorney:</strong> {attorney_name}</p>
        </div>
    """
    
    # Add intake analysis section
    if analysis_result.intake_analysis:
        ia = analysis_result.intake_analysis
        html_content += f"""
        <div class="section">
            <h2>Client Intake Analysis</h2>
            <div class="metadata">
                <div class="metadata-item">
                    <strong>Case Type:</strong>
                    {ia.case_type or 'Not specified'}
                </div>
                <div class="metadata-item">
                    <strong>Urgency Level:</strong>
                    {ia.urgency_level or 'Standard'}
                </div>
            </div>
            <h3>Case Summary</h3>
            <p>{ia.case_summary or 'No summary provided.'}</p>
            
            <h3>Client Priorities</h3>
            <ul>
        """
        if ia.client_priorities:
            for priority in ia.client_priorities:
                html_content += f"<li>{priority}</li>"
        else:
            html_content += "<li>No specific priorities identified</li>"
        
        html_content += "</ul><h3>Desired Outcomes</h3><ul>"
        
        if ia.desired_outcomes:
            for outcome in ia.desired_outcomes:
                html_content += f"<li>{outcome}</li>"
        else:
            html_content += "<li>No specific outcomes identified</li>"
        
        html_content += "</ul></div>"
    
    # Add analyzed documents section
    if analysis_result.analyzed_documents:
        html_content += """
        <div class="section">
            <h2>Document Analysis</h2>
            <div class="document-list">
        """
        
        for i, doc in enumerate(analysis_result.analyzed_documents, 1):
            html_content += f"""
            <div class="document-item">
                <h4>{i}. {doc.inferred_title or 'Untitled Document'}</h4>
                <p><strong>Source File:</strong> {doc.filename}</p>
                <p><strong>Document Type:</strong> {doc.document_type}</p>
                <p><strong>Summary:</strong> {doc.summary}</p>
                <p><strong>Key Information:</strong> {doc.key_information}</p>
                <p><strong>Relevance to Case:</strong> {doc.relevance_to_case}</p>
            </div>
            """
        
        html_content += "</div></div>"
    
    # Add legal assessment section
    if analysis_result.legal_assessment:
        la = analysis_result.legal_assessment
        html_content += f"""
        <div class="section">
            <h2>Legal Assessment</h2>
            <div class="metadata">
                <div class="metadata-item">
                    <strong>Claim Viability:</strong>
                    {la.claim_viability or 'Not assessed'}
                </div>
                <div class="metadata-item">
                    <strong>Overall Evidence Strength:</strong>
                    {la.overall_evidence_strength or 'Not assessed'}
                </div>
            </div>
            
            <h3>Potential Challenges</h3>
            <ul>
        """
        
        if la.potential_challenges:
            for challenge in la.potential_challenges:
                html_content += f"<li>{challenge}</li>"
        else:
            html_content += "<li>No specific challenges identified</li>"
        
        html_content += "</ul><h3>Recommended Actions</h3><ul>"
        
        if la.recommended_actions:
            for action in la.recommended_actions:
                html_content += f"<li>{action}</li>"
        else:
            html_content += "<li>No specific actions recommended</li>"
        
        html_content += "</ul></div>"
    
    # Add any errors or processing notes
    if analysis_result.errors:
        html_content += """
        <div class="section">
            <h2>Processing Notes</h2>
        """
        for error in analysis_result.errors:
            html_content += f"<p><strong>{error.source}:</strong> {error.error_message}</p>"
        html_content += "</div>"
    
    # Close the HTML
    html_content += f"""
        <div class="footer">
            <p>Generated by Legal Document Analysis Portal on {current_date}</p>
            <p>Bernhardt Riley PLLC</p>
        </div>
    </body>
    </html>
    """
    
    return html_content

def results_display_section():
    """Displays the final results and download links."""
    if st.session_state.final_results:
        st.header("Results")
        
        # Check if we have the new two-document format
        if st.session_state.main_letter and st.session_state.appendix:
            # Display the main findings letter inline using components.html for complete HTML documents
            st.subheader("Findings Letter")
            components.html(st.session_state.main_letter, height=800, scrolling=True)
            
            # Provide separate download buttons for all documents
            st.subheader("Download Options")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Download button for main findings letter as HTML
                try:
                    main_letter_bytes = st.session_state.main_letter.encode('utf-8')
                    
                    # Get client name for filename
                    client_name = "Client"
                    if (st.session_state.final_results.intake_analysis and
                        st.session_state.final_results.intake_analysis.client_name):
                        client_name_raw = st.session_state.final_results.intake_analysis.client_name
                        client_name = "".join(c for c in client_name_raw if c.isalnum() or c in " _-").rstrip()
                    
                    st.download_button(
                        label="📧 Findings Letter",
                        data=main_letter_bytes,
                        file_name=f"Findings_Letter_{client_name}.html",
                        mime="text/html",
                        help="Professional findings letter in HTML format"
                    )
                except Exception as e:
                    st.error(f"Error creating findings letter download: {e}")
            
            with col2:
                # Download button for document appendix as HTML
                try:
                    appendix_bytes = st.session_state.appendix.encode('utf-8')
                    
                    # Get client name for filename
                    client_name = "Client"
                    if (st.session_state.final_results.intake_analysis and
                        st.session_state.final_results.intake_analysis.client_name):
                        client_name_raw = st.session_state.final_results.intake_analysis.client_name
                        client_name = "".join(c for c in client_name_raw if c.isalnum() or c in " _-").rstrip()
                    
                    st.download_button(
                        label="📎 Document Appendix",
                        data=appendix_bytes,
                        file_name=f"Document_Appendix_{client_name}.html",
                        mime="text/html",
                        help="Supporting document analysis in HTML format"
                    )
                except Exception as e:
                    st.error(f"Error creating appendix download: {e}")
            
            with col3:
                # Download button for case analysis as HTML
                try:
                    # Generate the HTML case analysis document
                    case_analysis_html = generate_case_analysis_html(st.session_state.final_results)
                    case_analysis_bytes = case_analysis_html.encode('utf-8')
                    
                    # Get client name for filename
                    client_name = "Client"
                    if (st.session_state.final_results.intake_analysis and
                        st.session_state.final_results.intake_analysis.client_name):
                        client_name_raw = st.session_state.final_results.intake_analysis.client_name
                        client_name = "".join(c for c in client_name_raw if c.isalnum() or c in " _-").rstrip()
                    
                    st.download_button(
                        label="📄 Case Analysis",
                        data=case_analysis_bytes,
                        file_name=f"Case_Analysis_{client_name}.html",
                        mime="text/html",
                        help="Comprehensive case analysis in HTML format"
                    )
                except Exception as e:
                    st.error(f"Error creating case analysis download: {e}")
                    
        else:
            st.info("Results are available but in an unexpected format.")
            
        # Display any errors that occurred during processing
        if st.session_state.final_results.errors:
            st.subheader("Processing Notes")
            for error in st.session_state.final_results.errors:
                st.warning(f"**{error.source}**: {error.error_message}")

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
        
        elif st.session_state.processing_status == 'active':
            st.info("Analysis is currently in progress. Please wait...")
            
        # Show any processing errors
        if st.session_state.processing_status == 'failed' and st.session_state.processing_error:
            st.error(f"Processing failed: {st.session_state.processing_error}")

    with tab2:
        if st.session_state.final_results:
            results_display_section()
        else:
            st.info("No results available. Please upload documents and start the analysis first.")

if __name__ == "__main__":
    main()