"""In-memory progress backend using asyncio.Queue.

Extracted from the original ProgressManager implementation.
Suitable for single-process deployments.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import AsyncGenerator, Optional

from legal_portal.services.shared.progress_backend import ProgressBackend

logger = logging.getLogger(__name__)


class InMemoryProgressBackend(ProgressBackend):
    """Progress backend backed by per-channel asyncio.Queue instances."""

    def __init__(self):
        self._channels: dict[str, asyncio.Queue] = {}
        self._last_activity: dict[str, datetime] = {}
        self._latest_status: dict[str, dict] = {}

    async def create_channel(self, channel_id: str) -> str:
        if channel_id not in self._channels:
            self._channels[channel_id] = asyncio.Queue()
            self._last_activity[channel_id] = datetime.now()
            logger.info(f"Created progress channel: {channel_id}")
        return channel_id

    async def publish(self, channel_id: str, payload_json: str) -> None:
        if channel_id not in self._channels:
            await self.create_channel(channel_id)

        try:
            await self._channels[channel_id].put(payload_json)
            self._last_activity[channel_id] = datetime.now()
            self._latest_status[channel_id] = json.loads(payload_json)
            logger.debug(f"Published progress to channel {channel_id}")
        except Exception as e:
            logger.error(f"Failed to publish progress to channel {channel_id}: {e}")

    async def subscribe(self, channel_id: str) -> AsyncGenerator[str, None]:
        if channel_id not in self._channels:
            logger.info(f"Creating new channel for subscriber: {channel_id}")
            await self.create_channel(channel_id)

        queue = self._channels[channel_id]
        queue_size = queue.qsize()
        logger.info(f"Client subscribed to channel: {channel_id} (queue has {queue_size} pending messages)")

        try:
            while True:
                try:
                    data_json = await asyncio.wait_for(queue.get(), timeout=15.0)

                    yield data_json

                    msg_dict = json.loads(data_json)
                    if msg_dict.get("type") in ["completed", "failed", "error"]:
                        logger.info(f"Stream {channel_id} completed/failed. Closing connection.")
                        break

                except asyncio.TimeoutError:
                    if datetime.now() - self._last_activity.get(channel_id, datetime.min) > timedelta(
                        hours=1
                    ):
                        logger.warning(f"Channel {channel_id} timed out")
                        break

        except Exception as e:
            logger.error(f"Subscription error for {channel_id}: {e}")

    async def get_latest_status(self, channel_id: str) -> Optional[dict]:
        if channel_id in self._latest_status:
            return self._latest_status[channel_id]
        return None

    def cleanup_expired_channels(self, max_age_hours: int = 1) -> None:
        now = datetime.now()
        expired = []
        for cid, last_active in self._last_activity.items():
            if now - last_active > timedelta(hours=max_age_hours):
                expired.append(cid)

        for cid in expired:
            del self._channels[cid]
            del self._last_activity[cid]
            if cid in self._latest_status:
                del self._latest_status[cid]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired progress channels")
