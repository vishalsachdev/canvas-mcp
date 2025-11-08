# Performance Optimization Guide

This document describes the performance optimizations implemented in Canvas MCP and best practices for optimal performance.

## Table of Contents

1. [Overview](#overview)
2. [Caching System](#caching-system)
3. [HTTP Client Optimizations](#http-client-optimizations)
4. [Performance Monitoring](#performance-monitoring)
5. [Best Practices](#best-practices)
6. [Benchmarks](#benchmarks)

## Overview

Canvas MCP includes several performance optimizations:

- **Enhanced caching** with TTL and statistics
- **Connection pooling** and HTTP/2 support
- **Retry logic** with exponential backoff
- **Performance monitoring** decorators
- **Optimized pagination** strategies

## Caching System

### Features

The enhanced caching system (`cache_manager.py`) provides:

- **Time-to-Live (TTL)**: Automatic expiration of cache entries
- **LRU Eviction**: Automatic removal of oldest entries when cache is full
- **Statistics Tracking**: Monitor cache hits, misses, and hit rate
- **Background Cleanup**: Automatic cleanup of expired entries

### Configuration

```python
# In .env file
CACHE_TTL=300  # Default TTL in seconds (5 minutes)
```

### Usage

```python
from canvas_mcp.core.cache_manager import get_course_cache

cache = get_course_cache()

# Set a value with default TTL
cache.set("key", "value")

# Set a value with custom TTL (in seconds)
cache.set("key", "value", ttl=600)

# Get a value
value = cache.get("key")  # Returns None if not found or expired

# Get cache statistics
stats = cache.stats
print(f"Hit rate: {stats.hit_rate:.1f}%")
print(f"Total hits: {stats.hits}")
print(f"Total misses: {stats.misses}")
```

### Cache Statistics

Monitor cache performance:

```python
cache.print_stats()
# Output:
# Cache Stats: 150 hits, 50 misses, 75.0% hit rate, 200 sets, 0 deletes, 10 expirations
# Cache size: 190/1000
```

## HTTP Client Optimizations

### Connection Pooling

The HTTP client uses connection pooling for better performance:

- **Max connections**: 100 total
- **Max keepalive connections**: 20 per host
- **Keepalive expiry**: 30 seconds
- **HTTP/2 support**: Enabled for multiplexing

### Retry Logic

Automatic retry with exponential backoff for transient errors:

- **Default retries**: 3 attempts
- **Initial delay**: 1 second
- **Backoff factor**: 2x (delays: 1s, 2s, 4s)
- **Retryable errors**: 429, 500, 502, 503, 504, timeouts, connection errors

### Rate Limiting

Built-in rate limiting to prevent API throttling:

- Configurable concurrent request limit
- Automatic request queuing
- Rate limit detection and backoff

## Performance Monitoring

### Monitor Function Performance

Use the `@monitor_performance()` decorator:

```python
from canvas_mcp.core.performance import monitor_performance

@monitor_performance()
async def my_function():
    # Your code here
    pass
```

### View Performance Statistics

```python
from canvas_mcp.core.performance import print_performance_stats

# Print performance report
print_performance_stats()
```

Output:
```
================================================================================
PERFORMANCE STATISTICS
================================================================================

Function                                           Calls      Total        Avg        Min        Max
--------------------------------------------------------------------------------
canvas_mcp.core.cache.refresh_course_cache             5      2.450s     0.490s     0.420s     0.580s
canvas_mcp.core.cache.get_course_id                  150      0.045s     0.000s     0.000s     0.002s
canvas_mcp.core.client.make_canvas_request           100      5.230s     0.052s     0.015s     0.320s
================================================================================
```

### Configure Monitoring

```python
from canvas_mcp.core.performance import (
    enable_performance_monitoring,
    set_slow_threshold,
    reset_performance_stats
)

# Enable/disable monitoring
enable_performance_monitoring(True)

# Set threshold for slow operation warnings (seconds)
set_slow_threshold(2.0)  # Warn if operation takes >2 seconds

# Reset statistics
reset_performance_stats()
```

## Best Practices

### 1. Use Caching Effectively

```python
# ✅ Good: Cache expensive API calls
cache = get_course_cache()
courses = cache.get("all_courses")
if courses is None:
    courses = await fetch_all_paginated_results("/courses")
    cache.set("all_courses", courses, ttl=300)

# ❌ Bad: Don't cache frequently changing data
cache.set("current_time", datetime.now(), ttl=3600)  # Will be stale quickly
```

### 2. Batch API Requests

```python
# ✅ Good: Fetch all at once with pagination
all_submissions = await fetch_all_paginated_results(
    f"/courses/{course_id}/assignments/{assignment_id}/submissions",
    {"per_page": 100}
)

# ❌ Bad: Individual requests in a loop
for user_id in user_ids:
    submission = await make_canvas_request(
        "get",
        f"/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}"
    )
```

### 3. Use Appropriate TTLs

- **Course data**: 300-600 seconds (5-10 minutes)
- **User data**: 600-1800 seconds (10-30 minutes)
- **Frequently changing data**: 60-120 seconds (1-2 minutes)
- **Static data**: 3600+ seconds (1+ hour)

### 4. Monitor Performance

```python
# Add monitoring to critical functions
@monitor_performance()
async def process_large_dataset():
    # Your code here
    pass

# Periodically check statistics
if debug_mode:
    print_performance_stats()
    cache.print_stats()
```

### 5. Optimize Pagination

```python
# ✅ Good: Use maximum per_page value
params = {"per_page": 100}  # Canvas maximum

# ❌ Bad: Small page sizes mean more requests
params = {"per_page": 10}  # Too many requests
```

### 6. Handle Errors Gracefully

```python
# Rely on built-in retry logic
result = await make_canvas_request("get", endpoint)
if isinstance(result, dict) and "error" in result:
    # Handle error
    logger.error(f"Request failed: {result['error']}")
```

## Benchmarks

### Cache Performance

Run the cache benchmark:

```bash
python benchmarks/benchmark_cache.py
```

Expected results (operations per second):

| Operation  | Ops/Second | Notes                    |
| ---------- | ---------- | ------------------------ |
| SET        | ~1,000,000 | Fast in-memory writes    |
| GET (hit)  | ~2,000,000 | Fast dictionary lookups  |
| GET (miss) | ~2,000,000 | Fast negative lookups    |
| DELETE     | ~1,500,000 | Fast deletions           |

### API Request Performance

Typical Canvas API response times:

| Operation              | Time     | Notes                   |
| ---------------------- | -------- | ----------------------- |
| Single course lookup   | 50-200ms | Cached: <1ms            |
| List courses (100)     | 200-500ms | Pagination included     |
| List submissions (100) | 300-800ms | Depends on data size    |
| Create discussion      | 100-300ms | POST request            |

### Memory Usage

Estimated memory per cached item:

- **Course mapping**: ~100 bytes
- **API response (100 items)**: ~50-200 KB
- **Cache overhead**: ~100 bytes per entry

Example: 1000 courses cached = ~100 KB

## Configuration Reference

Environment variables for performance tuning:

```bash
# Cache settings
CACHE_TTL=300                    # Default cache TTL in seconds

# HTTP client settings
API_TIMEOUT=30                   # Request timeout in seconds
MAX_CONCURRENT_REQUESTS=10       # Max concurrent API requests

# Monitoring settings
LOG_API_REQUESTS=false           # Log all API requests
DEBUG=false                      # Enable debug mode
```

## Troubleshooting

### High Memory Usage

1. Reduce cache TTL: `CACHE_TTL=60`
2. Monitor cache size: `cache.size`
3. Clear cache manually: `cache.clear()`

### Slow API Requests

1. Check network latency to Canvas
2. Review performance stats: `print_performance_stats()`
3. Enable HTTP/2: Ensure `httpx[http2]` is installed
4. Increase timeout: `API_TIMEOUT=60`

### Rate Limiting Issues

1. Reduce concurrent requests: `MAX_CONCURRENT_REQUESTS=5`
2. Add delays between requests
3. Check Canvas API rate limits

## Future Optimizations

Potential future improvements:

1. **Redis caching**: For distributed deployments
2. **Request deduplication**: Avoid duplicate in-flight requests
3. **Compression**: Enable gzip compression for large responses
4. **Lazy loading**: Defer loading of large data structures
5. **Database caching**: PostgreSQL/SQLite for persistent cache

## Contributing

When adding new features, please:

1. Add `@monitor_performance()` decorators to expensive functions
2. Use the enhanced cache for expensive API calls
3. Write benchmarks for performance-critical code
4. Document performance characteristics
5. Test with realistic data volumes
