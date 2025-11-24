import os
import sys

# Add the root directory to the Python path so 'src' can be imported
# Vercel places the files in the task root
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

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
