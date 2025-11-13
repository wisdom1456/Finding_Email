"""Enterprise authentication and authorization module."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bcrypt
import jwt
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """User role definitions."""

    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"
    AUDITOR = "auditor"


class Permissions(Enum):
    """Permission definitions."""

    VIEW_DOCUMENTS = "view_documents"
    UPLOAD_DOCUMENTS = "upload_documents"
    GENERATE_LETTERS = "generate_letters"
    EXPORT_DATA = "export_data"
    VIEW_ANALYTICS = "view_analytics"
    MANAGE_USERS = "manage_users"
    AUDIT_LOGS = "audit_logs"
    SYSTEM_CONFIG = "system_config"


# Role-permission mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [
        Permissions.VIEW_DOCUMENTS,
        Permissions.UPLOAD_DOCUMENTS,
        Permissions.GENERATE_LETTERS,
        Permissions.EXPORT_DATA,
        Permissions.VIEW_ANALYTICS,
        Permissions.MANAGE_USERS,
        Permissions.AUDIT_LOGS,
        Permissions.SYSTEM_CONFIG,
    ],
    UserRole.USER: [
        Permissions.VIEW_DOCUMENTS,
        Permissions.UPLOAD_DOCUMENTS,
        Permissions.GENERATE_LETTERS,
        Permissions.EXPORT_DATA,
        Permissions.VIEW_ANALYTICS,
    ],
    UserRole.VIEWER: [
        Permissions.VIEW_DOCUMENTS,
        Permissions.VIEW_ANALYTICS,
    ],
    UserRole.AUDITOR: [
        Permissions.VIEW_DOCUMENTS,
        Permissions.VIEW_ANALYTICS,
        Permissions.AUDIT_LOGS,
    ],
}


class AuthManager:
    """Manage authentication and authorization."""

    def __init__(self, config_file: str = "config/auth_config.yaml"):
        """Initialize authentication manager."""
        self.config_file = Path(config_file)
        self.config = self._load_config()
        self.authenticator = self._setup_authenticator()
        self.jwt_secret = self.config.get("jwt_secret", secrets.token_urlsafe(32))

    def _load_config(self) -> Dict:
        """Load authentication configuration."""
        if not self.config_file.exists():
            # Create default config
            default_config = {
                "credentials": {
                    "usernames": {
                        "admin": {
                            "email": "admin@example.com",
                            "name": "Administrator",
                            "password": bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode(),
                            "role": "admin",
                        }
                    }
                },
                "cookie": {"name": "legal_portal_auth", "key": secrets.token_urlsafe(32), "expiry_days": 30},
                "preauthorized": {"emails": []},
                "jwt_secret": secrets.token_urlsafe(32),
            }

            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                yaml.dump(default_config, f)

            return default_config

        with open(self.config_file) as f:
            return yaml.load(f, Loader=SafeLoader)

    def _setup_authenticator(self) -> stauth.Authenticate:
        """Setup streamlit authenticator."""
        return stauth.Authenticate(
            self.config["credentials"],
            self.config["cookie"]["name"],
            self.config["cookie"]["key"],
            self.config["cookie"]["expiry_days"],
            self.config.get("preauthorized", {}),
        )

    def login(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Handle user login."""
        name, authentication_status, username = self.authenticator.login("Login", "main")

        if authentication_status:
            # Set session state
            st.session_state["authentication_status"] = True
            st.session_state["username"] = username
            st.session_state["name"] = name
            st.session_state["role"] = self._get_user_role(username)

            # Log successful login
            logger.info(f"User {username} logged in successfully")

            # Generate JWT token
            token = self._generate_jwt_token(username)
            st.session_state["auth_token"] = token

        elif authentication_status is False:
            st.error("Username/password is incorrect")
            logger.warning(f"Failed login attempt for username: {username}")

        elif authentication_status is None:
            st.warning("Please enter your username and password")

        return name, authentication_status, username

    def logout(self):
        """Handle user logout."""
        self.authenticator.logout("Logout", "sidebar")

        # Clear session state
        for key in ["authentication_status", "username", "name", "role", "auth_token"]:
            if key in st.session_state:
                del st.session_state[key]

        logger.info("User logged out")

    def _get_user_role(self, username: str) -> UserRole:
        """Get user role from config."""
        user_data = self.config["credentials"]["usernames"].get(username, {})
        role_str = user_data.get("role", "viewer")
        return UserRole(role_str)

    def _generate_jwt_token(self, username: str) -> str:
        """Generate JWT token for user."""
        payload = {
            "username": username,
            "role": st.session_state.get("role", UserRole.VIEWER).value,
            "exp": datetime.utcnow() + timedelta(days=1),
            "iat": datetime.utcnow(),
        }

        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify JWT token."""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid token")
            return None

    def has_permission(self, permission: Permissions) -> bool:
        """Check if current user has permission."""
        if not st.session_state.get("authentication_status"):
            return False

        user_role = st.session_state.get("role", UserRole.VIEWER)
        allowed_permissions = ROLE_PERMISSIONS.get(user_role, [])

        return permission in allowed_permissions

    def require_auth(self, permission: Optional[Permissions] = None):
        """Decorator to require authentication."""

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not st.session_state.get("authentication_status"):
                    st.error("Please login to access this feature")
                    st.stop()

                if permission and not self.has_permission(permission):
                    st.error(f"You don't have permission to {permission.value}")
                    st.stop()

                return func(*args, **kwargs)

            return wrapper

        return decorator

    def register_user(self, username: str, email: str, name: str, password: str, role: str = "user") -> bool:
        """Register a new user."""
        if username in self.config["credentials"]["usernames"]:
            return False

        # Hash password
        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Add user to config
        self.config["credentials"]["usernames"][username] = {
            "email": email,
            "name": name,
            "password": hashed_password,
            "role": role,
        }

        # Save config
        with open(self.config_file, "w") as f:
            yaml.dump(self.config, f)

        logger.info(f"New user registered: {username}")
        return True

    def update_user_role(self, username: str, new_role: str) -> bool:
        """Update user role."""
        if username not in self.config["credentials"]["usernames"]:
            return False

        self.config["credentials"]["usernames"][username]["role"] = new_role

        # Save config
        with open(self.config_file, "w") as f:
            yaml.dump(self.config, f)

        logger.info(f"User {username} role updated to {new_role}")
        return True

    def delete_user(self, username: str) -> bool:
        """Delete a user."""
        if username not in self.config["credentials"]["usernames"]:
            return False

        del self.config["credentials"]["usernames"][username]

        # Save config
        with open(self.config_file, "w") as f:
            yaml.dump(self.config, f)

        logger.info(f"User {username} deleted")
        return True

    def list_users(self) -> List[Dict]:
        """List all users."""
        users = []
        for username, data in self.config["credentials"]["usernames"].items():
            users.append(
                {
                    "username": username,
                    "email": data.get("email", ""),
                    "name": data.get("name", ""),
                    "role": data.get("role", "viewer"),
                }
            )
        return users

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Change user password."""
        if username not in self.config["credentials"]["usernames"]:
            return False

        # Verify old password
        stored_hash = self.config["credentials"]["usernames"][username]["password"]
        if not bcrypt.checkpw(old_password.encode(), stored_hash.encode()):
            return False

        # Update password
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        self.config["credentials"]["usernames"][username]["password"] = new_hash

        # Save config
        with open(self.config_file, "w") as f:
            yaml.dump(self.config, f)

        logger.info(f"Password changed for user {username}")
        return True

    def reset_password(self, username: str, new_password: str) -> bool:
        """Reset user password (admin function)."""
        if username not in self.config["credentials"]["usernames"]:
            return False

        # Update password
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        self.config["credentials"]["usernames"][username]["password"] = new_hash

        # Save config
        with open(self.config_file, "w") as f:
            yaml.dump(self.config, f)

        logger.info(f"Password reset for user {username}")
        return True
