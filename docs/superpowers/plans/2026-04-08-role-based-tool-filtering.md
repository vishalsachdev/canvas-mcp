# Role-Based Tool Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `CANVAS_ROLE` config option that controls which tools are registered at startup, reducing tool overhead from 91 to ~31 for students and ~86 for educators.

**Architecture:** Conditional registration via `register_all_tools(mcp, role)`. Modules with mixed shared/educator tools get split registration functions. The `other_tools.py` grab-bag is dissolved — tools move to proper category files. Default role is `all` for backwards compatibility.

**Tech Stack:** Python 3.10+, FastMCP, pytest, pytest-asyncio

---

### Task 1: Add `CANVAS_ROLE` to config

**Files:**
- Modify: `src/canvas_mcp/core/config.py`

- [ ] **Step 1: Add `canvas_role` to Config.__init__()**

In `src/canvas_mcp/core/config.py`, add after the `self.timezone` line (line 77):

```python
        # Role-based tool filtering
        self.canvas_role = os.getenv("CANVAS_ROLE", "all").lower()
```

- [ ] **Step 2: Add validation in validate_config()**

In `src/canvas_mcp/core/config.py`, add after the `ts_sandbox_mode` validation block (after line 139):

```python
    valid_roles = ("student", "educator", "all")
    if config.canvas_role not in valid_roles:
        log_warning(
            f"CANVAS_ROLE should be one of {', '.join(valid_roles)}; "
            f"defaulting to 'all' (got '{config.canvas_role}')"
        )
```

- [ ] **Step 3: Commit**

```bash
git add src/canvas_mcp/core/config.py
git commit -m "feat: add CANVAS_ROLE config option for role-based tool filtering"
```

---

### Task 2: Add `--role` CLI arg to server.py

**Files:**
- Modify: `src/canvas_mcp/server.py`

- [ ] **Step 1: Add --role argument to argparser**

In `src/canvas_mcp/server.py`, add after the `--port` argument block (after line 193):

```python
    parser.add_argument(
        "--role",
        choices=["student", "educator", "all"],
        default=None,
        help="Tool profile: student (~31 tools), educator (~86 tools), all (default: all)"
    )
```

- [ ] **Step 2: Resolve role with precedence and pass to register_all_tools**

In `src/canvas_mcp/server.py`, replace the `register_all_tools(mcp)` call at line 298 with:

```python
    # Resolve role: CLI flag > env var > default
    role = args.role or config.canvas_role
    if role not in ("student", "educator", "all"):
        log_warning(f"Unknown role '{role}', defaulting to 'all'")
        role = "all"
    log_info(f"Tool profile: {role}")
    register_all_tools(mcp, role=role)
```

- [ ] **Step 3: Add role to --config output**

In `src/canvas_mcp/server.py`, add after the `Transport` print line (line 210):

```python
        print(f"  Tool Profile: {config.canvas_role}", file=sys.stderr)
```

- [ ] **Step 4: Commit**

```bash
git add src/canvas_mcp/server.py
git commit -m "feat: add --role CLI arg for tool profile selection"
```

---

### Task 3: Split assignments.py registration

**Files:**
- Modify: `src/canvas_mcp/tools/assignments.py`

The current `register_assignment_tools()` defines 8 tools. Split into:
- `register_shared_assignment_tools()`: `list_assignments`, `get_assignment_details` (2 tools — students can see published assignments)
- `register_educator_assignment_tools()`: `assign_peer_review`, `list_peer_reviews`, `list_submissions`, `get_assignment_analytics`, `create_assignment`, `update_assignment` (6 tools)

- [ ] **Step 1: Rename and split the registration function**

In `src/canvas_mcp/tools/assignments.py`, replace:

```python
def register_assignment_tools(mcp: FastMCP):
    """Register all assignment-related MCP tools."""
```

with:

```python
def register_shared_assignment_tools(mcp: FastMCP):
    """Register assignment tools accessible to both students and educators."""
```

Then find the `assign_peer_review` tool definition (the third `@mcp.tool()` in the file, line ~94). Insert a new function boundary immediately before it:

```python

def register_educator_assignment_tools(mcp: FastMCP):
    """Register educator-only assignment tools (grading, analytics, management)."""
```

Move the closing indentation so that `list_assignments` and `get_assignment_details` are inside `register_shared_assignment_tools`, and the remaining 6 tools (`assign_peer_review`, `list_peer_reviews`, `list_submissions`, `get_assignment_analytics`, `create_assignment`, `update_assignment`) are inside `register_educator_assignment_tools`.

Both functions need the same imports — they're already at the module level so no changes needed there.

- [ ] **Step 2: Run existing assignment tests to verify no breakage**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/tools/test_assignments.py -v
```

Check which tests import `register_assignment_tools` directly. If any do, they'll need updating. If tests only call tool functions via the MCP framework, they should pass as-is after we update `__init__.py` (Task 8).

- [ ] **Step 3: Commit**

```bash
git add src/canvas_mcp/tools/assignments.py
git commit -m "refactor: split assignments.py into shared and educator registration functions"
```

---

### Task 4: Split discussions.py registration

**Files:**
- Modify: `src/canvas_mcp/tools/discussions.py`

Split into:
- `register_shared_discussion_tools()`: `list_discussion_topics`, `get_discussion_topic_details`, `list_discussion_entries`, `get_discussion_entry_details`, `get_discussion_with_replies`, `post_discussion_entry`, `reply_to_discussion_entry` (7 tools)
- `register_educator_discussion_tools()`: `create_discussion_topic`, `list_announcements`, `create_announcement`, `delete_announcement`, `bulk_delete_announcements`, `delete_announcement_with_confirmation`, `delete_announcements_by_criteria` (7 tools)

- [ ] **Step 1: Rename and split the registration function**

In `src/canvas_mcp/tools/discussions.py`, replace:

```python
def register_discussion_tools(mcp: FastMCP):
    """Register all discussion and announcement MCP tools."""
```

with:

```python
def register_shared_discussion_tools(mcp: FastMCP):
    """Register discussion tools accessible to both students and educators."""
```

Find the `create_discussion_topic` definition (line ~760). Insert before it:

```python

def register_educator_discussion_tools(mcp: FastMCP):
    """Register educator-only discussion and announcement tools."""
```

Move tools so that the first 7 (through `reply_to_discussion_entry`) are in the shared function and the remaining 7 (starting from `create_discussion_topic`) are in the educator function.

- [ ] **Step 2: Run existing discussion tests**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/tools/test_discussions.py -v
```

- [ ] **Step 3: Commit**

```bash
git add src/canvas_mcp/tools/discussions.py
git commit -m "refactor: split discussions.py into shared and educator registration functions"
```

---

### Task 5: Split modules.py registration

**Files:**
- Modify: `src/canvas_mcp/tools/modules.py`

Split into:
- `register_shared_module_tools()`: `list_modules`, `get_course_structure` (2 tools)
- `register_educator_module_tools()`: `create_module`, `update_module`, `delete_module`, `add_module_item`, `update_module_item`, `delete_module_item` (6 tools)

- [ ] **Step 1: Rename and split the registration function**

In `src/canvas_mcp/tools/modules.py`, replace:

```python
def register_module_tools(mcp: FastMCP):
    """Register all module-related MCP tools."""
```

with:

```python
def register_shared_module_tools(mcp: FastMCP):
    """Register module tools accessible to both students and educators."""
```

`list_modules` ends at line ~92. `get_course_structure` starts at line ~622 and goes to end of file. The educator tools (`create_module` through `delete_module_item`) are lines ~94-621.

Restructure so the shared function contains `list_modules` and `get_course_structure`, and the educator function contains the 6 CRUD tools in between:

```python
def register_shared_module_tools(mcp: FastMCP):
    """Register module tools accessible to both students and educators."""

    @mcp.tool()
    @validate_params
    async def list_modules(...):
        # ... existing code ...

    @mcp.tool()
    @validate_params
    async def get_course_structure(...):
        # ... existing code (moved from end of file) ...


def register_educator_module_tools(mcp: FastMCP):
    """Register educator-only module management tools."""

    @mcp.tool()
    @validate_params
    async def create_module(...):
        # ... existing code ...

    # ... update_module, delete_module, add_module_item, update_module_item, delete_module_item ...
```

- [ ] **Step 2: Run existing module tests**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/tools/test_modules.py tests/tools/test_course_structure.py -v
```

- [ ] **Step 3: Commit**

```bash
git add src/canvas_mcp/tools/modules.py
git commit -m "refactor: split modules.py into shared and educator registration functions"
```

---

### Task 6: Split files.py registration

**Files:**
- Modify: `src/canvas_mcp/tools/files.py`

Split into:
- `register_shared_file_tools()`: `list_course_files`, `download_course_file` (2 tools)
- `register_educator_file_tools()`: `upload_course_file` (1 tool)

- [ ] **Step 1: Rename and split the registration function**

In `src/canvas_mcp/tools/files.py`, replace:

```python
def register_file_tools(mcp: FastMCP):
    """Register all file-related MCP tools."""
```

with:

```python
def register_educator_file_tools(mcp: FastMCP):
    """Register educator-only file tools (upload)."""
```

Then add before the closing of the file, after `upload_course_file` but before `download_course_file`:

Actually, simpler approach — `upload_course_file` is defined first (lines 38-172), then `download_course_file` (174-242), then `list_course_files` (244-303). Restructure as:

```python
def register_shared_file_tools(mcp: FastMCP):
    """Register file tools accessible to both students and educators."""

    @mcp.tool()
    @validate_params
    async def download_course_file(...):
        # ... existing code ...

    @mcp.tool()
    @validate_params
    async def list_course_files(...):
        # ... existing code ...


def register_educator_file_tools(mcp: FastMCP):
    """Register educator-only file tools (upload)."""

    @mcp.tool()
    @validate_params
    async def upload_course_file(...):
        # ... existing code ...
```

Both functions need the same imports — already at module level.

- [ ] **Step 2: Run existing file tests**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/tools/test_files.py -v
```

- [ ] **Step 3: Commit**

```bash
git add src/canvas_mcp/tools/files.py
git commit -m "refactor: split files.py into shared and educator registration functions"
```

---

### Task 7: Split messaging.py registration

**Files:**
- Modify: `src/canvas_mcp/tools/messaging.py`

Split into:
- `register_shared_messaging_tools()`: `list_conversations`, `get_conversation_details`, `get_unread_count`, `mark_conversations_read` (4 tools)
- `register_educator_messaging_tools()`: `send_conversation`, `send_peer_review_reminders`, `send_bulk_messages_from_list`, `send_peer_review_followup_campaign` (4 tools)

- [ ] **Step 1: Rename and split the registration function**

In `src/canvas_mcp/tools/messaging.py`, replace:

```python
def register_messaging_tools(mcp: FastMCP) -> None:
    """Register all Canvas messaging tools."""
```

with:

```python
def register_shared_messaging_tools(mcp: FastMCP) -> None:
    """Register messaging tools accessible to both students and educators."""
```

The shared tools are: `list_conversations` (line ~177), `get_conversation_details` (line ~227), `get_unread_count` (line ~266), `mark_conversations_read` (line ~286).

The educator tools are: `send_conversation` (line ~17), `send_peer_review_reminders` (line ~103), `send_bulk_messages_from_list` (line ~320), `send_peer_review_followup_campaign` (line ~408).

Restructure so shared tools come first in `register_shared_messaging_tools`, then educator tools in `register_educator_messaging_tools`:

```python
def register_shared_messaging_tools(mcp: FastMCP) -> None:
    """Register messaging tools accessible to both students and educators."""

    @mcp.tool()
    @validate_params
    async def list_conversations(...):
        # ... existing code ...

    @mcp.tool()
    @validate_params
    async def get_conversation_details(...):
        # ... existing code ...

    @mcp.tool()
    @validate_params
    async def get_unread_count(...):
        # ... existing code ...

    @mcp.tool()
    @validate_params
    async def mark_conversations_read(...):
        # ... existing code ...


def register_educator_messaging_tools(mcp: FastMCP) -> None:
    """Register educator-only messaging tools (send, bulk, campaigns)."""

    @mcp.tool()
    @validate_params
    async def send_conversation(...):
        # ... existing code ...

    # ... send_peer_review_reminders, send_bulk_messages_from_list, send_peer_review_followup_campaign ...
```

- [ ] **Step 2: Run existing messaging tests**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/tools/test_messaging.py -v
```

- [ ] **Step 3: Commit**

```bash
git add src/canvas_mcp/tools/messaging.py
git commit -m "refactor: split messaging.py into shared and educator registration functions"
```

---

### Task 8: Dissolve other_tools.py

**Files:**
- Modify: `src/canvas_mcp/tools/other_tools.py` (delete after moving)
- Modify: `src/canvas_mcp/tools/courses.py` (receives shared page/module-item tools)
- Modify: `src/canvas_mcp/tools/pages.py` (receives educator page CRUD tools)
- Create: `src/canvas_mcp/tools/admin_tools.py` (receives admin/developer tools)

The 13 tools in `other_tools.py` move as follows:

**To courses.py** (shared — students can read published):
- `list_pages` (line ~20)
- `get_page_content` (line ~74)
- `get_page_details` (line ~102)
- `get_front_page` (line ~169)
- `list_module_items` (line ~381)

**To pages.py** (educator — content management):
- `create_page` (line ~195)
- `edit_page_content` (line ~248)
- `delete_page` (line ~290)

**To new admin_tools.py** (educator/developer):
- `list_groups` (line ~443)
- `list_users` (line ~508)
- `get_student_analytics` (line ~558)
- `get_anonymization_status` (line ~342)
- `create_student_anonymization_map` (line ~627)

- [ ] **Step 1: Read the full other_tools.py to get exact code**

Read the entire file to copy tools precisely.

- [ ] **Step 2: Add shared page/module tools to courses.py**

Add a new registration function to `src/canvas_mcp/tools/courses.py`:

```python
def register_shared_content_tools(mcp: FastMCP):
    """Register shared content tools (pages, module items) for both students and educators."""

    @mcp.tool()
    @validate_params
    async def list_pages(...):
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def get_page_content(...):
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def get_page_details(...):
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def get_front_page(...):
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def list_module_items(...):
        # ... exact code from other_tools.py ...
```

Add any missing imports to courses.py that these functions need (e.g., `fetch_all_paginated_results`, `format_date`).

- [ ] **Step 3: Add educator page CRUD tools to pages.py**

Add a new registration function to `src/canvas_mcp/tools/pages.py`:

```python
def register_educator_page_crud_tools(mcp: FastMCP):
    """Register educator-only page CRUD tools."""

    @mcp.tool()
    @validate_params
    async def create_page(...):
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def edit_page_content(...):
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def delete_page(...):
        # ... exact code from other_tools.py ...
```

Rename the existing `register_page_tools` to `register_educator_page_settings_tools` for clarity, or keep it and call the new one alongside it. Simplest: keep `register_page_tools` as-is and add `register_educator_page_crud_tools` as a second function. Both get called for educator role.

- [ ] **Step 4: Create admin_tools.py**

Create `src/canvas_mcp/tools/admin_tools.py`:

```python
"""Admin and developer MCP tools for Canvas API.

Provides tools for user management, group listing, student analytics,
and FERPA-compliant data anonymization.
"""

from mcp.server.fastmcp import FastMCP

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.validation import validate_params


def register_admin_tools(mcp: FastMCP):
    """Register admin/developer MCP tools."""

    @mcp.tool()
    @validate_params
    async def get_anonymization_status() -> str:
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def list_groups(...):
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def list_users(...):
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def get_student_analytics(...):
        # ... exact code from other_tools.py ...

    @mcp.tool()
    @validate_params
    async def create_student_anonymization_map(...):
        # ... exact code from other_tools.py ...
```

- [ ] **Step 5: Delete other_tools.py**

```bash
rm src/canvas_mcp/tools/other_tools.py
```

- [ ] **Step 6: Run all existing tests to check for breakage**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/ -v --tb=short 2>&1 | head -80
```

No existing tests import from `other_tools` (verified), so this should be clean.

- [ ] **Step 7: Commit**

```bash
git add src/canvas_mcp/tools/admin_tools.py src/canvas_mcp/tools/courses.py src/canvas_mcp/tools/pages.py
git rm src/canvas_mcp/tools/other_tools.py
git commit -m "refactor: dissolve other_tools.py into proper category files"
```

---

### Task 9: Update tools/__init__.py and register_all_tools()

**Files:**
- Modify: `src/canvas_mcp/tools/__init__.py`
- Modify: `src/canvas_mcp/server.py`

- [ ] **Step 1: Update __init__.py exports**

Replace the entire content of `src/canvas_mcp/tools/__init__.py`:

```python
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
    'register_course_tools',
    'register_shared_content_tools',
    'register_discovery_tools',
    'register_educator_assignment_tools',
    'register_educator_discussion_tools',
    'register_educator_file_tools',
    'register_educator_messaging_tools',
    'register_educator_module_tools',
    'register_educator_page_crud_tools',
    'register_code_execution_tools',
    'register_page_tools',
    'register_peer_review_tools',
    'register_peer_review_comment_tools',
    'register_rubric_tools',
    'register_shared_assignment_tools',
    'register_shared_discussion_tools',
    'register_shared_file_tools',
    'register_shared_messaging_tools',
    'register_shared_module_tools',
    'register_student_tools',
]
```

- [ ] **Step 2: Update server.py imports and register_all_tools()**

Replace the imports block in `src/canvas_mcp/server.py` (lines 30-46):

```python
from .resources import register_resources_and_prompts
from .tools import (
    register_accessibility_tools,
    register_admin_tools,
    register_code_execution_tools,
    register_course_tools,
    register_discovery_tools,
    register_educator_assignment_tools,
    register_educator_discussion_tools,
    register_educator_file_tools,
    register_educator_messaging_tools,
    register_educator_module_tools,
    register_educator_page_crud_tools,
    register_page_tools,
    register_peer_review_comment_tools,
    register_peer_review_tools,
    register_rubric_tools,
    register_shared_assignment_tools,
    register_shared_content_tools,
    register_shared_discussion_tools,
    register_shared_file_tools,
    register_shared_messaging_tools,
    register_shared_module_tools,
    register_student_tools,
)
```

Replace `register_all_tools` function:

```python
def register_all_tools(mcp: FastMCP, role: str = "all") -> None:
    """Register MCP tools based on the selected role profile.

    Args:
        mcp: FastMCP server instance
        role: One of "student", "educator", or "all" (default)
    """
    log_info(f"Registering Canvas MCP tools (role: {role})...")

    # Shared tools — always registered for all roles
    register_course_tools(mcp)
    register_shared_content_tools(mcp)
    register_shared_assignment_tools(mcp)
    register_shared_discussion_tools(mcp)
    register_shared_module_tools(mcp)
    register_shared_file_tools(mcp)
    register_shared_messaging_tools(mcp)
    register_discovery_tools(mcp)

    # Student-specific tools
    if role in ("student", "all"):
        register_student_tools(mcp)

    # Educator-specific tools
    if role in ("educator", "all"):
        register_educator_assignment_tools(mcp)
        register_educator_discussion_tools(mcp)
        register_educator_module_tools(mcp)
        register_educator_file_tools(mcp)
        register_page_tools(mcp)
        register_educator_page_crud_tools(mcp)
        register_rubric_tools(mcp)
        register_peer_review_tools(mcp)
        register_peer_review_comment_tools(mcp)
        register_educator_messaging_tools(mcp)
        register_accessibility_tools(mcp)
        register_code_execution_tools(mcp)
        register_admin_tools(mcp)

    # Resources and prompts — always registered
    register_resources_and_prompts(mcp)

    log_info("All Canvas MCP tools registered successfully!")
```

- [ ] **Step 3: Run full test suite**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/ -v --tb=short 2>&1 | head -100
```

- [ ] **Step 4: Commit**

```bash
git add src/canvas_mcp/tools/__init__.py src/canvas_mcp/server.py
git commit -m "feat: wire up conditional tool registration based on CANVAS_ROLE"
```

---

### Task 10: Write tests for role-based filtering

**Files:**
- Create: `tests/test_role_filtering.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_role_filtering.py`:

```python
"""Tests for role-based tool filtering."""

from unittest.mock import patch

import pytest
from mcp.server.fastmcp import FastMCP

from canvas_mcp.server import register_all_tools


def _get_tool_names(mcp: FastMCP) -> set[str]:
    """Extract registered tool names from a FastMCP instance."""
    return {tool.name for tool in mcp._tool_manager.list_tools()}


STUDENT_ONLY_TOOLS = {
    "get_my_upcoming_assignments",
    "get_my_submission_status",
    "get_my_course_grades",
    "get_my_todo_items",
    "get_my_peer_reviews_todo",
}

SHARED_TOOLS = {
    # courses
    "list_courses",
    "get_course_details",
    "get_course_content_overview",
    # shared content (pages + module items)
    "list_pages",
    "get_page_content",
    "get_page_details",
    "get_front_page",
    "list_module_items",
    # shared assignments
    "list_assignments",
    "get_assignment_details",
    # shared discussions
    "list_discussion_topics",
    "get_discussion_topic_details",
    "list_discussion_entries",
    "get_discussion_entry_details",
    "get_discussion_with_replies",
    "post_discussion_entry",
    "reply_to_discussion_entry",
    # shared modules
    "list_modules",
    "get_course_structure",
    # shared files
    "list_course_files",
    "download_course_file",
    # shared messaging
    "list_conversations",
    "get_conversation_details",
    "get_unread_count",
    "mark_conversations_read",
    # discovery
    "search_canvas_tools",
}

# A sample of educator-only tools to check (not exhaustive, just representative)
EDUCATOR_ONLY_SAMPLE = {
    "create_assignment",
    "update_assignment",
    "bulk_grade_submissions",
    "create_announcement",
    "create_module",
    "upload_course_file",
    "create_page",
    "list_users",
    "get_student_analytics",
}


class TestRoleFiltering:
    """Test that role-based filtering registers the correct tools."""

    def test_student_role_includes_student_tools(self):
        mcp = FastMCP(name="test-student")
        register_all_tools(mcp, role="student")
        tools = _get_tool_names(mcp)

        for tool in STUDENT_ONLY_TOOLS:
            assert tool in tools, f"Student role should include {tool}"

    def test_student_role_includes_shared_tools(self):
        mcp = FastMCP(name="test-student")
        register_all_tools(mcp, role="student")
        tools = _get_tool_names(mcp)

        for tool in SHARED_TOOLS:
            assert tool in tools, f"Student role should include shared tool {tool}"

    def test_student_role_excludes_educator_tools(self):
        mcp = FastMCP(name="test-student")
        register_all_tools(mcp, role="student")
        tools = _get_tool_names(mcp)

        for tool in EDUCATOR_ONLY_SAMPLE:
            assert tool not in tools, f"Student role should NOT include {tool}"

    def test_educator_role_includes_shared_tools(self):
        mcp = FastMCP(name="test-educator")
        register_all_tools(mcp, role="educator")
        tools = _get_tool_names(mcp)

        for tool in SHARED_TOOLS:
            assert tool in tools, f"Educator role should include shared tool {tool}"

    def test_educator_role_includes_educator_tools(self):
        mcp = FastMCP(name="test-educator")
        register_all_tools(mcp, role="educator")
        tools = _get_tool_names(mcp)

        for tool in EDUCATOR_ONLY_SAMPLE:
            assert tool in tools, f"Educator role should include {tool}"

    def test_educator_role_excludes_student_tools(self):
        mcp = FastMCP(name="test-educator")
        register_all_tools(mcp, role="educator")
        tools = _get_tool_names(mcp)

        for tool in STUDENT_ONLY_TOOLS:
            assert tool not in tools, f"Educator role should NOT include {tool}"

    def test_all_role_includes_everything(self):
        mcp = FastMCP(name="test-all")
        register_all_tools(mcp, role="all")
        tools = _get_tool_names(mcp)

        all_expected = STUDENT_ONLY_TOOLS | SHARED_TOOLS | EDUCATOR_ONLY_SAMPLE
        for tool in all_expected:
            assert tool in tools, f"'all' role should include {tool}"

    def test_all_role_is_default(self):
        mcp_default = FastMCP(name="test-default")
        register_all_tools(mcp_default)
        default_tools = _get_tool_names(mcp_default)

        mcp_all = FastMCP(name="test-all")
        register_all_tools(mcp_all, role="all")
        all_tools = _get_tool_names(mcp_all)

        assert default_tools == all_tools, "Default should match 'all' role"

    def test_no_tools_lost_across_roles(self):
        """Every tool in 'all' must appear in either student or educator (or both)."""
        mcp_all = FastMCP(name="test-all")
        register_all_tools(mcp_all, role="all")
        all_tools = _get_tool_names(mcp_all)

        mcp_student = FastMCP(name="test-student")
        register_all_tools(mcp_student, role="student")
        student_tools = _get_tool_names(mcp_student)

        mcp_educator = FastMCP(name="test-educator")
        register_all_tools(mcp_educator, role="educator")
        educator_tools = _get_tool_names(mcp_educator)

        combined = student_tools | educator_tools
        missing = all_tools - combined
        assert not missing, f"Tools in 'all' but missing from student+educator: {missing}"

    def test_student_tool_count(self):
        """Student role should have approximately 31 tools."""
        mcp = FastMCP(name="test-student")
        register_all_tools(mcp, role="student")
        tools = _get_tool_names(mcp)
        # Allow some flexibility as tools may be added/removed
        assert 25 <= len(tools) <= 40, f"Expected ~31 student tools, got {len(tools)}: {sorted(tools)}"

    def test_educator_tool_count(self):
        """Educator role should have approximately 86 tools."""
        mcp = FastMCP(name="test-educator")
        register_all_tools(mcp, role="educator")
        tools = _get_tool_names(mcp)
        assert 75 <= len(tools) <= 95, f"Expected ~86 educator tools, got {len(tools)}: {sorted(tools)}"
```

NOTE: The `_get_tool_names` helper accesses FastMCP internals. If `mcp._tool_manager.list_tools()` doesn't exist in the installed version, check how FastMCP exposes registered tools. Alternatives:
- `mcp.list_tools()` (if it has a public method)
- `mcp._tools` (dict of tool name -> tool)

Adjust the helper based on what FastMCP actually exposes. Run `python -c "from mcp.server.fastmcp import FastMCP; m = FastMCP('t'); print(dir(m))"` to check.

- [ ] **Step 2: Run the tests**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/test_role_filtering.py -v
```

Expected: All tests pass. If `_get_tool_names` needs adjustment, fix it based on FastMCP's API.

- [ ] **Step 3: Run full test suite to confirm nothing broke**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/ -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_role_filtering.py
git commit -m "test: add role-based tool filtering tests"
```

---

### Task 11: Update documentation

**Files:**
- Modify: `tools/TOOL_MANIFEST.json`
- Modify: `AGENTS.md` (if it exists and documents config)

- [ ] **Step 1: Update TOOL_MANIFEST.json categories**

Update the `tools` array in `tools/TOOL_MANIFEST.json` so each tool has the correct `category` reflecting our new mapping. The existing categories (`student`, `educator`, `shared`, `developer`) already match our design. Ensure all 91 tools are present with correct categories.

- [ ] **Step 2: Add CANVAS_ROLE to env.template (if exists)**

Check for `env.template` or `.env.example` and add:

```
# Tool profile: student (~31 tools), educator (~86 tools), all (default)
# CANVAS_ROLE=all
```

- [ ] **Step 3: Document in AGENTS.md**

If `AGENTS.md` has a configuration section, add a note about `CANVAS_ROLE` / `--role`.

- [ ] **Step 4: Commit**

```bash
git add tools/TOOL_MANIFEST.json AGENTS.md env.template
git commit -m "docs: update tool manifest categories and document CANVAS_ROLE config"
```

---

### Task 12: Manual smoke test

- [ ] **Step 1: Test student role**

```bash
cd D:/Projects/canvas-mcp && CANVAS_ROLE=student uv run canvas-mcp-server --config
```

Verify output shows `Tool Profile: student`.

- [ ] **Step 2: Test educator role via CLI flag**

```bash
cd D:/Projects/canvas-mcp && uv run canvas-mcp-server --role educator --config
```

Verify output shows `Tool Profile: educator`.

- [ ] **Step 3: Test CLI flag overrides env var**

```bash
cd D:/Projects/canvas-mcp && CANVAS_ROLE=student uv run canvas-mcp-server --role all --config
```

Verify output shows `Tool Profile: all` (CLI wins).

- [ ] **Step 4: Test invalid role warning**

```bash
cd D:/Projects/canvas-mcp && CANVAS_ROLE=admin uv run canvas-mcp-server --config
```

Verify warning about invalid role and fallback to `all`.

- [ ] **Step 5: Final full test run**

```bash
cd D:/Projects/canvas-mcp && uv run python -m pytest tests/ -v
```

All tests green.

- [ ] **Step 6: Commit any final fixes**

If smoke testing revealed issues, fix and commit.
