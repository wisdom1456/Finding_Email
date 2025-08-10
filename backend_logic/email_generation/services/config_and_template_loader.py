from __future__ import annotations

import os
from typing import Any, Dict, Optional

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend_logic.utils.logging_config import get_module_logger


logger = get_module_logger(__name__)


class ConfigAndTemplateLoader:
    def __init__(self):
        pass

    def load_configuration(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        logger.debug(
            "Configuration loading initiated",
            extra={
                "method": "load_configuration",
                "hypothesis_id": "config_loading_failure",
                "stage": "entry",
                "config_path_provided": config_path,
            },
        )

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

        # Check file existence
        file_exists = os.path.exists(config_path)
        logger.debug(
            "Configuration file existence check",
            extra={
                "method": "load_configuration",
                "hypothesis_id": "config_loading_failure",
                "stage": "file_check",
                "config_path": config_path,
                "file_exists": file_exists,
            },
        )

        if not file_exists:
            logger.error(
                "Configuration file not found", extra={"config_path": config_path}
            )
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)

        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # Log successful config parsing
            config_keys = list(config.keys()) if config else []
            logger.debug(
                "Configuration parsing successful",
                extra={
                    "method": "load_configuration",
                    "hypothesis_id": "config_loading_failure",
                    "stage": "parsing_success",
                    "config_keys": config_keys,
                    "config_is_none": config is None,
                    "config_type": type(config).__name__,
                },
            )

            logger.info(
                "Configuration loaded successfully",
                extra={
                    "config_path": config_path,
                    "config_keys_count": len(config_keys),
                },
            )
            return config
        except yaml.YAMLError as e:
            logger.error(
                "YAML parsing failed",
                extra={
                    "method": "load_configuration",
                    "hypothesis_id": "config_loading_failure",
                    "stage": "yaml_error",
                    "error": str(e),
                    "config_path": config_path,
                },
            )
            msg = f"Failed to parse YAML configuration: {e}"
            raise ValueError(msg) from e
        except Exception as e:
            logger.error(
                "Configuration loading failed",
                extra={
                    "method": "load_configuration",
                    "hypothesis_id": "config_loading_failure",
                    "stage": "general_error",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "config_path": config_path,
                },
            )
            msg = f"Failed to load configuration: {e}"
            raise RuntimeError(msg) from e

    def find_template_directory(self, config: Dict[str, Any]) -> str:
        """Find template directory using configuration or fallback path resolution."""
        # Try to use template_path from configuration
        if "template_path" in config:
            template_path = config["template_path"]
            # If template_path is relative, make it relative to project root
            if not os.path.isabs(template_path):
                current_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = current_dir

                while project_root != "/" and not (
                    os.path.exists(os.path.join(project_root, "app.py"))
                    and os.path.exists(os.path.join(project_root, "backend"))
                ):
                    project_root = os.path.dirname(project_root)

                if project_root == "/":
                    project_root = os.getcwd()

                template_dir = os.path.dirname(
                    os.path.join(project_root, template_path)
                )
            else:
                template_dir = os.path.dirname(template_path)
        else:
            # Fallback to default template directory
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

            template_dir = os.path.join(project_root, "backend", "assets", "templates")

        if not os.path.exists(template_dir):
            logger.error(
                "Template directory not found", extra={"template_dir": template_dir}
            )
            msg = f"Template directory not found: {template_dir}"
            raise FileNotFoundError(msg)

        # Verify required templates exist
        required_templates = ["findings_email.jinja2", "document_appendix.jinja2"]
        available_files = os.listdir(template_dir)
        missing_templates = [t for t in required_templates if t not in available_files]
        if missing_templates:
            logger.error(
                "Required templates missing",
                extra={
                    "template_dir": template_dir,
                    "missing_templates": missing_templates,
                    "available_files": available_files,
                },
            )
            msg = f"Required templates missing: {missing_templates}"
            raise FileNotFoundError(msg)

        logger.info(
            "Template directory configured successfully",
            extra={
                "template_dir": template_dir,
                "available_templates": available_files,
                "required_templates": required_templates,
            },
        )
        return template_dir

    def get_jinja_env(self, config: Dict[str, Any]) -> Environment:
        """Initialize and return Jinja2 environment."""
        template_dir = self.find_template_directory(config)
        jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )
        return jinja_env
