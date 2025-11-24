import os
import sys

# --- PATH CONFIGURATION ---
# We need to add both the root directory (for src/) and the api directory (for installed deps)
# to the Python path.

current_dir = os.path.dirname(__file__)  # The api/ directory
parent_dir = os.path.dirname(current_dir)  # The root directory
packages_dir = os.path.join(current_dir, "packages")  # Bundled dependencies

# 1. Add packages directory (HIGHEST PRIORITY for dependencies)
if os.path.exists(packages_dir) and packages_dir not in sys.path:
    sys.path.insert(0, packages_dir)

# 2. Add api/ directory to path (for local modules)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 3. Add root directory to path (for src/ imports)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print(f"PYTHONPATH modified. Added: {packages_dir}, {current_dir}, {parent_dir}", file=sys.stderr)
# --------------------------

# Check for required environment variables and provide helpful error messages
REQUIRED_ENV_VARS = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY"]
missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]

if missing_vars:
    error_msg = f"""
    ❌ Missing required environment variables: {', '.join(missing_vars)}

    To fix this error:
    1. Go to Vercel Dashboard → Settings → Environment Variables
    2. Add the missing variables
    3. Redeploy the application

    Required variables:
    - SUPABASE_URL: Your Supabase project URL
    - SUPABASE_SERVICE_KEY: Your Supabase service role key
    - SUPABASE_ANON_KEY: Your Supabase anon/public key

    See QUICK_FIX_STEPS.md for detailed instructions.
    """
    print(error_msg, file=sys.stderr)
    # Still try to import but will likely fail - at least we logged the issue

# Import the FastAPI app
# We use the full package path assuming 'src' is a package or in path
try:
    from src.legal_portal.api.main import app
except ImportError as e:
    print(f"Import error: {e}", file=sys.stderr)
    print(f"Python path: {sys.path}", file=sys.stderr)
    print(f"Current directory: {os.getcwd()}", file=sys.stderr)
    print(f"Directory contents: {os.listdir(os.getcwd())}", file=sys.stderr)
    # Fallback if src is not directly importable but legal_portal is
    # This might happen depending on how Vercel sets up PYTHONPATH
    try:
        from legal_portal.api.main import app
    except ImportError as e2:
        print(f"Fallback import also failed: {e2}", file=sys.stderr)
        raise

# Vercel expects 'app' to be the entry point
__all__ = ["app"]
