"""Performance monitoring and profiling utilities."""

import functools
import sys
import time
from collections import defaultdict
from typing import Any, Callable, TypeVar, cast

# Global performance statistics
_perf_stats: dict[str, dict[str, Any]] = defaultdict(
    lambda: {
        "calls": 0,
        "total_time": 0.0,
        "min_time": float("inf"),
        "max_time": 0.0,
        "errors": 0,
    }
)

# Performance monitoring configuration
_perf_enabled = True
_perf_slow_threshold = 1.0  # Log warnings for operations taking >1 second


def enable_performance_monitoring(enabled: bool = True) -> None:
    """Enable or disable performance monitoring."""
    global _perf_enabled
    _perf_enabled = enabled


def set_slow_threshold(seconds: float) -> None:
    """Set the threshold for logging slow operations."""
    global _perf_slow_threshold
    _perf_slow_threshold = seconds


def get_performance_stats() -> dict[str, dict[str, Any]]:
    """Get all performance statistics."""
    return dict(_perf_stats)


def reset_performance_stats() -> None:
    """Reset all performance statistics."""
    _perf_stats.clear()


def print_performance_stats() -> None:
    """Print a formatted performance statistics report."""
    if not _perf_stats:
        print("No performance statistics available.", file=sys.stderr)
        return

    print("\n" + "=" * 80, file=sys.stderr)
    print("PERFORMANCE STATISTICS", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    # Sort by total time descending
    sorted_stats = sorted(
        _perf_stats.items(), key=lambda x: x[1]["total_time"], reverse=True
    )

    print(f"\n{'Function':<50} {'Calls':>8} {'Total':>10} {'Avg':>10} {'Min':>10} {'Max':>10}", file=sys.stderr)
    print("-" * 80, file=sys.stderr)

    for func_name, stats in sorted_stats:
        calls = stats["calls"]
        total = stats["total_time"]
        avg = total / calls if calls > 0 else 0
        min_time = stats["min_time"] if stats["min_time"] != float("inf") else 0
        max_time = stats["max_time"]

        # Truncate function name if too long
        display_name = func_name if len(func_name) <= 50 else func_name[:47] + "..."

        print(
            f"{display_name:<50} {calls:>8} {total:>9.3f}s {avg:>9.3f}s {min_time:>9.3f}s {max_time:>9.3f}s",
            file=sys.stderr,
        )

        if stats["errors"] > 0:
            print(f"  └─ Errors: {stats['errors']}", file=sys.stderr)

    print("=" * 80 + "\n", file=sys.stderr)


F = TypeVar("F", bound=Callable[..., Any])


def monitor_performance(func_name: str | None = None) -> Callable[[F], F]:
    """Decorator to monitor function performance.

    Args:
        func_name: Optional custom name for the function (defaults to qualified name)

    Example:
        @monitor_performance()
        async def my_function():
            ...
    """

    def decorator(func: F) -> F:
        nonlocal func_name
        if func_name is None:
            func_name = f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _perf_enabled:
                return await func(*args, **kwargs)

            start_time = time.perf_counter()
            error_occurred = False

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error_occurred = True
                raise
            finally:
                elapsed = time.perf_counter() - start_time

                # Update statistics
                stats = _perf_stats[func_name]
                stats["calls"] += 1
                stats["total_time"] += elapsed
                stats["min_time"] = min(stats["min_time"], elapsed)
                stats["max_time"] = max(stats["max_time"], elapsed)
                if error_occurred:
                    stats["errors"] += 1

                # Log slow operations
                if elapsed > _perf_slow_threshold:
                    print(
                        f"⚠️  SLOW: {func_name} took {elapsed:.3f}s (threshold: {_perf_slow_threshold}s)",
                        file=sys.stderr,
                    )

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _perf_enabled:
                return func(*args, **kwargs)

            start_time = time.perf_counter()
            error_occurred = False

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error_occurred = True
                raise
            finally:
                elapsed = time.perf_counter() - start_time

                # Update statistics
                stats = _perf_stats[func_name]
                stats["calls"] += 1
                stats["total_time"] += elapsed
                stats["min_time"] = min(stats["min_time"], elapsed)
                stats["max_time"] = max(stats["max_time"], elapsed)
                if error_occurred:
                    stats["errors"] += 1

                # Log slow operations
                if elapsed > _perf_slow_threshold:
                    print(
                        f"⚠️  SLOW: {func_name} took {elapsed:.3f}s (threshold: {_perf_slow_threshold}s)",
                        file=sys.stderr,
                    )

        # Return the appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        else:
            return cast(F, sync_wrapper)

    return decorator


# Add asyncio import at the top
import asyncio
