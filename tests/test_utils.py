"""
Tests for the unified test utilities module.

This file tests our test utilities and serves as a validation
that the testing infrastructure is working correctly.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tests.test_utilities import (
    MockConfigFactory,
    TempConfigFile,
    TempEnvVar,
    TestUtils,
    assert_valid_email_structure,
    print_test_banner,
)


class TestTestUtils:
    """Test the TestUtils class functionality."""

    def test_create_temp_file(self):
        """Test temporary file creation."""
        content = b"test content"
        temp_path = TestUtils.create_temp_file(content, ".txt")
        
        try:
            assert Path(temp_path).exists()
            with open(temp_path, "rb") as f:
                assert f.read() == content
        finally:
            TestUtils.cleanup_temp_file(temp_path)
            assert not Path(temp_path).exists()

    def test_create_temp_env_file(self):
        """Test temporary .env file creation."""
        env_vars = {"TEST_VAR": "test_value", "ANOTHER_VAR": "another_value"}
        temp_path = TestUtils.create_temp_env_file(env_vars)
        
        try:
            assert Path(temp_path).exists()
            with open(temp_path) as f:
                content = f.read()
                assert "TEST_VAR=test_value" in content
                assert "ANOTHER_VAR=another_value" in content
        finally:
            TestUtils.cleanup_temp_file(temp_path)

    def test_create_mock_processed_document(self):
        """Test mock processed document creation."""
        doc = TestUtils.create_mock_processed_document()
        assert doc.file_name == "test.pdf"
        assert doc.content == "Test content"
        assert doc.file_type.value == "pdf"

    def test_create_mock_intake_analysis(self):
        """Test mock intake analysis creation."""
        analysis = TestUtils.create_mock_intake_analysis()
        assert analysis.client_name == "Test Client"
        assert analysis.case_type == "Test Case"
        assert analysis.case_summary == "Test case summary"

    def test_create_sample_pdf_content(self):
        """Test sample PDF content creation."""
        pdf_content = TestUtils.create_sample_pdf_content()
        assert pdf_content.startswith(b"%PDF-1.4")
        assert b"%%EOF" in pdf_content

    def test_create_mock_openai_response(self):
        """Test mock OpenAI response creation."""
        response = TestUtils.create_mock_openai_response()
        assert '"client_name": "Test Client"' in response
        assert '"case_type": "Test Case"' in response


class TestMockConfigFactory:
    """Test the MockConfigFactory class."""

    def test_create_minimal_config(self):
        """Test minimal configuration creation."""
        config = MockConfigFactory.create_minimal_config()
        assert "OPENAI_API_KEY" in config
        assert config["OPENAI_API_KEY"].startswith("sk-")

    def test_create_full_config(self):
        """Test full configuration creation."""
        config = MockConfigFactory.create_full_config()
        assert "OPENAI_API_KEY" in config
        assert "GCP_PROJECT_ID" in config
        assert "GCP_BUCKET_NAME" in config
        assert "GOOGLE_APPLICATION_CREDENTIALS" in config

    def test_create_invalid_config(self):
        """Test invalid configuration creation."""
        config = MockConfigFactory.create_invalid_config()
        assert config["OPENAI_API_KEY"] == "invalid-key-format"
        assert "/nonexistent/path.json" in config["GOOGLE_APPLICATION_CREDENTIALS"]


class TestContextManagers:
    """Test context manager utilities."""

    def test_temp_env_var(self):
        """Test temporary environment variable context manager."""
        import os
        
        original_value = os.environ.get("TEST_ENV_VAR")
        
        with TempEnvVar(TEST_ENV_VAR="temporary_value"):
            assert os.environ["TEST_ENV_VAR"] == "temporary_value"
        
        # Should restore original value (or remove if didn't exist)
        if original_value is None:
            assert "TEST_ENV_VAR" not in os.environ
        else:
            assert os.environ["TEST_ENV_VAR"] == original_value

    def test_temp_config_file(self):
        """Test temporary config file context manager."""
        config_data = {"TEST_KEY": "test_value"}
        
        with TempConfigFile(config_data) as config_path:
            assert Path(config_path).exists()
            with open(config_path) as f:
                content = f.read()
                assert "TEST_KEY=test_value" in content
        
        # File should be cleaned up
        assert not Path(config_path).exists()


class TestUtilityFunctions:
    """Test utility functions."""

    def test_print_test_banner(self, capsys):
        """Test test banner printing."""
        title = "Test Banner"
        print_test_banner(title)
        captured = capsys.readouterr()
        assert "Test Banner" in captured.out
        assert "🧪" in captured.out

    def test_assert_valid_email_structure_valid(self):
        """Test email structure validation with valid email."""
        valid_email = "Dear Client,\n\nThis is a test email.\n\nSincerely,\nTest Attorney"
        # Should not raise an exception
        assert_valid_email_structure(valid_email)

    def test_assert_valid_email_structure_invalid(self):
        """Test email structure validation with invalid email."""
        invalid_email = "This is not a proper email structure"
        with pytest.raises(AssertionError):
            assert_valid_email_structure(invalid_email)


class TestIntegration:
    """Integration tests for test utilities."""

    def test_full_workflow_simulation(self):
        """Test a complete workflow using multiple utilities."""
        # Create temporary config
        config_data = MockConfigFactory.create_minimal_config()
        
        with TempConfigFile(config_data) as config_path:
            # Verify config file creation
            assert Path(config_path).exists()
            
            # Create mock documents
            doc = TestUtils.create_mock_processed_document()
            analysis = TestUtils.create_mock_intake_analysis()
            
            # Verify mock data
            assert doc.file_name == "test.pdf"
            assert analysis.client_name == "Test Client"
            
            # Test environment variables
            with TempEnvVar(TEST_INTEGRATION="success"):
                import os
                assert os.environ["TEST_INTEGRATION"] == "success"