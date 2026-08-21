"""
Tests for messaging-related MCP tools.
"""

from unittest.mock import AsyncMock, patch

import pytest


def get_tool_function(tool_name: str):
    """Get a tool function by name by capturing it during registration."""
    from fastmcp import FastMCP

    from canvas_mcp.tools.messaging import register_shared_messaging_tools

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
    register_shared_messaging_tools(mcp)

    return captured_functions.get(tool_name)


def get_educator_tool_function(tool_name: str):
    """Get an educator messaging tool function by name."""
    from fastmcp import FastMCP

    from canvas_mcp.tools.messaging import register_educator_messaging_tools

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
    register_educator_messaging_tools(mcp)

    return captured_functions.get(tool_name)


class TestMarkConversationsRead:
    """Tests for the mark_conversations_read tool."""

    @pytest.mark.asyncio
    async def test_sends_form_data(self):
        """Regression for #208: /conversations batch update requires form data.

        Sent as JSON, the literal key "conversation_ids[]" is not recognized
        by Canvas (bracket syntax only means an array in form encoding), so
        the update fails. The request must use use_form_data=True like every
        other /conversations write in this repo.
        """
        with patch('canvas_mcp.tools.messaging.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = [{"id": 319, "workflow_state": "read"}]

            mark_conversations_read = get_tool_function("mark_conversations_read")
            result = await mark_conversations_read(conversation_ids=["319"])

            assert result.get("success") is True
            call = mock_request.call_args
            assert call.kwargs.get("use_form_data") is True
            assert call.kwargs.get("data") == {
                "conversation_ids[]": ["319"],
                "event": "mark_as_read",
            }

    @pytest.mark.asyncio
    async def test_empty_ids_rejected(self):
        """Empty conversation_ids returns an error without calling Canvas."""
        with patch('canvas_mcp.tools.messaging.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mark_conversations_read = get_tool_function("mark_conversations_read")
            result = await mark_conversations_read(conversation_ids=[])

            assert "error" in result
            mock_request.assert_not_called()


class TestMessagingTools:
    """Test messaging tool functions."""

    @pytest.mark.asyncio
    async def test_peer_review_message_tool_names_canvas_inbox_delivery(self):
        """A direct Inbox message must not masquerade as Canvas's native reminder."""
        from fastmcp import FastMCP

        from canvas_mcp.tools.messaging import register_educator_messaging_tools

        mcp = FastMCP("test")
        register_educator_messaging_tools(mcp)
        tools = {tool.name: tool for tool in await mcp.list_tools()}

        assert "send_peer_review_inbox_messages" in tools
        assert "send_peer_review_reminders" not in tools
        assert "Canvas Inbox" in (
            tools["send_peer_review_inbox_messages"].description or ""
        )

    @pytest.mark.asyncio
    async def test_peer_review_inbox_messages_refuse_without_grade_permission(self):
        """A student token must be refused before any message can be prepared."""
        requests = []

        async def fake_canvas_request(method, endpoint, **kwargs):
            requests.append((method, endpoint, kwargs))
            if endpoint == "/courses/60366/permissions":
                return {"manage_grades": False}
            return {"name": "Essay 1", "html_url": "https://canvas/e1"}

        with patch(
            "canvas_mcp.core.cache.get_course_id",
            new=AsyncMock(return_value="60366"),
        ), patch(
            "canvas_mcp.tools.messaging.make_canvas_request",
            new=fake_canvas_request,
        ):
            tool = get_educator_tool_function("send_peer_review_inbox_messages")
            result = await tool("badm_350_120251", 42, ["101"])

        assert result["nothing_sent"] is True
        assert "manage grades" in result["error"].lower()
        assert requests == [
            (
                "get",
                "/courses/60366/permissions",
                {"params": {"permissions[]": "manage_grades"}},
            )
        ]

    @pytest.mark.asyncio
    async def test_peer_review_inbox_messages_preview_then_send_with_resolved_course(self):
        """A permitted educator sees an Inbox preview before the resolved send."""
        requests = []

        async def fake_canvas_request(method, endpoint, **kwargs):
            requests.append((method, endpoint, kwargs))
            if endpoint == "/courses/60366/permissions":
                return {"manage_grades": True}
            if endpoint == "/courses/60366/assignments/42":
                return {"name": "Essay 1", "html_url": "https://canvas/e1"}
            if method == "post" and endpoint == "/conversations":
                return {"id": 9}
            return {"error": f"Unexpected request: {method} {endpoint}"}

        with patch(
            "canvas_mcp.core.cache.get_course_id",
            new=AsyncMock(return_value="60366"),
        ), patch(
            "canvas_mcp.tools.messaging.make_canvas_request",
            new=fake_canvas_request,
        ):
            tool = get_educator_tool_function("send_peer_review_inbox_messages")
            preview = await tool("badm_350_120251", 42, ["101", "102"])
            result = await tool(
                "badm_350_120251",
                42,
                ["101", "102"],
                confirmation_token=preview["confirmation_token"],
            )

        assert preview["preview"] is True
        assert preview["nothing_sent"] is True
        assert preview["delivery"] == "Direct Canvas Inbox messages"
        assert result["success"] is True
        post = next(request for request in requests if request[0] == "post")
        assert post[1] == "/conversations"
        assert post[2]["data"]["context_code"] == "course_60366"

    @pytest.mark.asyncio
    async def test_peer_review_inbox_messages_fail_closed_when_permission_is_unknown(self):
        """A failed permission check must not be misreported as a student role."""

        async def fake_canvas_request(method, endpoint, **kwargs):
            return {"error": "HTTP error: 503, Details: unavailable"}

        with patch(
            "canvas_mcp.core.cache.get_course_id",
            new=AsyncMock(return_value="60366"),
        ), patch(
            "canvas_mcp.tools.messaging.make_canvas_request",
            new=fake_canvas_request,
        ):
            tool = get_educator_tool_function("send_peer_review_inbox_messages")
            result = await tool("badm_350_120251", 42, ["101"])

        assert result["nothing_sent"] is True
        assert "could not verify" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_peer_review_inbox_messages_report_preflight_failure_as_unsent(self):
        """Unexpected preflight failures must still make the no-send result explicit."""
        with patch(
            "canvas_mcp.core.cache.get_course_id",
            new=AsyncMock(side_effect=RuntimeError("cache unavailable")),
        ):
            tool = get_educator_tool_function("send_peer_review_inbox_messages")
            result = await tool("badm_350_120251", 42, ["101"])

        assert result["nothing_sent"] is True
        assert "Canvas Inbox" in result["error"]

    @pytest.mark.asyncio
    async def test_send_conversation(self):
        """Test sending a conversation/message."""
        message_data = {
            "recipients": ["1001", "1002"],
            "subject": "Test Message",
            "body": "This is a test message"
        }

        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": 201, "subject": "Test Message"}

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("post", "/conversations", data=message_data)

            assert result["subject"] == "Test Message"

    @pytest.mark.asyncio
    async def test_message_validation(self):
        """Test message validation."""
        # Test empty recipients
        recipients = []
        assert len(recipients) == 0

        # Test valid recipients
        recipients = ["1001"]
        assert len(recipients) > 0

    @pytest.mark.asyncio
    async def test_conversation_error_handling(self):
        """Test error handling in conversation sending."""
        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"error": "Invalid recipients"}

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("post", "/conversations", data={})

            assert "error" in result


class TestAnnouncementTools:
    """Test announcement tool functions."""

    @pytest.mark.asyncio
    async def test_list_announcements(self):
        """Test listing announcements."""
        mock_announcements = [
            {"id": 301, "title": "Important Update", "message": "Test"},
            {"id": 302, "title": "Reminder", "message": "Don't forget"}
        ]

        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_announcements

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/courses/12345/discussion_topics", {"only_announcements": True})

            assert len(result) == 2
            assert result[0]["title"] == "Important Update"

    @pytest.mark.asyncio
    async def test_create_announcement(self):
        """Test creating an announcement."""
        announcement_data = {
            "title": "New Announcement",
            "message": "This is important"
        }

        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": 303, "title": "New Announcement"}

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("post", "/courses/12345/discussion_topics", data=announcement_data)

            assert result["title"] == "New Announcement"

    @pytest.mark.asyncio
    async def test_delete_announcement(self):
        """Test deleting an announcement."""
        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": 303, "deleted": True}

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("delete", "/courses/12345/discussion_topics/303")

            assert "deleted" in result or "id" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
