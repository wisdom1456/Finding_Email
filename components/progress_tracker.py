"""
Enhanced component for tracking processing status with detailed feedback.
"""
import streamlit as st
from typing import Dict, List, Optional
import time

class AdvancedProgressTracker:
    """
    Advanced progress tracker with time estimation and detailed feedback.
    """
    
    def __init__(self, container=None):
        self.container = container or st.container()
        self.start_time = None
        self.phase_start_times = {}
        self.completed_phases = []
        
    def start_tracking(self):
        """Initialize tracking with start time."""
        self.start_time = time.time()
        
    def create_progress_display(self):
        """Create the progress display elements."""
        with self.container:
            progress_col, time_col = st.columns([3, 1])
            
            with progress_col:
                progress_bar = st.progress(0)
                status_text = st.empty()
                detail_text = st.empty()
                
            with time_col:
                time_text = st.empty()
                eta_text = st.empty()
                
            return {
                'progress_bar': progress_bar,
                'status_text': status_text,
                'detail_text': detail_text,
                'time_text': time_text,
                'eta_text': eta_text
            }
    
    def estimate_time_remaining(self, current_progress: float) -> str:
        """Estimate time remaining based on current progress."""
        if not self.start_time or current_progress <= 0:
            return "Calculating..."
            
        elapsed = time.time() - self.start_time
        if current_progress >= 100:
            return f"Total: {elapsed:.1f}s"
            
        estimated_total = elapsed / (current_progress / 100)
        remaining = estimated_total - elapsed
        
        if remaining > 60:
            return f"~{remaining/60:.1f}m remaining"
        else:
            return f"~{remaining:.0f}s remaining"

def progress_tracker():
    """
    Enhanced progress tracker that displays detailed processing status.
    """
    processing_status = st.session_state.get('processing_status', 'idle')
    
    if processing_status == 'idle':
        st.info("Ready to start analysis")
        return
        
    elif processing_status == 'active':
        st.info("🔄 Analysis in progress...")
        
        # Show phase progress if available
        if 'current_phase' in st.session_state:
            phase = st.session_state.current_phase
            st.write(f"**Current Phase:** {phase.replace('_', ' ').title()}")
            
        if 'phase_progress' in st.session_state:
            progress = st.session_state.phase_progress
            st.progress(progress / 100.0)
            st.write(f"Progress: {progress:.1f}%")
            
        if 'current_detail' in st.session_state:
            st.write(f"**Status:** {st.session_state.current_detail}")
            
    elif processing_status == 'completed':
        st.success("✅ Analysis completed successfully!")
        
        # Show completion summary
        if 'processing_summary' in st.session_state:
            summary = st.session_state.processing_summary
            with st.expander("Processing Summary", expanded=False):
                st.write(summary)
                
    elif processing_status == 'failed':
        st.error("❌ Analysis failed")
        
        if 'processing_error' in st.session_state:
            st.write(f"**Error:** {st.session_state.processing_error}")
            
        if 'error_details' in st.session_state:
            with st.expander("Error Details", expanded=False):
                st.code(st.session_state.error_details)

def monitor_progress():
    """
    Monitor and display active processing progress.
    This function is called when processing is active.
    """
    if st.session_state.processing_status != 'active':
        return
        
    # Create progress display
    progress_container = st.container()
    
    with progress_container:
        # Main progress section
        st.subheader("Document Analysis Progress")
        
        # Progress metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Status",
                st.session_state.get('current_phase', 'Starting').replace('_', ' ').title()
            )
            
        with col2:
            progress = st.session_state.get('phase_progress', 0)
            st.metric("Progress", f"{progress:.1f}%")
            
        with col3:
            docs_processed = st.session_state.get('documents_processed', 0)
            total_docs = st.session_state.get('total_documents', 0)
            st.metric("Documents", f"{docs_processed}/{total_docs}")
        
        # Progress bar
        progress_value = st.session_state.get('phase_progress', 0) / 100.0
        st.progress(progress_value)
        
        # Current activity
        if 'current_detail' in st.session_state:
            st.info(st.session_state.current_detail)
        
        # Processing log (last 5 activities)
        if 'processing_log' in st.session_state:
            with st.expander("Processing Log", expanded=False):
                log_entries = st.session_state.processing_log[-5:]  # Last 5 entries
                for entry in reversed(log_entries):  # Most recent first
                    st.write(f"• {entry}")

def display_processing_metrics(total_files: int, total_size: int, start_time: float):
    """
    Display processing metrics in a sidebar or dedicated section.
    """
    with st.sidebar:
        st.subheader("Processing Metrics")
        
        # File metrics
        st.metric("Total Files", total_files)
        st.metric("Total Size", f"{total_size/1024:.1f} KB")
        
        # Time metrics
        if start_time:
            elapsed = time.time() - start_time
            st.metric("Elapsed Time", f"{elapsed:.1f}s")
        
        # System metrics
        if 'errors_count' in st.session_state:
            st.metric("Errors", st.session_state.errors_count, delta_color="inverse")