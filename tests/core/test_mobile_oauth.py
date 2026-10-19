"""Tests for Canvas mobile OAuth protocol, directory lookup, validation, and token exchange."""

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from canvas_mcp.auth.mobile import (
    REDIRECT_URI,
    build_authorization_url,
    exchange_authorization_code,
    extract_authorization_code,
    fetch_mobile_credentials,
    normalize_domain,
    verify_user_identity,
)
from canvas_mcp.auth.models import MobileCredentials, OAuthError, OAuthUser


def test_normalize_domain_valid_inputs() -> None:
    assert normalize_domain("canvas.example.edu") == "canvas.example.edu"
    assert normalize_domain("  CANVAS.EXAMPLE.EDU  ") == "canvas.example.edu"
    assert normalize_domain("https://canvas.example.edu") == "canvas.example.edu"
    assert normalize_domain("https://canvas.example.edu/") == "canvas.example.edu"
    assert normalize_domain("https://canvas.example.edu:443") == "canvas.example.edu"
    assert normalize_domain("https://canvas.example.edu:443/") == "canvas.example.edu"
    assert normalize_domain("https://canvas.example.edu/api/v1") == "canvas.example.edu"
    assert (
        normalize_domain("https://canvas.example.edu/api/v1/") == "canvas.example.edu"
    )
    assert normalize_domain("https://canvas.example.edu/api/v2") == "canvas.example.edu"


def test_normalize_domain_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_domain("")

    with pytest.raises(ValueError, match="non-default port"):
        normalize_domain("https://canvas.example.edu:8443")

    with pytest.raises(ValueError, match="requires HTTPS"):
        normalize_domain("http://canvas.example.edu")

    with pytest.raises(ValueError, match="userinfo"):
        normalize_domain("https://user:pass@canvas.example.edu")

    with pytest.raises(ValueError, match="query"):
        normalize_domain("https://canvas.example.edu?foo=bar")

    with pytest.raises(ValueError, match="fragment"):
        normalize_domain("https://canvas.example.edu#section")

    with pytest.raises(
        ValueError, match="Mobile OAuth requires a root-host Canvas URL"
    ):
        normalize_domain("https://canvas.example.edu/canvas/api/v1")


@pytest.mark.asyncio
async def test_fetch_mobile_credentials_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "sso.canvaslms.com"
        assert request.url.path == "/api/v1/mobile_verify.json"
        assert request.url.params["domain"] == "canvas.example.edu"
        assert request.headers["User-Agent"] == "candroid/8.6.1 (289)"
        return httpx.Response(
            200,
            json={
                "client_id": 10000000000001,
                "client_secret": "discovered-secret",
                "base_url": "https://canvas.example.edu",
                "authorized": True,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        creds = await fetch_mobile_credentials("canvas.example.edu", client=client)
        assert creds.client_id == "10000000000001"
        assert creds.client_secret.get_secret_value() == "discovered-secret"
        assert creds.base_url == "https://canvas.example.edu"


@pytest.mark.asyncio
async def test_fetch_mobile_credentials_cross_origin_refusal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "client_id": "client123",
                "client_secret": "secret123",
                "base_url": "https://different.instructure.com",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(
            OAuthError, match="different domain 'different.instructure.com'"
        ):
            await fetch_mobile_credentials("canvas.example.edu", client=client)


@pytest.mark.asyncio
async def test_fetch_mobile_credentials_unauthorized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"authorized": False, "client_id": "x", "client_secret": "y"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OAuthError, match="not authorized for mobile Canvas access"):
            await fetch_mobile_credentials("canvas.example.edu", client=client)


def test_build_authorization_url() -> None:
    url = build_authorization_url(
        "canvas.example.edu", "my-client-id", "my-state-token"
    )
    parsed = urlsplit(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "canvas.example.edu"
    assert parsed.path == "/login/oauth2/auth"
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["my-client-id"]
    assert qs["response_type"] == ["code"]
    assert qs["redirect_uri"] == [REDIRECT_URI]
    assert qs["mobile"] == ["1"]
    assert qs["state"] == ["my-state-token"]


def test_extract_authorization_code_valid() -> None:
    url = (
        "https://sso.canvaslms.com/canvas/login?code=auth_code_123&state=expected_state"
    )
    code = extract_authorization_code(url, "expected_state")
    assert code == "auth_code_123"


def test_extract_authorization_code_denied() -> None:
    url = "https://sso.canvaslms.com/canvas/login?error=access_denied&state=expected_state"
    with pytest.raises(OAuthError, match="authorization was denied"):
        extract_authorization_code(url, "expected_state")


def test_extract_authorization_code_invalid_host() -> None:
    # Attacker attempting domain deception
    url = (
        "https://sso.canvaslms.com.evil.test/canvas/login?code=123&state=expected_state"
    )
    with pytest.raises(OAuthError, match="Invalid redirect host"):
        extract_authorization_code(url, "expected_state")


def test_extract_authorization_code_state_mismatch() -> None:
    url = "https://sso.canvaslms.com/canvas/login?code=123&state=wrong_state"
    with pytest.raises(OAuthError, match="state mismatch"):
        extract_authorization_code(url, "expected_state")


def test_extract_authorization_code_duplicate_param() -> None:
    url = (
        "https://sso.canvaslms.com/canvas/login?code=123&code=456&state=expected_state"
    )
    with pytest.raises(OAuthError, match="Duplicate parameter"):
        extract_authorization_code(url, "expected_state")


@pytest.mark.asyncio
async def test_exchange_authorization_code_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "canvas.example.edu"
        assert request.url.path == "/login/oauth2/token"
        assert request.method == "POST"
        body = parse_qs(request.content.decode("utf-8"))
        assert body["grant_type"] == ["authorization_code"]
        assert body["client_id"] == ["cid"]
        assert body["client_secret"] == ["csec"]
        assert body["code"] == ["mycode"]
        assert body["redirect_uri"] == [REDIRECT_URI]

        return httpx.Response(
            200,
            json={
                "access_token": "acc-token-999",
                "refresh_token": "ref-token-888",
                "token_type": "Bearer",
                "user": {"id": 55, "name": "Jane Doe"},
            },
        )

    creds = MobileCredentials(
        client_id="cid", client_secret="csec", base_url="https://canvas.example.edu"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tokens = await exchange_authorization_code(
            "canvas.example.edu", creds, "mycode", client=client
        )
        assert tokens.canvas_domain == "canvas.example.edu"
        assert tokens.access_token.get_secret_value() == "acc-token-999"
        assert tokens.refresh_token.get_secret_value() == "ref-token-888"
        assert tokens.user is not None
        assert tokens.user.id == 55


@pytest.mark.asyncio
async def test_verify_user_identity_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer acc-token"
        return httpx.Response(200, json={"id": 999, "name": "Different User"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OAuthError, match="User identity mismatch"):
            await verify_user_identity(
                "canvas.example.edu",
                "acc-token",
                expected_user=OAuthUser(id=111, name="Original User"),
                client=client,
            )
