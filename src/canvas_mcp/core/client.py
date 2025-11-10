"""HTTP client and Canvas API utilities."""

import asyncio
import sys
from typing import Any

import httpx

from .anonymization import anonymize_response_data

# Rate limit retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2

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
    """Get or create the HTTP client with current configuration."""
    global http_client
    if http_client is None:
        from .config import get_config
        config = get_config()
        http_client = httpx.AsyncClient(
            headers={
                'Authorization': f'Bearer {config.api_token}'
            },
            timeout=config.api_timeout
        )
    return http_client


async def cleanup_http_client() -> None:
    """Close the HTTP client and release resources."""
    global http_client
    if http_client is not None:
        await http_client.aclose()
        http_client = None


async def make_canvas_request(
    method: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    use_form_data: bool = False,
    skip_anonymization: bool = False
) -> Any:
    """Make a request to the Canvas API with proper error handling.

    Automatically retries on rate limit errors (429) with exponential backoff.

    Args:
        method: HTTP method (get, post, put, delete)
        endpoint: Canvas API endpoint
        params: Query parameters
        data: Request body data
        use_form_data: Use form data instead of JSON
        skip_anonymization: Skip anonymization (used by paginated fetchers)
    """

    from .config import get_config
    config = get_config()
    client = _get_http_client()

    # Ensure the endpoint starts with a slash
    if not endpoint.startswith('/'):
        endpoint = f"/{endpoint}"

    # Construct the full URL
    url = f"{config.api_base_url.rstrip('/')}{endpoint}"

    # Retry loop for rate limiting
    for attempt in range(MAX_RETRIES + 1):
        try:
            # Log the request for debugging (if enabled)
            if config.log_api_requests:
                retry_info = f" (retry {attempt}/{MAX_RETRIES})" if attempt > 0 else ""
                print(f"Making {method.upper()} request to {url}{retry_info}", file=sys.stderr)

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
            # Skip if explicitly requested (e.g., from paginated fetcher that will anonymize the full result)
            if not skip_anonymization and config.enable_data_anonymization and _should_anonymize_endpoint(endpoint):
                data_type = _determine_data_type(endpoint)
                result = anonymize_response_data(result, data_type)

                # Log anonymization for debugging (if enabled)
                if config.anonymization_debug:
                    print(f"🔒 Applied {data_type} anonymization to {endpoint}", file=sys.stderr)

            return result

        except httpx.HTTPStatusError as e:
            # Handle rate limiting with exponential backoff
            if e.response.status_code == 429 and attempt < MAX_RETRIES:
                # Check for Retry-After header
                retry_after = e.response.headers.get('Retry-After')
                if retry_after:
                    try:
                        wait_time = int(retry_after)
                    except ValueError:
                        wait_time = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                else:
                    wait_time = INITIAL_BACKOFF_SECONDS * (2 ** attempt)

                print(f"⏳ Rate limited (429). Retrying in {wait_time}s... (attempt {attempt + 1}/{MAX_RETRIES})", file=sys.stderr)
                await asyncio.sleep(wait_time)
                continue

            # Not a rate limit error or out of retries - format and return error
            error_message = f"HTTP error: {e.response.status_code}"
            try:
                error_details = e.response.json()
                error_message += f", Details: {error_details}"
            except ValueError:
                error_details = e.response.text
                error_message += f", Text: {error_details}"

            print(f"API error: {error_message}", file=sys.stderr)
            return {"error": error_message}

        except Exception as e:
            print(f"Request failed: {str(e)}", file=sys.stderr)
            return {"error": f"Request failed: {str(e)}"}

    # Should never reach here, but just in case
    return {"error": "Max retries exceeded"}


async def fetch_all_paginated_results(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    """Fetch all results from a paginated Canvas API endpoint.

    Handles pagination automatically and applies anonymization once to the complete dataset
    to ensure consistent anonymization across all pages.
    """
    if params is None:
        params = {}

    # Ensure we get a reasonable number per page
    if "per_page" not in params:
        params["per_page"] = 100

    all_results: list[Any] = []
    page = 1

    while True:
        current_params = {**params, "page": page}
        # Skip anonymization on individual pages - we'll anonymize the complete dataset
        response = await make_canvas_request("get", endpoint, params=current_params, skip_anonymization=True)

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
