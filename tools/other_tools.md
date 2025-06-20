# Canvas MCP Server - Other Tools

This document provides detailed documentation for the miscellaneous tools available in the Canvas MCP server.

## Table of Contents
- [Discussion Tools](#discussion-tools)
  - [list_discussion_topics](#list_discussion_topics)
  - [get_discussion_topic_details](#get_discussion_topic_details)
  - [list_discussion_entries](#list_discussion_entries)
  - [get_discussion_entry_details](#get_discussion_entry_details)
  - [post_discussion_entry](#post_discussion_entry)
  - [reply_to_discussion_entry](#reply_to_discussion_entry)
  - [create_discussion_topic](#create_discussion_topic)
- [Announcement Tools](#announcement-tools)
  - [list_announcements](#list_announcements)
  - [create_announcement](#create_announcement)
- [Page Tools](#page-tools)
  - [list_pages](#list_pages)
  - [get_page_details](#get_page_details)
  - [get_page_content](#get_page_content)
  - [get_front_page](#get_front_page)
  - [list_module_items](#list_module_items)
- [User Tools](#user-tools)
  - [list_users](#list_users)
  - [get_user_details](#get_user_details)
- [Analytics Tools](#analytics-tools)
  - [get_student_analytics](#get_student_analytics)
  - [get_assignment_analytics](#get_assignment_analytics)

---

## Discussion Tools

### list_discussion_topics

Lists discussion topics for a specific course.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `include_announcements`: Whether to include announcements (default: False)

**Example:**
```python
# List all discussion topics
await list_discussion_topics("badm_554_120251_246794")

# Include announcements
await list_discussion_topics(12345, include_announcements=True)
```

---

### get_discussion_topic_details

Gets detailed information about a specific discussion topic.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `topic_id`: Canvas discussion topic ID

**Example:**
```python
await get_discussion_topic_details("badm_554_120251_246794", 78901)
```

---

### list_discussion_entries

Lists entries (posts) in a discussion topic.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `topic_id`: Canvas discussion topic ID

**Example:**
```python
await list_discussion_entries("badm_554_120251_246794", 78901)
```

---

### get_discussion_entry_details

Gets detailed information about a specific discussion entry.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `topic_id`: Canvas discussion topic ID
- `entry_id`: Canvas discussion entry ID

**Example:**
```python
await get_discussion_entry_details("badm_554_120251_246794", 78901, 12345)
```

---

### post_discussion_entry

Posts a new top-level entry to a discussion topic.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `topic_id`: Canvas discussion topic ID
- `message`: The message content to post

**Example:**
```python
await post_discussion_entry("badm_554_120251_246794", 78901, "This is my response to the discussion.")
```

---

### reply_to_discussion_entry

Replies to an existing discussion entry.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `topic_id`: Canvas discussion topic ID
- `entry_id`: Canvas discussion entry ID to reply to
- `message`: The reply message content

**Example:**
```python
await reply_to_discussion_entry("badm_554_120251_246794", 78901, 12345, "I agree with your point!")
```

---

### create_discussion_topic

Creates a new discussion topic.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `title`: Discussion topic title
- `message`: Initial discussion post content
- `is_announcement`: Whether this is an announcement (default: False)
- `pinned`: Whether to pin the topic (default: False)
- `locked`: Whether to lock the topic (default: False)
- `require_initial_post`: Whether users must post before seeing replies (default: False)

**Example:**
```python
await create_discussion_topic(
    "badm_554_120251_246794",
    "Weekly Discussion",
    "Let's discuss the weekly readings.",
    is_announcement=False,
    pinned=True
)
```

---

## Announcement Tools

### list_announcements

Lists announcements for a specific course.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `include_past`: Include past announcements (default: True)
- `include_future`: Include scheduled announcements (default: False)

**Example:**
```python
# List current announcements
await list_announcements("badm_554_120251_246794")

# Include past announcements
await list_announcements(12345, include_past=True)
```

---

### create_announcement

Creates a new announcement.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `title`: Announcement title
- `message`: Announcement content
- `delayed_post_at`: Schedule announcement for future (ISO 8601 format)
- `lock_at`: Automatically lock announcement at (ISO 8601 format)
- `published`: Whether to publish immediately (default: True)

**Example:**
```python
await create_announcement(
    "badm_554_120251_246794",
    "Important Update",
    "Please review the updated syllabus.",
    delayed_post_at="2024-01-15T09:00:00Z",
    published=True
)
```

---

## Page Tools

### list_pages

Lists pages in a course.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `sort`: Sort field (title, created_at, updated_at)
- `order`: Sort order (asc, desc)
- `search_term`: Filter by search term
- `published`: Filter by published status (True/False/None for all)

**Example:**
```python
# List all pages
await list_pages("badm_554_120251_246794")

# List published pages sorted by title
await list_pages(12345, sort="title", order="asc", published=True)
```

---

### get_page_details

Gets details about a specific page.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `page_url_or_id`: Page URL or ID

**Example:**
```python
await get_page_details("badm_554_120251_246794", "syllabus")
```

---

### get_page_content

Gets the content of a specific page.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `page_url_or_id`: Page URL or ID

**Example:**
```python
await get_page_content("badm_554_120251_246794", "syllabus")
```

---

### get_front_page

Gets the front page of the course.

**Parameters:**
- `course_identifier`: Canvas course code or ID

**Example:**
```python
await get_front_page("badm_554_120251_246794")
```

---

### list_module_items

Lists items in a module.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `module_id`: Canvas module ID
- `include_content_details`: Include additional item details (default: True)

**Example:**
```python
await list_module_items("badm_554_120251_246794", 12345)
```

---

## User Tools

### list_users

Lists users in a course.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `enrollment_type`: Filter by enrollment type (student, teacher, ta, etc.)
- `search_term`: Filter by name or email
- `sort`: Sort field (username, email, etc.)

**Example:**
```python
# List all users
await list_users("badm_554_120251_246794")

# List only students
await list_users(12345, enrollment_type="student")
```

---

### get_user_details

Gets details about a specific user.

**Parameters:**
- `user_id`: Canvas user ID
- `include_enrollments`: Include enrollment information (default: True)

**Example:**
```python
await get_user_details(54321)
```

---

## Analytics Tools

### get_student_analytics

Gets analytics for a specific student.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `student_id`: Canvas user ID
- `include_participation`: Include participation data (default: True)
- `include_assignments`: Include assignment data (default: True)

**Example:**
```python
await get_student_analytics("badm_554_120251_246794", 54321)
```

---

### get_assignment_analytics

Gets analytics for a specific assignment.

**Parameters:**
- `course_identifier`: Canvas course code or ID
- `assignment_id`: Canvas assignment ID
- `include_submissions`: Include submission data (default: True)

**Example:**
```python
await get_assignment_analytics("badm_554_120251_246794", 98765)
```

---

## Best Practices

1. **Error Handling**: All tools include comprehensive error handling
2. **Rate Limiting**: Respects Canvas API rate limits
3. **Caching**: Utilizes caching where appropriate for performance
4. **Pagination**: Handles pagination for large result sets
5. **Input Validation**: Validates all input parameters

## Common Error Scenarios

1. **Authentication Errors**: Check API token and permissions
2. **Not Found Errors**: Verify course, assignment, or user IDs
3. **Rate Limiting**: Tools include backoff and retry logic
4. **Network Issues**: Handles temporary network failures gracefully
