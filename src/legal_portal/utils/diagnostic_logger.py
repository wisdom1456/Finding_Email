import json
import os
import time
from typing import Any, Dict

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

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

        base_dir = _get_writable_base_dir()
        self.base_path = os.path.join(base_dir, "sessions", self.session_id)
        try:
            os.makedirs(self.base_path, exist_ok=True)
            logger.info(f"DIAGNOSTIC LOGGER: Initialized for session {self.session_id} at {self.base_path}")
        except OSError as e:
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

