"""OAuth 2.0/OIDC integration for enterprise SSO."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import urlencode

import streamlit as st
from authlib.integrations.requests_client import OAuth2Session

logger = logging.getLogger(__name__)


class OAuthProvider:
    """OAuth 2.0 provider integration."""

    def __init__(self, provider: str = "google"):
        """Initialize OAuth provider."""
        self.provider = provider
        self.client_id = os.getenv(f"{provider.upper()}_CLIENT_ID")
        self.client_secret = os.getenv(f"{provider.upper()}_CLIENT_SECRET")
        self.redirect_uri = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8501/callback")

        self.providers = {
            "google": {
                "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
                "scope": "openid email profile",
                "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
            },
            "azure": {
                "authorize_url": f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID', 'common')}/oauth2/v2.0/authorize",
                "token_url": f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID', 'common')}/oauth2/v2.0/token",
                "userinfo_url": "https://graph.microsoft.com/v1.0/me",
                "scope": "openid email profile User.Read",
                "discovery_url": f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID', 'common')}/v2.0/.well-known/openid-configuration",
            },
            "okta": {
                "authorize_url": f"{os.getenv('OKTA_DOMAIN')}/oauth2/v1/authorize",
                "token_url": f"{os.getenv('OKTA_DOMAIN')}/oauth2/v1/token",
                "userinfo_url": f"{os.getenv('OKTA_DOMAIN')}/oauth2/v1/userinfo",
                "scope": "openid email profile",
                "discovery_url": f"{os.getenv('OKTA_DOMAIN')}/.well-known/openid-configuration",
            },
            "auth0": {
                "authorize_url": f"{os.getenv('AUTH0_DOMAIN')}/authorize",
                "token_url": f"{os.getenv('AUTH0_DOMAIN')}/oauth/token",
                "userinfo_url": f"{os.getenv('AUTH0_DOMAIN')}/userinfo",
                "scope": "openid email profile",
                "discovery_url": f"{os.getenv('AUTH0_DOMAIN')}/.well-known/openid-configuration",
            },
        }

        self.config = self.providers.get(provider)
        if not self.config:
            raise ValueError(f"Unsupported OAuth provider: {provider}")

        # Validate required environment variables
        if not self.client_id or not self.client_secret:
            logger.warning(f"OAuth provider {provider} not configured properly. Missing client credentials.")

    def get_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        """Get OAuth authorization URL."""
        if not self.client_id:
            raise ValueError(f"OAuth provider {self.provider} not configured. Missing CLIENT_ID.")

        # Generate state for CSRF protection
        if not state:
            state = secrets.token_urlsafe(32)

        # Build authorization URL
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.config["scope"],
            "response_type": "code",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }

        # Add provider-specific parameters
        if self.provider == "azure":
            params["response_mode"] = "query"

        authorization_url = f"{self.config['authorize_url']}?{urlencode(params)}"

        # Store state in session
        st.session_state["oauth_state"] = state
        st.session_state["oauth_provider"] = self.provider

        logger.info(f"Generated OAuth authorization URL for provider: {self.provider}")

        return authorization_url, state

    def handle_callback(self, code: str, state: str) -> Optional[Dict]:
        """Handle OAuth callback."""
        # Verify state for CSRF protection
        stored_state = st.session_state.get("oauth_state")
        if not stored_state or stored_state != state:
            logger.error("OAuth state mismatch - possible CSRF attack")
            return None

        if not self.client_id or not self.client_secret:
            logger.error(f"OAuth provider {self.provider} not configured properly")
            return None

        client = OAuth2Session(client_id=self.client_id, redirect_uri=self.redirect_uri)

        try:
            # Exchange code for token
            token = client.fetch_token(
                self.config["token_url"], code=code, client_secret=self.client_secret, include_client_id=True
            )

            # Store token in session
            st.session_state["oauth_token"] = token
            st.session_state["oauth_token_expiry"] = datetime.utcnow() + timedelta(
                seconds=token.get("expires_in", 3600)
            )

            # Get user info
            client.token = token

            # Handle provider-specific user info retrieval
            if self.provider == "azure":
                # Azure requires authorization header
                headers = {"Authorization": f"Bearer {token['access_token']}"}
                resp = client.get(self.config["userinfo_url"], headers=headers)
            else:
                resp = client.get(self.config["userinfo_url"])

            userinfo = resp.json()

            # Normalize user info across providers
            normalized_info = self._normalize_userinfo(userinfo)

            logger.info(f"OAuth login successful for user: {normalized_info.get('email')}")

            # Clear OAuth state
            del st.session_state["oauth_state"]

            return normalized_info

        except Exception as e:
            logger.error(f"OAuth callback error: {e}")
            return None

    def _normalize_userinfo(self, userinfo: Dict) -> Dict:
        """Normalize user info across different providers."""
        normalized = {"provider": self.provider, "raw_data": userinfo}

        if self.provider == "google":
            normalized.update(
                {
                    "email": userinfo.get("email"),
                    "name": userinfo.get("name"),
                    "picture": userinfo.get("picture"),
                    "email_verified": userinfo.get("email_verified", False),
                    "sub": userinfo.get("sub"),  # Unique identifier
                }
            )

        elif self.provider == "azure":
            normalized.update(
                {
                    "email": userinfo.get("mail") or userinfo.get("userPrincipalName"),
                    "name": userinfo.get("displayName"),
                    "picture": None,  # Azure doesn't provide picture in basic scope
                    "email_verified": True,  # Azure AD emails are verified
                    "sub": userinfo.get("id"),  # Unique identifier
                }
            )

        elif self.provider == "okta" or self.provider == "auth0":
            normalized.update(
                {
                    "email": userinfo.get("email"),
                    "name": userinfo.get("name"),
                    "picture": userinfo.get("picture"),
                    "email_verified": userinfo.get("email_verified", False),
                    "sub": userinfo.get("sub"),  # Unique identifier
                }
            )

        return normalized

    def refresh_token(self, refresh_token: str) -> Optional[Dict]:
        """Refresh OAuth token."""
        if not self.client_id or not self.client_secret:
            logger.error(f"OAuth provider {self.provider} not configured properly")
            return None

        client = OAuth2Session(client_id=self.client_id, redirect_uri=self.redirect_uri)

        try:
            token = client.refresh_token(
                self.config["token_url"], refresh_token=refresh_token, client_secret=self.client_secret
            )

            # Update token in session
            st.session_state["oauth_token"] = token
            st.session_state["oauth_token_expiry"] = datetime.utcnow() + timedelta(
                seconds=token.get("expires_in", 3600)
            )

            logger.info("OAuth token refreshed successfully")
            return token

        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return None

    def revoke_token(self, token: str) -> bool:
        """Revoke OAuth token."""
        # Implementation varies by provider
        # Some providers don't support token revocation

        revoke_urls = {
            "google": "https://oauth2.googleapis.com/revoke",
            "azure": None,  # Azure doesn't have a revoke endpoint
            "okta": f"{os.getenv('OKTA_DOMAIN')}/oauth2/v1/revoke",
            "auth0": f"{os.getenv('AUTH0_DOMAIN')}/oauth/revoke",
        }

        revoke_url = revoke_urls.get(self.provider)
        if not revoke_url:
            logger.info(f"Token revocation not supported for provider: {self.provider}")
            return False

        try:
            import requests

            if self.provider == "google":
                response = requests.post(revoke_url, params={"token": token})
            else:
                response = requests.post(
                    revoke_url,
                    data={"token": token, "client_id": self.client_id, "client_secret": self.client_secret},
                )

            if response.status_code == 200:
                logger.info("OAuth token revoked successfully")
                return True
            logger.error(f"Failed to revoke token: {response.text}")
            return False

        except Exception as e:
            logger.error(f"Token revocation error: {e}")
            return False

    @staticmethod
    def is_token_expired() -> bool:
        """Check if the OAuth token is expired."""
        expiry = st.session_state.get("oauth_token_expiry")
        if not expiry:
            return True

        return datetime.utcnow() >= expiry

    @staticmethod
    def get_current_token() -> Optional[Dict]:
        """Get current OAuth token from session."""
        return st.session_state.get("oauth_token")


class OAuthManager:
    """Manage multiple OAuth providers."""

    def __init__(self):
        """Initialize OAuth manager."""
        self.providers = {}
        self._load_configured_providers()

    def _load_configured_providers(self):
        """Load all configured OAuth providers."""
        # Check which providers are configured
        provider_checks = {
            "google": "GOOGLE_CLIENT_ID",
            "azure": "AZURE_CLIENT_ID",
            "okta": "OKTA_CLIENT_ID",
            "auth0": "AUTH0_CLIENT_ID",
        }

        for provider, env_var in provider_checks.items():
            if os.getenv(env_var):
                try:
                    self.providers[provider] = OAuthProvider(provider)
                    logger.info(f"OAuth provider {provider} configured successfully")
                except Exception as e:
                    logger.error(f"Failed to configure OAuth provider {provider}: {e}")

    def get_provider(self, provider: str) -> Optional[OAuthProvider]:
        """Get a specific OAuth provider."""
        return self.providers.get(provider)

    def get_available_providers(self) -> list[str]:
        """Get list of available OAuth providers."""
        return list(self.providers.keys())

    def handle_oauth_callback(self) -> Optional[Dict]:
        """Handle OAuth callback from any provider."""
        # Check if we're handling a callback
        query_params = st.experimental_get_query_params()

        if "code" in query_params and "state" in query_params:
            code = query_params["code"][0]
            state = query_params["state"][0]

            # Get the provider from session
            provider_name = st.session_state.get("oauth_provider")
            if not provider_name:
                logger.error("No OAuth provider in session during callback")
                return None

            provider = self.get_provider(provider_name)
            if not provider:
                logger.error(f"OAuth provider {provider_name} not found")
                return None

            # Handle the callback
            userinfo = provider.handle_callback(code, state)

            # Clear query parameters
            st.experimental_set_query_params()

            return userinfo

        return None
