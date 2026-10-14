"""HTTP callers must not share the discussion REST-availability hint (issue 489).

discussions._unservable_topics remembers that REST refused a topic and GraphQL
served it, so repeat reads skip straight to GraphQL. The key is only
(prefix, topic_id), so one HTTP caller's verdict would otherwise change what
every other caller requests and returns. These tests drive the real tools and
the real client through a controlled httpx.MockTransport that answers by bearer
token, and assert on the requests each credential actually sent. Tokens are
obviously fake and no Canvas request leaves the process.
"""

import asyncio
import logging
import re
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastmcp import FastMCP

from canvas_mcp.core import client as client_module
from canvas_mcp.core.config import reset_config
from canvas_mcp.core.credentials import (
    RequestCredentials,
    clear_http_request_context,
    get_request_credentials,
    set_http_request_active,
    set_request_credentials,
)
from canvas_mcp.tools import discussions

API = "https://canvas.example/api/v1"
GRAPHQL = "/api/graphql"
TOPIC_ID = 805022
ENTRY_ID = 1
GROUP_ID = 9
COURSE_PREFIX = "/api/v1/courses/60366"
GROUP_PREFIX = f"/api/v1/groups/{GROUP_ID}"
TOPIC = f"{COURSE_PREFIX}/discussion_topics/{TOPIC_ID}"
STDIO_TOKEN = "fake-token-stdio"

READ_TOOLS = [
    "get_discussion_topic_details",
    "list_discussion_entries",
    "get_discussion_entry_details",
    "get_discussion_with_replies",
]

# Text only the GraphQL-served rendering contains (the GraphQL fixtures carry an
# anonymous alias and a "GraphQL body" entry, the REST fixtures "REST Staff" and
# "REST body"), and the issue-421 error text.
GRAPHQL_RENDERED = {
    "get_discussion_topic_details": "Anonymous x1",
    "list_discussion_entries": "GraphQL body",
    "get_discussion_entry_details": "GraphQL body",
    "get_discussion_with_replies": "GraphQL body",
}
FALLBACK_ERROR = "exists (it is in this course's topic list)"

LISTING = [{"id": TOPIC_ID, "title": "Anon topic", "anonymous_state": "partial_anonymity"}]
REST_TOPIC = {
    "id": TOPIC_ID, "title": "Anon topic", "message": "<p>Ask here.</p>",
    "is_announcement": False, "author": {"id": 1, "display_name": "REST Staff"},
    "created_at": "2026-08-31T16:38:36Z", "posted_at": "2026-08-31T16:38:36Z",
    "discussion_entries_count": 1, "unread_count": 0, "read_state": "read",
    "locked": False, "pinned": True, "require_initial_post": False,
    "anonymous_state": "partial_anonymity", "assignment": None,
}
REST_ENTRY = {
    "id": ENTRY_ID, "user_id": 1, "user_name": "REST Staff", "message": "<p>REST body</p>",
    "created_at": "2026-09-01T08:00:00Z", "read_state": "read", "rating_sum": 0,
    "recent_replies": [],
}
ROOT_NODE = {
    "_id": str(ENTRY_ID), "parentId": None, "deleted": False,
    "createdAt": "2026-09-01T08:00:00Z", "updatedAt": None,
    "message": "<p>GraphQL body</p>", "author": None, "anonymousAuthor": {"shortName": "x1"},
}


def graphql_topic(context: tuple[str, str] = ("Course", "60366")) -> dict[str, Any]:
    return {"data": {"legacyNode": {
        "_id": str(TOPIC_ID), "title": "Anon topic", "message": "<p>Ask here.</p>",
        "createdAt": "2026-08-31T16:38:36Z", "postedAt": "2026-08-31T16:38:36Z",
        "locked": False, "requireInitialPost": False, "isAnnouncement": False,
        "anonymousState": "partial_anonymity",
        "contextType": context[0], "contextId": context[1],
        "author": None, "anonymousAuthor": {"shortName": "x1"},
        "entryCounts": {"repliesCount": 0, "unreadCount": 0}, "participant": {"read": True},
        "discussionEntriesConnection": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [ROOT_NODE],
        },
    }}}


GRAPHQL_OK = graphql_topic()
GRAPHQL_DENIED = {"errors": [{"message": "not authorized"}]}

# Per-credential Canvas behaviour: (status of every REST discussion read, GraphQL body).
# The topic is listed for every caller; 200 means REST serves it.
CALLERS: dict[str, tuple[int, dict[str, Any]]] = {
    "fake-token-a": (404, GRAPHQL_OK),      # REST refuses the topic, GraphQL serves it
    "fake-token-b": (200, GRAPHQL_OK),      # REST serves the topic
    "fake-token-c": (403, GRAPHQL_OK),      # REST denies, GraphQL would serve
    "fake-token-d": (403, GRAPHQL_DENIED),  # REST and GraphQL both deny
    "fake-token-b-rotated": (200, GRAPHQL_OK),  # a rotated credential of the same client
    "fake-token-member": (404, graphql_topic(("Group", str(GROUP_ID)))),  # in group 9
    "fake-token-outsider": (404, graphql_topic(("Group", str(GROUP_ID)))),  # not in group 9
    STDIO_TOKEN: (404, GRAPHQL_OK),
}
GROUP_MEMBERS = {"fake-token-member"}

Sent = list[tuple[str, str, str]]  # (token, method, path)


class Canvas:
    """Request log plus gates for one test's controlled transport."""

    def __init__(self) -> None:
        self.sent: Sent = []

    def by(self, token: str) -> list[tuple[str, str]]:
        return [(method, path) for who, method, path in self.sent if who == token]

    def reset(self) -> None:
        self.sent.clear()
        discussions._unservable_topics.clear()


def _discussion_path(path: str) -> str | None:
    """The part after .../discussion_topics for a course or group request."""
    match = re.fullmatch(r"/api/v1/(?:courses/60366|groups/9)/discussion_topics(/.*)?", path)
    return None if match is None else (match.group(1) or "")


def _make_handler(canvas: Canvas) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        path = request.url.path
        canvas.sent.append((token, request.method, path))
        rest_status, graphql = CALLERS[token]
        if path == GRAPHQL:
            return httpx.Response(200, json=graphql)
        if path.endswith("/permissions"):
            return httpx.Response(403, json={"errors": [{"message": "no"}]})
        if path == "/api/v1/users/self/groups":
            member = [{"id": GROUP_ID, "course_id": 60366}] if token in GROUP_MEMBERS else []
            return httpx.Response(200, json=member)
        if path == GROUP_PREFIX:
            return httpx.Response(200, json={"id": GROUP_ID, "course_id": 60366})
        sub = _discussion_path(path)
        if sub is None:
            return httpx.Response(500, json={"error": "unexpected"})
        if sub == "":  # the topic listing
            return httpx.Response(200, json=LISTING)
        if rest_status != 200:
            return httpx.Response(rest_status, json={"errors": [{"message": "no"}]})
        if sub == f"/{TOPIC_ID}":
            return httpx.Response(200, json=REST_TOPIC)
        if sub in (f"/{TOPIC_ID}/entries", f"/{TOPIC_ID}/entry_list"):
            return httpx.Response(200, json=[REST_ENTRY])
        if sub == f"/{TOPIC_ID}/view":
            return httpx.Response(200, json={"view": [REST_ENTRY]})
        return httpx.Response(200, json=[])

    return handler


@pytest.fixture(autouse=True)
def canvas(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    monkeypatch.setenv("CANVAS_API_URL", API)
    monkeypatch.setenv("CANVAS_API_TOKEN", STDIO_TOKEN)
    monkeypatch.setenv("DISCUSSION_GRAPHQL_ENABLED", "true")
    monkeypatch.delenv("CANVAS_ROLE", raising=False)
    reset_config()
    clear_http_request_context()
    discussions._unservable_topics.clear()
    caplog.set_level(logging.DEBUG)
    state = Canvas()
    handler = _make_handler(state)

    real_client = httpx.AsyncClient

    def http_client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    # HTTP requests build a client per credential; stdio reuses a shared one.
    monkeypatch.setattr(client_module.httpx, "AsyncClient", http_client_factory)
    stdio_client = real_client(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": f"Bearer {STDIO_TOKEN}"},
    )
    monkeypatch.setattr(client_module, "_get_http_client", lambda: stdio_client)
    monkeypatch.setattr(discussions, "get_course_id", AsyncMock(return_value="60366"))
    monkeypatch.setattr(discussions, "get_course_code", AsyncMock(return_value="C1"))

    yield state

    # Forbidden side effects: nothing but the GraphQL read may leave the GET path.
    assert {(m, p) for _, m, p in state.sent if m != "GET"} <= {("POST", GRAPHQL)}
    # No credential material in any hint key or log line.
    leaked_keys = [k for k in discussions._unservable_topics if "fake-token" in repr(k)]
    assert leaked_keys == []
    assert "fake-token" not in caplog.text
    discussions._unservable_topics.clear()
    clear_http_request_context()
    reset_config()


_TOOLS: dict[str, Callable[..., Any]] = {}


def _tool(name: str) -> Callable[..., Any]:
    if not _TOOLS:
        mcp = FastMCP("discussion-hint-isolation")
        original = mcp.tool

        def capturing(*args: Any, **kwargs: Any) -> Any:
            decorator = original(*args, **kwargs)

            def wrapper(fn: Callable[..., Any]) -> Any:
                _TOOLS[fn.__name__] = fn
                return decorator(fn)

            return wrapper

        mcp.tool = capturing  # type: ignore[method-assign]
        discussions.register_shared_discussion_tools(mcp)
    return _TOOLS[name]


def _args(name: str) -> tuple[Any, ...]:
    return ("60366", TOPIC_ID, ENTRY_ID) if name == "get_discussion_entry_details" else ("60366", TOPIC_ID)


async def as_caller(token: str, name: str = "get_discussion_topic_details", **kwargs: Any) -> str:
    """Run one tool call in its own context, as the server does per HTTP request."""
    fn = _tool(name)

    async def run() -> str:
        set_http_request_active(True)
        set_request_credentials(RequestCredentials(token, API))
        try:
            return await fn(*_args(name), **kwargs)
        finally:
            clear_http_request_context()

    return await asyncio.create_task(run())


async def as_stdio(name: str = "get_discussion_topic_details", **kwargs: Any) -> str:
    return await _tool(name)(*_args(name), **kwargs)


def rest_reads(requests: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(m, p) for m, p in requests if m == "GET" and f"/discussion_topics/{TOPIC_ID}" in p]


async def alone(canvas: Canvas, token: str, name: str) -> tuple[str, list[tuple[str, str]]]:
    """What `token` returns and sends when it is the only caller."""
    canvas.reset()
    output = await as_caller(token, name)
    requests = canvas.by(token)
    canvas.reset()
    return output, requests


@pytest.mark.parametrize("name", READ_TOOLS)
async def test_second_caller_asks_rest_with_its_own_credential(canvas, name):
    """A's REST 404 plus GraphQL success must not become B's route (A then B)."""
    expected, expected_requests = await alone(canvas, "fake-token-b", name)
    assert rest_reads(expected_requests), "control: B alone reads the topic over REST"
    assert ("POST", GRAPHQL) not in expected_requests

    await as_caller("fake-token-a", name)
    canvas.sent.clear()
    after_a = await as_caller("fake-token-b", name)

    assert canvas.by("fake-token-b") == expected_requests
    assert after_a == expected


@pytest.mark.parametrize("name", READ_TOOLS)
async def test_first_caller_is_unaffected_by_a_later_one(canvas, name):
    """B then A: A still falls back through its own REST 404 and listing check."""
    expected, expected_requests = await alone(canvas, "fake-token-a", name)
    assert ("POST", GRAPHQL) in expected_requests
    assert rest_reads(expected_requests)
    assert GRAPHQL_RENDERED[name] in expected
    assert FALLBACK_ERROR not in expected

    await as_caller("fake-token-b", name)
    canvas.sent.clear()
    after_b = await as_caller("fake-token-a", name)

    assert canvas.by("fake-token-a") == expected_requests
    assert after_b == expected


@pytest.mark.parametrize("name", READ_TOOLS)
async def test_http_fallback_serves_graphql_content(canvas, name):
    """An HTTP caller with a listed REST 404 still gets the GraphQL-served topic (issue 421).

    Positive assertion on the content, so a fallback that silently returns the
    issue-421 error cannot hide behind a comparison of two equally broken outputs.
    """
    http_output = await as_caller("fake-token-a", name)
    assert GRAPHQL_RENDERED[name] in http_output
    assert FALLBACK_ERROR not in http_output
    assert "Also, None" not in http_output
    requests = canvas.by("fake-token-a")
    assert requests[-1] == ("POST", GRAPHQL)
    assert rest_reads(requests), "the REST 404 and listing check still run first"

    # Same rendering the single-credential (stdio) fallback produces for this tool.
    canvas.reset()
    assert await as_stdio(name) == http_output


@pytest.mark.parametrize("name", READ_TOOLS)
async def test_graphql_is_not_offered_to_a_caller_rest_denied(canvas, name):
    """C's own REST 403 stands; A's earlier GraphQL success cannot override it."""
    expected, expected_requests = await alone(canvas, "fake-token-c", name)
    assert ("POST", GRAPHQL) not in expected_requests, "control: 403 is not a 404 fallback"

    await as_caller("fake-token-a", name)
    canvas.sent.clear()
    after_a = await as_caller("fake-token-c", name)

    assert canvas.by("fake-token-c") == expected_requests
    assert ("POST", GRAPHQL) not in canvas.by("fake-token-c")
    assert after_a == expected


async def test_topic_details_denial_is_the_callers_own_error(canvas):
    output, _ = await alone(canvas, "fake-token-c", "get_discussion_topic_details")
    await as_caller("fake-token-a")
    after_a = await as_caller("fake-token-c")
    assert "HTTP error: 403" in output
    assert "HTTP error: 403" in after_a
    assert "Anon topic" not in after_a


@pytest.mark.parametrize("name", READ_TOOLS)
async def test_denied_callers_failure_does_not_change_another_callers_requests(canvas, name):
    """D's failed GraphQL read is D's alone: A's next requests are identical."""
    await as_caller("fake-token-a", name)
    canvas.sent.clear()
    await as_caller("fake-token-a", name)
    without_d = canvas.by("fake-token-a")

    canvas.reset()
    await as_caller("fake-token-a", name)
    await as_caller("fake-token-d", name)
    canvas.sent.clear()
    await as_caller("fake-token-a", name)

    assert canvas.by("fake-token-a") == without_d


async def test_denied_caller_gets_no_graphql_content(canvas):
    """D is denied on both routes and must not receive A's GraphQL-served content."""
    await as_caller("fake-token-a")
    output = await as_caller("fake-token-d")
    assert "Anon topic" not in output
    assert "HTTP error: 403" in output


@pytest.mark.parametrize("name", READ_TOOLS)
async def test_in_flight_caller_does_not_borrow_a_verdict_published_meanwhile(
    canvas, monkeypatch, name
):
    """B is already inside the tool when A finishes; B still asks REST itself.

    B's course lookup (the first await in every read tool) is held until A's
    whole call has completed, so on unpatched code A has published its hint by
    the time B checks it.
    """
    expected_b, expected_b_requests = await alone(canvas, "fake-token-b", name)
    expected_a, expected_a_requests = await alone(canvas, "fake-token-a", name)

    a_done = asyncio.Event()
    b_inside = asyncio.Event()

    async def course_lookup(identifier: str) -> str:
        creds = get_request_credentials()
        if creds is not None and creds.api_token == "fake-token-b":
            b_inside.set()
            await a_done.wait()
        return "60366"

    monkeypatch.setattr(discussions, "get_course_id", course_lookup)

    async def run_a() -> str:
        await b_inside.wait()  # B is in flight before A starts
        try:
            return await as_caller("fake-token-a", name)
        finally:
            a_done.set()

    out_b, out_a = await asyncio.gather(as_caller("fake-token-b", name), run_a())
    assert (out_b, out_a) == (expected_b, expected_a)
    assert canvas.by("fake-token-b") == expected_b_requests
    assert canvas.by("fake-token-a") == expected_a_requests


async def test_rotated_credential_takes_its_own_route(canvas):
    """The same client with a new credential is a new caller, not the old verdict."""
    expected, expected_requests = await alone(canvas, "fake-token-b-rotated", "get_discussion_topic_details")
    await as_caller("fake-token-a")
    canvas.sent.clear()
    rotated = await as_caller("fake-token-b-rotated")
    assert canvas.by("fake-token-b-rotated") == expected_requests
    assert rotated == expected
    assert rest_reads(canvas.by("fake-token-b-rotated"))


@pytest.mark.parametrize("name", READ_TOOLS)
async def test_http_caller_repeat_read_never_publishes_a_hint(canvas, name):
    await as_caller("fake-token-a", name)
    await as_caller("fake-token-a", name)
    assert discussions._unservable_topics == {}


@pytest.mark.parametrize("name", READ_TOOLS)
async def test_stdio_keeps_its_single_credential_hint(canvas, name):
    """stdio has one credential: the repeat read is one GraphQL request (issues 439/442)."""
    first = await as_stdio(name)
    assert ("GET", TOPIC) in [(m, p) for _, m, p in canvas.sent] or name != "get_discussion_topic_details"
    assert ("POST", GRAPHQL) in [(m, p) for _, m, p in canvas.sent]
    canvas.sent.clear()
    second = await as_stdio(name)
    assert [(m, p) for _, m, p in canvas.sent] == [("POST", GRAPHQL)]
    assert second == first
    assert len(discussions._unservable_topics) == 1


async def test_stdio_hint_is_not_served_to_http_callers(canvas):
    """A stdio-published hint stays out of HTTP requests, which take the full path."""
    await as_stdio()
    assert len(discussions._unservable_topics) == 1
    expected, expected_requests = await alone(canvas, "fake-token-b", "get_discussion_topic_details")
    discussions._unservable_topics.clear()
    await as_stdio()
    canvas.sent.clear()
    after = await as_caller("fake-token-b")
    assert canvas.by("fake-token-b") == expected_requests
    assert after == expected


async def test_group_membership_gate_still_runs_for_every_caller(canvas):
    """A member's group read leaves nothing that lets a non-member skip the membership gate."""
    kwargs = {"group_id": GROUP_ID}
    member = await as_caller("fake-token-member", **kwargs)
    assert "Discussion Details" in member
    assert FALLBACK_ERROR not in member
    canvas.sent.clear()

    outsider = await as_caller("fake-token-outsider", **kwargs)

    assert "not a member of group 9" in outsider
    assert "Anon topic" not in outsider
    outsider_requests = canvas.by("fake-token-outsider")
    assert ("GET", "/api/v1/users/self/groups") in outsider_requests
    assert not any("discussion_topics" in p for _, p in outsider_requests)
    assert ("POST", GRAPHQL) not in outsider_requests


async def test_member_repeat_group_read_rechecks_membership(canvas):
    """A group member's repeat read re-reads membership before any discussion request."""
    kwargs = {"group_id": GROUP_ID}
    await as_caller("fake-token-member", **kwargs)
    canvas.sent.clear()
    await as_caller("fake-token-member", **kwargs)
    requests = canvas.by("fake-token-member")
    membership = requests.index(("GET", "/api/v1/users/self/groups"))
    first_discussion = next(i for i, (_, p) in enumerate(requests) if "discussion_topics" in p or p == GRAPHQL)
    assert membership < first_discussion
