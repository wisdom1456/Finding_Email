import os
import json
import time
from typing import Any, Dict
from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

class DiagnosticLogger:
    """Utility to capture intermediate pipeline outputs for debugging and quality analysis."""
    
    def __init__(self, session_id: str = None):
        self.session_id = session_id or f"diag_{int(time.time())}"
        self.base_path = os.path.join("debug_output", "sessions", self.session_id)
        os.makedirs(self.base_path, exist_ok=True)
        logger.info(f"DIAGNOSTIC LOGGER: Initialized for session {self.session_id} at {self.base_path}")

    def log_stage(self, stage_name: str, data: Any, metadata: Dict[str, Any] = None):
        """Save data for a specific pipeline stage."""
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

