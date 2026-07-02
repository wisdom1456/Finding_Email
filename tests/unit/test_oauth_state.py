"""Tests for the HMAC-signed OAuth state parameter."""

import time

import pytest

from legal_portal.utils.oauth_state import (
    OAuthStateError,
    generate_oauth_state,
    verify_oauth_state,
)

USER_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def _state_secret(monkeypatch):
    monkeypatch.setenv("OAUTH_STATE_SECRET", "test-secret-for-oauth-state")


class TestOAuthState:
    def test_round_trip(self):
        state = generate_oauth_state(USER_ID)
        assert verify_oauth_state(state) == USER_ID

    def test_states_are_unique(self):
        assert generate_oauth_state(USER_ID) != generate_oauth_state(USER_ID)

    def test_legacy_unsigned_state_rejected(self):
        with pytest.raises(OAuthStateError):
            verify_oauth_state(f"user:{USER_ID}")

    def test_tampered_user_id_rejected(self):
        state = generate_oauth_state(USER_ID)
        nonce, expiry, _uid, sig = state.split(":")
        forged = f"{nonce}:{expiry}:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee:{sig}"
        with pytest.raises(OAuthStateError):
            verify_oauth_state(forged)

    def test_tampered_signature_rejected(self):
        state = generate_oauth_state(USER_ID)
        with pytest.raises(OAuthStateError):
            verify_oauth_state(state[:-4] + "0000")

    def test_expired_state_rejected(self, monkeypatch):
        state = generate_oauth_state(USER_ID)
        monkeypatch.setattr(time, "time", lambda: time.gmtime and 9999999999)
        with pytest.raises(OAuthStateError, match="expired"):
            verify_oauth_state(state)

    def test_wrong_secret_rejected(self, monkeypatch):
        state = generate_oauth_state(USER_ID)
        monkeypatch.setenv("OAUTH_STATE_SECRET", "a-different-secret")
        with pytest.raises(OAuthStateError):
            verify_oauth_state(state)

    def test_fallback_to_service_key(self, monkeypatch):
        monkeypatch.delenv("OAUTH_STATE_SECRET", raising=False)
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fallback-secret")
        state = generate_oauth_state(USER_ID)
        assert verify_oauth_state(state) == USER_ID

    def test_no_secret_fails_closed(self, monkeypatch):
        monkeypatch.delenv("OAUTH_STATE_SECRET", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        with pytest.raises(OAuthStateError):
            generate_oauth_state(USER_ID)

    def test_malformed_state_rejected(self):
        for bad in ("", "abc", "a:b:c", "a:b:c:d:e"):
            with pytest.raises(OAuthStateError):
                verify_oauth_state(bad)