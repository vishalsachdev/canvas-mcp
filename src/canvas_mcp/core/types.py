"""Type definitions for Canvas API objects."""

from typing import Any, TypedDict


class CourseInfo(TypedDict, total=False):
    id: int | str
    name: str
    course_code: str
    start_at: str
    end_at: str
    time_zone: str
    default_view: str
    is_public: bool
    blueprint: bool


class AssignmentInfo(TypedDict, total=False):
    id: int | str
    name: str
    due_at: str | None
    points_possible: float
    submission_types: list[str]
    published: bool
    locked_for_user: bool


class PageInfo(TypedDict, total=False):
    page_id: int | str
    url: str
    title: str
    published: bool
    front_page: bool
    locked_for_user: bool
    last_edited_by: dict[str, Any]
    editing_roles: str


class AnnouncementInfo(TypedDict, total=False):
    id: int | str
    title: str
    message: str
    posted_at: str | None
    delayed_post_at: str | None
    lock_at: str | None
    published: bool
    is_announcement: bool
