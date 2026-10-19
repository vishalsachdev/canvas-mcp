"""Tests for OAuth token refresh, single-flight concurrency, HTTP auth flow, and 401 replay."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import SecretStr

from canvas_mcp.auth.httpx_auth import MobileOAuthAuth
from canvas_mcp.auth.models import (
    OAuthRefreshError,
    OAuthUser,
    ReauthenticationRequired,
    StoredTokens,
)
from canvas_mcp.auth.session import OAuthSession
from canvas_mcp.auth.store import TokenStore


def _make_stored_tokens(
    domain: str = "canvas.example.edu",
    access_token: str = "old-access-tok",
    refresh_token: str = "valid-refresh-tok",
) -> StoredTokens:
    now = datetime.now(UTC)
    return StoredTokens(
        canvas_domain=domain,
        access_token=SecretStr(access_token),
        refresh_token=SecretStr(refresh_token),
        client_id="client-123",
        client_secret=SecretStr("client-secret-abc"),
        obtained_at=now,
        last_refreshed_at=now,
        user=OAuthUser(id=42, name="Test User"),
    )


@pytest.mark.asyncio
async def test_successful_refresh_and_replay_with_identical_body(
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)
    auth = MobileOAuthAuth(session)

    call_log: list[str] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        call_log.append(f"{request.method} {request.url}")
        auth_hdr = request.headers.get("Authorization", "")

        if request.url.path == "/login/oauth2/token":
            body = parse_qs(request.content.decode("utf-8"))
            assert body["grant_type"] == ["refresh_token"]
            assert body["refresh_token"] == ["valid-refresh-tok"]
            return httpx.Response(
                200,
                json={"access_token": "new-access-tok", "token_type": "Bearer"},
            )

        if request.url.path == "/api/v1/courses":
            if auth_hdr == "Bearer old-access-tok":
                return httpx.Response(401, json={"message": "Token expired"})
            elif auth_hdr == "Bearer new-access-tok":
                return httpx.Response(200, json=[{"id": 1, "name": "CS 101"}])
            return httpx.Response(403)

        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport, auth=auth) as client:
        # Patch session's internal client to use the mock transport
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
        ):
            resp = await client.get(
                "https://canvas.example.edu/api/v1/courses?per_page=10",
                headers={"X-Custom": "test-header"},
            )

    assert resp.status_code == 200
    assert resp.json() == [{"id": 1, "name": "CS 101"}]

    # Sequence: GET courses (401), POST refresh (200), replayed GET courses (200)
    assert call_log == [
        "GET https://canvas.example.edu/api/v1/courses?per_page=10",
        "POST https://canvas.example.edu/login/oauth2/token",
        "GET https://canvas.example.edu/api/v1/courses?per_page=10",
    ]

    # Verify store has the refreshed token
    saved = store.load("canvas.example.edu")
    assert saved is not None
    assert saved.access_token.get_secret_value() == "new-access-tok"


@pytest.mark.asyncio
async def test_burst_401_single_flight_deduplication(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)
    auth = MobileOAuthAuth(session)

    refresh_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal refresh_count
        auth_hdr = request.headers.get("Authorization", "")

        if request.url.path == "/login/oauth2/token":
            refresh_count += 1
            return httpx.Response(200, json={"access_token": "refreshed-tok"})

        if request.url.path.startswith("/api/v1/item/"):
            if auth_hdr == "Bearer old-access-tok":
                return httpx.Response(401, json={"error": "unauthorized"})
            elif auth_hdr == "Bearer refreshed-tok":
                return httpx.Response(200, json={"ok": True})

        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport, auth=auth) as client:
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
        ):
            tasks = [
                client.get(f"https://canvas.example.edu/api/v1/item/{i}")
                for i in range(20)
            ]
            responses = await asyncio.gather(*tasks)

    assert all(r.status_code == 200 for r in responses)
    # Exactly one refresh request must run across all 20 concurrent 401s
    assert refresh_count == 1


@pytest.mark.asyncio
async def test_failed_burst_deduplication(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)
    auth = MobileOAuthAuth(session)

    refresh_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal refresh_count
        if request.url.path == "/login/oauth2/token":
            refresh_count += 1
            return httpx.Response(500, json={"error": "server error"})
        if request.url.path == "/api/v1/test":
            return httpx.Response(401)
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport, auth=auth) as client:
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
        ):
            tasks = [
                client.get("https://canvas.example.edu/api/v1/test") for _ in range(5)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

    # All 5 requests receive the refresh failure
    for r in results:
        assert isinstance(r, OAuthRefreshError)

    # Exactly 1 refresh attempted for the failed burst
    assert refresh_count == 1


@pytest.mark.asyncio
async def test_waiter_cancellation_preserves_refresh(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)

    refresh_started = asyncio.Event()

    async def slow_refresh(*args: Any, **kwargs: Any) -> httpx.Response:
        refresh_started.set()
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={"access_token": "shielded-new-tok"})

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"access_token": "shielded-new-tok"})
        )
    )

    with patch.object(mock_client, "post", side_effect=slow_refresh):
        with patch("httpx.AsyncClient", return_value=mock_client):
            # Task 1 triggers refresh
            t1 = asyncio.create_task(session.refresh(0))
            await refresh_started.wait()

            # Task 2 also refreshes and gets cancelled
            t2 = asyncio.create_task(session.refresh(0))
            await asyncio.sleep(0.01)
            t2.cancel()

            with pytest.raises(asyncio.CancelledError):
                await t2

            # Task 1 succeeds
            res1 = await t1
            assert res1 == "shielded-new-tok"

    # Future snapshot returns the new token
    tok, gen = session.snapshot()
    assert tok == "shielded-new-tok"
    assert gen == 1


@pytest.mark.asyncio
async def test_second_401_terminates_without_looping(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)
    auth = MobileOAuthAuth(session)

    refresh_count = 0
    get_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal refresh_count, get_count
        if request.url.path == "/login/oauth2/token":
            refresh_count += 1
            return httpx.Response(200, json={"access_token": "tok2"})
        if request.url.path == "/api/v1/test":
            get_count += 1
            # Always return 401 even with refreshed token
            return httpx.Response(401, json={"error": "still unauthorized"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport, auth=auth) as client:
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
        ):
            resp = await client.get("https://canvas.example.edu/api/v1/test")

    assert resp.status_code == 401
    assert refresh_count == 1
    assert get_count == 2  # initial + 1 replay, then stop


@pytest.mark.asyncio
async def test_form_duplicate_keys_and_payload_integrity(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)
    auth = MobileOAuthAuth(session)

    received_bodies: list[bytes] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth2/token":
            return httpx.Response(200, json={"access_token": "new-tok"})
        if request.url.path == "/api/v1/form":
            received_bodies.append(request.content)
            if request.headers.get("Authorization") == "Bearer old-access-tok":
                return httpx.Response(401)
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    form_data = {"item": ["one", "two"], "flag": "true"}

    async with httpx.AsyncClient(transport=transport, auth=auth) as client:
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
        ):
            resp = await client.post(
                "https://canvas.example.edu/api/v1/form", data=form_data
            )

    assert resp.status_code == 200
    assert len(received_bodies) == 2
    # Exact byte match on replay
    assert received_bodies[0] == received_bodies[1]


@pytest.mark.asyncio
async def test_multipart_payload_integrity(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)
    auth = MobileOAuthAuth(session)

    received_bodies: list[bytes] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth2/token":
            return httpx.Response(200, json={"access_token": "new-tok"})
        if request.url.path == "/api/v1/upload":
            received_bodies.append(request.content)
            if request.headers.get("Authorization") == "Bearer old-access-tok":
                return httpx.Response(401)
            return httpx.Response(200, json={"uploaded": True})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    files = {"file": ("report.txt", b"secret report content", "text/plain")}

    async with httpx.AsyncClient(transport=transport, auth=auth) as client:
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
        ):
            resp = await client.post(
                "https://canvas.example.edu/api/v1/upload", files=files
            )

    assert resp.status_code == 200
    assert len(received_bodies) == 2
    assert received_bodies[0] == received_bodies[1]


@pytest.mark.asyncio
async def test_cross_origin_request_omits_auth_and_no_refresh(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)
    auth = MobileOAuthAuth(session)

    refresh_attempted = False

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal refresh_attempted
        if request.url.host == "storage.example.s3.amazonaws.com":
            assert "Authorization" not in request.headers
            return httpx.Response(401, text="Access Denied")
        if request.url.path == "/login/oauth2/token":
            refresh_attempted = True
            return httpx.Response(200, json={"access_token": "bad"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport, auth=auth) as client:
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
        ):
            resp = await client.get(
                "https://storage.example.s3.amazonaws.com/files/123.pdf"
            )

    assert resp.status_code == 401
    assert not refresh_attempted


@pytest.mark.asyncio
async def test_revoked_refresh_latches_reauthentication_without_deletion(
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)
    auth = MobileOAuthAuth(session)

    refresh_calls = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal refresh_calls
        if request.url.path == "/login/oauth2/token":
            refresh_calls += 1
            return httpx.Response(400, json={"error": "invalid_grant"})
        if request.url.path == "/api/v1/test":
            return httpx.Response(401)
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport, auth=auth) as client:
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
        ):
            with pytest.raises(ReauthenticationRequired) as exc:
                await client.get("https://canvas.example.edu/api/v1/test")
            assert "run canvas-mcp-auth login and restart" in str(exc.value)

            # Subsequent calls fail immediately from the latch without hitting token endpoint again
            with pytest.raises(ReauthenticationRequired):
                await client.get("https://canvas.example.edu/api/v1/test")

    assert refresh_calls == 1
    # Store still has the tokens (not deleted)
    assert store.load("canvas.example.edu") is not None


@pytest.mark.asyncio
async def test_persistence_failure_raises_oauth_refresh_error(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "refreshed-tok"})

    transport = httpx.MockTransport(mock_handler)
    with patch(
        "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
    ):
        with patch.object(store, "save", side_effect=OSError("Disk write error")):
            with pytest.raises(
                OAuthRefreshError, match="Failed to persist refreshed OAuth tokens"
            ):
                await session.refresh(0)

    # In-memory generation and token remain unchanged on failed persistence
    tok, gen = session.snapshot()
    assert tok == "old-access-tok"
    assert gen == 0


def test_session_loop_transition(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    tokens = _make_stored_tokens()
    store.save(tokens)
    session = OAuthSession(tokens, store)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "loop-tok"})

    transport = httpx.MockTransport(handler)

    async def run_in_loop() -> str:
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)
        ):
            return await session.refresh(session._generation)

    # Run in loop 1
    res1 = asyncio.run(run_in_loop())
    assert res1 == "loop-tok"

    # Run in loop 2 (new event loop)
    def handler2(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "loop-tok-2"})

    transport2 = httpx.MockTransport(handler2)

    async def run_in_loop2() -> str:
        with patch(
            "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport2)
        ):
            return await session.refresh(session._generation)

    res2 = asyncio.run(run_in_loop2())
    assert res2 == "loop-tok-2"
