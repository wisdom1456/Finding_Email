"""UI components for the Legal Document Analysis Portal."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from legal_portal.services.document_formatter import DocumentFormatterService
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


def review_and_confirm_section():
    """Display the interactive review and confirmation screen with editable Q&A pairs."""
    st.header("Step 2: Review & Confirm Intake Information")

    review_data = st.session_state.review_data

    # ===== SECTION 1: Editable Q&A Pairs (Main Focus) =====
    st.subheader("📋 Intake Form Questions & Answers")
    st.info(
        "💡 Review the information below. You can edit answers, add new questions (click ➕), or remove incorrect entries (click 🗑️)."  # noqa: E501
    )

    # Initialize editable Q&A in session state if not present OR if review_data has new intake_qa_pairs
    qa_pairs_from_extraction = review_data.get("intake_qa_pairs", [])

    # Check if we need to initialize or refresh the editable Q&A pairs
    should_initialize = False

    if "editable_qa_pairs" not in st.session_state:
        # First time - initialize
        should_initialize = True
    elif qa_pairs_from_extraction and len(qa_pairs_from_extraction) > len(st.session_state.editable_qa_pairs):
        # New extraction has more pairs than current state - refresh with new data
        should_initialize = True
        logger.info(
            f"Refreshing Q&A pairs: {len(qa_pairs_from_extraction)} extracted vs {len(st.session_state.editable_qa_pairs)} in state"  # noqa: E501
        )

    if should_initialize:
        if qa_pairs_from_extraction:
            st.session_state.editable_qa_pairs = qa_pairs_from_extraction.copy()
            logger.info(f"Initialized editable_qa_pairs with {len(qa_pairs_from_extraction)} extracted pairs")
        else:
            # No extraction data - provide starter questions
            st.session_state.editable_qa_pairs = [
                {"question": "What is the primary legal issue?", "answer": ""},
                {"question": "What is the desired outcome?", "answer": ""},
                {"question": "Are there any deadlines or urgency?", "answer": ""},
            ]
            logger.info("No Q&A pairs extracted - initialized with starter questions")

    # Show warning if extraction failed or returned few results
    if qa_pairs_from_extraction and len(qa_pairs_from_extraction) < 3:
        st.warning(
            "⚠️ Very few questions were detected from the intake form. Please add any missing information using the form below, or refer to the full intake text at the bottom."  # noqa: E501
        )

    # Defensive check: Ensure editable_qa_pairs is a list of dicts
    if not isinstance(st.session_state.editable_qa_pairs, list):
        logger.error(f"editable_qa_pairs is not a list! Type: {type(st.session_state.editable_qa_pairs)}")
        st.error(
            f"⚠️ Data format error. Resetting Q&A pairs. Type was: {type(st.session_state.editable_qa_pairs)}"
        )
        st.session_state.editable_qa_pairs = [
            {"question": "What is the primary legal issue?", "answer": ""},
            {"question": "What is the desired outcome?", "answer": ""},
            {"question": "Are there any deadlines or urgency?", "answer": ""},
        ]

    # Validate each item in the list
    valid_qa_pairs = []
    for item in st.session_state.editable_qa_pairs:
        if isinstance(item, dict):
            # Ensure question and answer keys exist
            valid_qa_pairs.append(
                {"question": str(item.get("question", "")), "answer": str(item.get("answer", ""))}
            )
        else:
            logger.warning(f"Skipping invalid Q&A item: {item} (type: {type(item)})")

    # Update with validated data
    st.session_state.editable_qa_pairs = (
        valid_qa_pairs
        if valid_qa_pairs
        else [
            {"question": "What is the primary legal issue?", "answer": ""},
        ]
    )

    # Show count and stats
    total_pairs = len(st.session_state.editable_qa_pairs)
    answered_pairs = sum(1 for qa in st.session_state.editable_qa_pairs if qa.get("answer", "").strip())
    st.caption(f"📊 {total_pairs} questions extracted • {answered_pairs} answered")

    # Handle large forms
    if total_pairs > 25:
        st.info(
            f"ℹ️ Large form detected ({total_pairs} questions). Consider removing non-essential questions for clarity."  # noqa: E501
        )

    # Display editable data table
    try:
        edited_qa = st.data_editor(
            st.session_state.editable_qa_pairs,
            column_config={
                "question": st.column_config.TextColumn("Question", required=True),
                "answer": st.column_config.TextColumn("Answer", required=False),
            },
            num_rows="dynamic",  # Allow adding/removing rows
            use_container_width=True,
            hide_index=True,
            height=400,  # Limit height for long forms
            key="qa_editor",
        )
    except Exception as e:
        logger.error(f"Error in st.data_editor: {e}", exc_info=True)
        st.error(f"⚠️ Error displaying Q&A editor: {e}")
        # Fallback to simple text areas
        st.warning("Using fallback editor due to error.")
        edited_qa = st.session_state.editable_qa_pairs

    # Update session state with edits (persist across reruns)
    st.session_state.editable_qa_pairs = edited_qa

    st.divider()

    # ===== SECTION 2: Structured Data Summary (Reference) =====
    with st.expander("📊 Structured Data Summary (Auto-extracted for reference)", expanded=False):
        parsed_intake = review_data.get("parsed_intake_data", {})

        if parsed_intake:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Case Summary:**")
                st.write(parsed_intake.get("case_summary", "Not provided"))

                st.markdown("**Desired Outcome:**")
                st.write(parsed_intake.get("desired_outcome", "Not provided"))

            with col2:
                st.markdown("**Urgency Level:**")
                st.write(parsed_intake.get("urgency_level", "Not specified"))

                st.markdown("**Parties Involved:**")
                parties = parsed_intake.get("parties", [])
                if parties:
                    for party in parties:
                        st.write(
                            f"• {party.get('name', 'Unknown')} ({party.get('relationship', 'Unknown relationship')})"  # noqa: E501
                        )
                else:
                    st.write("No parties listed")

            # Display additional fields if present
            additional_fields = parsed_intake.get("additional_fields", {})
            if additional_fields:
                st.divider()
                st.markdown("**Additional Information Extracted:**")
                cols = st.columns(2)
                items = list(additional_fields.items())
                for idx, (field_name, field_value) in enumerate(items):
                    if field_value:  # Only show fields with values
                        with cols[idx % 2]:
                            # Format field name nicely (e.g., "attorney_name" -> "Attorney Name")
                            display_name = field_name.replace("_", " ").title()
                            st.markdown(f"**{display_name}:**")
                            st.write(field_value)
        else:
            st.info("No structured data extracted")

    st.divider()

    # ===== SECTION 3: Confirm Client Name =====
    st.subheader("Confirm Client Name")
    st.info(
        "The client name has been automatically extracted from the intake form. Please confirm or correct it below."  # noqa: E501
    )
    confirmed_client_name = st.text_input(
        "Client Name", value=review_data.get("client_name", ""), key="confirmed_client_name_input"
    )

    # ===== SECTION 4: Prioritize Key Documents =====
    st.subheader("Prioritize Key Documents")
    st.info(
        "You can select up to 3 documents to be given extra weight during the AI analysis. This is optional but recommended for focusing the results."  # noqa: E501
    )
    all_docs = review_data.get("uploaded_files", [])
    key_documents = st.multiselect(
        "Select Key Documents", options=all_docs, max_selections=3, key="key_documents_multiselect"
    )

    # ===== SECTION 5: Define Legal Issue =====
    st.subheader("Define Primary Legal Issue")
    st.info(
        "✨ The AI has analyzed your intake form and auto-selected the most likely legal issue. "
        "Please verify and change if needed."
    )

    # Get AI-suggested practice areas from review_data
    suggested_areas = review_data.get("suggested_practice_areas", ["Other"])

    # Auto-select the first (most relevant) suggestion, but allow user to change
    # Index 0 is the AI's top recommendation
    selected_issue = st.selectbox(
        "Primary Legal Issue (AI-selected, verify or change)",
        options=suggested_areas,
        index=0,  # Auto-select the first (most relevant) option
        key="legal_issue_selectbox",
        help="The AI selected the top match based on your intake form. You can change this if needed.",
    )

    custom_issue = ""
    if selected_issue == "Other":
        custom_issue = st.text_input("Please specify the legal issue:", key="custom_legal_issue_input")

    # ===== SECTION 6: Full Intake Form Text (Reference) =====
    with st.expander("Show Full Intake Form Text for Reference"):
        st.text_area(
            "Intake Form Content",
            value=review_data.get("intake_content", ""),
            height=300,
            key="intake_text_area",
            label_visibility="hidden",
        )

    st.divider()

    # ===== CONFIRMATION BUTTON WITH ENHANCED VALIDATION =====
    if st.button("Confirm & Start Full Analysis", type="primary"):
        # Validation: Client Name
        if not confirmed_client_name:
            st.warning("⚠️ Client Name cannot be empty.")
            return

        # Validation: Legal Issue (now just check for "Other" with no custom text)
        if selected_issue == "Other" and not custom_issue:
            st.warning("⚠️ Please specify the legal issue when 'Other' is selected.")
            return

        # Validation: Q&A has sufficient content
        valid_qa_count = sum(
            1 for qa in edited_qa if qa.get("question", "").strip() and qa.get("answer", "").strip()
        )
        if valid_qa_count < 2:
            st.warning(
                "⚠️ Please provide at least 2 complete question-answer pairs with both question and answer filled."  # noqa: E501
            )
            return

        # Save the confirmed and selected data back to session state to be used by the main processor
        st.session_state.case_info["clientName"] = confirmed_client_name
        st.session_state.review_data["key_documents"] = key_documents
        st.session_state.review_data["legal_issue"] = (
            custom_issue if selected_issue == "Other" else selected_issue
        )
        st.session_state.review_data["confirmed_qa_pairs"] = edited_qa  # NEW: Save confirmed Q&A

        # Log confirmation for debugging
        logger.info(f"User confirmed {len(edited_qa)} Q&A pairs for analysis")
        logger.info(f"Selected legal issue: {st.session_state.review_data['legal_issue']}")

        # Set flag to start the analysis
        st.session_state.start_full_analysis = True
        st.rerun()


def case_information_form():
    """Render the case information form in the sidebar."""
    st.sidebar.header("Case Information")

    # Test Data Button
    st.sidebar.text("---")

    st.session_state.case_info["clientName"] = st.sidebar.text_input(
        "Client Name", value=st.session_state.case_info["clientName"]
    )
    st.session_state.case_info["attorneyName"] = st.sidebar.text_input(
        "Attorney Name", value=st.session_state.case_info["attorneyName"]
    )
    st.session_state.case_info["caseReference"] = st.sidebar.text_input(
        "Case Reference", value=st.session_state.case_info["caseReference"]
    )

    # Optional contact information for letter footer
    st.sidebar.text("---")
    st.sidebar.caption("Optional Contact Information (for letter)")
    st.session_state.case_info["contactPhone"] = st.sidebar.text_input(
        "Contact Phone",
        value=st.session_state.case_info.get("contactPhone", "(727) 275-9575"),
        placeholder="e.g., (555) 123-4567",
        help="Phone number for letter footer",
    )
    st.session_state.case_info["contactEmail"] = st.sidebar.text_input(
        "Contact Email",
        value=st.session_state.case_info.get("contactEmail", ""),
        placeholder="e.g., contact@lawfirm.com",
        help="Optional: If provided, replaces [EMAIL PLACEHOLDER] in letter",
    )


def file_upload_section():
    """Gated two-step upload: CLIO selection first, then documents."""
    import os

    # Check if CLIO is configured
    clio_enabled = bool(os.getenv("CLIO_CLIENT_ID") and os.getenv("CLIO_CLIENT_SECRET"))

    if not clio_enabled:
        # No CLIO - go straight to manual upload
        _show_manual_upload_section()
        return

    # === Step 1: Matter Selection (Gated) ===
    st.subheader("Step 1: Select CLIO Matter (Optional)")

    matter_selected = st.session_state.get("clio_selected_matter") is not None
    matter_skipped = st.session_state.get("clio_matter_skipped", False)
    step1_complete = matter_selected or matter_skipped

    if not step1_complete:
        # Show CLIO connection/search
        from legal_portal.ui.components.clio_integration_ui import (
            clio_connection_section,
            matter_search_section,
        )

        if not st.session_state.get("clio_authenticated"):
            clio_connection_section()
        else:
            matter_search_section()

            st.divider()
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button(
                    "📝 No CLIO matter available - Skip to document upload", use_container_width=True
                ):
                    st.session_state.clio_matter_skipped = True
                    st.rerun()
    else:
        # Show selection summary
        if matter_selected:
            matter = st.session_state.clio_selected_matter
            st.success(f"✅ Matter selected: **{matter.display_number}** - {matter.client_name}")
            col1, col2 = st.columns([3, 1])
            with col1:
                if matter.description:
                    st.caption(
                        matter.description[:100] + "..."
                        if len(matter.description) > 100
                        else matter.description
                    )
            with col2:
                if st.button("Change matter"):
                    st.session_state.clio_selected_matter = None
                    st.session_state.clio_imported_data = None
                    st.session_state.clio_processed_docs = []
                    st.rerun()
        else:
            st.info("ℹ️ Proceeding without CLIO matter")
            if st.button("Select a matter instead"):
                st.session_state.clio_matter_skipped = False
                st.rerun()

    st.divider()

    # === Step 2: Document Upload (Only shown after Step 1) ===
    if step1_complete:
        st.subheader("Step 2: Upload Case Documents")
        _show_manual_upload_section()
    else:
        st.info("👆 Please select a CLIO matter or click 'No CLIO matter available' to continue")


def _show_manual_upload_section():
    """Show manual file upload interface."""
    uploaded_files = st.file_uploader(
        "Select intake form and case documents (TXT, PDF, DOCX, DOC, PNG, JPG, EML, CSV, ZIP)",
        type=["txt", "pdf", "docx", "doc", "png", "jpg", "jpeg", "eml", "csv", "zip"],
        accept_multiple_files=True,
        key="manual_file_uploader",
    )

    if uploaded_files:
        st.session_state.uploaded_files = uploaded_files
        # Don't set data_source here - will be determined during preparation

        # Check for large files
        large_files = [f for f in uploaded_files if f.size > 10 * 1024 * 1024]
        if large_files:
            st.warning(f"{len(large_files)} large file(s) detected. Compressing is recommended.")
            compress_choice = st.checkbox("✅ Compress large files before analysis", value=True)
            st.session_state.compress_files = compress_choice
        else:
            st.session_state.compress_files = False

        # Show file count
        st.success(f"✅ {len(uploaded_files)} file(s) ready for upload")

        # Show detailed file list with zip file hierarchy
        _display_uploaded_files_list(uploaded_files)

    # Show any currently uploaded files
    elif st.session_state.get("uploaded_files"):
        current_files = st.session_state.uploaded_files
        st.info(f"📁 {len(current_files)} file(s) currently uploaded")
        _display_uploaded_files_list(current_files)
        if st.button("Clear uploaded files"):
            st.session_state.uploaded_files = []
            st.rerun()


def _display_uploaded_files_list(uploaded_files):
    """Display uploaded files with special visualization for zip files."""
    import os
    import tempfile
    import zipfile
    from pathlib import Path

    st.markdown("### 📋 Files to be processed:")

    # Custom CSS for zip file highlighting
    st.markdown(
        """
        <style>
        .zip-file {
            background-color: #fff3cd;
            padding: 8px 12px;
            border-radius: 4px;
            margin: 4px 0;
            border-left: 4px solid #ffc107;
            font-weight: 600;
        }
        .extracted-file {
            padding: 4px 12px 4px 32px;
            margin: 2px 0;
            color: #666;
            font-size: 0.9em;
        }
        .regular-file {
            padding: 4px 12px;
            margin: 2px 0;
        }
        .file-icon {
            margin-right: 8px;
        }
        </style>
    """,
        unsafe_allow_html=True,
    )

    # Define video and audio file extensions to skip
    video_audio_extensions = [
        ".mov",
        ".mp4",
        ".avi",
        ".mkv",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",  # Video
        ".mp3",
        ".wav",
        ".aac",
        ".flac",
        ".m4a",
        ".ogg",
        ".wma",
        ".aiff",  # Audio
    ]

    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name
        file_size_mb = uploaded_file.size / (1024 * 1024)

        # Check if it's a zip file
        if file_name.lower().endswith(".zip"):
            # Display zip file with yellow highlight
            st.markdown(
                f'<div class="zip-file">'
                f'<span class="file-icon">📦</span>{file_name} '
                f'<span style="color: #666; font-weight: normal;">({file_size_mb:.2f} MB)</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

            # Try to peek into the zip file to show its contents
            try:
                # Create a temporary file to read the zip
                with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_path = tmp_file.name

                # Read zip contents
                try:
                    with zipfile.ZipFile(tmp_path, "r") as zip_ref:
                        zip_contents = zip_ref.namelist()

                        # Filter out hidden files and system files
                        visible_files = [
                            f
                            for f in zip_contents
                            if not any(
                                part.startswith(".") or part.startswith("__MACOSX") for part in Path(f).parts
                            )
                            and not f.endswith("/")  # Skip directories
                        ]

                        # Show extracted files indented
                        included_count = 0
                        skipped_count = 0

                        for extracted_file in visible_files:
                            Path(extracted_file).suffix.lower()

                            # Check if file will be skipped
                            if any(extracted_file.lower().endswith(ext) for ext in video_audio_extensions):
                                st.markdown(
                                    f'<div class="extracted-file" style="color: #999;">'
                                    f'<span class="file-icon">⏭️</span>↳ {Path(extracted_file).name} '
                                    f'<span style="font-style: italic;">(will be skipped - video/audio)</span>'
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                                skipped_count += 1
                            else:
                                st.markdown(
                                    f'<div class="extracted-file">'
                                    f'<span class="file-icon">✓</span>↳ {Path(extracted_file).name}'
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                                included_count += 1

                        # Show summary
                        if included_count > 0 or skipped_count > 0:
                            summary_parts = []
                            if included_count > 0:
                                summary_parts.append(f"{included_count} file(s) will be processed")
                            if skipped_count > 0:
                                summary_parts.append(f"{skipped_count} file(s) will be skipped")

                            st.markdown(
                                f'<div class="extracted-file" style="color: #666; font-style: italic;">'
                                f'<span class="file-icon">ℹ️</span>↳ {", ".join(summary_parts)}'
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                except zipfile.BadZipFile:
                    st.markdown(
                        '<div class="extracted-file" style="color: #dc3545;">'
                        '<span class="file-icon">⚠️</span>↳ Invalid zip file - cannot extract'
                        "</div>",
                        unsafe_allow_html=True,
                    )
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

            except Exception:
                st.markdown(
                    '<div class="extracted-file" style="color: #dc3545;">'
                    '<span class="file-icon">⚠️</span>↳ Error reading zip contents'
                    "</div>",
                    unsafe_allow_html=True,
                )
        else:
            # Regular file - check if it will be skipped
            if any(file_name.lower().endswith(ext) for ext in video_audio_extensions):
                st.markdown(
                    f'<div class="regular-file" style="color: #999;">'
                    f'<span class="file-icon">⏭️</span>{file_name} '
                    f'<span style="color: #999;">({file_size_mb:.2f} MB)</span> '
                    f'<span style="font-style: italic;">(will be skipped - video/audio)</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="regular-file">'
                    f'<span class="file-icon">📄</span>{file_name} '
                    f'<span style="color: #666;">({file_size_mb:.2f} MB)</span>'
                    f"</div>",
                    unsafe_allow_html=True,
                )


def results_display_section():
    """Display the final results and download links."""
    if st.session_state.get("final_results"):
        st.header("Results")

        # Get client name for formatting
        client_name = "Client"
        if st.session_state.get("case_info"):
            client_name = st.session_state.case_info.get("clientName", "Client") or "Client"

        # DEBUG: Log what we're passing to formatter
        logger.info(f"Formatting reports with client_name: '{client_name}'")

        # Create tabs for organized display
        tab_titles = [
            "📧 Client Letter (Clean)",
            "📚 Attorney Letter (With Citations)",
            "📄 Document Review",
            "⚖️ Case Analysis",
        ]
        if st.session_state.get("quality_report"):
            tab_titles.append("📊 Quality Report")

        tabs = st.tabs(tab_titles)

        # Client Letter Tab (Clean - No Citations)
        with tabs[0]:
            st.markdown(
                """
                <div style="background-color: #e8f4f8; padding: 12px; border-radius: 8px; border-left: 4px solid #0066cc; margin-bottom: 16px;">
                    <strong>📧 Client-Ready Letter</strong><br/>
                    <span style="color: #555; font-size: 14px;">
                        Clean version without source citations - ready to send to the client.
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # DEBUG: Check for citations in clean letter
            main_letter_content = st.session_state.get("main_letter", "")
            has_source_citations = "[Source:" in main_letter_content or "(Source:" in main_letter_content
            if has_source_citations:
                citation_count = main_letter_content.count("[Source:") + main_letter_content.count("(Source:")
                st.error(
                    f"🐛 DEBUG: Clean letter contains {citation_count} citation(s) - this should not happen!"
                )
                st.warning(f"Letter length: {len(main_letter_content)} chars")
            else:
                st.success(f"✅ Clean letter has no citations (length: {len(main_letter_content)} chars)")

            # Display the main findings email
            if st.session_state.get("main_letter"):
                # Wrap the letter content with explicit styling to force white background and black text
                # This ensures the content is readable in both light and dark modes
                wrapped_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        html, body {{
                            background-color: #ffffff !important;
                            color: #000000 !important;
                            margin: 0;
                            padding: 0;
                        }}
                        * {{
                            color: inherit;
                        }}
                    </style>
                </head>
                <body>
                    {st.session_state.main_letter}
                </body>
                </html>
                """

                # Display the letter directly without cleaning citations
                components.html(wrapped_html, height=800, scrolling=True, width=None)
            else:
                st.info("The findings email is being generated.")

        # Attorney Review Letter Tab (With Citations)
        with tabs[1]:
            st.markdown(
                """
                <div style="background-color: #fff8e8; padding: 12px; border-radius: 8px; border-left: 4px solid #ff9800; margin-bottom: 16px;">
                    <strong>📚 Attorney Review Version</strong><br/>
                    <span style="color: #555; font-size: 14px;">
                        Contains inline source citations (Source: filename.pdf) for fact verification.
                        Use this version to review the evidence supporting each statement.
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # DEBUG: Check for citations in cited letter
            cited_letter_content = st.session_state.get("main_letter_with_citations", "")
            has_source_citations_cited = (
                "[Source:" in cited_letter_content or "(Source:" in cited_letter_content
            )
            if has_source_citations_cited:
                citation_count_cited = cited_letter_content.count("[Source:") + cited_letter_content.count(
                    "(Source:"
                )
                st.success(f"✅ Cited letter contains {citation_count_cited} citation(s) as expected")
                st.info(f"Letter length: {len(cited_letter_content)} chars")
            else:
                st.error("🐛 DEBUG: Cited letter has NO citations - something went wrong!")
                st.warning(f"Letter length: {len(cited_letter_content)} chars")

            # Display the findings email with citations
            if st.session_state.get("main_letter_with_citations"):
                # Wrap the cited letter content with explicit styling
                wrapped_cited_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        html, body {{
                            background-color: #ffffff !important;
                            color: #000000 !important;
                            margin: 0;
                            padding: 0;
                        }}
                        * {{
                            color: inherit;
                        }}
                        /* Style for citation links */
                        sup a {{
                            color: #0066cc !important;
                            text-decoration: none;
                        }}
                        sup a:hover {{
                            text-decoration: underline;
                        }}
                    </style>
                </head>
                <body>
                    {st.session_state.main_letter_with_citations}
                </body>
                </html>
                """

                # Display the cited letter
                components.html(wrapped_cited_html, height=800, scrolling=True, width=None)
            else:
                st.info("The cited letter is being generated or citations are unavailable.")

        # Document Review Tab
        with tabs[2]:
            # Display the formatted document review
            if st.session_state.get("document_review"):
                formatter = DocumentFormatterService()
                formatted_review = formatter.format_document_review(
                    st.session_state.document_review, client_name
                )

                # Wrap with white background styling
                wrapped_review = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        html, body {{
                            background-color: #ffffff !important;
                            margin: 0;
                            padding: 0;
                        }}
                    </style>
                </head>
                <body>
                    {formatted_review}
                </body>
                </html>
                """

                components.html(wrapped_review, height=800, scrolling=True, width=None)
            else:
                st.info("Document review is not available.")

        # Case Analysis Tab
        with tabs[3]:
            # Display the formatted case analysis
            if st.session_state.get("case_analysis"):
                formatter = DocumentFormatterService()
                formatted_analysis = formatter.format_case_analysis(
                    st.session_state.case_analysis, client_name
                )

                # Wrap with white background styling
                wrapped_analysis = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        html, body {{
                            background-color: #ffffff !important;
                            margin: 0;
                            padding: 0;
                        }}
                    </style>
                </head>
                <body>
                    {formatted_analysis}
                </body>
                </html>
                """

                components.html(wrapped_analysis, height=800, scrolling=True, width=None)
            else:
                st.info("Case analysis is not available.")

        # Quality Report Tab (conditionally displayed)
        if len(tabs) > 4:
            with tabs[4]:
                st.subheader("Document Quality & Integrity Report")
                quality_report_data = st.session_state.quality_report
                if quality_report_data:
                    formatter = DocumentFormatterService()
                    report_html = formatter.format_quality_report(quality_report_data)
                    components.html(report_html, height=800, scrolling=True)
                else:
                    st.info("No quality report data is available.")

        # Provide download buttons below tabs
        st.subheader("Download Options")
        col1, col2, col3, col4 = st.columns(4)
        _display_download_buttons(col1, col2, col3, col4)

        # Display any errors that occurred
        if st.session_state.get("errors"):
            st.error("Errors occurred during processing:")
            for error in st.session_state.errors:
                st.warning(f"**{error.source}**: {error.error_message}")


def _display_download_buttons(col1, col2, col3, col4):
    """Display download buttons for the findings emails (clean and cited), document review, and case analysis."""  # noqa: E501
    # Get client name for filename
    client_name = "Client"
    if st.session_state.get("case_info"):
        client_name_raw = st.session_state.case_info.get("clientName", "Client")
        client_name = "".join(c for c in client_name_raw if c.isalnum() or c in " _-").rstrip()

    if not client_name:
        client_name = "Client"

    formatter = DocumentFormatterService()

    with col1:
        # Download button for clean findings email (no citations)
        try:
            if st.session_state.get("main_letter"):
                main_letter_bytes = st.session_state.main_letter.encode("utf-8")
                st.download_button(
                    label="📧 Findings Email",
                    data=main_letter_bytes,
                    file_name=f"Findings_Letter_{client_name}.html",
                    mime="text/html",
                    help="Download findings email (clean version)",
                )
        except Exception as e:
            st.error(f"Error: {e}")

    with col2:
        # Download button for cited findings email (NEW)
        try:
            if st.session_state.get("main_letter_with_citations"):
                cited_letter_bytes = st.session_state.main_letter_with_citations.encode("utf-8")
                st.download_button(
                    label="📚 Letter (Cited)",
                    data=cited_letter_bytes,
                    file_name=f"Findings_Letter_Cited_{client_name}.html",
                    mime="text/html",
                    help="With citations and source references",
                )
            else:
                st.info("Citations unavailable", icon="ℹ️")
        except Exception as e:
            st.error(f"Error: {e}")

    with col3:
        # Download button for document review (formatted HTML) - MOVED from col2
        try:
            if st.session_state.get("document_review"):
                # Format the document review as HTML
                formatted_review = formatter.format_document_review(
                    st.session_state.document_review, client_name
                )
                doc_review_bytes = formatted_review.encode("utf-8")
                st.download_button(
                    label="📄 Doc Review",
                    data=doc_review_bytes,
                    file_name=f"Document_Review_{client_name}.html",
                    mime="text/html",
                    help="Download the formatted document review.",
                )
        except Exception as e:
            st.error(f"Error: {e}")

    with col4:
        # Download button for case analysis (formatted HTML) - MOVED from col3
        try:
            if st.session_state.get("case_analysis"):
                # Format the case analysis as HTML
                formatted_analysis = formatter.format_case_analysis(
                    st.session_state.case_analysis, client_name
                )
                case_analysis_bytes = formatted_analysis.encode("utf-8")

                st.download_button(
                    label="⚖️ Case Analysis",
                    data=case_analysis_bytes,
                    file_name=f"Case_Analysis_{client_name}.html",
                    mime="text/html",
                    help="Download the formatted case analysis.",
                )
        except Exception as e:
            st.error(f"Error: {e}")
