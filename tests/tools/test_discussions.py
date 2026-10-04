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

        from canvas_mcp.tools import discussions as discussions_module
        discussions_module._unservable_topics.clear()

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
        assert [call.args[0] for call in mock_canvas_api['make_canvas_request'].call_args_list] == [
            "get", "put",
        ]

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
        # Must not claim cleanup was attempted when it wasn't (round-2 note).
        assert "could not be attempted" in result

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


class TestGroupDiscussionReads:
    """Read tools reach discussions inside a group space via group_id."""

    @staticmethod
    def _group_aware_request(group_course_id="60366"):
        async def request(method, path, **kwargs):
            if path == "/groups/298062":
                return {"id": 298062, "course_id": group_course_id}
            if path.endswith("/discussion_topics/814175"):
                return {"id": 814175, "title": "Utkast till Första Referensgruppsmötet"}
            return {"error": f"unexpected path {path}"}
        return request

    @pytest.mark.asyncio
    async def test_list_topics_uses_group_path(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].side_effect = self._group_aware_request()
        mock_canvas_api['fetch_all_paginated_results'].return_value = [
            {"id": 814175, "title": "Utkast till Första Referensgruppsmötet",
             "published": True, "posted_at": "2026-09-25T10:00:00Z"},
        ]

        list_discussion_topics = get_tool_function('list_discussion_topics')
        result = await list_discussion_topics("badm_350_120251", group_id=298062)

        path = mock_canvas_api['fetch_all_paginated_results'].call_args[0][0]
        assert path == "/groups/298062/discussion_topics"
        assert "814175" in result

    @pytest.mark.asyncio
    async def test_list_topics_without_group_keeps_course_path(self, mock_canvas_api):
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        list_discussion_topics = get_tool_function('list_discussion_topics')
        await list_discussion_topics("badm_350_120251")

        path = mock_canvas_api['fetch_all_paginated_results'].call_args[0][0]
        assert path == "/courses/60366/discussion_topics"
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_group_from_another_course_is_rejected(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].side_effect = self._group_aware_request(
            group_course_id="99999"
        )

        list_discussion_entries = get_tool_function('list_discussion_entries')
        result = await list_discussion_entries(
            "badm_350_120251", 814175, group_id=298062
        )

        assert "does not belong to course 60366" in result
        mock_canvas_api['fetch_all_paginated_results'].assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_group_id", [
        "298062/discussion_topics", "298062?as_user_id=1", "../courses/60366", "", "12a",
    ])
    async def test_non_numeric_group_id_is_refused_before_any_request(
        self, mock_canvas_api, bad_group_id
    ):
        list_discussion_entries = get_tool_function('list_discussion_entries')
        result = await list_discussion_entries(
            "badm_350_120251", 814175, group_id=bad_group_id
        )

        assert "group_id must be a numeric Canvas group ID" in result
        requested = [c.args[1] for c in mock_canvas_api['make_canvas_request'].call_args_list]
        assert not any(path.startswith("/groups") for path in requested)
        mock_canvas_api['fetch_all_paginated_results'].assert_not_called()

    @pytest.mark.asyncio
    async def test_entries_and_replies_use_group_path(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].side_effect = self._group_aware_request()

        async def fetch(path, params=None):
            if path.endswith("/entries"):
                return [{"id": 1, "user_id": 7, "user_name": "Student",
                         "message": "<p>Feedback</p>", "created_at": "2026-09-26T08:00:00Z",
                         "recent_replies": [], "has_more_replies": False}]
            return []
        mock_canvas_api['fetch_all_paginated_results'].side_effect = fetch

        get_discussion_with_replies = get_tool_function('get_discussion_with_replies')
        result = await get_discussion_with_replies(
            "badm_350_120251", 814175, include_replies=True, group_id=298062
        )

        fetched = [c[0][0] for c in mock_canvas_api['fetch_all_paginated_results'].call_args_list]
        assert fetched == [
            "/groups/298062/discussion_topics/814175/entries",
            "/groups/298062/discussion_topics/814175/entries/1/replies",
        ]
        assert "Feedback" in result

    def test_group_discussion_content_is_anonymization_gated(self):
        from canvas_mcp.core.client import ANONYMIZE_FULL, _endpoint_anonymization_mode

        for path in (
            "/groups/298062/discussion_topics/814175/entries",
            "/groups/298062/discussion_topics/814175/view",
            "/groups/298062/discussion_topics/814175/entries/1/replies",
        ):
            assert _endpoint_anonymization_mode(path) == ANONYMIZE_FULL


class TestListGroupDiscussionTopics:
    """list_group_discussion_topics sweeps every group space of a course."""

    GROUPS = [
        {"id": 298061, "name": "Referensgrupp A", "group_category_id": 47901},
        {"id": 298062, "name": "Referensgrupp B", "group_category_id": 47901},
        {"id": 294537, "name": "Projektgrupp 1", "group_category_id": 47915},
    ]
    TOPICS = {
        "/groups/298061/discussion_topics": [
            {"id": 807009, "title": "Första referensgruppsmöte - Referensgrupp A",
             "root_topic_id": 803256, "discussion_subentry_count": 6},
        ],
        "/groups/298062/discussion_topics": [
            {"id": 814175, "title": "Utkast till Första Referensgruppsmötet",
             "root_topic_id": None, "discussion_subentry_count": 4,
             "author": {"display_name": "Julia Student"}},
        ],
        "/groups/294537/discussion_topics": [],
    }

    def _fetch(self):
        async def fetch(path, params=None):
            if path == "/courses/60366/groups":
                return self.GROUPS
            return self.TOPICS[path]
        return fetch

    @pytest.mark.asyncio
    async def test_marks_topics_started_in_a_group(self, mock_canvas_api):
        mock_canvas_api['fetch_all_paginated_results'].side_effect = self._fetch()

        tool = get_tool_function('list_group_discussion_topics')
        result = await tool("badm_350_120251")

        assert "(3 groups)" in result
        assert "Group copy of course topic 803256" in result
        assert "Started in this group by" in result
        assert "Julia Student" in result
        assert "Entries: 4" in result
        assert "No discussion topics." in result

    @pytest.mark.asyncio
    async def test_filters_by_group_category(self, mock_canvas_api):
        mock_canvas_api['fetch_all_paginated_results'].side_effect = self._fetch()

        tool = get_tool_function('list_group_discussion_topics')
        result = await tool("badm_350_120251", group_category_id=47901)

        fetched = {c[0][0] for c in mock_canvas_api['fetch_all_paginated_results'].call_args_list}
        assert "/groups/294537/discussion_topics" not in fetched
        assert "(2 groups)" in result

    @pytest.mark.asyncio
    async def test_reports_a_failing_group_without_dropping_the_rest(self, mock_canvas_api):
        topics = dict(self.TOPICS)
        topics["/groups/298061/discussion_topics"] = {"error": "HTTP error: 403"}

        async def fetch(path, params=None):
            if path == "/courses/60366/groups":
                return self.GROUPS
            return topics[path]
        mock_canvas_api['fetch_all_paginated_results'].side_effect = fetch

        tool = get_tool_function('list_group_discussion_topics')
        result = await tool("badm_350_120251")

        assert "Error fetching topics: HTTP error: 403" in result
        assert "814175" in result


class TestAnonymousTopics:
    """Issue 421 Part 1: REST answers 404 for anonymous topics the list still shows."""

    NOT_FOUND = {"error": (
        "HTTP error: 404, Details: {'errors': [{'message': "
        "'The specified resource does not exist.'}]}"
    )}
    ANON_TOPIC = {
        "id": 555, "title": "Anonymous feedback", "published": True,
        "posted_at": "2026-09-20T10:00:00Z", "anonymous_state": "full_anonymity",
        "html_url": "https://canvas.example.edu/courses/60366/discussion_topics/555",
    }
    PLAIN_TOPIC = {
        "id": 556, "title": "Week 3", "published": True,
        "posted_at": "2026-09-21T10:00:00Z", "anonymous_state": None,
    }

    def _list_fetch(self, topics_path="/courses/60366/discussion_topics"):
        """Entries 404; the topic index at topics_path lists both topics."""
        async def fetch(path, params=None):
            if path == topics_path:
                return [self.ANON_TOPIC, self.PLAIN_TOPIC]
            if "/entries" in path:
                return dict(self.NOT_FOUND)
            return {"error": f"unexpected path {path}"}
        return fetch

    @pytest.mark.asyncio
    async def test_list_shows_anonymous_state_only_when_canvas_sends_one(
        self, mock_canvas_api
    ):
        legacy = {"id": 557, "title": "No field", "published": True}
        mock_canvas_api['fetch_all_paginated_results'].return_value = [
            self.ANON_TOPIC, self.PLAIN_TOPIC, legacy,
        ]

        result = await get_tool_function('list_discussion_topics')("badm_350_120251")

        assert result.count("Anonymity:") == 1
        assert "Anonymity: full_anonymity" in result

    @pytest.mark.asyncio
    async def test_group_list_shows_anonymous_state(self, mock_canvas_api):
        async def fetch(path, params=None):
            if path == "/courses/60366/groups":
                return [{"id": 298062, "name": "B", "group_category_id": 1}]
            return [dict(self.ANON_TOPIC, anonymous_state="partial_anonymity")]
        mock_canvas_api['fetch_all_paginated_results'].side_effect = fetch

        result = await get_tool_function('list_group_discussion_topics')("badm_350_120251")

        assert "  Anonymity: partial_anonymity" in result

    @pytest.mark.asyncio
    async def test_details_404_for_listed_topic_explains_anonymity(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].return_value = dict(self.NOT_FOUND)
        mock_canvas_api['fetch_all_paginated_results'].side_effect = self._list_fetch()

        result = await get_tool_function('get_discussion_topic_details')(
            "badm_350_120251", 555
        )

        assert "topic 555 exists" in result
        assert "anonymous_state: full_anonymity" in result
        assert "returns 404" in result
        assert "Canvas UI" in result
        assert self.ANON_TOPIC["html_url"] in result
        assert "Error fetching discussion topic details" not in result
        fetched = [c[0][0] for c in mock_canvas_api['fetch_all_paginated_results'].call_args_list]
        assert fetched == ["/courses/60366/discussion_topics"]

    @pytest.mark.asyncio
    async def test_details_404_for_unlisted_topic_stays_not_found(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].return_value = dict(self.NOT_FOUND)
        mock_canvas_api['fetch_all_paginated_results'].side_effect = self._list_fetch()

        result = await get_tool_function('get_discussion_topic_details')(
            "badm_350_120251", 999
        )

        assert result.startswith("Error fetching discussion topic details: HTTP error: 404")
        assert "anonymous" not in result.lower()

    @pytest.mark.asyncio
    async def test_details_404_when_list_fails_stays_not_found(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].return_value = dict(self.NOT_FOUND)
        mock_canvas_api['fetch_all_paginated_results'].return_value = {"error": "HTTP error: 403"}

        result = await get_tool_function('get_discussion_topic_details')(
            "badm_350_120251", 555
        )

        assert result.startswith("Error fetching discussion topic details: HTTP error: 404")

    @pytest.mark.asyncio
    async def test_non_404_error_makes_no_list_call(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].return_value = {"error": "HTTP error: 403"}

        result = await get_tool_function('get_discussion_topic_details')(
            "badm_350_120251", 555
        )

        assert result == "Error fetching discussion topic details: HTTP error: 403"
        mock_canvas_api['fetch_all_paginated_results'].assert_not_called()

    @pytest.mark.asyncio
    async def test_details_success_makes_no_list_call(self, mock_canvas_api):
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 556, "title": "Week 3", "message": "<p>Hi</p>",
            "author": {"id": 1, "display_name": "Prof"},
        }

        result = await get_tool_function('get_discussion_topic_details')(
            "badm_350_120251", 556
        )

        assert "Discussion Details" in result
        mock_canvas_api['fetch_all_paginated_results'].assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name", [
        "list_discussion_entries", "get_discussion_with_replies",
    ])
    async def test_entry_readers_explain_listed_404(self, mock_canvas_api, tool_name):
        # Without operator opt-in, explain the REST limitation without GraphQL.
        mock_canvas_api['fetch_all_paginated_results'].side_effect = self._list_fetch()
        mock_canvas_api['make_canvas_request'].return_value = dict(self.NOT_FOUND)

        result = await get_tool_function(tool_name)("badm_350_120251", 555)

        assert "topic 555 exists" in result
        assert "Canvas UI" in result
        assert "Error fetching discussion entries" not in result
        paths = [c.args[1] for c in mock_canvas_api['make_canvas_request'].call_args_list]
        assert paths == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name", [
        "list_discussion_entries", "get_discussion_with_replies",
    ])
    async def test_entry_readers_keep_not_found_for_unlisted(self, mock_canvas_api, tool_name):
        mock_canvas_api['fetch_all_paginated_results'].side_effect = self._list_fetch()

        result = await get_tool_function(tool_name)("badm_350_120251", 999)

        assert result.startswith("Error fetching discussion entries: HTTP error: 404")

    @pytest.mark.asyncio
    async def test_group_topic_404_checks_the_group_list(self, mock_canvas_api):
        async def request(method, path, **kwargs):
            if path == "/groups/298062":
                return {"id": 298062, "course_id": "60366"}
            if path == "/groups/298062/discussion_topics/555":
                return dict(self.NOT_FOUND)
            return {"error": f"unexpected path {path}"}
        mock_canvas_api['make_canvas_request'].side_effect = request
        mock_canvas_api['fetch_all_paginated_results'].side_effect = self._list_fetch(
            "/groups/298062/discussion_topics"
        )

        result = await get_tool_function('get_discussion_topic_details')(
            "badm_350_120251", 555, group_id=298062
        )

        assert "in this group's topic list" in result
        fetched = [c[0][0] for c in mock_canvas_api['fetch_all_paginated_results'].call_args_list]
        assert fetched == ["/groups/298062/discussion_topics"]


@pytest.mark.asyncio
async def test_anonymous_topic_404_through_real_client_transport(monkeypatch):
    """The 404 detector must match what the real client produces for a 404."""
    import httpx

    from canvas_mcp.core import client as cm
    from canvas_mcp.core.config import reset_config

    # The real client builds absolute URLs from config; pin it so the test does
    # not depend on a developer's .env (CI has none).
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example/api/v1")
    monkeypatch.setenv("CANVAS_API_TOKEN", "test-token")
    reset_config()

    requested = []

    async def transport(request):
        requested.append(request.url.path)
        if request.url.path.endswith("/discussion_topics/555"):
            return httpx.Response(
                404, json={"errors": [{"message": "The specified resource does not exist."}]}
            )
        if request.url.path.endswith("/courses/60366/discussion_topics"):
            return httpx.Response(200, json=[TestAnonymousTopics.ANON_TOPIC])
        if request.url.path == "/api/graphql":
            # GraphQL cannot serve it either, so the explanation stands.
            return httpx.Response(200, json={"data": {"legacyNode": None}})
        return httpx.Response(500, json={"error": "unexpected"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with patch.object(cm, "_get_http_client", return_value=client), \
             patch('canvas_mcp.tools.discussions.get_course_id',
                   AsyncMock(return_value="60366")), \
             patch('canvas_mcp.tools.discussions.get_course_code',
                   AsyncMock(return_value="badm_350_120251")):
            result = await get_tool_function('get_discussion_topic_details')(
                "badm_350_120251", 555
            )

    assert "topic 555 exists" in result, result
    assert [p.rsplit("/api/v1", 1)[-1] for p in requested] == [
        "/courses/60366/discussion_topics/555",
        "/courses/60366/discussion_topics",
    ]


@pytest.fixture
def enable_discussion_graphql(monkeypatch):
    monkeypatch.setenv("DISCUSSION_GRAPHQL_ENABLED", "true")


@pytest.mark.usefixtures("enable_discussion_graphql")
class TestAnonymousDiscussionFallback:
    """REST reads of an anonymous topic fall back to GraphQL transparently."""

    NOT_FOUND = {"error": "HTTP error: 404, Details: {'errors': [{'message': 'The specified resource does not exist.'}]}"}
    LISTING = [
        {"id": 805022, "title": "Frågor om kursen", "published": True,
         "anonymous_state": "partial_anonymity"},
        {"id": 803256, "title": "Första referensgruppsmöte", "published": True,
         "anonymous_state": None},
    ]
    ROOT = {"_id": "1", "parentId": None, "deleted": False,
            "createdAt": "2026-09-01T08:00:00Z", "updatedAt": None,
            "message": "<p>When is the deadline?</p>",
            "author": None, "anonymousAuthor": {"shortName": "8x6pv"}}
    REPLY = {"_id": "2", "parentId": "1", "deleted": False,
             "createdAt": "2026-09-01T09:00:00Z", "updatedAt": None,
             "message": "<p>Friday.</p>",
             "author": {"id": "2448", "display_name": "Teacher Name"}, "anonymousAuthor": None}
    NESTED = {"_id": "3", "parentId": "2", "deleted": False,
              "createdAt": "2026-09-01T10:00:00Z", "updatedAt": None,
              "message": "<p>Thanks!</p>",
              "author": None, "anonymousAuthor": {"shortName": "8x6pv"}}

    @classmethod
    def _graphql(cls, nodes=None, *, has_next=False, cursor=None, context=("Course", "60366")):
        return {"data": {"legacyNode": {
            "_id": "805022", "title": "Frågor om kursen", "message": "<p>Ask here.</p>",
            "createdAt": "2026-08-31T16:38:36Z", "postedAt": "2026-08-31T16:38:36Z",
            "locked": False, "requireInitialPost": False, "isAnnouncement": False,
            "anonymousState": "partial_anonymity",
            "contextType": context[0], "contextId": context[1],
            "author": {"id": "2448", "display_name": "Teacher Name"}, "anonymousAuthor": None,
            "entryCounts": {"repliesCount": 3, "unreadCount": 0}, "participant": {"read": True},
            "discussionEntriesConnection": {
                "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                "nodes": nodes if nodes is not None else [cls.NESTED, cls.REPLY, cls.ROOT],
            },
        }}}

    def _wire(self, mock_canvas_api, graphql_responses=None, listing=None):
        """REST discussion paths 404; the listing and GraphQL answer."""
        graphql = list(graphql_responses or [self._graphql()])

        async def request(method, path, **kwargs):
            if path == "/graphql":
                return graphql.pop(0)
            return self.NOT_FOUND

        async def fetch(path, params=None):
            if path.endswith("/discussion_topics"):
                return self.LISTING if listing is None else listing
            return self.NOT_FOUND

        mock_canvas_api['make_canvas_request'].side_effect = request
        mock_canvas_api['fetch_all_paginated_results'].side_effect = fetch

    @staticmethod
    def _graphql_calls(mock_canvas_api):
        return [c for c in mock_canvas_api['make_canvas_request'].call_args_list
                if c.args[1] == "/graphql"]

    @pytest.mark.asyncio
    async def test_graphql_raw_dates_are_explicitly_unavailable(self, mock_canvas_api):
        self._wire(mock_canvas_api, graphql_responses=[self._graphql(), self._graphql()])
        tool = get_tool_function('get_discussion_topic_details')
        for _ in range(2):  # cold fallback and cached route
            result = await tool("badm_350_120251", 805022, raw_dates=True)
            assert "Raw dates unavailable" in result
            assert "Ungraded topic" not in result
            assert "Raw dates (JSON" not in result

    @pytest.mark.asyncio
    async def test_graphql_entry_read_state_is_unknown(self, mock_canvas_api):
        self._wire(mock_canvas_api)
        result = await get_tool_function('get_discussion_entry_details')(
            "badm_350_120251", 805022, 2
        )
        assert "Read State: Unknown" in result
        assert "Read State: Read" not in result

    @pytest.mark.asyncio
    async def test_graphql_page_cap_refuses_partial_discussion(self, mock_canvas_api, monkeypatch):
        from canvas_mcp.tools import discussions
        monkeypatch.setattr(discussions, "_GRAPHQL_MAX_PAGES", 1)
        self._wire(mock_canvas_api, graphql_responses=[
            self._graphql([self.ROOT], has_next=True, cursor="c1")
        ])
        result = await get_tool_function('get_discussion_with_replies')("badm_350_120251", 805022)
        assert "page limit" in result
        assert "incomplete" in result
        assert "When is the deadline?" not in result
        assert ("/courses/60366", "805022") not in discussions._unservable_topics

    @pytest.mark.asyncio
    async def test_graphql_deep_reply_chain_does_not_recurse(self, mock_canvas_api):
        from canvas_mcp.tools import discussions
        nodes = [dict(self.ROOT, _id=str(i), parentId=str(i - 1) if i else None)
                 for i in range(1100)]
        self._wire(mock_canvas_api, graphql_responses=[self._graphql(nodes)])
        discussion, reason = await discussions._read_discussion_via_graphql("60366", 805022, None)
        assert reason is None
        assert discussion is not None
        root = discussion.find("0")
        assert root is not None
        assert len(root["replies"]) == 1099
        assert {e["id"] for e in root["replies"]} == {str(i) for i in range(1, 1100)}

    @pytest.mark.asyncio
    async def test_graphql_preserves_canvas_connection_order(self, mock_canvas_api):
        from canvas_mcp.tools import discussions
        newer_root = dict(self.ROOT, _id="4", createdAt="2026-09-02T08:00:00Z")
        self._wire(mock_canvas_api, graphql_responses=[
            self._graphql([newer_root, self.NESTED, self.REPLY, self.ROOT])
        ])
        discussion, reason = await discussions._read_discussion_via_graphql("60366", 805022, None)
        assert reason is None
        assert discussion is not None
        assert [e["id"] for e in discussion.entries] == ["4", "1"]
        root = discussion.find("1")
        assert root is not None
        assert [e["id"] for e in root["replies"]] == ["3", "2"]

    @pytest.mark.asyncio
    async def test_topic_details_fall_back(self, mock_canvas_api):
        self._wire(mock_canvas_api)

        result = await get_tool_function('get_discussion_topic_details')("badm_350_120251", 805022)

        assert "Total Entries: 3" in result
        assert "Anonymity: partial_anonymity" in result
        assert "404" not in result
        call = self._graphql_calls(mock_canvas_api)[0]
        assert call.kwargs["api_root"] == "graphql"
        assert call.kwargs["data"]["variables"] == {"id": "805022", "after": None}

    @pytest.mark.asyncio
    async def test_with_replies_falls_back_and_keeps_nested_replies(self, mock_canvas_api):
        self._wire(mock_canvas_api)

        result = await get_tool_function('get_discussion_with_replies')(
            "badm_350_120251", 805022, include_replies=True
        )

        assert "📝 Entry 1 by" in result
        assert "Anonymous 8x6pv" in result
        assert "Replies (2)" in result  # the direct reply and the nested one
        # Canvas supplied NESTED before REPLY; retain that connection order.
        assert result.index("Thanks!") < result.index("Friday.")
        # No REST reply calls once GraphQL has answered.
        fetched = [c.args[0] for c in mock_canvas_api['fetch_all_paginated_results'].call_args_list]
        assert not any("/replies" in p for p in fetched)

    @pytest.mark.asyncio
    async def test_list_entries_falls_back_with_full_content(self, mock_canvas_api):
        self._wire(mock_canvas_api)

        result = await get_tool_function('list_discussion_entries')(
            "badm_350_120251", 805022, include_full_content=True, include_replies=True
        )

        assert result.count("Entry ID:") == 1
        assert "When is the deadline?" in result
        assert "Replies (2):" in result
        assert len(self._graphql_calls(mock_canvas_api)) == 1

    @pytest.mark.asyncio
    async def test_entry_details_find_a_reply(self, mock_canvas_api):
        self._wire(mock_canvas_api)

        result = await get_tool_function('get_discussion_entry_details')(
            "badm_350_120251", 805022, 2
        )

        assert "Entry ID: 2" in result
        assert "Teacher Name" in result
        assert "Replies (1):" in result

    @pytest.mark.asyncio
    async def test_follows_the_pagination_cursor(self, mock_canvas_api):
        self._wire(mock_canvas_api, graphql_responses=[
            self._graphql([self.ROOT], has_next=True, cursor="c1"),
            self._graphql([self.REPLY, self.NESTED]),
        ])

        result = await get_tool_function('get_discussion_with_replies')(
            "badm_350_120251", 805022, include_replies=True
        )

        afters = [c.kwargs["data"]["variables"]["after"] for c in self._graphql_calls(mock_canvas_api)]
        assert afters == [None, "c1"]
        assert "Replies (2)" in result

    @pytest.mark.asyncio
    async def test_unlisted_topic_keeps_its_404_and_skips_graphql(self, mock_canvas_api):
        self._wire(mock_canvas_api)

        result = await get_tool_function('get_discussion_topic_details')("badm_350_120251", 999999)

        assert "HTTP error: 404" in result
        assert self._graphql_calls(mock_canvas_api) == []

    @pytest.mark.asyncio
    async def test_listed_topic_without_anonymous_state_is_still_read(self, mock_canvas_api):
        # Issue 421 treats any listed topic that 404s as unservable by REST,
        # whether or not the listing reports anonymous_state.
        self._wire(mock_canvas_api)

        result = await get_tool_function('get_discussion_topic_details')("badm_350_120251", 803256)

        assert "Discussion Details" in result
        assert len(self._graphql_calls(mock_canvas_api)) == 1

    @pytest.mark.asyncio
    async def test_graphql_failure_is_explained(self, mock_canvas_api):
        self._wire(mock_canvas_api, graphql_responses=[{"errors": [{"message": "max query aliases exceeded"}]}])

        result = await get_tool_function('list_discussion_entries')("badm_350_120251", 805022)

        assert "topic 805022 exists" in result
        assert "reading it through Canvas GraphQL failed: max query aliases exceeded" in result

    @pytest.mark.asyncio
    async def test_topic_from_another_course_is_rejected(self, mock_canvas_api):
        self._wire(mock_canvas_api, graphql_responses=[self._graphql(context=("Course", "99999"))])

        result = await get_tool_function('get_discussion_with_replies')("badm_350_120251", 805022)

        assert "topic 805022 exists" in result
        assert "does not belong to course 60366" in result
        assert "deadline" not in result


    @pytest.mark.asyncio
    async def test_second_read_goes_straight_to_graphql(self, mock_canvas_api):
        self._wire(mock_canvas_api, graphql_responses=[self._graphql(), self._graphql()])
        tool = get_tool_function('get_discussion_with_replies')

        await tool("badm_350_120251", 805022, include_replies=True)
        mock_canvas_api['make_canvas_request'].reset_mock()
        mock_canvas_api['fetch_all_paginated_results'].reset_mock()
        result = await tool("badm_350_120251", 805022, include_replies=True)

        assert "📝 Entry 1 by" in result
        mock_canvas_api['fetch_all_paginated_results'].assert_not_called()
        paths = [c.args[1] for c in mock_canvas_api['make_canvas_request'].call_args_list]
        assert paths == ["/graphql"]

    @pytest.mark.asyncio
    async def test_cache_hit_serves_every_read_tool(self, mock_canvas_api):
        self._wire(mock_canvas_api, graphql_responses=[self._graphql() for _ in range(5)])
        await get_tool_function('get_discussion_topic_details')("badm_350_120251", 805022)

        for name, args in (
            ('get_discussion_topic_details', (805022,)),
            ('list_discussion_entries', (805022,)),
            ('get_discussion_entry_details', (805022, 2)),
            ('get_discussion_with_replies', (805022,)),
        ):
            mock_canvas_api['make_canvas_request'].reset_mock()
            mock_canvas_api['fetch_all_paginated_results'].reset_mock()
            result = await get_tool_function(name)("badm_350_120251", *args)
            assert "404" not in result, name
            if name == "get_discussion_entry_details":
                assert "Replies (1):" in result
                assert "Thanks!" in result
            mock_canvas_api['fetch_all_paginated_results'].assert_not_called()
            paths = [c.args[1] for c in mock_canvas_api['make_canvas_request'].call_args_list]
            assert paths == ["/graphql"], (name, paths)

    @pytest.mark.asyncio
    async def test_cache_entry_expires(self, mock_canvas_api, monkeypatch):
        from canvas_mcp.tools import discussions as discussions_module

        self._wire(mock_canvas_api, graphql_responses=[self._graphql(), self._graphql()])
        tool = get_tool_function('get_discussion_topic_details')
        await tool("badm_350_120251", 805022)

        later = discussions_module.time.monotonic() + discussions_module._UNSERVABLE_TOPIC_TTL_SECONDS + 1
        monkeypatch.setattr(discussions_module.time, "monotonic", lambda: later)
        mock_canvas_api['make_canvas_request'].reset_mock()
        await tool("badm_350_120251", 805022)

        paths = [c.args[1] for c in mock_canvas_api['make_canvas_request'].call_args_list]
        assert paths[0] != "/graphql"  # REST is tried again first
        assert paths[-1] == "/graphql"

    @pytest.mark.asyncio
    async def test_graphql_failure_on_a_cache_hit_falls_back_to_rest(self, mock_canvas_api):
        self._wire(mock_canvas_api, graphql_responses=[
            self._graphql(),
            {"errors": [{"message": "temporarily unavailable"}]},
            {"errors": [{"message": "temporarily unavailable"}]},
        ])
        tool = get_tool_function('get_discussion_topic_details')
        await tool("badm_350_120251", 805022)

        result = await tool("badm_350_120251", 805022)

        # The cached GraphQL read failed, so REST and the explanation ran again.
        assert "topic 805022 exists" in result
        assert "temporarily unavailable" in result

@pytest.mark.asyncio
async def test_anonymous_topic_graphql_fallback_through_real_client(monkeypatch, enable_discussion_graphql):
    """The fallback's GraphQL answer goes through the real client and its anonymization."""
    import httpx

    from canvas_mcp.core import client as cm
    from canvas_mcp.core.config import reset_config

    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example/api/v1")
    monkeypatch.setenv("CANVAS_API_TOKEN", "test-token")
    monkeypatch.setenv("ENABLE_DATA_ANONYMIZATION", "true")
    reset_config()
    from canvas_mcp.tools import discussions as discussions_module
    discussions_module._unservable_topics.clear()

    graphql = TestAnonymousDiscussionFallback._graphql()
    requested = []

    async def transport(request):
        requested.append((request.method, request.url.path))
        if request.url.path.endswith("/discussion_topics/805022/entries"):
            return httpx.Response(
                404, json={"errors": [{"message": "The specified resource does not exist."}]}
            )
        if request.url.path.endswith("/courses/60366/discussion_topics"):
            return httpx.Response(200, json=TestAnonymousDiscussionFallback.LISTING)
        if request.url.path == "/api/graphql":
            return httpx.Response(200, json=graphql)
        return httpx.Response(500, json={"error": "unexpected"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        with patch.object(cm, "_get_http_client", return_value=client), \
             patch('canvas_mcp.tools.discussions.get_course_id',
                   AsyncMock(return_value="60366")), \
             patch('canvas_mcp.tools.discussions.get_course_code',
                   AsyncMock(return_value="badm_350_120251")):
            result = await get_tool_function('get_discussion_with_replies')(
                "badm_350_120251", 805022, include_replies=True
            )
    reset_config()

    assert ("POST", "/api/graphql") in requested
    assert "📝 Entry 1 by" in result
    assert "Anonymous 8x6pv" in result
    # The real author name is pseudonymised by the client layer.
    assert "Teacher Name" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("setting", [None, "false", "invalid"])
@pytest.mark.parametrize("tool_name", ["get_discussion_topic_details", "list_discussion_entries", "get_discussion_with_replies", "get_discussion_entry_details"])
async def test_graphql_requires_operator_opt_in(mock_canvas_api, monkeypatch, setting, tool_name):
    from canvas_mcp.tools import discussions
    if setting is None:
        monkeypatch.delenv("DISCUSSION_GRAPHQL_ENABLED", raising=False)
    else:
        monkeypatch.setenv("DISCUSSION_GRAPHQL_ENABLED", setting)
    case = TestAnonymousDiscussionFallback()
    case._wire(mock_canvas_api)
    # Even a marker left by a previously enabled read cannot bypass the gate.
    discussions._unservable_topics[("/courses/60366", "805022")] = float("inf")
    args = ["badm_350_120251", 805022]
    if tool_name == "get_discussion_entry_details":
        args.append(2)
    result = await get_tool_function(tool_name)(*args)
    assert "topic 805022 exists" in result
    assert "Canvas UI" in result
    assert case._graphql_calls(mock_canvas_api) == []
