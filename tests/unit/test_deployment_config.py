"""Deployment configuration consistency tests.

Catches mismatches between Vercel config files and ensures no endpoint
can silently exceed the platform's function execution limit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Project root — tests/ is one level below
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(relative_path: str) -> dict:
    path = PROJECT_ROOT / relative_path
    assert path.exists(), f"Config file not found: {path}"
    return json.loads(path.read_text())


def _get_vercel_max_duration() -> int:
    """Return maxDuration from vercel.json for the main API function."""
    config = _load_json("vercel.json")
    functions = config.get("functions", {})
    # The API entry point
    api_config = functions.get("api/index.py", {})
    return api_config.get("maxDuration", 60)  # Vercel default is 60


def _get_vc_config_max_duration() -> int:
    """Return maxDuration from api/.vc-config.json (runtime override)."""
    config = _load_json("api/.vc-config.json")
    return config.get("maxDuration", 60)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDeploymentConfigConsistency:
    """Verify deployment config files agree on critical values."""

    def test_vc_config_matches_vercel_json_max_duration(self):
        """The .vc-config.json maxDuration must match vercel.json.

        A mismatch here caused production outages (2026-03-16) where
        .vc-config.json had 60s while vercel.json had 800s, causing
        Vercel to silently kill functions after 60s mid-stream.
        """
        vercel_duration = _get_vercel_max_duration()
        vc_config_duration = _get_vc_config_max_duration()

        assert vc_config_duration == vercel_duration, (
            f"maxDuration mismatch: api/.vc-config.json={vc_config_duration}s "
            f"vs vercel.json={vercel_duration}s. "
            f"The .vc-config.json value overrides vercel.json at runtime."
        )

    def test_max_duration_sufficient_for_letter_generation(self):
        """The platform maxDuration must exceed the letter generation budget."""
        from legal_portal.config.default import Settings

        # Build settings with only the required field so we don't need .env
        settings = Settings(openai_api_key="sk-test-placeholder-key")
        platform_limit = _get_vc_config_max_duration()

        assert platform_limit > settings.letter_internal_budget_seconds, (
            f"Platform maxDuration ({platform_limit}s) must exceed "
            f"letter_internal_budget_seconds ({settings.letter_internal_budget_seconds}s). "
            f"Non-streaming /generate-letter runs for the full budget."
        )

    def test_max_duration_sufficient_for_streaming_analysis(self):
        """The platform maxDuration must allow streaming analysis to complete.

        Streaming analysis with GPT-5.4 reasoning_effort=medium typically
        takes 60-120s. Allow at least 300s headroom.
        """
        platform_limit = _get_vc_config_max_duration()
        min_required = 300  # Conservative floor for streaming analysis

        assert platform_limit >= min_required, (
            f"Platform maxDuration ({platform_limit}s) is too low for "
            f"streaming analysis (needs >= {min_required}s)."
        )

    def test_ghostscript_timeout_within_platform_limit(self):
        """Ghostscript subprocess timeout must not exceed platform limit.

        file_compression_service.py runs Ghostscript with timeout=300s
        synchronously. If this exceeds maxDuration, the function dies
        before the subprocess can even timeout gracefully.
        """
        platform_limit = _get_vc_config_max_duration()
        ghostscript_timeout = 300  # Hardcoded in file_compression_service.py

        assert platform_limit > ghostscript_timeout, (
            f"Platform maxDuration ({platform_limit}s) must exceed "
            f"Ghostscript subprocess timeout ({ghostscript_timeout}s). "
            f"Otherwise the function is killed before Ghostscript can timeout."
        )

    def test_max_duration_sufficient_for_gap_analysis(self):
        """The platform maxDuration must exceed the gap analysis budget.

        Gap analysis AI calls use asyncio.wait_for with this budget.
        If the platform kills the function first, the timeout is useless.
        """
        from legal_portal.config.default import Settings

        settings = Settings(openai_api_key="sk-test-placeholder-key")
        platform_limit = _get_vc_config_max_duration()

        assert platform_limit > settings.gap_analysis_budget_seconds, (
            f"Platform maxDuration ({platform_limit}s) must exceed "
            f"gap_analysis_budget_seconds ({settings.gap_analysis_budget_seconds}s). "
            f"Otherwise Vercel kills the function before the AI call can timeout."
        )
