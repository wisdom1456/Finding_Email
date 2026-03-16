#!/usr/bin/env python3
"""Entry point for running the FastAPI backend locally."""

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

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("legal_portal.api.main:app", host="0.0.0.0", port=8080, reload=False)
