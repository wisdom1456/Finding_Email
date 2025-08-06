"""
Unit tests for the configuration system (backend_logic/config.py).

These tests verify that the configuration module properly loads and validates
environment variables, handles error cases, and provides the expected API.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend_logic.config import (
    Settings,
    get_google_cloud_config,
    get_openai_api_key,
    get_settings,
    is_production,
    settings,
)
from tests.utils import (
    MockConfigFactory,
    TempConfigFile,
    TempEnvVar,
    TestUtils,
)


class TestSettings:
    """Test the Settings class configuration model."""

    def test_minimal_config_valid(self):
        """Test that minimal configuration with only OpenAI key works."""
        config_data = MockConfigFactory.create_minimal_config()
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.openai_api_key == "sk-test123456789"
            assert test_settings.gcp_project_id is None
            assert test_settings.port == 8501  # Default value
            assert not test_settings.has_google_cloud_config
            assert not test_settings.video_processing_enabled

    def test_full_config_valid(self):
        """Test that full configuration with all settings works."""
        config_data = MockConfigFactory.create_full_config()
        
        # Create a temporary credentials file
        temp_creds = TestUtils.create_temp_file(b'{"type": "service_account"}', ".json")
        config_data["GOOGLE_APPLICATION_CREDENTIALS"] = temp_creds
        
        try:
            with TempEnvVar(**config_data):
                test_settings = Settings()
                assert test_settings.openai_api_key == "sk-test123456789"
                assert test_settings.gcp_project_id == "test-project"
                assert test_settings.gcp_bucket_name == "test-bucket"
                assert test_settings.google_application_credentials == temp_creds
                assert test_settings.port == 8501
                assert test_settings.railway_static_url == "https://test.railway.app"
                assert test_settings.has_google_cloud_config
                assert test_settings.video_processing_enabled
        finally:
            TestUtils.cleanup_temp_file(temp_creds)

    def test_openai_key_validation_valid_sk_format(self):
        """Test that OpenAI API key validation accepts valid sk- format."""
        with TempEnvVar(OPENAI_API_KEY="sk-123456789abcdef"):
            test_settings = Settings()
            assert test_settings.openai_api_key == "sk-123456789abcdef"

    def test_openai_key_validation_valid_sk_proj_format(self):
        """Test that OpenAI API key validation accepts valid sk-proj- format."""
        with TempEnvVar(OPENAI_API_KEY="sk-proj-123456789abcdef"):
            test_settings = Settings()
            assert test_settings.openai_api_key == "sk-proj-123456789abcdef"

    def test_openai_key_validation_invalid_format(self):
        """Test that OpenAI API key validation rejects invalid format."""
        with TempEnvVar(OPENAI_API_KEY="invalid-key-format"):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "OpenAI API key must start with 'sk-' or 'sk-proj-'" in str(exc_info.value)

    def test_openai_key_missing(self):
        """Test that missing OpenAI API key raises validation error."""
        # Clear any existing OPENAI_API_KEY
        with TempEnvVar():
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]
            with pytest.raises(ValidationError):
                Settings()

    def test_google_credentials_file_validation_valid(self):
        """Test that Google credentials file validation works with valid file."""
        temp_creds = TestUtils.create_temp_file(b'{"type": "service_account"}', ".json")
        
        try:
            config_data = {
                "OPENAI_API_KEY": "sk-test123456789",
                "GOOGLE_APPLICATION_CREDENTIALS": temp_creds,
            }
            with TempEnvVar(**config_data):
                test_settings = Settings()
                assert test_settings.google_application_credentials == temp_creds
        finally:
            TestUtils.cleanup_temp_file(temp_creds)

    def test_google_credentials_file_validation_invalid(self):
        """Test that Google credentials file validation rejects nonexistent file."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "GOOGLE_APPLICATION_CREDENTIALS": "/nonexistent/path.json",
        }
        
        with TempEnvVar(**config_data):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "Google credentials file not found" in str(exc_info.value)

    def test_google_credentials_file_validation_none(self):
        """Test that Google credentials file validation allows None."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
        }
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.google_application_credentials is None

    def test_has_google_cloud_config_property_complete(self):
        """Test has_google_cloud_config property with complete configuration."""
        temp_creds = TestUtils.create_temp_file(b'{"type": "service_account"}', ".json")
        
        try:
            config_data = {
                "OPENAI_API_KEY": "sk-test123456789",
                "GCP_PROJECT_ID": "test-project",
                "GCP_BUCKET_NAME": "test-bucket",
                "GOOGLE_APPLICATION_CREDENTIALS": temp_creds,
            }
            with TempEnvVar(**config_data):
                test_settings = Settings()
                assert test_settings.has_google_cloud_config is True
        finally:
            TestUtils.cleanup_temp_file(temp_creds)

    def test_has_google_cloud_config_property_incomplete(self):
        """Test has_google_cloud_config property with incomplete configuration."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "GCP_PROJECT_ID": "test-project",
            # Missing GCP_BUCKET_NAME and GOOGLE_APPLICATION_CREDENTIALS
        }
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.has_google_cloud_config is False

    def test_video_processing_enabled_property(self):
        """Test video_processing_enabled property matches has_google_cloud_config."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "GCP_PROJECT_ID": "test-project",
        }
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.video_processing_enabled == test_settings.has_google_cloud_config

    def test_port_configuration(self):
        """Test port configuration with custom value."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "PORT": "3000",
        }
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.port == 3000

    def test_config_from_env_file(self):
        """Test configuration loading from .env file."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "PORT": "3000",
        }
        
        with TempConfigFile(config_data) as env_file:
            # Temporarily change directory to where the .env file is
            original_cwd = os.getcwd()
            env_dir = Path(env_file).parent
            
            try:
                os.chdir(env_dir)
                test_settings = Settings()
                assert test_settings.openai_api_key == "sk-test123456789"
                assert test_settings.port == 3000
            finally:
                os.chdir(original_cwd)


class TestConvenienceFunctions:
    """Test convenience functions in the config module."""

    def test_get_settings_returns_settings_instance(self):
        """Test that get_settings returns a Settings instance."""
        result = get_settings()
        assert isinstance(result, Settings)

    def test_is_production_with_railway_url(self):
        """Test is_production returns True when RAILWAY_STATIC_URL is set."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "RAILWAY_STATIC_URL": "https://test.railway.app",
        }
        
        with TempEnvVar(**config_data):
            # Need to create a new settings instance to pick up the env vars
            with patch('backend_logic.config.settings', Settings()):
                assert is_production() is True

    def test_is_production_without_railway_url(self):
        """Test is_production returns False when RAILWAY_STATIC_URL is not set."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
        }
        
        with TempEnvVar(**config_data):
            with patch('backend_logic.config.settings', Settings()):
                assert is_production() is False

    def test_get_openai_api_key_success(self):
        """Test get_openai_api_key returns key when available."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
        }
        
        with TempEnvVar(**config_data):
            with patch('backend_logic.config.settings', Settings()):
                result = get_openai_api_key()
                assert result == "sk-test123456789"

    def test_get_openai_api_key_missing(self):
        """Test get_openai_api_key raises error when key is missing."""
        # Create a mock settings object with empty API key
        mock_settings = Settings.__new__(Settings)
        mock_settings.openai_api_key = ""
        
        with patch('backend_logic.config.settings', mock_settings):
            with pytest.raises(ValueError) as exc_info:
                get_openai_api_key()
            assert "OPENAI_API_KEY is required but not set" in str(exc_info.value)

    def test_get_google_cloud_config_complete(self):
        """Test get_google_cloud_config with complete configuration."""
        temp_creds = TestUtils.create_temp_file(b'{"type": "service_account"}', ".json")
        
        try:
            config_data = {
                "OPENAI_API_KEY": "sk-test123456789",
                "GCP_PROJECT_ID": "test-project",
                "GCP_BUCKET_NAME": "test-bucket",
                "GOOGLE_APPLICATION_CREDENTIALS": temp_creds,
            }
            
            with TempEnvVar(**config_data):
                with patch('backend_logic.config.settings', Settings()):
                    project_id, bucket_name, credentials_path = get_google_cloud_config()
                    assert project_id == "test-project"
                    assert bucket_name == "test-bucket"
                    assert credentials_path == temp_creds
        finally:
            TestUtils.cleanup_temp_file(temp_creds)

    def test_get_google_cloud_config_incomplete(self):
        """Test get_google_cloud_config with incomplete configuration."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "GCP_PROJECT_ID": "test-project",
            # Missing GCP_BUCKET_NAME and GOOGLE_APPLICATION_CREDENTIALS
        }
        
        with TempEnvVar(**config_data):
            with patch('backend_logic.config.settings', Settings()):
                with pytest.raises(ValueError) as exc_info:
                    get_google_cloud_config()
                assert "Incomplete Google Cloud configuration" in str(exc_info.value)
                assert "GCP_BUCKET_NAME" in str(exc_info.value)
                assert "GOOGLE_APPLICATION_CREDENTIALS" in str(exc_info.value)


class TestConfigurationIntegration:
    """Integration tests for configuration system."""

    def test_global_settings_instance_access(self):
        """Test that the global settings instance is accessible."""
        assert settings is not None
        assert isinstance(settings, Settings)

    def test_configuration_error_messages_helpful(self):
        """Test that configuration errors provide helpful messages."""
        with TempEnvVar(OPENAI_API_KEY="invalid-key"):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            error_message = str(exc_info.value)
            assert "OpenAI API key must start with" in error_message

    def test_configuration_case_insensitive(self):
        """Test that configuration is case insensitive."""
        config_data = {
            "openai_api_key": "sk-test123456789",  # lowercase
            "gcp_project_id": "test-project",      # lowercase
        }
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.openai_api_key == "sk-test123456789"
            assert test_settings.gcp_project_id == "test-project"

    def test_extra_environment_variables_ignored(self):
        """Test that extra environment variables are ignored."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "SOME_RANDOM_VAR": "should_be_ignored",
            "ANOTHER_VAR": "also_ignored",
        }
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.openai_api_key == "sk-test123456789"
            # Should not raise an error even with extra variables


class TestConfigurationEdgeCases:
    """Test edge cases and error conditions in configuration."""

    def test_empty_string_values(self):
        """Test behavior with empty string values."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "GCP_PROJECT_ID": "",  # Empty string
            "GCP_BUCKET_NAME": "",  # Empty string
        }
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.gcp_project_id == ""
            assert test_settings.gcp_bucket_name == ""
            assert not test_settings.has_google_cloud_config

    def test_whitespace_values(self):
        """Test behavior with whitespace values."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "GCP_PROJECT_ID": "   ",  # Whitespace only
        }
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.gcp_project_id == "   "

    def test_numeric_port_conversion(self):
        """Test that port value is properly converted to integer."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "PORT": "9000",
        }
        
        with TempEnvVar(**config_data):
            test_settings = Settings()
            assert test_settings.port == 9000
            assert isinstance(test_settings.port, int)

    def test_invalid_port_value(self):
        """Test that invalid port value raises validation error."""
        config_data = {
            "OPENAI_API_KEY": "sk-test123456789",
            "PORT": "not_a_number",
        }
        
        with TempEnvVar(**config_data):
            with pytest.raises(ValidationError):
                Settings()