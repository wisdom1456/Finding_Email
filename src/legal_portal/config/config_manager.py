"""Configuration management for AI analysis components.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import yaml
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)


class ConfigManager:
    """Manages YAML configuration loading for AI analysis components."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize ConfigManager with optional config path."""
        self.config_path = config_path
        self.config = self._load_configuration(config_path)
        logger.info(f"CONFIG MANAGER: ✅ Initialized with configuration: {config_path or 'default'}")

    def _load_configuration(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if config_path is None:
            # Default to universal_legal_config.yaml for all case types
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = current_dir

            # Navigate up until we find the project root
            while project_root != "/" and not (
                os.path.exists(os.path.join(project_root, "app.py"))
                and os.path.exists(os.path.join(project_root, "backend"))
            ):
                project_root = os.path.dirname(project_root)

            if project_root == "/":
                project_root = os.getcwd()

            config_path = os.path.join(
                project_root,
                "backend",
                "config",
                "templates",
                "universal_legal_config.yaml",
            )

        if not os.path.exists(config_path):
            logger.info(
                f"CONFIG MANAGER: ⚠️  Configuration file not found: {config_path}, using default prompts"
            )
            return {}

        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            logger.info(f"CONFIG MANAGER: Configuration loaded from: {config_path}")
            return config
        except yaml.YAMLError as e:
            logger.error(f"CONFIG MANAGER: ⚠️  Failed to parse YAML configuration: {e}, using default prompts")
            return {}
        except Exception as e:
            logger.error(f"CONFIG MANAGER: ⚠️  Failed to load configuration: {e}, using default prompts")
            return {}

    def get_prompt(self, section: str, fallback: str = "") -> str:
        """Get a prompt from the configuration with fallback."""
        return self.config.get("sections", {}).get(section, fallback)

    def get_persona(self, persona_name: str, fallback: str = "") -> str:
        """Get a persona from the configuration with fallback."""
        return self.config.get("personas", {}).get(persona_name, fallback)

    def get_formatting_rule(self, rule_name: str, fallback: str = "") -> str:
        """Get a formatting rule from the configuration with fallback."""
        return self.config.get("formatting", {}).get(rule_name, fallback)

    def get_template_path(self) -> Optional[str]:
        """Get the template path from configuration."""
        return self.config.get("template_path")

    def has_config(self) -> bool:
        """Check if configuration was successfully loaded."""
        return bool(self.config)
