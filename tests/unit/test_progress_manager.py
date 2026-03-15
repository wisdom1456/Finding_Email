"""Tests for ProgressManager pub/sub progress stream service."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from legal_portal.services.shared.progress_manager import ProgressManager


@pytest.mark.asyncio
async def test_create_channel():
    """Channel created with an asyncio.Queue."""
    pm = ProgressManager()
    channel_id = await pm.create_channel("ch-1")

    assert channel_id == "ch-1"
    assert "ch-1" in pm._channels
    assert isinstance(pm._channels["ch-1"], asyncio.Queue)
    assert "ch-1" in pm._last_activity


@pytest.mark.asyncio
async def test_create_channel_idempotent():
    """Second create on the same channel is a no-op (queue preserved)."""
    pm = ProgressManager()
    await pm.create_channel("ch-dup")
    queue_ref = pm._channels["ch-dup"]

    # Put a message to verify queue identity is preserved
    await queue_ref.put("marker")
    await pm.create_channel("ch-dup")

    assert pm._channels["ch-dup"] is queue_ref
    assert not pm._channels["ch-dup"].empty()


@pytest.mark.asyncio
async def test_publish_progress():
    """Message queued with correct payload structure."""
    pm = ProgressManager()
    await pm.create_channel("ch-pub")

    await pm.publish_progress(
        "ch-pub",
        message="Extracting documents",
        phase="extraction",
        percent=42,
        status="progress",
    )

    raw = await pm._channels["ch-pub"].get()
    payload = json.loads(raw)

    assert payload["type"] == "progress"
    assert payload["message"] == "Extracting documents"
    assert payload["phase"] == "extraction"
    assert payload["percent"] == 42
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_publish_to_nonexistent_creates_channel():
    """Publishing to a non-existent channel auto-creates it."""
    pm = ProgressManager()
    assert "new-ch" not in pm._channels

    await pm.publish_progress("new-ch", message="auto-created")

    assert "new-ch" in pm._channels
    raw = await pm._channels["new-ch"].get()
    payload = json.loads(raw)
    assert payload["message"] == "auto-created"


@pytest.mark.asyncio
async def test_subscribe_yields_messages():
    """Messages received in order via subscribe generator."""
    pm = ProgressManager()
    await pm.create_channel("ch-sub")

    # Pre-load messages
    await pm.publish_progress("ch-sub", message="msg-1", status="progress")
    await pm.publish_progress("ch-sub", message="msg-2", status="progress")
    await pm.publish_progress("ch-sub", message="done", status="completed")

    received = []
    async for data_json in pm.subscribe("ch-sub"):
        payload = json.loads(data_json)
        received.append(payload["message"])

    assert received == ["msg-1", "msg-2", "done"]


@pytest.mark.asyncio
async def test_subscribe_terminal_stops():
    """Stream stops when a terminal status (completed/failed/error) is received."""
    pm = ProgressManager()
    await pm.create_channel("ch-term")

    await pm.publish_progress("ch-term", message="working", status="progress")
    await pm.publish_progress("ch-term", message="oops", status="failed")
    # This message should NOT be received because the stream should stop
    await pm.publish_progress("ch-term", message="after-fail", status="progress")

    received = []
    async for data_json in pm.subscribe("ch-term"):
        payload = json.loads(data_json)
        received.append(payload["message"])

    assert "working" in received
    assert "oops" in received
    assert "after-fail" not in received


@pytest.mark.asyncio
async def test_get_latest_status():
    """Returns the most recently published payload."""
    pm = ProgressManager()
    await pm.create_channel("ch-latest")

    assert await pm.get_latest_status("ch-latest") is None

    await pm.publish_progress("ch-latest", message="first", percent=10)
    await pm.publish_progress("ch-latest", message="second", percent=50)

    latest = await pm.get_latest_status("ch-latest")
    assert latest is not None
    assert latest["message"] == "second"
    assert latest["percent"] == 50


@pytest.mark.asyncio
async def test_cleanup_expired_channels():
    """Stale channels are removed by cleanup."""
    pm = ProgressManager()
    await pm.create_channel("ch-stale")
    await pm.create_channel("ch-fresh")

    # Backdate stale channel
    pm._last_activity["ch-stale"] = datetime.now() - timedelta(hours=2)

    pm.cleanup_expired_channels(max_age_hours=1)

    assert "ch-stale" not in pm._channels
    assert "ch-stale" not in pm._last_activity
    assert "ch-fresh" in pm._channels
    assert "ch-fresh" in pm._last_activity
