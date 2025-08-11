import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import main

class TestMain(unittest.TestCase):

    @patch('app.main.StreamlitRunner')
    def test_main_runs_streamlit(self, mock_streamlit_runner):
        """
        Test that the main function initializes and runs the StreamlitRunner.
        """
        # Arrange
        mock_instance = MagicMock()
        mock_streamlit_runner.return_value = mock_instance

        # Act
        main()

        # Assert
        mock_streamlit_runner.assert_called_once()
        mock_instance.run.assert_called_once()

if __name__ == '__main__':
    unittest.main()