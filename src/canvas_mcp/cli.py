"""CLI utilities for debugging and testing Canvas MCP."""

import argparse
import asyncio
import json
import sys
from typing import Any

from .core.cache import course_code_to_id_cache, id_to_course_code_cache
from .core.client import make_canvas_request
from .core.config import get_config


async def test_endpoint(endpoint: str, method: str = "get", data: dict[str, Any] | None = None) -> None:
    """Test a Canvas API endpoint.

    Args:
        endpoint: API endpoint to test
        method: HTTP method (get, post, put, delete)
        data: Optional data for POST/PUT requests
    """
    print(f"\n🔍 Testing endpoint: {method.upper()} {endpoint}")
    print("-" * 60)

    try:
        response = await make_canvas_request(method, endpoint, data=data)

        if isinstance(response, dict) and "error" in response:
            print(f"❌ Error: {response['error']}")
        else:
            print("✅ Success!")
            print("\nResponse:")
            print(json.dumps(response, indent=2)[:1000])  # Limit output
            if isinstance(response, (list, dict)):
                size = len(response)
                print(f"\n(Showing first 1000 chars. Full response has {size} items)")
    except Exception as e:
        print(f"❌ Exception: {e}")


async def list_cache_contents() -> None:
    """Display the current cache contents."""
    print("\n📦 Cache Contents")
    print("-" * 60)

    print("\nCourse Code → ID Cache:")
    if course_code_to_id_cache:
        for code, course_id in list(course_code_to_id_cache.items())[:10]:
            print(f"  {code} → {course_id}")
        if len(course_code_to_id_cache) > 10:
            print(f"  ... and {len(course_code_to_id_cache) - 10} more entries")
    else:
        print("  (empty)")

    print("\nCourse ID → Code Cache:")
    if id_to_course_code_cache:
        for course_id, code in list(id_to_course_code_cache.items())[:10]:
            print(f"  {course_id} → {code}")
        if len(id_to_course_code_cache) > 10:
            print(f"  ... and {len(id_to_course_code_cache) - 10} more entries")
    else:
        print("  (empty)")


async def check_api_health() -> None:
    """Check Canvas API health and connectivity."""
    print("\n🏥 Canvas API Health Check")
    print("-" * 60)

    # Test 1: User profile
    print("\n1. Testing user profile endpoint...")
    user_response = await make_canvas_request("get", "/users/self")
    if "error" not in user_response:
        print(f"   ✅ Connected as: {user_response.get('name', 'Unknown')}")
        print(f"   📧 Email: {user_response.get('primary_email', 'N/A')}")
        print(f"   🆔 User ID: {user_response.get('id', 'N/A')}")
    else:
        print(f"   ❌ Failed: {user_response['error']}")
        return

    # Test 2: Courses
    print("\n2. Testing courses endpoint...")
    courses_response = await make_canvas_request("get", "/courses", params={"per_page": 5})
    if isinstance(courses_response, list):
        print(f"   ✅ Found {len(courses_response)} courses (showing up to 5)")
        for course in courses_response[:3]:
            print(f"      - {course.get('name', 'Unknown')} ({course.get('course_code', 'N/A')})")
    else:
        print(f"   ❌ Failed: {courses_response.get('error', 'Unknown error')}")

    # Test 3: Rate limiting check
    print("\n3. Testing rate limiting...")
    try:
        from .core.retry import get_rate_limiter
        limiter = get_rate_limiter()
        print(f"   ✅ Rate limiter active: {limiter.current_rate} req/s")
    except Exception as e:
        print(f"   ⚠️  Warning: {e}")

    print("\n✅ Health check complete!")


async def show_config() -> None:
    """Display current configuration."""
    config = get_config()

    print("\n⚙️  Canvas MCP Configuration")
    print("-" * 60)
    print(f"Server Name:         {config.mcp_server_name}")
    print(f"Canvas API URL:      {config.canvas_api_url}")
    print(f"API Base URL:        {config.api_base_url}")
    print(f"Debug Mode:          {config.debug}")
    print(f"API Timeout:         {config.api_timeout}s")
    print(f"Cache TTL:           {config.cache_ttl}s")
    print(f"Log API Requests:    {config.log_api_requests}")
    print(f"Institution:         {config.institution_name or 'Not set'}")
    print(f"Data Anonymization:  {config.enable_data_anonymization}")
    if config.enable_data_anonymization:
        print(f"Anonymization Debug: {config.anonymization_debug}")
    print(f"API Token:           {'Set (' + config.api_token[:10] + '...)' if config.api_token else 'Not set'}")


async def validate_setup() -> bool:
    """Validate the complete setup.

    Returns:
        True if setup is valid, False otherwise
    """
    print("\n🔍 Validating Canvas MCP Setup")
    print("-" * 60)

    issues = []

    # Check config
    print("\n1. Checking configuration...")
    config = get_config()

    if not config.api_token:
        issues.append("❌ CANVAS_API_TOKEN not set")
    else:
        print("   ✅ API token configured")

    if not config.canvas_api_url:
        issues.append("❌ CANVAS_API_URL not set")
    else:
        print(f"   ✅ API URL: {config.canvas_api_url}")

    # Test connection
    print("\n2. Testing Canvas API connection...")
    try:
        user_response = await make_canvas_request("get", "/users/self")
        if "error" in user_response:
            issues.append(f"❌ API connection failed: {user_response['error']}")
        else:
            print(f"   ✅ Connected as: {user_response.get('name', 'Unknown')}")
    except Exception as e:
        issues.append(f"❌ Connection error: {e}")

    # Check tools
    print("\n3. Checking tool registration...")
    try:
        from .server import create_server, register_all_tools
        mcp = create_server()
        register_all_tools(mcp)
        print("   ✅ All tools registered successfully")
    except Exception as e:
        issues.append(f"❌ Tool registration failed: {e}")

    # Summary
    print("\n" + "=" * 60)
    if issues:
        print("❌ Setup validation FAILED with the following issues:")
        for issue in issues:
            print(f"   {issue}")
        return False
    else:
        print("✅ Setup validation PASSED!")
        print("   Your Canvas MCP server is ready to use.")
        return True


def main() -> None:
    """CLI entry point for debugging utilities."""
    parser = argparse.ArgumentParser(
        description="Canvas MCP CLI - Debugging and testing utilities"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Health check command
    subparsers.add_parser("health", help="Check Canvas API health and connectivity")

    # Config command
    subparsers.add_parser("config", help="Show current configuration")

    # Cache command
    subparsers.add_parser("cache", help="Show cache contents")

    # Validate command
    subparsers.add_parser("validate", help="Validate complete setup")

    # Test endpoint command
    test_parser = subparsers.add_parser("test", help="Test a specific API endpoint")
    test_parser.add_argument("endpoint", help="API endpoint to test (e.g., /users/self)")
    test_parser.add_argument("--method", default="get", choices=["get", "post", "put", "delete"],
                           help="HTTP method")
    test_parser.add_argument("--data", help="JSON data for POST/PUT requests")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Run the appropriate command
    if args.command == "health":
        asyncio.run(check_api_health())
    elif args.command == "config":
        asyncio.run(show_config())
    elif args.command == "cache":
        asyncio.run(list_cache_contents())
    elif args.command == "validate":
        success = asyncio.run(validate_setup())
        sys.exit(0 if success else 1)
    elif args.command == "test":
        data = json.loads(args.data) if args.data else None
        asyncio.run(test_endpoint(args.endpoint, args.method, data))


if __name__ == "__main__":
    main()
