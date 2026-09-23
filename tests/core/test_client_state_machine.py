"""Real httpx transports and scheduled client-lifecycle counterexamples."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from canvas_mcp.core import client as cm
from canvas_mcp.core.credentials import RequestCredentials


@pytest.fixture(autouse=True)
def isolated_client(monkeypatch):
    for name in ("http_client", "_http_client_loop_ref", "_request_semaphore", "_semaphore_loop_ref"):
        monkeypatch.setattr(cm, name, None)
    config = SimpleNamespace(canvas_api_url="https://canvas.example/api/v1",
                             canvas_api_token="synthetic", max_concurrent_requests=2,
                             api_timeout=1, log_api_requests=False,
                             enable_data_anonymization=False, anonymization_debug=False)
    monkeypatch.setattr("canvas_mcp.core.config.get_config", lambda: config)
    monkeypatch.setattr(cm, "get_request_credentials", lambda: None)
    monkeypatch.setattr(cm, "is_http_request_active", lambda: False)
    yield config


@pytest.mark.asyncio
async def test_short_page_with_next_link_is_not_truncated():
    seen = []
    next_url = "https://canvas.example/api/v1/courses?cursor=opaque%2Bvalue&include[]=a&include[]=b"

    async def transport(request):
        seen.append(str(request.url))
        if len(seen) == 1:
            return httpx.Response(200, json=[{"id": 1}], headers={"Link": f'<{next_url}>; rel="next"'})
        assert str(request.url) == next_url
        return httpx.Response(200, json=[{"id": 2}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with patch.object(cm, "_get_http_client", return_value=client):
            result = await cm.fetch_all_paginated_results("/courses", {"per_page": 100})
    assert result == [{"id": 1}, {"id": 2}]
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_cyclic_next_link_fails_without_repeating_page():
    seen = []

    async def transport(request):
        seen.append(str(request.url))
        if len(seen) > 3:
            return httpx.Response(500, json={"error": "test sentinel: pagination did not terminate"})
        return httpx.Response(200, json=[{"id": 1}], headers={"Link": f'<{request.url}>; rel="next"'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with patch.object(cm, "_get_http_client", return_value=client):
            result = await cm.fetch_all_paginated_results("/courses", {"per_page": 1})
    assert "cycle" in result.get("error", "").lower()
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_cancelled_semaphore_wait_closes_request_owned_client():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])))
    sem = asyncio.Semaphore(0)
    creds = RequestCredentials("synthetic", "https://canvas.example/api/v1")
    with (patch.object(cm, "get_request_credentials", return_value=creds),
          patch.object(cm.httpx, "AsyncClient", return_value=client),
          patch.object(cm, "_get_request_semaphore", return_value=sem)):
        task = asyncio.create_task(cm.make_canvas_request("get", "/courses"))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    try:
        assert client.is_closed
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cleanup_cannot_discard_replacement_client():
    entered, finish = asyncio.Event(), asyncio.Event()

    class PausedCloseTransport(httpx.AsyncBaseTransport):
        async def aclose(self):
            entered.set()
            await finish.wait()

    old = httpx.AsyncClient(transport=PausedCloseTransport())
    replacement = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=[])))
    cm.http_client = old
    task = asyncio.create_task(cm.cleanup_http_client())
    await entered.wait()
    try:
        assert old.is_closed
        with patch.object(cm.httpx, "AsyncClient", return_value=replacement):
            assert cm._get_http_client() is replacement
        finish.set()
        await task
        assert cm.http_client is replacement
    finally:
        finish.set()
        await task
        await replacement.aclose()


@pytest.mark.asyncio
async def test_429_terminates_after_four_attempts_and_three_backoffs():
    calls = []

    async def transport(request):
        calls.append(request)
        return httpx.Response(429, json={"error": "slow down"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with (patch.object(cm, "_get_http_client", return_value=client),
              patch.object(cm.asyncio, "sleep", new_callable=AsyncMock) as sleep):
            result = await cm.make_canvas_request("get", "/courses")
    assert "429" in result["error"]
    assert len(calls) == 4
    assert [c.args[0] for c in sleep.await_args_list] == [2, 4, 8]


@pytest.mark.asyncio
async def test_concurrent_requests_obey_semaphore_cap():
    active = peak = 0

    async def transport(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with patch.object(cm, "_get_http_client", return_value=client):
            await asyncio.gather(*(cm.make_canvas_request("get", "/courses") for _ in range(20)))
    assert peak == 2
    assert active == 0


@pytest.mark.asyncio
async def test_unbounded_unique_next_links_hit_explicit_budget(monkeypatch):
    monkeypatch.setattr(cm, "MAX_PAGINATION_PAGES", 3)
    calls = 0

    async def transport(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[{"id": calls}], headers={
            "Link": f'<https://canvas.example/api/v1/courses?cursor={calls}>; rel="next"'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with patch.object(cm, "_get_http_client", return_value=client):
            result = await cm.fetch_all_paginated_results("/courses")
    assert "exceeded 3 pages" in result["error"]
    assert calls == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["https://evil.example/api/v1/courses?page=2",
                                    "https://canvas.example/api/v1/users?page=2"])
async def test_pagination_cannot_redirect_credentials_or_change_endpoint(target):
    seen = []

    async def transport(request):
        seen.append(request)
        return httpx.Response(200, json=[{"id": 1}], headers={"Link": f'<{target}>; rel="next"'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with patch.object(cm, "_get_http_client", return_value=client):
            result = await cm.fetch_all_paginated_results("/courses")
    assert "Invalid pagination link" in result["error"]
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_concurrent_pagination_owns_each_cursor_and_input():
    params = {"include[]": ["a", "b"]}
    seen = {"courses": [], "users": []}

    async def transport(request):
        collection = request.url.path.split("/")[-1]
        seen[collection].append(str(request.url))
        await asyncio.sleep(0)
        if "cursor" not in request.url.params:
            return httpx.Response(200, json=[{"id": collection + "1"}], headers={
                "Link": f'<https://canvas.example/api/v1/{collection}?cursor=next>; rel="next"'})
        return httpx.Response(200, json=[{"id": collection + "2"}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with patch.object(cm, "_get_http_client", return_value=client):
            courses, users = await asyncio.gather(
                cm.fetch_all_paginated_results("/courses", params),
                cm.fetch_all_paginated_results("/users", params))
    assert courses == [{"id": "courses1"}, {"id": "courses2"}]
    assert users == [{"id": "users1"}, {"id": "users2"}]
    assert params == {"include[]": ["a", "b"]}
    assert all(len(urls) == len(set(urls)) == 2 for urls in seen.values())


@pytest.mark.asyncio
async def test_queued_request_reselects_client_after_cleanup():
    import weakref

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[{"id": 1}]))
    old = httpx.AsyncClient(transport=transport)
    new = httpx.AsyncClient(transport=transport)
    cm.http_client = old
    cm._http_client_loop_ref = weakref.ref(asyncio.get_running_loop())
    sem = asyncio.Semaphore(0)
    with (patch.object(cm, "_get_request_semaphore", return_value=sem),
          patch.object(cm.httpx, "AsyncClient", return_value=new)):
        task = asyncio.create_task(cm.make_canvas_request("get", "/courses"))
        await asyncio.sleep(0)
        await cm.cleanup_http_client()
        sem.release()
        result = await task
    await new.aclose()
    assert result == [{"id": 1}]


@pytest.mark.asyncio
async def test_retry_reselects_client_after_cleanup_during_backoff():
    import weakref

    old = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(429, json={})))
    new = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
    cm.http_client = old
    cm._http_client_loop_ref = weakref.ref(asyncio.get_running_loop())

    async def backoff(_delay):
        await cm.cleanup_http_client()

    with (patch.object(cm.asyncio, "sleep", side_effect=backoff),
          patch.object(cm.httpx, "AsyncClient", return_value=new)):
        result = await cm.make_canvas_request("get", "/courses")
    await new.aclose()
    assert result == []
