"""Secure session management."""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, List, Optional

import streamlit as st

logger = logging.getLogger(__name__)


class SessionManager:
    """Manage user sessions securely."""

    def __init__(self, timeout_minutes: int = 30, max_sessions_per_user: int = 3):
        """Initialize session manager.

        Args:
        ----
            timeout_minutes: Session timeout in minutes
            max_sessions_per_user: Maximum concurrent sessions per user

        """
        self.timeout_minutes = timeout_minutes
        self.max_sessions_per_user = max_sessions_per_user
        self._init_session_state()
        self._init_session_store()

    def _init_session_state(self):
        """Initialize session state variables."""
        if "session_id" not in st.session_state:
            st.session_state["session_id"] = self._generate_session_id()

        if "last_activity" not in st.session_state:
            st.session_state["last_activity"] = datetime.now()

        if "session_data" not in st.session_state:
            st.session_state["session_data"] = {}

        if "session_created" not in st.session_state:
            st.session_state["session_created"] = datetime.now()

        if "session_ip" not in st.session_state:
            # In production, you would get the actual client IP
            st.session_state["session_ip"] = "unknown"

    def _init_session_store(self):
        """Initialize global session store."""
        # In production, this would be Redis or a database
        # For now, using st.session_state as a simple store
        if "global_sessions" not in st.session_state:
            st.session_state["global_sessions"] = {}

    def _generate_session_id(self) -> str:
        """Generate secure session ID."""
        random_bytes = secrets.token_bytes(32)
        timestamp = str(datetime.now().timestamp()).encode()
        unique_id = str(uuid.uuid4()).encode()
        combined = random_bytes + timestamp + unique_id

        session_id = hashlib.sha256(combined).hexdigest()
        logger.info(f"Generated new session ID: {session_id[:8]}...")
        return session_id

    def check_session_timeout(self) -> bool:
        """Check if session has timed out."""
        if "last_activity" not in st.session_state:
            logger.warning("No last_activity in session, treating as timeout")
            return True

        last_activity = st.session_state["last_activity"]
        timeout_threshold = datetime.now() - timedelta(minutes=self.timeout_minutes)

        if last_activity < timeout_threshold:
            logger.info(
                f"Session timeout for session: {st.session_state.get('session_id', 'unknown')[:8]}..."
            )
            self.clear_session()
            return True

        # Update last activity
        st.session_state["last_activity"] = datetime.now()
        return False

    def clear_session(self):
        """Clear session data."""
        session_id = st.session_state.get("session_id")
        if session_id:
            logger.info(f"Clearing session: {session_id[:8]}...")

            # Remove from global sessions if exists
            if "global_sessions" in st.session_state and session_id in st.session_state["global_sessions"]:
                del st.session_state["global_sessions"][session_id]

        # Keys to preserve across session clear
        keys_to_keep = ["session_id", "global_sessions"]

        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]

        # Generate new session ID
        st.session_state["session_id"] = self._generate_session_id()
        st.session_state["last_activity"] = datetime.now()
        st.session_state["session_data"] = {}
        st.session_state["session_created"] = datetime.now()

    def get_session_data(self, key: str, default: Any = None) -> Any:
        """Get data from session."""
        return st.session_state.get("session_data", {}).get(key, default)

    def set_session_data(self, key: str, value: Any):
        """Set data in session."""
        if "session_data" not in st.session_state:
            st.session_state["session_data"] = {}

        st.session_state["session_data"][key] = value
        st.session_state["last_activity"] = datetime.now()

    def extend_session(self, minutes: Optional[int] = None):
        """Extend session timeout."""
        if minutes is None:
            minutes = self.timeout_minutes

        st.session_state["last_activity"] = datetime.now()
        logger.info(f"Session extended for {minutes} minutes")

    def create_user_session(self, username: str, user_data: Dict) -> bool:
        """Create a new user session."""
        session_id = st.session_state.get("session_id")

        # Check for existing sessions for this user
        existing_sessions = self._get_user_sessions(username)

        # Enforce session limit
        if len(existing_sessions) >= self.max_sessions_per_user:
            # Remove oldest session
            oldest_session = min(existing_sessions, key=lambda x: x.get("created", datetime.now()))
            self._remove_session(oldest_session["session_id"])
            logger.info(f"Removed oldest session for user {username} due to session limit")

        # Store session info
        session_info = {
            "session_id": session_id,
            "username": username,
            "created": datetime.now(),
            "last_activity": datetime.now(),
            "ip_address": st.session_state.get("session_ip", "unknown"),
            "user_data": user_data,
        }

        if "global_sessions" not in st.session_state:
            st.session_state["global_sessions"] = {}

        st.session_state["global_sessions"][session_id] = session_info

        # Update session state
        st.session_state["username"] = username
        st.session_state["user_data"] = user_data
        st.session_state["authenticated"] = True

        logger.info(f"Created session for user {username}: {session_id[:8]}...")
        return True

    def _get_user_sessions(self, username: str) -> List[Dict]:
        """Get all sessions for a user."""
        sessions = []
        for _session_id, session_info in st.session_state.get("global_sessions", {}).items():
            if session_info.get("username") == username:
                sessions.append(session_info)
        return sessions

    def _remove_session(self, session_id: str):
        """Remove a specific session."""
        if "global_sessions" in st.session_state and session_id in st.session_state["global_sessions"]:
            del st.session_state["global_sessions"][session_id]
            logger.info(f"Removed session: {session_id[:8]}...")

    def invalidate_user_sessions(self, username: str):
        """Invalidate all sessions for a user."""
        sessions = self._get_user_sessions(username)
        for session in sessions:
            self._remove_session(session["session_id"])

        logger.info(f"Invalidated all sessions for user {username}")

    def get_session_info(self) -> Dict:
        """Get current session information."""
        session_id = st.session_state.get("session_id")

        return {
            "session_id": session_id,
            "created": st.session_state.get("session_created"),
            "last_activity": st.session_state.get("last_activity"),
            "authenticated": st.session_state.get("authenticated", False),
            "username": st.session_state.get("username"),
            "timeout_minutes": self.timeout_minutes,
            "time_remaining": self._get_time_remaining(),
        }

    def _get_time_remaining(self) -> Optional[int]:
        """Get remaining time before session timeout (in minutes)."""
        if "last_activity" not in st.session_state:
            return None

        last_activity = st.session_state["last_activity"]
        elapsed = (datetime.now() - last_activity).total_seconds() / 60
        remaining = self.timeout_minutes - elapsed

        return max(0, int(remaining))

    def get_active_sessions_count(self) -> int:
        """Get count of active sessions."""
        return len(st.session_state.get("global_sessions", {}))

    def cleanup_expired_sessions(self):
        """Clean up expired sessions from the global store."""
        if "global_sessions" not in st.session_state:
            return

        current_time = datetime.now()
        expired_sessions = []

        for session_id, session_info in st.session_state["global_sessions"].items():
            last_activity = session_info.get("last_activity", current_time)
            if isinstance(last_activity, str):
                last_activity = datetime.fromisoformat(last_activity)

            timeout_threshold = current_time - timedelta(minutes=self.timeout_minutes)

            if last_activity < timeout_threshold:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del st.session_state["global_sessions"][session_id]
            logger.info(f"Cleaned up expired session: {session_id[:8]}...")

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

    def require_session(self, func):
        """Decorator to require valid session."""

        @wraps(func)
        def wrapper(*args, **kwargs):
            if self.check_session_timeout():
                st.error("Your session has expired. Please login again.")
                st.stop()

            if not st.session_state.get("authenticated"):
                st.error("Please login to access this feature")
                st.stop()

            return func(*args, **kwargs)

        return wrapper

    def update_session_activity(self):
        """Update session activity timestamp."""
        st.session_state["last_activity"] = datetime.now()

        # Update in global store if exists
        session_id = st.session_state.get("session_id")
        if session_id and "global_sessions" in st.session_state:
            if session_id in st.session_state["global_sessions"]:
                st.session_state["global_sessions"][session_id]["last_activity"] = datetime.now()


class SessionMonitor:
    """Monitor and audit session activities."""

    def __init__(self, log_file: str = "session_audit.log"):
        """Initialize session monitor."""
        self.log_file = log_file
        self.setup_audit_logger()

    def setup_audit_logger(self):
        """Setup audit logger for session activities."""
        self.audit_logger = logging.getLogger("session_audit")
        self.audit_logger.setLevel(logging.INFO)

        # Create file handler
        handler = logging.FileHandler(self.log_file)
        handler.setLevel(logging.INFO)

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)

        # Add handler to logger
        self.audit_logger.addHandler(handler)

    def log_login(self, username: str, session_id: str, ip_address: str = "unknown"):
        """Log user login."""
        self.audit_logger.info(f"LOGIN - User: {username}, Session: {session_id[:8]}..., IP: {ip_address}")

    def log_logout(self, username: str, session_id: str):
        """Log user logout."""
        self.audit_logger.info(f"LOGOUT - User: {username}, Session: {session_id[:8]}...")

    def log_timeout(self, username: str, session_id: str):
        """Log session timeout."""
        self.audit_logger.info(f"TIMEOUT - User: {username}, Session: {session_id[:8]}...")

    def log_failed_login(self, username: str, ip_address: str = "unknown"):
        """Log failed login attempt."""
        self.audit_logger.warning(f"FAILED_LOGIN - User: {username}, IP: {ip_address}")

    def log_permission_denied(self, username: str, resource: str):
        """Log permission denied."""
        self.audit_logger.warning(f"PERMISSION_DENIED - User: {username}, Resource: {resource}")

    def log_session_extended(self, username: str, session_id: str, minutes: int):
        """Log session extension."""
        self.audit_logger.info(
            f"SESSION_EXTENDED - User: {username}, Session: {session_id[:8]}..., Minutes: {minutes}"
        )

    def log_password_change(self, username: str):
        """Log password change."""
        self.audit_logger.info(f"PASSWORD_CHANGED - User: {username}")

    def log_user_created(self, username: str, created_by: str):
        """Log user creation."""
        self.audit_logger.info(f"USER_CREATED - User: {username}, Created by: {created_by}")

    def log_user_deleted(self, username: str, deleted_by: str):
        """Log user deletion."""
        self.audit_logger.info(f"USER_DELETED - User: {username}, Deleted by: {deleted_by}")

    def log_role_changed(self, username: str, old_role: str, new_role: str, changed_by: str):
        """Log role change."""
        self.audit_logger.info(
            f"ROLE_CHANGED - User: {username}, Old: {old_role}, New: {new_role}, Changed by: {changed_by}"
        )

    def get_recent_activities(self, limit: int = 100) -> List[str]:
        """Get recent audit activities."""
        try:
            with open(self.log_file) as f:
                lines = f.readlines()
                return lines[-limit:] if len(lines) > limit else lines
        except FileNotFoundError:
            return []
