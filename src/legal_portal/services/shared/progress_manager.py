"""ProgressManager — thin facade over a pluggable ProgressBackend.

Builds structured JSON payloads and delegates storage/pub-sub to the
active backend.  Default backend: InMemoryProgressBackend (preserves
pre-refactor single-process behavior).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import Request

from legal_portal.services.shared.progress_backend import ProgressBackend

logger = logging.getLogger(__name__)


class ProgressManager:
    """Manages progress streams for different tasks using pub/sub pattern.

    Delegates channel management, publishing, and subscription to a
    ProgressBackend instance. Convenience methods (publish_stage,
    publish_document, etc.) stay here because they build domain-specific
    payloads before delegating.
    """

    def __init__(self, backend: Optional[ProgressBackend] = None):
        if backend is None:
            from legal_portal.services.shared.progress_backend_memory import InMemoryProgressBackend

            backend = InMemoryProgressBackend()
        self._backend = backend

    async def create_channel(self, channel_id: str) -> str:
        """Create a new progress channel."""
        return await self._backend.create_channel(channel_id)

    async def publish_progress(
        self,
        channel_id: str,
        message: str,
        phase: str = "",
        percent: int = 0,
        docs_processed: list = None,
        current_doc: dict = None,
        sub_step: str = None,
        status: str = "progress",
        error: str = None,
        data: dict = None,
        **kwargs,
    ):
        """Publish a progress event to a channel."""
        payload = {
            "type": status,
            "message": message,
            "phase": phase,
            "percent": percent,
            "docs_processed": docs_processed or [],
            "current_doc": current_doc,
            "sub_step": sub_step,
            "timestamp": kwargs.get("timestamp", datetime.now().isoformat()),
            "data": data,
        }

        # Add any extra kwargs to payload (like stage, document, stats)
        for key, value in kwargs.items():
            if key not in payload and key != "timestamp":
                payload[key] = value

        if error:
            payload["error"] = error

        payload_json = json.dumps(payload)
        await self._backend.publish(channel_id, payload_json)

    async def publish_finalizing(self, channel_id: str, message: str, percent: int):
        """Emit a finalization-tail progress update (legacy/SSE path).

        Mirrors DBProgressManager.publish_finalizing: no cancellation coupling,
        so the orchestrator can report the 92/95/98 save steps after the
        point of no return without risking an abort mid-persistence.
        """
        await self.publish_progress(
            channel_id=channel_id,
            message=message,
            phase="finalizing",
            percent=percent,
        )

    async def publish_stage(self, channel_id: str, stage: dict):
        """Publish a stage progress update."""
        await self.publish_progress(
            channel_id=channel_id,
            message=f"Stage: {stage.get('name', 'Unknown')}",
            status="stage",
            stage=stage,
        )

    async def publish_document(self, channel_id: str, document: dict):
        """Publish a document progress update."""
        await self.publish_progress(
            channel_id=channel_id,
            message=f"Document: {document.get('name', 'Unknown')}",
            status="document",
            document=document,
        )

    async def publish_stats(self, channel_id: str, stats: dict):
        """Publish stats update."""
        await self.publish_progress(
            channel_id=channel_id,
            message="Stats update",
            status="stats",
            stats=stats,
        )

    async def publish_token(self, channel_id: str, token: str, stream_id: str):
        """Publish a streaming token."""
        await self.publish_progress(
            channel_id=channel_id,
            message="",
            status="stream",
            token=token,
            stream_id=stream_id,
        )

    async def subscribe(self, channel_id: str) -> AsyncGenerator[str, None]:
        """Subscribe to progress updates for a channel."""
        async for data_json in self._backend.subscribe(channel_id):
            yield data_json

    async def get_latest_status(self, channel_id: str) -> dict | None:
        """Get the latest progress status for a channel (for polling)."""
        return await self._backend.get_latest_status(channel_id)

    def cleanup_expired_channels(self, max_age_hours: int = 1):
        """Remove channels that haven't had activity."""
        self._backend.cleanup_expired_channels(max_age_hours)


# Dependency for FastAPI
def get_progress_manager(request: "Request") -> ProgressManager:
    """Get the ProgressManager from app.state for FastAPI dependency injection."""
    return request.app.state.progress_manager
