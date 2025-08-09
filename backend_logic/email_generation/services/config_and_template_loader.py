from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape


class ConfigAndTemplateLoader:
    def __init__(self):
        pass

    def load_configuration(self, config_path: str | None = None) -> dict[str, Any]:
        """Load configuration from YAML file."""
        # JSON logging for Hypothesis 2 (Configuration Loading Failure) - Entry
        config_log_entry = {
            "module": "ConfigAndTemplateLoader",
            "method": "load_configuration",
            "hypothesis_id": "config_loading_failure",
            "stage": "entry",
            "config_path_provided": config_path,
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_entry)}")
        
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
            
            config_path = os.path.join(project_root, "backend", "config", "templates", "universal_legal_config.yaml")
        
        # JSON logging for file existence check
        file_exists = os.path.exists(config_path)
        config_log_file_check = {
            "module": "ConfigAndTemplateLoader",
            "method": "load_configuration",
            "hypothesis_id": "config_loading_failure",
            "stage": "file_check",
            "config_path": config_path,
            "file_exists": file_exists,
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_file_check)}")
        
        if not file_exists:
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)
        
        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            # JSON logging for successful config parsing
            config_keys = list(config.keys()) if config else []
            config_log_success = {
                "module": "ConfigAndTemplateLoader",
                "method": "load_configuration",
                "hypothesis_id": "config_loading_failure",
                "stage": "parsing_success",
                "config_keys": config_keys,
                "config_is_none": config is None,
                "config_type": type(config).__name__,
                "timestamp": datetime.now().isoformat()
            }
            print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_success)}")
            
            print(f"EMAIL GENERATOR V2: Configuration loaded from: {config_path}")
            return config
        except yaml.YAMLError as e:
            # JSON logging for YAML parsing failure
            config_log_yaml_error = {
                "module": "ConfigAndTemplateLoader",
                "method": "load_configuration",
                "hypothesis_id": "config_loading_failure",
                "stage": "yaml_error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_yaml_error)}")
            
            msg = f"Failed to parse YAML configuration: {e}"
            raise ValueError(msg) from e
        except Exception as e:
            # JSON logging for general loading failure
            config_log_general_error = {
                "module": "ConfigAndTemplateLoader",
                "method": "load_configuration",
                "hypothesis_id": "config_loading_failure",
                "stage": "general_error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(config_log_general_error)}")
            
            msg = f"Failed to load configuration: {e}"
            raise RuntimeError(msg) from e

    def find_template_directory(self, config: dict[str, Any]) -> str:
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
                
                template_dir = os.path.dirname(os.path.join(project_root, template_path))
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
            msg = f"Template directory not found: {template_dir}"
            raise FileNotFoundError(msg)

        # Verify required templates exist
        required_templates = ["findings_email.jinja2", "document_appendix.jinja2"]
        available_files = os.listdir(template_dir)
        missing_templates = [t for t in required_templates if t not in available_files]
        if missing_templates:
            msg = f"Required templates missing: {missing_templates}"
            raise FileNotFoundError(msg)

        print(f"EMAIL GENERATOR V2: Template directory: {template_dir}")
        return template_dir

    def get_jinja_env(self, config: dict[str, Any]) -> Environment:
        """Initialize and return Jinja2 environment."""
        template_dir = self.find_template_directory(config)
        jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )
        return jinja_env
