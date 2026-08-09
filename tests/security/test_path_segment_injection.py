"""Path-segment injection invariants for Canvas request routing.

Canvas endpoints are built by interpolating caller-supplied identifiers into a
path template, and several student tools rely on a hard-coded ``/submissions/self``
suffix for their *authorization*: the route is self-scoped because the path says
``self``. A '?' or '#' inside an identifier ends the path early and demotes that
suffix to the query string, so ``assignment_id="123/submissions/456?"`` turns a
self-scoped read into a read of submission 456. Canvas then answers it for any
token that also carries grading permission.

Two layers are pinned here:

1. ``make_canvas_request`` refuses any endpoint containing a path delimiter.
   Every caller passes query parameters via ``params=``, so a delimiter in the
   path is always smuggling. This covers all ~23 interpolation sites at once.
2. The self-scoped student tools additionally require a numeric assignment_id,
   so the bad value never reaches the client layer.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from canvas_mcp.core.validation import coerce_canvas_id


class TestUrlConstructionPremise:
    """The premise the whole finding rests on, asserted rather than assumed."""

    @pytest.mark.parametrize(
        "assignment_id",
        ["123/submissions/456?", "123/submissions/456#", "123%2Fsubmissions%2F456?"],
    )
    def test_delimiter_moves_the_self_suffix_off_the_path(self, assignment_id):
        """Without the guard, '/submissions/self' would not be in the request path."""
        endpoint = f"/courses/60366/assignments/{assignment_id}/submissions/self"
        url = httpx.Request("GET", f"https://canvas.example.com/api/v1{endpoint}").url

        assert not url.path.endswith("/submissions/self")
        assert url.path.endswith("/submissions/456")

    def test_a_plain_numeric_id_keeps_the_self_suffix(self):
        endpoint = "/courses/60366/assignments/999/submissions/self"
        url = httpx.Request("GET", f"https://canvas.example.com/api/v1{endpoint}").url

        assert url.path.endswith("/assignments/999/submissions/self")


class TestClientRefusesDelimiters:
    """Layer 1: the central chokepoint, covering every interpolation site."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("delimiter", ["?", "#"])
    async def test_endpoint_with_delimiter_is_refused(self, delimiter):
        from canvas_mcp.core.client import make_canvas_request

        with patch("canvas_mcp.core.client.httpx.AsyncClient") as client:
            result = await make_canvas_request(
                "get",
                f"/courses/1/assignments/123{delimiter}x/submissions/self",
            )

        assert isinstance(result, dict)
        assert "error" in result
        assert delimiter in result["error"]
        # Refused before any network client was constructed.
        assert client.call_count == 0

    @pytest.mark.asyncio
    async def test_endpoint_with_traversal_segment_is_refused(self):
        from canvas_mcp.core.client import make_canvas_request

        with patch("canvas_mcp.core.client.httpx.AsyncClient") as client:
            result = await make_canvas_request(
                "get", "/courses/1/assignments/../../users/2"
            )

        assert isinstance(result, dict)
        assert ".." in result["error"]
        assert client.call_count == 0

    @pytest.mark.asyncio
    async def test_ordinary_endpoint_is_not_refused(self):
        """The guard must not reject legitimate paths.

        Proven by letting the endpoint reach the network layer: a sentinel raised
        from the HTTP client can only escape if the guard already let the request
        through, whereas a refused endpoint returns an error dict before that point.
        """
        from canvas_mcp.core.client import make_canvas_request

        with patch("canvas_mcp.core.client.httpx.AsyncClient") as client:
            client.side_effect = RuntimeError("reached the network layer")
            with pytest.raises(RuntimeError, match="reached the network layer"):
                await make_canvas_request(
                    "get", "/courses/1/assignments/123/submissions/self"
                )


class TestCoerceCanvasId:
    """Layer 2: the identifier grammar."""

    @pytest.mark.parametrize("good", [123, "123", " 123 ", "0"])
    def test_numeric_ids_accepted(self, good):
        assert coerce_canvas_id(good) == str(good).strip()

    @pytest.mark.parametrize(
        "bad",
        [
            "123/submissions/456?",
            "123/submissions/456#",
            "123%2Fsubmissions%2F456",
            "../../users/2",
            "123 456",
            "",
            "abc",
            "12.3",
            "-1",
            "sis_assignment_id:x",
            "١٢٣",  # non-ASCII digits: str.isdigit() would accept these
        ],
    )
    def test_non_numeric_ids_rejected(self, bad):
        assert coerce_canvas_id(bad) is None


class TestSelfScopedToolsRejectSmuggledIds:
    """Layer 2 in place: the tools refuse before any Canvas call is made."""

    def _tools(self, **env):
        from fastmcp import FastMCP

        from canvas_mcp.core.config import reset_config
        from canvas_mcp.tools.student_write import register_student_write_tools

        reset_config()
        captured: dict = {}
        mcp = FastMCP("test")
        original = mcp.tool

        def capturing(*a, **k):
            decorator = original(*a, **k)

            def wrapper(fn):
                captured[fn.__name__] = fn
                return decorator(fn)

            return wrapper

        mcp.tool = capturing
        with patch.dict("os.environ", env, clear=False):
            reset_config()
            register_student_write_tools(mcp)
        reset_config()
        return captured

    @pytest.mark.asyncio
    async def test_get_my_submission_rejects_smuggled_id(self):
        tools = self._tools()
        with patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request, patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="60366"),
        ):
            result = await tools["get_my_submission"](
                course_identifier="badm_350", assignment_id="123/submissions/456?"
            )

        assert "numeric Canvas assignment ID" in result
        assert request.call_count == 0

    @pytest.mark.asyncio
    async def test_comment_on_my_submission_rejects_smuggled_id(self):
        tools = self._tools(
            STUDENT_WRITE_TOOLS="comment_on_my_submission",
            COURSE_AGENT_POLICY_ENABLED="false",
        )
        if "comment_on_my_submission" not in tools:
            pytest.skip("comment_on_my_submission not registered in this configuration")

        with patch(
            "canvas_mcp.tools.student_write.make_canvas_request", new_callable=AsyncMock
        ) as request, patch(
            "canvas_mcp.tools.student_write.get_course_id",
            new=AsyncMock(return_value="60366"),
        ):
            result = await tools["comment_on_my_submission"](
                course_identifier="badm_350",
                assignment_id="123/submissions/456?",
                comment="hello",
            )

        assert "numeric Canvas assignment ID" in result
        assert request.call_count == 0
