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


class TestDiscussionTools:
    """Test discussion tool functions."""

    @pytest.mark.asyncio
    async def test_list_discussion_topics(self):
        """Test listing discussion topics."""
        mock_topics = [
            {"id": 1, "title": "Topic 1", "posted_at": "2024-01-15"},
            {"id": 2, "title": "Topic 2", "posted_at": "2024-01-20"}
        ]

        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_topics

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/courses/12345/discussion_topics", {})

            assert len(result) == 2
            assert result[0]["title"] == "Topic 1"

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
