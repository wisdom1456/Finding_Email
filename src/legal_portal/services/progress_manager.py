import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class ProgressManager:
    """Manages progress streams for different tasks using pub/sub pattern.

    Uses asyncio.Queue for single-process deployments.
    """

    _instance = None

    def __new__(cls):
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super(ProgressManager, cls).__new__(cls)
            cls._instance._channels = {}  # type: Dict[str, asyncio.Queue]
            cls._instance._last_activity = {}  # type: Dict[str, datetime]
            cls._instance._latest_status = {}  # type: Dict[str, dict] - Store latest status for polling
        return cls._instance

    def __init__(self):
        # Initialized in __new__ to ensure singleton behavior
        pass

    @classmethod
    def get_instance(cls):
        """Get the singleton instance of the progress manager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def create_channel(self, channel_id: str) -> str:
        """Create a new progress channel."""
        if channel_id not in self._channels:
            self._channels[channel_id] = asyncio.Queue()
            self._last_activity[channel_id] = datetime.now()
            logger.info(f"Created progress channel: {channel_id}")
        return channel_id

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
        # #region agent log
        _DEBUG_LOG_PATH = "/tmp/cursor_debug.log" if __import__('os').getenv("VERCEL") else "/Users/BRFlorida/Projects/Work/Finding_Emails/.cursor/debug.log"
        def _dbg_log(hyp: str, msg: str, data: dict = None):
            try:
                import json as _j; import time as _t; open(_DEBUG_LOG_PATH, "a").write(_j.dumps({"hypothesisId": hyp, "location": "progress_manager.py:publish_progress", "message": msg, "data": data or {}, "timestamp": _t.time(), "sessionId": "debug-session"}) + "\n")
            except: pass
        _dbg_log("H1,H4", "publish_progress called", {"channel_id": channel_id, "phase": phase, "percent": percent, "channel_exists": channel_id in self._channels})
        # #endregion agent log

        if channel_id not in self._channels:
            logger.warning(f"Attempted to publish to non-existent channel: {channel_id}")
            # Create it implicitly if it doesn't exist (for race conditions where task starts before listener)
            await self.create_channel(channel_id)

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

        try:
            await self._channels[channel_id].put(json.dumps(payload))
            self._last_activity[channel_id] = datetime.now()
            # Store latest status for polling fallback
            self._latest_status[channel_id] = payload
            logger.debug(f"Published progress to channel {channel_id}: {message} ({percent}%)")
        except Exception as e:
            logger.error(f"Failed to publish progress to channel {channel_id}: {e}")

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
        # #region agent log
        _DEBUG_LOG_PATH = "/tmp/cursor_debug.log" if __import__('os').getenv("VERCEL") else "/Users/BRFlorida/Projects/Work/Finding_Emails/.cursor/debug.log"
        def _dbg_log(hyp: str, msg: str, data: dict = None):
            try:
                import json as _j; import time as _t; open(_DEBUG_LOG_PATH, "a").write(_j.dumps({"hypothesisId": hyp, "location": "progress_manager.py:subscribe", "message": msg, "data": data or {}, "timestamp": _t.time(), "sessionId": "debug-session"}) + "\n")
            except: pass
        _dbg_log("H1,H3", "subscribe called", {"channel_id": channel_id, "channel_exists": channel_id in self._channels, "all_channels": list(self._channels.keys())})
        # #endregion agent log

        if channel_id not in self._channels:
            # Allow subscribing to a channel that might be created momentarily
            logger.info(f"Creating new channel for subscriber: {channel_id}")
            await self.create_channel(channel_id)

        queue = self._channels[channel_id]
        queue_size = queue.qsize()
        logger.info(f"Client subscribed to channel: {channel_id} (queue has {queue_size} pending messages)")

        # If there are already messages in the queue, they will be delivered immediately

        try:
            while True:
                # Get message from queue
                # Use wait_for to allow sending keep-alive pings
                try:
                    data_json = await asyncio.wait_for(queue.get(), timeout=15.0)
                    msg_dict = json.loads(data_json)

                    # Format for SSE: yield just the JSON string (EventSourceResponse will format it)
                    # The data is already JSON, so just yield it
                    yield data_json

                    # If process is completed or failed, stop the stream after sending the final message
                    msg_dict = json.loads(data_json)
                    if msg_dict.get("type") in ["completed", "failed", "error"]:
                        logger.info(f"Stream {channel_id} completed/failed. Closing connection.")
                        break

                except asyncio.TimeoutError:
                    # EventSourceResponse handles keep-alive automatically with ping parameter
                    # Just continue waiting
                    pass

                    # Check if channel is stale (no updates for 1 hour)
                    if datetime.now() - self._last_activity.get(channel_id, datetime.min) > timedelta(
                        hours=1
                    ):
                        logger.warning(f"Channel {channel_id} timed out")
                        break

        except Exception as e:
            logger.error(f"Subscription error for {channel_id}: {e}")

    async def get_latest_status(self, channel_id: str) -> dict | None:
        """Get the latest progress status for a channel (for polling)."""
        if channel_id in self._latest_status:
            return self._latest_status[channel_id]
        return None

    def cleanup_expired_channels(self, max_age_hours: int = 1):
        """Remove channels that haven't had activity."""
        now = datetime.now()
        expired = []
        for cid, last_active in self._last_activity.items():
            if now - last_active > timedelta(hours=max_age_hours):
                expired.append(cid)

        for cid in expired:
            del self._channels[cid]
            del self._last_activity[cid]
            # Also clean up latest status
            if cid in self._latest_status:
                del self._latest_status[cid]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired progress channels")


# Dependency for FastAPI
def get_progress_manager() -> ProgressManager:
    """Get the ProgressManager singleton instance for FastAPI dependency injection."""
    return ProgressManager.get_instance()
