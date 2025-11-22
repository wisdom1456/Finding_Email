from __future__ import annotations

"""Lightweight configuration manager used by compatibility tests and prompt helpers.

Historically the project exposed a ``ConfigManager`` class that loaded YAML/JSON
configuration data plus prompt templates. Several legacy regression tests
(`test_html_formatting.py`, `test_preamble_removal.py`, `validation_test.py`)
still import this symbol directly, and some helper utilities expect a simple
``get_prompt`` API.  During the refactor to the consolidated
`prompts_and_settings.json` file the wrapper went missing, which causes the test
suite to fail during collection.  This module restores that class while
adapting it to the newer configuration layout.

The implementation intentionally keeps the surface area small but flexible:

* Loads ``prompts_and_settings.json`` (or a caller-provided path) once and
  exposes the parsed dictionary via the ``config`` attribute.
* Provides ``get_prompt`` that looks for prompts in either a ``prompts`` or
  ``sections`` section, falling back to a caller-provided default string.
* Supplies a generic ``get`` helper that supports simple dot-notation lookups
  for other config values.

This is sufficient for the remaining legacy callers and keeps the door open to
swap in a richer unified manager later without breaking imports.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """Backward-compatible configuration loader for legacy tooling."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.config_path = (
            Path(config_path) if config_path else Path(__file__).with_name("prompts_and_settings.json")
        )
        self.config: Dict[str, Any] = self._load_config()

    # --------------------------------------------------------------------- #
    # Public helpers
    # --------------------------------------------------------------------- #
    def reload(self) -> None:
        """Reload configuration from disk."""
        self.config = self._load_config()

    def get_prompt(self, section: str, fallback: str = "") -> str:
        """Return a prompt template for the requested section."""
        prompts = self.config.get("prompts") or self.config.get("sections") or {}
        if isinstance(prompts, dict):
            value = prompts.get(section)
            if isinstance(value, str):
                return value
        return fallback

    def get(self, path: Optional[str] = None, default: Any = None) -> Any:
        """Retrieve a configuration value using dot notation."""
        if not path:
            return self.config

        cursor: Any = self.config
        for part in path.split("."):
            if isinstance(cursor, dict) and part in cursor:
                cursor = cursor[part]
            else:
                return default
        return cursor

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _load_config(self) -> Dict[str, Any]:
        """Load JSON configuration with graceful fallbacks."""
        try:
            with self.config_path.open(encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, dict):
                    return data
                logger.warning(
                    "Unexpected config structure in %s; falling back to empty dict", self.config_path
                )
        except FileNotFoundError:
            logger.warning(f"Configuration file not found at {self.config_path}; using defaults")
        except json.JSONDecodeError as exc:
            logger.error(f"Failed to parse configuration file {self.config_path}: {exc}")

        # Fallback minimal structure so tests can still run.
        return {"prompts": {}, "metadata": {}}


__all__ = ["ConfigManager"]
