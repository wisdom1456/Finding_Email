"""FastAPI dependencies for the Legal Document Analysis Portal.

This module provides dependency injection functions for:
- Supabase client
- Authentication
- Database sessions
"""

import logging
import os
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from supabase import Client, create_client

logger = logging.getLogger(__name__)
security = HTTPBearer()
# Separate instance for optional auth: auto_error=False allows unauthenticated requests through
optional_security = HTTPBearer(auto_error=False)


@lru_cache()
def get_supabase_client() -> Client:
    """Get Supabase client instance (cached) with Service Role Key.
    Use this for admin tasks or reading user data during auth validation.

    Returns
    -------
        Supabase client

    Raises
    ------
        ValueError: If required environment variables are missing

    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variable")

    return create_client(supabase_url, supabase_key)


def get_user_supabase_client(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Client:
    """Get Supabase client authenticated as the current user.
    This ensures RLS policies work correctly because auth.uid() will be set.

    Args:
    ----
        credentials: HTTP Bearer token

    Returns:
    -------
        Supabase client authenticated as user

    Raises:
    ------
        ValueError: If required environment variables are missing

    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")

    logger.debug(
        "Creating user-authenticated Supabase client",
        extra={
            "has_url": bool(supabase_url),
            "has_key": bool(supabase_key),
            "token_prefix": credentials.credentials[:20] if credentials else None,
        },
    )

    if not supabase_url or not supabase_key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_ANON_KEY environment variable")

    # Create a fresh client for this request
    # We don't cache this because it holds user-specific auth state
    client = create_client(supabase_url, supabase_key)

    # Authenticate with the user's token
    # This sets the 'Authorization: Bearer <token>' header for PostgREST
    client.postgrest.auth(credentials.credentials)

    # Explicitly set the header to ensure it overrides the API key
    # This fixes an issue where .auth() might not override the key-based header in some versions
    client.postgrest.session.headers["Authorization"] = f"Bearer {credentials.credentials}"

    return client


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    supabase: Client = Depends(get_user_supabase_client),
) -> dict:
    """Verify JWT token and get current user.

    Args:
    ----
        credentials: HTTP Bearer token from Authorization header
        supabase: Supabase client

    Returns:
    -------
        User dict with 'id', 'email', etc.

    Raises:
    ------
        HTTPException: If token is invalid or user not found

    """
    try:
        # Verify the JWT token with Supabase
        # Note: get_user is synchronous in supabase-py v2
        response = supabase.auth.get_user(credentials.credentials)

        # The response has a 'user' attribute
        if not response or not response.user:
            logger.warning("Authentication failed: Invalid token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Return user as dict for easier access
        user = response.user
        return {
            "id": user.id,
            "email": user.email,
            "user_metadata": user.user_metadata,
            "app_metadata": user.app_metadata,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
) -> Optional[dict]:
    """Get current user if authenticated, otherwise None.

    Uses optional_security (auto_error=False) so unauthenticated requests
    pass through instead of getting a 403.

    Args:
    ----
        credentials: Optional HTTP Bearer token (None when unauthenticated)

    Returns:
    -------
        User dict or None

    """
    if not credentials:
        return None

    try:
        # Build a user-scoped supabase client manually for the token
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_ANON_KEY")
        if not supabase_url or not supabase_key:
            return None

        client = create_client(supabase_url, supabase_key)
        client.postgrest.auth(credentials.credentials)
        client.postgrest.session.headers["Authorization"] = f"Bearer {credentials.credentials}"

        response = client.auth.get_user(credentials.credentials)
        if not response or not response.user:
            return None

        user = response.user
        return {
            "id": user.id,
            "email": user.email,
            "user_metadata": user.user_metadata,
            "app_metadata": user.app_metadata,
        }
    except Exception:
        return None
