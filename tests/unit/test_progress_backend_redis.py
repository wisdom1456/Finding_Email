"""Tests for RedisProgressBackend with mocked redis."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Create a mock aioredis.Redis instance."""
    redis_mock = AsyncMock()
    redis_mock.publish = AsyncMock()
    redis_mock.hset = AsyncMock()
    redis_mock.hget = AsyncMock(return_value=None)

    pipe_mock = AsyncMock()
    pipe_mock.publish = MagicMock()
    pipe_mock.hset = MagicMock()
    pipe_mock.execute = AsyncMock()
    redis_mock.pipeline = MagicMock(return_value=pipe_mock)

    return redis_mock, pipe_mock


@pytest.mark.asyncio
async def test_redis_backend_publish(mock_redis):
    """Publish sends to Redis pub/sub and stores latest status."""
    redis_mock, pipe_mock = mock_redis

    with patch(
        "legal_portal.services.shared.progress_backend_redis.REDIS_ASYNC_AVAILABLE", True
    ), patch(
        "legal_portal.services.shared.progress_backend_redis.aioredis"
    ) as aioredis_mock:
        aioredis_mock.from_url.return_value = redis_mock

        from legal_portal.services.shared.progress_backend_redis import RedisProgressBackend

        backend = RedisProgressBackend.__new__(RedisProgressBackend)
        backend._redis_url = "redis://localhost:6379/1"
        backend._redis = redis_mock

        payload = json.dumps({"type": "progress", "message": "test"})
        await backend.publish("ch-1", payload)

        pipe_mock.publish.assert_called_once()
        pipe_mock.hset.assert_called_once()
        pipe_mock.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_backend_get_latest_status(mock_redis):
    """get_latest_status reads from Redis hash."""
    redis_mock, _ = mock_redis
    expected = {"type": "progress", "message": "latest"}
    redis_mock.hget.return_value = json.dumps(expected)

    with patch(
        "legal_portal.services.shared.progress_backend_redis.REDIS_ASYNC_AVAILABLE", True
    ), patch(
        "legal_portal.services.shared.progress_backend_redis.aioredis"
    ) as aioredis_mock:
        aioredis_mock.from_url.return_value = redis_mock

        from legal_portal.services.shared.progress_backend_redis import RedisProgressBackend

        backend = RedisProgressBackend.__new__(RedisProgressBackend)
        backend._redis = redis_mock

        result = await backend.get_latest_status("ch-1")
        assert result == expected


@pytest.mark.asyncio
async def test_redis_backend_create_channel_noop(mock_redis):
    """create_channel is a no-op for Redis."""
    redis_mock, _ = mock_redis

    with patch(
        "legal_portal.services.shared.progress_backend_redis.REDIS_ASYNC_AVAILABLE", True
    ), patch(
        "legal_portal.services.shared.progress_backend_redis.aioredis"
    ) as aioredis_mock:
        aioredis_mock.from_url.return_value = redis_mock

        from legal_portal.services.shared.progress_backend_redis import RedisProgressBackend

        backend = RedisProgressBackend.__new__(RedisProgressBackend)
        backend._redis = redis_mock

        cid = await backend.create_channel("ch-test")
        assert cid == "ch-test"


def test_redis_backend_requires_redis_package():
    """RedisProgressBackend raises if redis[asyncio] is not installed."""
    with patch(
        "legal_portal.services.shared.progress_backend_redis.REDIS_ASYNC_AVAILABLE", False
    ):
        from legal_portal.services.shared.progress_backend_redis import RedisProgressBackend

        with pytest.raises(RuntimeError, match="redis"):
            RedisProgressBackend("redis://localhost:6379/1")
