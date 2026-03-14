"""Tests for document grouping feature flag behavior."""
from unittest.mock import patch, MagicMock


def test_grouping_disabled_by_default():
    """When enable_group_detection is False (default), no grouping runs."""
    from legal_portal.config.default import get_settings
    settings = get_settings()
    # Default should be False
    assert settings.enable_group_detection is False
