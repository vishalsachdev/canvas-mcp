"""The Inbox recipient search must not be a real-name -> pseudonym oracle.

While ``ENABLE_DATA_ANONYMIZATION`` is on, people who are not course staff are
shown only as ``Student_<hash>`` (with their real numeric user ID). Canvas's
``GET /search/recipients`` matches ``search`` against REAL names server-side,
so anything that survives a name search reveals that the name matched.
Returning a classmate's pseudonym or user ID for a real-name search would map
that real name onto the pseudonym the rest of the server shows for them, which
is exactly what anonymization exists to prevent, and a prompt-injected model
could do it for a whole class one name at a time.

These tests drive the real tool through the real Canvas client over a mocked
transport whose address book filters by the search term the way Canvas does
(a case-insensitive match on the person's name).
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastmcp import FastMCP

from canvas_mcp.core import client as client_module
from canvas_mcp.core.anonymization import generate_anonymous_id
from canvas_mcp.core.config import reset_config
from canvas_mcp.core.course_policy import reset_policy_cache
from canvas_mcp.tools import student_messaging
from canvas_mcp.tools.student_messaging import (
    register_student_messaging_tools,
    reset_pending_confirmations,
)

COURSE = "123"
API = "/api/v1"

PROF = {"id": 501, "name": "Ada", "full_name": "Ada Lovelace",
        "common_courses": {COURSE: ["TeacherEnrollment"]}}
TA = {"id": 502, "name": "Grace", "full_name": "Grace Hopper",
      "common_courses": {COURSE: ["TaEnrollment"]}}
DESIGNER = {"id": 507, "name": "Margaret", "full_name": "Margaret Hamilton",
            "common_courses": {COURSE: ["DesignerEnrollment"]}}
CLASSMATE = {"id": 503, "name": "Alan", "full_name": "Alan Turing",
             "common_courses": {COURSE: ["StudentEnrollment"]}}
# Shares a first name with the professor.
NAMESAKE = {"id": 504, "name": "Ada", "full_name": "Ada Turing",
            "common_courses": {COURSE: ["StudentEnrollment"]}}
OBSERVER = {"id": 506, "name": "Pat", "full_name": "Pat Observer",
            "common_courses": {COURSE: ["ObserverEnrollment"]}}
# Staff in another course, a student in this one.
STAFF_ELSEWHERE = {"id": 505, "name": "Barbara", "full_name": "Barbara Liskov",
                   "common_courses": {COURSE: ["StudentEnrollment"], "777": ["TeacherEnrollment"]}}

ADDRESS_BOOK = [PROF, TA, DESIGNER, CLASSMATE, NAMESAKE, OBSERVER, STAFF_ELSEWHERE]
NON_STAFF = [CLASSMATE, NAMESAKE, OBSERVER, STAFF_ELSEWHERE]


# Canvas address-book sub-contexts (``course_<id>_<type>``) and the enrollment
# type each one lists.
SUBCONTEXT_TYPES = {
    "teachers": "TeacherEnrollment",
    "tas": "TaEnrollment",
    "designers": "DesignerEnrollment",
    "students": "StudentEnrollment",
    "observers": "ObserverEnrollment",
}
STAFF_CONTEXTS = [f"course_{COURSE}_{t}" for t in ("teachers", "tas", "designers")]


class AddressBook:
    """Canvas's course address book, with server-side real-name search.

    ``context=course_<id>_<type>`` lists only people with that enrollment type
    in the course, as Canvas's address book does, unless
    ``honor_subcontexts`` is off (a Canvas that ignores the suffix). Results
    are paginated by ``per_page`` with a ``Link: rel="next"`` header.
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.people: list[dict] = list(ADDRESS_BOOK)
        self.honor_subcontexts = True

    def _in_context(self, person: dict, context: str) -> bool:
        if not self.honor_subcontexts:
            return True
        match = re.fullmatch(rf"course_{COURSE}_([a-z]+)", context)
        if match is None:
            return True
        roles = person["common_courses"].get(COURSE, [])
        return SUBCONTEXT_TYPES.get(match.group(1)) in roles

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix(API)
        params = request.url.params
        if request.method != "GET":
            return httpx.Response(500, json={"errors": [{"message": "no writes here"}]})
        if path == f"/courses/{COURSE}":
            return httpx.Response(200, json={"id": int(COURSE), "syllabus_body": ""})
        if path == "/search/recipients":
            if "user_id" in params:
                user = next(
                    (u for u in self.people if str(u["id"]) == params["user_id"]), None
                )
                return httpx.Response(200, json=[user] if user else [])
            term = params.get("search", "").lower()
            context = params.get("context", "")
            hits = [
                u for u in self.people
                if (term in u["full_name"].lower() or term in u["name"].lower())
                and self._in_context(u, context)
            ]
            per_page = int(params.get("per_page", "10"))
            page = int(params.get("page", "1"))
            headers = {}
            if page * per_page < len(hits):
                nxt = request.url.copy_merge_params({"page": str(page + 1)})
                headers["Link"] = f'<{nxt}>; rel="next"'
            return httpx.Response(
                200, json=hits[(page - 1) * per_page:page * per_page], headers=headers
            )
        return httpx.Response(404, json={"errors": [{"message": f"unrouted {path}"}]})

    def lookups(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == f"{API}/search/recipients"]


@pytest.fixture
def address_book(monkeypatch):
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example/api/v1")
    monkeypatch.setenv("CANVAS_API_TOKEN", "synthetic")
    monkeypatch.setenv("ENABLE_DATA_ANONYMIZATION", "true")
    monkeypatch.setenv("STUDENT_WRITE_TOOLS", "send_message")
    monkeypatch.setenv("COURSE_AGENT_POLICY_ENABLED", "false")
    reset_config()
    reset_policy_cache()
    reset_pending_confirmations()
    fake = AddressBook()
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    with patch.object(client_module, "_get_http_client", return_value=client), patch.object(
        student_messaging, "get_course_code", AsyncMock(return_value="CS101")
    ):
        yield fake
    reset_policy_cache()
    reset_pending_confirmations()


async def _tools() -> dict:
    mcp = FastMCP("recipient-privacy")
    register_student_messaging_tools(mcp)
    return {tool.name: tool.fn for tool in await mcp.list_tools(run_middleware=False)}


async def _find(**kwargs) -> dict:
    tools = await _tools()
    return await tools["find_message_recipients"](COURSE, **kwargs)


def _assert_no_trace_of_non_staff(result: dict) -> None:
    dumped = json.dumps(result)
    returned = {r["user_id"] for r in result.get("recipients", [])}
    for person in NON_STAFF:
        user_id = str(person["id"])
        assert user_id not in returned
        assert generate_anonymous_id(user_id) not in dumped
        assert person["full_name"] not in dumped


@pytest.mark.asyncio
@pytest.mark.parametrize("term", ["Alan Turing", "turing", "ALAN", "Pat Observer", "liskov"])
@pytest.mark.parametrize("role", ["any", "student"])
async def test_real_name_search_returns_no_student_and_no_pseudonym(address_book, term, role):
    result = await _find(search=term, role=role)

    # Canvas really was asked, but only for staff: the search went to the
    # staff sub-contexts, never to the whole-course address book.
    lookups = address_book.lookups()
    assert lookups and all(r.url.params["search"] == term for r in lookups)
    assert all(r.url.params["context"] in STAFF_CONTEXTS for r in lookups)
    assert result["success"] is True
    assert result["recipients"] == []
    assert result["count"] == 0 and result["total_matches"] == 0
    _assert_no_trace_of_non_staff(result)
    assert "staff" in result["anonymization_note"]


@pytest.mark.asyncio
async def test_search_matching_staff_and_students_returns_only_staff(address_book):
    """"ada" matches the professor and a classmate; only the professor comes back."""
    result = await _find(search="ada")
    assert [r["user_id"] for r in result["recipients"]] == ["501"]
    assert "Ada Lovelace" in result["recipients"][0]["name"]
    assert result["recipients"][0]["roles"] == ["teacher"]
    _assert_no_trace_of_non_staff(result)
    assert "staff" in result["anonymization_note"]


@pytest.mark.asyncio
async def test_broad_search_cannot_enumerate_classmates(address_book):
    """A one-letter search matches nearly everyone; still staff only."""
    result = await _find(search="a")
    assert {r["user_id"] for r in result["recipients"]} == {"501", "502", "507"}
    _assert_no_trace_of_non_staff(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("term,role,expected", [
    ("lovelace", "staff", PROF),
    ("Grace", "any", TA),
    ("hopper", "ta", TA),
    ("hamilton", "staff", DESIGNER),
])
async def test_staff_search_still_works(address_book, term, role, expected):
    result = await _find(search=term, role=role)
    [match] = result["recipients"]
    assert match["user_id"] == str(expected["id"])
    assert match["name"].startswith("<<<UNTRUSTED CANVAS CONTENT")
    assert expected["full_name"] in match["name"]


@pytest.mark.asyncio
async def test_listing_without_search_keeps_pseudonyms(address_book):
    """No search term means no name was matched, so pseudonyms are safe to list."""
    result = await _find()
    names = {r["user_id"]: r["name"] for r in result["recipients"]}
    assert set(names) == {str(u["id"]) for u in ADDRESS_BOOK}
    for person in NON_STAFF:
        assert names[str(person["id"])] == generate_anonymous_id(str(person["id"]))
        assert person["full_name"] not in json.dumps(result)
    assert "search" not in address_book.lookups()[0].url.params


@pytest.mark.asyncio
async def test_search_is_unchanged_when_anonymization_is_off(address_book, monkeypatch):
    monkeypatch.setenv("ENABLE_DATA_ANONYMIZATION", "false")
    reset_config()
    result = await _find(search="turing")
    assert [r["user_id"] for r in result["recipients"]] == ["503", "504"]
    assert "Alan Turing" in result["recipients"][0]["name"]
    assert "Ada Turing" in result["recipients"][1]["name"]
    assert "anonymization_note" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("recipient", ["Alan Turing", "turing", "@turing", "user_503"])
async def test_send_preview_cannot_resolve_a_recipient_by_name(address_book, recipient):
    """send_message takes numeric user IDs only, so a name never reaches Canvas."""
    tools = await _tools()
    result = await tools["send_message"](COURSE, [recipient], "Hi", "Body")
    assert result["nothing_sent"] is True
    assert "not a Canvas user ID" in result["error"]
    assert "preview" not in result
    assert address_book.requests == []


@pytest.mark.asyncio
async def test_send_preview_looks_recipients_up_by_id_never_by_search(address_book):
    """The preview's own lookup is by user_id; it shows the pseudonym the
    caller already had for that ID and adds no name -> ID link."""
    tools = await _tools()
    preview = await tools["send_message"](COURSE, ["501", "503"], "Hi", "Body")
    assert preview["preview"] is True
    lookups = address_book.lookups()
    assert [r.url.params["user_id"] for r in lookups] == ["501", "503"]
    assert all("search" not in r.url.params for r in lookups)
    names = {r["user_id"]: r["name"] for r in preview["recipients"]}
    assert names["503"] == generate_anonymous_id("503")
    assert "Alan Turing" not in json.dumps(preview)


# ---------------------------------------------------------------------------
# A staff-only search asks Canvas for staff, not for everyone
# ---------------------------------------------------------------------------


def _many_students(count: int, surname: str = "Smith") -> list[dict]:
    return [
        {"id": 10_000 + i, "name": f"Kid{i}", "full_name": f"Kid{i} {surname}",
         "common_courses": {COURSE: ["StudentEnrollment"]}}
        for i in range(count)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("role,contexts", [
    ("any", STAFF_CONTEXTS),
    ("staff", STAFF_CONTEXTS),
    ("student", STAFF_CONTEXTS),
    ("teacher", [f"course_{COURSE}_teachers"]),
    ("ta", [f"course_{COURSE}_tas"]),
])
async def test_staff_only_search_queries_staff_subcontexts(address_book, role, contexts):
    await _find(search="smith", role=role)
    lookups = address_book.lookups()
    assert [r.url.params["context"] for r in lookups] == contexts
    assert all(r.url.params["search"] == "smith" for r in lookups)


@pytest.mark.asyncio
async def test_many_matching_students_cost_no_extra_pages_and_no_truncation(address_book):
    """Hundreds of students named Smith are not read and then thrown away,
    and their number does not surface as a misleading truncation note."""
    smith = {"id": 520, "name": "Prof", "full_name": "Prof Smith",
             "common_courses": {COURSE: ["TeacherEnrollment"]}}
    address_book.people = [smith, *_many_students(600)]

    result = await _find(search="smith")

    assert [r["user_id"] for r in result["recipients"]] == ["520"]
    # One page per staff sub-context, nothing more.
    assert len(address_book.lookups()) == len(STAFF_CONTEXTS)
    assert result["truncated"] is False
    assert result["total_is_lower_bound"] is False
    assert "note" not in result


@pytest.mark.asyncio
async def test_students_dropped_even_if_canvas_ignores_the_subcontext(address_book):
    """If Canvas returned students for a staff sub-context, they are still dropped."""
    address_book.honor_subcontexts = False
    for term in ("turing", "liskov", "a"):
        result = await _find(search=term)
        _assert_no_trace_of_non_staff(result)
    result = await _find(search="ada")
    assert [r["user_id"] for r in result["recipients"]] == ["501"]


@pytest.mark.asyncio
async def test_staff_search_still_pages_and_truncates(address_book):
    """Paging across staff sub-contexts still stops at the page cap and says so."""
    many_tas = [
        {"id": 20_000 + i, "name": f"TA{i}", "full_name": f"TA{i} Jones",
         "common_courses": {COURSE: ["TaEnrollment"]}}
        for i in range(1_000)
    ]
    address_book.people = many_tas
    result = await _find(search="jones", role="staff", limit=50)
    assert len(address_book.lookups()) <= student_messaging._MAX_RECIPIENT_PAGES
    assert result["count"] == 50
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_search_without_anonymization_uses_the_course_address_book(
    address_book, monkeypatch
):
    monkeypatch.setenv("ENABLE_DATA_ANONYMIZATION", "false")
    reset_config()
    await _find(search="turing")
    assert [r.url.params["context"] for r in address_book.lookups()] == [f"course_{COURSE}"]


@pytest.mark.asyncio
async def test_page_cap_is_shared_across_staff_subcontexts(address_book):
    """A Canvas that ignored the sub-context would hand back every student on
    every staff context; the page cap still bounds the whole call."""
    address_book.honor_subcontexts = False
    address_book.people = _many_students(600)
    result = await _find(search="smith")
    assert len(address_book.lookups()) == student_messaging._MAX_RECIPIENT_PAGES
    assert result["recipients"] == []
    assert result["truncated"] is True
