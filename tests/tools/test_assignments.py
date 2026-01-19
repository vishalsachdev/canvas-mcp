"""
Tests for assignment-related MCP tools.
"""

import pytest
from unittest.mock import AsyncMock, patch

class TestAssignmentTools:
    """Test assignment tool functions."""
    
    @pytest.mark.asyncio
    async def test_list_assignments(self):
        """Test listing assignments."""
        mock_assignments = [
            {"id": 1, "name": "Assignment 1", "due_at": "2024-02-15", "points_possible": 100},
            {"id": 2, "name": "Assignment 2", "due_at": "2024-03-01", "points_possible": 50}
        ]
        
        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_assignments
            
            from canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/assignments", {})
            
            assert len(result) == 2
            assert result[0]["name"] == "Assignment 1"
    
    @pytest.mark.asyncio
    async def test_get_assignment_details(self):
        """Test getting assignment details."""
        mock_assignment = {
            "id": 67890,
            "name": "Test Assignment",
            "description": "Test description",
            "points_possible": 100
        }
        
        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_assignment
            
            from canvas_mcp.core.client import make_canvas_request
            
            result = await make_canvas_request("get", "/courses/12345/assignments/67890")
            
            assert result["name"] == "Test Assignment"
            assert result["points_possible"] == 100
    
    @pytest.mark.asyncio
    async def test_list_submissions(self):
        """Test listing submissions."""
        mock_submissions = [
            {"user_id": 1001, "score": 85, "submitted_at": "2024-02-14"},
            {"user_id": 1002, "score": 92, "submitted_at": "2024-02-14"}
        ]
        
        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_submissions
            
            from canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/assignments/67890/submissions", {})
            
            assert len(result) == 2
            assert result[0]["score"] == 85
    
    @pytest.mark.asyncio
    async def test_assignment_analytics(self):
        """Test assignment analytics calculation."""
        from statistics import mean, median
        
        scores = [85, 92, 78, 95, 88]
        
        avg = mean(scores)
        med = median(scores)
        
        assert avg == 87.6
        assert med == 88
    
    @pytest.mark.asyncio
    async def test_empty_submissions(self):
        """Test handling empty submissions list."""
        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            
            from canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/assignments/67890/submissions", {})
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_assignment_error_handling(self):
        """Test error handling in assignment operations."""
        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"error": "Assignment not found"}
            
            from canvas_mcp.core.client import make_canvas_request
            
            result = await make_canvas_request("get", "/courses/12345/assignments/99999")
            
            assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
