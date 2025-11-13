"""Async Streamlit Helper Module.

Enables async operations and parallel processing in Streamlit applications
to keep the UI responsive during long-running operations.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Generator, List, Optional

import streamlit as st

# Configure logger
logger = logging.getLogger(__name__)


class AsyncStreamlit:
    """Enable async operations in Streamlit."""

    @staticmethod
    def run_async(func: Callable, *args, **kwargs) -> Any:
        """Run async function in Streamlit.

        Args:
        ----
            func: Async function to run
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
        -------
            Result of the async function

        """
        # Check if there's already an event loop running
        try:
            loop = asyncio.get_running_loop()
            # If we're in an existing loop, schedule the coroutine
            if asyncio.iscoroutinefunction(func):
                future = asyncio.ensure_future(func(*args, **kwargs))
                return loop.run_until_complete(future)
            # Not an async function, just call it
            return func(*args, **kwargs)
        except RuntimeError:
            # No loop running, create a new one
            if asyncio.iscoroutinefunction(func):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(func(*args, **kwargs))
                finally:
                    loop.close()
            else:
                # Not an async function, just call it
                return func(*args, **kwargs)

    @staticmethod
    def parallel_progress(
        tasks: List[Callable],
        task_args: Optional[List[tuple]] = None,
        task_kwargs: Optional[List[dict]] = None,
        progress_bar=None,
        status_text=None,
        max_workers: int = 5,
    ) -> Generator[Any, None, None]:
        """Execute tasks in parallel with progress updates.

        Args:
        ----
            tasks: List of callable tasks to execute
            task_args: Optional list of positional arguments for each task
            task_kwargs: Optional list of keyword arguments for each task
            progress_bar: Streamlit progress bar widget
            status_text: Streamlit text widget for status updates
            max_workers: Maximum number of parallel workers

        Yields:
        ------
            Results of completed tasks as they finish

        """
        total = len(tasks)
        completed = 0

        # Prepare arguments
        if task_args is None:
            task_args = [() for _ in tasks]
        if task_kwargs is None:
            task_kwargs = [{} for _ in tasks]

        # Validate input lengths
        if len(task_args) != total or len(task_kwargs) != total:
            raise ValueError("task_args and task_kwargs must match the length of tasks")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {}
            for i, (task, args, kwargs) in enumerate(zip(tasks, task_args, task_kwargs, strict=False)):
                future = executor.submit(task, *args, **kwargs)
                futures[future] = i

            # Process results as they complete
            for future in as_completed(futures):
                task_index = futures[future]
                completed += 1

                # Update progress
                if progress_bar:
                    progress_bar.progress(completed / total)

                if status_text:
                    status_text.text(f"Processing {completed}/{total}...")

                # Get result
                try:
                    result = future.result()
                    logger.debug(f"Task {task_index} completed successfully")
                    yield (task_index, result)
                except Exception as e:
                    logger.error(f"Task {task_index} failed: {e}")
                    yield (task_index, None)

    @staticmethod
    def batch_process(
        items: List[Any],
        process_func: Callable,
        batch_size: int = 10,
        max_workers: int = 5,
        progress_callback: Optional[Callable] = None,
    ) -> List[Any]:
        """Process items in batches with parallel execution.

        Args:
        ----
            items: List of items to process
            process_func: Function to process each item
            batch_size: Size of each batch
            max_workers: Maximum number of parallel workers
            progress_callback: Optional callback for progress updates

        Returns:
        -------
            List of processed results

        """
        results = [None] * len(items)
        total_batches = (len(items) + batch_size - 1) // batch_size

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(items))
                batch = items[start_idx:end_idx]

                # Process batch in parallel
                futures = {}
                for i, item in enumerate(batch):
                    future = executor.submit(process_func, item)
                    futures[future] = start_idx + i

                # Collect results
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        results[idx] = future.result()
                    except Exception as e:
                        logger.error(f"Failed to process item {idx}: {e}")
                        results[idx] = None

                    # Update progress
                    if progress_callback:
                        completed = sum(1 for r in results if r is not None)
                        progress_callback(completed, len(items))

        return results

    @staticmethod
    @contextmanager
    def spinner(text: str = "Processing..."):
        """Context manager for showing a spinner during async operations.

        Args:
        ----
            text: Text to display with the spinner

        """
        spinner = st.spinner(text)
        spinner.__enter__()
        try:
            yield
        finally:
            spinner.__exit__(None, None, None)

    @staticmethod
    def async_cache(ttl: int = 3600):
        """Decorator for caching async function results in Streamlit.

        Args:
        ----
            ttl: Time to live in seconds (default 1 hour)

        Returns:
        -------
            Decorated function with caching

        """

        def decorator(func):
            # Use Streamlit's built-in caching
            cached_func = st.cache_data(ttl=ttl, show_spinner=False)(func)

            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Convert async to sync for caching
                if asyncio.iscoroutinefunction(func):
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, cached_func, *args, **kwargs)
                return cached_func(*args, **kwargs)

            return wrapper

        return decorator


class ParallelDocumentProcessor:
    """Specialized parallel processor for document operations."""

    def __init__(self, max_workers: int = 10):
        """Initialize parallel document processor.

        Args:
        ----
            max_workers: Maximum number of parallel workers

        """
        self.max_workers = max_workers
        logger.info(f"ParallelDocumentProcessor initialized with {max_workers} workers")

    def process_documents(
        self,
        documents: List[Dict[str, Any]],
        process_func: Callable,
        progress_bar=None,
        status_text=None,
        chunk_size: int = 5,
    ) -> List[Any]:
        """Process multiple documents in parallel with progress updates.

        Args:
        ----
            documents: List of document data to process
            process_func: Function to process each document
            progress_bar: Optional Streamlit progress bar
            status_text: Optional Streamlit status text
            chunk_size: Number of documents to process per batch

        Returns:
        -------
            List of processed results

        """
        total = len(documents)
        results = [None] * total
        processed = 0

        logger.info(f"Starting parallel processing of {total} documents")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Process in chunks to avoid overwhelming the system
            for chunk_start in range(0, total, chunk_size):
                chunk_end = min(chunk_start + chunk_size, total)
                chunk = documents[chunk_start:chunk_end]

                # Submit chunk for processing
                futures = {}
                for i, doc in enumerate(chunk):
                    future = executor.submit(process_func, doc)
                    futures[future] = chunk_start + i

                # Collect results for this chunk
                for future in as_completed(futures):
                    idx = futures[future]
                    processed += 1

                    try:
                        results[idx] = future.result()
                        logger.debug(f"Document {idx + 1}/{total} processed successfully")
                    except Exception as e:
                        logger.error(f"Failed to process document {idx}: {e}")
                        results[idx] = {"error": str(e)}

                    # Update UI
                    if progress_bar:
                        progress_bar.progress(processed / total)
                    if status_text:
                        status_text.text(f"Processing document {processed}/{total}...")

        logger.info(f"Completed processing {total} documents")
        return results

    def parallel_api_calls(
        self,
        api_func: Callable,
        prompts: List[str],
        rate_limit_delay: float = 0.1,
        progress_callback: Optional[Callable] = None,
    ) -> List[Any]:
        """Execute API calls in parallel with rate limiting.

        Args:
        ----
            api_func: API function to call
            prompts: List of prompts or inputs for the API
            rate_limit_delay: Delay between API calls to avoid rate limits
            progress_callback: Optional callback for progress updates

        Returns:
        -------
            List of API responses

        """
        results = [None] * len(prompts)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}

            # Submit with staggered start times to avoid rate limits
            for i, prompt in enumerate(prompts):
                if i > 0 and rate_limit_delay > 0:
                    time.sleep(rate_limit_delay)

                future = executor.submit(api_func, prompt)
                futures[future] = i

            # Collect results
            completed = 0
            for future in as_completed(futures):
                idx = futures[future]
                completed += 1

                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"API call {idx} failed: {e}")
                    results[idx] = None

                if progress_callback:
                    progress_callback(completed, len(prompts))

        return results


# Convenience functions for common async patterns
def run_parallel_tasks(tasks: List[Callable], max_workers: int = 5) -> List[Any]:
    """Run multiple tasks in parallel and return results.

    Args:
    ----
        tasks: List of callable tasks
        max_workers: Maximum number of parallel workers

    Returns:
    -------
        List of task results

    """
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(task) for task in tasks]
        results = []
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"Task failed: {e}")
                results.append(None)
    return results


def async_map(func: Callable, items: List[Any], max_workers: int = 5) -> List[Any]:
    """Apply function to items in parallel.

    Args:
    ----
        func: Function to apply to each item
        items: List of items to process
        max_workers: Maximum number of parallel workers

    Returns:
    -------
        List of processed results

    """
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(func, item) for item in items]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"Processing failed: {e}")
                results.append(None)
    return results


# Example usage in Streamlit app
def example_streamlit_usage():
    """Example of using AsyncStreamlit in a Streamlit app."""
    st.title("Async Processing Example")

    # Create progress indicators
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Sample tasks
    def slow_task(n):
        time.sleep(1)  # Simulate slow operation
        return n * 2

    # Process tasks in parallel
    tasks = [lambda i=i: slow_task(i) for i in range(10)]

    results = []
    for _task_idx, result in AsyncStreamlit.parallel_progress(
        tasks, progress_bar=progress_bar, status_text=status_text, max_workers=5
    ):
        results.append(result)

    st.success(f"Processed {len(results)} tasks")
    st.write("Results:", results)
