"""HMAC-signed OAuth state parameter.

The Clio OAuth flow previously used ``state = f"user:{user_id}"`` — a
predictable value the callback trusted verbatim to decide whose account the
tokens attach to. That allows OAuth CSRF / account fixation: anyone who can
guess a user id can complete a flow that links tokens to that user.

This module issues a signed, expiring state:

    nonce : expiry_epoch : user_id : hmac_sha256(secret, payload)

and verifies it on callback with a constant-time comparison. The signing
secret is ``OAUTH_STATE_SECRET`` (provision via env); until that is set we
fall back to ``SUPABASE_SERVICE_KEY`` — already a high-entropy secret present
in every API environment — so the flow keeps working, with a warning nudging
provisioning of the dedicated secret.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from legal_portal.utils.logging_config import get_module_logger

logger = get_module_logger(__name__)

STATE_TTL_SECONDS = 600  # OAuth round-trip must complete within 10 minutes


class OAuthStateError(ValueError):
    """Raised when an OAuth state parameter fails verification."""


def _signing_secret() -> bytes:
    secret = os.getenv("OAUTH_STATE_SECRET")
    if secret:
        return secret.encode()
    fallback = os.getenv("SUPABASE_SERVICE_KEY")
    if fallback:
        logger.warning(
            "OAUTH_STATE_SECRET is not set; falling back to SUPABASE_SERVICE_KEY "
            "for OAuth state signing. Provision OAUTH_STATE_SECRET "
            "(openssl rand -base64 32)."
        )
        return fallback.encode()
    raise OAuthStateError(
        "No OAuth state signing secret available: set OAUTH_STATE_SECRET"
    )


def _sign(payload: str) -> str:
    return hmac.new(_signing_secret(), payload.encode(), hashlib.sha256).hexdigest()


def generate_oauth_state(user_id: str) -> str:
    """Create a signed, expiring state parameter bound to a user id."""
    nonce = secrets.token_urlsafe(16)
    expiry = int(time.time()) + STATE_TTL_SECONDS
    payload = f"{nonce}:{expiry}:{user_id}"
    return f"{payload}:{_sign(payload)}"


def verify_oauth_state(state: str) -> str:
    """Verify a state parameter and return the embedded user id.

    Raises:
    ------
        OAuthStateError: on malformed, tampered, or expired state.

    """
    parts = state.split(":")
    if len(parts) != 4:
        raise OAuthStateError("Malformed OAuth state")

    nonce, expiry_str, user_id, signature = parts
    payload = f"{nonce}:{expiry_str}:{user_id}"

    if not hmac.compare_digest(_sign(payload), signature):
        raise OAuthStateError("OAuth state signature mismatch")

    try:
        expiry = int(expiry_str)
    except ValueError as e:
        raise OAuthStateError("Malformed OAuth state expiry") from e

    if time.time() > expiry:
        raise OAuthStateError("OAuth state expired")

    return user_id
