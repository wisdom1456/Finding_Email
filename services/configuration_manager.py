"""
Configuration Manager Service

Handles loading and managing YAML configuration files and template directory discovery.
This service is responsible for:
- Loading YAML configuration files
- Finding and validating template directories
- Providing configuration access to other services

This replaces configuration-related methods from the original EmailGeneratorV2 class.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import yaml


logger = logging.getLogger(__name__)


class ConfigurationManager:
    """
    Manages configuration loading and template directory discovery.

    This service handles all configuration-related operations that were previously
    embedded in the monolithic EmailGeneratorV2 class.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration manager.

        Args:
            config_path: Optional path to configuration file. If None, uses default.
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.template_directory: Optional[str] = None

        # Load configuration on initialization
        self._load_configuration()
        self._find_template_directory()

    def _load_configuration(self) -> None:
        """
        Load configuration from YAML file.

        This method loads the email generation configuration from the specified
        YAML file, with fallback to default location if not specified.
        """
        if self.config_path is None:
            # Default configuration path
            self.config_path = "backend/config/templates/universal_legal_config.yaml"

        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, encoding="utf-8") as file:
                    self.config = yaml.safe_load(file) or {}
                logger.info(
                    f"Configuration loaded successfully from {self.config_path}"
                )
            else:
                logger.warning(f"Configuration file not found: {self.config_path}")
                self.config = {}
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            self.config = {}

    def _find_template_directory(self) -> None:
        """
        Find and validate the template directory.

        Searches for the template directory in common locations and validates
        that it exists and contains expected template files.
        """
        possible_dirs = ["backend/assets/templates", "assets/templates", "templates"]

        for directory in possible_dirs:
            if os.path.exists(directory) and os.path.isdir(directory):
                self.template_directory = directory
                logger.info(f"Template directory found: {directory}")
                return

        logger.warning("Template directory not found in any expected location")
        self.template_directory = None

    def get_config(self, key: str = None, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key to retrieve. If None, returns entire config.
            default: Default value if key not found.

        Returns:
            Configuration value or default if not found.
        """
        if key is None:
            return self.config

        # Support dot notation for nested keys
        keys = key.split(".")
        value = self.config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def get_template_directory(self) -> Optional[str]:
        """
        Get the template directory path.

        Returns:
            Path to template directory or None if not found.
        """
        return self.template_directory

    def get_template_path(self, template_name: str) -> Optional[str]:
        """
        Get full path to a specific template file.

        Args:
            template_name: Name of the template file.

        Returns:
            Full path to template file or None if not found.
        """
        if self.template_directory is None:
            return None

        template_path = os.path.join(self.template_directory, template_name)
        if os.path.exists(template_path):
            return template_path

        return None

    def is_configured(self) -> bool:
        """
        Check if configuration is properly loaded.

        Returns:
            True if configuration is loaded and template directory is found.
        """
        return bool(self.config and self.template_directory)

    def reload_configuration(self, new_config_path: Optional[str] = None) -> None:
        """
        Reload configuration from file.

        Args:
            new_config_path: Optional new configuration file path.
        """
        if new_config_path:
            self.config_path = new_config_path

        self._load_configuration()
        self._find_template_directory()

        logger.info("Configuration reloaded successfully")
