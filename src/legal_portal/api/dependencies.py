"""FastAPI dependencies for the Legal Document Analysis Portal.

This module provides dependency injection functions for:
- Supabase client
- Authentication
- Database sessions
"""

import os
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from supabase import create_client

security = HTTPBearer()


@lru_cache()
def get_supabase_client():
    """Get Supabase client instance (cached) with Service Role Key.
    Use this for admin tasks or reading user data during auth validation.

    Returns
    -------
        Supabase client
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variable")

    return create_client(supabase_url, supabase_key)


def get_user_supabase_client(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get Supabase client authenticated as the current user.
    This ensures RLS policies work correctly because auth.uid() will be set.

    Args:
    ----
        credentials: HTTP Bearer token

    Returns:
    -------
        Supabase client authenticated as user
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")

    print("🔍 DEBUG get_user_supabase_client:")
    print(f"  - SUPABASE_URL: {supabase_url[:40]}..." if supabase_url else "  - SUPABASE_URL: None")
    print(
        f"  - SUPABASE_ANON_KEY: {'SET (len=' + str(len(supabase_key)) + ')' if supabase_key else 'NOT SET'}"
    )
    print(f"  - User Token (first 20 chars): {credentials.credentials[:20]}...")

    if not supabase_url or not supabase_key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_ANON_KEY environment variable")

    # Create a fresh client for this request
    # We don't cache this because it holds user-specific auth state
    client = create_client(supabase_url, supabase_key)

    print("  - Client created with anon key")

    # Authenticate with the user's token
    # This sets the 'Authorization: Bearer <token>' header for PostgREST
    client.postgrest.auth(credentials.credentials)

    print("  - Called client.postgrest.auth()")

    # Explicitly set the header to ensure it overrides the API key
    # This fixes an issue where .auth() might not override the key-based header in some versions
    client.postgrest.session.headers["Authorization"] = f"Bearer {credentials.credentials}"

    print("  - Explicitly set Authorization header")
    print(f"  - Final headers: {dict(client.postgrest.session.headers)}")

    return client


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security), supabase=Depends(get_supabase_client)
):
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
        response = supabase.auth.get_user(credentials.credentials)

        # The response has a 'user' attribute
        if not response or not response.user:
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    supabase=Depends(get_supabase_client),
):
    """Get current user if authenticated, otherwise None.

    Args:
    ----
        credentials: Optional HTTP Bearer token
        supabase: Supabase client

    Returns:
    -------
        User object or None
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, supabase)
    except HTTPException:
        return None
