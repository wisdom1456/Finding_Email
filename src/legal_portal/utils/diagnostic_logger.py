import json
import os
import time
from typing import Any, Dict

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

# #region agent log
_DEBUG_LOG_PATH = "/tmp/cursor_debug.log" if os.getenv("VERCEL") else "/Users/BRFlorida/Projects/Work/Finding_Emails/.cursor/debug.log"
def _dbg_log(hyp: str, msg: str, data: dict = None):
    try:
        import json as _j; open(_DEBUG_LOG_PATH, "a").write(_j.dumps({"hypothesisId": hyp, "location": "diagnostic_logger.py", "message": msg, "data": data or {}, "timestamp": time.time(), "sessionId": "debug-session"}) + "\n")
    except: pass
# #endregion agent log

def _is_serverless_environment() -> bool:
    """Detect if running in a serverless environment (Vercel, AWS Lambda, etc.)."""
    return bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("FUNCTION_NAME"))

def _get_writable_base_dir() -> str:
    """Get a writable base directory for diagnostic output."""
    if _is_serverless_environment():
        # Serverless environments only have /tmp writable
        return "/tmp/debug_output"
    return "debug_output"

class DiagnosticLogger:
    """Utility to capture intermediate pipeline outputs for debugging and quality analysis."""

    def __init__(self, session_id: str = None):
        self.session_id = session_id or f"diag_{int(time.time())}"
        self._enabled = True  # Track if file logging is working
        # #region agent log
        _dbg_log("H1", "DiagnosticLogger.__init__ called", {"session_id": session_id, "cwd": os.getcwd()})
        _dbg_log("H2", "Checking DIAGNOSTIC_MODE env", {"DIAGNOSTIC_MODE": os.getenv("DIAGNOSTIC_MODE"), "enabled": self.get_enabled()})
        _dbg_log("H3", "Checking serverless env vars", {"VERCEL": os.getenv("VERCEL"), "AWS_LAMBDA_FUNCTION_NAME": os.getenv("AWS_LAMBDA_FUNCTION_NAME"), "is_serverless": _is_serverless_environment()})
        # #endregion agent log

        base_dir = _get_writable_base_dir()
        self.base_path = os.path.join(base_dir, "sessions", self.session_id)
        # #region agent log
        _dbg_log("H1", "Attempting makedirs with serverless-aware path", {"base_path": self.base_path, "abs_path": os.path.abspath(self.base_path), "base_dir": base_dir})
        # #endregion agent log
        try:
            os.makedirs(self.base_path, exist_ok=True)
            # #region agent log
            _dbg_log("H4", "makedirs succeeded", {"base_path": self.base_path})
            # #endregion agent log
            logger.info(f"DIAGNOSTIC LOGGER: Initialized for session {self.session_id} at {self.base_path}")
        except OSError as e:
            # #region agent log
            _dbg_log("H4", "makedirs FAILED - disabling file logging gracefully", {"error": str(e), "errno": e.errno, "base_path": self.base_path})
            # #endregion agent log
            # Gracefully disable file logging instead of crashing
            self._enabled = False
            logger.warning(f"DIAGNOSTIC LOGGER: Could not create output directory ({e}). File logging disabled for session {self.session_id}")

    def log_stage(self, stage_name: str, data: Any, metadata: Dict[str, Any] = None):
        """Save data for a specific pipeline stage."""
        if not self._enabled:
            # File logging disabled (e.g., in serverless environment with read-only filesystem)
            logger.debug(f"DIAGNOSTIC LOGGER: Skipping stage '{stage_name}' (file logging disabled)")
            return

        file_ext = "json" if isinstance(data, (dict, list)) else "txt"
        file_path = os.path.join(self.base_path, f"{stage_name}.{file_ext}")

        try:
            if file_ext == "json":
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump({"data": data, "metadata": metadata or {}}, f, indent=2, default=str)
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(str(data))

            logger.info(f"DIAGNOSTIC LOGGER: Saved stage '{stage_name}' to {file_path}")
        except Exception as e:
            logger.error(f"DIAGNOSTIC LOGGER: Failed to save stage '{stage_name}': {e}")

    @staticmethod
    def get_enabled() -> bool:
        """Check if diagnostic logging is enabled via environment variable."""
        return os.getenv("DIAGNOSTIC_MODE", "false").lower() == "true"

