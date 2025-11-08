"""HTTP client and Canvas API utilities."""

import asyncio
import sys
from typing import Any

import httpx

from .anonymization import anonymize_response_data
from .performance import monitor_performance

# HTTP client will be initialized with configuration
http_client: httpx.AsyncClient | None = None


def _determine_data_type(endpoint: str) -> str:
    """Determine the type of data based on the API endpoint."""
    endpoint_lower = endpoint.lower()

    if '/users' in endpoint_lower:
        return 'users'
    elif '/discussion_topics' in endpoint_lower and '/entries' in endpoint_lower:
        return 'discussions'
    elif '/discussion' in endpoint_lower:
        return 'discussions'
    elif '/submissions' in endpoint_lower:
        return 'submissions'
    elif '/assignments' in endpoint_lower:
        return 'assignments'
    elif '/enrollments' in endpoint_lower:
        return 'users'  # Enrollments contain user data
    else:
        return 'general'


def _should_anonymize_endpoint(endpoint: str) -> bool:
    """Determine if an endpoint should have its data anonymized."""
    # Don't anonymize these endpoints as they don't contain student data
    safe_endpoints = [
        '/courses',  # Course info without student data (unless it includes users)
        '/self',     # User's own profile
        '/accounts', # Account information
        '/terms',    # Academic terms
    ]

    endpoint_lower = endpoint.lower()

    # Always anonymize discussion entries as they contain student posts
    if '/discussion_topics' in endpoint_lower and '/entries' in endpoint_lower:
        return True

    # Check if it's a safe endpoint
    for safe in safe_endpoints:
        if safe in endpoint_lower and '/users' not in endpoint_lower:
            return False

    # Anonymize endpoints that contain student data
    student_data_endpoints = [
        '/users',
        '/discussion',
        '/submissions',
        '/enrollments',
        '/groups',
        '/analytics'
    ]

    return any(student_endpoint in endpoint_lower for student_endpoint in student_data_endpoints)


def _get_http_client() -> httpx.AsyncClient:
    """Get or create the HTTP client with optimized configuration.

    Optimizations:
    - Connection pooling (max 100 connections, max 20 per host)
    - HTTP/2 support for better performance
    - Keep-alive connections
    - Configurable timeout
    """
    global http_client
    if http_client is None:
        from .config import get_config
        config = get_config()

        # Configure connection limits for optimal performance
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=30.0
        )

        http_client = httpx.AsyncClient(
            headers={
                'Authorization': f'Bearer {config.api_token}'
            },
            timeout=config.api_timeout,
            limits=limits,
            http2=True,  # Enable HTTP/2 for better performance
            follow_redirects=True
        )
    return http_client


@monitor_performance()
async def make_canvas_request(
    method: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    use_form_data: bool = False,
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> Any:
    """Make a request to the Canvas API with retry logic and proper error handling.

    Args:
        method: HTTP method (get, post, put, delete)
        endpoint: API endpoint path
        params: Query parameters
        data: Request body data
        use_form_data: Whether to send data as form-encoded
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 1.0)

    Returns:
        JSON response from the API or error dict

    Implements exponential backoff for retries on transient errors.
    """

    last_error = None

    for attempt in range(max_retries + 1):
        try:
        from .config import get_config
        from .security import get_rate_limiter

        config = get_config()
        client = _get_http_client()

        # Check rate limiting
        rate_limiter = get_rate_limiter()
        allowed, rate_message = rate_limiter.check_rate_limit()
        if not allowed:
            return {"error": rate_message}

        # Ensure the endpoint starts with a slash
        if not endpoint.startswith('/'):
            endpoint = f"/{endpoint}"

        # Construct the full URL
        url = f"{config.api_base_url.rstrip('/')}{endpoint}"

        # Log the request for debugging (if enabled) - but sanitize URL params
        if config.log_api_requests:
            from .security import SecurityValidator
            safe_endpoint = SecurityValidator.sanitize_for_logging(endpoint)
            print(f"Making {method.upper()} request to endpoint: {safe_endpoint}", file=sys.stderr)

        if method.lower() == "get":
            response = await client.get(url, params=params)
        elif method.lower() == "post":
            if use_form_data:
                response = await client.post(url, data=data)
            else:
                response = await client.post(url, json=data)
        elif method.lower() == "put":
            if use_form_data:
                response = await client.put(url, data=data)
            else:
                response = await client.put(url, json=data)
        elif method.lower() == "delete":
            response = await client.delete(url, params=params)
        else:
            return {"error": f"Unsupported method: {method}"}

        response.raise_for_status()
        result = response.json()

        # Apply anonymization if enabled and this endpoint contains student data
        if config.enable_data_anonymization and _should_anonymize_endpoint(endpoint):
            data_type = _determine_data_type(endpoint)
            result = anonymize_response_data(result, data_type)

            # Log anonymization for debugging (if enabled)
            if config.anonymization_debug:
                print(f"🔒 Applied {data_type} anonymization to {endpoint}", file=sys.stderr)

        return result
    except httpx.HTTPStatusError as e:
        from .security import SecurityValidator

        error_message = f"HTTP error: {e.response.status_code}"

        # Only include error details in debug mode to avoid information leakage
        if config.debug:
            try:
                error_details = e.response.json()
                safe_details = SecurityValidator.sanitize_for_logging(error_details)
                error_message += f", Details: {safe_details}"
            except ValueError:
                # Don't include raw response text as it might contain sensitive info
                error_message += ", Response: Unable to parse error details"
        else:
            # Provide user-friendly error messages without internal details
            status_messages = {
                400: "Bad request - please check your input parameters",
                401: "Authentication failed - check your API token",
                403: "Access forbidden - insufficient permissions",
                404: "Resource not found",
                429: "Rate limit exceeded - please try again later",
                500: "Canvas server error - please try again later",
                503: "Canvas service unavailable - please try again later"
            }
            error_message = status_messages.get(
                e.response.status_code,
                f"Request failed with status {e.response.status_code}"
            )

        print(f"API error: {error_message}", file=sys.stderr)
        return {"error": error_message}

    except httpx.TimeoutException:
        error_message = "Request timed out - Canvas API may be slow or unavailable"
        print(f"Request error: {error_message}", file=sys.stderr)
        return {"error": error_message}

    except httpx.ConnectError:
        error_message = "Cannot connect to Canvas API - check your network and API URL"
        print(f"Connection error: {error_message}", file=sys.stderr)
        return {"error": error_message}

    except Exception as e:
        # Generic error handling - don't expose internal details
        if config.debug:
            error_message = f"Request failed: {str(e)}"
        else:
            error_message = "Request failed - please try again or contact support"

        print(f"Request failed: {str(e)}", file=sys.stderr)
        return {"error": error_message}


async def fetch_all_paginated_results(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    """Fetch all results from a paginated Canvas API endpoint."""
    if params is None:
        params = {}

    # Ensure we get a reasonable number per page
    if "per_page" not in params:
        params["per_page"] = 100

    all_results: list[Any] = []
    page = 1

    while True:
        current_params = {**params, "page": page}
        response = await make_canvas_request("get", endpoint, params=current_params)

        if isinstance(response, dict) and "error" in response:
            print(f"Error fetching page {page}: {response['error']}", file=sys.stderr)
            return response

        if not response or not isinstance(response, list) or len(response) == 0:
            break

        all_results.extend(response)

        # If we got fewer results than requested per page, we're done
        if len(response) < params.get("per_page", 100):
            break

        page += 1

    # Apply anonymization to the complete result set if needed
    from .config import get_config
    config = get_config()

    if config.enable_data_anonymization and _should_anonymize_endpoint(endpoint):
        data_type = _determine_data_type(endpoint)
        all_results = anonymize_response_data(all_results, data_type)

        if config.anonymization_debug:
            print(f"🔒 Applied {data_type} anonymization to paginated results from {endpoint}", file=sys.stderr)

    return all_results
