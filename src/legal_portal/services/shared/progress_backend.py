"""Abstract base class for progress stream backends.

Defines the interface that InMemoryProgressBackend and RedisProgressBackend
must implement. ProgressManager delegates all storage/pub-sub operations
to the active backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class ProgressBackend(ABC):
    """Abstract backend for progress channel storage and pub/sub."""

    @abstractmethod
    async def create_channel(self, channel_id: str) -> str:
        """Create or ensure a progress channel exists. Return channel_id."""

    @abstractmethod
    async def publish(self, channel_id: str, payload_json: str) -> None:
        """Publish a JSON-encoded progress payload to a channel."""

    @abstractmethod
    async def subscribe(self, channel_id: str) -> AsyncGenerator[str, None]:
        """Yield JSON-encoded messages from a channel until terminal status."""

    @abstractmethod
    async def get_latest_status(self, channel_id: str) -> Optional[dict]:
        """Return the most recently published payload for a channel, or None."""

    @abstractmethod
    def cleanup_expired_channels(self, max_age_hours: int = 1) -> None:
        """Remove channels with no activity for longer than max_age_hours."""
