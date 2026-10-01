"""Issue 419: optional drift and fragment guards on the body-writing tools.

Each test drives the real tool against a small stateful fake of the Canvas
endpoints it touches and asserts the outgoing requests: above all, that a
refusal sends NO PUT, and that a plain call (no guard parameters) sends
exactly the request it sent before the guards existed.
"""

import copy
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


class FakeCanvas:
    """One Canvas object behind GET/PUT, recording every request.

    ``advance`` controls whether a PUT moves updated_at forward; ``store``
    controls whether it actually stores the body it was sent. Turning either
    off simulates Canvas answering 200 while not doing the write.
    """

    def __init__(self, body_field: str, body: str, *, advance: bool = True,
                 store: bool = True, include_updated_at: bool = True) -> None:
        self.body_field = body_field
        self.state: dict[str, Any] = {body_field: body, "url": "week-1"}
        if include_updated_at:
            self.state["updated_at"] = OLD_TS
        self.advance = advance
        self.store = store
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def put_bodies(self) -> list[Any]:
        return [kw.get("data") for method, _, kw in self.calls if method == "put"]

    async def __call__(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if method == "get":
            return copy.deepcopy(self.state)
        payload = kwargs["data"]
        inner = payload.get("wiki_page") or payload.get("assignment") or payload
        if self.store and self.body_field in inner:
            self.state[self.body_field] = inner[self.body_field]
        if self.advance and "updated_at" in self.state:
            self.state["updated_at"] = NEW_TS
        return copy.deepcopy(self.state)


@dataclass
class ToolSpec:
    name: str
    module: str
    register: str
    body_field: str
    body_param: str
    path: str
    args: tuple[Any, ...]

    def tool(self) -> Any:
        import importlib

        module = importlib.import_module(self.module)
        return capture_tools(getattr(module, self.register))[self.name]

    def put_body(self, data: dict[str, Any]) -> Any:
        inner = data.get("wiki_page") or data.get("assignment") or data
        return inner.get(self.body_field)


PAGE = ToolSpec("edit_page_content", "canvas_mcp.tools.pages",
                "register_educator_page_crud_tools", "body", "new_content",
                f"/courses/{COURSE_ID}/pages/week-1", ("CS101", "week-1"))
ASSIGNMENT = ToolSpec("update_assignment", "canvas_mcp.tools.assignments",
                      "register_educator_assignment_tools", "description", "description",
                      f"/courses/{COURSE_ID}/assignments/77", ("CS101", 77))
TOPIC = ToolSpec("update_discussion_topic", "canvas_mcp.tools.discussions",
                 "register_educator_discussion_tools", "message", "message",
                 f"/courses/{COURSE_ID}/discussion_topics/42", ("CS101", 42))
SPECS = [PAGE, ASSIGNMENT, TOPIC]
IDS = [s.name for s in SPECS]

ORIGINAL = "<p>Office hours: Monday 2pm.</p><p>Read chapter 3.</p>"


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


# --------------------------------------------------------------------------
# Plain calls are unchanged
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_plain_call_sends_exactly_the_pre_419_request(spec, canvas_for):
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL))

    await spec.tool()(*spec.args, **{spec.body_param: "<p>New body</p>"})

    expected_data = {
        "edit_page_content": {"wiki_page": {"body": "<p>New body</p>"}},
        "update_assignment": {"assignment": {"description": "<p>New body</p>"}},
        "update_discussion_topic": {"message": "<p>New body</p>"},
    }[spec.name]
    assert fake.calls == [("put", spec.path, {"data": expected_data})]


# --------------------------------------------------------------------------
# expect_updated_at
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_drift_refuses_and_reports_both_values(spec, canvas_for):
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL))

    result = await spec.tool()(
        *spec.args, **{spec.body_param: "<p>Stale copy</p>"},
        expect_updated_at="2026-09-09T13:00:00Z",
    )

    assert result.startswith("❌"), result
    assert "2026-09-09T13:00:00Z" in result and OLD_TS in result
    assert fake.put_bodies() == []
    assert fake.state[spec.body_field] == ORIGINAL


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_same_instant_in_offset_form_passes(spec, canvas_for):
    """14:00Z and 09:00-05:00 are one instant; a string compare would refuse."""
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL))

    result = await spec.tool()(
        *spec.args, **{spec.body_param: "<p>Fresh copy</p>"},
        expect_updated_at="2026-09-09T09:00:00-05:00",
    )

    assert result.startswith("✅"), result
    assert [spec.put_body(d) for d in fake.put_bodies()] == ["<p>Fresh copy</p>"]
    assert OLD_TS in result and NEW_TS in result


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_missing_updated_at_refuses_rather_than_guessing(spec, canvas_for):
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL, include_updated_at=False))

    result = await spec.tool()(
        *spec.args, **{spec.body_param: "<p>x</p>"}, expect_updated_at=OLD_TS,
    )

    assert result.startswith("❌"), result
    assert fake.put_bodies() == []


# --------------------------------------------------------------------------
# find / replace / require
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_find_replace_writes_the_substituted_body(spec, canvas_for):
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL))

    result = await spec.tool()(
        *spec.args, find="Monday 2pm", replace="Tuesday 3pm",
        require=["Read chapter 3."], expect_updated_at=OLD_TS,
    )

    # Hand-derived expectation, not computed by the code under test.
    expected = "<p>Office hours: Tuesday 3pm.</p><p>Read chapter 3.</p>"
    assert [spec.put_body(d) for d in fake.put_bodies()] == [expected]
    assert [m for m, _, _ in fake.calls] == ["get", "put", "get"]
    assert result.startswith("✅"), result
    assert f"Previous updated_at: {OLD_TS}" in result
    assert f"New updated_at: {NEW_TS}" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_find_with_zero_matches_refuses(spec, canvas_for):
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL))

    result = await spec.tool()(*spec.args, find="Friday", replace="Saturday")

    assert result.startswith("❌"), result
    assert "matched 0 times" in result
    assert fake.put_bodies() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_find_with_two_matches_refuses(spec, canvas_for):
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL))

    result = await spec.tool()(*spec.args, find="<p>", replace="<p class='x'>")

    assert result.startswith("❌"), result
    assert "matched 2 times" in result
    assert fake.put_bodies() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_missing_require_string_refuses(spec, canvas_for):
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL))

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
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL))

    result = await spec.tool()(
        *spec.args, **{spec.body_param: "<p>All</p>"}, find="Monday", replace="Tuesday",
    )

    assert result.startswith("❌"), result
    assert fake.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_find_without_replace_is_an_error(spec, canvas_for):
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL))

    result = await spec.tool()(*spec.args, find="Monday")

    assert result.startswith("❌"), result
    assert fake.calls == []


# --------------------------------------------------------------------------
# Post-write read-back
# --------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_readback_where_updated_at_did_not_advance_is_unconfirmed(spec, canvas_for):
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL, advance=False))

    result = await spec.tool()(*spec.args, find="Monday 2pm", replace="Tuesday 3pm")

    assert len(fake.put_bodies()) == 1
    assert "Could not confirm" in result
    assert "did not advance" in result
    assert "✅" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", SPECS, ids=IDS)
async def test_readback_missing_the_replacement_is_unconfirmed(spec, canvas_for):
    """Canvas bumps updated_at but keeps the old body (e.g. a dropped field)."""
    fake = canvas_for(spec, FakeCanvas(spec.body_field, ORIGINAL, store=False))

    result = await spec.tool()(*spec.args, find="Monday 2pm", replace="Tuesday 3pm")

    assert len(fake.put_bodies()) == 1
    assert "Could not confirm" in result
    assert "does not contain the text that was written" in result
    assert "✅" not in result


@pytest.mark.asyncio
async def test_assignment_guard_without_body_change_only_checks_updated_at(canvas_for):
    fake = canvas_for(ASSIGNMENT, FakeCanvas("description", ORIGINAL))

    result = await ASSIGNMENT.tool()("CS101", 77, name="Essay 1", expect_updated_at=OLD_TS)

    assert fake.put_bodies() == [{"assignment": {"name": "Essay 1"}}]
    assert result.startswith("✅"), result


@pytest.mark.asyncio
async def test_page_readback_follows_a_renamed_slug(canvas_for):
    fake = FakeCanvas("body", ORIGINAL)
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

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FakeSyllabus:
    def __init__(self, body: str, *, store: bool = True) -> None:
        self.body = body
        self.store = store
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def puts(self) -> list[str]:
        return [kw["data"]["course"]["syllabus_body"] for m, _, kw in self.calls if m == "put"]

    async def __call__(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if method == "put":
            if self.store:
                self.body = kwargs["data"]["course"]["syllabus_body"]
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
