import unittest
from unittest.mock import patch, MagicMock
import sys
import os

from app.main import main

class TestNewArchitecture(unittest.TestCase):

    @patch('app.main.StreamlitRunner')
    def test_streamlit_runner_initialization(self, mock_streamlit_runner):
        """
        Test if the StreamlitRunner is initialized and run correctly.
        """
        # Arrange
        mock_instance = MagicMock()
        mock_streamlit_runner.return_value = mock_instance

        # Act
        main()

        # Assert
        mock_streamlit_runner.assert_called_once_with(
            entrypoint="app.main:main",
            config={"server.port": 8501, "server.headless": True}
        )
        mock_instance.run.assert_called_once()

    @patch('app.main.os.environ.get', return_value='production')
    @patch('app.main.StreamlitRunner')
    def test_streamlit_runner_production_mode(self, mock_streamlit_runner, mock_env_get):
        """
        Test if the StreamlitRunner is initialized correctly in production mode.
        """
        # Arrange
        mock_instance = MagicMock()
        mock_streamlit_runner.return_value = mock_instance

        # Act
        main()

        # Assert
        mock_streamlit_runner.assert_called_once_with(
            entrypoint="app.main:main",
            config={"server.port": 8501, "server.headless": True}
        )
        mock_instance.run.assert_called_once()

if __name__ == '__main__':
    unittest.main()