"""
OpenAI API Optimizer Module

Provides optimized OpenAI API client with concurrency, caching, and rate limiting.
Designed to improve throughput by 3-5x through parallel processing.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI


# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class APICallResult:
    """Result of an API call with metadata"""
    content: str
    model: str
    tokens_used: int
    latency: float
    cached: bool = False


class RateLimiter:
    """Rate limiter for API calls"""
    
    def __init__(self, calls_per_minute: int, calls_per_day: int):
        """
        Initialize rate limiter
        
        Args:
            calls_per_minute: Maximum calls per minute
            calls_per_day: Maximum calls per day
        """
        self.calls_per_minute = calls_per_minute
        self.calls_per_day = calls_per_day
        self.minute_calls = []
        self.day_calls = []
    
    def can_call(self) -> bool:
        """Check if we can make another API call"""
        now = time.time()
        
        # Clean old calls
        self.minute_calls = [t for t in self.minute_calls if now - t < 60]
        self.day_calls = [t for t in self.day_calls if now - t < 86400]
        
        # Check limits
        if len(self.minute_calls) >= self.calls_per_minute:
            return False
        if len(self.day_calls) >= self.calls_per_day:
            return False
        
        return True
    
    def record_call(self):
        """Record an API call"""
        now = time.time()
        self.minute_calls.append(now)
        self.day_calls.append(now)
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        while not self.can_call():
            # Wait for oldest call to expire
            now = time.time()
            if self.minute_calls:
                wait_time = 60 - (now - self.minute_calls[0]) + 0.1
                if wait_time > 0:
                    logger.info(f"Rate limit reached, waiting {wait_time:.1f} seconds")
                    time.sleep(wait_time)
            else:
                time.sleep(0.1)


class OpenAIOptimizer:
    """Optimized OpenAI API client with concurrency and caching"""
    
    def __init__(self, api_key: str, max_workers: int = 10):
        """
        Initialize with concurrency control
        
        Args:
            api_key: OpenAI API key
            max_workers: Maximum concurrent API calls (default 10)
        """
        self.client = OpenAI(api_key=api_key)
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._cache = {}  # Simple in-memory cache
        self.rate_limiter = RateLimiter(
            calls_per_minute=500,  # OpenAI tier limits
            calls_per_day=10000
        )
        logger.info(f"OpenAIOptimizer initialized with {max_workers} workers")
    
    def _cache_key(self, prompt: str, model: str, temperature: float = 0) -> str:
        """Generate cache key for prompt"""
        content = f"{model}:{temperature}:{prompt}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _single_completion(self, prompt: str, model: str, temperature: float = 0) -> APICallResult:
        """Execute a single completion with rate limiting"""
        # Wait if rate limit would be exceeded
        self.rate_limiter.wait_if_needed()
        
        start = time.time()
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature
            )
            
            # Record successful call
            self.rate_limiter.record_call()
            
            return APICallResult(
                content=response.choices[0].message.content,
                model=model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                latency=time.time() - start,
                cached=False
            )
        except Exception as e:
            logger.error(f"API call failed: {e}")
            raise
    
    @lru_cache(maxsize=1000)
    def _cached_completion(self, cache_key: str, prompt: str, model: str, temperature: float = 0) -> APICallResult:
        """LRU cached completion for identical prompts"""
        result = self._single_completion(prompt, model, temperature)
        logger.debug(f"Cached new result for key {cache_key[:8]}...")
        return result
    
    def batch_completions(
        self,
        prompts: List[str],
        model: str = "gpt-4",
        use_cache: bool = True,
        temperature: float = 0,
        progress_callback: Optional[Callable] = None
    ) -> List[APICallResult]:
        """
        Process multiple prompts concurrently
        
        Args:
            prompts: List of prompts to process
            model: OpenAI model to use
            use_cache: Whether to use caching
            temperature: Temperature for generation (0 for deterministic)
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of results in same order as prompts
        """
        logger.info(f"Processing batch of {len(prompts)} prompts with model {model}")
        results = [None] * len(prompts)
        futures = {}
        cache_hits = 0
        
        with self.executor as executor:
            for i, prompt in enumerate(prompts):
                cache_key = self._cache_key(prompt, model, temperature)
                
                # Check cache first
                if use_cache and cache_key in self._cache:
                    results[i] = self._cache[cache_key]
                    results[i].cached = True
                    cache_hits += 1
                    if progress_callback:
                        progress_callback(i + 1, len(prompts))
                    logger.debug(f"Cache hit for prompt {i + 1}/{len(prompts)}")
                    continue
                
                # Submit for concurrent processing
                if use_cache and temperature == 0:
                    # Use cached completion for deterministic results
                    future = executor.submit(
                        self._cached_completion,
                        cache_key, prompt, model, temperature
                    )
                else:
                    # Non-cacheable completion
                    future = executor.submit(
                        self._single_completion,
                        prompt, model, temperature
                    )
                futures[future] = i
            
            # Process completed futures
            completed = 0
            for future in as_completed(futures):
                idx = futures[future]
                completed += 1
                try:
                    result = future.result()
                    results[idx] = result
                    
                    # Update cache for deterministic results
                    if use_cache and temperature == 0:
                        cache_key = self._cache_key(prompts[idx], model, temperature)
                        self._cache[cache_key] = result
                    
                    if progress_callback:
                        progress_callback(cache_hits + completed, len(prompts))
                    
                    logger.debug(f"Completed API call {completed}/{len(futures)} (prompt {idx + 1})")
                        
                except Exception as e:
                    logger.error(f"API call failed for prompt {idx}: {e}")
                    # Create error result
                    results[idx] = APICallResult(
                        content=f"Error: {e!s}",
                        model=model,
                        tokens_used=0,
                        latency=0,
                        cached=False
                    )
        
        # Log statistics
        successful = sum(1 for r in results if r and not r.content.startswith("Error:"))
        total_tokens = sum(r.tokens_used for r in results if r)
        avg_latency = sum(r.latency for r in results if r) / len(results) if results else 0
        
        logger.info(f"Batch complete: {successful}/{len(prompts)} successful, "
                   f"{cache_hits} cache hits, {total_tokens} total tokens, "
                   f"{avg_latency:.2f}s avg latency")
        
        return results
    
    async def async_batch_completions(
        self,
        prompts: List[str],
        model: str = "gpt-4",
        use_cache: bool = True,
        temperature: float = 0,
        progress_callback: Optional[Callable] = None
    ) -> List[APICallResult]:
        """
        Async version of batch_completions for use in async contexts
        
        Args:
            prompts: List of prompts to process
            model: OpenAI model to use
            use_cache: Whether to use caching
            temperature: Temperature for generation
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of results in same order as prompts
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.batch_completions,
            prompts,
            model,
            use_cache,
            temperature,
            progress_callback
        )
    
    def clear_cache(self):
        """Clear the result cache"""
        self._cache.clear()
        self._cached_completion.cache_clear()
        logger.info("Cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "cache_size": len(self._cache),
            "lru_cache_info": self._cached_completion.cache_info()._asdict(),
            "rate_limiter": {
                "minute_calls": len(self.rate_limiter.minute_calls),
                "day_calls": len(self.rate_limiter.day_calls),
                "limits": {
                    "per_minute": self.rate_limiter.calls_per_minute,
                    "per_day": self.rate_limiter.calls_per_day
                }
            }
        }
    
    def __del__(self):
        """Cleanup executor on deletion"""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)
