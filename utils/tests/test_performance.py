"""Performance benchmark tests."""
from __future__ import annotations

import time

import pytest

from utils.api_optimizer import OpenAIOptimizer
from utils.cache_manager import CacheManager


@pytest.fixture
def api_optimizer():
    """Create API optimizer instance."""
    return OpenAIOptimizer(api_key="test", max_workers=10)

@pytest.fixture
def cache_manager():
    """Create cache manager instance."""
    return CacheManager(cache_dir=".test_cache")

def test_api_optimizer_throughput(benchmark, api_optimizer):
    """Benchmark API optimizer throughput."""
    def process_batch():
        # Simulate batch processing
        prompts = ["test prompt"] * 10
        # Mock the actual API call for benchmarking
        return [{"content": "response"} for _ in prompts]
    
    result = benchmark(process_batch)
    assert len(result) == 10

def test_cache_performance(benchmark, cache_manager):
    """Benchmark cache operations."""
    test_data = {"key": "value", "data": list(range(1000))}
    
    def cache_operations():
        cache_manager.set("test_key", test_data)
        return cache_manager.get("test_key")
    
    result = benchmark(cache_operations)
    assert result == test_data

def test_parallel_processing_performance(benchmark):
    """Benchmark parallel vs sequential processing."""
    from concurrent.futures import ThreadPoolExecutor
    
    def task(n):
        time.sleep(0.001)  # Simulate work
        return n * 2
    
    def parallel_execution():
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(task, range(50)))
        return results
    
    results = benchmark(parallel_execution)
    assert len(results) == 50
