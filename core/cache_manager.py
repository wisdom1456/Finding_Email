"""
Cache Manager Module

Provides caching functionality for expensive operations with file-based 
and optional Redis support.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Optional, Union


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
    """Manage caching for expensive operations"""
    
    def __init__(self, cache_dir: str = ".cache", use_redis: bool = False):
        """
        Initialize cache manager
        
        Args:
            cache_dir: Directory for file-based cache
            use_redis: Use Redis for distributed caching
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Initialize Redis if requested and available
        self.redis_client = None
        if use_redis and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=os.getenv("REDIS_HOST", "localhost"),
                    port=int(os.getenv("REDIS_PORT", 6379)),
                    decode_responses=False,  # We'll handle encoding/decoding
                    socket_connect_timeout=5,
                    socket_timeout=5
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
        """Generate cache key from arguments"""
        key_data = {
            "args": args,
            "kwargs": kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        # Try Redis first
        if self.redis_client:
            try:
                value = self.redis_client.get(key)
                if value:
                    logger.debug(f"Cache hit (Redis): {key[:8]}...")
                    return pickle.loads(value)
            except Exception as e:
                logger.debug(f"Redis cache get failed: {e}")
        
        # Fall back to file cache
        cache_file = self.cache_dir / f"{key}.pkl"
        if cache_file.exists():
            # Check if not expired (24 hours by default)
            file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if file_age < timedelta(hours=24):
                try:
                    with open(cache_file, "rb") as f:
                        logger.debug(f"Cache hit (file): {key[:8]}...")
                        return pickle.load(f)
                except Exception as e:
                    logger.debug(f"File cache read failed: {e}")
            else:
                logger.debug(f"Cache expired (file): {key[:8]}...")
                try:
                    cache_file.unlink()  # Remove expired cache file
                except:
                    pass
        
        logger.debug(f"Cache miss: {key[:8]}...")
        return None
    
    def set(self, key: str, value: Any, ttl: int = 86400):
        """
        Set value in cache with TTL
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default 24 hours)
        """
        serialized_value = pickle.dumps(value)
        
        # Save to Redis
        if self.redis_client:
            try:
                self.redis_client.setex(
                    key,
                    ttl,
                    serialized_value
                )
                logger.debug(f"Cached to Redis: {key[:8]}...")
            except Exception as e:
                logger.debug(f"Redis cache set failed: {e}")
        
        # Save to file cache
        cache_file = self.cache_dir / f"{key}.pkl"
        try:
            with open(cache_file, "wb") as f:
                pickle.dump(value, f)
            logger.debug(f"Cached to file: {key[:8]}...")
        except Exception as e:
            logger.error(f"File cache write failed: {e}")
    
    def delete(self, key: str):
        """Delete a specific cache entry"""
        # Delete from Redis
        if self.redis_client:
            try:
                self.redis_client.delete(key)
            except:
                pass
        
        # Delete from file cache
        cache_file = self.cache_dir / f"{key}.pkl"
        if cache_file.exists():
            try:
                cache_file.unlink()
            except:
                pass
        
        logger.debug(f"Cache deleted: {key[:8]}...")
    
    def clear(self):
        """Clear all cache entries"""
        # Clear Redis cache
        if self.redis_client:
            try:
                self.redis_client.flushdb()
                logger.info("Redis cache cleared")
            except Exception as e:
                logger.error(f"Failed to clear Redis cache: {e}")
        
        # Clear file cache
        for cache_file in self.cache_dir.glob("*.pkl"):
            try:
                cache_file.unlink()
            except:
                pass
        logger.info("File cache cleared")
    
    def cached(self, ttl: int = 86400, key_prefix: str = ""):
        """
        Decorator for caching function results
        
        Args:
            ttl: Time to live in seconds (default 24 hours)
            key_prefix: Optional prefix for cache keys
            
        Returns:
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
        """Get cache statistics"""
        stats = {
            "cache_dir": str(self.cache_dir),
            "file_cache_count": len(list(self.cache_dir.glob("*.pkl"))),
            "file_cache_size_mb": sum(f.stat().st_size for f in self.cache_dir.glob("*.pkl")) / (1024 * 1024),
            "redis_available": self.redis_client is not None
        }
        
        if self.redis_client:
            try:
                info = self.redis_client.info()
                stats["redis_keys"] = self.redis_client.dbsize()
                stats["redis_memory_mb"] = info.get("used_memory", 0) / (1024 * 1024)
            except:
                stats["redis_status"] = "error"
        
        return stats
    
    def cleanup_expired(self, max_age_hours: int = 24):
        """
        Remove expired cache files
        
        Args:
            max_age_hours: Maximum age in hours for cache files
        """
        now = datetime.now()
        max_age = timedelta(hours=max_age_hours)
        cleaned = 0
        
        for cache_file in self.cache_dir.glob("*.pkl"):
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


# Global cache instance (singleton pattern)
_global_cache = None

def get_cache_manager(cache_dir: str = ".cache", use_redis: bool = False) -> CacheManager:
    """
    Get or create global cache manager instance
    
    Args:
        cache_dir: Directory for file-based cache
        use_redis: Use Redis for distributed caching
        
    Returns:
        CacheManager instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = CacheManager(cache_dir, use_redis)
    return _global_cache


# Convenience decorators using global cache
def cached(ttl: int = 86400, key_prefix: str = ""):
    """
    Convenience decorator using global cache manager
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Optional prefix for cache keys
        
    Returns:
        Decorated function with caching
    """
    cache = get_cache_manager()
    return cache.cached(ttl, key_prefix)


# Example usage for document processing cache
class DocumentCache:
    """Specialized cache for document processing operations"""
    
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        """Initialize with optional custom cache manager"""
        self.cache = cache_manager or get_cache_manager()
    
    def cache_document_analysis(self, document_id: str, analysis_result: Dict[str, Any]):
        """Cache document analysis results"""
        key = f"doc_analysis:{document_id}"
        self.cache.set(key, analysis_result, ttl=86400 * 7)  # Cache for 7 days
    
    def get_document_analysis(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached document analysis"""
        key = f"doc_analysis:{document_id}"
        return self.cache.get(key)
    
    def cache_embeddings(self, text_hash: str, embeddings: Any):
        """Cache text embeddings"""
        key = f"embeddings:{text_hash}"
        self.cache.set(key, embeddings, ttl=86400 * 30)  # Cache for 30 days
    
    def get_embeddings(self, text_hash: str) -> Optional[Any]:
        """Retrieve cached embeddings"""
        key = f"embeddings:{text_hash}"
        return self.cache.get(key)
    
    def cache_api_response(self, prompt_hash: str, response: str, model: str = "gpt-4"):
        """Cache API responses"""
        key = f"api_response:{model}:{prompt_hash}"
        self.cache.set(key, response, ttl=86400 * 3)  # Cache for 3 days
    
    def get_api_response(self, prompt_hash: str, model: str = "gpt-4") -> Optional[str]:
        """Retrieve cached API response"""
        key = f"api_response:{model}:{prompt_hash}"
        return self.cache.get(key)
