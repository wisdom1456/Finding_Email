import os
import sys

# Add the root directory to the Python path so 'src' can be imported
# Vercel places the files in the task root
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import the FastAPI app
# We use the full package path assuming 'src' is a package or in path
try:
    from src.legal_portal.api.main import app
except ImportError:
    # Fallback if src is not directly importable but legal_portal is
    # This might happen depending on how Vercel sets up PYTHONPATH
    from legal_portal.api.main import app

# Vercel expects 'app' to be the entry point
__all__ = ["app"]
