import os
import sys

# Configure Python path
current_dir = os.path.dirname(__file__)  # api/
root_dir = os.path.dirname(current_dir)  # project root
src_dir = os.path.join(root_dir, "src")
packages_dir = os.path.join(current_dir, "packages")

# Add paths: src/ first (for legal_portal), then packages/ (for dependencies)
sys.path.insert(0, src_dir)
if os.path.exists(packages_dir):
    sys.path.insert(0, packages_dir)

# Import app (must be after sys.path configuration)
from legal_portal.api.main import app  # noqa: E402

__all__ = ["app"]
