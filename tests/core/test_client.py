"""Unit tests for core HTTP client helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import canvas_mcp.core.client as client_module
from canvas_mcp.core.client import _canvas_auth_headers


class TestCanvasAuthHeaders:
    """All Canvas API requests must carry a User-Agent (Instructure enforces it)."""

    def test_includes_user_agent(self):
        headers = _canvas_auth_headers("some-token")
        assert "User-Agent" in headers
        assert headers["User-Agent"].startswith("canvas-mcp/")

    def test_includes_bearer_authorization(self):
        headers = _canvas_auth_headers("some-token")
        assert headers["Authorization"] == "Bearer some-token"

    def test_user_agent_identifies_project(self):
        """UA should be self-identifying per Instructure's guidance (contact URL)."""
        headers = _canvas_auth_headers("t")
        assert "github.com/vishalsachdev/canvas-mcp" in headers["User-Agent"]


class TestResolveCanvasApiRoot:
    def test_rest_root_is_unchanged(self):
        assert (
            client_module._resolve_canvas_api_root(
                "https://canvas.school.edu/api/v1", "rest"
            )
            == "https://canvas.school.edu/api/v1"
        )

    def test_quiz_root_rewrites_trailing_api_version(self):
        assert (
            client_module._resolve_canvas_api_root(
                "https://canvas.school.edu/lms/api/v2", "quiz"
            )
            == "https://canvas.school.edu/lms/api/quiz/v1"
        )

    def test_quiz_root_rejects_non_api_version_base(self):
        with pytest.raises(ValueError, match="expected trailing /api/v<N>"):
            client_module._resolve_canvas_api_root(
                "https://canvas.school.edu/not-api", "quiz"
            )


class TestMakeCanvasRequestApiRoot:
    @pytest.fixture(autouse=True)
    def reset_client_state(self):
        client_module._request_semaphore = None
        client_module._semaphore_loop_ref = None
        yield
        client_module._request_semaphore = None
        client_module._semaphore_loop_ref = None

    @pytest.mark.asyncio
    async def test_quiz_api_root_uses_quiz_base_and_still_anonymizes(self):
        mock_config = SimpleNamespace(
            canvas_api_url="https://canvas.school.edu/api/v1",
            max_concurrent_requests=5,
            api_timeout=30,
            log_api_requests=False,
            enable_data_anonymization=True,
            anonymization_debug=False,
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"id": 101, "name": "Alice"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("canvas_mcp.core.config.get_config", return_value=mock_config),
            patch("canvas_mcp.core.client._get_http_client", return_value=mock_client),
            patch(
                "canvas_mcp.core.client._anonymize_for_endpoint",
                return_value=({"id": 101, "name": "Student_x"}, "users"),
            ) as mock_anonymize,
        ):
            result = await client_module.make_canvas_request(
                "get",
                "/courses/42/users",
                api_root="quiz",
            )

        assert result == {"id": 101, "name": "Student_x"}
        requested_url = mock_client.get.await_args.args[0]
        assert requested_url == "https://canvas.school.edu/api/quiz/v1/courses/42/users"
        mock_anonymize.assert_called_once_with(
            {"id": 101, "name": "Alice"}, "/courses/42/users"
        )


class TestPaginatedFetchApiRoot:
    """`api_root` must reach the paginated path without weakening the gate.

    A quiz-root caller that hand-rolls its own pagination over
    ``make_canvas_request`` loses the single-anonymization-pass-over-the-
    complete-dataset property, which is the #164 shortcut. So the paginated
    helper has to support the alternate root itself.
    """

    @pytest.fixture(autouse=True)
    def reset_client_state(self):
        client_module._request_semaphore = None
        client_module._semaphore_loop_ref = None
        yield
        client_module._request_semaphore = None
        client_module._semaphore_loop_ref = None

    @pytest.mark.asyncio
    async def test_quiz_root_is_forwarded_to_every_page_request(self):
        pages = [[{"id": i} for i in range(100)], [{"id": 100}]]

        async def fake_request(method, endpoint, **kwargs):
            return pages.pop(0) if pages else []

        with patch.object(
            client_module, "make_canvas_request", side_effect=fake_request
        ) as mock_req:
            await client_module.fetch_all_paginated_results(
                "/courses/42/quizzes", api_root="quiz", skip_anonymization=True
            )

        assert mock_req.await_count == 2, "expected two page fetches"
        for call in mock_req.await_args_list:
            assert call.kwargs["api_root"] == "quiz"
            assert call.kwargs["skip_anonymization"] is True

    @pytest.mark.asyncio
    async def test_rest_root_remains_the_default(self):
        async def fake_request(method, endpoint, **kwargs):
            return []

        with patch.object(
            client_module, "make_canvas_request", side_effect=fake_request
        ) as mock_req:
            await client_module.fetch_all_paginated_results("/courses/42/quizzes")

        assert mock_req.await_args.kwargs["api_root"] == "rest"

    @pytest.mark.asyncio
    async def test_quiz_root_still_anonymizes_once_over_the_merged_dataset(self):
        """The gate keys off `endpoint`, so the alternate root cannot bypass it."""
        mock_config = SimpleNamespace(
            enable_data_anonymization=True, anonymization_debug=False
        )
        pages = [
            [{"id": 1, "name": "Alice"} for _ in range(100)],
            [{"id": 2, "name": "Bob"}],
        ]

        async def fake_request(method, endpoint, **kwargs):
            return pages.pop(0) if pages else []

        with (
            patch.object(client_module, "make_canvas_request", side_effect=fake_request),
            patch("canvas_mcp.core.config.get_config", return_value=mock_config),
            patch.object(
                client_module,
                "_anonymize_for_endpoint",
                return_value=([{"id": 1, "name": "Student_x"}], "users"),
            ) as mock_anon,
        ):
            result = await client_module.fetch_all_paginated_results(
                "/courses/42/users", api_root="quiz"
            )

        # Exactly one anonymization pass, over all 101 merged records, keyed on
        # the endpoint path rather than the base URL.
        mock_anon.assert_called_once()
        merged, endpoint_arg = mock_anon.call_args.args
        assert len(merged) == 101
        assert endpoint_arg == "/courses/42/users"
        assert result == [{"id": 1, "name": "Student_x"}]
