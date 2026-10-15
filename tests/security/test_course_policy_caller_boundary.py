"""Course-policy verdicts must not cross the HTTP caller boundary.

The per-course agent policy is read from the syllabus with the *calling*
user's own token. In streamable-HTTP mode one process serves many callers, each
with their own token, so a verdict cached under the course id alone would answer
a caller who cannot read the course with another caller's read: disclosing the
instructor's ``note:`` line and the course's allow/deny posture, and skipping
the caller's own Canvas authorization check. Canvas still authorizes the actual
write under the caller's token, so this is a disclosure and gate-integrity
boundary rather than an unauthorized write.

stdio has a single credential, so its cache is that one user's own and stays.
"""

import asyncio
import itertools
import logging
import time
from typing import NamedTuple
from unittest.mock import patch

import httpx
import pytest
from fastmcp import FastMCP

from canvas_mcp.core import client as client_module
from canvas_mcp.core import course_policy
from canvas_mcp.core.config import reset_config
from canvas_mcp.core.course_policy import (
    CoursePolicy,
    check_student_write_allowed,
    get_course_policy,
    reset_policy_cache,
)
from canvas_mcp.core.credentials import (
    RequestCredentials,
    clear_http_request_context,
    get_request_credentials,
    set_http_request_active,
    set_request_credentials,
)

API_URL = "https://canvas.example/api/v1"
INSTRUCTOR_NOTE = "INSTRUCTOR-NOTE-visible-only-to-enrolled-students"
TOOL = "submit_assignment"
UNREADABLE = {"error": "HTTP error: 404 - The specified resource does not exist."}


@pytest.fixture(autouse=True)
def isolate_state(monkeypatch):
    monkeypatch.setenv("CANVAS_API_URL", API_URL)
    monkeypatch.setenv("STUDENT_WRITE_TOOLS", TOOL)
    monkeypatch.setenv("COURSE_AGENT_POLICY_ENABLED", "true")
    monkeypatch.setenv("COURSE_AGENT_POLICY_DEFAULT", "deny")
    reset_config()
    reset_policy_cache()
    clear_http_request_context()
    yield
    clear_http_request_context()
    reset_policy_cache()
    reset_config()


def http_caller(token: str) -> None:
    clear_http_request_context()
    set_http_request_active()
    set_request_credentials(RequestCredentials(token, API_URL))


class FakeCanvas:
    """Answers by the current request's token, the way Canvas does.

    Tokens in ``readers`` can read the course; any other token gets a 404.
    Every call is recorded with the token it was made under.
    """

    def __init__(self, syllabus: str, readers: tuple[str, ...] = ("enrolled", "enrolled-2")):
        self.syllabus = syllabus
        self.readers = readers
        self.calls: list[tuple[str, str, str]] = []

    async def __call__(self, method, endpoint, **kwargs):
        credentials = get_request_credentials()
        token = credentials.api_token if credentials else "<stdio>"
        self.calls.append((token, method, endpoint))
        if token != "<stdio>" and token not in self.readers:
            return UNREADABLE
        if endpoint in ("/courses/123", "/courses/456"):
            return {"id": 123, "syllabus_body": self.syllabus}
        return UNREADABLE

    def reads_by(self, token: str) -> list[tuple[str, str, str]]:
        return [call for call in self.calls if call[0] == token]


def patched(fake: FakeCanvas):
    return patch.object(course_policy, "make_canvas_request", new=fake)


@pytest.mark.asyncio
async def test_http_policy_note_not_served_to_caller_who_cannot_read_course():
    fake = FakeCanvas(f"<p>agent_writes: deny</p><p>note: {INSTRUCTOR_NOTE}</p>")
    with patched(fake):
        http_caller("enrolled")
        allowed, reason = await check_student_write_allowed("123", TOOL)
        assert not allowed and INSTRUCTOR_NOTE in reason

        http_caller("outsider")
        allowed, reason = await check_student_write_allowed("123", TOOL)

    assert not allowed
    assert INSTRUCTOR_NOTE not in reason
    assert fake.reads_by("outsider"), "the outsider's verdict must come from its own read"


@pytest.mark.asyncio
async def test_http_grant_not_reused_for_caller_who_cannot_read_course():
    fake = FakeCanvas("agent_writes: allow")
    with patched(fake):
        http_caller("enrolled")
        assert await check_student_write_allowed("123", TOOL) == (True, "")

        http_caller("outsider")
        allowed, reason = await check_student_write_allowed("123", TOOL)

    assert not allowed
    assert "could not be checked" in reason


@pytest.mark.asyncio
async def test_http_caller_cannot_tell_whether_another_caller_used_the_course():
    fake = FakeCanvas("An ordinary syllabus that states no agent policy.")
    with patched(fake):
        http_caller("outsider")
        before = await check_student_write_allowed("123", TOOL)

        http_caller("enrolled")
        await check_student_write_allowed("123", TOOL)

        http_caller("outsider")
        after = await check_student_write_allowed("123", TOOL)

    assert before == after


@pytest.mark.asyncio
async def test_http_each_caller_reads_policy_under_own_token():
    fake = FakeCanvas("agent_writes: allow")
    with patched(fake):
        for token in ("enrolled", "enrolled-2"):
            http_caller(token)
            assert await check_student_write_allowed("123", TOOL) == (True, "")

    for token in ("enrolled", "enrolled-2"):
        assert fake.reads_by(token) == [(token, "get", "/courses/123")]


@pytest.mark.asyncio
async def test_http_ignores_and_never_populates_shared_policy_cache():
    # An entry another path (stdio, an earlier request) left behind.
    seeded = (time.monotonic() + 600, CoursePolicy(True, None, "", "course_artifact"))
    course_policy._policy_cache["123"] = seeded

    fake = FakeCanvas("agent_writes: deny")
    with patched(fake):
        http_caller("enrolled")
        policy = await get_course_policy("123")
        # A different course must not be added to the shared map either.
        await get_course_policy("456")

    assert not policy.allow_writes, "HTTP must read the policy itself, not use the seeded grant"
    assert fake.reads_by("enrolled")
    assert course_policy._policy_cache == {"123": seeded}, "HTTP checks must not touch the shared map"


@pytest.mark.asyncio
async def test_http_without_token_never_reads_cached_policy():
    course_policy._policy_cache["123"] = (
        time.monotonic() + 600,
        CoursePolicy(True, None, "", "course_artifact"),
    )

    async def no_token(method, endpoint, **kwargs):
        return {"error": "Canvas token required"}

    clear_http_request_context()
    set_http_request_active()
    with patch.object(course_policy, "make_canvas_request", new=no_token):
        policy = await get_course_policy("123")
        allowed, _ = await check_student_write_allowed("123", TOOL)

    assert not policy.allow_writes and policy.source == "read_error"
    assert not allowed


@pytest.mark.asyncio
async def test_stdio_repeat_checks_use_cache():
    """Control: with a single credential the cache is that user's own."""
    fake = FakeCanvas("agent_writes: allow")
    with patched(fake):
        assert await check_student_write_allowed("123", TOOL) == (True, "")
        assert await check_student_write_allowed("123", TOOL) == (True, "")
    assert len(fake.calls) == 1
    assert "123" in course_policy._policy_cache


@pytest.mark.asyncio
async def test_tool_preview_does_not_show_note_to_caller_who_cannot_read_course():
    from canvas_mcp.tools import student_write

    captured = {}
    mcp = FastMCP("test")
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    student_write.register_student_write_tools(mcp)
    submit = captured[TOOL]

    fake = FakeCanvas(f"agent_writes: deny\nnote: {INSTRUCTOR_NOTE}")
    args = {
        "course_identifier": "123",
        "assignment_id": "9",
        "submission_type": "online_text_entry",
        "body": "draft",
    }
    with patched(fake), patch.object(student_write, "make_canvas_request", new=fake):
        http_caller("enrolled")
        await submit(**args)

        http_caller("outsider")
        output = await submit(**args)

    assert INSTRUCTOR_NOTE not in output
    assert not [call for call in fake.calls if call[1] != "get"], "no write may be sent"


# ---------------------------------------------------------------------------
# Controlled transport.
#
# The tests above replace make_canvas_request. The ones below keep the real
# client and put a Canvas stand-in on the wire (httpx.MockTransport), so they
# observe what a caller actually sends: which bearer token each outgoing request
# carried, which reads happened, and that no write left the process. Every token
# here is a made-up value.
# ---------------------------------------------------------------------------

REAL_ASYNC_CLIENT = httpx.AsyncClient
COURSE_PATH = "/api/v1/courses/123"
SUBMISSION_PATH = "/api/v1/courses/123/assignments/9/submissions/self"
COMMENT_TOOL = "comment_on_my_submission"
COMMENT_ARGS = {"course_identifier": "123", "assignment_id": "9", "comment": "hello"}

TOK_ENROLLED = "fake-token-enrolled-1"
TOK_ENROLLED_2 = "fake-token-enrolled-2"
TOK_OUTSIDER = "fake-token-outsider"
TOK_OLD = "fake-token-rotated-out"
TOK_NEW = "fake-token-rotated-in"
TOK_STDIO = "fake-token-server-env"
ALL_FAKE_TOKENS = (TOK_ENROLLED, TOK_ENROLLED_2, TOK_OUTSIDER, TOK_OLD, TOK_NEW, TOK_STDIO)


class Seen(NamedTuple):
    """One request as it left the process."""

    token: str
    method: str
    path: str


class CanvasWire:
    """Canvas as seen over the wire: authorizes every request by its bearer token.

    ``users`` maps a token to a Canvas user, ``enrolled`` is the set of users who
    can read the course, and ``revoked`` tokens get a 401. A token in ``held`` has
    its course read parked until ``release`` so a test decides the order in which
    concurrent callers are answered.
    """

    def __init__(self, syllabus: str = "agent_writes: allow") -> None:
        self.syllabus = syllabus
        self.users: dict[str, str] = {
            TOK_ENROLLED: "ada",
            TOK_ENROLLED_2: "grace",
            TOK_OUTSIDER: "mallory",
            TOK_OLD: "linus",
            TOK_NEW: "linus",
            TOK_STDIO: "ada",
        }
        self.enrolled: set[str] = {"ada", "grace", "linus"}
        self.revoked: set[str] = set()
        self.seen: list[Seen] = []
        self.held: set[str] = set()
        self.pending: set[str] = set()
        self.peak_pending = 0
        self._gates: dict[str, asyncio.Event] = {}

    def gate(self, token: str) -> asyncio.Event:
        return self._gates.setdefault(token, asyncio.Event())

    def release(self, token: str) -> None:
        self.gate(token).set()

    async def wait_until_pending(self, *tokens: str) -> None:
        async def poll() -> None:
            while not set(tokens) <= self.pending:
                await asyncio.sleep(0)

        await asyncio.wait_for(poll(), timeout=5)

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        token = request.headers["authorization"].removeprefix("Bearer ")
        path = request.url.path
        self.seen.append(Seen(token, request.method, path))

        if token in self.held and request.method == "GET" and path == COURSE_PATH:
            self.pending.add(token)
            self.peak_pending = max(self.peak_pending, len(self.pending))
            try:
                await asyncio.wait_for(self.gate(token).wait(), timeout=5)
            finally:
                self.pending.discard(token)

        if token in self.revoked or token not in self.users:
            return httpx.Response(401, json={"errors": [{"message": "Invalid access token."}]})
        can_read = self.users[token] in self.enrolled
        if request.method == "GET" and path == COURSE_PATH and can_read:
            return httpx.Response(200, json={"id": 123, "syllabus_body": self.syllabus})
        if request.method == "PUT" and path == SUBMISSION_PATH and can_read:
            return httpx.Response(200, json={"id": 1})
        return httpx.Response(404, json={"errors": [{"message": "The specified resource does not exist."}]})

    def by(self, token: str) -> list[Seen]:
        return [seen for seen in self.seen if seen.token == token]

    def writes(self) -> list[Seen]:
        return [seen for seen in self.seen if seen.method != "GET"]


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv("STUDENT_WRITE_TOOLS", f"{TOOL},{COMMENT_TOOL}")
    monkeypatch.setenv("ENABLE_DATA_ANONYMIZATION", "false")
    monkeypatch.setenv("CANVAS_API_TOKEN", TOK_STDIO)
    reset_config()
    canvas = CanvasWire()
    transport = httpx.MockTransport(canvas)

    def client_on_wire(*args, **kwargs):
        return REAL_ASYNC_CLIENT(*args, transport=transport, **kwargs)

    with patch.object(client_module.httpx, "AsyncClient", new=client_on_wire):
        yield canvas


async def check(token: str, tool: str = TOOL) -> tuple[bool, str]:
    http_caller(token)
    return await check_student_write_allowed("123", tool)


def course_read(token: str) -> Seen:
    return Seen(token, "GET", COURSE_PATH)


def register_tools() -> dict:
    from canvas_mcp.tools import student_write

    captured = {}
    mcp = FastMCP("test")
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    student_write.register_student_write_tools(mcp)
    return captured


ORDERS = {
    "enrolled-then-outsider": (TOK_ENROLLED, TOK_OUTSIDER),
    "outsider-then-enrolled": (TOK_OUTSIDER, TOK_ENROLLED),
    "alternating": (TOK_OUTSIDER, TOK_ENROLLED, TOK_OUTSIDER, TOK_ENROLLED_2, TOK_OUTSIDER, TOK_ENROLLED),
}
GRANT = "agent_writes: allow"
DENY_WITH_NOTE = f"agent_writes: deny\nnote: {INSTRUCTOR_NOTE}"


def assert_verdict(token: str, verdict: tuple[bool, str], syllabus: str) -> None:
    """What each caller must get: the outsider never sees a course-derived verdict."""
    allowed, reason = verdict
    if token == TOK_OUTSIDER:
        assert not allowed
        assert "could not be checked" in reason
        assert INSTRUCTOR_NOTE not in reason
    elif syllabus == GRANT:
        assert verdict == (True, "")
    else:
        assert not allowed and INSTRUCTOR_NOTE in reason


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ORDERS.values(), ids=ORDERS.keys())
@pytest.mark.parametrize("syllabus", [GRANT, DENY_WITH_NOTE], ids=["grant", "deny-with-note"])
async def test_wire_verdict_is_independent_of_caller_order(wire, order, syllabus):
    wire.syllabus = syllabus

    verdicts = [await check(token) for token in order]

    for token, verdict in zip(order, verdicts, strict=True):
        assert_verdict(token, verdict, syllabus)
    # One read per check, each under the token of the check that triggered it:
    # no check was answered from an entry another caller left behind.
    assert wire.seen == [course_read(token) for token in order]
    assert not wire.writes()
    assert course_policy._policy_cache == {}


@pytest.mark.asyncio
async def test_wire_denial_for_one_caller_does_not_poison_the_next(wire):
    wire.revoked.add(TOK_ENROLLED)  # an expired token: a read error for that caller only

    expired = await check(TOK_ENROLLED)
    healthy = await check(TOK_ENROLLED_2)
    expired_again = await check(TOK_ENROLLED)
    healthy_again = await check(TOK_ENROLLED_2)

    assert not expired[0] and not expired_again[0]
    assert healthy == (True, "") and healthy_again == (True, "")
    assert wire.by(TOK_ENROLLED_2) == [course_read(TOK_ENROLLED_2)] * 2
    assert wire.by(TOK_ENROLLED) == [course_read(TOK_ENROLLED)] * 2


@pytest.mark.asyncio
async def test_wire_deny_by_default_verdict_is_not_reused_for_other_callers(wire):
    # A syllabus that states no policy yields the operator's default (deny here).
    # That conclusion needs a successful course read, so only a caller who made
    # one may reach it.
    wire.syllabus = "An ordinary syllabus that states no agent policy."

    enrolled = await check(TOK_ENROLLED)
    outsider = await check(TOK_OUTSIDER)

    assert not enrolled[0] and "has not opted in" in enrolled[1]
    assert not outsider[0] and "could not be checked" in outsider[1]
    assert wire.by(TOK_OUTSIDER) == [course_read(TOK_OUTSIDER)]


@pytest.mark.asyncio
async def test_wire_cached_grant_cannot_skip_loss_of_access(wire):
    assert await check(TOK_ENROLLED) == (True, "")

    wire.enrolled.discard("ada")  # Canvas now says no to this very token
    after = await check(TOK_ENROLLED)

    assert not after[0] and "could not be checked" in after[1]
    assert wire.by(TOK_ENROLLED) == [course_read(TOK_ENROLLED)] * 2


@pytest.mark.asyncio
async def test_wire_http_revocation_takes_effect_on_the_next_check(wire):
    assert await check(TOK_ENROLLED) == (True, "")

    wire.syllabus = "agent_writes: deny"
    allowed, reason = await check(TOK_ENROLLED)

    assert not allowed and "not permitted" in reason


@pytest.mark.asyncio
async def test_wire_http_request_without_token_sends_nothing_and_ignores_seeded_cache(wire):
    course_policy._policy_cache["123"] = (
        time.monotonic() + 600,
        CoursePolicy(True, None, "", "course_artifact"),
    )
    clear_http_request_context()
    set_http_request_active()

    allowed, _ = await check_student_write_allowed("123", TOOL)

    assert not allowed
    assert wire.seen == [], "an HTTP request with no token must not fall back to any credential"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first", "second"),
    [(TOK_ENROLLED, TOK_OUTSIDER), (TOK_OUTSIDER, TOK_ENROLLED)],
    ids=["enrolled-to-outsider", "outsider-to-enrolled"],
)
async def test_wire_credential_swapped_inside_one_request_context(wire, first, second):
    http_caller(first)
    before = await check_student_write_allowed("123", TOOL)
    # Same context, same process: only the credential changes.
    set_request_credentials(RequestCredentials(second, API_URL))
    after = await check_student_write_allowed("123", TOOL)

    assert (before[0], after[0]) == (first == TOK_ENROLLED, second == TOK_ENROLLED)
    assert wire.seen == [course_read(first), course_read(second)]
    assert not wire.writes()


@pytest.mark.asyncio
async def test_wire_token_rotation_for_one_canvas_user_rereads_under_the_new_token(wire):
    assert await check(TOK_OLD) == (True, "")
    assert await check(TOK_NEW) == (True, "")  # same Canvas user, new credential

    wire.revoked.add(TOK_OLD)  # the rotation retires the old token
    old_after_rotation = await check(TOK_OLD)
    new_after_rotation = await check(TOK_NEW)

    assert not old_after_rotation[0] and "could not be checked" in old_after_rotation[1]
    assert new_after_rotation == (True, "")
    assert wire.seen == [
        course_read(TOK_OLD),
        course_read(TOK_NEW),
        course_read(TOK_OLD),
        course_read(TOK_NEW),
    ]


async def run_concurrently(wire, callers, release_order, one_call):
    """Start every caller in its own task, then answer their reads in ``release_order``."""
    wire.held = set(callers)
    tasks = [asyncio.create_task(one_call(token)) for token in callers]
    await wire.wait_until_pending(*callers)
    for token in release_order:
        wire.release(token)
        while token in wire.pending:
            await asyncio.sleep(0)
    return await asyncio.gather(*tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_shared_cache", [False, True], ids=["cold", "stale-shared-entry"])
@pytest.mark.parametrize(
    "release_order",
    list(itertools.permutations((TOK_ENROLLED, TOK_ENROLLED_2, TOK_OUTSIDER))),
)
async def test_wire_concurrent_callers_each_get_their_own_verdict(wire, release_order, seed_shared_cache):
    callers = (TOK_ENROLLED, TOK_ENROLLED_2, TOK_OUTSIDER)
    seeded = (time.monotonic() + 600, CoursePolicy(True, None, "", "course_artifact"))
    if seed_shared_cache:
        course_policy._policy_cache["123"] = seeded
    wire.syllabus = DENY_WITH_NOTE

    async def one_call(token):
        http_caller(token)  # a task's own copy of the context, as in a real request
        verdict = await check_student_write_allowed("123", TOOL)
        creds = get_request_credentials()
        return token, verdict, creds.api_token if creds else None

    results = await run_concurrently(wire, callers, release_order, one_call)

    assert wire.peak_pending == 3, "the three reads must have been in flight together"
    for token, verdict, creds_after in results:
        assert creds_after == token, "a caller's credential must survive the interleaving"
        assert_verdict(token, verdict, DENY_WITH_NOTE)
    assert sorted(wire.seen) == sorted(course_read(token) for token in callers)
    assert not wire.writes()
    assert get_request_credentials() is None
    assert course_policy._policy_cache == ({"123": seeded} if seed_shared_cache else {})


@pytest.mark.asyncio
@pytest.mark.parametrize("release_order", [(TOK_ENROLLED, TOK_OUTSIDER), (TOK_OUTSIDER, TOK_ENROLLED)])
async def test_wire_concurrent_grant_is_not_lent_to_the_outsider(wire, release_order):
    callers = (TOK_ENROLLED, TOK_OUTSIDER)

    async def one_call(token):
        http_caller(token)
        return token, await check_student_write_allowed("123", TOOL)

    results = dict(await run_concurrently(wire, callers, release_order, one_call))

    assert results[TOK_ENROLLED] == (True, "")
    assert not results[TOK_OUTSIDER][0]
    # The outsider's own read went out and Canvas, not a cache, refused it.
    assert wire.by(TOK_OUTSIDER) == [course_read(TOK_OUTSIDER)]
    assert wire.by(TOK_ENROLLED) == [course_read(TOK_ENROLLED)]


@pytest.mark.asyncio
async def test_wire_policy_cache_holds_no_credential_and_logs_none(wire, caplog):
    caplog.set_level(logging.DEBUG, logger="canvas_mcp")
    wire.revoked.add(TOK_ENROLLED_2)

    for token in (TOK_ENROLLED, TOK_OUTSIDER, TOK_ENROLLED_2, TOK_NEW):
        await check(token)

    assert course_policy._policy_cache == {}
    for token in ALL_FAKE_TOKENS:
        assert token not in repr(course_policy._policy_cache)
        assert token not in caplog.text


@pytest.mark.asyncio
async def test_wire_stdio_keeps_its_cache_and_http_never_reads_it(wire):
    """stdio: one credential, one read, cached. An HTTP caller must still read for itself."""
    try:
        assert await check_student_write_allowed("123", TOOL) == (True, "")
        assert await check_student_write_allowed("123", TOOL) == (True, "")
        assert wire.seen == [course_read(TOK_STDIO)], "the second stdio check is served from its own cache"
        stdio_entry = dict(course_policy._policy_cache)
        assert set(stdio_entry) == {"123"}

        outsider = await check(TOK_OUTSIDER)

        assert not outsider[0] and "could not be checked" in outsider[1]
        assert wire.by(TOK_OUTSIDER) == [course_read(TOK_OUTSIDER)]
        assert course_policy._policy_cache == stdio_entry, "HTTP must not rewrite the stdio entry"
    finally:
        clear_http_request_context()
        await client_module.cleanup_http_client()


ONE_AT_A_TIME = [(TOK_ENROLLED, TOK_OUTSIDER), (TOK_OUTSIDER, TOK_ENROLLED)]
ONE_AT_A_TIME_IDS = ["enrolled-first", "outsider-first"]


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ONE_AT_A_TIME, ids=ONE_AT_A_TIME_IDS)
async def test_wire_tool_writes_only_for_the_caller_who_passes_the_gate(wire, order):
    comment = register_tools()[COMMENT_TOOL]

    outputs = {}
    for token in order:
        http_caller(token)
        outputs[token] = await comment(**COMMENT_ARGS)

    assert "Comment added" in outputs[TOK_ENROLLED]
    assert "Comment blocked" in outputs[TOK_OUTSIDER]
    # The only write on the wire is the enrolled caller's own, under its own token.
    assert wire.writes() == [Seen(TOK_ENROLLED, "PUT", SUBMISSION_PATH)]
    # The outsider made its own read, and nothing else.
    assert wire.by(TOK_OUTSIDER) == [course_read(TOK_OUTSIDER)]
    assert wire.by(TOK_ENROLLED) == [course_read(TOK_ENROLLED), Seen(TOK_ENROLLED, "PUT", SUBMISSION_PATH)]


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ONE_AT_A_TIME, ids=ONE_AT_A_TIME_IDS)
async def test_wire_tool_denied_policy_sends_no_write_and_note_stays_with_readers(wire, order):
    wire.syllabus = DENY_WITH_NOTE
    comment = register_tools()[COMMENT_TOOL]

    outputs = {}
    for token in order:
        http_caller(token)
        outputs[token] = await comment(**COMMENT_ARGS)

    assert INSTRUCTOR_NOTE in outputs[TOK_ENROLLED]
    assert INSTRUCTOR_NOTE not in outputs[TOK_OUTSIDER]
    assert all("Comment blocked" in text for text in outputs.values())
    assert wire.writes() == []
    assert sorted(wire.seen) == sorted(course_read(token) for token in order)


@pytest.mark.asyncio
async def test_wire_tool_concurrent_callers_write_only_as_the_enrolled_caller(wire):
    comment = register_tools()[COMMENT_TOOL]
    callers = (TOK_OUTSIDER, TOK_ENROLLED)

    async def one_call(token):
        http_caller(token)
        return token, await comment(**COMMENT_ARGS)

    results = dict(await run_concurrently(wire, callers, (TOK_ENROLLED, TOK_OUTSIDER), one_call))

    assert "Comment added" in results[TOK_ENROLLED]
    assert "Comment blocked" in results[TOK_OUTSIDER]
    assert wire.writes() == [Seen(TOK_ENROLLED, "PUT", SUBMISSION_PATH)]
    assert wire.by(TOK_OUTSIDER) == [course_read(TOK_OUTSIDER)]


@pytest.mark.asyncio
async def test_wire_tool_write_is_refused_after_the_callers_access_is_withdrawn(wire):
    comment = register_tools()[COMMENT_TOOL]
    http_caller(TOK_ENROLLED)
    assert "Comment added" in await comment(**COMMENT_ARGS)

    wire.enrolled.discard("ada")
    again = await comment(**COMMENT_ARGS)

    assert "Comment blocked" in again
    assert wire.writes() == [Seen(TOK_ENROLLED, "PUT", SUBMISSION_PATH)], "no second write after the loss of access"
