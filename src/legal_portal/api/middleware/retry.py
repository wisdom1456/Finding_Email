"""Shared retry utilities for transient Supabase/PostgREST errors.

Provides both sync and async retry helpers with exponential backoff.
Does NOT handle Clio, OpenAI, or OCR retries — those are domain-specific.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Set, Tuple, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_CODES: Set[str] = {"502", "503", "57014"}
TRANSIENT_MESSAGES: Tuple[str, ...] = (
    "bad gateway",
    "service unavailable",
    "schema cache",
    "statement timeout",
)


def is_transient_supabase_error(err: Exception) -> bool:
    """Check if a Supabase/PostgREST error is transient and worth retrying."""
    code = str(getattr(err, "code", ""))
    message = str(getattr(err, "message", str(err))).lower()
    if code in TRANSIENT_CODES:
        return True
    return any(msg in message for msg in TRANSIENT_MESSAGES)


def retry_sync(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    is_retryable: Callable[[Exception], bool] = is_transient_supabase_error,
    context_label: str = "",
) -> T:
    """Execute fn() with retry on transient errors (synchronous).

    Returns fn() result on success. Re-raises the last exception on exhaustion.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as err:
            if is_retryable(err) and attempt < max_attempts - 1:
                delay = 2 ** attempt
                logger.warning(
                    "Transient error%s (attempt %d/%d), retrying in %ds: %s",
                    f" on {context_label}" if context_label else "",
                    attempt + 1, max_attempts, delay, err,
                )
                time.sleep(delay)
                continue
            raise


async def retry_async(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    is_retryable: Callable[[Exception], bool] = is_transient_supabase_error,
    context_label: str = "",
) -> T:
    """Execute fn() with retry on transient errors (async backoff).

    Same contract as retry_sync but uses asyncio.sleep.
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as err:
            if is_retryable(err) and attempt < max_attempts - 1:
                delay = 2 ** attempt
                logger.warning(
                    "Transient error%s (attempt %d/%d), retrying in %ds: %s",
                    f" on {context_label}" if context_label else "",
                    attempt + 1, max_attempts, delay, err,
                )
                await asyncio.sleep(delay)
                continue
            raise
