"""Tool modules for Canvas MCP server."""

from .accessibility import register_accessibility_tools
from .admin_tools import register_admin_tools
from .assignments import register_educator_assignment_tools, register_shared_assignment_tools
from .code_execution import register_code_execution_tools
from .courses import register_course_tools, register_shared_content_tools
from .discovery import register_discovery_tools
from .discussions import register_educator_discussion_tools, register_shared_discussion_tools
from .files import register_educator_file_tools, register_shared_file_tools
from .messaging import register_educator_messaging_tools, register_shared_messaging_tools
from .modules import register_educator_module_tools, register_shared_module_tools
from .pages import register_educator_page_crud_tools, register_page_tools
from .peer_review_comments import register_peer_review_comment_tools
from .peer_reviews import register_peer_review_tools
from .rubrics import register_rubric_tools
from .student_tools import register_student_tools

__all__ = [
    'register_accessibility_tools',
    'register_admin_tools',
    'register_code_execution_tools',
    'register_course_tools',
    'register_discovery_tools',
    'register_educator_assignment_tools',
    'register_educator_discussion_tools',
    'register_educator_file_tools',
    'register_educator_messaging_tools',
    'register_educator_module_tools',
    'register_educator_page_crud_tools',
    'register_page_tools',
    'register_peer_review_comment_tools',
    'register_peer_review_tools',
    'register_rubric_tools',
    'register_shared_assignment_tools',
    'register_shared_content_tools',
    'register_shared_discussion_tools',
    'register_shared_file_tools',
    'register_shared_messaging_tools',
    'register_shared_module_tools',
    'register_student_tools',
]
