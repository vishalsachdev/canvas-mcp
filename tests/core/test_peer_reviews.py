"""Focused tests for peer-review analytics request efficiency."""

from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.core.peer_reviews import PeerReviewAnalyzer


@pytest.mark.asyncio
async def test_completion_analytics_fetches_roster_once_and_keeps_names():
    """Removing either the single-fetch path or name reuse breaks this test."""
    assignment = {
        "id": 2,
        "name": "Review",
        "anonymous_peer_reviews": False,
        "automatic_peer_reviews": True,
        "peer_review_count": 1,
    }
    peer_reviews = [
        {
            "id": 30,
            "assessor_id": 10,
            "user_id": 20,
            "workflow_state": "assigned",
            "created_at": None,
        }
    ]
    roster = [
        {"id": 10, "name": "Reviewer Name"},
        {"id": 20, "name": "Reviewee Name"},
    ]

    with patch(
        "canvas_mcp.core.peer_reviews.make_canvas_request",
        new=AsyncMock(side_effect=[assignment, peer_reviews]),
    ), patch(
        "canvas_mcp.core.peer_reviews.fetch_all_paginated_results",
        new=AsyncMock(return_value=roster),
    ) as fetch:
        result = await PeerReviewAnalyzer().get_completion_analytics(1, 2)

    assert fetch.await_count == 1
    student = result["completion_groups"]["none_complete"][0]
    assert student["student_name"] == "Reviewer Name"
    assert student["pending_reviews"][0]["reviewee_name"] == "Reviewee Name"
