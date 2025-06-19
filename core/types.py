"""Type definitions for Canvas API objects."""

from typing import Any, Dict, List, Optional, Union, TypedDict


class CourseInfo(TypedDict, total=False):
    id: Union[int, str]
    name: str
    course_code: str
    start_at: str
    end_at: str
    time_zone: str
    default_view: str
    is_public: bool
    blueprint: bool


class AssignmentInfo(TypedDict, total=False):
    id: Union[int, str]
    name: str
    due_at: Optional[str]
    points_possible: float
    submission_types: List[str]
    published: bool
    locked_for_user: bool


class PageInfo(TypedDict, total=False):
    page_id: Union[int, str]
    url: str
    title: str
    published: bool
    front_page: bool
    locked_for_user: bool
    last_edited_by: Dict[str, Any]
    editing_roles: str


class AnnouncementInfo(TypedDict, total=False):
    id: Union[int, str]
    title: str
    message: str
    posted_at: Optional[str]
    delayed_post_at: Optional[str]
    lock_at: Optional[str]
    published: bool
    is_announcement: bool