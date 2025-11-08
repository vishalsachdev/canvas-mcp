"""Calendar and event management MCP tools for Canvas API."""

import datetime

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.validation import validate_params


def register_calendar_tools(mcp: FastMCP) -> None:
    """Register all calendar and event management MCP tools."""

    @mcp.tool()
    @validate_params
    async def list_calendar_events(
        start_date: str | None = None,
        end_date: str | None = None,
        context_codes: list[str] | None = None,
        type: str | None = None
    ) -> str:
        """List calendar events for the authenticated user.

        Args:
            start_date: Start date in ISO format (YYYY-MM-DD) or relative (e.g., "today", "tomorrow")
            end_date: End date in ISO format (YYYY-MM-DD)
            context_codes: Optional list of context codes (e.g., ["course_123", "user_456"])
            type: Optional event type filter ("event" or "assignment")
        """
        params: dict = {"per_page": 100}

        # Handle relative dates
        if start_date:
            if start_date.lower() == "today":
                start_date = datetime.date.today().isoformat()
            elif start_date.lower() == "tomorrow":
                start_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            elif start_date.lower() == "this_week":
                today = datetime.date.today()
                start_date = (today - datetime.timedelta(days=today.weekday())).isoformat()
            params["start_date"] = start_date

        if end_date:
            if end_date.lower() == "today":
                end_date = datetime.date.today().isoformat()
            elif end_date.lower() == "this_week":
                today = datetime.date.today()
                end_date = (today + datetime.timedelta(days=6 - today.weekday())).isoformat()
            params["end_date"] = end_date

        if context_codes:
            params["context_codes[]"] = context_codes

        if type:
            params["type"] = type

        events = await fetch_all_paginated_results("/calendar_events", params)

        if isinstance(events, dict) and "error" in events:
            return f"Error fetching calendar events: {events['error']}"

        if not events:
            date_range = ""
            if start_date and end_date:
                date_range = f" between {start_date} and {end_date}"
            elif start_date:
                date_range = f" from {start_date}"
            elif end_date:
                date_range = f" until {end_date}"
            return f"No calendar events found{date_range}."

        events_info = []
        for event in events:
            event_id = event.get("id")
            title = event.get("title", "Untitled")
            start_at = format_date(event.get("start_at"))
            end_at = format_date(event.get("end_at"))
            location = event.get("location_name", "No location")
            description = event.get("description", "")
            event_type = event.get("type", "event")
            context_code = event.get("context_code", "")

            # Truncate description
            if description and len(description) > 100:
                description = description[:100] + "..."

            events_info.append(
                f"ID: {event_id}\n"
                f"Title: {title}\n"
                f"Type: {event_type}\n"
                f"Start: {start_at}\n"
                f"End: {end_at}\n"
                f"Location: {location}\n"
                f"Context: {context_code}\n"
                f"Description: {description}\n"
            )

        header = f"Calendar Events (Total: {len(events)}):\n\n"
        return header + "\n".join(events_info)

    @mcp.tool()
    @validate_params
    async def get_calendar_event_details(event_id: str | int) -> str:
        """Get detailed information about a specific calendar event.

        Args:
            event_id: The Canvas calendar event ID
        """
        event_id_str = str(event_id)

        response = await make_canvas_request("get", f"/calendar_events/{event_id_str}")

        if "error" in response:
            return f"Error fetching calendar event: {response['error']}"

        details = [
            f"ID: {response.get('id')}",
            f"Title: {response.get('title', 'N/A')}",
            f"Type: {response.get('type', 'event')}",
            f"Start: {format_date(response.get('start_at'))}",
            f"End: {format_date(response.get('end_at'))}",
            f"All Day: {response.get('all_day', False)}",
            f"Location: {response.get('location_name', 'N/A')}",
            f"Location Address: {response.get('location_address', 'N/A')}",
            f"Context: {response.get('context_code', 'N/A')}",
            f"Workflow State: {response.get('workflow_state', 'N/A')}",
            f"Created: {format_date(response.get('created_at'))}",
            f"Updated: {format_date(response.get('updated_at'))}",
            f"\nDescription:\n{response.get('description', 'No description')}"
        ]

        return f"Calendar Event Details:\n\n" + "\n".join(details)

    @mcp.tool()
    @validate_params
    async def create_calendar_event(
        title: str,
        start_at: str,
        end_at: str | None = None,
        description: str | None = None,
        location_name: str | None = None,
        location_address: str | None = None,
        context_code: str | None = None
    ) -> str:
        """Create a new calendar event.

        Args:
            title: Event title
            start_at: Start time in ISO format (YYYY-MM-DDTHH:MM:SSZ)
            end_at: Optional end time in ISO format
            description: Optional event description
            location_name: Optional location name
            location_address: Optional location address
            context_code: Optional context code (e.g., "course_123")
        """
        data: dict = {
            "calendar_event": {
                "title": title,
                "start_at": start_at
            }
        }

        if end_at:
            data["calendar_event"]["end_at"] = end_at

        if description:
            data["calendar_event"]["description"] = description

        if location_name:
            data["calendar_event"]["location_name"] = location_name

        if location_address:
            data["calendar_event"]["location_address"] = location_address

        if context_code:
            data["calendar_event"]["context_code"] = context_code

        response = await make_canvas_request("post", "/calendar_events", data=data)

        if "error" in response:
            return f"Error creating calendar event: {response['error']}"

        event_id = response.get("id")
        event_title = response.get("title")
        event_start = format_date(response.get("start_at"))

        return (f"Successfully created calendar event:\n"
                f"Event ID: {event_id}\n"
                f"Title: {event_title}\n"
                f"Start: {event_start}")

    @mcp.tool()
    @validate_params
    async def update_calendar_event(
        event_id: str | int,
        title: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        description: str | None = None,
        location_name: str | None = None,
        location_address: str | None = None
    ) -> str:
        """Update a calendar event.

        Args:
            event_id: The Canvas calendar event ID
            title: New event title
            start_at: New start time in ISO format
            end_at: New end time in ISO format
            description: New event description
            location_name: New location name
            location_address: New location address
        """
        event_id_str = str(event_id)

        data: dict = {"calendar_event": {}}

        if title is not None:
            data["calendar_event"]["title"] = title
        if start_at is not None:
            data["calendar_event"]["start_at"] = start_at
        if end_at is not None:
            data["calendar_event"]["end_at"] = end_at
        if description is not None:
            data["calendar_event"]["description"] = description
        if location_name is not None:
            data["calendar_event"]["location_name"] = location_name
        if location_address is not None:
            data["calendar_event"]["location_address"] = location_address

        if not data["calendar_event"]:
            return "Error: No update parameters provided"

        response = await make_canvas_request(
            "put",
            f"/calendar_events/{event_id_str}",
            data=data
        )

        if "error" in response:
            return f"Error updating calendar event: {response['error']}"

        return (f"Successfully updated calendar event {event_id}:\n"
                f"Title: {response.get('title')}\n"
                f"Start: {format_date(response.get('start_at'))}\n"
                f"End: {format_date(response.get('end_at'))}")

    @mcp.tool()
    @validate_params
    async def delete_calendar_event(event_id: str | int) -> str:
        """Delete a calendar event.

        Args:
            event_id: The Canvas calendar event ID
        """
        event_id_str = str(event_id)

        response = await make_canvas_request("delete", f"/calendar_events/{event_id_str}")

        if "error" in response:
            return f"Error deleting calendar event: {response['error']}"

        return f"Successfully deleted calendar event {event_id}"

    @mcp.tool()
    @validate_params
    async def list_course_calendar_events(
        course_identifier: str | int,
        start_date: str | None = None,
        end_date: str | None = None,
        type: str | None = None
    ) -> str:
        """List calendar events for a specific course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            start_date: Start date in ISO format (YYYY-MM-DD)
            end_date: End date in ISO format (YYYY-MM-DD)
            type: Optional event type filter ("event" or "assignment")
        """
        course_id = await get_course_id(course_identifier)

        # Use the course context code
        context_code = f"course_{course_id}"

        params: dict = {
            "per_page": 100,
            "context_codes[]": [context_code]
        }

        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if type:
            params["type"] = type

        events = await fetch_all_paginated_results("/calendar_events", params)

        if isinstance(events, dict) and "error" in events:
            return f"Error fetching calendar events: {events['error']}"

        if not events:
            course_display = await get_course_code(course_id) or course_identifier
            return f"No calendar events found for course {course_display}."

        events_info = []
        for event in events:
            event_id = event.get("id")
            title = event.get("title", "Untitled")
            start_at = format_date(event.get("start_at"))
            end_at = format_date(event.get("end_at"))
            event_type = event.get("type", "event")

            events_info.append(
                f"ID: {event_id}\n"
                f"Title: {title}\n"
                f"Type: {event_type}\n"
                f"Start: {start_at}\n"
                f"End: {end_at}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        header = f"Calendar Events for Course {course_display} (Total: {len(events)}):\n\n"
        return header + "\n".join(events_info)
