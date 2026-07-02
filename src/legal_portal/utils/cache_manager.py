"""Cache Manager Module.

Provides caching functionality for expensive operations with file-based
and optional Redis support.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any, Dict, Optional

# Configure logger
logger = logging.getLogger(__name__)

# Optional Redis support
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, using file-based caching only")


class CacheManager:
    """Manage caching for expensive operations."""

    def __init__(
        self,
        cache_dir: str = ".cache",
        use_redis: bool = False,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: Optional[str] = None,
        redis_db: int = 0,
    ):
        """Initialize cache manager.

        Args:
        ----
            cache_dir: Directory for file-based cache
            use_redis: Use Redis for distributed caching
            redis_host: Redis hostname
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number

        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # Initialize Redis if requested and available
        self.redis_client = None
        if use_redis and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    password=redis_password,
                    db=redis_db,
                    decode_responses=False,  # We'll handle encoding/decoding
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                # Test connection
                self.redis_client.ping()
                logger.info("Redis cache initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Using file cache only.")
                self.redis_client = None
        elif use_redis and not REDIS_AVAILABLE:
            logger.warning("Redis requested but not installed. Using file cache only.")

    def cache_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        key_data = {"args": args, "kwargs": kwargs}
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        # Try Redis first
        if self.redis_client:
            try:
                value = self.redis_client.get(key)
                if value:
                    logger.debug(f"Cache hit (Redis): {key[:8]}...")
                    return json.loads(value)
            except Exception as e:
                logger.debug(f"Redis cache get failed: {e}")

        # Fall back to file cache (JSON format)
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            # Check if not expired (24 hours by default)
            file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if file_age < timedelta(hours=24):
                try:
                    with open(cache_file, "r") as f:
                        logger.debug(f"Cache hit (file): {key[:8]}...")
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"File cache read failed: {e}")
            else:
                try:
                    cache_file.unlink()  # Remove expired cache file
                except Exception:
                    pass

        # Clean up any legacy .pkl files for this key
        legacy_pkl = self.cache_dir / f"{key}.pkl"
        if legacy_pkl.exists():
            try:
                legacy_pkl.unlink()
            except Exception:
                pass

        return None

    def set(self, key: str, value: Any, ttl: int = 86400):
        """Set value in cache with TTL.

        Args:
        ----
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default 24 hours)

        """
        serialized_value = json.dumps(value, default=str)

        # Save to Redis
        if self.redis_client:
            try:
                self.redis_client.setex(key, ttl, serialized_value)
                logger.debug(f"Cached to Redis: {key[:8]}...")
            except Exception as e:
                logger.debug(f"Redis cache set failed: {e}")

        # Save to file cache (JSON format)
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(value, f, default=str)
            logger.debug(f"Cached to file: {key[:8]}...")
        except Exception as e:
            logger.error(f"File cache write failed: {e}")

    def delete(self, key: str):
        """Delete a specific cache entry."""
        # Delete from Redis
        if self.redis_client:
            try:
                self.redis_client.delete(key)
            except Exception:
                pass

        # Delete from file cache
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                cache_file.unlink()
            except Exception:
                pass

        logger.debug(f"Cache deleted: {key[:8]}...")

    def clear(self):
        """Clear all cache entries."""
        # Clear Redis cache
        if self.redis_client:
            try:
                self.redis_client.flushdb()
                logger.info("Redis cache cleared")
            except Exception as e:
                logger.error(f"Failed to clear Redis cache: {e}")

        # Clear file cache
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except Exception:
                pass
        logger.info("File cache cleared")

    def cached(self, ttl: int = 86400, key_prefix: str = ""):
        """Decorator for caching function results.

        Args:
        ----
            ttl: Time to live in seconds (default 24 hours)
            key_prefix: Optional prefix for cache keys

        Returns:
        -------
            Decorated function with caching

        """

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key
                base_key = self.cache_key(func.__name__, *args, **kwargs)
                key = f"{key_prefix}:{base_key}" if key_prefix else base_key

                # Check cache
                cached_value = self.get(key)
                if cached_value is not None:
                    logger.debug(f"Using cached result for {func.__name__}")
                    return cached_value

                # Compute and cache
                logger.debug(f"Computing result for {func.__name__}")
                result = func(*args, **kwargs)
                self.set(key, result, ttl)

                return result

            # Add method to clear specific function cache
            def clear_cache(*args, **kwargs):
                base_key = self.cache_key(func.__name__, *args, **kwargs)
                key = f"{key_prefix}:{base_key}" if key_prefix else base_key
                self.delete(key)

            wrapper.clear_cache = clear_cache
            return wrapper

        return decorator

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "cache_dir": str(self.cache_dir),
            "file_cache_count": len(list(self.cache_dir.glob("*.json"))),
            "file_cache_size_mb": sum(f.stat().st_size for f in self.cache_dir.glob("*.json")) / (1024 * 1024),
            "redis_available": self.redis_client is not None,
        }

        if self.redis_client:
            try:
                info = self.redis_client.info()
                stats["redis_keys"] = self.redis_client.dbsize()
                stats["redis_memory_mb"] = info.get("used_memory", 0) / (1024 * 1024)
            except Exception:
                stats["redis_status"] = "error"

        return stats

    def cleanup_expired(self, max_age_hours: int = 24):
        """Remove expired cache files.

        Args:
        ----
            max_age_hours: Maximum age in hours for cache files

        """
        now = datetime.now()
        max_age = timedelta(hours=max_age_hours)
        cleaned = 0

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                file_age = now - datetime.fromtimestamp(cache_file.stat().st_mtime)
                if file_age > max_age:
                    cache_file.unlink()
                    cleaned += 1
            except Exception as e:
                logger.debug(f"Failed to clean cache file {cache_file}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} expired cache files")

        return cleaned


@lru_cache(maxsize=1)
def get_cache_manager() -> CacheManager:
    """Get the singleton CacheManager instance.

    Reads Redis settings from config.default.Settings when available.
    Defaults to file-only cache if Redis is disabled or settings
    cannot be loaded.
    """
    try:
        from legal_portal.config.default import get_settings

        settings = get_settings()
        return CacheManager(
            cache_dir=".cache",
            use_redis=settings.redis_cache_enabled,
            redis_host=settings.redis_cache_host,
            redis_port=settings.redis_cache_port,
            redis_password=settings.redis_cache_password,
            redis_db=settings.redis_cache_db,
        )
    except Exception:
        # Graceful fallback: if settings can't be loaded, use file cache only.
        return CacheManager(cache_dir=".cache", use_redis=False)


# Convenience decorators using global cache
def cached(ttl: int = 86400, key_prefix: str = ""):
    """Convenience decorator using global cache manager.

    Args:
    ----
        ttl: Time to live in seconds
        key_prefix: Optional prefix for cache keys

    Returns:
    -------
        Decorated function with caching

    """
    cache = get_cache_manager()
    return cache.cached(ttl, key_prefix)


# Example usage for document processing cache
class DocumentCache:
    """Specialized cache for document processing operations."""

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        """Initialize with optional custom cache manager."""
        self.cache = cache_manager or get_cache_manager()

    # NOTE: former cache_document_analysis / cache_embeddings /
    # cache_api_response / cache_generated_document helpers were removed —
    # they had zero callers, and their keys omitted model/prompt version, so
    # any future caller would have served stale content across upgrades. The
    # document-summary cache below is the live, version-safe pattern (key
    # includes doc_id + text hash + model + tier, built in main_processor).

    def cache_document_summary(self, cache_key: str, summary: Dict[str, Any], ttl: int = 86400 * 7):
        """Cache a document summary dict keyed by content+tier+model hash. TTL: 7 days."""
        self.cache.set(f"doc_summary:{cache_key}", summary, ttl=ttl)

    def get_document_summary(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a cached document summary dict, or None on miss/expiry."""
        return self.cache.get(f"doc_summary:{cache_key}")


def cleanup_validation_output(validation_dir: str = "validation_output", max_age_hours: int = 24) -> int:
    """Remove old files from validation_output directory.

    Args:
    ----
        validation_dir: Path to validation output directory
        max_age_hours: Maximum age in hours for files (default 24)

    Returns:
    -------
        Number of files cleaned

    """
    output_path = Path(validation_dir)
    if not output_path.exists():
        logger.debug(f"Validation output directory does not exist: {validation_dir}")
        return 0

    now = datetime.now()
    max_age = timedelta(hours=max_age_hours)
    cleaned = 0

    for file_path in output_path.glob("*"):
        if file_path.is_file():
            try:
                file_age = now - datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_age > max_age:
                    file_path.unlink()
                    cleaned += 1
                    logger.info(f"Cleaned expired file: {file_path.name} (age: {file_age})")
            except Exception as e:
                logger.debug(f"Failed to clean file {file_path}: {e}")

    if cleaned > 0:
        logger.info(f"Cleaned {cleaned} expired files from {validation_dir}")

    return cleaned
