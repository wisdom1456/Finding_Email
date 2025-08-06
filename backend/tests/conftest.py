import sys
from pathlib import Path

# Add the project's root directory to the Python path
# This allows tests to import modules from the 'backend' and 'backend_logic' directories
root_dir = Path(__file__).resolve().parents[2]
sys.path.append(str(root_dir))
