---
name: canvas-discussion-facilitator
description: Discussion forum facilitator for Canvas LMS. Helps students and educators browse, read, reply to, and create discussion posts. Trigger phrases include "discussion posts", "reply to students", "check discussions", "forum participation", "post a discussion", or any discussion-related Canvas task.
---

# Canvas Discussion Facilitator

Facilitate discussion forum activity in Canvas LMS -- browse topics, read posts, reply to students, create new discussions, and monitor participation. Works for both students and educators.

## Prerequisites

- **Canvas MCP server** must be running and connected to the agent's MCP client.
- The authenticated user can have **any Canvas role** (student, TA, or instructor). Tool access is governed by Canvas API permissions.
- **FERPA compliance** (educators): Set `ENABLE_DATA_ANONYMIZATION=true` in the Canvas MCP server environment to anonymize student names in output.

## Steps

### 1. Identify the Course

Ask the user which course to work with. Accept a course code, Canvas ID, or ask them to pick from a list.

If the user does not specify, use `list_courses` to show active courses and prompt:

> Which course should I look at discussions for?

### 2. Browse Discussion Topics

Call the MCP tool `list_discussion_topics` with the course identifier to retrieve all discussion forums.

**Parameters:**
- `course_identifier` -- course code or Canvas ID
- `include_announcements` -- set to `false` (default) to see only discussions, or `true` to include announcements

**Data to surface per topic:**
- Topic ID and title
- Author name
- Posted date
- Number of entries (if available)
- Whether the topic is pinned or locked

Present the list so the user can pick a topic to drill into.

### 3. View Posts in a Discussion

Once the user selects a topic, call `list_discussion_entries` to retrieve posts.

**Parameters:**
- `course_identifier` -- course code or Canvas ID
- `topic_id` -- the selected discussion topic ID
- `include_full_content` -- set to `true` to see complete post bodies
- `include_replies` -- set to `true` to see threaded replies

**Data to surface per entry:**
- Author name
- Posted date
- Message content (or preview)
- Number of replies
- Entry ID (needed for replying)

### 4. Read a Specific Post in Full

If a post is truncated or the user wants the complete text, call `get_discussion_entry_details`.

**Parameters:**
- `course_identifier` -- course code or Canvas ID
- `topic_id` -- the discussion topic ID
- `entry_id` -- the specific entry ID
- `include_replies` -- set to `true` to also fetch all replies to this entry

Present the full post content along with any replies, timestamps, and author information.

### 5. Reply to a Post

When the user wants to respond to a specific post, call `reply_to_discussion_entry`.

**Parameters:**
- `course_identifier` -- course code or Canvas ID
- `topic_id` -- the discussion topic ID
- `entry_id` -- the entry being replied to
- `message` -- the reply content (HTML is supported)

**Before sending, always:**
1. Show the draft reply to the user for confirmation
2. Reference the original post so the user can verify context
3. Only send after explicit approval

### 6. Post a New Top-Level Entry

When the user wants to add a new post to an existing discussion (not a reply), call `post_discussion_entry`.

**Parameters:**
- `course_identifier` -- course code or Canvas ID
- `topic_id` -- the discussion topic ID
- `message` -- the post content (HTML is supported)

Show the draft to the user and confirm before posting.

### 7. Create a New Discussion Topic

When the user needs an entirely new discussion forum, call `create_discussion_topic`.

**Parameters:**
- `course_identifier` -- course code or Canvas ID
- `title` -- the discussion title
- `message` -- the opening post / prompt for the discussion
- `delayed_post_at` -- (optional) ISO 8601 datetime to schedule the discussion to appear later
- `lock_at` -- (optional) ISO 8601 datetime to automatically lock the discussion
- `require_initial_post` -- set to `true` if students must post before seeing classmates' responses
- `pinned` -- set to `true` to pin the topic to the top of the discussion list

Confirm the title, content, and any scheduling options with the user before creating.

## Educator Use Cases

### Monitor Participation

1. Call `list_discussion_topics` to get all discussion forums in the course.
2. For each topic, call `list_discussion_entries` to retrieve all posts.
3. Cross-reference posters against the class roster (use `list_users` or `list_submissions` to get enrolled students).
4. Identify students who have not posted in any active discussion.

Present participation as a summary:

```
## Discussion Participation: [Course Name]

### Topic: "Week 5 Reading Response" (due Mar 3)
- **Posted:** 28 / 32 students (88%)
- **Not posted:** Student_a1b2c3d, Student_e4f5g6h, Student_i7j8k9l, Student_m0n1o2p

### Topic: "Case Study Analysis" (due Mar 5)
- **Posted:** 15 / 32 students (47%)
- **Not posted:** [17 students listed]

### Students Missing Multiple Discussions
- Student_a1b2c3d -- missing 2 discussions
- Student_e4f5g6h -- missing 2 discussions
```

### Send Reminders About Participation

After identifying non-participants, offer to:

1. **Post an announcement** using `create_announcement` with a general reminder about discussion deadlines.
2. **Message specific students** using `send_conversation` to contact students who are behind on participation.

### Draft Thoughtful Replies

When an educator wants to reply to student posts:

1. Read the full post with `get_discussion_entry_details` (include replies for context).
2. Draft a reply that acknowledges the student's points, asks follow-up questions, or connects ideas to course material.
3. Show the draft for educator review and revision before calling `reply_to_discussion_entry`.

## Student Use Cases

### Browse and Catch Up on Discussions

1. Call `list_discussion_topics` to see all active discussions.
2. Call `list_discussion_entries` with `include_full_content=true` to read posts.
3. Summarize key themes or arguments across posts to help the student catch up quickly.

### Reply to Classmates

1. Read the target post with `get_discussion_entry_details`.
2. Help the student draft a reply that engages substantively with the original post.
3. Confirm and send via `reply_to_discussion_entry`.

### Post a New Entry

1. Review existing posts with `list_discussion_entries` to avoid duplicating points already made.
2. Help the student draft a post that adds a distinct perspective or builds on the conversation.
3. Confirm and send via `post_discussion_entry`.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `list_courses` | Find the target course |
| `list_discussion_topics` | Browse all discussion forums in a course |
| `list_discussion_entries` | View posts within a discussion topic |
| `get_discussion_entry_details` | Read a single post with full content and replies |
| `get_discussion_topic_details` | Get metadata about a discussion topic |
| `reply_to_discussion_entry` | Reply to an existing post |
| `post_discussion_entry` | Add a new top-level post to a discussion |
| `create_discussion_topic` | Create a new discussion forum |
| `create_announcement` | Post a course announcement (educator) |
| `send_conversation` | Message specific students through Canvas (educator) |
| `list_users` | Get enrolled students for participation tracking (educator) |

## Best Practices

- **Read before replying.** Always read the full post and its replies before drafting a response. This avoids repeating points and shows engagement with the conversation.
- **Check for existing similar posts.** Before posting a new entry, scan existing posts to avoid duplicating what others have already said. Build on or respectfully challenge existing arguments instead.
- **Reference specific points.** When replying, quote or paraphrase specific parts of the original post. This makes the reply more substantive and shows careful reading.
- **Confirm before sending.** Always show draft content to the user for approval before calling any write tool (`reply_to_discussion_entry`, `post_discussion_entry`, `create_discussion_topic`, `create_announcement`).
- **Respect discussion settings.** Some discussions require an initial post before viewing others (`require_initial_post`). If a student cannot see other posts, they need to post first.
- **Mind the timing.** Check `delayed_post_at` and `lock_at` dates on topics. Do not attempt to post to locked discussions.
- **Anonymization for educators.** When reviewing student participation, rely on anonymous IDs if anonymization is enabled. The Canvas MCP server preserves functional user IDs for messaging while anonymizing display names.

## Example

**User (educator):** "Show me who hasn't posted in the Week 5 discussion for CS 101."

**Agent:** Calls `list_discussion_topics` to find the Week 5 topic, then `list_discussion_entries` to get all posts, then cross-references with enrolled students. Outputs a participation summary listing students who have not posted.

**User:** "Send them a reminder."

**Agent:** Drafts a reminder message referencing the discussion deadline, shows it for confirmation, then calls `send_conversation` to message the non-participating students.

---

**User (student):** "I need to reply to Maria's post in the Case Study discussion."

**Agent:** Calls `list_discussion_topics` to find the Case Study topic, then `list_discussion_entries` to locate Maria's post, then `get_discussion_entry_details` to read the full content. Helps draft a reply that references Maria's key arguments, shows the draft for confirmation, then calls `reply_to_discussion_entry`.

## Notes

- This skill pairs well with `canvas-morning-check` for educators who want a full course status before diving into discussions.
- Discussion entries support HTML content. When drafting posts, use paragraph tags for readability but avoid overly complex markup.
- Canvas API permissions determine what each user can do. Students cannot create discussion topics unless the course allows it. Educators have full access.
- For courses with many discussions, suggest filtering by recent or pinned topics to keep the workflow focused.
