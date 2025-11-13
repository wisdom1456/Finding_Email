#!/usr/bin/env python3
"""Entry point for the Legal Document Analysis Portal.

This script serves as the main entry point for running the Streamlit application.
It ensures proper module path configuration and launches the UI.

Usage:
    streamlit run run_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Load environment variables FIRST before any other imports
from dotenv import load_dotenv

load_dotenv()

# Add the src directory to the Python path to ensure imports work correctly
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import and run the main UI
from legal_portal.ui.main import main  # noqa: E402

if __name__ == "__main__":
    main()
