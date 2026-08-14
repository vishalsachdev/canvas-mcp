"""
Tests for discussion-related MCP tools.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls for discussion tools."""
    with patch('canvas_mcp.tools.discussions.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.discussions.get_course_code') as mock_get_code, \
         patch('canvas_mcp.tools.discussions.fetch_all_paginated_results') as mock_fetch, \
         patch('canvas_mcp.tools.discussions.make_canvas_request') as mock_request:

        mock_get_id.return_value = "60366"
        mock_get_code.return_value = "badm_350_120251"

        yield {
            'get_course_id': mock_get_id,
            'get_course_code': mock_get_code,
            'fetch_all_paginated_results': mock_fetch,
            'make_canvas_request': mock_request
        }


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered discussion tools."""
    from fastmcp import FastMCP

    from canvas_mcp.tools.discussions import (
        register_educator_discussion_tools,
        register_shared_discussion_tools,
    )

    mcp = FastMCP("test")
    captured_functions = {}

    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured_functions[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    register_shared_discussion_tools(mcp)
    register_educator_discussion_tools(mcp)

    return captured_functions.get(tool_name)


class TestUpdateDiscussionTopic:
    """Tests for update_discussion_topic tool."""

    @pytest.mark.asyncio
    async def test_update_discussion_topic_message_only(self, mock_canvas_api):
        """Test updating only the discussion body."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 42,
            "title": "Week 1 Discussion",
            "message": "<p>Updated prompt text</p>",
            "published": True,
            "is_announcement": False,
        }

        update_discussion_topic = get_tool_function('update_discussion_topic')
        assert update_discussion_topic is not None

        result = await update_discussion_topic(
            "badm_350_120251",
            42,
            message="<p>Updated prompt text</p>",
        )

        mock_canvas_api['get_course_id'].assert_called_once_with("badm_350_120251")
        mock_canvas_api['make_canvas_request'].assert_called_once()

        call_args = mock_canvas_api['make_canvas_request'].call_args
        assert call_args[0][0] == "put"
        assert call_args[0][1] == "/courses/60366/discussion_topics/42"
        assert call_args[1]['data'] == {"message": "<p>Updated prompt text</p>"}

        assert "successfully" in result
        assert "Week 1 Discussion" in result
        assert "Updated fields: message" in result

    @pytest.mark.asyncio
    async def test_update_discussion_topic_multiple_fields(self, mock_canvas_api):
        """Test updating title, message, and published together."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 42,
            "title": "Renamed Discussion",
            "message": "<p>New body</p>",
            "published": True,
            "is_announcement": False,
        }

        update_discussion_topic = get_tool_function('update_discussion_topic')
        result = await update_discussion_topic(
            "badm_350_120251",
            42,
            title="Renamed Discussion",
            message="<p>New body</p>",
            published=True,
        )

        call_args = mock_canvas_api['make_canvas_request'].call_args
        assert call_args[1]['data'] == {
            "title": "Renamed Discussion",
            "message": "<p>New body</p>",
            "published": True,
        }

        assert "successfully" in result
        assert "title" in result
        assert "message" in result
        assert "published" in result

    @pytest.mark.asyncio
    async def test_update_discussion_topic_no_fields(self, mock_canvas_api):
        """Test that error is returned when no fields are provided."""
        update_discussion_topic = get_tool_function('update_discussion_topic')
        result = await update_discussion_topic("badm_350_120251", 42)

        assert "No fields provided to update" in result
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_update_discussion_topic_api_error(self, mock_canvas_api):
        """Test error handling when API fails."""
        mock_canvas_api['make_canvas_request'].return_value = {"error": "Topic not found"}

        update_discussion_topic = get_tool_function('update_discussion_topic')
        result = await update_discussion_topic(
            "badm_350_120251",
            99999,
            message="New text",
        )

        assert "Error updating discussion topic" in result
        assert "Topic not found" in result

    @pytest.mark.asyncio
    async def test_update_discussion_topic_invalid_date(self, mock_canvas_api):
        """Test validation of invalid lock_at date."""
        update_discussion_topic = get_tool_function('update_discussion_topic')
        result = await update_discussion_topic(
            "badm_350_120251",
            42,
            lock_at="not-a-valid-date",
        )

        assert "Invalid date format for lock_at" in result
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_update_discussion_topic_announcement(self, mock_canvas_api):
        """Test that announcement topics are labeled correctly in output."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 7,
            "title": "Exam reminder",
            "message": "<p>Bring a pencil</p>",
            "published": True,
            "is_announcement": True,
        }

        update_discussion_topic = get_tool_function('update_discussion_topic')
        result = await update_discussion_topic(
            "badm_350_120251",
            7,
            message="<p>Bring a pencil</p>",
        )

        assert "Announcement updated successfully" in result
        assert "Type: Announcement" in result


class TestListDiscussionTopics:
    """Tests for list_discussion_topics (issue #238).

    Canvas's ``GET /courses/:id/discussion_topics`` index excludes announcements
    unless ``only_announcements=true`` is passed. ``include[]=announcement`` is
    NOT a supported include value and is silently ignored -- measured live on
    2026-08-08 against course 41635: with and without it the endpoint returned
    the same 19 topics, 0 of them announcements.
    """

    @pytest.mark.asyncio
    async def test_list_discussion_topics(self, mock_canvas_api):
        """Default call lists discussion topics via the tool itself."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = [
            {"id": 1, "title": "Topic 1", "posted_at": "2024-01-15", "published": True},
            {"id": 2, "title": "Topic 2", "posted_at": "2024-01-20", "published": True},
        ]

        list_discussion_topics = get_tool_function('list_discussion_topics')
        result = await list_discussion_topics("badm_350_120251")

        assert "Topic 1" in result
        assert "Topic 2" in result
        assert "Type: Discussion" in result

    @pytest.mark.asyncio
    async def test_default_does_not_request_announcements(self, mock_canvas_api):
        """Default call must not ask Canvas for announcements at all."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        list_discussion_topics = get_tool_function('list_discussion_topics')
        await list_discussion_topics("badm_350_120251")

        assert mock_canvas_api['fetch_all_paginated_results'].call_count == 1
        params = mock_canvas_api['fetch_all_paginated_results'].call_args[0][1]
        assert "only_announcements" not in params

    @pytest.mark.asyncio
    async def test_never_sends_unsupported_include_announcement(self, mock_canvas_api):
        """``include[]=announcement`` is not a valid Canvas include -- never send it."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        list_discussion_topics = get_tool_function('list_discussion_topics')
        await list_discussion_topics("badm_350_120251", include_announcements=True)

        for call in mock_canvas_api['fetch_all_paginated_results'].call_args_list:
            params = call[0][1]
            assert "announcement" not in params.get("include[]", [])

    @pytest.mark.asyncio
    async def test_include_announcements_actually_returns_announcements(self, mock_canvas_api):
        """include_announcements=True must really yield announcements, not just discussions.

        This is the issue #238 regression: the flag used to set an ignored
        ``include[]`` value, so the caller got discussions only while believing
        announcements were included.
        """
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            [{"id": 1, "title": "Week 1 discussion", "posted_at": "2024-01-15",
              "published": True, "is_announcement": False}],
            [{"id": 9, "title": "Exam moved", "posted_at": "2024-01-20",
              "published": True, "is_announcement": True}],
        ]

        list_discussion_topics = get_tool_function('list_discussion_topics')
        result = await list_discussion_topics("badm_350_120251", include_announcements=True)

        assert mock_canvas_api['fetch_all_paginated_results'].call_count == 2
        announcement_params = mock_canvas_api['fetch_all_paginated_results'].call_args_list[1][0][1]
        assert announcement_params["only_announcements"] is True

        assert "Week 1 discussion" in result
        assert "Exam moved" in result
        assert "Type: Announcement" in result
        assert "Type: Discussion" in result

    @pytest.mark.asyncio
    async def test_include_announcements_deduplicates(self, mock_canvas_api):
        """A topic returned by both queries must appear once."""
        duplicate = {"id": 9, "title": "Exam moved", "posted_at": "2024-01-20",
                     "published": True, "is_announcement": True}
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            [duplicate], [dict(duplicate)],
        ]

        list_discussion_topics = get_tool_function('list_discussion_topics')
        result = await list_discussion_topics("badm_350_120251", include_announcements=True)

        assert result.count("Exam moved") == 1

    @pytest.mark.asyncio
    async def test_include_announcements_survives_announcement_error(self, mock_canvas_api):
        """If the announcements query errors, still return the discussions."""
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            [{"id": 1, "title": "Week 1 discussion", "posted_at": "2024-01-15",
              "published": True, "is_announcement": False}],
            {"error": "403 Forbidden"},
        ]

        list_discussion_topics = get_tool_function('list_discussion_topics')
        result = await list_discussion_topics("badm_350_120251", include_announcements=True)

        assert "Week 1 discussion" in result

    @pytest.mark.asyncio
    async def test_error_response_surfaces(self, mock_canvas_api):
        """A failing primary query returns a readable error."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = {"error": "404 Not Found"}

        list_discussion_topics = get_tool_function('list_discussion_topics')
        result = await list_discussion_topics("badm_350_120251")

        assert "Error fetching discussion topics" in result


class TestListAnnouncements:
    """Tests for list_announcements (issue #238)."""

    @pytest.mark.asyncio
    async def test_sends_only_announcements_filter(self, mock_canvas_api):
        """The announcements listing must filter server-side."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        list_announcements = get_tool_function('list_announcements')
        await list_announcements("badm_350_120251")

        params = mock_canvas_api['fetch_all_paginated_results'].call_args[0][1]
        assert params["only_announcements"] is True

    @pytest.mark.asyncio
    async def test_does_not_send_unsupported_include(self, mock_canvas_api):
        """``include[]=announcement`` is a no-op against Canvas -- drop it."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        list_announcements = get_tool_function('list_announcements')
        await list_announcements("badm_350_120251")

        params = mock_canvas_api['fetch_all_paginated_results'].call_args[0][1]
        assert "include[]" not in params

    @pytest.mark.asyncio
    async def test_lists_announcements(self, mock_canvas_api):
        """Announcements are rendered with id, title and post date."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = [
            {"id": 9, "title": "Exam moved", "posted_at": "2024-01-20", "is_announcement": True},
        ]

        list_announcements = get_tool_function('list_announcements')
        result = await list_announcements("badm_350_120251")

        assert "Exam moved" in result
        assert "ID: 9" in result


class TestDiscussionTools:
    """Test discussion tool functions."""

    @pytest.mark.asyncio
    async def test_list_discussion_entries(self):
        """Test listing discussion entries."""
        mock_entries = [
            {"id": 101, "message": "Great post!", "user_id": 1001},
            {"id": 102, "message": "I agree", "user_id": 1002}
        ]

        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_entries

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/courses/12345/discussion_topics/1/entries", {})

            assert len(result) == 2
            assert result[0]["message"] == "Great post!"

    @pytest.mark.asyncio
    async def test_post_discussion_entry(self):
        """Test posting a discussion entry."""
        new_entry = {
            "message": "This is my reply"
        }

        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": 103, "message": "This is my reply"}

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("post", "/courses/12345/discussion_topics/1/entries", data=new_entry)

            assert result["message"] == "This is my reply"

    @pytest.mark.asyncio
    async def test_reply_to_discussion_entry(self):
        """Test replying to a discussion entry."""
        reply = {
            "message": "Reply to your post"
        }

        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": 104, "message": "Reply to your post"}

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("post", "/courses/12345/discussion_topics/1/entries/101/replies", data=reply)

            assert result["message"] == "Reply to your post"

    @pytest.mark.asyncio
    async def test_empty_discussion_topics(self):
        """Test handling empty discussion topics list."""
        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/courses/12345/discussion_topics", {})

            assert result == []


# The course payload the permission pre-check (#283) reads. Shapes measured
# live 2026-08-14 on UIUC Canvas: GET /courses/:id?include[]=permissions
# returns exactly {"create_discussion_topic": bool, "create_announcement":
# bool} on the single-course endpoint (the list endpoint ignores the
# include, and the dedicated /permissions endpoint omits both keys).
def _course_with_permissions(can_announce):
    return {
        "id": 60366,
        "name": "Test Course",
        "permissions": {
            "create_discussion_topic": True,
            "create_announcement": can_announce,
        },
    }


class TestCreateAnnouncementPermissionPrecheck:
    """#283: check course-level create_announcement permission before the
    POST, so a student token is refused up front instead of Canvas silently
    creating a regular discussion topic."""

    @pytest.mark.asyncio
    async def test_permission_false_refuses_without_posting(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].side_effect = [
            _course_with_permissions(can_announce=False),
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello class")

        assert "Error creating announcement" in result
        assert "permission" in result.lower()
        # The anti-fallback steering must ride along (issue #283).
        assert "Do not attempt to post this content via discussion tools" in result
        # Exactly one API call — the pre-check GET; no POST ever happened.
        assert mock_canvas_api['make_canvas_request'].call_count == 1
        method = mock_canvas_api['make_canvas_request'].call_args_list[0][0][0]
        assert method == "get"

    @pytest.mark.asyncio
    async def test_permission_true_proceeds_to_create(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].side_effect = [
            _course_with_permissions(can_announce=True),
            {
                "id": 1001,
                "title": "Real announcement",
                "is_announcement": True,
                "created_at": "2026-08-03T15:00:00Z",
            },
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "Real announcement", "Hello")

        assert "created successfully" in result
        assert mock_canvas_api['make_canvas_request'].call_count == 2

    @pytest.mark.asyncio
    async def test_missing_permissions_key_fails_open(self, mock_canvas_api):
        """Older Canvas / unexpected shapes: no permissions dict means we
        proceed and rely on the post-create backstop, not refuse."""
        mock_canvas_api['make_canvas_request'].side_effect = [
            {"id": 60366, "name": "Test Course"},  # no permissions key
            {
                "id": 1002,
                "title": "HI",
                "is_announcement": True,
                "created_at": "2026-08-03T15:00:00Z",
            },
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello")

        assert "created successfully" in result

    @pytest.mark.asyncio
    async def test_precheck_error_fails_open(self, mock_canvas_api):
        """A failed pre-check GET must not block the create attempt."""
        mock_canvas_api['make_canvas_request'].side_effect = [
            {"error": "HTTP error: 500"},
            {
                "id": 1003,
                "title": "HI",
                "is_announcement": True,
                "created_at": "2026-08-03T15:00:00Z",
            },
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello")

        assert "created successfully" in result


class TestCreateAnnouncementConfirmsWrite:
    """#220/#283: Canvas silently drops is_announcement for tokens without
    announcement permission and creates a regular discussion, returning 200.
    The tool must not report success — and must clean up the unintended
    topic rather than leave it visible to the course.
    """

    @pytest.mark.asyncio
    async def test_silent_downgrade_deletes_orphan_and_reports_failure(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].side_effect = [
            _course_with_permissions(can_announce=True),  # pre-check passes (stale/racy)
            {
                "id": 999,
                "title": "HI",
                "is_announcement": False,
                "created_at": "2026-08-03T15:00:00Z",
            },
            {"id": 999, "deleted": True},  # cleanup DELETE succeeds
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello class")

        assert "created successfully" not in result
        assert "Error creating announcement" in result
        assert "deleted" in result.lower()  # says the orphan was cleaned up
        assert "Do not attempt to post this content via discussion tools" in result
        # Third call is the cleanup DELETE aimed at the orphan topic.
        method, endpoint = mock_canvas_api['make_canvas_request'].call_args_list[2][0][:2]
        assert method == "delete"
        assert endpoint.endswith("/discussion_topics/999")

    @pytest.mark.asyncio
    async def test_silent_downgrade_delete_fails_warns_with_manual_remedy(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].side_effect = [
            _course_with_permissions(can_announce=True),
            {
                "id": 999,
                "title": "HI",
                "is_announcement": False,
                "created_at": "2026-08-03T15:00:00Z",
            },
            {"error": "HTTP error: 403"},  # cleanup DELETE refused
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello class")

        assert "created successfully" not in result
        assert "Could not confirm" in result
        assert "999" in result  # points at the stray discussion topic
        assert "delete it in Canvas" in result

    @pytest.mark.asyncio
    async def test_silent_downgrade_delete_returns_none_warns(self, mock_canvas_api):
        """make_canvas_request returns response.json() verbatim, so a null
        200 body surfaces as None — must warn, not crash on `in` (found by
        adversarial review probe)."""
        mock_canvas_api['make_canvas_request'].side_effect = [
            _course_with_permissions(can_announce=True),
            {
                "id": 999,
                "title": "HI",
                "is_announcement": False,
                "created_at": "2026-08-03T15:00:00Z",
            },
            None,  # cleanup DELETE answered 200 with a null body
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello class")

        assert "created successfully" not in result
        assert "Could not confirm" in result
        assert "delete it in Canvas" in result

    @pytest.mark.asyncio
    async def test_missing_flag_in_response_is_not_success(self, mock_canvas_api):
        """A response without the is_announcement key is also unconfirmed."""
        mock_canvas_api['make_canvas_request'].side_effect = [
            _course_with_permissions(can_announce=True),
            {
                "id": 1000,
                "title": "HI",
                "created_at": "2026-08-03T15:00:00Z",
            },
            {"id": 1000, "deleted": True},
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello class")

        assert "created successfully" not in result

    @pytest.mark.asyncio
    async def test_downgrade_without_topic_id_cannot_clean_up(self, mock_canvas_api):
        """No id in the response: nothing to delete — warn, don't crash."""
        mock_canvas_api['make_canvas_request'].side_effect = [
            _course_with_permissions(can_announce=True),
            {
                "title": "HI",
                "is_announcement": False,
                "created_at": "2026-08-03T15:00:00Z",
            },
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello class")

        assert "created successfully" not in result
        assert "Could not confirm" in result

    @pytest.mark.asyncio
    async def test_confirmed_announcement_reports_success(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].side_effect = [
            _course_with_permissions(can_announce=True),
            {
                "id": 1001,
                "title": "Real announcement",
                "is_announcement": True,
                "created_at": "2026-08-03T15:00:00Z",
            },
        ]

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "Real announcement", "Hello")

        assert "created successfully" in result
        assert "1001" in result


class TestAnnouncementPermissionErrorSteersAwayFromDiscussionFallback:
    """#283: a client model watched create_announcement fail for a student
    (insufficient permissions) and silently posted the same content as a
    discussion topic instead — an unwanted, unconfirmed write. When the
    Canvas API error looks like a permission failure, the returned message
    must explicitly tell the caller not to fall back to a discussion tool.
    """

    @pytest.mark.asyncio
    async def test_403_error_includes_no_fallback_guidance(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].return_value = {
            "error": "HTTP error: 403, Details: {'status': 'unauthorized'}"
        }

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello class")

        assert "Error creating announcement" in result
        assert "do not attempt to post this content via discussion" in result.lower()
        assert "report this to the user" in result.lower()

    @pytest.mark.asyncio
    async def test_401_error_includes_no_fallback_guidance(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].return_value = {
            "error": "HTTP error: 401, Text: Unauthorized"
        }

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello class")

        assert "do not attempt to post this content via discussion" in result.lower()

    @pytest.mark.asyncio
    async def test_non_permission_error_has_no_fallback_guidance(self, mock_canvas_api):
        """A plain 500/network error isn't a permissions story — don't
        editorialize about fallback behavior that isn't the cause here."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "error": "HTTP error: 500, Details: {'status': 'internal_server_error'}"
        }

        create_announcement = get_tool_function('create_announcement')
        result = await create_announcement("badm_350_120251", "HI", "Hello class")

        assert "Error creating announcement" in result
        assert "do not attempt to post this content via discussion" not in result.lower()


class TestDiscussionToolDocstringsWarnAgainstAnnouncementFallback:
    """#283: the MCP server can't block a client model's tool choice, but it
    controls the descriptions the model reads. post_discussion_entry and
    create_discussion_topic must carry an explicit anti-fallback warning.
    """

    @staticmethod
    def _registered_descriptions() -> dict[str, str]:
        import asyncio

        from fastmcp import FastMCP

        from canvas_mcp.tools.discussions import (
            register_educator_discussion_tools,
            register_shared_discussion_tools,
        )

        mcp = FastMCP("test-descriptions")
        register_shared_discussion_tools(mcp)
        register_educator_discussion_tools(mcp)

        async def _collect():
            tools = await mcp.list_tools()
            return {tool.name: (tool.description or "") for tool in tools}

        return asyncio.run(_collect())

    def test_post_discussion_entry_warns_against_announcement_fallback(self):
        descriptions = self._registered_descriptions()
        description = descriptions["post_discussion_entry"].lower()

        assert "create_announcement" in description
        assert "do not" in description or "never" in description

    def test_create_discussion_topic_warns_against_announcement_fallback(self):
        descriptions = self._registered_descriptions()
        description = descriptions["create_discussion_topic"].lower()

        assert "create_announcement" in description
        assert "do not" in description or "never" in description


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
