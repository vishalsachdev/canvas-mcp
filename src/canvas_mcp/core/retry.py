"""Retry and rate limiting utilities for API calls."""

import asyncio
import time
from collections import deque
from functools import wraps
from typing import Any, Callable, TypeVar

import httpx

from .logging import log_error, log_info

T = TypeVar('T')


class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(self, requests_per_second: float = 10.0, burst_size: int = 20):
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate
            burst_size: Maximum burst of requests allowed
        """
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size
        self.tokens = float(burst_size)
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a request (blocks if rate limit exceeded)."""
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_update

            # Refill tokens based on elapsed time
            self.tokens = min(
                self.burst_size,
                self.tokens + elapsed * self.requests_per_second
            )
            self.last_update = now

            # If we don't have a token, wait until we do
            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.requests_per_second
                await asyncio.sleep(wait_time)

                # Update tokens after waiting
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(
                    self.burst_size,
                    self.tokens + elapsed * self.requests_per_second
                )
                self.last_update = now

            # Consume one token
            self.tokens -= 1


class AdaptiveRateLimiter:
    """Adaptive rate limiter that adjusts based on 429 responses."""

    def __init__(self, initial_rate: float = 10.0, min_rate: float = 1.0, max_rate: float = 20.0):
        """Initialize adaptive rate limiter.

        Args:
            initial_rate: Initial requests per second
            min_rate: Minimum requests per second
            max_rate: Maximum requests per second
        """
        self.current_rate = initial_rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.limiter = RateLimiter(requests_per_second=initial_rate)
        self.recent_429s = deque(maxlen=10)
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a request."""
        await self.limiter.acquire()

    async def record_429(self) -> None:
        """Record a 429 response and reduce rate."""
        async with self.lock:
            self.recent_429s.append(time.time())

            # Reduce rate by 50%
            new_rate = max(self.min_rate, self.current_rate * 0.5)
            if new_rate != self.current_rate:
                self.current_rate = new_rate
                self.limiter = RateLimiter(requests_per_second=new_rate)
                log_info(f"Rate limit hit, reducing to {new_rate} req/s")

    async def record_success(self) -> None:
        """Record a successful request and potentially increase rate."""
        async with self.lock:
            now = time.time()

            # Remove old 429s (older than 60 seconds)
            while self.recent_429s and now - self.recent_429s[0] > 60:
                self.recent_429s.popleft()

            # If no recent 429s, gradually increase rate
            if not self.recent_429s:
                new_rate = min(self.max_rate, self.current_rate * 1.1)
                if new_rate != self.current_rate:
                    self.current_rate = new_rate
                    self.limiter = RateLimiter(requests_per_second=new_rate)


# Global rate limiter instance
_global_rate_limiter: AdaptiveRateLimiter | None = None


def get_rate_limiter() -> AdaptiveRateLimiter:
    """Get or create the global rate limiter."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = AdaptiveRateLimiter()
    return _global_rate_limiter


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    **kwargs: Any
) -> Any:
    """Retry a function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for the function
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        **kwargs: Keyword arguments for the function

    Returns:
        Result from the function

    Raises:
        The last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            last_exception = e

            # Don't retry on client errors (except 429)
            if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                raise

            # For 429, use retry-after header if available
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        pass

                # Record 429 for adaptive rate limiting
                rate_limiter = get_rate_limiter()
                await rate_limiter.record_429()

            if attempt < max_retries:
                log_info(f"Request failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.2f}s: {e}")
                await asyncio.sleep(delay)
                delay = min(max_delay, delay * exponential_base)
            else:
                log_error(f"Request failed after {max_retries + 1} attempts", exc=e)
                raise

        except (httpx.RequestError, asyncio.TimeoutError) as e:
            last_exception = e

            if attempt < max_retries:
                log_info(f"Network error (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.2f}s: {e}")
                await asyncio.sleep(delay)
                delay = min(max_delay, delay * exponential_base)
            else:
                log_error(f"Network error after {max_retries + 1} attempts", exc=e)
                raise

    # This should never be reached, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry loop completed without success or exception")


def with_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to add retry logic to async functions.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff

    Returns:
        Decorator function
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await retry_with_backoff(
                func,
                *args,
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                **kwargs
            )
        return wrapper
    return decorator


def with_rate_limit(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to add rate limiting to async functions.

    Args:
        func: Async function to rate limit

    Returns:
        Wrapped function with rate limiting
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        rate_limiter = get_rate_limiter()
        await rate_limiter.acquire()

        try:
            result = await func(*args, **kwargs)
            await rate_limiter.record_success()
            return result
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                await rate_limiter.record_429()
            raise

    return wrapper
