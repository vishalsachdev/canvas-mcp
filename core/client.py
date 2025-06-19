"""HTTP client and Canvas API utilities."""

import os
import sys
from typing import Any, Dict, List, Optional, Union
import httpx

from .validation import validate_params

# Configuration
API_BASE_URL = os.environ.get("CANVAS_API_URL", "https://canvas.illinois.edu/api/v1")
API_TOKEN = os.environ.get("CANVAS_API_TOKEN", "")

# Initialize HTTP client with auth
http_client = httpx.AsyncClient(
    headers={
        'Authorization': f'Bearer {API_TOKEN}'
    },
    timeout=30.0
)


async def make_canvas_request(
    method: str, 
    endpoint: str, 
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Make a request to the Canvas API with proper error handling."""
    
    try:
        # Ensure the endpoint starts with a slash
        if not endpoint.startswith('/'):
            endpoint = f"/{endpoint}"
            
        # Construct the full URL
        url = f"{API_BASE_URL.rstrip('/')}{endpoint}"
        
        # Log the request for debugging
        print(f"Making {method.upper()} request to {url}", file=sys.stderr)
        
        if method.lower() == "get":
            response = await http_client.get(url, params=params)
        elif method.lower() == "post":
            response = await http_client.post(url, json=data)
        elif method.lower() == "put":
            response = await http_client.put(url, json=data)
        elif method.lower() == "delete":
            response = await http_client.delete(url, params=params)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        error_message = f"HTTP error: {e.response.status_code}"
        try:
            error_details = e.response.json()
            error_message += f", Details: {error_details}"
        except:
            error_details = e.response.text
            error_message += f", Text: {error_details}"
            
        print(f"API error: {error_message}", file=sys.stderr)
        return {"error": error_message}
    except Exception as e:
        print(f"Request failed: {str(e)}", file=sys.stderr)
        return {"error": f"Request failed: {str(e)}"}


async def fetch_all_paginated_results(endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Fetch all results from a paginated Canvas API endpoint."""
    if params is None:
        params = {}
    
    # Ensure we get a reasonable number per page
    if "per_page" not in params:
        params["per_page"] = 100
        
    all_results = []
    page = 1
    
    while True:
        current_params = {**params, "page": page}
        response = await make_canvas_request("get", endpoint, params=current_params)
        
        if isinstance(response, dict) and "error" in response:
            print(f"Error fetching page {page}: {response['error']}", file=sys.stderr)
            return response
            
        if not response or not isinstance(response, list) or len(response) == 0:
            break
            
        all_results.extend(response)
        
        # If we got fewer results than requested per page, we're done
        if len(response) < params.get("per_page", 100):
            break
            
        page += 1
        
    return all_results