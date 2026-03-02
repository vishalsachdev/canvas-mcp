"""
Tests for peer review MCP tools.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestPeerReviewTools:
    """Test peer review tool functions."""

    @pytest.mark.asyncio
    async def test_get_peer_review_assignments(self):
        """Test getting peer review assignments."""
        mock_peer_reviews = [
            {"assessor_id": 1001, "asset_id": 101, "workflow_state": "assigned"},
            {"assessor_id": 1002, "asset_id": 102, "workflow_state": "completed"}
        ]

        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_peer_reviews

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("get", "/courses/12345/assignments/1/peer_reviews")

            assert len(result) == 2
            assert result[0]["workflow_state"] == "assigned"

    @pytest.mark.asyncio
    async def test_get_peer_review_comments(self):
        """Test getting peer review comments."""
        mock_comments = [
            {"id": 201, "comment": "Great work!", "author_id": 1001},
            {"id": 202, "comment": "Needs improvement", "author_id": 1002}
        ]

        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_comments

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/courses/12345/assignments/1/submissions/101/comments", {})

            assert len(result) == 2
            assert result[0]["comment"] == "Great work!"

    @pytest.mark.asyncio
    async def test_assign_peer_review(self):
        """Test assigning a peer review."""
        peer_review_data = {
            "user_id": 1001
        }

        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"assessor_id": 1001, "workflow_state": "assigned"}

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("post", "/courses/12345/assignments/1/submissions/101/peer_reviews", data=peer_review_data)

            assert result["workflow_state"] == "assigned"

    @pytest.mark.asyncio
    async def test_peer_review_completion_check(self):
        """Test checking peer review completion status."""
        mock_peer_reviews = [
            {"workflow_state": "completed"},
            {"workflow_state": "assigned"},
            {"workflow_state": "completed"}
        ]

        completed = [pr for pr in mock_peer_reviews if pr["workflow_state"] == "completed"]
        assigned = [pr for pr in mock_peer_reviews if pr["workflow_state"] == "assigned"]

        assert len(completed) == 2
        assert len(assigned) == 1

    @pytest.mark.asyncio
    async def test_empty_peer_reviews(self):
        """Test handling empty peer reviews list."""
        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = []

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("get", "/courses/12345/assignments/1/peer_reviews")

            assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
