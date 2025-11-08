"""HTTP utilities for retry logic and request optimization."""

import asyncio
import sys
from typing import Any, Callable

import httpx


async def retry_with_backoff(
    func: Callable[[], Any],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retryable_statuses: set[int] | None = None
) -> Any:
    """Retry a function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retries (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        backoff_factor: Multiplier for delay on each retry (default: 2.0)
        retryable_statuses: HTTP status codes to retry (default: 429, 500, 502, 503, 504)

    Returns:
        Result of the function call

    Raises:
        Last exception if all retries fail
    """
    if retryable_statuses is None:
        retryable_statuses = {429, 500, 502, 503, 504}

    last_exception = None
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except httpx.HTTPStatusError as e:
            last_exception = e

            # Check if this status code is retryable
            if e.response.status_code not in retryable_statuses:
                raise

            # Don't retry on last attempt
            if attempt == max_retries:
                raise

            # Log retry attempt
            print(
                f"⚠️  Request failed with status {e.response.status_code}, "
                f"retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})...",
                file=sys.stderr
            )

            # Wait with exponential backoff
            await asyncio.sleep(delay)
            delay *= backoff_factor

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exception = e

            # Don't retry on last attempt
            if attempt == max_retries:
                raise

            # Log retry attempt
            print(
                f"⚠️  Request failed ({type(e).__name__}), "
                f"retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})...",
                file=sys.stderr
            )

            # Wait with exponential backoff
            await asyncio.sleep(delay)
            delay *= backoff_factor

    # This should not be reached but satisfy type checker
    if last_exception:
        raise last_exception
