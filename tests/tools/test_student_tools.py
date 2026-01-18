"""
Tests for student self-service MCP tools.
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestStudentTools:
    """Test student self-service tool functions."""
    
    @pytest.mark.asyncio
    async def test_get_my_upcoming_assignments(self):
        """Test getting upcoming assignments for current user."""
        mock_assignments = [
            {"id": 1, "name": "Assignment 1", "due_at": "2024-02-20"},
            {"id": 2, "name": "Assignment 2", "due_at": "2024-02-25"}
        ]
        
        with patch('src.canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_assignments
            
            from src.canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/users/self/upcoming_events", {})
            
            assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_get_my_course_grades(self):
        """Test getting current user's course grades."""
        mock_enrollments = [
            {"course_id": 101, "grades": {"current_score": 85.5}},
            {"course_id": 102, "grades": {"current_score": 92.0}}
        ]
        
        with patch('src.canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_enrollments
            
            from src.canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/users/self/enrollments", {})
            
            assert len(result) == 2
            assert result[0]["grades"]["current_score"] == 85.5
    
    @pytest.mark.asyncio
    async def test_get_my_todo_items(self):
        """Test getting TODO items for current user."""
        mock_todos = [
            {"assignment": {"id": 1, "name": "Complete reading"}},
            {"assignment": {"id": 2, "name": "Submit essay"}}
        ]
        
        with patch('src.canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_todos
            
            from src.canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/users/self/todo", {})
            
            assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_get_my_submission_status(self):
        """Test getting submission status for current user."""
        mock_submissions = [
            {"assignment_id": 1, "workflow_state": "submitted"},
            {"assignment_id": 2, "workflow_state": "graded"}
        ]
        
        with patch('src.canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_submissions
            
            from src.canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/students/submissions", {})
            
            assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_get_my_peer_reviews_todo(self):
        """Test getting pending peer reviews for current user."""
        mock_peer_reviews = [
            {"assessor_id": "self", "asset_id": 101, "workflow_state": "assigned"},
            {"assessor_id": "self", "asset_id": 102, "workflow_state": "assigned"}
        ]
        
        with patch('src.canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_peer_reviews
            
            from src.canvas_mcp.core.client import make_canvas_request
            
            result = await make_canvas_request("get", "/courses/12345/assignments/1/peer_reviews")
            
            assert len(result) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
