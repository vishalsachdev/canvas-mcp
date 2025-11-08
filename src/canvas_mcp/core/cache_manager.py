"""Enhanced caching system with TTL, statistics, and optional Redis support."""

import asyncio
import sys
import time
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """A cache entry with expiration time."""

    value: T
    expires_at: float
    created_at: float

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return time.time() > self.expires_at


class CacheStats:
    """Statistics tracker for cache operations."""

    def __init__(self) -> None:
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.expirations = 0
        self.evictions = 0

    @property
    def total_requests(self) -> int:
        """Total cache requests (hits + misses)."""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.hits / self.total_requests) * 100

    def reset(self) -> None:
        """Reset all statistics."""
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.expirations = 0
        self.evictions = 0

    def __str__(self) -> str:
        """Format statistics as a string."""
        return (
            f"Cache Stats: {self.hits} hits, {self.misses} misses, "
            f"{self.hit_rate:.1f}% hit rate, {self.sets} sets, "
            f"{self.deletes} deletes, {self.expirations} expirations"
        )


class EnhancedCache:
    """Enhanced cache with TTL support and statistics.

    Features:
    - Time-to-live (TTL) for cache entries
    - Cache statistics (hits, misses, hit rate)
    - Maximum cache size with LRU eviction
    - Background cleanup of expired entries
    """

    def __init__(self, default_ttl: int = 300, max_size: int = 1000) -> None:
        """Initialize the cache.

        Args:
            default_ttl: Default time-to-live in seconds (default: 300s = 5min)
            max_size: Maximum number of entries before eviction (default: 1000)
        """
        self._cache: dict[str, CacheEntry[Any]] = {}
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._stats = CacheStats()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._cleanup_interval = 60  # Clean up expired entries every 60 seconds

    def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: The cache key

        Returns:
            The cached value, or None if not found or expired
        """
        entry = self._cache.get(key)

        if entry is None:
            self._stats.misses += 1
            return None

        if entry.is_expired():
            self._stats.misses += 1
            self._stats.expirations += 1
            del self._cache[key]
            return None

        self._stats.hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: The cache key
            value: The value to cache
            ttl: Time-to-live in seconds (uses default_ttl if not specified)
        """
        if ttl is None:
            ttl = self._default_ttl

        # Evict oldest entries if cache is full
        if len(self._cache) >= self._max_size and key not in self._cache:
            self._evict_oldest()

        now = time.time()
        self._cache[key] = CacheEntry(
            value=value, expires_at=now + ttl, created_at=now
        )
        self._stats.sets += 1

    def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: The cache key

        Returns:
            True if the key was deleted, False if it didn't exist
        """
        if key in self._cache:
            del self._cache[key]
            self._stats.deletes += 1
            return True
        return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self._cache.clear()

    def _evict_oldest(self) -> None:
        """Evict the oldest entry from the cache (LRU)."""
        if not self._cache:
            return

        # Find the oldest entry by creation time
        oldest_key = min(self._cache.items(), key=lambda x: x[1].created_at)[0]
        del self._cache[oldest_key]
        self._stats.evictions += 1

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items() if entry.expires_at < now
        ]

        for key in expired_keys:
            del self._cache[key]
            self._stats.expirations += 1

        return len(expired_keys)

    async def start_cleanup_task(self) -> None:
        """Start background task to clean up expired entries."""
        if self._cleanup_task is not None:
            return

        async def cleanup_loop() -> None:
            while True:
                try:
                    await asyncio.sleep(self._cleanup_interval)
                    removed = self.cleanup_expired()
                    if removed > 0:
                        print(
                            f"🧹 Cache cleanup: removed {removed} expired entries",
                            file=sys.stderr,
                        )
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"Error in cache cleanup: {e}", file=sys.stderr)

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def stop_cleanup_task(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    @property
    def stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    @property
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)

    def print_stats(self) -> None:
        """Print cache statistics to stderr."""
        print(f"\n{self._stats}", file=sys.stderr)
        print(f"Cache size: {self.size}/{self._max_size}", file=sys.stderr)


# Global cache instances
_course_cache: EnhancedCache | None = None


def get_course_cache() -> EnhancedCache:
    """Get the global course cache instance."""
    global _course_cache
    if _course_cache is None:
        from .config import get_config

        config = get_config()
        _course_cache = EnhancedCache(default_ttl=config.cache_ttl)
    return _course_cache
