"""Redis-backed progress backend using pub/sub + hash for latest status.

Requires ``redis[asyncio]>=5.0.0``. If Redis is unavailable at init time
an exception is raised so the caller can fall back to the in-memory backend.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from legal_portal.services.shared.progress_backend import ProgressBackend

logger = logging.getLogger(__name__)

# redis.asyncio (merged into redis-py >= 5.0)
try:
    import redis.asyncio as aioredis

    REDIS_ASYNC_AVAILABLE = True
except ImportError:
    aioredis = None  # type: ignore[assignment]
    REDIS_ASYNC_AVAILABLE = False


class RedisProgressBackend(ProgressBackend):
    """Progress backend using Redis pub/sub and hash storage."""

    _LATEST_STATUS_KEY = "progress:latest"
    _CHANNEL_PREFIX = "progress:channel:"

    def __init__(self, redis_url: str = "redis://localhost:6379/1"):
        if not REDIS_ASYNC_AVAILABLE:
            raise RuntimeError("redis[asyncio] package is required for RedisProgressBackend")

        self._redis_url = redis_url
        self._redis: aioredis.Redis = aioredis.from_url(  # type: ignore[union-attr]
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        logger.info("Redis progress backend initialized (url=%s)", redis_url)

    def _channel_key(self, channel_id: str) -> str:
        return f"{self._CHANNEL_PREFIX}{channel_id}"

    async def create_channel(self, channel_id: str) -> str:
        # Redis pub/sub doesn't need pre-creation — no-op.
        return channel_id

    async def publish(self, channel_id: str, payload_json: str) -> None:
        try:
            pipe = self._redis.pipeline()
            pipe.publish(self._channel_key(channel_id), payload_json)
            pipe.hset(self._LATEST_STATUS_KEY, channel_id, payload_json)
            await pipe.execute()
        except Exception as e:
            logger.error(f"Redis publish failed for {channel_id}: {e}")

    async def subscribe(self, channel_id: str) -> AsyncGenerator[str, None]:
        pubsub = self._redis.pubsub()
        channel_key = self._channel_key(channel_id)

        try:
            await pubsub.subscribe(channel_key)
            logger.info(f"Redis subscriber attached to {channel_key}")

            while True:
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0),
                        timeout=20.0,
                    )
                except asyncio.TimeoutError:
                    message = None

                if message is None:
                    continue

                data = message.get("data")
                if not isinstance(data, str):
                    continue

                yield data

                try:
                    msg_dict = json.loads(data)
                    if msg_dict.get("type") in ["completed", "failed", "error"]:
                        logger.info(f"Redis stream {channel_id} completed/failed. Closing.")
                        break
                except (json.JSONDecodeError, AttributeError):
                    pass

        except Exception as e:
            logger.error(f"Redis subscription error for {channel_id}: {e}")
        finally:
            try:
                await pubsub.unsubscribe(channel_key)
                await pubsub.close()
            except Exception:
                pass

    async def get_latest_status(self, channel_id: str) -> Optional[dict]:
        try:
            raw = await self._redis.hget(self._LATEST_STATUS_KEY, channel_id)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.debug(f"Redis get_latest_status failed for {channel_id}: {e}")
        return None

    def cleanup_expired_channels(self, max_age_hours: int = 1) -> None:
        # Redis entries are cleaned via TTL or periodic sweeps.
        # For now, this is a no-op — the in-memory backend handles local cleanup.
        pass
