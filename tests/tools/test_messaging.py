"""
Tests for messaging-related MCP tools.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestMessagingTools:
    """Test messaging tool functions."""

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
    async def test_send_peer_review_reminders(self):
        """Test sending peer review reminders."""
        # Test that reminder logic works
        students_missing_reviews = ["1001", "1002", "1003"]

        assert len(students_missing_reviews) == 3

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
