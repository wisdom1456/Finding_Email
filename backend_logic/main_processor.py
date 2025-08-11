"""
Main processing module for the Legal Document Analysis Portal.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

from utils.logging_config import get_module_logger


logger = get_module_logger(__name__)


# Add project root to Python path for standalone execution
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    sys.path.insert(0, project_root)

# Additional imports for file output functionality
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st
from openai import OpenAI

from backend.utils.data_models import (
    AnalysisError,
    AnalyzedDocument,
    DocumentType,
    MediaProcessingError,
    TranscriptedMedia,
    VideoInsight,
)
from backend_logic.ai import AIAnalyzer
from backend_logic.audio_processor import AudioProcessor
from backend_logic.config import get_openai_api_key
from backend_logic.cost_session_manager import CostSessionManager
from backend_logic.document_processor import DocumentProcessor
from backend_logic.email_generation import EmailGeneratorV2
from backend_logic.email_generator import EmailReadabilityError
from backend_logic.utils import (
    ProgressTracker,
    calculate_document_sizes,
    display_processing_cost_update,
)
from backend_logic.video_processor import VideoProcessor


# Optional imports with fallbacks for testing
try:
    import html2text

    HTML2TEXT_AVAILABLE = True
except ImportError:
    HTML2TEXT_AVAILABLE = False

try:
    import docx
    from docx.shared import Inches

    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# Don't import weasyprint at module level to avoid dependency issues
WEASYPRINT_AVAILABLE = None  # Will be checked when needed


def html_to_plain_text(html_content: str) -> str:
    """Convert HTML content to plain text."""
    if HTML2TEXT_AVAILABLE:
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        return h.handle(html_content)
    # Simple fallback HTML stripping
    import re

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", html_content)
    # Replace HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    # Clean up whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_case_name(analysis_result) -> str:
    """Extract case name from analysis result."""
    if hasattr(analysis_result, "intake_analysis") and analysis_result.intake_analysis:
        if (
            hasattr(analysis_result.intake_analysis, "client_name")
            and analysis_result.intake_analysis.client_name
        ):
            # Clean the client name for use as filename
            case_name = analysis_result.intake_analysis.client_name
            # Remove special characters and spaces
            case_name = re.sub(r"[^\w\s-]", "", case_name)
            case_name = re.sub(r"[-\s]+", "_", case_name)
            return case_name.lower()

    # Fallback to timestamp-based name
    return f"case_{int(datetime.now(timezone.utc).timestamp())}"


def save_output_files(
    output_dir: str, main_letter: str, appendix: str, analysis_result
) -> None:
    """Save HTML output files to the specified directory."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    case_name = extract_case_name(analysis_result)

    # Save main findings letter as HTML
    letter_html_path = output_path / f"{case_name}_findings_letter.html"
    with open(letter_html_path, "w", encoding="utf-8") as f:
        f.write(main_letter)

    # Save analysis appendix as HTML
    appendix_html_path = output_path / f"{case_name}_analysis_appendix.html"
    with open(appendix_html_path, "w", encoding="utf-8") as f:
        f.write(appendix)

    logger.info(f"HTML output files saved to: {output_path}")
    logger.info("Files created:")
    logger.info(f"  - {case_name}_findings_letter.html")
    logger.info(f"  - {case_name}_analysis_appendix.html")


async def process_case_documents(
    output_dir: Optional[str] = None, config_path: Optional[str] = None
) -> Optional[bool]:
    """
    Enhanced processing function with size-based progress tracking and cost tracking.

    Args:
        output_dir: Directory to save output files
        config_path: Path to configuration YAML file for legal practice area-specific prompts
    """
    try:
        st.session_state.processing_status = "active"
        st.session_state.processing_error = None

        # Initialize processors
        from backend_logic.ai.openai_client import OpenAIClient
        openai_client_wrapper = OpenAIClient(api_key=get_openai_api_key())
        openai_client = openai_client_wrapper.client  # Get the properly configured client
        doc_processor = DocumentProcessor()
        audio_processor = AudioProcessor(openai_client)
        
        # Initialize video processor with graceful fallback
        video_processor = None
        try:
            from backend_logic.config import get_settings
            settings = get_settings()
            
            if settings.video_processing_enabled:
                video_processor = VideoProcessor()
                logger.info("Video processor initialized successfully")
            else:
                logger.info("Video processing disabled - Google Cloud credentials not configured")
        except Exception as e:
            logger.warning(f"Could not initialize video processor: {e}")
            logger.info("Continuing without video processing support")
        
        ai_analyzer = AIAnalyzer(openai_client, doc_processor, config_path=config_path)
        email_generator = EmailGeneratorV2(
            config_path=config_path, openai_api_key=openai_client.api_key
        )

        # Initialize cost tracking
        cost_session_manager = CostSessionManager()

        # Generate case ID for cost tracking
        case_id = (
            st.session_state.case_info.get("caseReference", "")
            or f"case_{int(datetime.now(timezone.utc).timestamp())}"
        )

        # Initialize cost session if we have a cost estimate
        if st.session_state.cost_estimate:
            st.session_state.cost_session_id = (
                cost_session_manager.initialize_cost_session(
                    case_id=case_id,
                    documents=[],  # Will be updated with processed documents
                    audio_files=[],
                    video_files=[],
                )
            )
            # Update with our existing estimate
            cost_summary = cost_session_manager.get_cost_summary(
                st.session_state.cost_session_id
            )
            if cost_summary:
                cost_summary.cost_estimate = st.session_state.cost_estimate
                cost_session_manager.active_sessions[
                    st.session_state.cost_session_id
                ] = cost_summary

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
        case_doc_sizes = {
            name: size
            for name, size in doc_sizes.items()
            if name
            != (
                st.session_state.intake_form.name
                if st.session_state.intake_form
                else None
            )
        }
        total_case_size = sum(case_doc_sizes.values())

        # Phase 1: Document Processing
        tracker.set_phase(
            "document_processing",
            f"Processing {len(all_files)} files ({total_size / 1024:.1f} KB total)",
        )

        # Separate files by type
        doc_files = []
        audio_files = []
        video_files = []
        for f in all_files:
            file_type = f.type.lower()
            if "audio" in file_type:
                audio_files.append(f)
            elif "video" in file_type:
                video_files.append(f)
            else:
                doc_files.append(f)

        intake_filenames = (
            [st.session_state.intake_form.name] if st.session_state.intake_form else []
        )

        # Process documents, audio, and video in parallel
        doc_processing_task = doc_processor.process_documents_from_streamlit(
            doc_files, intake_filenames
        )
        audio_processing_task = asyncio.gather(
            *[
                audio_processor.process_audio_from_streamlit(f, f.name)
                for f in audio_files
            ]
        )
        # Only process videos if video processor is available
        async def create_video_error(file_name):
            from backend.utils.data_models import MediaProcessingError
            return MediaProcessingError(
                source="VideoProcessor",
                file_name=file_name,
                error_message="Video processing is disabled. Google Cloud credentials are not configured.",
                error_type="ConfigurationError",
            )
        
        if video_processor and hasattr(video_processor, 'enabled') and video_processor.enabled:
            video_processing_task = asyncio.gather(
                *[
                    video_processor.process_video_from_streamlit(f, f.name)
                    for f in video_files
                ]
            )
        else:
            # Return MediaProcessingError for each video file when processor is unavailable
            video_processing_task = asyncio.gather(
                *[
                    create_video_error(f.name)
                    for f in video_files
                ]
            )

        processed_docs, processed_audio, processed_video = await asyncio.gather(
            doc_processing_task, audio_processing_task, video_processing_task
        )

        # Separate intake and case documents
        intake_doc = next(
            (
                doc
                for doc in processed_docs
                if doc.document_type == DocumentType.INTAKE_FORM
            ),
            None,
        )
        case_docs = [
            doc
            for doc in processed_docs
            if doc.document_type != DocumentType.INTAKE_FORM
        ]

        # H3 DEBUG: Intake validation failure point (OLD logic)
        import json
        logger.info(
            f"DEBUG_H3: {json.dumps({'module': 'backend_logic.main_processor', 'hypothesis_id': 'H3', 'action': 'intake_validation_check', 'line': 319, 'intake_doc_found': bool(intake_doc), 'processed_docs_count': len(processed_docs), 'processed_doc_types': [doc.document_type.name for doc in processed_docs], 'architecture': 'OLD_FastAPI'})}"
        )
        
        if not intake_doc:
            msg = "Intake form is required but was not found after processing."
            logger.error(
                f"DEBUG_H3: {json.dumps({'module': 'backend_logic.main_processor', 'hypothesis_id': 'H3', 'action': 'intake_validation_failure', 'line': 321, 'error_message': msg, 'architecture': 'OLD_FastAPI'})}"
            )
            raise ValueError(msg)

        total_processed = (
            len(processed_docs) + len(processed_audio) + len(processed_video)
        )
        tracker.complete_phase(
            "document_processing",
            f"Successfully processed {total_processed} files",
        )

        # Phase 2: Intake Analysis
        tracker.set_phase(
            "intake_analysis", f"Analyzing intake form: {intake_doc.file_name}"
        )

        # Update cost tracking before intake analysis
        if st.session_state.cost_session_id:
            try:
                current_cost_summary = cost_session_manager.get_cost_summary(
                    st.session_state.cost_session_id
                )
                if current_cost_summary and current_cost_summary.actual_costs:
                    current_cost = float(
                        current_cost_summary.actual_costs.total_actual_cost
                    )
                    st.session_state.current_processing_cost = current_cost
                    display_processing_cost_update(current_cost)
            except Exception:
                pass

        analysis_result = await ai_analyzer.analyze_intake(intake_doc)

        if not analysis_result.intake_analysis:
            msg = "Failed to analyze intake form."
            raise ValueError(msg)

        # Update cost tracking after intake analysis
        if st.session_state.cost_session_id:
            try:
                updated_cost_summary = cost_session_manager.get_cost_summary(
                    st.session_state.cost_session_id
                )
                if updated_cost_summary and updated_cost_summary.actual_costs:
                    updated_cost = float(
                        updated_cost_summary.actual_costs.total_actual_cost
                    )
                    st.session_state.current_processing_cost = updated_cost
                    display_processing_cost_update(updated_cost)
            except Exception:
                pass

        tracker.complete_phase("intake_analysis", "Intake analysis completed")

        # Phase 3: Case Document Analysis (Size-based progress)
        if case_docs or processed_audio or processed_video:
            num_docs = len(case_docs)
            num_audio = len(processed_audio)
            num_video = len(processed_video)
            tracker.set_phase(
                "case_analysis",
                f"Starting analysis of {num_docs} documents, {num_audio} audio files, "
                f"and {num_video} video files",
            )

            processed_size = 0

            # Enhanced concurrent analysis with progress tracking and cost monitoring
            async def analyze_with_progress():
                import concurrent.futures
                import functools

                nonlocal processed_size

                # Use the parallelized analyze_case_documents method for concurrent processing
                logger.info(
                    f"MAIN PROCESSOR: 🚀 Starting concurrent analysis of {len(case_docs)} documents..."
                )

                # Initial progress update
                tracker.update_progress(
                    "case_analysis",
                    0.1,
                    f"Initializing concurrent processing of {len(case_docs)} documents",
                )

                # Pre-processing cost update
                if st.session_state.cost_session_id:
                    try:
                        current_cost_summary = cost_session_manager.get_cost_summary(
                            st.session_state.cost_session_id
                        )
                        if current_cost_summary and current_cost_summary.actual_costs:
                            current_cost = float(
                                current_cost_summary.actual_costs.total_actual_cost
                            )
                            st.session_state.current_processing_cost = current_cost
                            display_processing_cost_update(current_cost)
                    except (AttributeError, KeyError, ValueError):
                        pass

                # Use concurrent document analysis (this calls the parallelized method)
                results = await ai_analyzer.analyze_case_documents(
                    case_docs, analysis_result.intake_analysis
                )

                # Post-processing with ThreadPoolExecutor for I/O-bound operations
                def process_cost_tracking_batch(result_batch):
                    """Process cost tracking for a batch of results using ThreadPoolExecutor."""
                    processed_results = []
                    for result in result_batch:
                        if st.session_state.cost_session_id and isinstance(
                            result, AnalyzedDocument
                        ):
                            try:
                                cost_session_manager.update_document_costs(
                                    st.session_state.cost_session_id, [result]
                                )
                                processed_results.append(("success", result))
                            except Exception as e:
                                logger.error(
                                    f"MAIN PROCESSOR: ⚠️ Cost tracking failed for {result.file_name}: {e}"
                                )
                                processed_results.append(("error", result))
                        else:
                            processed_results.append(("no_cost_tracking", result))
                    return processed_results

                # Split results into batches for concurrent processing
                batch_size = 5
                result_batches = [
                    results[i : i + batch_size]
                    for i in range(0, len(results), batch_size)
                ]

                if result_batches and st.session_state.cost_session_id:
                    logger.debug(
                        f"MAIN PROCESSOR: 🚀 Processing cost tracking for {len(results)} results in {len(result_batches)} batches..."
                    )

                    # Use ThreadPoolExecutor for concurrent cost tracking operations
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=3
                    ) as executor:
                        # Submit all batch processing tasks
                        future_to_batch = {
                            executor.submit(process_cost_tracking_batch, batch): batch
                            for batch in result_batches
                        }

                        # Process completed futures
                        for future in concurrent.futures.as_completed(future_to_batch):
                            batch = future_to_batch[future]
                            try:
                                batch_results = future.result()
                                logger.info(
                                    f"MAIN PROCESSOR: ✅ Completed cost tracking for batch of {len(batch)} results"
                                )
                            except Exception as e:
                                logger.error(
                                    f"MAIN PROCESSOR: ❌ Cost tracking batch failed: {e}"
                                )

                # Update progress tracking with the completed results
                tracker.update_progress(
                    "case_analysis",
                    0.9,
                    f"Finalizing analysis of {len(results)} documents",
                )

                # Update final cost tracking
                if st.session_state.cost_session_id:
                    try:
                        updated_cost_summary = cost_session_manager.get_cost_summary(
                            st.session_state.cost_session_id
                        )
                        if updated_cost_summary and updated_cost_summary.actual_costs:
                            updated_cost = float(
                                updated_cost_summary.actual_costs.total_actual_cost
                            )
                            st.session_state.current_processing_cost = updated_cost
                            display_processing_cost_update(updated_cost)
                    except (AttributeError, KeyError, ValueError):
                        pass

                # Add media results to the final analysis (using ThreadPoolExecutor for I/O operations)
                def process_media_results():
                    """Process media results in parallel."""
                    media_errors = []
                    media_insights = []
                    transcripted_media = []

                    for item in processed_audio:
                        if isinstance(item, TranscriptedMedia):
                            transcripted_media.append(item)
                        elif isinstance(item, MediaProcessingError):
                            media_errors.append(
                                AnalysisError(
                                    source=item.source,
                                    file_name=item.file_name,
                                    error_message=item.error_message,
                                )
                            )

                    for item in processed_video:
                        if isinstance(item, VideoInsight):
                            media_insights.append(item)
                        elif isinstance(item, MediaProcessingError):
                            media_errors.append(
                                AnalysisError(
                                    source=item.source,
                                    file_name=item.file_name,
                                    error_message=item.error_message,
                                )
                            )

                    return media_errors, media_insights, transcripted_media

                # Process media results concurrently if there are any
                if processed_audio or processed_video:
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=2
                    ) as executor:
                        media_future = executor.submit(process_media_results)
                        media_errors, media_insights, transcripted_media = (
                            media_future.result()
                        )

                        # Add to analysis result
                        analysis_result.errors.extend(media_errors)
                        analysis_result.video_insights.extend(media_insights)
                        analysis_result.transcripted_media.extend(transcripted_media)

                        logger.info(
                            f"MAIN PROCESSOR: ✅ Processed {len(transcripted_media)} audio and {len(media_insights)} video items"
                        )

                logger.info(
                    f"MAIN PROCESSOR: ✅ Completed concurrent analysis of {len(results)} documents"
                )
                return results

            case_analysis_results = await analyze_with_progress()

            # Process results
            for res in case_analysis_results:
                if isinstance(res, AnalyzedDocument):
                    analysis_result.analyzed_documents.append(res)
                elif isinstance(res, AnalysisError):
                    analysis_result.errors.append(res)

            media_count = len(processed_audio) + len(processed_video)
            tracker.complete_phase(
                "case_analysis",
                f"Analyzed {len(case_docs)} documents and {media_count} media files successfully",
            )
        else:
            tracker.complete_phase(
                "case_analysis", "No case documents or media to analyze"
            )

        # Phase 4: Final Assessment
        tracker.set_phase(
            "final_assessment", "Performing comprehensive legal assessment"
        )

        # Update cost tracking before final assessment
        if st.session_state.cost_session_id:
            try:
                current_cost_summary = cost_session_manager.get_cost_summary(
                    st.session_state.cost_session_id
                )
                if current_cost_summary and current_cost_summary.actual_costs:
                    current_cost = float(
                        current_cost_summary.actual_costs.total_actual_cost
                    )
                    st.session_state.current_processing_cost = current_cost
                    display_processing_cost_update(current_cost)
            except (AttributeError, KeyError, ValueError):
                pass

        final_analysis = await ai_analyzer.perform_final_assessment(analysis_result)

        # Update cost tracking after final assessment
        if st.session_state.cost_session_id:
            try:
                updated_cost_summary = cost_session_manager.get_cost_summary(
                    st.session_state.cost_session_id
                )
                if updated_cost_summary and updated_cost_summary.actual_costs:
                    updated_cost = float(
                        updated_cost_summary.actual_costs.total_actual_cost
                    )
                    st.session_state.current_processing_cost = updated_cost
                    display_processing_cost_update(updated_cost)
            except (AttributeError, KeyError, ValueError):
                pass

        tracker.complete_phase("final_assessment", "Legal assessment completed")

        # Phase 5: Email Generation
        tracker.set_phase("email_generation", "Generating professional findings letter")

        # Update cost tracking before email generation
        if st.session_state.cost_session_id:
            try:
                current_cost_summary = cost_session_manager.get_cost_summary(
                    st.session_state.cost_session_id
                )
                if current_cost_summary and current_cost_summary.actual_costs:
                    current_cost = float(
                        current_cost_summary.actual_costs.total_actual_cost
                    )
                    st.session_state.current_processing_cost = current_cost
                    display_processing_cost_update(current_cost)
            except (AttributeError, KeyError, ValueError):
                pass

        # H1 DEBUG: Email generation start
        import json

        logger.debug(
            f"DEBUG_H1: {json.dumps({'module': 'main_processor', 'hypothesis_id': 'H1', 'action': 'email_generation_start', 'line': 625})}"
        )

        email_docs = email_generator.generate_email_and_analysis_docs(final_analysis)

        # H1 DEBUG: Email generation complete - capture return value analysis
        email_docs_debug = {
            "module": "main_processor",
            "hypothesis_id": "H1",
            "action": "email_generation_complete",
            "line": 627,
            "email_docs_type": str(type(email_docs)),
            "email_docs_keys": list(email_docs.keys())
            if isinstance(email_docs, dict)
            else None,
            "email_docs_length": len(str(email_docs)) if email_docs else 0,
            "has_content": bool(email_docs),
        }
        logger.debug(f"DEBUG_H1: {json.dumps(email_docs_debug)}")

        # H1 DEBUG: Critical issue - No file save operation found after email generation
        logger.debug(
            f"DEBUG_H1: {json.dumps({'module': 'main_processor', 'hypothesis_id': 'H1', 'action': 'file_save_missing', 'line': 628, 'issue': 'No file write operation found after email generation'})}"
        )

        # CRITICAL FIX: Add missing file save operation
        if email_docs and isinstance(email_docs, dict):
            try:
                import os

                # Ensure output directory exists
                output_dir = "validation_output"
                os.makedirs(output_dir, exist_ok=True)

                # Extract HTML content - check multiple possible keys
                html_content = None
                for key in [
                    "letter_content",
                    "main_letter",
                    "rendered_email",
                    "html_content",
                ]:
                    if email_docs.get(key):
                        html_content = email_docs[key]
                        break

                if html_content:
                    output_file = os.path.join(output_dir, "findings_letter.html")
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(html_content)

                    logger.debug(
                        f"DEBUG_FIX: {json.dumps({'module': 'main_processor', 'action': 'file_saved_successfully', 'file_path': output_file, 'content_length': len(html_content)})}"
                    )
                    st.success(
                        f"✅ Findings letter saved successfully to: {output_file}"
                    )
                else:
                    logger.error(
                        f"DEBUG_FIX: {json.dumps({'module': 'main_processor', 'action': 'file_save_failed', 'issue': 'No HTML content found in email_docs', 'available_keys': list(email_docs.keys())})}"
                    )
                    st.warning("⚠️ HTML content not found in generated email data")

            except Exception as e:
                error_msg = f"Failed to save findings letter: {e!s}"
                logger.error(
                    f"DEBUG_FIX: {json.dumps({'module': 'main_processor', 'action': 'file_save_error', 'error': error_msg})}"
                )
                st.error(f"❌ {error_msg}")
        else:
            logger.error(
                f"DEBUG_FIX: {json.dumps({'module': 'main_processor', 'action': 'file_save_failed', 'issue': 'email_docs is None or not a dictionary'})}"
            )
            st.error("❌ Email generation returned invalid data")

        # Update cost tracking after email generation
        if st.session_state.cost_session_id:
            try:
                updated_cost_summary = cost_session_manager.get_cost_summary(
                    st.session_state.cost_session_id
                )
                if updated_cost_summary and updated_cost_summary.actual_costs:
                    # Fix TypeError: Add null checking for total_actual_cost
                    total_cost = updated_cost_summary.actual_costs.total_actual_cost
                    if total_cost is not None:
                        updated_cost = float(total_cost)
                        st.session_state.current_processing_cost = updated_cost
                        display_processing_cost_update(updated_cost)
                    else:
                        # Default to 0.0 if cost is None
                        st.session_state.current_processing_cost = 0.0
                        display_processing_cost_update(0.0)
            except (AttributeError, KeyError, ValueError, TypeError) as e:
                # Enhanced error handling for cost tracking
                logger.error(
                    f"DEBUG_COST: {json.dumps({'module': 'main_processor', 'action': 'cost_tracking_error', 'error': str(e), 'error_type': type(e).__name__})}"
                )

        tracker.complete_phase(
            "email_generation", "Findings letter generated successfully"
        )

        # Finalize cost tracking
        if st.session_state.cost_session_id:
            try:
                # Update cost session with actual results
                cost_summary = cost_session_manager.update_actual_costs(
                    st.session_state.cost_session_id, final_analysis
                )

                # Finalize the session
                st.session_state.cost_summary = (
                    cost_session_manager.finalize_cost_session(
                        st.session_state.cost_session_id
                    )
                )

                # Display final cost summary in sidebar
                if (
                    st.session_state.cost_summary
                    and st.session_state.cost_summary.actual_costs
                    and st.session_state.cost_summary.actual_costs.total_actual_cost
                    is not None
                ):
                    # FIXED: Enhanced error handling for float conversion
                    try:
                        final_cost = float(
                            st.session_state.cost_summary.actual_costs.total_actual_cost
                        )
                        st.sidebar.success(f"✅ Final Processing Cost: ${final_cost:.4f}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"Cost conversion error: {e}, total_cost={st.session_state.cost_summary.actual_costs.total_actual_cost}")
                        st.sidebar.warning("⚠️ Cost data format error - displaying as $0.00")
                        st.sidebar.success("✅ Final Processing Cost: $0.0000")

                    # FIXED: Enhanced error handling for variance conversion
                    if st.session_state.cost_summary.cost_variance is not None:
                        try:
                            variance = float(st.session_state.cost_summary.cost_variance)
                            if abs(variance) <= 0.01:  # Within 1 cent
                                st.sidebar.info("💰 Cost was exactly as estimated!")
                            elif variance > 0:
                                st.sidebar.warning(
                                    f"📈 Cost was ${variance:.4f} over estimate"
                                )
                            else:
                                st.sidebar.info(
                                    f"📉 Cost was ${abs(variance):.4f} under estimate"
                                )
                        except (ValueError, TypeError) as e:
                            logger.error(f"Variance conversion error: {e}, cost_variance={st.session_state.cost_summary.cost_variance}")
                            st.sidebar.info("💰 Cost variance data not available")
                elif st.session_state.cost_summary:
                    # Handle case where cost_summary exists but actual_costs is None or incomplete
                    st.sidebar.info(
                        "💰 Cost tracking initialized but processing not yet completed"
                    )

            except Exception as e:
                st.warning(f"Could not finalize cost tracking: {e!s}")

        # Store results - FIXED: Use correct keys from EmailGeneratorV2
        st.session_state.final_results = final_analysis

        # EmailGeneratorV2 returns "letter_content", not "main_letter"/"appendix"
        if email_docs and isinstance(email_docs, dict):
            # Extract the main letter content using the correct key
            main_letter_content = email_docs.get("letter_content", "")

            # Set both main_letter and appendix to the same content since
            # the new architecture generates a single complete findings letter
            st.session_state.main_letter = main_letter_content
            st.session_state.appendix = main_letter_content  # For UI compatibility
        else:
            # Fallback if email_docs is invalid
            st.session_state.main_letter = ""
            st.session_state.appendix = ""

        st.session_state.processing_status = "completed"

        # Save output files if output_dir is specified
        if output_dir:
            save_output_files(
                output_dir,
                email_docs.get("main_letter", ""),
                email_docs.get("appendix", ""),
                final_analysis,
            )

        # Final success message
        status_text.text("**Analysis Complete!** (100.0%)")
        detail_text.text(
            f"Successfully processed {len(all_files)} documents totaling {total_size / 1024:.1f} KB"
        )
        st.success("Document analysis completed successfully!")

        return True

    except EmailReadabilityError as e:
        logger.error(f"🔍 MAIN_PROCESSOR: EmailReadabilityError caught: {e}")
        st.session_state.processing_status = "failed"
        st.session_state.processing_error = str(e)
        st.error(f"Failed to generate a readable document after multiple attempts: {e}")
        return False

    except Exception as e:
        logger.error(f"🔍 MAIN_PROCESSOR: Exception caught: {e}")
        logger.error(f"🔍 MAIN_PROCESSOR: Exception type: {type(e)}")
        import traceback

        logger.error(f"🔍 MAIN_PROCESSOR: Full traceback: {traceback.format_exc()}")
        st.session_state.processing_status = "failed"
        st.session_state.processing_error = str(e)
        st.error(f"An error occurred during processing: {e}")
        return False


async def process_case_documents_cli(
    intake_form_path: str,
    case_documents_paths: List,
    output_dir: str,
    config_path: Optional[str] = None,
) -> Optional[bool]:
    """
    Command-line version of the case processing function.

    Args:
        intake_form_path: Path to the intake form file
        case_documents_paths: List of paths to case document files
        output_dir: Directory to save output files
        config_path: Path to configuration YAML file for legal practice area-specific prompts
    """
    try:
        logger.info("Initializing processors...")

        # Initialize processors
        from backend_logic.config import get_openai_api_key
        from backend_logic.ai.openai_client import OpenAIClient

        openai_client_wrapper = OpenAIClient(api_key=get_openai_api_key())
        openai_client = openai_client_wrapper.client  # Get the properly configured client
        doc_processor = DocumentProcessor()
        AudioProcessor(openai_client)
        
        # Try to initialize video processor but don't fail if credentials are missing
        try:
            from backend_logic.config import get_settings
            settings = get_settings()
            
            if settings.video_processing_enabled:
                VideoProcessor()
                logger.info("Video processor initialized for CLI mode")
            else:
                logger.info("Video processing disabled in CLI mode - Google Cloud credentials not configured")
        except Exception as e:
            logger.warning(f"Could not initialize video processor in CLI mode: {e}")
        
        ai_analyzer = AIAnalyzer(openai_client, doc_processor, config_path=config_path)
        email_generator = EmailGeneratorV2(openai_client, config_path=config_path)

        logger.debug(f"Processing {len(case_documents_paths) + 1} files...")

        # Process documents
        all_file_paths = [intake_form_path, *case_documents_paths]
        intake_filenames = [Path(intake_form_path).name]

        processed_docs = await doc_processor.process_documents_from_paths(
            all_file_paths, intake_filenames
        )

        # Separate intake and case documents
        intake_doc = next(
            (
                doc
                for doc in processed_docs
                if doc.document_type == DocumentType.INTAKE_FORM
            ),
            None,
        )
        case_docs = [
            doc
            for doc in processed_docs
            if doc.document_type != DocumentType.INTAKE_FORM
        ]

        if not intake_doc:
            msg = "Intake form is required but was not found after processing."
            raise ValueError(msg)

        logger.info("Analyzing intake form...")
        analysis_result = await ai_analyzer.analyze_intake(intake_doc)

        if not analysis_result.intake_analysis:
            msg = "Failed to analyze intake form."
            raise ValueError(msg)

        logger.info(f"Analyzing {len(case_docs)} case documents...")
        if case_docs:
            for doc in case_docs:
                result = await ai_analyzer._analyze_single_document(
                    doc, analysis_result.intake_analysis
                )
                # Add the analyzed document to the results
                if isinstance(result, AnalyzedDocument):
                    analysis_result.analyzed_documents.append(result)
                elif isinstance(result, AnalysisError):
                    analysis_result.errors.append(result)

        logger.info("Performing final assessment...")
        final_analysis = await ai_analyzer.perform_final_assessment(analysis_result)

        logger.info("Generating findings letter...")
        email_docs = email_generator.generate_email_and_analysis_docs(final_analysis)

        logger.info("Saving output files...")
        save_output_files(
            output_dir,
            email_docs.get("main_letter", ""),
            email_docs.get("appendix", ""),
            final_analysis,
        )

        logger.debug("✅ Case processing completed successfully!")
        return True

    except EmailReadabilityError as e:
        logger.error(
            f"❌ EmailReadabilityError: Failed to generate a readable document after multiple attempts: {e}"
        )
        return False

    except Exception as e:
        logger.error(f"❌ Error occurred during processing: {e}")
        return False


def main():
    """Command-line interface for the main processor."""
    parser = argparse.ArgumentParser(
        description="Legal Document Analysis Portal - Case Processing Tool"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        required=True,
        help="Directory where output files should be saved",
    )
    parser.add_argument(
        "--intake_form", type=str, required=True, help="Path to the intake form file"
    )
    parser.add_argument(
        "--case_documents",
        type=str,
        nargs="+",
        default=[],
        help="Paths to case document files or directories containing case documents",
    )
    parser.add_argument(
        "--config_path",
        type=str,
        help="Path to configuration YAML file for legal practice area-specific prompts",
    )

    args = parser.parse_args()

    # Validate input files exist
    if not os.path.exists(args.intake_form):
        logger.info(f"❌ Intake form not found: {args.intake_form}")
        sys.exit(1)

    # Expand directories to include all files within them
    expanded_case_documents = []
    for doc_path in args.case_documents:
        if not os.path.exists(doc_path):
            logger.info(f"❌ Case document path not found: {doc_path}")
            sys.exit(1)

        if os.path.isfile(doc_path):
            # It's a file, add it directly
            expanded_case_documents.append(doc_path)
        elif os.path.isdir(doc_path):
            # It's a directory, find all supported files within it
            logger.info(f"📁 Scanning directory for case documents: {doc_path}")
            supported_extensions = [
                ".pdf",
                ".docx",
                ".doc",
                ".txt",
                ".eml",
                ".jpg",
                ".jpeg",
                ".png",
            ]

            for root, _dirs, files in os.walk(doc_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_ext = os.path.splitext(file)[1].lower()

                    if file_ext in supported_extensions:
                        expanded_case_documents.append(file_path)
                        logger.info(f"  ✓ Found: {file}")

            if not any(
                os.path.join(doc_path, f) in expanded_case_documents
                for f in os.listdir(doc_path)
                if os.path.isfile(os.path.join(doc_path, f))
            ):
                logger.info(f"⚠️  No supported files found in directory: {doc_path}")
        else:
            logger.info(f"❌ Path is neither file nor directory: {doc_path}")
            sys.exit(1)

    # Update the case documents list with expanded paths
    args.case_documents = expanded_case_documents

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)

    logger.info("🚀 Starting Legal Document Analysis...")
    logger.info(f"📁 Output directory: {args.output_dir}")
    logger.info(f"📄 Intake form: {args.intake_form}")
    logger.info(f"📋 Case documents: {len(args.case_documents)} files")

    # Run the async processing function
    success = asyncio.run(
        process_case_documents_cli(
            args.intake_form, args.case_documents, args.output_dir, args.config_path
        )
    )

    if success:
        logger.debug("🎉 Processing completed successfully!")
        sys.exit(0)
    else:
        logger.error("💥 Processing failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
