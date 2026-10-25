"""Observe file-transfer credentials at the HTTP transport boundary."""

from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from canvas_mcp.core import client as client_module
from canvas_mcp.core.credentials import clear_http_request_context
from canvas_mcp.tools import files as file_tools

CANVAS = "https://canvas.example.com"
STORAGE = "https://files.example.net"
TOKEN = "synthetic-canvas-token"


@pytest_asyncio.fixture
async def transfer_http(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    """Keep real clients and request construction; replace only the network."""
    requests: list[httpx.Request] = []
    routes: dict[str, httpx.Response] = {}
    clients: list[httpx.AsyncClient] = []
    real_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return routes.get(str(request.url), httpx.Response(200, content=b"file bytes"))

    def make_client(**kwargs: Any) -> httpx.AsyncClient:
        client = real_client(transport=httpx.MockTransport(respond), **kwargs)
        clients.append(client)
        return client

    config = SimpleNamespace(
        canvas_api_url=f"{CANVAS}/api/v1",
        canvas_api_token=TOKEN,
        api_timeout=30,
        log_api_requests=False,
        read_file_max_size_mb=100,
    )
    clear_http_request_context()
    monkeypatch.setattr("canvas_mcp.core.config.get_config", lambda: config)
    monkeypatch.setattr(file_tools, "get_config", lambda: config)
    monkeypatch.setattr(httpx, "AsyncClient", make_client)
    monkeypatch.setattr(client_module, "http_client", None)
    monkeypatch.setattr(client_module, "_http_client_loop_ref", None)
    yield SimpleNamespace(
        requests=requests, routes=routes, config=config, clients=clients
    )
    await client_module.cleanup_http_client()
    for client in clients:
        await client.aclose()
    clear_http_request_context()


@pytest.fixture
def file_tool(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    """Capture the actual decorated tool functions without replacing their bodies."""
    from fastmcp import FastMCP

    mcp = FastMCP("file-origin-tests")
    captured: dict[str, Any] = {}
    original_tool = mcp.tool

    def tool(*args: Any, **kwargs: Any) -> Any:
        decorate = original_tool(*args, **kwargs)

        def register(fn: Callable[..., Any]) -> Any:
            captured[fn.__name__] = fn
            return decorate(fn)

        return register

    monkeypatch.setattr(mcp, "tool", tool)
    file_tools.register_shared_file_tools(mcp)
    monkeypatch.setattr(
        file_tools, "resolve_numeric_course_id", AsyncMock(return_value=("42", None))
    )
    monkeypatch.setattr(file_tools, "get_course_code", AsyncMock(return_value="COURSE"))
    return captured.__getitem__


@pytest.mark.asyncio
async def test_upload_does_not_send_token_to_storage_selected_origin(
    transfer_http: Any, tmp_path: Any
) -> None:
    upload = tmp_path / "upload.txt"
    upload.write_bytes(b"upload content")
    transfer_http.routes[f"{STORAGE}/upload"] = httpx.Response(
        303, headers={"Location": "https://attacker.example/collect"}
    )
    transfer_http.routes["https://attacker.example/collect"] = httpx.Response(
        200, json={"id": 7}
    )

    result = await client_module.upload_file_to_storage(
        f"{STORAGE}/upload", {}, str(upload), "upload.txt", "text/plain"
    )

    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == [(f"{STORAGE}/upload", None)]
    assert "error" in result
    await client_module.cleanup_http_client()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["read_course_file", "download_course_file"])
async def test_off_origin_download_has_no_canvas_token(
    transfer_http: Any,
    file_tool: Any,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
) -> None:
    monkeypatch.setattr(
        file_tools,
        "make_canvas_request",
        AsyncMock(
            return_value={
                "id": 7,
                "display_name": "file.txt",
                "url": f"{STORAGE}/direct",
                "size": 10,
                "content-type": "text/plain",
            }
        ),
    )
    kwargs = (
        {"save_directory": str(tmp_path)} if tool_name == "download_course_file" else {}
    )
    result = await file_tool(tool_name)("42", "7", **kwargs)

    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == [(f"{STORAGE}/direct", None)]
    assert not result.startswith("Error")
    if tool_name == "download_course_file":
        assert (tmp_path / "file.txt").read_bytes() == b"file bytes"
    else:
        assert "ZmlsZSBieXRlcw==" in result
    await client_module.cleanup_http_client()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303])
@pytest.mark.parametrize(
    "target",
    [
        "https://canvas.example.com.attacker.net/confirm",
        "https://sub.canvas.example.com/confirm",
        "https://canvas.example.com:8443/confirm",
        "http://canvas.example.com/confirm",
        "https://canvas.example.com@attacker.example/confirm",
        "//attacker.example/confirm",
        "/relative-confirm",
        "ftp://canvas.example.com/confirm",
    ],
)
async def test_upload_refuses_non_canvas_confirmation(
    transfer_http: Any,
    tmp_path: Any,
    status: int,
    target: str,
) -> None:
    upload = tmp_path / "upload.txt"
    upload.write_bytes(b"upload content")
    transfer_http.routes[f"{STORAGE}/upload"] = httpx.Response(
        status, headers={"Location": target}
    )
    result = await client_module.upload_file_to_storage(
        f"{STORAGE}/upload", {}, str(upload), "upload.txt", "text/plain"
    )
    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == [(f"{STORAGE}/upload", None)]
    assert "error" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target",
    [
        f"{CANVAS}/confirm",
        "https://CANVAS.example.com:443/confirm",
        "/confirm",
        "//canvas.example.com/confirm",
    ],
)
async def test_upload_confirms_only_on_canvas_origin(
    transfer_http: Any,
    tmp_path: Any,
    target: str,
) -> None:
    upload = tmp_path / "upload.txt"
    upload.write_bytes(b"upload content")
    transfer_http.routes[f"{CANVAS}/upload"] = httpx.Response(
        303, headers={"Location": target}
    )
    transfer_http.routes[f"{CANVAS}/confirm"] = httpx.Response(201, json={"id": 7})
    result = await client_module.upload_file_to_storage(
        f"{CANVAS}/upload", {}, str(upload), "upload.txt", "text/plain"
    )
    assert [
        (r.method, str(r.url), r.headers.get("Authorization"))
        for r in transfer_http.requests
    ] == [
        ("POST", f"{CANVAS}/upload", None),
        ("GET", f"{CANVAS}/confirm", f"Bearer {TOKEN}"),
    ]
    assert result == {"id": 7}


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [f"{STORAGE}/collect", f"{CANVAS}/other"])
async def test_upload_confirmation_does_not_follow_another_redirect(
    transfer_http: Any,
    tmp_path: Any,
    target: str,
) -> None:
    upload = tmp_path / "upload.txt"
    upload.write_bytes(b"upload content")
    transfer_http.routes[f"{STORAGE}/upload"] = httpx.Response(
        303, headers={"Location": f"{CANVAS}/confirm"}
    )
    transfer_http.routes[f"{CANVAS}/confirm"] = httpx.Response(
        302, headers={"Location": target}
    )
    result = await client_module.upload_file_to_storage(
        f"{STORAGE}/upload", {}, str(upload), "upload.txt", "text/plain"
    )
    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == [(f"{STORAGE}/upload", None), (f"{CANVAS}/confirm", f"Bearer {TOKEN}")]
    assert "error" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["read_course_file", "download_course_file"])
@pytest.mark.parametrize(
    ("url", "sent_url", "authorization"),
    [
        (f"{CANVAS}/file", f"{CANVAS}/file", f"Bearer {TOKEN}"),
        ("https://CANVAS.example.com:443/file", f"{CANVAS}/file", f"Bearer {TOKEN}"),
        (
            "https://canvas.example.com.attacker.net/file",
            "https://canvas.example.com.attacker.net/file",
            None,
        ),
        (
            "https://sub.canvas.example.com/file",
            "https://sub.canvas.example.com/file",
            None,
        ),
        (
            "https://canvas.example.com:8443/file",
            "https://canvas.example.com:8443/file",
            None,
        ),
        ("http://canvas.example.com/file", "http://canvas.example.com/file", None),
        (
            "https://canvas.example.com@attacker.example/file",
            "https://canvas.example.com@attacker.example/file",
            None,
        ),
    ],
)
async def test_download_origin_boundaries(
    transfer_http: Any,
    file_tool: Any,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    url: str,
    sent_url: str,
    authorization: str | None,
) -> None:
    monkeypatch.setattr(
        file_tools,
        "make_canvas_request",
        AsyncMock(
            return_value={
                "id": 7,
                "display_name": "file.txt",
                "url": url,
                "size": 10,
                "content-type": "text/plain",
            }
        ),
    )
    kwargs = (
        {"save_directory": str(tmp_path)} if tool_name == "download_course_file" else {}
    )
    result = await file_tool(tool_name)("42", "7", **kwargs)
    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == [(sent_url, authorization)]
    assert not result.startswith("Error")


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["read_course_file", "download_course_file"])
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize(
    ("start", "locations", "expected"),
    [
        (
            f"{CANVAS}/file",
            ["/signed?verifier=synthetic"],
            [
                (f"{CANVAS}/file", f"Bearer {TOKEN}"),
                (f"{CANVAS}/signed?verifier=synthetic", f"Bearer {TOKEN}"),
            ],
        ),
        (
            f"{CANVAS}/file",
            [f"{STORAGE}/signed?sig=synthetic", f"{CANVAS}/back"],
            [
                (f"{CANVAS}/file", f"Bearer {TOKEN}"),
                (f"{STORAGE}/signed?sig=synthetic", None),
                (f"{CANVAS}/back", None),
            ],
        ),
        (
            f"{STORAGE}/file",
            [f"{CANVAS}/back"],
            [
                (f"{STORAGE}/file", None),
                (f"{CANVAS}/back", None),
            ],
        ),
        (
            f"{CANVAS}/file",
            ["//canvas.example.com.attacker.net/collect"],
            [
                (f"{CANVAS}/file", f"Bearer {TOKEN}"),
                ("https://canvas.example.com.attacker.net/collect", None),
            ],
        ),
        (
            f"{CANVAS}/file",
            ["https://canvas.example.com:8443/file"],
            [
                (f"{CANVAS}/file", f"Bearer {TOKEN}"),
                ("https://canvas.example.com:8443/file", None),
            ],
        ),
    ],
)
async def test_download_scopes_every_redirect_hop(
    transfer_http: Any,
    file_tool: Any,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    status: int,
    start: str,
    locations: list[str],
    expected: list[tuple[str, str | None]],
) -> None:
    current = start
    for location in locations:
        transfer_http.routes[current] = httpx.Response(
            status, headers={"Location": location}
        )
        current = str(httpx.URL(current).join(location))
    monkeypatch.setattr(
        file_tools,
        "make_canvas_request",
        AsyncMock(
            return_value={
                "id": 7,
                "display_name": "file.txt",
                "url": start,
                "size": 10,
                "content-type": "text/plain",
            }
        ),
    )
    kwargs = (
        {"save_directory": str(tmp_path)} if tool_name == "download_course_file" else {}
    )
    result = await file_tool(tool_name)("42", "7", **kwargs)
    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == expected
    assert not result.startswith("Error")
    if tool_name == "download_course_file":
        assert (tmp_path / "file.txt").read_bytes() == b"file bytes"
    else:
        assert "ZmlsZSBieXRlcw==" in result


@pytest.mark.asyncio
async def test_download_strips_token_on_same_host_scheme_upgrade(
    transfer_http: Any,
) -> None:
    transfer_http.config.canvas_api_url = "http://canvas.example.com/api/v1"
    transfer_http.routes["http://canvas.example.com/file"] = httpx.Response(
        302, headers={"Location": f"{CANVAS}/file"}
    )
    async with client_module.canvas_file_download_client() as client:
        response = await client.get(
            "http://canvas.example.com/file", follow_redirects=True
        )
    assert response.content == b"file bytes"
    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == [
        ("http://canvas.example.com/file", f"Bearer {TOKEN}"),
        (f"{CANVAS}/file", None),
    ]


@pytest.mark.asyncio
async def test_nondefault_configured_port_gets_token_only_on_that_port(
    transfer_http: Any,
) -> None:
    transfer_http.config.canvas_api_url = "https://canvas.example.com:8443/api/v1"
    transfer_http.routes["https://canvas.example.com:8443/file"] = httpx.Response(
        302, headers={"Location": f"{CANVAS}/file"}
    )
    async with client_module.canvas_file_download_client() as client:
        await client.get("https://canvas.example.com:8443/file", follow_redirects=True)
    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == [
        ("https://canvas.example.com:8443/file", f"Bearer {TOKEN}"),
        (f"{CANVAS}/file", None),
    ]


@pytest.mark.asyncio
async def test_download_redirect_loop_stops_without_sending_token(
    transfer_http: Any,
) -> None:
    transfer_http.routes[f"{STORAGE}/loop"] = httpx.Response(
        302, headers={"Location": "/loop"}
    )
    with pytest.raises(httpx.TooManyRedirects):
        async with client_module.canvas_file_download_client() as client:
            await client.get(f"{STORAGE}/loop", follow_redirects=True)
    assert 1 < len(transfer_http.requests) <= 21
    assert all(
        str(r.url) == f"{STORAGE}/loop" and "Authorization" not in r.headers
        for r in transfer_http.requests
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "download"])
async def test_hosted_file_transfer_uses_callers_token_and_origin(
    transfer_http: Any,
    tmp_path: Any,
    operation: str,
) -> None:
    from canvas_mcp.core.credentials import (
        RequestCredentials,
        set_http_request_active,
        set_request_credentials,
    )

    set_http_request_active()
    set_request_credentials(
        RequestCredentials(
            "synthetic-caller-token", "https://tenant.example.edu/api/v1"
        )
    )
    if operation == "download":
        async with client_module.canvas_file_download_client() as client:
            await client.get("https://tenant.example.edu/file")
        async with client_module.canvas_file_download_client() as client:
            await client.get(f"{CANVAS}/file")
        assert [
            (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
        ] == [
            ("https://tenant.example.edu/file", "Bearer synthetic-caller-token"),
            (f"{CANVAS}/file", None),
        ]
    else:
        upload = tmp_path / "upload.txt"
        upload.write_bytes(b"upload content")
        transfer_http.routes[f"{STORAGE}/upload"] = httpx.Response(
            303, headers={"Location": "https://tenant.example.edu/confirm"}
        )
        transfer_http.routes["https://tenant.example.edu/confirm"] = httpx.Response(
            201, json={"id": 7}
        )
        result = await client_module.upload_file_to_storage(
            f"{STORAGE}/upload", {}, str(upload), "upload.txt", "text/plain"
        )
        assert result == {"id": 7}
        assert [
            (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
        ] == [
            (f"{STORAGE}/upload", None),
            ("https://tenant.example.edu/confirm", "Bearer synthetic-caller-token"),
        ]


@pytest.mark.asyncio
async def test_hosted_download_without_token_refuses_before_dispatch(
    transfer_http: Any,
) -> None:
    from canvas_mcp.core.credentials import set_http_request_active

    set_http_request_active()
    with pytest.raises(PermissionError, match="Canvas token required"):
        async with client_module.canvas_file_download_client() as client:
            await client.get(f"{CANVAS}/file")
    assert transfer_http.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target", ["https://[invalid/confirm", "https://canvas.example.com:bad/confirm"]
)
async def test_invalid_upload_confirmation_is_not_requested(
    transfer_http: Any,
    tmp_path: Any,
    target: str,
) -> None:
    upload = tmp_path / "upload.txt"
    upload.write_bytes(b"upload content")
    transfer_http.routes[f"{STORAGE}/upload"] = httpx.Response(
        303, headers={"Location": target}
    )
    result = await client_module.upload_file_to_storage(
        f"{STORAGE}/upload", {}, str(upload), "upload.txt", "text/plain"
    )
    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == [(f"{STORAGE}/upload", None)]
    assert "error" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("hosted_token", [None, "synthetic-caller-token"])
async def test_upload_confirmation_never_uses_server_token_for_hosted_caller(
    transfer_http: Any,
    tmp_path: Any,
    hosted_token: str | None,
) -> None:
    from canvas_mcp.core.credentials import (
        RequestCredentials,
        set_http_request_active,
        set_request_credentials,
    )

    set_http_request_active()
    if hosted_token:
        set_request_credentials(
            RequestCredentials(hosted_token, "https://tenant.example.edu/api/v1")
        )
    upload = tmp_path / "upload.txt"
    upload.write_bytes(b"upload content")
    transfer_http.routes[f"{STORAGE}/upload"] = httpx.Response(
        303, headers={"Location": f"{CANVAS}/confirm"}
    )
    result = await client_module.upload_file_to_storage(
        f"{STORAGE}/upload", {}, str(upload), "upload.txt", "text/plain"
    )
    assert [
        (str(r.url), r.headers.get("Authorization")) for r in transfer_http.requests
    ] == [(f"{STORAGE}/upload", None)]
    assert "error" in result
