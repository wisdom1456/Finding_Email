"""Audit logging for compliance and security."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from legal_portal.utils.structured_logger import StructuredLogger


class AuditLogger:
    """Specialized logger for audit trails."""

    def __init__(self):
        """Initialize audit logger."""
        self.logger = StructuredLogger("audit")

        # Only create audit directory if not in serverless environment
        # Vercel/AWS Lambda have read-only filesystems
        if not os.getenv("VERCEL") and not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
            try:
                self.audit_dir = Path("logs/audit")
                self.audit_dir.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError):
                # If we can't create audit dir, use None (will skip file writing)
                self.audit_dir = None
        else:
            # In serverless, skip file-based audit logging (use structured logger to stdout)
            self.audit_dir = None

    def log_authentication(
        self, username: str, action: str, success: bool, ip_address: Optional[str] = None, **kwargs
    ):
        """Log authentication events."""
        self.logger.audit(
            action=f"auth.{action}",
            resource="authentication",
            outcome="success" if success else "failure",
            username=username,
            ip_address=ip_address,
            **kwargs,
        )

        # Store in separate audit file
        self._write_audit_log(
            {
                "category": "authentication",
                "action": action,
                "username": username,
                "success": success,
                "ip_address": ip_address,
                **kwargs,
            }
        )

    def log_data_access(
        self, user: str, resource: str, action: str, data_classification: str = "confidential", **kwargs
    ):
        """Log data access events."""
        self.logger.audit(
            action=f"data.{action}",
            resource=resource,
            outcome="accessed",
            user=user,
            data_classification=data_classification,
            **kwargs,
        )

        self._write_audit_log(
            {
                "category": "data_access",
                "action": action,
                "resource": resource,
                "user": user,
                "data_classification": data_classification,
                **kwargs,
            }
        )

    def log_configuration_change(self, user: str, setting: str, old_value: Any, new_value: Any, **kwargs):
        """Log configuration changes."""
        self.logger.audit(
            action="config.change",
            resource=setting,
            outcome="modified",
            user=user,
            old_value=str(old_value),
            new_value=str(new_value),
            **kwargs,
        )

        self._write_audit_log(
            {
                "category": "configuration",
                "action": "change",
                "setting": setting,
                "user": user,
                "old_value": old_value,
                "new_value": new_value,
                **kwargs,
            }
        )

    def log_security_event(self, event_type: str, severity: str, description: str, **kwargs):
        """Log security events."""
        self.logger.audit(
            action=f"security.{event_type}",
            resource="system",
            outcome=severity,
            description=description,
            **kwargs,
        )

        self._write_audit_log(
            {
                "category": "security",
                "event_type": event_type,
                "severity": severity,
                "description": description,
                **kwargs,
            }
        )

    def log_document_processing(self, user: str, document_name: str, action: str, success: bool, **kwargs):
        """Log document processing events for legal compliance."""
        self.logger.audit(
            action=f"document.{action}",
            resource=document_name,
            outcome="success" if success else "failure",
            user=user,
            **kwargs,
        )

        self._write_audit_log(
            {
                "category": "document_processing",
                "action": action,
                "document": document_name,
                "user": user,
                "success": success,
                **kwargs,
            }
        )

    def log_api_access(self, user: str, api_endpoint: str, method: str, status_code: int, **kwargs):
        """Log API access events."""
        self.logger.audit(
            action=f"api.{method.lower()}",
            resource=api_endpoint,
            outcome=str(status_code),
            user=user,
            **kwargs,
        )

        self._write_audit_log(
            {
                "category": "api_access",
                "action": method,
                "endpoint": api_endpoint,
                "user": user,
                "status_code": status_code,
                **kwargs,
            }
        )

    def _write_audit_log(self, audit_data: Dict[str, Any]):
        """Write audit log to tamper-resistant file."""
        # Add metadata
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "audit_id": str(uuid.uuid4()),
            **audit_data,
        }

        # Calculate hash for integrity
        entry_json = json.dumps(audit_entry, sort_keys=True)
        audit_entry["hash"] = hashlib.sha256(entry_json.encode()).hexdigest()

        # Write to daily audit file (only if audit_dir is available)
        if self.audit_dir is not None:
            audit_file = self.audit_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.json"
            with open(audit_file, "a") as f:
                f.write(json.dumps(audit_entry) + "\n")


@lru_cache(maxsize=1)
def get_audit_logger() -> AuditLogger:
    """Get the singleton AuditLogger instance."""
    return AuditLogger()


# Backward-compatible alias (preserves: from ...audit_logger import audit_logger)
audit_logger = get_audit_logger()
