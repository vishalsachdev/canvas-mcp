"""
Tests for discussion-related MCP tools.
"""

from unittest.mock import AsyncMock, patch

import pytest


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
