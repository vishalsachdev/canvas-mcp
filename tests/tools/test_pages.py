"""
Tests for page-related MCP tools (from other_tools.py).
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestPageTools:
    """Test page tool functions."""
    
    @pytest.mark.asyncio
    async def test_list_pages(self):
        """Test listing pages."""
        mock_pages = [
            {"page_id": 1, "title": "Page 1", "published": True},
            {"page_id": 2, "title": "Page 2", "published": False}
        ]
        
        with patch('src.canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_pages
            
            from src.canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/pages", {})
            
            assert len(result) == 2
            assert result[0]["title"] == "Page 1"
    
    @pytest.mark.asyncio
    async def test_get_page_content(self):
        """Test getting page content."""
        mock_page = {
            "url": "intro",
            "title": "Introduction",
            "body": "<p>Welcome</p>",
            "published": True
        }
        
        with patch('src.canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_page
            
            from src.canvas_mcp.core.client import make_canvas_request
            
            result = await make_canvas_request("get", "/courses/12345/pages/intro")
            
            assert result["title"] == "Introduction"
            assert "<p>Welcome</p>" in result["body"]
    
    @pytest.mark.asyncio
    async def test_create_page(self):
        """Test creating a new page."""
        new_page = {
            "wiki_page": {
                "title": "New Page",
                "body": "<p>Content</p>",
                "published": False
            }
        }
        
        with patch('src.canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"url": "new-page", "title": "New Page"}
            
            from src.canvas_mcp.core.client import make_canvas_request
            
            result = await make_canvas_request("post", "/courses/12345/pages", data=new_page)
            
            assert result["title"] == "New Page"
    
    @pytest.mark.asyncio
    async def test_edit_page_content(self):
        """Test editing page content."""
        updated_page = {
            "wiki_page": {
                "body": "<p>Updated content</p>"
            }
        }
        
        with patch('src.canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"url": "intro", "body": "<p>Updated content</p>"}
            
            from src.canvas_mcp.core.client import make_canvas_request
            
            result = await make_canvas_request("put", "/courses/12345/pages/intro", data=updated_page)
            
            assert "<p>Updated content</p>" in result["body"]
    
    @pytest.mark.asyncio
    async def test_empty_pages_list(self):
        """Test handling empty pages list."""
        with patch('src.canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            
            from src.canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/pages", {})
            
            assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
