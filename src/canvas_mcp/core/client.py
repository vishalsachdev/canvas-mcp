"""HTTP client and Canvas API utilities."""

import asyncio
import re
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal
from urllib.parse import urlencode

import httpx

from .anonymization import anonymize_response_data, scrub_identity
from .credentials import get_request_credentials, is_http_request_active
from .logging import log_debug, log_error, log_warning, sanitize_url

# Rate limit retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2

# Default number of results per page for paginated requests
DEFAULT_PAGE_SIZE = 100
API_ROOT_REST = "rest"
API_ROOT_QUIZ = "quiz"


def _canvas_auth_headers(api_token: str) -> dict[str, str]:
    """Build the standard Canvas auth + User-Agent headers for a token."""
    from .. import __version__

    return {
        "Authorization": f"Bearer {api_token}",
        "User-Agent": f"canvas-mcp/{__version__} (https://github.com/vishalsachdev/canvas-mcp)",
    }

def _resolve_canvas_api_root(base_api_url: str, api_root: Literal["rest", "quiz"]) -> str:
    """Resolve a configured ``…/api/v<N>`` base URL to a selected Canvas API root.

    ``rest`` keeps the configured URL unchanged. ``quiz`` rewrites only the
    trailing API version segment to ``/api/quiz/v1`` while preserving any
    institution prefix (e.g. ``/lms``). This is an explicit call-site opt-in;
    endpoint strings never select a base path implicitly.
    """
    if api_root == API_ROOT_REST:
        return base_api_url

    match = re.search(r"/api/v\d+$", base_api_url)
    if not match:
        raise ValueError(
            "Invalid Canvas API base URL for quiz root resolution: expected trailing /api/v<N>"
        )

    return f"{base_api_url[:match.start()]}/api/quiz/v1"


# HTTP client will be initialized with configuration
http_client: httpx.AsyncClient | None = None
_http_client_loop_ref: "weakref.ref[asyncio.AbstractEventLoop] | None" = None  # weakref to the loop that owns http_client

# Concurrency limiter for outbound Canvas API calls
_request_semaphore: asyncio.Semaphore | None = None
_semaphore_loop_ref: "weakref.ref[asyncio.AbstractEventLoop] | None" = None  # weakref to the loop that owns _request_semaphore


def _get_request_semaphore() -> asyncio.Semaphore:
    """Get or create the concurrency semaphore from config.

    Recreates the semaphore when the running event loop has changed (e.g. after
    asyncio.run() closes one loop and mcp.run() starts a new one) to avoid
    "Event loop is closed" errors on asyncio synchronization primitives.

    A weakref to the creating loop is stored so that when the old loop is
    garbage-collected (as asyncio.run() does), the weakref goes dead and we
    detect the loop change reliably without relying on object id() reuse.
    """
    global _request_semaphore, _semaphore_loop_ref
    try:
        current_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    stored_loop = _semaphore_loop_ref() if _semaphore_loop_ref is not None else None

    if _request_semaphore is not None and current_loop is not None and stored_loop is not current_loop:
        _request_semaphore = None
        _semaphore_loop_ref = None

    if _request_semaphore is None:
        from .config import get_config
        _request_semaphore = asyncio.Semaphore(get_config().max_concurrent_requests)
        _semaphore_loop_ref = weakref.ref(current_loop) if current_loop is not None else None
    return _request_semaphore


def _path_segments(endpoint: str) -> list[str]:
    """Lower-cased, query-stripped path segments of a Canvas API endpoint."""
    path = endpoint.lower().split('?', 1)[0]
    return [seg for seg in path.split('/') if seg]


def _is_route_segment(segments: list[str], index: int) -> bool:
    """Whether segments[index] is a route keyword rather than a user slug.

    A segment directly after 'pages' is a user-controlled page slug — e.g. a
    page named "users" at /courses/{id}/pages/users — and must never be treated
    as a route keyword.
    """
    return not (index > 0 and segments[index - 1] == 'pages')


def _has_route_segment(segments: list[str], names: set[str]) -> bool:
    """Whether any route (non-slug) segment matches one of `names`."""
    return any(
        seg in names and _is_route_segment(segments, i)
        for i, seg in enumerate(segments)
    )


def _self_submission_indices(segments: list[str]) -> set[int]:
    """Indices of 'submissions' route segments followed by the literal 'self'.

    Anchored on the literal 'self' segment IMMEDIATELY after a 'submissions'
    route segment. A looser match (e.g. 'self' anywhere in the path) would
    recreate the #164 bypass class, where a broad short-circuit silently
    disabled anonymization for unrelated student-data endpoints.
    """
    return {
        i
        for i, seg in enumerate(segments)
        if seg == 'submissions'
        and _is_route_segment(segments, i)
        and i + 1 < len(segments)
        and segments[i + 1] == 'self'
    }


# Endpoints that describe ONLY the authenticated caller. Anonymizing these
# corrupts the caller's own identity (they would be told their name is
# "Student_<hash>"), which is a data-integrity bug, not a privacy win: FERPA
# protects a student's record FROM OTHERS, never from themselves.
#
# This is a deliberate loosening of a FERPA control, so it is an EXACT
# full-joined-path allowlist, never a prefix or substring rule. A looser form is
# exactly how #164/#166 happened. Notably NOT exempt (all still anonymized):
#   users/self/observees   -> other people (the observed students)
#   users/self/courses/... -> may embed other users
#   courses/*/enrollments, courses/*/users -> rosters
#   users/<other-id>/profile -> somebody else
#   users/self/enrollments -> looks self-only by its path but is NOT. Canvas
#       expands it with include[]=observed_users, which returns OTHER students'
#       records on observer enrollments. This gate sees only the path and cannot
#       see request parameters, so exempting the path would let those bypass
#       anonymization whenever that include is present. get_my_enrollments
#       deliberately reads /courses instead, so nothing needs this exemption.
_SELF_ONLY_ENDPOINTS = frozenset({
    "users/self",
    "users/self/profile",
})


def _is_self_only_endpoint(segments: list[str]) -> bool:
    """Whether the path is EXACTLY one of the caller-only endpoints."""
    return "/".join(segments) in _SELF_ONLY_ENDPOINTS


def _determine_data_type(endpoint: str) -> str:
    """Determine the type of data based on the API endpoint.

    Segment-aware (query string stripped, page slugs excluded) so that a
    substring match on a user-controlled slug cannot mis-route a response into
    the wrong typed handler.
    """
    segments = _path_segments(endpoint)

    if _has_route_segment(segments, {'users'}):
        return 'users'
    if _has_route_segment(segments, {'discussion_topics', 'discussion_entries'}):
        return 'discussions'
    if _has_route_segment(segments, {'submissions'}):
        return 'submissions'
    if _has_route_segment(segments, {'assignments'}):
        return 'assignments'
    if _has_route_segment(segments, {'enrollments'}):
        return 'users'  # Enrollments contain user data
    return 'general'


# --------------------------------------------------------------------------
# Anonymization tiers (issue #179)
# --------------------------------------------------------------------------
# A single boolean could not express the two endpoint families found by the
# #166 follow-up audit: /conversations needs the free-text half of the scrubber
# without the name half, /pages needs the name half without the free-text half.
# Forcing either into the all-or-nothing "full" tier costs real functionality,
# and leaving them at "none" (the pre-#179 state) leaks PII.

#: Not sensitive — response passes through untouched.
ANONYMIZE_NONE = "none"

#: Everything: recursive identity scrub + free-text redaction + the typed
#: refinements (submission-content redaction, long-description truncation).
ANONYMIZE_FULL = "full"

#: Identity only — names/avatars/direct identifiers scrubbed, free text kept.
ANONYMIZE_IDENTITY = "identity"

#: Free text only — emails/phones redacted from bodies, direct identifiers and
#: avatars nulled, but display names preserved.
ANONYMIZE_FREE_TEXT = "free_text"


def _endpoint_anonymization_mode(endpoint: str) -> str:
    """Which anonymization tier applies to `endpoint`.

    Sensitive-data checks MUST run before any safe-endpoint reasoning: almost
    every call here is scoped /courses/{id}/..., so a '/courses' short-circuit
    checked first silently disables anonymization for the whole codebase
    (issue #164). Anything not matched defaults to ANONYMIZE_NONE.

    The tiers are ordered most-protective-first, so a path that matches several
    families (e.g. /courses/1/pages plus a /users segment) gets the strongest
    treatment rather than the narrowest.

    Partially gated (issue #179) — matched, but NOT at the "full" tier:
    - /conversations, /conversations/{id} -> ANONYMIZE_FREE_TEXT. Previously
      ungated entirely: a live call returned 97 records with student email
      addresses inlined in `last_message`/`last_authored_message` plus
      participant pronouns and avatars. But this is the caller's OWN inbox, so
      the participants are their own correspondents, not third parties whose
      records they are browsing — pseudonymising `participants[].name` would
      make "who emailed me?" unanswerable while protecting nobody.
    - /pages, /courses/{id}/pages/{slug} -> ANONYMIZE_IDENTITY. Previously
      ungated: `last_edited_by` leaked a display name and avatar URL. Page
      *bodies* are deliberately exempt — instructors publish office hours,
      contact addresses and phone numbers on course pages, and redacting those
      would break the page's purpose.

    Intentionally NOT matched at all:
    - /groups listings — carry group names, not student names; generic
      anonymization would mangle them. Membership goes via /groups/{id}/users,
      which the '/users' rule covers.
    - /discussion_topics listings (incl. announcements) — typically
      instructor-authored; student content lives under the content endpoints
      matched below.
    - /submissions/self — the caller's OWN submission. Anonymizing it redacts
      body/url/attachments, so a student cannot read back what they submitted
      (issue #166). Only the literal 'self' sub-route is excluded; any other
      sensitive segment in the same path still forces anonymization.
    - the exact self-only paths in _SELF_ONLY_ENDPOINTS — the caller's OWN
      identity (issue #171). Exact full-path match only.
    """
    segments = _path_segments(endpoint)

    # Caller-only identity endpoints: exact-path allowlist, checked before the
    # sensitive-segment rules because 'users' would otherwise match.
    if _is_self_only_endpoint(segments):
        return ANONYMIZE_NONE

    # Drop only the 'submissions' segment of a /submissions/self route; every
    # other sensitive segment keeps its effect.
    self_indices = _self_submission_indices(segments)
    if self_indices:
        segments = [seg for i, seg in enumerate(segments) if i not in self_indices]

    # Discussion content endpoints carry student posts and names
    if 'discussion_topics' in segments and _has_route_segment(
        segments, {'entries', 'view', 'entry_list', 'replies'}
    ):
        return ANONYMIZE_FULL

    # Endpoints whose responses contain student records
    if _has_route_segment(segments, {'users', 'submissions', 'enrollments', 'analytics'}):
        return ANONYMIZE_FULL

    if _has_route_segment(segments, {'conversations'}):
        return ANONYMIZE_FREE_TEXT

    if _has_route_segment(segments, {'pages'}):
        return ANONYMIZE_IDENTITY

    return ANONYMIZE_NONE


def _should_anonymize_endpoint(endpoint: str) -> bool:
    """Whether `endpoint` gets any anonymization at all.

    Thin boolean view over :func:`_endpoint_anonymization_mode`. Callers that
    need to know *which* treatment applies must use the mode function; this one
    only answers "is this endpoint gated".
    """
    return _endpoint_anonymization_mode(endpoint) != ANONYMIZE_NONE


def _anonymize_for_endpoint(result: Any, endpoint: str) -> tuple[Any, str]:
    """Apply `endpoint`'s anonymization tier to a Canvas response.

    Returns the (possibly rewritten) payload plus a short label for debug
    logging. The identity/free_text tiers deliberately skip the typed
    refinements in ``_apply_type_refinements``: those exist for submission and
    assignment records, which neither /conversations nor /pages returns.
    """
    mode = _endpoint_anonymization_mode(endpoint)

    if mode == ANONYMIZE_FULL:
        data_type = _determine_data_type(endpoint)
        return anonymize_response_data(result, data_type), data_type
    if mode == ANONYMIZE_IDENTITY:
        return scrub_identity(result, scrub_text=False), mode
    if mode == ANONYMIZE_FREE_TEXT:
        return scrub_identity(result, scrub_display_names=False), mode
    return result, mode


def _get_http_client() -> httpx.AsyncClient:
    """Get or create the HTTP client with current configuration.

    Recreates the client when the running event loop has changed (e.g. after
    asyncio.run() closes one loop and mcp.run() starts a new one).  The stale
    client's internal anyio/asyncio connection-pool primitives are tied to the
    closed loop and will raise "Event loop is closed" on the first use.

    A weakref to the creating loop is stored so that when the old loop is
    garbage-collected (as asyncio.run() does), the weakref goes dead and we
    detect the loop change reliably without relying on object id() reuse.
    """
    global http_client, _http_client_loop_ref
    try:
        current_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    stored_loop = _http_client_loop_ref() if _http_client_loop_ref is not None else None

    if http_client is not None and (
        http_client.is_closed
        or (current_loop is not None and stored_loop is not current_loop)
    ):
        http_client = None
        _http_client_loop_ref = None

    if http_client is None:
        from .config import get_config
        config = get_config()
        http_client = httpx.AsyncClient(
            headers=_canvas_auth_headers(config.canvas_api_token),
            timeout=config.api_timeout
        )
        _http_client_loop_ref = weakref.ref(current_loop) if current_loop is not None else None
    return http_client


async def cleanup_http_client() -> None:
    """Close the HTTP client and release resources."""
    global http_client
    if http_client is not None:
        await http_client.aclose()
        http_client = None


@asynccontextmanager
async def canvas_authenticated_client() -> AsyncIterator[httpx.AsyncClient]:
    """Yield a Canvas-authenticated httpx client for the current context.

    Resolution, fail-closed:
    - Per-request credentials present (HTTP mode) -> a fresh client with the
      caller's token.
    - No per-request credentials but an HTTP request is active -> raise
      PermissionError (never fall back to the server's own token).
    - Otherwise (stdio mode) -> the shared global client (env-based token).
    """
    from .config import get_config

    req_creds = get_request_credentials()
    if req_creds:
        config = get_config()
        async with httpx.AsyncClient(
            headers=_canvas_auth_headers(req_creds.api_token),
            timeout=config.api_timeout,
        ) as client:
            yield client
        return

    if is_http_request_active():
        raise PermissionError("Canvas token required for HTTP request")

    yield _get_http_client()


async def make_canvas_request(
    method: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    use_form_data: bool = False,
    skip_anonymization: bool = False,
    files: dict[str, tuple[str, bytes, str]] | None = None,
    api_root: Literal["rest", "quiz"] = API_ROOT_REST,
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
        files: Dictionary of file objects for multipart form uploads
        api_root: Which Canvas API root to call ("rest" => /api/v<N>, "quiz" => /api/quiz/v1)
    """

    from .audit import log_data_access
    from .config import get_config

    config = get_config()

    # Check for per-request credentials (HTTP transport mode)
    req_creds = get_request_credentials()

    # Ensure the endpoint starts with a slash
    if not endpoint.startswith('/'):
        endpoint = f"/{endpoint}"

    if api_root not in (API_ROOT_REST, API_ROOT_QUIZ):
        return {"error": f"Unsupported api_root: {api_root}"}

    if req_creds:
        # Per-request client with user's credentials (HTTP mode)
        client = httpx.AsyncClient(
            headers=_canvas_auth_headers(req_creds.api_token),
            timeout=config.api_timeout,
        )
        try:
            base_url = _resolve_canvas_api_root(req_creds.api_url.rstrip('/'), api_root)
        except ValueError as exc:
            await client.aclose()
            return {"error": str(exc)}
        url = f"{base_url}{endpoint}"
        _close_client = True
    elif is_http_request_active():
        # HTTP request without a per-request token: fail closed. Never fall
        # back to the server's own credentials (would mis-attribute actions).
        log_warning(
            "Blocked Canvas API request without per-request Canvas token",
            endpoint=sanitize_url(endpoint),
        )
        return {"error": "Canvas token required for HTTP request"}
    else:
        # Global client (stdio mode)
        client = _get_http_client()
        try:
            base_url = _resolve_canvas_api_root(config.canvas_api_url.rstrip('/'), api_root)
        except ValueError as exc:
            return {"error": str(exc)}
        url = f"{base_url}{endpoint}"
        _close_client = False

    # Gate outbound calls with concurrency semaphore (uses MAX_CONCURRENT_REQUESTS)
    semaphore = _get_request_semaphore()
    async with semaphore:
        # Retry loop for rate limiting
        try:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    # Log the request for debugging (if enabled)
                    if config.log_api_requests:
                        retry_info = f" (retry {attempt}/{MAX_RETRIES})" if attempt > 0 else ""
                        log_debug(f"Making {method.upper()} request to {sanitize_url(url)}{retry_info}")

                    if method.lower() == "get":
                        response = await client.get(url, params=params)
                    elif method.lower() == "post":
                        if files:
                            response = await client.post(url, data=data, files=files)
                        elif use_form_data:
                            # Handle list of tuples separately to work around httpx async bug
                            # with duplicate keys (e.g., module[prerequisite_module_ids][])
                            if isinstance(data, list):
                                encoded = urlencode(data)
                                response = await client.post(
                                    url,
                                    content=encoded,
                                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                                )
                            else:
                                response = await client.post(url, data=data)
                        else:
                            response = await client.post(url, json=data)
                    elif method.lower() == "put":
                        if use_form_data:
                            # Handle list of tuples separately to work around httpx async bug
                            if isinstance(data, list):
                                encoded = urlencode(data)
                                response = await client.put(
                                    url,
                                    content=encoded,
                                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                                )
                            else:
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
                    if not skip_anonymization and config.enable_data_anonymization:
                        result, applied = _anonymize_for_endpoint(result, endpoint)

                        # Log anonymization for debugging (if enabled)
                        if config.anonymization_debug and applied != ANONYMIZE_NONE:
                            log_debug(f"Applied {applied} anonymization to {endpoint}")

                    # Audit: log successful data access
                    log_data_access(method, endpoint, "success")

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

                        log_warning(f"Rate limited (429). Retrying in {wait_time}s...", attempt=attempt + 1, max_retries=MAX_RETRIES)
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

                    log_error(f"API error on {sanitize_url(endpoint)}", status_code=e.response.status_code)

                    # Audit: log HTTP error (status code only — response body may contain PII)
                    log_data_access(method, endpoint, "error", f"HTTP {e.response.status_code}")

                    return {"error": error_message}

                except Exception as e:
                    log_error(f"Request failed for {sanitize_url(endpoint)}", error_type=type(e).__name__)

                    # Audit: log request exception (type only — message may contain PII)
                    log_data_access(method, endpoint, "error", type(e).__name__)

                    return {"error": f"Request failed: {str(e)}"}

            # Should never reach here, but just in case
            return {"error": "Max retries exceeded"}
        finally:
            if _close_client:
                await client.aclose()


async def upload_file_to_storage(
    upload_url: str,
    upload_params: dict[str, Any],
    file_path: str,
    filename: str,
    content_type: str
) -> dict[str, Any]:
    """Upload a file to Canvas storage URL (step 2 of 3-step upload process).

    This function handles the multipart file upload to S3/Instructure storage.
    It's called after requesting an upload URL from the Canvas API.

    Args:
        upload_url: The pre-signed upload URL from Canvas API
        upload_params: Additional parameters required by the storage (from Canvas API)
        file_path: Local filesystem path to the file
        filename: Name to use for the uploaded file
        content_type: MIME type of the file

    Returns:
        Response from the storage service, typically containing file confirmation
        or redirect location

    Note:
        This posts to external storage (S3/Instructure), not the Canvas API.
        The response handling differs from regular Canvas API calls.
    """
    from .config import get_config

    config = get_config()

    # Create a separate client for external uploads (no auth header needed)
    async with httpx.AsyncClient(timeout=config.api_timeout) as client:
        try:
            # Read the file content
            with open(file_path, 'rb') as f:
                file_content = f.read()

            # Build multipart form data
            # upload_params contains required fields like 'key', 'Policy', 'Signature', etc.
            files = {
                'file': (filename, file_content, content_type)
            }

            # Log for debugging
            if config.log_api_requests:
                log_debug(f"Uploading file to storage: {upload_url}", filename=filename, content_type=content_type, size=len(file_content))

            # Make the upload request
            # Note: follow_redirects=False because Canvas may return a 3xx with file info
            response = await client.post(
                upload_url,
                data=upload_params,
                files=files,
                follow_redirects=False
            )

            # Canvas storage upload can return:
            # - 200/201 with JSON body containing file info
            # - 301/302/303 redirect to Canvas API with file info
            if response.status_code in (200, 201):
                # Direct success response
                try:
                    return response.json()
                except ValueError:
                    # Some storage backends return empty success
                    return {"success": True, "status_code": response.status_code}

            elif response.status_code in (301, 302, 303):
                # Redirect - follow it to get file info from Canvas
                redirect_url = response.headers.get('Location')
                if redirect_url:
                    # Follow the redirect to get file info. This goes back to the
                    # Canvas API and needs auth; route through the shared
                    # fail-closed resolver so HTTP mode never uses the server's
                    # own token.
                    try:
                        async with canvas_authenticated_client() as canvas_client:
                            confirm_response = await canvas_client.get(redirect_url)
                            confirm_response.raise_for_status()
                            return confirm_response.json()
                    except PermissionError as e:
                        return {"error": str(e)}
                else:
                    return {"error": "Redirect without Location header"}

            else:
                # Unexpected status
                error_text = response.text
                return {
                    "error": f"Storage upload failed with status {response.status_code}",
                    "details": error_text
                }

        except FileNotFoundError:
            return {"error": f"File not found: {file_path}"}
        except PermissionError:
            return {"error": f"Permission denied reading file: {file_path}"}
        except httpx.TimeoutException:
            return {"error": "Upload timed out"}
        except Exception as e:
            return {"error": f"Upload failed: {str(e)}"}


async def fetch_all_paginated_results(
    endpoint: str,
    params: dict[str, Any] | None = None,
    skip_anonymization: bool = False,
) -> Any:
    """Fetch all results from a paginated Canvas API endpoint.

    Handles pagination automatically and applies anonymization once to the complete dataset
    to ensure consistent anonymization across all pages.

    Args:
        endpoint: Canvas API endpoint.
        params: Query parameters.
        skip_anonymization: Return the raw records. Reserved for the one caller
            whose whole purpose is to see real identities — the local
            pseudonym-map export. Anonymizing that fetch maps pseudonyms to
            pseudonyms, which is not a privacy win, just a broken tool.
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
            log_error(f"Error fetching page {page}", error=response['error'])
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

    if not skip_anonymization and config.enable_data_anonymization:
        all_results, applied = _anonymize_for_endpoint(all_results, endpoint)

        if config.anonymization_debug and applied != ANONYMIZE_NONE:
            log_debug(f"Applied {applied} anonymization to paginated results from {endpoint}")

    return all_results
