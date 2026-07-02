"""Tests for InMemoryProgressBackend — direct backend tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from legal_portal.services.shared.progress_backend_memory import InMemoryProgressBackend


@pytest.mark.asyncio
async def test_create_channel():
    backend = InMemoryProgressBackend()
    cid = await backend.create_channel("ch-1")
    assert cid == "ch-1"
    assert "ch-1" in backend._channels


@pytest.mark.asyncio
async def test_create_channel_idempotent():
    backend = InMemoryProgressBackend()
    await backend.create_channel("ch-dup")
    queue_ref = backend._channels["ch-dup"]
    await backend.create_channel("ch-dup")
    assert backend._channels["ch-dup"] is queue_ref


@pytest.mark.asyncio
async def test_publish_creates_channel_implicitly():
    backend = InMemoryProgressBackend()
    payload = json.dumps({"type": "progress", "message": "hello"})
    await backend.publish("auto-ch", payload)
    assert "auto-ch" in backend._channels


@pytest.mark.asyncio
async def test_publish_stores_latest_status():
    backend = InMemoryProgressBackend()
    await backend.create_channel("ch-status")
    payload = json.dumps({"type": "progress", "message": "step1", "percent": 42})
    await backend.publish("ch-status", payload)
    latest = await backend.get_latest_status("ch-status")
    assert latest["message"] == "step1"
    assert latest["percent"] == 42


@pytest.mark.asyncio
async def test_subscribe_yields_and_stops_on_terminal():
    backend = InMemoryProgressBackend()
    await backend.create_channel("ch-sub")

    await backend.publish("ch-sub", json.dumps({"type": "progress", "message": "msg-1"}))
    await backend.publish("ch-sub", json.dumps({"type": "completed", "message": "done"}))

    received = []
    async for data_json in backend.subscribe("ch-sub"):
        received.append(json.loads(data_json)["message"])

    assert received == ["msg-1", "done"]


@pytest.mark.asyncio
async def test_get_latest_status_none_for_unknown():
    backend = InMemoryProgressBackend()
    assert await backend.get_latest_status("unknown") is None


@pytest.mark.asyncio
async def test_cleanup_expired_channels():
    backend = InMemoryProgressBackend()
    await backend.create_channel("stale")
    await backend.create_channel("fresh")
    backend._last_activity["stale"] = datetime.now() - timedelta(hours=2)

    backend.cleanup_expired_channels(max_age_hours=1)

    assert "stale" not in backend._channels
    assert "fresh" in backend._channels
