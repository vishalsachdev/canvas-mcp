"""Tests for canvas-mcp-auth CLI login, manual flow, fallback, and argument validation."""

import re
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from canvas_mcp.auth import cli
from canvas_mcp.auth.models import OAuthError
from canvas_mcp.auth.store import TokenStore


def test_cli_missing_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "usage:" in err


def test_cli_negative_timeout(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["login", "--domain", "canvas.example.edu", "--timeout", "-1"])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "--timeout must be positive" in err


def test_cli_missing_domain_and_env(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CANVAS_API_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["login"])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Domain not provided" in err


def test_cli_invalid_domain(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["login", "--domain", "http://insecure.example.edu"])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Invalid Canvas domain" in err


def test_cli_manual_login_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_file = tmp_path / "tokens.json"
    custom_store = TokenStore(store_file)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "mobile_verify.json" in url_str:
            return httpx.Response(
                200,
                json={
                    "client_id": "cid-12345",
                    "client_secret": "csec-secret-value",
                    "base_url": "https://canvas.example.edu",
                    "authorized": True,
                },
            )
        elif "/login/oauth2/token" in url_str:
            return httpx.Response(
                200,
                json={
                    "access_token": "acc-token-real-secret",
                    "refresh_token": "ref-token-real-secret",
                    "token_type": "Bearer",
                    "user": {"id": 1234, "name": "Secret User Name"},
                },
            )
        elif "/api/v1/users/self" in url_str:
            return httpx.Response(
                200,
                json={"id": 1234, "name": "Secret User Name"},
            )
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    # Intercept stderr to extract generated state from authorization URL
    state_holder: list[str] = []

    def mock_getpass(prompt: str = "") -> str:
        # Extract state from captured stderr so far
        captured = capsys.readouterr().err
        match = re.search(r"[?&]state=([a-zA-Z0-9_-]+)", captured)
        assert match is not None, f"State not found in stderr output: {captured}"
        state = match.group(1)
        state_holder.append(state)
        return f"https://sso.canvaslms.com/canvas/login?code=auth_code_secret&state={state}"

    with patch.object(cli, "TokenStore", return_value=custom_store):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("getpass.getpass", side_effect=mock_getpass):
                cli.main(["login", "--domain", "canvas.example.edu", "--manual"])

    out = capsys.readouterr().out
    assert "Successfully authenticated" in out
    assert "Canvas host: canvas.example.edu" in out
    assert "User ID: 1234" in out
    assert str(store_file) in out

    # Secret leakage assertions: tokens, secrets, user name, and auth code must NEVER appear in output
    assert "acc-token-real-secret" not in out
    assert "ref-token-real-secret" not in out
    assert "csec-secret-value" not in out
    assert "Secret User Name" not in out
    assert "auth_code_secret" not in out

    # Verify store content
    saved = custom_store.load("canvas.example.edu")
    assert saved is not None
    assert saved.access_token.get_secret_value() == "acc-token-real-secret"
    assert saved.refresh_token.get_secret_value() == "ref-token-real-secret"
    assert saved.user is not None and saved.user.id == 1234


def test_cli_manual_login_cancellation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_file = tmp_path / "tokens.json"
    custom_store = TokenStore(store_file)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "client_id": "cid",
                "client_secret": "csec",
                "base_url": "https://canvas.example.edu",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    with patch.object(cli, "TokenStore", return_value=custom_store):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("getpass.getpass", side_effect=EOFError):
                with pytest.raises(SystemExit) as exc:
                    cli.main(["login", "--domain", "canvas.example.edu", "--manual"])
                assert exc.value.code == 1

    assert not store_file.exists()


def test_cli_browser_launch_failure_falls_back_when_interactive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_file = tmp_path / "tokens.json"
    custom_store = TokenStore(store_file)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "mobile_verify.json" in url_str:
            return httpx.Response(
                200,
                json={
                    "client_id": "cid",
                    "client_secret": "csec",
                    "base_url": "https://canvas.example.edu",
                },
            )
        elif "/login/oauth2/token" in url_str:
            return httpx.Response(
                200,
                json={
                    "access_token": "acc",
                    "refresh_token": "ref",
                    "user": {"id": 10, "name": "User"},
                },
            )
        elif "/api/v1/users/self" in url_str:
            return httpx.Response(200, json={"id": 10, "name": "User"})
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    stderr_chunks: list[str] = []

    def mock_getpass(prompt: str = "") -> str:
        chunk = capsys.readouterr().err
        stderr_chunks.append(chunk)
        match = re.search(r"[?&]state=([a-zA-Z0-9_-]+)", chunk)
        assert match is not None
        state = match.group(1)
        return f"https://sso.canvaslms.com/canvas/login?code=auth_code&state={state}"

    with patch.object(cli, "TokenStore", return_value=custom_store):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("sys.stdin.isatty", return_value=True):
                with patch(
                    "canvas_mcp.auth.cli.capture_authorization_code",
                    side_effect=OAuthError(
                        "Failed to launch Chromium browser: No display"
                    ),
                ):
                    with patch("getpass.getpass", side_effect=mock_getpass):
                        cli.main(["login", "--domain", "canvas.example.edu"])

    stderr_chunks.append(capsys.readouterr().err)
    all_err = "".join(stderr_chunks)
    assert "Browser launch unavailable" in all_err
    assert "Switching to manual login" in all_err
    assert custom_store.load("canvas.example.edu") is not None


def test_cli_browser_launch_failure_refuses_when_noninteractive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_file = tmp_path / "tokens.json"
    custom_store = TokenStore(store_file)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "client_id": "cid",
                "client_secret": "csec",
                "base_url": "https://canvas.example.edu",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    with patch.object(cli, "TokenStore", return_value=custom_store):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("sys.stdin.isatty", return_value=False):
                with patch(
                    "canvas_mcp.auth.cli.capture_authorization_code",
                    side_effect=OAuthError("Playwright is not installed"),
                ):
                    with pytest.raises(SystemExit) as exc:
                        cli.main(["login", "--domain", "canvas.example.edu"])
                    assert exc.value.code == 1

    err = capsys.readouterr().err
    assert "Run `canvas-mcp-auth login --manual` in an interactive terminal" in err
    assert not store_file.exists()


def test_cli_browser_denial_does_not_retry_or_fallback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_file = tmp_path / "tokens.json"
    custom_store = TokenStore(store_file)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "client_id": "cid",
                "client_secret": "csec",
                "base_url": "https://canvas.example.edu",
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    with patch.object(cli, "TokenStore", return_value=custom_store):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("sys.stdin.isatty", return_value=True):
                with patch(
                    "canvas_mcp.auth.cli.capture_authorization_code",
                    side_effect=OAuthError("Canvas OAuth authorization was denied."),
                ):
                    with pytest.raises(SystemExit) as exc:
                        cli.main(["login", "--domain", "canvas.example.edu"])
                    assert exc.value.code == 1

    err = capsys.readouterr().err
    assert "Canvas OAuth authorization was denied" in err
    assert "Switching to manual login" not in err
    assert not store_file.exists()
