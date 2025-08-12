import unittest
from unittest.mock import MagicMock, patch

from app.main import main


class TestNewArchitecture(unittest.TestCase):
    @patch("app.main.st.session_state", new_callable=MagicMock)
    @patch("app.main.st.set_page_config")
    @patch("app.main.initialize_session_state")
    @patch("app.main.case_information_form")
    def test_streamlit_app_initialization(
        self, mock_case_form, mock_initialize_session, mock_set_page_config, mock_session_state
    ):
        """Test if the Streamlit app is initialized and configured correctly."""
        # Arrange
        mock_set_page_config.return_value = None
        mock_initialize_session.return_value = None
        mock_case_form.return_value = None
        mock_session_state.performance_mode = "optimized"
        mock_session_state.enable_caching = True
        mock_session_state.enable_parallel_processing = True
        mock_session_state.max_concurrent_requests = 10
        mock_session_state.main_letter = "This is a test letter with no citations."
        mock_session_state.get.return_value = False  # For authentication_status and other get() calls

        # Configure cost_summary mock to return proper float values
        mock_cost_summary = MagicMock()
        mock_cost_summary.cost_variance_percentage = 12.34
        mock_session_state.cost_summary = mock_cost_summary

        # Act
        main()

        # Assert
        mock_set_page_config.assert_called_once_with(
            page_title="Legal Document Analysis Portal",
            layout="wide",
            menu_items={
                "About": "Legal Document Analysis Portal v2.1 - Enterprise Edition with Authentication"
            },
        )
        mock_initialize_session.assert_called_once()
        mock_case_form.assert_called_once()

    @patch("app.main.st.session_state", new_callable=MagicMock)
    @patch("app.main.os.getenv", return_value="INFO")
    @patch("app.main.st.set_page_config")
    @patch("app.main.initialize_session_state")
    def test_streamlit_app_environment_config(
        self, mock_initialize_session, mock_set_page_config, mock_getenv, mock_session_state
    ):
        """Test if the Streamlit app handles environment configuration correctly."""
        # Arrange
        mock_set_page_config.return_value = None
        mock_initialize_session.return_value = None
        mock_session_state.performance_mode = "optimized"
        mock_session_state.enable_caching = True
        mock_session_state.enable_parallel_processing = True
        mock_session_state.max_concurrent_requests = 10
        mock_session_state.main_letter = "This is a test letter with no citations."
        mock_session_state.get.return_value = False  # For authentication_status and other get() calls

        # Configure cost_summary mock to return proper float values
        mock_cost_summary = MagicMock()
        mock_cost_summary.cost_variance_percentage = 12.34
        mock_session_state.cost_summary = mock_cost_summary

        # Act
        main()

        # Assert
        mock_set_page_config.assert_called_once()
        mock_initialize_session.assert_called_once()
        # Verify that environment variables are accessed
        mock_getenv.assert_called()


if __name__ == "__main__":
    unittest.main()
