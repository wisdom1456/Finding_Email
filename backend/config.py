"""
Configuration settings for the application.
"""

from __future__ import annotations

import logging
import os


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- Mandatory Settings ---
# These settings must be configured for the application to run.
API_KEY = os.environ.get("API_KEY")
MODEL_NAME = os.environ.get("MODEL_NAME", "default-model")
DATABASE_URL = os.environ.get("DATABASE_URL")

# --- Optional Settings ---
# These settings have default values but can be overridden.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
TEMPLATE_DIR = os.environ.get("TEMPLATE_DIR", "templates/")
FILE_STORAGE_PATH = os.environ.get("FILE_STORAGE_PATH", "/tmp/uploads")

MANDATORY_SETTINGS = ["API_KEY", "MODEL_NAME", "DATABASE_URL"]


def validate_config():
    """
    Validates that all mandatory configuration settings are present.

    Raises:
        ValueError: If a mandatory setting is missing.
    """
    logging.info("Entering validate_config.")
    missing_settings = []

    for setting in MANDATORY_SETTINGS:
        if globals().get(setting) is None:
            missing_settings.append(setting)

    if missing_settings:
        error_message = (
            f"Missing mandatory configuration settings: {', '.join(missing_settings)}"
        )
        logging.error(error_message)
        raise ValueError(error_message)

    logging.info("Configuration validated successfully.")


if __name__ == "__main__":
    logging.info("config.py is being run standalone for testing.")

    try:
        # To test validation, you might need to unset environment variables.
        # For example:
        # unset API_KEY
        # python config.py
        validate_config()
    except ValueError as e:
        logging.exception(f"Configuration validation failed: {e}")
