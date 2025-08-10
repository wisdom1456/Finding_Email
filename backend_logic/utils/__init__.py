"""
Backend Logic Utilities

This package contains utility functions and modules for the backend logic.
"""

from __future__ import annotations

import os

# Import from utils.py (the file that contains ProgressTracker and other utilities)
import sys
from pathlib import Path

from .logging_config import get_logger, get_module_logger, setup_logging


# Add the parent directory to import from utils.py
utils_py_path = Path(__file__).parent.parent / "utils.py"
if utils_py_path.exists():
    import importlib.util

    spec = importlib.util.spec_from_file_location("backend_logic_utils", utils_py_path)
    utils_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(utils_module)

    # Import specific items from utils.py
    ProgressTracker = utils_module.ProgressTracker
    calculate_document_sizes = utils_module.calculate_document_sizes
    display_cost_estimation = utils_module.display_cost_estimation
    display_processing_cost_update = utils_module.display_processing_cost_update
    generate_cost_estimate_for_files = utils_module.generate_cost_estimate_for_files
    generate_case_analysis_html = utils_module.generate_case_analysis_html
    handle_file_uploads = utils_module.handle_file_uploads

__all__ = [
    "ProgressTracker",
    "calculate_document_sizes",
    "display_cost_estimation",
    "display_processing_cost_update",
    "generate_case_analysis_html",
    "generate_cost_estimate_for_files",
    "get_logger",
    "get_module_logger",
    "handle_file_uploads",
    "setup_logging",
]
