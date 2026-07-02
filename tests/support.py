"""Shared test helpers for capability gating.

Lets tests that need live external services skip cleanly under CI's mocked
environment instead of failing red. CI sets CI_MOCK_SERVICES=true alongside
validation-passing placeholder credentials; a red build then means a real
regression, not missing infrastructure.
"""

from __future__ import annotations

import os


def real_openai_available() -> bool:
    """True only when a usable (non-placeholder) OpenAI key is present.

    Returns False under CI_MOCK_SERVICES or when the key looks like a
    placeholder, so embedding/completion tests requiring the real API skip
    rather than fail.
    """
    if os.getenv("CI_MOCK_SERVICES"):
        return False
    key = os.getenv("OPENAI_API_KEY", "")
    return key.startswith("sk-") and "mock" not in key and "placeholder" not in key
