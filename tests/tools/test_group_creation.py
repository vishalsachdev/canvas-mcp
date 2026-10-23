"""Synthetic HTTP contracts for previewed, resumable course group creation."""

import asyncio
import importlib.util
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
import pytest
from fastmcp import FastMCP

from canvas_mcp.core.credentials import (
    RequestCredentials,
    clear_request_credentials,
    set_request_credentials,
)
from canvas_mcp.core.tool_policy import apply_tool_policy, resolve_tool_policy
from canvas_mcp.server import register_all_tools

CSV = "group_name,description,canvas_user_id\nAlpha,First project,101\nAlpha,First project,102\nBeta,Second project,103\n"
CREATE = "create_course_groups"
RESUME = "resume_course_group_creation"


class Canvas:
    """Small stateful Canvas double; assertions cover the actual HTTP wire."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.categories: dict[int, dict[str, Any]] = {}
        self.groups: dict[int, dict[str, Any]] = {}
        self.members: dict[int, dict[int, str]] = {}
        self.permissions: Any = dict.fromkeys(
            ("manage_groups_add", "manage_groups_manage", "read_roster"), True
        )
        self.students = [101, 102, 103]
        self.override: Any = None
        self.page_memberships = False

    @property
    def writes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method != "GET"]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api/v1")
        if self.override:
            response = self.override(request, path)
            if response is not None:
                return response
        if path == "/courses/1/permissions":
            assert request.url.params.get_list("permissions[]") == [
                "manage_groups_add",
                "manage_groups_manage",
                "read_roster",
            ]
            return httpx.Response(200, json=self.permissions)
        if path == "/courses/1":
            return httpx.Response(200, json={"id": 1, "course_code": "CS 101"})
        if path == "/courses/1/enrollments":
            # Required students extend past page one.
            students = (
                self.students[:1]
                if request.url.params.get("page") != "2"
                else self.students[1:]
            )
            headers = (
                {}
                if request.url.params.get("page") == "2"
                else {
                    "Link": '<https://canvas.example/api/v1/courses/1/enrollments?page=2>; rel="next"'
                }
            )
            return httpx.Response(
                200,
                json=[
                    {
                        "id": i + 500,
                        "user_id": i,
                        "type": "StudentEnrollment",
                        "enrollment_state": "active",
                        "user": {
                            "id": i,
                            "name": "PRIVATE_PERSON",
                            "email": "private@example.edu",
                        },
                    }
                    for i in students
                ],
                headers=headers,
            )
        if path == "/courses/1/group_categories":
            if request.method == "GET":
                return httpx.Response(200, json=list(self.categories.values()))
            form = parse_qs(request.content.decode())
            assert form == {"name": ["Projects"], "non_collaborative": ["false"]}
            self.categories[5] = {
                "id": 5,
                "name": "Projects",
                "context_type": "Course",
                "course_id": 1,
                "self_signup": None,
                "non_collaborative": False,
            }
            return httpx.Response(200, json=self.categories[5])
        if path == "/group_categories/5":
            return httpx.Response(200, json=self.categories[5])
        if path == "/group_categories/5/groups":
            if request.method == "GET":
                return httpx.Response(200, json=list(self.groups.values()))
            form = parse_qs(request.content.decode())
            assert set(form) == {"name", "description"}
            assert request.headers["content-type"].startswith(
                "application/x-www-form-urlencoded"
            )
            gid = 10 + len(self.groups)
            self.groups[gid] = {
                "id": gid,
                "name": form["name"][0],
                "description": form["description"][0],
                "course_id": 1,
                "context_type": "Course",
                "group_category_id": 5,
                "is_public": False,
            }
            self.members[gid] = {}
            return httpx.Response(200, json=self.groups[gid])
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "groups":
            gid = int(parts[1])
            if len(parts) == 2:
                return httpx.Response(200, json=self.groups[gid])
            if parts[2] == "users":
                uid = int(parts[3])
                state = self.members[gid].get(uid)
                return httpx.Response(
                    200 if state else 404,
                    json={
                        "id": gid * 1000 + uid,
                        "group_id": gid,
                        "user_id": uid,
                        "workflow_state": state,
                    },
                )
            if parts[2] == "memberships":
                if request.method == "POST":
                    form = parse_qs(request.content.decode())
                    assert set(form) == {
                        "user_id"
                    }  # never members[]= replacement or all-in-course
                    uid = int(form["user_id"][0])
                    # Model Canvas's hazardous side effect: a bad implementation
                    # displaces an existing membership, so preservation tests fail.
                    for other in self.members.values():
                        other.pop(uid, None)
                    self.members[gid][uid] = "accepted"
                    return httpx.Response(
                        200,
                        json={
                            "id": gid * 1000 + uid,
                            "group_id": gid,
                            "user_id": uid,
                            "workflow_state": "accepted",
                        },
                    )
                values = [
                    {
                        "id": gid * 1000 + uid,
                        "group_id": gid,
                        "user_id": uid,
                        "workflow_state": state,
                    }
                    for uid, state in self.members[gid].items()
                ]
                headers = {}
                if (
                    self.page_memberships
                    and values
                    and request.url.params.get("page") != "2"
                ):
                    headers = {
                        "Link": f'<https://canvas.example/api/v1/groups/{gid}/memberships?page=2>; rel="next"'
                    }
                    values = []
                return httpx.Response(200, json=values, headers=headers)
        raise AssertionError(f"Unexpected request: {request.method} {path}")


@pytest.fixture
async def api(monkeypatch) -> AsyncIterator[SimpleNamespace]:
    from canvas_mcp.core import client as cm
    from canvas_mcp.core.config import Config

    config = Config()
    config.canvas_api_url = "https://canvas.example/api/v1"
    config.canvas_api_token = "synthetic"
    config.enable_data_anonymization = True
    config.log_api_requests = False
    monkeypatch.setattr("canvas_mcp.core.config.get_config", lambda: config)
    monkeypatch.setattr(cm, "is_http_request_active", lambda: False)
    monkeypatch.setattr(cm, "_request_semaphore", None)
    monkeypatch.setattr(cm, "_semaphore_loop_ref", None)
    if importlib.util.find_spec("canvas_mcp.tools.group_creation"):
        from canvas_mcp.tools import group_creation as gc

        gc._RUNS.clear()
        gc._GUARD.reset()
        monkeypatch.setattr(gc, "_WORK_LOCK", asyncio.Lock())
    canvas = Canvas()
    mcp = FastMCP("group-test")
    register_all_tools(mcp, role="educator")
    registered = {t.name: t for t in await mcp.list_tools()}

    async def call(name: str = CREATE, **kwargs: Any) -> dict[str, Any]:
        assert name in registered, f"Missing required educator tool: {name}"
        return await registered[name].fn(**kwargs)

    async with httpx.AsyncClient(transport=httpx.MockTransport(canvas)) as client:
        with patch.object(cm, "_get_http_client", return_value=client):
            yield SimpleNamespace(canvas=canvas, call=call, mcp=mcp)
    clear_request_credentials()


async def preview(api: SimpleNamespace, **changes: Any) -> dict[str, Any]:
    return await api.call(
        course_identifier=1, group_set_name="Projects", csv_data=CSV, **changes
    )


async def confirm(api: SimpleNamespace) -> dict[str, Any]:
    p = await preview(api)
    assert p["status"] == "preview" and not api.canvas.writes
    return await preview(api, confirmation_token=p["confirmation_token"])


async def partial(api: SimpleNamespace) -> dict[str, Any]:
    def fail(request: httpx.Request, path: str) -> httpx.Response | None:
        if (
            path == "/groups/10/memberships"
            and request.method == "POST"
            and b"102" in request.content
        ):
            return httpx.Response(403, json={"message": "PRIVATE_ERROR_PERSON"})
        return None

    api.canvas.override = fail
    result = await confirm(api)
    assert result["status"] == "partial_failure"
    api.canvas.override = None
    return result


async def test_preview_then_confirm_all_three_operations_with_form_encoding(
    api,
) -> None:
    p = await preview(api)
    assert p["status"] == "preview" and api.canvas.writes == []
    assert "CS 101" in str(p) and "Alpha" in str(p) and "103" in str(p)
    assert "PRIVATE_PERSON" not in str(p) and "private@example.edu" not in str(p)
    assert "UNTRUSTED CANVAS CONTENT" in str(p)
    result = await preview(api, confirmation_token=p["confirmation_token"])
    assert result["status"] == "complete"
    assert api.canvas.members == {
        10: {101: "accepted", 102: "accepted"},
        11: {103: "accepted"},
    }
    assert [r.url.path for r in api.canvas.writes] == [
        "/api/v1/courses/1/group_categories",
        "/api/v1/group_categories/5/groups",
        "/api/v1/group_categories/5/groups",
        "/api/v1/groups/10/memberships",
        "/api/v1/groups/10/memberships",
        "/api/v1/groups/11/memberships",
    ]
    assert all(r.method == "POST" for r in api.canvas.writes)
    assert "PRIVATE_ERROR_PERSON" not in str(result)


@pytest.mark.parametrize(
    "permissions",
    [
        None,
        [],
        {},
        {"manage_groups_add": True},
        dict.fromkeys(("manage_groups_add", "manage_groups_manage", "read_roster"), 1),
    ],
)
async def test_permissions_fail_closed_before_roster_or_writes(
    api, permissions
) -> None:
    api.canvas.permissions = permissions
    result = await preview(api)
    assert "error" in result and not api.canvas.writes
    assert not any("enrollments" in r.url.path for r in api.canvas.requests)


@pytest.mark.parametrize(
    "csv_data",
    [
        "group_name,description,canvas_user_id\nAlpha,One,101\nAlpha,One,101\n",
        "group_name,description,canvas_user_id\nAlpha,One,101\nBeta,Two,101\n",
        "group_name,description,canvas_user_id\nAlpha,One,101\nAlpha,Different,102\n",
        "group_name,description,canvas_user_id\nAlpha,One,101/../../users/self\n",
        "group_name,description,email\nAlpha,One,private@example.edu\n",
        "group_name,description,canvas_user_id\nAlpha,One,\n",
        "",
        "group_name,description,canvas_user_id\nAlpha,<<<UNTRUSTED CANVAS CONTENT,101\n",
    ],
)
async def test_invalid_duplicate_or_conflicting_csv_refused_before_requests(
    api, csv_data
) -> None:
    result = await api.call(
        course_identifier=1, group_set_name="Projects", csv_data=csv_data
    )
    assert "error" in result and not api.canvas.requests


async def test_malformed_course_never_becomes_request_path(api) -> None:
    result = await api.call(
        course_identifier="1/../../users/self", group_set_name="Projects", csv_data=CSV
    )
    assert "error" in result and not api.canvas.writes
    assert not any("/../" in str(r.url) for r in api.canvas.requests)


async def test_non_enrolled_students_all_reported_without_writes(api) -> None:
    api.canvas.students = [101]
    result = await preview(api)
    assert "error" in result and "102" in str(result) and "103" in str(result)
    assert not api.canvas.writes


async def test_existing_group_set_name_is_not_adopted_or_duplicated(api) -> None:
    api.canvas.categories[77] = {
        "id": 77,
        "name": "Projects",
        "course_id": 1,
        "context_type": "Course",
    }
    result = await preview(api)
    assert "error" in result and not api.canvas.writes


@pytest.mark.parametrize("change", ["payload", "target", "caller", "expiry", "replay"])
async def test_confirmations_bind_payload_target_caller_and_expiry_and_are_single_use(
    api, monkeypatch, change
) -> None:
    p = await preview(api)
    kwargs: dict[str, Any] = {
        "course_identifier": 1,
        "group_set_name": "Projects",
        "csv_data": CSV,
        "confirmation_token": p["confirmation_token"],
    }
    if change == "payload":
        kwargs["csv_data"] = CSV.replace("First project", "Changed project")
    elif change == "target":
        kwargs["group_set_name"] = "Other projects"
    elif change == "caller":
        set_request_credentials(
            RequestCredentials(
                "different-synthetic-token", "https://canvas.example/api/v1"
            )
        )
    elif change == "expiry":
        from canvas_mcp.tools import group_creation as gc

        now = gc._GUARD._now()
        monkeypatch.setattr(gc._GUARD, "_now", lambda: now + 301)
    elif change == "replay":
        await api.call(**kwargs)
    before = len(api.canvas.writes)
    result = await api.call(**kwargs)
    assert "error" in result and len(api.canvas.writes) == before


async def test_partial_report_and_resume_use_fresh_preview_and_no_duplicate_groups(
    api,
) -> None:
    result = await partial(api)
    assert result["group_set_id"] == "5"
    assert [g["group_id"] for g in result["groups"]] == ["10", "11"]
    assert (
        "confirmed" in str(result)
        and "failed" in str(result)
        and "pending" in str(result)
    )
    assert "PRIVATE_ERROR_PERSON" not in str(result)
    before = len(api.canvas.writes)
    p = await api.call(RESUME, run_id=result["run_id"])
    assert p["status"] == "preview" and len(api.canvas.writes) == before
    complete = await api.call(
        RESUME, run_id=result["run_id"], confirmation_token=p["confirmation_token"]
    )
    assert complete["status"] == "complete"
    assert len(api.canvas.categories) == 1 and len(api.canvas.groups) == 2
    assert all("/memberships" in r.url.path for r in api.canvas.writes[before:])
    assert (
        sum(
            b"101" in r.content
            for r in api.canvas.writes
            if "/memberships" in r.url.path
        )
        == 1
    )


async def test_all_membership_conflicts_including_other_groups_and_pages_shown_before_any_resume_write(
    api,
) -> None:
    result = await partial(api)
    api.canvas.groups[99] = {
        "id": 99,
        "name": "Existing external group",
        "description": "Existing",
        "context_type": "Course",
        "course_id": 1,
        "group_category_id": 5,
        "is_public": False,
    }
    api.canvas.members[99] = {102: "accepted", 103: "invited"}
    api.canvas.page_memberships = True
    before = len(api.canvas.writes)
    blocked = await api.call(RESUME, run_id=result["run_id"])
    assert "error" in blocked and len(blocked["conflicts"]) == 2
    assert {c["user_id"] for c in blocked["conflicts"]} == {"102", "103"}
    assert "confirmation_token" not in blocked and len(api.canvas.writes) == before
    assert api.canvas.members[99] == {102: "accepted", 103: "invited"}


async def test_changed_membership_after_resume_preview_refuses_confirmation(
    api,
) -> None:
    result = await partial(api)
    p = await api.call(RESUME, run_id=result["run_id"])
    api.canvas.members[11][102] = "accepted"
    before = len(api.canvas.writes)
    result = await api.call(
        RESUME, run_id=result["run_id"], confirmation_token=p["confirmation_token"]
    )
    assert "error" in result and result["conflicts"]
    assert len(api.canvas.writes) == before and 102 in api.canvas.members[11]


@pytest.mark.parametrize("change", ["course", "category", "name", "description"])
async def test_resume_refuses_recorded_group_identity_or_content_drift(
    api, change
) -> None:
    result = await partial(api)
    field, value = {
        "course": ("course_id", 2),
        "category": ("group_category_id", 7),
        "name": ("name", "Changed"),
        "description": ("description", "Changed"),
    }[change]
    api.canvas.groups[10][field] = value
    before = len(api.canvas.writes)
    blocked = await api.call(RESUME, run_id=result["run_id"])
    assert "error" in blocked and len(api.canvas.writes) == before


async def test_unknown_or_other_callers_run_id_cannot_authorize_existing_ids(
    api,
) -> None:
    assert "error" in await api.call(RESUME, run_id="5")
    result = await partial(api)
    before = len(api.canvas.writes)
    set_request_credentials(
        RequestCredentials("foreign-token", "https://canvas.example/api/v1")
    )
    assert "error" in await api.call(RESUME, run_id=result["run_id"])
    assert len(api.canvas.writes) == before


@pytest.mark.parametrize(
    "path",
    [
        "/courses/1/group_categories",
        "/group_categories/5/groups",
        "/groups/10/memberships",
    ],
)
async def test_uncertain_transport_failure_is_reported_and_never_blindly_recreated(
    api, path
) -> None:
    def fail(request: httpx.Request, current: str) -> httpx.Response | None:
        if request.method == "POST" and current == path:
            raise httpx.ReadTimeout("PRIVATE_TRANSPORT_SECRET", request=request)
        return None

    api.canvas.override = fail
    result = await confirm(api)
    assert result["status"] in {"partial_failure", "needs_inspection"}
    assert "uncertain" in str(result) and "PRIVATE_TRANSPORT_SECRET" not in str(result)
    assert sum(r.url.path.endswith(path) for r in api.canvas.writes) == 1
    api.canvas.override = None
    before = len(api.canvas.writes)
    p = await api.call(RESUME, run_id=result["run_id"])
    if path != "/groups/10/memberships":
        assert "error" in p and "confirmation_token" not in p
    else:
        assert p["status"] == "preview"
    assert len(api.canvas.writes) == before


async def test_group_readback_mismatch_is_not_success_or_silently_adopted(api) -> None:
    def corrupt(request: httpx.Request, path: str) -> httpx.Response | None:
        if path == "/groups/10" and request.method == "GET":
            return httpx.Response(200, json={**api.canvas.groups[10], "course_id": 99})
        return None

    api.canvas.override = corrupt
    result = await confirm(api)
    assert result["status"] == "partial_failure"
    assert result["last_operation"]["status"] == "uncertain"
    assert "error" in result
    assert not any("memberships" in r.url.path for r in api.canvas.writes)


async def test_definitely_rejected_group_creation_can_resume_only_in_recorded_set(
    api,
) -> None:
    def reject(request: httpx.Request, path: str) -> httpx.Response | None:
        if (
            request.method == "POST"
            and path == "/group_categories/5/groups"
            and b"Beta" in request.content
        ):
            return httpx.Response(422, json={"error": "PRIVATE_ERROR_PERSON"})
        return None

    api.canvas.override = reject
    result = await confirm(api)
    assert result["status"] == "partial_failure" and len(api.canvas.groups) == 1
    assert result["last_operation"]["status"] == "failed"
    assert not any("memberships" in r.url.path for r in api.canvas.writes)
    api.canvas.override = None
    p = await api.call(RESUME, run_id=result["run_id"])
    done = await api.call(
        RESUME, run_id=result["run_id"], confirmation_token=p["confirmation_token"]
    )
    assert done["status"] == "complete" and len(api.canvas.groups) == 2
    assert len(api.canvas.categories) == 1


async def test_uncertain_membership_already_committed_is_reconciled_without_reposting(
    api,
) -> None:
    def lost_response(request: httpx.Request, path: str) -> httpx.Response | None:
        if request.method == "POST" and path == "/groups/10/memberships":
            api.canvas.members[10][101] = "accepted"
            raise httpx.ReadTimeout("synthetic", request=request)
        return None

    api.canvas.override = lost_response
    result = await confirm(api)
    assert result["last_operation"]["status"] == "uncertain"
    api.canvas.override = None
    p = await api.call(RESUME, run_id=result["run_id"])
    done = await api.call(
        RESUME, run_id=result["run_id"], confirmation_token=p["confirmation_token"]
    )
    assert done["status"] == "complete"
    assert (
        sum(
            r.method == "POST"
            and r.url.path.endswith("/memberships")
            and r.content == b"user_id=101"
            for r in api.canvas.requests
        )
        == 1
    )


async def test_resume_token_cannot_be_replayed_or_replaced_by_initial_token(
    api,
) -> None:
    result = await partial(api)
    p = await api.call(RESUME, run_id=result["run_id"])
    await api.call(
        RESUME, run_id=result["run_id"], confirmation_token=p["confirmation_token"]
    )
    before = len(api.canvas.writes)
    assert "error" in await api.call(
        RESUME, run_id=result["run_id"], confirmation_token=p["confirmation_token"]
    )
    assert len(api.canvas.writes) == before


async def test_concurrent_confirmation_cannot_create_duplicate_set(api) -> None:
    p = await preview(api)
    results = await asyncio.gather(
        preview(api, confirmation_token=p["confirmation_token"]),
        preview(api, confirmation_token=p["confirmation_token"]),
    )
    assert sum(r.get("status") == "complete" for r in results) == 1
    assert len(api.canvas.categories) == 1 and len(api.canvas.groups) == 2


async def test_removed_confirmed_membership_is_never_silently_restored(api) -> None:
    result = await partial(api)
    api.canvas.members[10].pop(101)
    before = len(api.canvas.writes)
    assert "error" in await api.call(RESUME, run_id=result["run_id"])
    assert len(api.canvas.writes) == before and 101 not in api.canvas.members[10]


async def test_conflicts_on_a_previously_confirmed_student_are_all_shown(api) -> None:
    result = await partial(api)
    api.canvas.members[10].pop(101)
    api.canvas.members[11].update({101: "accepted", 102: "accepted"})
    before = len(api.canvas.writes)
    blocked = await api.call(RESUME, run_id=result["run_id"])
    assert {c["user_id"] for c in blocked["conflicts"]} == {"101", "102"}
    assert len(api.canvas.writes) == before


@pytest.mark.parametrize("endpoint", ["/group_categories/5", "/groups/10/memberships"])
async def test_malformed_revalidation_refuses_all_resume_writes(api, endpoint) -> None:
    result = await partial(api)

    def malformed(request: httpx.Request, path: str) -> httpx.Response | None:
        return (
            httpx.Response(200, json={"unexpected": "PRIVATE_SECRET"})
            if path == endpoint
            else None
        )

    api.canvas.override = malformed
    before = len(api.canvas.writes)
    response = await api.call(RESUME, run_id=result["run_id"])
    assert "error" in response and "PRIVATE_SECRET" not in str(response)
    assert len(api.canvas.writes) == before


async def test_membership_endpoint_uses_full_anonymization_tier() -> None:
    from canvas_mcp.core.client import _anonymize_for_endpoint

    data, _ = _anonymize_for_endpoint(
        {
            "id": 120,
            "group_id": 10,
            "user_id": 101,
            "user": {
                "id": 101,
                "name": "Private Student",
                "email": "private@example.edu",
            },
        },
        "/groups/10/memberships",
    )
    assert data["user_id"] == 101 and data["group_id"] == 10
    assert "Private Student" not in str(data) and "private@example.edu" not in str(data)


async def test_group_creation_response_cannot_adopt_a_preexisting_foreign_group_id(
    api,
) -> None:
    def reject_beta(request: httpx.Request, path: str) -> httpx.Response | None:
        if (
            request.method == "POST"
            and path == "/group_categories/5/groups"
            and b"Beta" in request.content
        ):
            return httpx.Response(422, json={"error": "synthetic rejection"})
        return None

    api.canvas.override = reject_beta
    result = await confirm(api)
    api.canvas.groups[11] = {
        **api.canvas.groups[10],
        "id": 11,
        "name": "Unrelated existing group",
    }
    api.canvas.members[11] = {}
    before = len(api.canvas.writes)

    def reused_id(request: httpx.Request, path: str) -> httpx.Response | None:
        if request.method == "POST" and path == "/group_categories/5/groups":
            api.canvas.groups[11]["name"] = "Beta"
            api.canvas.groups[11]["description"] = "Second project"
            return httpx.Response(200, json=api.canvas.groups[11])
        return None

    api.canvas.override = reused_id
    p = await api.call(RESUME, run_id=result["run_id"])
    blocked = await api.call(
        RESUME, run_id=result["run_id"], confirmation_token=p["confirmation_token"]
    )
    assert blocked["status"] == "needs_inspection"
    assert blocked["groups"][1]["group_id"] is None
    assert len(api.canvas.writes) == before + 1


async def test_hosted_policy_removes_both_tools_and_student_profile_never_registers_them(
    api,
) -> None:
    names = {t.name for t in await api.mcp.list_tools()}
    assert {CREATE, RESUME} <= names
    removed = await apply_tool_policy(api.mcp, resolve_tool_policy(None, "http"))
    assert {CREATE, RESUME} <= set(removed)
    allowed = FastMCP("allowed")
    register_all_tools(allowed, role="educator")
    await apply_tool_policy(allowed, resolve_tool_policy(f"{CREATE},{RESUME}", "http"))
    assert {CREATE, RESUME} <= {t.name for t in await allowed.list_tools()}
    student = FastMCP("student")
    register_all_tools(student, role="student")
    assert not {CREATE, RESUME} & {t.name for t in await student.list_tools()}


async def test_tools_declare_complete_preview_output_size(api) -> None:
    for tool in await api.mcp.list_tools():
        if tool.name in {CREATE, RESUME}:
            assert tool.meta["anthropic/maxResultSizeChars"] == 500000


async def test_membership_acknowledgment_without_readback_is_uncertain(api) -> None:
    def no_op(request: httpx.Request, path: str) -> httpx.Response | None:
        if request.method == "POST" and path == "/groups/10/memberships":
            return httpx.Response(
                200,
                json={
                    "id": 10101,
                    "group_id": 10,
                    "user_id": 101,
                    "workflow_state": "accepted",
                },
            )
        return None

    api.canvas.override = no_op
    result = await confirm(api)
    assert result["status"] == "partial_failure" and "error" in result
    assert result["last_operation"]["status"] == "uncertain"
    assert result["groups"][0]["members"][0]["status"] == "uncertain"
    assert sum("memberships" in r.url.path for r in api.canvas.writes) == 1
