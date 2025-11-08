"""Benchmark script for cache performance."""

import asyncio
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from canvas_mcp.core.cache_manager import EnhancedCache


def benchmark_cache_operations(cache: EnhancedCache, num_operations: int = 10000) -> dict[str, float]:
    """Benchmark cache get/set operations.

    Args:
        cache: Cache instance to benchmark
        num_operations: Number of operations to perform

    Returns:
        Dict with benchmark results
    """
    results = {}

    # Benchmark SET operations
    start = time.perf_counter()
    for i in range(num_operations):
        cache.set(f"key_{i}", f"value_{i}")
    set_time = time.perf_counter() - start
    results["set_ops_per_sec"] = num_operations / set_time
    results["set_time_total"] = set_time

    # Benchmark GET operations (all hits)
    start = time.perf_counter()
    for i in range(num_operations):
        cache.get(f"key_{i}")
    get_time = time.perf_counter() - start
    results["get_ops_per_sec"] = num_operations / get_time
    results["get_time_total"] = get_time

    # Benchmark GET operations (all misses)
    start = time.perf_counter()
    for i in range(num_operations):
        cache.get(f"missing_key_{i}")
    miss_time = time.perf_counter() - start
    results["miss_ops_per_sec"] = num_operations / miss_time
    results["miss_time_total"] = miss_time

    # Benchmark DELETE operations
    start = time.perf_counter()
    for i in range(num_operations):
        cache.delete(f"key_{i}")
    delete_time = time.perf_counter() - start
    results["delete_ops_per_sec"] = num_operations / delete_time
    results["delete_time_total"] = delete_time

    return results


def print_benchmark_results(results: dict[str, float]) -> None:
    """Print benchmark results in a formatted table."""
    print("\n" + "=" * 70)
    print("CACHE PERFORMANCE BENCHMARK RESULTS")
    print("=" * 70)
    print(f"\n{'Operation':<20} {'Ops/Second':>15} {'Total Time':>15}")
    print("-" * 70)

    operations = [
        ("SET", "set_ops_per_sec", "set_time_total"),
        ("GET (hit)", "get_ops_per_sec", "get_time_total"),
        ("GET (miss)", "miss_ops_per_sec", "miss_time_total"),
        ("DELETE", "delete_ops_per_sec", "delete_time_total"),
    ]

    for op_name, ops_key, time_key in operations:
        ops_per_sec = results.get(ops_key, 0)
        total_time = results.get(time_key, 0)
        print(f"{op_name:<20} {ops_per_sec:>15,.0f} {total_time:>14.3f}s")

    print("=" * 70 + "\n")


def main() -> None:
    """Run cache benchmarks."""
    print("Starting cache performance benchmarks...")

    # Create cache instance
    cache = EnhancedCache(default_ttl=300, max_size=20000)

    # Run benchmarks with different sizes
    for size in [1000, 5000, 10000]:
        print(f"\nBenchmarking with {size:,} operations...")
        results = benchmark_cache_operations(cache, num_operations=size)
        print_benchmark_results(results)

        # Print cache statistics
        print("\nCache Statistics:")
        cache.print_stats()
        print()

        # Clear cache between runs
        cache.clear()
        cache.stats.reset()


if __name__ == "__main__":
    main()
