import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import main


class TestMain(unittest.TestCase):
    @patch("app.main.st.session_state", new_callable=MagicMock)
    @patch("app.main.st.set_page_config")
    @patch("app.main.initialize_session_state")
    def test_main_runs_streamlit(self, mock_initialize_session, mock_set_page_config, mock_session_state):
        """Test that the main function initializes and configures Streamlit."""
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


if __name__ == "__main__":
    unittest.main()
