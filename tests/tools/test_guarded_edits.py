"""Issue 419: optional drift and fragment guards on the body-writing tools.

Each test drives the real tool against a small stateful fake of the Canvas
endpoints it touches and asserts the outgoing requests: above all, that a
refusal sends NO PUT, and that a plain call (no guard parameters) sends
exactly the request it sent before the guards existed.

The fakes keep the field sets Canvas really returns. In particular a
discussion topic has NO updated_at (measured live, read-only: a single-topic
GET's only timestamps are created_at, delayed_post_at, last_reply_at, lock_at
and posted_at), while pages and assignments do.
"""

import copy
import datetime
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.core.guarded_edit import parse_timestamp

COURSE_ID = 60366
OLD_TS = "2026-09-09T14:00:00Z"
NEW_TS = "2026-09-09T14:05:00Z"

ORIGINAL = "<p>Office hours: Monday 2pm.</p><p>Read chapter 3.</p>"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def capture_tools(register: Callable[[Any], None]) -> dict[str, Any]:
    """Register a tool group on a throwaway server and keep the raw functions."""
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    captured: dict[str, Any] = {}
    original_tool = mcp.tool

    def capturing_tool(*args: Any, **kwargs: Any) -> Any:
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn: Any) -> Any:
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool  # type: ignore[method-assign]
    register(mcp)
    return captured


def _initial_state(kind: str, body: str) -> dict[str, Any]:
    if kind == "page":
        return {"body": body, "title": "Week 1", "url": "week-1", "updated_at": OLD_TS,
                "published": True}
    if kind == "assignment":
        return {"description": body, "name": "Essay", "due_at": "2026-10-01T04:59:00Z",
                "points_possible": 10.0, "published": False, "updated_at": OLD_TS}
    # The real topic timestamp set: no updated_at.
    return {"message": body, "title": "Week 1 prompt", "created_at": "2026-08-20T15:00:00Z",
            "delayed_post_at": None, "last_reply_at": None, "lock_at": None,
            "posted_at": "2026-08-20T15:00:00Z", "published": True, "pinned": False,
            "locked": False, "require_initial_post": False}


class FakeCanvas:
    """One Canvas object behind GET/PUT, recording every request.

    ``advance`` controls whether a PUT moves updated_at forward (objects that
    have one), ``store`` whether it stores the body it was sent, and
    ``store_fields`` whether it stores the other fields. Turning any off
    simulates Canvas answering 200 while not doing (all of) the write; the old
    values stay, so a test can prove the tool notices. ``rewrite`` simulates
    Canvas sanitizing the stored HTML.
    """

    def __init__(self, kind: str, body: str, *, advance: bool = True, store: bool = True,
                 store_fields: bool = True, include_updated_at: bool = True,
                 rewrite: Callable[[str], str] | None = None) -> None:
        self.kind = kind
        self.body_field = {"page": "body", "assignment": "description", "topic": "message"}[kind]
        self.state = _initial_state(kind, body)
        if not include_updated_at:
            self.state.pop("updated_at", None)
        self.advance = advance
        self.store = store
        self.store_fields = store_fields
        self.rewrite = rewrite
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def put_bodies(self) -> list[Any]:
        return [kw.get("data") for method, _, kw in self.calls if method == "put"]

    async def __call__(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if method == "get":
            return copy.deepcopy(self.state)
        payload = kwargs["data"]
        inner = payload.get("wiki_page") or payload.get("assignment") or payload
        for field, value in inner.items():
            if field == self.body_field:
                if self.store:
                    self.state[field] = self.rewrite(value) if self.rewrite else value
            elif self.store_fields:
                if field.endswith("_at") and isinstance(value, str):
                    # Canvas echoes dates back in UTC Z form, not as sent.
                    parsed = parse_timestamp(value)
                    assert parsed is not None
                    value = parsed.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                self.state[field] = value
        if self.advance and "updated_at" in self.state:
            self.state["updated_at"] = NEW_TS
        return copy.deepcopy(self.state)


@dataclass
class ToolSpec:
    name: str
    kind: str
    module: str
    register: str
    body_param: str
    path: str
    args: tuple[Any, ...]

    def tool(self) -> Any:
        import importlib

        module = importlib.import_module(self.module)
        return capture_tools(getattr(module, self.register))[self.name]

    def fake(self, body: str = ORIGINAL, **options: Any) -> FakeCanvas:
        return FakeCanvas(self.kind, body, **options)

    def put_body(self, data: dict[str, Any]) -> Any:
        inner = data.get("wiki_page") or data.get("assignment") or data
        return inner.get({"page": "body", "assignment": "description", "topic": "message"}[self.kind])


PAGE = ToolSpec("edit_page_content", "page", "canvas_mcp.tools.pages",
                "register_educator_page_crud_tools", "new_content",
                f"/courses/{COURSE_ID}/pages/week-1", ("CS101", "week-1"))
ASSIGNMENT = ToolSpec("update_assignment", "assignment", "canvas_mcp.tools.assignments",
                      "register_educator_assignment_tools", "description",
                      f"/courses/{COURSE_ID}/assignments/77", ("CS101", 77))
TOPIC = ToolSpec("update_discussion_topic", "topic", "canvas_mcp.tools.discussions",
                 "register_educator_discussion_tools", "message",
                 f"/courses/{COURSE_ID}/discussion_topics/42", ("CS101", 42))
SPECS = [PAGE, ASSIGNMENT, TOPIC]
IDS = [s.name for s in SPECS]
# Objects Canvas gives an updated_at.
TS_SPECS = [PAGE, ASSIGNMENT]
TS_IDS = [s.name for s in TS_SPECS]


@pytest.fixture
def canvas_for():
    """Patch one tool module's Canvas access with a FakeCanvas."""
    patches: list[Any] = []

    def install(spec: ToolSpec, fake: FakeCanvas) -> FakeCanvas:
        for target, value in (
            ("get_course_id", AsyncMock(return_value=COURSE_ID)),
            ("get_course_code", AsyncMock(return_value="CS101")),
            ("make_canvas_request", AsyncMock(side_effect=fake.__call__)),
        ):
            p = patch(f"{spec.module}.{target}", value)
            p.start()
            patches.append(p)
        return fake

    yield install
    for p in patches:
        p.stop()


def assert_unconfirmed(result: str, reason_fragment: str) -> None:
    assert "Could not confirm" in result, result
    assert reason_fragment in result, result
    assert "✅" not in result and "Verified" not in result, result


# --------------------------------------------------------------------------
# Plain calls preserve their write payload; topics add an anonymity preflight.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_plain_call_preserves_write_payload(spec, canvas_for):
    fake = canvas_for(spec, spec.fake())

    await spec.tool()(*spec.args, **{spec.body_param: "<p>New body</p>"})

    expected_data = {
        "edit_page_content": {"wiki_page": {"body": "<p>New body</p>"}},
        "update_assignment": {"assignment": {"description": "<p>New body</p>"}},
        "update_discussion_topic": {"message": "<p>New body</p>"},
    }[spec.name]
    expected_calls = [("put", spec.path, {"data": expected_data})]
    if spec.name == "update_discussion_topic":
        expected_calls.insert(0, ("get", spec.path, {}))
    assert fake.calls == expected_calls


# --------------------------------------------------------------------------
# Drift: updated_at for pages and assignments
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("spec", TS_SPECS, ids=TS_IDS)
async def test_drift_refuses_and_reports_both_values(spec, canvas_for):
    fake = canvas_for(spec, spec.fake())

    result = await spec.tool()(
        *spec.args, **{spec.body_param: "<p>Stale copy</p>"},
        expect_updated_at="2026-09-09T13:00:00Z",
    )

    assert result.startswith("❌"), result
    assert "2026-09-09T13:00:00Z" in result and OLD_TS in result
    assert fake.put_bodies() == []
    assert fake.state[fake.body_field] == ORIGINAL


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", TS_SPECS, ids=TS_IDS)
async def test_same_instant_in_offset_form_passes(spec, canvas_for):
    """14:00Z and 09:00-05:00 are one instant; a string compare would refuse."""
    fake = canvas_for(spec, spec.fake())

    result = await spec.tool()(
        *spec.args, **{spec.body_param: "<p>Fresh copy</p>"},
        expect_updated_at="2026-09-09T09:00:00-05:00",
    )

    assert result.startswith("✅"), result
    assert [spec.put_body(d) for d in fake.put_bodies()] == ["<p>Fresh copy</p>"]
    assert OLD_TS in result and NEW_TS in result


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", TS_SPECS, ids=TS_IDS)
async def test_missing_updated_at_refuses_rather_than_guessing(spec, canvas_for):
    fake = canvas_for(spec, spec.fake(include_updated_at=False))

    result = await spec.tool()(
        *spec.args, **{spec.body_param: "<p>x</p>"}, expect_updated_at=OLD_TS,
    )

    assert result.startswith("❌"), result
    assert fake.put_bodies() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", TS_SPECS, ids=TS_IDS)
async def test_readback_where_updated_at_did_not_advance_is_unconfirmed(spec, canvas_for):
    fake = canvas_for(spec, spec.fake(advance=False))

    result = await spec.tool()(*spec.args, find="Monday 2pm", replace="Tuesday 3pm")

    assert len(fake.put_bodies()) == 1
    assert_unconfirmed(result, "did not advance")


# --------------------------------------------------------------------------
# Drift: body hash for discussion topics (no updated_at in Canvas)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_topic_expect_updated_at_is_an_error_naming_the_alternative(canvas_for):
    fake = canvas_for(TOPIC, TOPIC.fake())

    result = await TOPIC.tool()("CS101", 42, message="<p>x</p>", expect_updated_at=OLD_TS)

    assert result.startswith("❌"), result
    assert "expect_body_sha256" in result
    assert fake.calls == []


@pytest.mark.asyncio
async def test_topic_hash_drift_refuses_and_reports_both_hashes(canvas_for):
    fake = canvas_for(TOPIC, TOPIC.fake())
    stale = _sha("<p>What I read an hour ago</p>")

    result = await TOPIC.tool()(
        "CS101", 42, find="Monday 2pm", replace="Tuesday 3pm", expect_body_sha256=stale,
    )

    assert result.startswith("❌"), result
    assert stale in result and _sha(ORIGINAL) in result
    assert fake.put_bodies() == []


@pytest.mark.asyncio
async def test_topic_matching_hash_writes_and_reports_old_and_new_hash(canvas_for):
    fake = canvas_for(TOPIC, TOPIC.fake())

    result = await TOPIC.tool()(
        "CS101", 42, find="Monday 2pm", replace="Tuesday 3pm",
        expect_body_sha256=_sha(ORIGINAL).upper(),
    )

    expected = "<p>Office hours: Tuesday 3pm.</p><p>Read chapter 3.</p>"
    assert fake.put_bodies() == [{"message": expected}]
    assert result.startswith("✅"), result
    assert f"Previous body SHA-256: {_sha(ORIGINAL)}" in result
    assert f"New body SHA-256: {_sha(expected)}" in result
    assert "updated_at" not in result


@pytest.mark.asyncio
async def test_topic_hash_printed_by_the_read_tool_is_the_one_the_guard_accepts(canvas_for):
    """get_discussion_topic_details gives the caller a starting hash; once the
    message changes, that same hash must be refused."""
    import re

    from canvas_mcp.tools.discussions import register_shared_discussion_tools

    fake = canvas_for(TOPIC, TOPIC.fake())
    read = capture_tools(register_shared_discussion_tools)["get_discussion_topic_details"]

    details = await read("CS101", 42)
    match = re.search(
        r"Body SHA-256 \(pass as expect_body_sha256 to update_discussion_topic\): ([0-9a-f]{64})",
        details,
    )
    assert match, details
    printed = match.group(1)
    assert printed == _sha(ORIGINAL)  # independent of the code under test

    result = await TOPIC.tool()(
        "CS101", 42, find="Monday 2pm", replace="Tuesday 3pm", expect_body_sha256=printed,
    )
    assert result.startswith("✅"), result
    assert len(fake.put_bodies()) == 1

    # A colleague edits the message; the hash read earlier is now stale.
    fake.state["message"] = "<p>Office hours moved by a colleague.</p><p>Read chapter 3.</p>"
    stale = await TOPIC.tool()(
        "CS101", 42, find="Read chapter 3.", replace="Read chapter 4.", expect_body_sha256=printed,
    )
    assert stale.startswith("❌"), stale
    assert len(fake.put_bodies()) == 1, "a refused edit must not PUT"


@pytest.mark.asyncio
async def test_topic_malformed_hash_is_an_error(canvas_for):
    fake = canvas_for(TOPIC, TOPIC.fake())

    result = await TOPIC.tool()("CS101", 42, message="<p>x</p>", expect_body_sha256="abc")

    assert result.startswith("❌"), result
    assert fake.calls == []


# --------------------------------------------------------------------------
# find / replace / require
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_find_replace_writes_the_substituted_body(spec, canvas_for):
    fake = canvas_for(spec, spec.fake())

    result = await spec.tool()(
        *spec.args, find="Monday 2pm", replace="Tuesday 3pm", require=["Read chapter 3."],
    )

    # Hand-derived expectation, not computed by the code under test.
    expected = "<p>Office hours: Tuesday 3pm.</p><p>Read chapter 3.</p>"
    assert [spec.put_body(d) for d in fake.put_bodies()] == [expected]
    assert [m for m, _, _ in fake.calls] == ["get", "put", "get"]
    assert result.startswith("✅"), result


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", TS_SPECS, ids=TS_IDS)
async def test_find_replace_reports_old_and_new_updated_at(spec, canvas_for):
    canvas_for(spec, spec.fake())

    result = await spec.tool()(
        *spec.args, find="Monday 2pm", replace="Tuesday 3pm", expect_updated_at=OLD_TS,
    )

    assert f"Previous updated_at: {OLD_TS}" in result
    assert f"New updated_at: {NEW_TS}" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_find_with_zero_matches_refuses(spec, canvas_for):
    fake = canvas_for(spec, spec.fake())

    result = await spec.tool()(*spec.args, find="Friday", replace="Saturday")

    assert result.startswith("❌"), result
    assert "matched 0 times" in result
    assert fake.put_bodies() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_find_with_two_matches_refuses(spec, canvas_for):
    fake = canvas_for(spec, spec.fake())

    result = await spec.tool()(*spec.args, find="<p>", replace="<p class='x'>")

    assert result.startswith("❌"), result
    assert "matched 2 times" in result
    assert fake.put_bodies() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_missing_require_string_refuses(spec, canvas_for):
    fake = canvas_for(spec, spec.fake())

    result = await spec.tool()(
        *spec.args, find="Monday 2pm", replace="Tuesday 3pm",
        require=["Read chapter 3.", "Quiz on Friday"],
    )

    assert result.startswith("❌"), result
    assert "Quiz on Friday" in result
    assert fake.put_bodies() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_full_body_and_find_together_is_an_error(spec, canvas_for):
    fake = canvas_for(spec, spec.fake())

    result = await spec.tool()(
        *spec.args, **{spec.body_param: "<p>All</p>"}, find="Monday", replace="Tuesday",
    )

    assert result.startswith("❌"), result
    assert fake.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_find_without_replace_is_an_error(spec, canvas_for):
    fake = canvas_for(spec, spec.fake())

    result = await spec.tool()(*spec.args, find="Monday")

    assert result.startswith("❌"), result
    assert fake.calls == []


# --------------------------------------------------------------------------
# Post-write read-back of the body
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_readback_missing_the_replacement_is_unconfirmed(spec, canvas_for):
    """Canvas bumps updated_at (where it has one) but keeps the old body."""
    fake = canvas_for(spec, spec.fake(store=False))

    result = await spec.tool()(*spec.args, find="Monday 2pm", replace="Tuesday 3pm")

    assert len(fake.put_bodies()) == 1
    assert_unconfirmed(result, "is not the expected body")


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_failed_deletion_is_not_reported_as_verified(spec, canvas_for):
    """The kept text is present either way; only the removed text proves it."""
    body = "<p>Keep me</p><p>Remove me</p>"
    fake = canvas_for(spec, spec.fake(body, store=False))

    result = await spec.tool()(
        *spec.args, find="<p>Keep me</p><p>Remove me</p>", replace="<p>Keep me</p>",
    )

    assert [spec.put_body(d) for d in fake.put_bodies()] == ["<p>Keep me</p>"]
    assert_unconfirmed(result, "is not the expected body")


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_deletion_that_lost_unrelated_content_is_not_verified(spec, canvas_for):
    """find is gone and the (empty) replacement is trivially present, but the
    kept paragraph vanished too: only whole-body equality catches this."""
    body = "<p>Keep me</p><p>Remove me</p>"
    fake = canvas_for(spec, spec.fake(body, rewrite=lambda _html: ""))

    result = await spec.tool()(*spec.args, find="<p>Remove me</p>", replace="")

    assert [spec.put_body(d) for d in fake.put_bodies()] == ["<p>Keep me</p>"]
    assert_unconfirmed(result, "is not the expected body")


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_edit_that_lost_unrelated_content_is_not_verified(spec, canvas_for):
    """The replacement landed but Canvas dropped the second paragraph."""
    fake = canvas_for(spec, spec.fake(
        rewrite=lambda html: html.replace("<p>Read chapter 3.</p>", "")))

    result = await spec.tool()(*spec.args, find="Monday 2pm", replace="Tuesday 3pm")

    assert len(fake.put_bodies()) == 1
    assert_unconfirmed(result, "is not the expected body")


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_deletion_that_landed_exactly_is_verified(spec, canvas_for):
    canvas_for(spec, spec.fake("<p>Keep me</p><p>Remove me</p>"))

    result = await spec.tool()(*spec.args, find="<p>Remove me</p>", replace="")

    assert result.startswith("✅"), result


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_failed_attribute_only_edit_is_not_reported_as_verified(spec, canvas_for):
    """Visible text is identical before and after an href change."""
    body = '<p><a href="https://old.example/syllabus">Syllabus</a></p>'
    fake = canvas_for(spec, spec.fake(body, store=False))

    result = await spec.tool()(
        *spec.args, find="https://old.example/syllabus", replace="https://new.example/syllabus",
    )

    assert len(fake.put_bodies()) == 1
    assert_unconfirmed(result, "is not the expected body")


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_attribute_only_edit_that_landed_is_verified(spec, canvas_for):
    body = '<p><a href="https://old.example/syllabus">Syllabus</a></p>'
    canvas_for(spec, spec.fake(body))

    result = await spec.tool()(
        *spec.args, find="https://old.example/syllabus", replace="https://new.example/syllabus",
    )

    assert result.startswith("✅"), result


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_find_inside_replace_needs_a_new_occurrence(spec, canvas_for):
    """Appending after find: success means one more copy of replace."""
    fake = canvas_for(spec, spec.fake(store=False))

    result = await spec.tool()(
        *spec.args, find="Read chapter 3.", replace="Read chapter 3. Then chapter 4.",
    )

    assert len(fake.put_bodies()) == 1
    assert_unconfirmed(result, "is not the expected body")


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_whitespace_only_rewrite_still_verifies(spec, canvas_for):
    canvas_for(spec, spec.fake(rewrite=lambda html: html.replace("</p><p>", "</p>\n  <p>")))

    result = await spec.tool()(*spec.args, find="Monday 2pm", replace="Tuesday 3pm")

    assert result.startswith("✅"), result


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_full_body_rewritten_by_canvas_is_unconfirmed(spec, canvas_for):
    """When markup differs from what was sent, it cannot be called verified."""
    canvas_for(spec, spec.fake(rewrite=lambda html: html.replace(' rel="noopener"', "")))
    guard = ({"expect_updated_at": OLD_TS} if spec in TS_SPECS
             else {"expect_body_sha256": _sha(ORIGINAL)})

    result = await spec.tool()(
        *spec.args, **{spec.body_param: '<p><a href="/x" rel="noopener">x</a></p>'}, **guard,
    )

    assert_unconfirmed(result, "is not the expected body")


# --------------------------------------------------------------------------
# Post-write read-back of the other requested fields
# --------------------------------------------------------------------------

FIELD_CASES = [
    (PAGE, {"title": "Week one"}, "title"),
    (ASSIGNMENT, {"name": "Essay 1", "due_at": "2026-10-08T23:59:00-05:00",
                  "points_possible": 20, "published": True}, "name, due_at, points_possible, published"),
    (TOPIC, {"title": "Week 1 prompt (revised)", "pinned": True, "locked": True},
     "title, pinned, locked"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("spec", "fields", "names"), FIELD_CASES, ids=IDS)
async def test_other_fields_that_did_not_save_are_unconfirmed(spec, fields, names, canvas_for):
    """Body lands, the other requested fields keep their old values."""
    fake = canvas_for(spec, spec.fake(store_fields=False))

    result = await spec.tool()(*spec.args, find="Monday 2pm", replace="Tuesday 3pm", **fields)

    assert len(fake.put_bodies()) == 1
    assert_unconfirmed(result, f"did not read back with the value sent: {names}")


@pytest.mark.asyncio
@pytest.mark.parametrize(("spec", "fields", "names"), FIELD_CASES, ids=IDS)
async def test_other_fields_that_saved_are_verified(spec, fields, names, canvas_for):
    """Includes a due date sent as -05:00 and echoed back by Canvas as Z."""
    canvas_for(spec, spec.fake())

    result = await spec.tool()(*spec.args, find="Monday 2pm", replace="Tuesday 3pm", **fields)

    assert result.startswith("✅"), result


@pytest.mark.asyncio
async def test_assignment_guard_without_body_change_checks_the_field(canvas_for):
    fake = canvas_for(ASSIGNMENT, ASSIGNMENT.fake(store_fields=False))

    result = await ASSIGNMENT.tool()("CS101", 77, name="Essay 1", expect_updated_at=OLD_TS)

    assert fake.put_bodies() == [{"assignment": {"name": "Essay 1"}}]
    assert_unconfirmed(result, "did not read back with the value sent: name")


@pytest.mark.asyncio
async def test_page_readback_follows_a_renamed_slug(canvas_for):
    fake = PAGE.fake()
    canvas_for(PAGE, fake)

    async def renaming(method: str, path: str, **kwargs: Any) -> Any:
        result = await FakeCanvas.__call__(fake, method, path, **kwargs)
        if method == "put":
            fake.state["url"] = "week-one"
            result["url"] = "week-one"
        return result

    with patch("canvas_mcp.tools.pages.make_canvas_request", AsyncMock(side_effect=renaming)):
        result = await PAGE.tool()(
            "CS101", "week-1", find="Monday 2pm", replace="Tuesday 3pm", title="Week one",
        )

    assert fake.calls[-1][:2] == ("get", f"/courses/{COURSE_ID}/pages/week-one")
    assert fake.put_bodies()[0]["wiki_page"]["title"] == "Week one"
    assert result.startswith("✅"), result


@pytest.mark.parametrize(("a", "b", "same"), [
    ("2026-09-09T14:00:00Z", "2026-09-09T14:00:00+00:00", True),
    ("2026-09-09T14:00:00Z", "2026-09-09T09:00:00-05:00", True),
    ("2026-09-09T14:00:00Z", "2026-09-09T14:00:00.000Z", True),
    ("2026-09-09T14:00:00Z", "2026-09-09T14:00:01Z", False),
    ("2026-09-09T14:00:00Z", "2026-09-09T14:00:00-05:00", False),
])
def test_parse_timestamp_compares_instants(a, b, same):
    assert (parse_timestamp(a) == parse_timestamp(b)) is same


def test_parse_timestamp_rejects_garbage():
    assert parse_timestamp("last Tuesday") is None
    assert parse_timestamp("") is None


# --------------------------------------------------------------------------
# update_syllabus: body hash instead of updated_at; token flow intact
# --------------------------------------------------------------------------

class FakeSyllabus:
    def __init__(self, body: str, *, store: bool = True, inject: str = "",
                 rewrite: Callable[[str], str] | None = None) -> None:
        self.body = body
        self.store = store
        # Canvas's sanitizer rewriting the stored HTML.
        self.rewrite = rewrite
        # Theme injection Canvas adds to the stored body on every write.
        self.inject = inject
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def puts(self) -> list[str]:
        return [kw["data"]["course"]["syllabus_body"] for m, _, kw in self.calls if m == "put"]

    async def __call__(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if method == "put":
            if self.store:
                sent = kwargs["data"]["course"]["syllabus_body"]
                self.body = self.rewrite(sent) if self.rewrite else sent
            self.body += self.inject
            return {"id": COURSE_ID, "course_code": "CS101"}
        return {"course_code": "CS101", "syllabus_body": self.body}


@pytest.fixture
def syllabus_tools():
    from canvas_mcp.tools.courses import (
        register_course_tools,
        register_educator_course_tools,
    )

    tools = capture_tools(register_educator_course_tools)
    tools.update(capture_tools(register_course_tools))
    return tools


@pytest.fixture
def syllabus_canvas():
    patches: list[Any] = []

    def install(fake: FakeSyllabus) -> FakeSyllabus:
        for target, value in (
            ("get_course_id", AsyncMock(return_value=COURSE_ID)),
            ("make_canvas_request", AsyncMock(side_effect=fake.__call__)),
        ):
            p = patch(f"canvas_mcp.tools.courses.{target}", value)
            p.start()
            patches.append(p)
        return fake

    yield install
    for p in patches:
        p.stop()


def _token(preview: str) -> str:
    return preview.split("Confirmation token: ", 1)[1].split("\n", 1)[0].strip()


@pytest.mark.asyncio
async def test_plain_syllabus_call_sends_exactly_the_pre_419_requests(syllabus_tools, syllabus_canvas):
    fake = syllabus_canvas(FakeSyllabus(""))

    await syllabus_tools["update_syllabus"]("CS101", "<p>See the website</p>")

    read = {"params": {"include[]": "syllabus_body"}}
    assert fake.calls == [
        ("get", f"/courses/{COURSE_ID}", read),
        ("put", f"/courses/{COURSE_ID}", {"data": {"course": {"syllabus_body": "<p>See the website</p>"}}}),
        ("get", f"/courses/{COURSE_ID}", read),
    ]


@pytest.mark.asyncio
async def test_syllabus_hash_drift_refuses(syllabus_tools, syllabus_canvas):
    fake = syllabus_canvas(FakeSyllabus(ORIGINAL))
    stale = _sha("<p>What I read an hour ago</p>")

    result = await syllabus_tools["update_syllabus"](
        "CS101", find="Monday 2pm", replace="Tuesday 3pm", expect_body_sha256=stale,
    )

    assert result.startswith("❌"), result
    assert stale in result and _sha(ORIGINAL) in result
    assert fake.puts() == []


@pytest.mark.asyncio
async def test_syllabus_find_replace_still_previews_then_confirms(syllabus_tools, syllabus_canvas):
    fake = syllabus_canvas(FakeSyllabus(ORIGINAL))
    update = syllabus_tools["update_syllabus"]
    args = {"find": "Monday 2pm", "replace": "Tuesday 3pm", "expect_body_sha256": _sha(ORIGINAL)}

    preview = await update("CS101", **args)
    assert fake.puts() == [], "a find/replace over existing content must preview first"
    assert "Confirmation token:" in preview

    result = await update("CS101", **args, confirmation_token=_token(preview))

    expected = "<p>Office hours: Tuesday 3pm.</p><p>Read chapter 3.</p>"
    assert fake.puts() == [expected]
    assert result.startswith("✅"), result
    assert f"Previous body SHA-256: {_sha(ORIGINAL)}" in result
    assert f"New body SHA-256: {_sha(expected)}" in result


@pytest.mark.asyncio
async def test_syllabus_token_from_a_different_guarded_call_does_not_confirm(syllabus_tools, syllabus_canvas):
    fake = syllabus_canvas(FakeSyllabus(ORIGINAL))
    update = syllabus_tools["update_syllabus"]

    preview = await update("CS101", find="Monday 2pm", replace="Tuesday 3pm")
    result = await update(
        "CS101", find="Monday 2pm", replace="Tuesday 3pm", require=["chapter 3"],
        confirmation_token=_token(preview),
    )

    assert result.startswith("❌"), result
    assert fake.puts() == []


@pytest.mark.asyncio
async def test_syllabus_missing_require_refuses(syllabus_tools, syllabus_canvas):
    fake = syllabus_canvas(FakeSyllabus(ORIGINAL))

    result = await syllabus_tools["update_syllabus"](
        "CS101", "<p>more</p>", mode="append", require=["Quiz on Friday"],
    )

    assert result.startswith("❌"), result
    assert fake.puts() == []


@pytest.mark.asyncio
async def test_syllabus_find_with_append_mode_is_an_error(syllabus_tools, syllabus_canvas):
    fake = syllabus_canvas(FakeSyllabus(ORIGINAL))

    result = await syllabus_tools["update_syllabus"](
        "CS101", find="Monday", replace="Tuesday", mode="append",
    )

    assert result.startswith("❌"), result
    assert fake.calls == []


@pytest.mark.asyncio
async def test_syllabus_guarded_write_with_unchanged_body_is_unconfirmed(syllabus_tools, syllabus_canvas):
    fake = syllabus_canvas(FakeSyllabus(ORIGINAL, store=False))

    result = await syllabus_tools["update_syllabus"](
        "CS101", "<p>Office hours</p>", mode="append", expect_body_sha256=_sha(ORIGINAL),
    )

    assert len(fake.puts()) == 1
    assert "Could not confirm" in result
    assert "✅" not in result


@pytest.mark.asyncio
async def test_get_syllabus_prints_the_hash_update_syllabus_expects(syllabus_tools, syllabus_canvas):
    syllabus_canvas(FakeSyllabus(ORIGINAL))

    result = await syllabus_tools["get_syllabus"]("CS101")

    assert f"Body SHA-256 (pass as expect_body_sha256 to update_syllabus): {_sha(ORIGINAL)}" in result


@pytest.mark.asyncio
async def test_syllabus_failed_deletion_is_not_reported_as_verified(syllabus_tools, syllabus_canvas):
    """Canvas keeps the old body but injects a theme tag, so the hash moves and
    the kept text is present; only the still-present removed text shows the
    edit did not land."""
    body = "<p>Keep me</p><p>Remove me</p>"
    fake = syllabus_canvas(FakeSyllabus(body, store=False, inject='<link rel="stylesheet" href="/theme.css">'))
    update = syllabus_tools["update_syllabus"]
    args = {"find": "<p>Keep me</p><p>Remove me</p>", "replace": "<p>Keep me</p>"}

    preview = await update("CS101", **args)
    result = await update("CS101", **args, confirmation_token=_token(preview))

    assert fake.puts() == ["<p>Keep me</p>"]
    assert "Could not confirm" in result, result
    assert "is not the expected body" in result
    assert "✅" not in result


STRIP_NOOPENER = {"rewrite": lambda html: html.replace(' rel="noopener"', "")}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["replace", "append", "prepend"])
async def test_syllabus_guarded_write_with_a_dropped_attribute_is_unconfirmed(
    syllabus_tools, syllabus_canvas, mode
):
    """Visible text is identical after Canvas strips rel="noopener"; the
    stored HTML is not the HTML that was meant to be written."""
    fake = syllabus_canvas(FakeSyllabus(ORIGINAL, **STRIP_NOOPENER))
    update = syllabus_tools["update_syllabus"]
    args = {"syllabus_body": '<p><a href="/x" rel="noopener">x</a></p>', "mode": mode,
            "expect_body_sha256": _sha(ORIGINAL)}

    first = await update("CS101", **args)
    if mode == "replace":
        assert fake.puts() == [], "a replace over existing content previews first"
        result = await update("CS101", **args, confirmation_token=_token(first))
    else:
        result = first  # append/prepend destroy nothing: one call writes

    assert len(fake.puts()) == 1
    assert "Could not confirm" in result, result
    assert "is not the expected body" in result
    assert "✅" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize(("mode", "expected"), [
    ("replace", '<p><a href="/x" rel="noopener">x</a></p>'),
    ("append", ORIGINAL + '\n<p><a href="/x" rel="noopener">x</a></p>'),
    ("prepend", '<p><a href="/x" rel="noopener">x</a></p>\n' + ORIGINAL),
])
async def test_syllabus_guarded_write_stored_exactly_is_verified(
    syllabus_tools, syllabus_canvas, mode, expected
):
    fake = syllabus_canvas(FakeSyllabus(ORIGINAL))
    update = syllabus_tools["update_syllabus"]
    args = {"syllabus_body": '<p><a href="/x" rel="noopener">x</a></p>', "mode": mode,
            "expect_body_sha256": _sha(ORIGINAL)}

    first = await update("CS101", **args)
    result = (await update("CS101", **args, confirmation_token=_token(first))
              if mode == "replace" else first)

    assert fake.puts() == [expected]
    assert result.startswith("✅"), result


@pytest.mark.asyncio
async def test_syllabus_fragment_edit_that_lost_unrelated_content_is_unconfirmed(
    syllabus_tools, syllabus_canvas
):
    fake = syllabus_canvas(FakeSyllabus(
        "<p>Keep me</p><p>Remove me</p>", rewrite=lambda _html: "<p>x</p>"))
    update = syllabus_tools["update_syllabus"]
    args = {"find": "<p>Remove me</p>", "replace": ""}

    preview = await update("CS101", **args)
    result = await update("CS101", **args, confirmation_token=_token(preview))

    assert fake.puts() == ["<p>Keep me</p>"]
    assert "Could not confirm" in result, result
    assert "✅" not in result


@pytest.mark.asyncio
async def test_unguarded_syllabus_write_keeps_the_visible_text_check(syllabus_tools, syllabus_canvas):
    """No guard parameters: today's behavior, where Canvas stripping an
    attribute still reads as success with a 'rewritten copy' note."""
    syllabus_canvas(FakeSyllabus("", **STRIP_NOOPENER))

    result = await syllabus_tools["update_syllabus"](
        "CS101", '<p><a href="/x" rel="noopener">x</a></p>')

    assert result.startswith("✅"), result
    assert "rewritten copy" in result
