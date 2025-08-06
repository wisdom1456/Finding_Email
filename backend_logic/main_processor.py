"""
Main processing module for the Legal Document Analysis Portal.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

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
from backend_logic.ai_analyzer import AIAnalyzer
from backend_logic.audio_processor import AudioProcessor
from backend_logic.config import get_openai_api_key
from backend_logic.cost_session_manager import CostSessionManager
from backend_logic.document_processor import DocumentProcessor
from backend_logic.email_generator import EmailGenerator
from backend_logic.video_processor import VideoProcessor
from backend_logic.utils import (
    ProgressTracker,
    calculate_document_sizes,
    display_processing_cost_update,
)

async def process_case_documents():
    """
    Enhanced processing function with size-based progress tracking and cost tracking.
    """
    try:
        st.session_state.processing_status = "active"
        st.session_state.processing_error = None

        # Initialize processors
        openai_client = OpenAI(api_key=get_openai_api_key())
        doc_processor = DocumentProcessor()
        audio_processor = AudioProcessor(openai_client)
        video_processor = VideoProcessor()
        ai_analyzer = AIAnalyzer(openai_client, doc_processor)
        email_generator = EmailGenerator(openai_client)

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
        video_processing_task = asyncio.gather(
            *[
                video_processor.process_video_from_streamlit(f, f.name)
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

        if not intake_doc:
            msg = "Intake form is required but was not found after processing."
            raise ValueError(msg)

        total_processed = len(processed_docs) + len(processed_audio) + len(processed_video)
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

            # Custom progress callback for document analysis with cost tracking
            async def analyze_with_progress():
                nonlocal processed_size
                results = []

                # Analyze documents
                for i, doc in enumerate(case_docs):
                    doc_size = case_doc_sizes.get(doc.file_name, 1024)
                    current_doc_progress = (
                        processed_size / total_case_size
                        if total_case_size > 0
                        else (i / len(case_docs))
                    )

                    progress_msg = (
                        f"Processing {i + 1}/{len(case_docs)}: {doc.file_name} "
                        f"({doc_size / 1024:.1f} KB)"
                    )
                    tracker.update_progress(
                        "case_analysis",
                        current_doc_progress,
                        progress_msg,
                    )

                    # Update real-time cost tracking before processing
                    if st.session_state.cost_session_id:
                        try:
                            current_cost_summary = (
                                cost_session_manager.get_cost_summary(
                                    st.session_state.cost_session_id
                                )
                            )
                            if (
                                current_cost_summary
                                and current_cost_summary.actual_costs
                            ):
                                current_cost = float(
                                    current_cost_summary.actual_costs.total_actual_cost
                                )
                                st.session_state.current_processing_cost = current_cost
                                display_processing_cost_update(current_cost)
                        except (AttributeError, KeyError, ValueError):
                            pass  # Continue processing even if cost update fails

                    result = await ai_analyzer._analyze_single_document(
                        doc, analysis_result.intake_analysis
                    )
                    results.append(result)

                    # Update cost tracking after processing document
                    if st.session_state.cost_session_id and isinstance(
                        result, AnalyzedDocument
                    ):
                        try:
                            # Update the cost session with the newly processed document
                            cost_session_manager.update_document_costs(
                                st.session_state.cost_session_id, [result]
                            )

                            # Get updated cost and display
                            updated_cost_summary = (
                                cost_session_manager.get_cost_summary(
                                    st.session_state.cost_session_id
                                )
                            )
                            if (
                                updated_cost_summary
                                and updated_cost_summary.actual_costs
                            ):
                                updated_cost = float(
                                    updated_cost_summary.actual_costs.total_actual_cost
                                )
                                st.session_state.current_processing_cost = updated_cost
                                display_processing_cost_update(updated_cost)
                        except (AttributeError, KeyError, ValueError):
                            pass  # Continue processing even if cost update fails

                    processed_size += doc_size
                    final_progress = (
                        processed_size / total_case_size
                        if total_case_size > 0
                        else ((i + 1) / len(case_docs))
                    )

                    tracker.update_progress(
                        "case_analysis",
                        final_progress,
                        f"Completed {i + 1}/{len(case_docs)} documents",
                    )

                    if i < len(case_docs) - 1:
                        await asyncio.sleep(3)

                # Add media results to the final analysis
                for item in processed_audio:
                    if isinstance(item, TranscriptedMedia):
                        analysis_result.transcripted_media.append(item)
                    elif isinstance(item, MediaProcessingError):
                        analysis_result.errors.append(
                            AnalysisError(
                                source=item.source,
                                file_name=item.file_name,
                                error_message=item.error_message,
                            )
                        )

                for item in processed_video:
                    if isinstance(item, VideoInsight):
                        analysis_result.video_insights.append(item)
                    elif isinstance(item, MediaProcessingError):
                        analysis_result.errors.append(
                            AnalysisError(
                                source=item.source,
                                file_name=item.file_name,
                                error_message=item.error_message,
                            )
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

        email_docs = email_generator.generate_email_and_analysis_docs(final_analysis)

        # Update cost tracking after email generation
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
                ):
                    final_cost = float(
                        st.session_state.cost_summary.actual_costs.total_actual_cost
                    )
                    st.sidebar.success(f"✅ Final Processing Cost: ${final_cost:.4f}")

                    if st.session_state.cost_summary.cost_variance is not None:
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

            except Exception as e:
                st.warning(f"Could not finalize cost tracking: {e!s}")

        # Store results
        st.session_state.final_results = final_analysis
        st.session_state.main_letter = email_docs.get("main_letter", "")
        st.session_state.appendix = email_docs.get("appendix", "")
        st.session_state.processing_status = "completed"

        # Final success message
        status_text.text("**Analysis Complete!** (100.0%)")
        detail_text.text(
            f"Successfully processed {len(all_files)} documents totaling {total_size / 1024:.1f} KB"
        )
        st.success("Document analysis completed successfully!")

        return True

    except Exception as e:
        st.session_state.processing_status = "failed"
        st.session_state.processing_error = str(e)
        st.error(f"An error occurred during processing: {e}")
        return False