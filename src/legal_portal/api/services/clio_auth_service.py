"""CLIO OAuth 2.0 authentication service for FastAPI integration.

This module handles OAuth authentication flow with CLIO Manage API,
adapted for use with Vercel Python runtime and Supabase token storage.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from urllib.parse import urlencode

import requests


class ClioAuthService:
    """Service for handling CLIO OAuth 2.0 authentication."""

    def __init__(self, redirect_uri: str | None = None):
        """Initialize the CLIO authentication service.

        Args:
        ----
            redirect_uri: Optional override for redirect URI (supports dynamic URLs for Vercel)

        """
        self.client_id = os.getenv("CLIO_CLIENT_ID")
        self.client_secret = os.getenv("CLIO_CLIENT_SECRET")

        # Dynamic redirect URI support for Vercel deployments
        if redirect_uri:
            self.redirect_uri = redirect_uri
        else:
            # Auto-detect based on environment
            vercel_url = os.getenv("VERCEL_URL")
            if vercel_url:
                self.redirect_uri = f"https://{vercel_url}/api/clio/callback"
            else:
                self.redirect_uri = os.getenv("CLIO_REDIRECT_URI", "http://localhost:8080/api/clio/callback")

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "CLIO credentials not configured. "
                "Set CLIO_CLIENT_ID and CLIO_CLIENT_SECRET environment variables."
            )

        # CLIO API URLs (same for both sandbox and production)
        self.base_url = "https://app.clio.com"
        self.auth_url = f"{self.base_url}/oauth/authorize"
        self.token_url = f"{self.base_url}/oauth/token"

        # Required OAuth scopes for CLIO integration
        self.scopes = [
            "matters:read",
            "communications:read",
            "documents:read",
            "notes:read",
            "contacts:read",
        ]

    def get_api_base_url(self) -> str:
        """Get the CLIO API base URL.

        Returns
        -------
            str: Base URL for CLIO API v4

        """
        return f"{self.base_url}/api/v4"

    def get_authorization_url(self, state: str | None = None) -> str:
        """Generate CLIO OAuth authorization URL.

        Args:
        ----
            state: Optional state parameter for CSRF protection

        Returns:
        -------
            str: Authorization URL to redirect user to

        """
        if not self.client_id:
            raise ValueError("CLIO_CLIENT_ID not configured")

        # Generate random state if not provided
        if not state:
            state = secrets.token_urlsafe(32)

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
        }

        auth_url = f"{self.auth_url}?{urlencode(params)}"

        return auth_url

    def handle_oauth_callback(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token.

        Args:
        ----
            code: Authorization code from OAuth callback

        Returns:
        -------
            Dict containing:
                - access_token: Access token for API calls
                - refresh_token: Token for refreshing access
                - expires_at: Datetime when token expires
                - token_type: Type of token (usually "Bearer")

        Raises:
        ------
            ValueError: If exchange fails or invalid code

        """
        if not self.client_id or not self.client_secret:
            raise ValueError("CLIO credentials not configured")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
        }

        try:
            response = requests.post(self.token_url, data=data, timeout=30)
            response.raise_for_status()

            token_data = response.json()

            # Calculate expiration time (CLIO tokens typically expire in 1 hour)
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            result = {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": expires_at,
                "token_type": token_data.get("token_type", "Bearer"),
            }

            return result

        except requests.exceptions.RequestException as e:
            raise ValueError(f"OAuth token exchange failed: {e}") from e

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh an expired access token.

        Args:
        ----
            refresh_token: Refresh token from previous authorization

        Returns:
        -------
            Dict containing new access_token, refresh_token, and expires_at

        Raises:
        ------
            ValueError: If refresh fails

        """
        if not self.client_id or not self.client_secret:
            raise ValueError("CLIO credentials not configured")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = requests.post(self.token_url, data=data, timeout=30)
            response.raise_for_status()

            token_data = response.json()

            # Calculate new expiration time
            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            result = {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", refresh_token),  # Reuse if not provided
                "expires_at": expires_at,
                "token_type": token_data.get("token_type", "Bearer"),
            }

            return result

        except requests.exceptions.RequestException as e:
            raise ValueError(f"Token refresh failed: {e}") from e

    def is_token_expired(self, expires_at: datetime) -> bool:
        """Check if access token is expired or about to expire.

        Args:
        ----
            expires_at: Token expiration datetime

        Returns:
        -------
            bool: True if token is expired or expires in < 5 minutes

        """
        # Consider token expired if it expires in less than 5 minutes
        buffer = timedelta(minutes=5)
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return now >= (expires_at - buffer)
