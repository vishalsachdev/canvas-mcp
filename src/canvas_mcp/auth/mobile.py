"""Mobile OAuth protocol utilities, endpoint constants, and domain validation."""

import re
import secrets
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from pydantic import SecretStr

from canvas_mcp.auth.models import (
    MobileCredentials,
    OAuthError,
    OAuthUser,
    StoredTokens,
)

MOBILE_VERIFY_URL = "https://sso.canvaslms.com/api/v1/mobile_verify.json"
MOBILE_USER_AGENT = "candroid/8.6.1 (289)"
REDIRECT_URI = "https://sso.canvaslms.com/canvas/login"
OAUTH_PURPOSE = "Canvas MCP"


def normalize_domain(value: str) -> str:
    """Normalize a Canvas domain or URL to a canonical DNS hostname.

    Accepts bare hostnames (e.g. 'canvas.example.edu') or HTTPS URLs with root path
    or '/api/v<N>' (e.g. 'https://canvas.example.edu/api/v1').

    Rejects userinfo, query, fragment, non-HTTPS schemes, non-default ports, and
    institution path prefixes.
    """
    raw = value.strip()
    if not raw:
        raise ValueError("Domain cannot be empty")

    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() != "https":
            raise ValueError(
                f"Mobile OAuth requires HTTPS URL, got scheme '{parsed.scheme}'"
            )
    else:
        # If there's an explicit scheme-like prefix without :// (e.g. http:example.com)
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw):
            raise ValueError("Mobile OAuth requires HTTPS URL or bare hostname")
        parsed = urlsplit(f"https://{raw}")

    if parsed.username or parsed.password:
        raise ValueError("Mobile OAuth URLs cannot contain userinfo credentials")

    if parsed.query:
        raise ValueError("Mobile OAuth URLs cannot contain query parameters")

    if parsed.fragment:
        raise ValueError("Mobile OAuth URLs cannot contain fragments")

    if not parsed.hostname:
        raise ValueError("Invalid domain: missing hostname")

    # Port checking
    try:
        port = parsed.port
    except ValueError as e:
        raise ValueError(f"Invalid port in domain: {e}") from e

    if port is not None and port != 443:
        raise ValueError(
            f"Mobile OAuth requires default HTTPS port (443), got non-default port {port}"
        )

    # Path checking
    path = parsed.path.rstrip("/")
    if path:
        if not re.fullmatch(r"/api/v\d+", path):
            raise ValueError(
                "Mobile OAuth requires a root-host Canvas URL; use a PAT for prefixed deployments."
            )

    try:
        normalized_host = parsed.hostname.encode("idna").decode("ascii").lower()
    except Exception as e:
        raise ValueError(f"Invalid domain encoding: {e}") from e

    if not normalized_host:
        raise ValueError("Invalid domain: empty normalized hostname")

    return normalized_host


def build_authorization_url(domain: str, client_id: str, state: str) -> str:
    """Build the Canvas mobile OAuth authorization URL."""
    norm_domain = normalize_domain(domain)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "mobile": "1",
        "purpose": OAUTH_PURPOSE,
        "state": state,
    }
    query = urlencode(params)
    return f"https://{norm_domain}/login/oauth2/auth?{query}"


async def fetch_mobile_credentials(
    domain: str,
    *,
    client: httpx.AsyncClient,
) -> MobileCredentials:
    """Discover Canvas mobile client_id and client_secret from SSO mobile_verify endpoint."""
    norm_domain = normalize_domain(domain)
    try:
        resp = await client.get(
            MOBILE_VERIFY_URL,
            params={"domain": norm_domain, "user_agent": MOBILE_USER_AGENT},
            headers={"User-Agent": MOBILE_USER_AGENT},
            timeout=10.0,
            follow_redirects=False,
        )
    except httpx.RequestError as e:
        raise OAuthError(
            f"Network error querying mobile verification directory: {type(e).__name__}"
        ) from e

    if resp.status_code != 200:
        raise OAuthError(
            f"Mobile verification directory returned HTTP {resp.status_code}"
        )

    try:
        data = resp.json()
    except Exception as e:
        raise OAuthError("Malformed JSON from mobile verification directory") from e

    if not isinstance(data, dict):
        raise OAuthError("Mobile verification directory returned non-object response")

    if data.get("authorized") is False:
        raise OAuthError(
            f"Domain '{norm_domain}' is not authorized for mobile Canvas access"
        )

    raw_client_id = data.get("client_id")
    if raw_client_id is None or not str(raw_client_id).strip():
        raise OAuthError("Mobile verification did not return a valid client_id")
    client_id = str(raw_client_id).strip()

    raw_secret = data.get("client_secret")
    if not raw_secret or not str(raw_secret).strip():
        raise OAuthError("Mobile verification did not return a valid client_secret")
    client_secret = SecretStr(str(raw_secret).strip())

    raw_base_url = data.get("base_url")
    if raw_base_url and str(raw_base_url).strip():
        base_url_str = str(raw_base_url).strip()
        norm_base_domain = normalize_domain(base_url_str)
        if norm_base_domain != norm_domain:
            raise OAuthError(
                f"Mobile directory returned different domain '{norm_base_domain}' than requested '{norm_domain}'. "
                f"Verify the institution domain and explicitly rerun login with --domain {norm_base_domain}."
            )
        base_url = f"https://{norm_base_domain}"
    else:
        base_url = f"https://{norm_domain}"

    return MobileCredentials(
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
    )


def extract_authorization_code(redirect_url: str, expected_state: str) -> str:
    """Extract and validate the authorization code and state from callback URL."""
    if not isinstance(redirect_url, str) or not redirect_url.strip():
        raise OAuthError("Redirect URL is empty")

    parsed = urlsplit(redirect_url.strip())
    if parsed.scheme.lower() != "https":
        raise OAuthError(
            f"Invalid redirect scheme: expected https, got '{parsed.scheme}'"
        )

    if not parsed.hostname or parsed.hostname.lower() != "sso.canvaslms.com":
        raise OAuthError(
            f"Invalid redirect host: expected 'sso.canvaslms.com', got '{parsed.hostname}'"
        )

    try:
        port = parsed.port
    except ValueError as e:
        raise OAuthError(f"Invalid port in redirect URL: {e}") from e

    if port is not None and port != 443:
        raise OAuthError(f"Invalid non-default port in redirect URL: {port}")

    if parsed.path.rstrip("/") != "/canvas/login":
        raise OAuthError(
            f"Invalid redirect path: expected '/canvas/login', got '{parsed.path}'"
        )

    if parsed.username or parsed.password:
        raise OAuthError("Redirect URL cannot contain user credentials")

    if parsed.fragment:
        raise OAuthError("Redirect URL cannot contain a fragment")

    query_params = parse_qs(parsed.query, keep_blank_values=True)

    # Check duplicate query parameters
    for k, v in query_params.items():
        if len(v) != 1:
            raise OAuthError(f"Duplicate parameter '{k}' in callback URL")

    if "error" in query_params:
        state_list = query_params.get("state")
        if state_list and secrets.compare_digest(state_list[0], expected_state):
            raise OAuthError("Canvas OAuth authorization was denied.")
        raise OAuthError("Canvas OAuth authorization was denied.")

    if "code" not in query_params or not query_params["code"][0].strip():
        raise OAuthError("Missing authorization code in redirect URL")

    if "state" not in query_params or not query_params["state"][0].strip():
        raise OAuthError("Missing state parameter in redirect URL")

    returned_state = query_params["state"][0]
    if not secrets.compare_digest(returned_state, expected_state):
        raise OAuthError("Canvas OAuth callback state mismatch.")

    return query_params["code"][0].strip()


async def exchange_authorization_code(
    domain: str,
    credentials: MobileCredentials,
    code: str,
    *,
    client: httpx.AsyncClient,
) -> StoredTokens:
    """Exchange authorization code for access and refresh tokens at Canvas token endpoint."""
    norm_domain = normalize_domain(domain)
    token_url = f"https://{norm_domain}/login/oauth2/token"
    form_data = {
        "grant_type": "authorization_code",
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret.get_secret_value(),
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    try:
        resp = await client.post(
            token_url,
            data=form_data,
            timeout=15.0,
            follow_redirects=False,
        )
    except httpx.RequestError as e:
        raise OAuthError(
            f"Network error during token exchange: {type(e).__name__}"
        ) from e

    if resp.status_code != 200:
        raise OAuthError(f"Token exchange failed with HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:
        raise OAuthError("Malformed JSON response from token exchange") from e

    if not isinstance(data, dict):
        raise OAuthError("Token exchange returned non-object response")

    access_token = data.get("access_token")
    if (
        not access_token
        or not isinstance(access_token, str)
        or not access_token.strip()
    ):
        raise OAuthError("Token exchange did not return a valid access_token")

    refresh_token = data.get("refresh_token")
    if (
        not refresh_token
        or not isinstance(refresh_token, str)
        or not refresh_token.strip()
    ):
        raise OAuthError("Token exchange did not return a valid refresh_token")

    token_type = data.get("token_type")
    if token_type is not None:
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise OAuthError(f"Incompatible token_type returned: {token_type}")

    user_obj: OAuthUser | None = None
    user_data = data.get("user")
    if user_data is not None and isinstance(user_data, dict):
        uid = user_data.get("id")
        uname = user_data.get("name")
        if (
            isinstance(uid, int)
            and not isinstance(uid, bool)
            and isinstance(uname, str)
            and uname.strip()
        ):
            user_obj = OAuthUser(id=uid, name=uname)

    now = datetime.now(UTC)
    return StoredTokens(
        canvas_domain=norm_domain,
        access_token=SecretStr(access_token),
        refresh_token=SecretStr(refresh_token),
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        obtained_at=now,
        last_refreshed_at=now,
        user=user_obj,
    )


async def verify_user_identity(
    domain: str,
    access_token: str,
    *,
    expected_user: OAuthUser | None = None,
    client: httpx.AsyncClient,
) -> OAuthUser:
    """Verify user identity via GET /api/v1/users/self."""
    norm_domain = normalize_domain(domain)
    user_url = f"https://{norm_domain}/api/v1/users/self"
    try:
        resp = await client.get(
            user_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
            follow_redirects=False,
        )
    except httpx.RequestError as e:
        raise OAuthError(
            f"Network error reading user identity: {type(e).__name__}"
        ) from e

    if resp.status_code != 200:
        raise OAuthError(
            f"User identity verification failed with HTTP {resp.status_code}"
        )

    try:
        data = resp.json()
    except Exception as e:
        raise OAuthError("Malformed JSON response from user identity endpoint") from e

    if not isinstance(data, dict):
        raise OAuthError("User identity endpoint returned non-object response")

    uid = data.get("id")
    uname = data.get("name")
    if uid is None or not isinstance(uid, int) or isinstance(uid, bool):
        raise OAuthError(
            "User identity response did not contain a valid integer user id"
        )

    if not isinstance(uname, str) or not uname.strip():
        uname = f"User {uid}"

    verified = OAuthUser(id=uid, name=uname)
    if expected_user is not None and expected_user.id != verified.id:
        raise OAuthError(
            f"User identity mismatch: token exchange returned user {expected_user.id}, "
            f"but /users/self returned user {verified.id}"
        )

    return verified
