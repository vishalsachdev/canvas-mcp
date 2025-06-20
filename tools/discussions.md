# Canvas MCP Server - Discussion & Announcement Tools

This document provides detailed documentation for the discussion and announcement tools available in the Canvas MCP server.

## Table of Contents

### Discussion Tools
- [list_discussion_topics](#list_discussion_topics)
- [get_discussion_topic_details](#get_discussion_topic_details)
- [list_discussion_entries](#list_discussion_entries)
- [get_discussion_entry_details](#get_discussion_entry_details)
- [post_discussion_entry](#post_discussion_entry)
- [reply_to_discussion_entry](#reply_to_discussion_entry)
- [create_discussion_topic](#create_discussion_topic)

### Announcement Tools
- [list_announcements](#list_announcements)
- [create_announcement](#create_announcement)

---

## Discussion Tools

### list_discussion_topics

Lists discussion topics for a specific course.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code (e.g., 'badm_554_120251_246794') or ID |
| include_announcements | boolean | No | Whether to include announcements in the list (default: False) |

**Returns:**
A formatted string containing:
- Topic ID, type (Discussion/Announcement), title, status, and posting date
- Course information

**Example:**
```python
# List only discussions
await list_discussion_topics("badm_554_120251_246794")

# Include announcements in the list
await list_discussion_topics("badm_554_120251_246794", include_announcements=True)
```

**Error Handling:**
- Returns error message if course cannot be found
- Handles empty discussion lists gracefully

---

### get_discussion_topic_details

Gets detailed information about a specific discussion topic.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| topic_id | string or int | Yes | Canvas discussion topic ID |

**Returns:**
A formatted string containing:
- Topic metadata (title, ID, type, author)
- Creation and posting dates
- Discussion statistics (entry count, unread count)
- Topic settings (locked, pinned, require initial post)
- Full topic content

**Example:**
```python
await get_discussion_topic_details("badm_554_120251_246794", 12345)
```

**Error Handling:**
- Validates topic existence and accessibility
- Returns detailed error messages for API failures

---

### list_discussion_entries

Lists discussion entries (posts) for a specific discussion topic.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| topic_id | string or int | Yes | Canvas discussion topic ID |

**Returns:**
A formatted string containing:
- Entry ID, author information, posting date
- Reply count information
- Content preview (HTML stripped, truncated to 300 characters)
- Topic context information

**Example:**
```python
await list_discussion_entries("badm_554_120251_246794", 12345)
```

**Error Handling:**
- Continues operation even if topic details cannot be retrieved
- Handles HTML content cleaning and message truncation

---

### get_discussion_entry_details

Gets detailed information about a specific discussion entry including all its replies.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| topic_id | string or int | Yes | Canvas discussion topic ID |
| entry_id | string or int | Yes | Canvas discussion entry ID |

**Returns:**
A formatted string containing:
- Complete entry details (author, dates, content, read state)
- All replies with full content and metadata
- Topic context information
- Hierarchical reply structure

**Example:**
```python
await get_discussion_entry_details("badm_554_120251_246794", 12345, 67890)
```

**Error Handling:**
- Gracefully handles missing replies
- Continues with entry details if replies cannot be fetched

---

### post_discussion_entry

Posts a new top-level entry to a discussion topic.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| topic_id | string or int | Yes | Canvas discussion topic ID |
| message | string | Yes | The entry message content |

**Returns:**
A formatted confirmation message containing:
- Course and topic information
- Created entry ID and metadata
- Confirmation of posted content

**Example:**
```python
await post_discussion_entry(
    "badm_554_120251_246794", 
    12345, 
    "Great discussion topic! I think we should consider..."
)
```

**Error Handling:**
- Validates posting permissions
- Returns detailed error messages for posting failures

---

### reply_to_discussion_entry

Replies to a student's discussion entry/comment.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| topic_id | string or int | Yes | Canvas discussion topic ID |
| entry_id | string or int | Yes | Canvas discussion entry ID to reply to |
| message | string | Yes | The reply message content |

**Returns:**
A formatted confirmation message containing:
- Course information
- Original entry and reply IDs
- Message preview (truncated to 200 characters)

**Example:**
```python
await reply_to_discussion_entry(
    "badm_554_120251_246794", 
    12345, 
    67890,
    "Excellent point! You might also want to consider..."
)
```

**Error Handling:**
- Validates reply permissions and entry existence
- Provides clear error messages for failures

---

### create_discussion_topic

Creates a new discussion topic for a course.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| title | string | Yes | The title/subject of the discussion topic |
| message | string | Yes | The content/body of the discussion topic |
| delayed_post_at | string | No | ISO 8601 datetime to schedule posting |
| lock_at | string | No | ISO 8601 datetime to automatically lock |
| require_initial_post | boolean | No | Students must post before seeing others (default: False) |
| pinned | boolean | No | Whether to pin this discussion topic (default: False) |

**Returns:**
A formatted confirmation message containing:
- Course information
- Created topic ID, title, and creation date

**Example:**
```python
# Basic discussion topic
await create_discussion_topic(
    "badm_554_120251_246794",
    "Week 5 Discussion: Market Analysis", 
    "Please analyze the market trends we discussed in class..."
)

# Scheduled discussion with initial post requirement
await create_discussion_topic(
    "badm_554_120251_246794",
    "Final Project Proposals",
    "Share your final project proposal here...",
    delayed_post_at="2024-03-15T09:00:00Z",
    require_initial_post=True,
    pinned=True
)
```

**Error Handling:**
- Validates creation permissions
- Handles scheduling parameter validation

---

## Announcement Tools

### list_announcements

Lists announcements for a specific course.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string | Yes | Canvas course code or ID |

**Returns:**
A formatted string containing:
- Announcement ID, title, and posting date
- Course information

**Example:**
```python
await list_announcements("badm_554_120251_246794")
```

**Error Handling:**
- Returns error message if course cannot be found
- Handles empty announcement lists gracefully

---

### create_announcement

Creates a new announcement for a course with optional scheduling.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| course_identifier | string or int | Yes | Canvas course code or ID |
| title | string | Yes | The title/subject of the announcement |
| message | string | Yes | The content/body of the announcement |
| delayed_post_at | string | No | ISO 8601 datetime to schedule posting |
| lock_at | string | No | ISO 8601 datetime to automatically lock |

**Returns:**
A formatted confirmation message containing:
- Course information
- Created announcement ID, title, and creation date

**Example:**
```python
# Immediate announcement
await create_announcement(
    "badm_554_120251_246794",
    "Exam Reminder",
    "Don't forget about the midterm exam next Tuesday..."
)

# Scheduled announcement
await create_announcement(
    "badm_554_120251_246794",
    "Spring Break Notice",
    "The university will be closed during spring break...",
    delayed_post_at="2024-03-10T08:00:00Z",
    lock_at="2024-03-20T23:59:59Z"
)
```

**Error Handling:**
- Validates creation permissions
- Handles scheduling parameter validation

---

## Common Workflows

### Discussion Management Workflow

1. **Browse Available Discussions**
   ```python
   # See all discussions and announcements
   await list_discussion_topics(course_id, include_announcements=True)
   ```

2. **Review Student Participation**
   ```python
   # Get discussion details and entry count
   await get_discussion_topic_details(course_id, topic_id)
   
   # List all student posts
   await list_discussion_entries(course_id, topic_id)
   ```

3. **Engage with Students**
   ```python
   # Read full student post with context
   await get_discussion_entry_details(course_id, topic_id, entry_id)
   
   # Reply to student
   await reply_to_discussion_entry(course_id, topic_id, entry_id, "Great insight...")
   ```

4. **Create New Discussions**
   ```python
   # Create topic requiring initial posts
   await create_discussion_topic(
       course_id, 
       "Case Study Analysis",
       "Analyze the business case...",
       require_initial_post=True
   )
   ```

### Announcement Management Workflow

1. **Review Existing Announcements**
   ```python
   await list_announcements(course_id)
   ```

2. **Create Immediate or Scheduled Announcements**
   ```python
   # Immediate announcement
   await create_announcement(course_id, "Class Cancelled", "Today's class is cancelled...")
   
   # Scheduled announcement
   await create_announcement(
       course_id, 
       "Assignment Due Soon", 
       "Reminder: Project due Friday...",
       delayed_post_at="2024-03-13T08:00:00Z"
   )
   ```

## Best Practices

1. **Content Management**: Use HTML formatting in messages for better readability
2. **Scheduling**: Use ISO 8601 format for all datetime parameters
3. **Engagement**: Check discussion details before replying to understand context
4. **Moderation**: Use topic locking and pinning strategically
5. **Student Privacy**: Be mindful of student information when reading discussion content

## Error Scenarios

1. **Permission Issues**: Ensure API token has discussion posting/editing permissions
2. **Invalid IDs**: Verify topic and entry IDs exist and are accessible
3. **Scheduling Conflicts**: Check that scheduled times are in the future
4. **Content Formatting**: HTML content may appear differently in Canvas interface
5. **Rate Limiting**: Tools include automatic backoff for API rate limits