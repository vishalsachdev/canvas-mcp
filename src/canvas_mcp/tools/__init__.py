"""Tool modules for Canvas MCP server."""

from .courses import register_course_tools
from .assignments import register_assignment_tools
from .discussions import register_discussion_tools
from .other_tools import register_other_tools
from .rubrics import register_rubric_tools
from .peer_reviews import register_peer_review_tools

__all__ = [
    'register_course_tools',
    'register_assignment_tools',
    'register_discussion_tools',
    'register_other_tools',
    'register_rubric_tools',
    'register_peer_review_tools'
]