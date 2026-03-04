"""Throttled DB Writer - Reduces database write frequency.

Gates DB writes by time interval to prevent disk I/O budget exhaustion.
Stores only the latest payload in memory and writes at most once per interval.
"""

import logging
import time
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class ThrottledDBWriter:
    """Gates DB writes by time interval, always keeping the latest payload."""

    def __init__(
        self,
        write_fn: Callable[[Any], Coroutine],
        min_interval_seconds: float = 5.0,
    ):
        """Initialize throttled writer.

        Args:
            write_fn: Async callable that performs the actual DB write.
                      Receives the payload as its single argument.
            min_interval_seconds: Minimum seconds between DB writes.

        """
        self._write_fn = write_fn
        self._min_interval = min_interval_seconds
        self._last_write_time: float = 0.0
        self._pending_payload: Optional[Any] = None

    async def maybe_write(self, payload: Any) -> bool:
        """Write to DB only if the minimum interval has elapsed.

        Always stores the latest payload. Returns True if a write occurred.
        """
        self._pending_payload = payload
        now = time.monotonic()

        if now - self._last_write_time >= self._min_interval:
            await self._do_write()
            return True
        return False

    async def flush(self) -> bool:
        """Force-write the pending payload (if any). Call at completion/error boundaries."""
        if self._pending_payload is not None:
            await self._do_write()
            return True
        return False

    async def _do_write(self) -> None:
        """Execute the write and reset state."""
        payload = self._pending_payload
        self._pending_payload = None
        self._last_write_time = time.monotonic()
        await self._write_fn(payload)
