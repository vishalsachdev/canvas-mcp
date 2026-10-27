"""In-memory OAuth session management, thread-safe single-flight refresh, and generation tracking."""

import asyncio
import logging
import weakref
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
from pydantic import SecretStr

from canvas_mcp.auth.mobile import REDIRECT_URI, normalize_domain
from canvas_mcp.auth.models import (
    OAuthError,
    OAuthRefreshError,
    OAuthUser,
    ReauthenticationRequired,
    StoredTokens,
    TokenStoreConflict,
)
from canvas_mcp.auth.store import TokenStore

if TYPE_CHECKING:
    from canvas_mcp.core.config import Config

logger = logging.getLogger(__name__)


class OAuthSession:
    """Manages memory credentials and single-flight token refresh for one domain."""

    def __init__(self, entry: StoredTokens, store: TokenStore) -> None:
        if entry.user is None:
            raise ReauthenticationRequired(
                "Canvas OAuth identity is unavailable; run canvas-mcp-auth login and restart the MCP server."
            )
        self._entry = entry
        self._store = store
        self._bound_user_id: int = entry.user.id
        self._bound_domain: str = entry.canvas_domain
        self._generation = 0
        self._latched_error: ReauthenticationRequired | None = None
        self._last_failure_time: float = 0.0
        self._last_failure_exc: OAuthError | None = None
        self._min_retry_interval: float = 1.0

        self._lock: asyncio.Lock | None = None
        self._refresh_task: asyncio.Task[str] | None = None
        self._loop_ref: weakref.ref[asyncio.AbstractEventLoop] | None = None

    def _require_bound_identity(self, entry: StoredTokens) -> None:
        if (
            entry.user is None
            or entry.user.id != self._bound_user_id
            or entry.canvas_domain != self._bound_domain
        ):
            latched = ReauthenticationRequired(
                "Canvas OAuth account changed or cannot be verified; run canvas-mcp-auth login and restart the MCP server."
            )
            self._latched_error = latched
            self._last_failure_exc = latched
            raise latched

    @property
    def canvas_domain(self) -> str:
        return self._entry.canvas_domain

    @property
    def store(self) -> TokenStore:
        return self._store

    def _ensure_loop_primitives(self) -> asyncio.Lock:
        current_loop = asyncio.get_running_loop()
        stored_loop = self._loop_ref() if self._loop_ref is not None else None

        if self._lock is None or stored_loop is not current_loop:
            self._lock = asyncio.Lock()
            self._refresh_task = None
            self._loop_ref = weakref.ref(current_loop)

        return self._lock

    def snapshot(self) -> tuple[str, int]:
        """Snapshot current access token and generation counter."""
        if self._latched_error is not None:
            raise self._latched_error
        return self._entry.access_token.get_secret_value(), self._generation

    async def refresh(self, observed_generation: int) -> str:
        """Refresh access token, single-flight deduplicated by generation."""
        if self._latched_error is not None:
            raise self._latched_error

        # If another request already refreshed past the observed generation
        if self._generation > observed_generation:
            return self._entry.access_token.get_secret_value()

        lock = self._ensure_loop_primitives()
        async with lock:
            if self._latched_error is not None:
                raise self._latched_error

            if self._generation > observed_generation:
                return self._entry.access_token.get_secret_value()

            # Check for an active _refresh_task before another caller performs store adoption
            if self._refresh_task is not None and not self._refresh_task.done():
                return await asyncio.shield(self._refresh_task)

            # Check if another process refreshed the store on disk/keyring
            stored = await asyncio.to_thread(self._store.load, self._bound_domain)
            if stored is not None:
                self._require_bound_identity(stored)
                if (
                    stored.last_refreshed_at > self._entry.last_refreshed_at
                    or stored.access_token.get_secret_value()
                    != self._entry.access_token.get_secret_value()
                ):
                    self._entry = stored
                    self._generation += 1
                    self._last_failure_exc = None
                    return self._entry.access_token.get_secret_value()

            # Deduplicate rapid concurrent burst immediately after failure
            loop = asyncio.get_running_loop()
            now = loop.time()
            if (
                self._last_failure_exc is not None
                and (now - self._last_failure_time) < self._min_retry_interval
            ):
                raise self._last_failure_exc

            self._refresh_task = asyncio.create_task(self._do_refresh())

        return await asyncio.shield(self._refresh_task)

    async def _do_refresh(self) -> str:
        loop = asyncio.get_running_loop()
        base_entry = self._entry
        self._require_bound_identity(base_entry)

        norm_domain = normalize_domain(base_entry.canvas_domain)
        token_url = f"https://{norm_domain}/login/oauth2/token"
        form_data = {
            "grant_type": "refresh_token",
            "client_id": base_entry.client_id,
            "client_secret": base_entry.client_secret.get_secret_value(),
            "refresh_token": base_entry.refresh_token.get_secret_value(),
            "redirect_uri": REDIRECT_URI,
        }

        try:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=False
            ) as client:
                resp = await client.post(token_url, data=form_data)
        except httpx.RequestError as exc:
            network_err = OAuthRefreshError(
                f"Network error refreshing OAuth token: {type(exc).__name__}"
            )
            self._last_failure_exc = network_err
            self._last_failure_time = loop.time()
            raise network_err from exc

        if resp.status_code in (400, 401):
            latched = ReauthenticationRequired(
                "Canvas OAuth session rejected; run canvas-mcp-auth login and restart the MCP server."
            )
            self._latched_error = latched
            self._last_failure_exc = latched
            self._last_failure_time = loop.time()
            raise latched

        if resp.status_code != 200:
            status_err = OAuthRefreshError(
                f"OAuth token refresh rejected with HTTP {resp.status_code}"
            )
            self._last_failure_exc = status_err
            self._last_failure_time = loop.time()
            raise status_err

        try:
            data = resp.json()
        except Exception as exc:
            json_err = OAuthRefreshError("Malformed JSON response from token refresh")
            self._last_failure_exc = json_err
            self._last_failure_time = loop.time()
            raise json_err from exc

        if not isinstance(data, dict):
            non_obj_err = OAuthRefreshError("Token refresh returned non-object response")
            self._last_failure_exc = non_obj_err
            self._last_failure_time = loop.time()
            raise non_obj_err

        access_token_val = data.get("access_token")
        if (
            not access_token_val
            or not isinstance(access_token_val, str)
            or not access_token_val.strip()
        ):
            missing_tok_err = OAuthRefreshError("Token refresh response missing access_token")
            self._last_failure_exc = missing_tok_err
            self._last_failure_time = loop.time()
            raise missing_tok_err

        # Optional replacement refresh token
        new_refresh = data.get("refresh_token")
        if new_refresh and isinstance(new_refresh, str) and new_refresh.strip():
            refresh_secret = SecretStr(new_refresh.strip())
        else:
            refresh_secret = base_entry.refresh_token

        # User verification if present
        user_obj = base_entry.user
        if "user" in data:
            user_data = data.get("user")
            if not isinstance(user_data, dict):
                malformed_err = OAuthRefreshError("Malformed user object in token refresh response")
                self._last_failure_exc = malformed_err
                self._last_failure_time = loop.time()
                raise malformed_err
            new_uid = user_data.get("id")
            new_name = user_data.get("name")
            if (
                not isinstance(new_uid, int)
                or isinstance(new_uid, bool)
                or not isinstance(new_name, str)
                or not new_name.strip()
            ):
                invalid_user_err = OAuthRefreshError("Invalid user identity in token refresh response")
                self._last_failure_exc = invalid_user_err
                self._last_failure_time = loop.time()
                raise invalid_user_err
            if new_uid != self._bound_user_id:
                latched = ReauthenticationRequired(
                    "Canvas OAuth account changed or cannot be verified; run canvas-mcp-auth login and restart the MCP server."
                )
                self._latched_error = latched
                self._last_failure_exc = latched
                self._last_failure_time = loop.time()
                raise latched
            user_obj = OAuthUser(id=new_uid, name=new_name)

        now = datetime.now(UTC)
        updated_entry = StoredTokens(
            canvas_domain=base_entry.canvas_domain,
            access_token=SecretStr(access_token_val.strip()),
            refresh_token=refresh_secret,
            client_id=base_entry.client_id,
            client_secret=base_entry.client_secret,
            obtained_at=base_entry.obtained_at,
            last_refreshed_at=now,
            user=user_obj,
        )
        self._require_bound_identity(updated_entry)

        try:
            await asyncio.to_thread(
                self._store.save, updated_entry, expected=base_entry
            )
        except TokenStoreConflict as exc:
            # Check if another process refreshed the store concurrently
            reloaded = await asyncio.to_thread(self._store.load, base_entry.canvas_domain)
            if reloaded is not None:
                self._require_bound_identity(reloaded)
                if (
                    reloaded.last_refreshed_at > base_entry.last_refreshed_at
                    or reloaded.access_token.get_secret_value()
                    != base_entry.access_token.get_secret_value()
                ):
                    if self._latched_error is not None:
                        raise self._latched_error
                    self._entry = reloaded
                    self._generation += 1
                    self._last_failure_exc = None
                    return reloaded.access_token.get_secret_value()

            conflict_err = TokenStoreConflict(
                "Token store conflict: credentials modified by another process; restart server."
            )
            self._last_failure_exc = conflict_err
            self._last_failure_time = loop.time()
            raise conflict_err from exc
        except Exception as exc:
            persist_err = OAuthRefreshError(f"Failed to persist refreshed OAuth tokens: {exc}")
            self._last_failure_exc = persist_err
            self._last_failure_time = loop.time()
            raise persist_err from exc

        if self._latched_error is not None:
            raise self._latched_error

        # Publish new state
        self._require_bound_identity(updated_entry)
        self._entry = updated_entry
        self._generation += 1
        self._last_failure_exc = None
        return str(access_token_val).strip()


_session_cache: dict[tuple[int, str, str], OAuthSession] = {}


def get_stdio_oauth(config: "Config | None" = None) -> OAuthSession | None:
    """Retrieve or construct the active OAuth session for stdio mode.

    Returns None if:
    - An HTTP request is active
    - Config has a non-empty Personal Access Token (PAT)
    - CANVAS_API_URL is missing or invalid
    - No stored token exists for CANVAS_API_URL's domain
    """
    from canvas_mcp.core.credentials import (
        get_request_credentials,
        is_http_request_active,
    )

    # In HTTP mode, each request supplies its own token; stdio OAuth is inactive
    if is_http_request_active() or get_request_credentials() is not None:
        return None

    from canvas_mcp.core.config import get_config

    cfg = config if config is not None else get_config()

    # PAT takes strict precedence over stored OAuth tokens
    pat = getattr(cfg, "canvas_api_token", None) or getattr(cfg, "api_token", None)
    if pat and str(pat).strip():
        return None

    api_url = getattr(cfg, "canvas_api_url", None) or getattr(cfg, "api_url", None)
    if not api_url or not str(api_url).strip():
        return None

    try:
        norm_domain = normalize_domain(str(api_url))
    except Exception:
        return None

    try:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
    except RuntimeError:
        loop_id = 0
    cache_key = (loop_id, norm_domain, str(api_url))

    session = _session_cache.get(cache_key)
    if session is not None:
        return session

    store = TokenStore()
    entry = store.load(norm_domain)
    if entry is None:
        return None

    session = OAuthSession(entry, store)
    _session_cache[cache_key] = session
    return session


def clear_stdio_oauth_cache() -> None:
    """Clear the cached stdio OAuth sessions (primarily for tests)."""
    _session_cache.clear()
