"""Optional Sentry error tracking.

No-op unless SENTRY_DSN is set, so local/dev environments and tests are
unaffected. Called from both the API app and the worker entrypoint —
without this, a crashed analysis only surfaces as a status row plus a
stdout stack trace in Railway/Vercel logs.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def init_error_tracking(component: str) -> bool:
    """Initialize Sentry if configured. Returns True when active.

    Args:
    ----
        component: 'api' or 'worker' — tagged on every event.

    """
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("VERCEL_ENV", os.getenv("ENVIRONMENT", "development")),
            release=os.getenv("APP_VERSION"),
            # Error tracking only; keep performance tracing off until wanted
            traces_sample_rate=0.0,
            # Legal documents: never attach local variables or request bodies
            include_local_variables=False,
            max_request_body_size="never",
        )
        sentry_sdk.set_tag("component", component)
        logger.info(f"Sentry error tracking initialized for {component}")
        return True
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed — error tracking disabled")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        return False
