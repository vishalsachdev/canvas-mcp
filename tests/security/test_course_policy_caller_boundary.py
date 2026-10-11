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

import time
from unittest.mock import patch

import pytest
from fastmcp import FastMCP

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
