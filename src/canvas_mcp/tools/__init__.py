"""Tool modules for Canvas MCP server."""

from .courses import register_course_tools
from .assignments import register_assignment_tools
from .discussions import register_discussion_tools
from .other_tools import register_other_tools
from .rubrics import register_rubric_tools
from .peer_reviews import register_peer_review_tools
from .peer_review_comments import register_peer_review_comment_tools
from .messaging import register_messaging_tools
from .student_tools import register_student_tools
from .accessibility import register_accessibility_tools

__all__ = [
    'register_course_tools',
    'register_assignment_tools',
    'register_discussion_tools',
    'register_other_tools',
    'register_rubric_tools',
    'register_peer_review_tools',
    'register_peer_review_comment_tools',
    'register_messaging_tools',
    'register_student_tools',
    'register_accessibility_tools'
]