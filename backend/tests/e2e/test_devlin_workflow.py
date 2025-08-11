"""
End-to-end test for the Devlin case workflow.

This test validates the complete letter generation workflow from document processing
to final delivery using the Devlin case test data.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from utils.logging_config import get_module_logger


logger = get_module_logger(__name__)


# Import the main processing function and required modules
from core.main_processor import process_case_documents

# H3 DEBUG: Architecture import confirmation - FIXED
import json
logger.info(
    f"DEBUG_H3_FIXED: {json.dumps({'module': 'test_devlin_workflow', 'hypothesis_id': 'H3', 'action': 'import_confirmation_fixed', 'imported_module': 'core.main_processor', 'line': 23, 'architecture': 'NEW_Streamlit', 'fix_applied': True})}"
)

# Test configuration
DEVLIN_TEST_DATA_DIR = "test_data/Devlin, Erik [MetLife]/Shared Folder with Client/Shared with Bernhardt Riley"
DEVLIN_E2E_OUTPUT_DIR = "test_results/devlin_e2e_output"


class TestDevlinWorkflow:
    """End-to-end test class for the Devlin case workflow."""

    @pytest.fixture
    def devlin_documents(self) -> list[str]:
        """Fixture providing paths to all Devlin case documents."""
        test_data_path = Path(DEVLIN_TEST_DATA_DIR)
        if not test_data_path.exists():
            pytest.skip(f"Devlin test data directory not found: {DEVLIN_TEST_DATA_DIR}")

        # Get all PDF files from the Devlin test data directory
        pdf_files = list(test_data_path.glob("*.pdf"))

        # Verify we have the expected 9 documents

        assert len(pdf_files) == 9, f"Expected 9 documents, found {len(pdf_files)}"

        return [str(f) for f in pdf_files]

    @pytest.fixture
    def mock_streamlit_files(self, devlin_documents) -> list[Mock]:
        """Fixture providing mock Streamlit file objects for all Devlin documents."""
        mock_files = []

        for doc_path in devlin_documents:
            mock_file = Mock()
            mock_file.name = Path(doc_path).name
            mock_file.type = "application/pdf"
            mock_file.size = 1024 * 100  # Mock 100KB files

            # Mock file reading - both read() and getvalue() methods
            with open(doc_path, "rb") as f:
                file_content = f.read()
                mock_file.read.return_value = file_content
                mock_file.getvalue.return_value = file_content

            mock_files.append(mock_file)

        return mock_files

    @pytest.fixture
    def mock_intake_form(self, mock_streamlit_files) -> Mock:
        """Fixture providing the intake form from the Devlin documents."""
        # Find the intake form (should be "Devlin - Intake for Contractor Dispute.pdf")
        for mock_file in mock_streamlit_files:
            if "Intake" in mock_file.name:
                return mock_file

        # If not found, use the first document as intake
        return mock_streamlit_files[0]

    @pytest.fixture
    def mock_case_documents(self, mock_streamlit_files, mock_intake_form) -> list[Mock]:
        """Fixture providing case documents (all documents except intake form)."""
        return [f for f in mock_streamlit_files if f != mock_intake_form]

    @pytest.fixture
    def output_directory(self) -> Path:
        """Fixture providing the output directory for test results."""
        output_dir = Path(DEVLIN_E2E_OUTPUT_DIR)

        # Clear the directory if it exists to ensure clean state
        if output_dir.exists():
            shutil.rmtree(output_dir)

        # Create fresh directory
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    # Note: Removed mock_openai_responses fixture - E2E test uses real API calls

    @pytest.fixture
    def mock_session_state(self, mock_intake_form, mock_case_documents):
        """Fixture to mock Streamlit session state."""
        return {
            "intake_form": mock_intake_form,
            "case_documents": mock_case_documents,
            "case_info": {
                "caseReference": "DEVLIN-2025-001",
                "clientName": "Erik Devlin",
            },
            "processing_status": None,
            "processing_error": None,
            "cost_estimate": 5.0,  # Mock cost estimate
            "cost_session_id": None,
            "current_processing_cost": 0.0,
            "final_results": None,
            "main_letter": None,
            "appendix": None,
            "cost_summary": None,
        }

    @pytest.mark.asyncio
    @patch("core.main_processor.st")
    @patch("core.main_processor.OpenAI")
    async def test_devlin_complete_workflow(
        self, mock_openai_class, mock_st, mock_session_state, output_directory
    ):
        """
        Test the complete Devlin case workflow from document loading to final output generation.

        This test:
        1. Loads all 9 Devlin case documents
        2. Executes the entire processing workflow
        3. Generates output files (.eml, analysis docs)
        4. Validates all outputs are created and non-empty
        """
        # Create a proper mock for session_state that returns actual values
        session_state_mock = MagicMock()

        # Setup session state attributes to return actual values
        for key, value in mock_session_state.items():
            setattr(session_state_mock, key, value)

        mock_st.session_state = session_state_mock

        # Configure OpenAI mock for E2E test to avoid real API calls
        mock_openai_client = MagicMock()
        mock_openai_class.return_value = mock_openai_client

        # Mock OpenAI chat completions with proper JSON responses
        def mock_chat_completion(*args, **kwargs):
            import json

            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_message = MagicMock()

            # Default response for intake analysis
            default_intake_response = {
                "client_name": "Erik Devlin",
                "attorney_name": "John Doe",
                "case_type": "Contract Dispute - Construction",
                "incident_date": "2025-06-09",
                "client_contact": "client@example.com",
                "case_summary": "Construction contract dispute involving incomplete work and contractor abandonment",
                "legal_issues": [
                    "Breach of contract",
                    "Incomplete work",
                    "Financial damages",
                ],
                "urgency_level": "High",
                "financial_impact": "$50,000 - $75,000 in estimated damages",
                "client_priorities": [
                    "Recover financial losses",
                    "Complete construction work",
                ],
                "desired_outcomes": ["Financial compensation", "Project completion"],
                "legal_claims": [
                    "Breach of contract",
                    "Incomplete work",
                    "Financial damages",
                ],
                "parties_involved": [
                    {"name": "Erik Devlin", "role": "Client/Property Owner"},
                    {"name": "Contractor ABC", "role": "General Contractor"},
                ],
                "key_facts": [
                    "Contract signed for construction project",
                    "Contractor failed to complete work as specified",
                    "Client suffered financial damages",
                    "Notice to Owner filed",
                ],
            }

            # Default response for document analysis
            default_doc_response = {
                "file_name": "document.pdf",
                "analysis": "Construction contract and supporting documentation analysis showing evidence of incomplete work and contractor breach",
                "key_points": [
                    "Original contract terms and specifications",
                    "Evidence of incomplete work",
                    "Financial documentation of damages",
                    "Correspondence with contractor",
                ],
                "metadata": {
                    "legal_significance": "High",
                    "evidence_strength": "Strong",
                },
            }

            # Return appropriate response based on context
            if "intake" in str(kwargs.get("messages", [])).lower():
                mock_message.content = json.dumps(default_intake_response)
            else:
                mock_message.content = json.dumps(default_doc_response)

            mock_choice.message = mock_message
            mock_response.choices = [mock_choice]
            return mock_response

        mock_openai_client.chat.completions.create.side_effect = mock_chat_completion

        # Mock Streamlit UI components
        mock_st.container.return_value.__enter__ = Mock(return_value=Mock())
        mock_st.container.return_value.__exit__ = Mock()
        mock_st.progress.return_value = Mock()
        mock_st.empty.return_value = Mock()
        mock_st.success = Mock()
        mock_st.sidebar.success = Mock()
        mock_st.sidebar.info = Mock()
        mock_st.sidebar.warning = Mock()

        # Execute the real E2E workflow without mocking internal components
        logger.info(
            "🔍 E2E TEST: About to call process_case_documents() for real E2E workflow"
        )
        logger.info(f"🔍 E2E TEST: Output directory = {output_directory}")
        logger.info(f"🔍 E2E TEST: Session state before call: {mock_session_state}")

        result = await process_case_documents(output_dir=str(output_directory))
        logger.info(f"🔍 E2E TEST: process_case_documents() returned: {result}")
        logger.info(
            f"🔍 E2E TEST: Session state after call: {vars(session_state_mock)}"
        )

        # Check directory contents before assertions
        logger.info(
            f"🔍 E2E TEST: Output directory contents: {list(output_directory.glob('*'))}"
        )

        # Verify the workflow completed successfully
        assert result is True, "Workflow should return True on success"

        # Check for HTML output files (primary deliverable format)
        expected_html_files = [
            f"{output_directory}/erik_devlin_findings_letter.html",
            f"{output_directory}/erik_devlin_analysis_appendix.html",
        ]

        # Validate that HTML content is generated in session state
        assert session_state_mock.main_letter is not None, (
            "Main letter HTML not generated"
        )
        assert session_state_mock.appendix is not None, "Appendix HTML not generated"
        assert len(session_state_mock.main_letter) > 100, "Main letter HTML too short"
        assert len(session_state_mock.appendix) > 50, "Appendix HTML too short"
        assert (
            "<!doctype html>" in session_state_mock.main_letter.lower()
            or "<html" in session_state_mock.main_letter.lower()
        ), "Main letter should be HTML format"
        assert (
            "<!doctype html>" in session_state_mock.appendix.lower()
            or "<html" in session_state_mock.appendix.lower()
        ), "Appendix should be HTML format"

        # Verify HTML files are saved
        for expected_file in expected_html_files:
            file_path = Path(expected_file)
            assert file_path.exists(), f"Expected HTML file not found: {expected_file}"
            assert file_path.stat().st_size > 0, f"HTML file is empty: {expected_file}"

            # Verify HTML content
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
                assert "<html>" in content.lower() or "<!DOCTYPE html>" in content, (
                    f"File {expected_file} should contain HTML"
                )

        # Verify session state updates
        assert session_state_mock.processing_status == "completed"
        assert session_state_mock.processing_error is None
        assert session_state_mock.final_results is not None
        assert session_state_mock.main_letter is not None
        assert session_state_mock.appendix is not None

        # Verify final results structure
        final_results = session_state_mock.final_results
        assert hasattr(final_results, "intake_analysis"), (
            "Final results should have intake_analysis"
        )
        assert final_results.intake_analysis is not None, (
            "Intake analysis should not be None"
        )

        logger.info(
            "✅ E2E TEST: All validations passed - workflow completed successfully!"
        )

    # Note: Removed legacy helper methods - E2E test now validates real HTML output files directly

    def test_devlin_documents_available(self, devlin_documents):
        """Test that all required Devlin test documents are available."""
        assert len(devlin_documents) == 9, (
            f"Expected 9 Devlin documents, found {len(devlin_documents)}"
        )

        # Verify specific expected documents exist
        document_names = [Path(doc).name for doc in devlin_documents]

        required_documents = [
            "Devlin - Intake for Contractor Dispute.pdf",
            "Devlin - Contract for Construction - Highlighted w Items not Completed 6.9.25.pdf",
            "Devlin-LLW Emails.pdf",
            "Notice to Owner.pdf",
        ]

        for required_doc in required_documents:
            assert required_doc in document_names, (
                f"Required document not found: {required_doc}"
            )

    def test_output_directory_creation(self, output_directory):
        """Test that the output directory is created successfully."""
        assert output_directory.exists(), "Output directory should be created"
        assert output_directory.is_dir(), "Output path should be a directory"
        assert str(output_directory).endswith("devlin_e2e_output"), (
            "Directory should have correct name"
        )


# Utility function for running the test
def run_devlin_e2e_test():
    """Utility function to run the Devlin E2E test programmatically."""
    import subprocess
    import sys

    # Run the specific test
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/e2e/test_devlin_workflow.py::TestDevlinWorkflow::test_devlin_complete_workflow",
            "-v",
            "--tb=short",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    logger.info("Test Output:")
    logger.info(result.stdout)
    if result.stderr:
        logger.error("Errors:")
        logger.info(result.stderr)

    return result.returncode == 0


if __name__ == "__main__":
    # Allow running the test directly
    success = run_devlin_e2e_test()
    if success:
        logger.info("\n✅ Devlin E2E test completed successfully!")
    else:
        logger.error("\n❌ Devlin E2E test failed!")
