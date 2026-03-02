---
name: canvas-peer-review-manager
description: Educator peer review management for Canvas LMS. Tracks completion rates, analyzes comment quality, flags problematic reviews, sends targeted reminders, and generates instructor-ready reports. Trigger phrases include "peer review status", "how are peer reviews going", "who hasn't reviewed", "review quality", or any peer review follow-up task.
---

# Canvas Peer Review Manager

A complete peer review management workflow for educators using Canvas LMS. Monitor completion, analyze quality, identify students who need follow-up, send reminders, and export data -- all through MCP tool calls against the Canvas API.

## Prerequisites

- **Canvas MCP server** must be running and connected to the agent's MCP client (e.g., Claude Code, Cursor, Codex, OpenCode).
- The authenticated user must have an **educator or instructor role** in the target Canvas course.
- The assignment must have **peer reviews enabled** in Canvas (either manual or automatic assignment).
- **FERPA compliance**: Set `ENABLE_DATA_ANONYMIZATION=true` in the Canvas MCP server environment to anonymize student names. When enabled, names render as `Student_xxxxxxxx` hashes while preserving functional user IDs for messaging.

## Steps

### 1. Identify the Assignment

Ask the user which course and assignment to manage peer reviews for. Accept a course code, Canvas ID, or course name, plus an assignment name or ID.

If the user does not specify, prompt:

> Which course and assignment would you like to check peer reviews for?

Use `list_courses` and `list_assignments` to help the user find the right identifiers.

### 2. Check Peer Review Completion

Call `get_peer_review_completion_analytics` with the course identifier and assignment ID. This returns:

- Overall completion rate (percentage)
- Number of students with all reviews complete, partial, and none complete
- Per-student breakdown showing completed vs. assigned reviews

**Key data points to surface:**

| Metric | What It Tells You |
|--------|-------------------|
| Completion rate | Overall health of the peer review cycle |
| "None complete" count | Students who haven't started -- highest priority for reminders |
| "Partial complete" count | Students who started but didn't finish |
| Per-student breakdown | Exactly who needs follow-up |

### 3. Review the Assignment Mapping

If the user wants to understand who is reviewing whom, call `get_peer_review_assignments` with:

- `include_names=true` for human-readable output
- `include_submission_details=true` for submission context

This shows the full reviewer-to-reviewee mapping with completion status.

### 4. Extract and Read Comments

Call `get_peer_review_comments` to retrieve actual comment text. Parameters:

- `include_reviewer_info=true` -- who wrote the comment
- `include_reviewee_info=true` -- who received the comment
- `anonymize_students=true` -- recommended when sharing results or working with sensitive data

This reveals what students actually wrote in their reviews.

### 5. Analyze Comment Quality

Call `analyze_peer_review_quality` to generate quality metrics across all reviews. The analysis includes:

- **Average quality score** (1-5 scale)
- **Word count statistics** (mean, median, range)
- **Constructiveness analysis** (constructive feedback vs. generic comments vs. specific suggestions)
- **Sentiment distribution** (positive, neutral, negative)
- **Flagged reviews** that fall below quality thresholds

Optionally pass `analysis_criteria` as a JSON string to customize what counts as high/low quality.

### 6. Flag Problematic Reviews

Call `identify_problematic_peer_reviews` to automatically flag reviews needing instructor attention. Flagging criteria include:

- Very short or empty comments
- Generic responses (e.g., "looks good", "nice work")
- Lack of constructive feedback
- Potential copy-paste or identical reviews

Pass custom `criteria` as a JSON string to override default thresholds.

### 7. Get the Follow-up List

Call `get_peer_review_followup_list` to get a prioritized list of students requiring action:

- `priority_filter="urgent"` -- students with zero reviews completed
- `priority_filter="medium"` -- students with partial completion
- `priority_filter="all"` -- everyone who needs follow-up
- `days_threshold=3` -- adjusts urgency calculation based on days since assignment

### 8. Send Reminders

**Always use a dry run or review step before sending messages.**

For targeted reminders, call `send_peer_review_reminders` with:

- `recipient_ids` -- list of Canvas user IDs from the analytics results
- `custom_message` -- optional custom text (a default template is used if omitted)
- `subject_prefix` -- defaults to "Peer Review Reminder"

Example flow:

1. Get incomplete reviewers from step 2
2. Extract their user IDs
3. Review the recipient list with the user
4. Send reminders after confirmation

For a fully automated pipeline, call `send_peer_review_followup_campaign` with just the course identifier and assignment ID. This tool:

1. Runs completion analytics automatically
2. Segments students into "urgent" (none complete) and "partial" groups
3. Sends appropriately toned reminders to each group
4. Returns combined analytics and messaging results

**Warning:** The campaign tool sends real messages. Always confirm with the instructor before running it.

### 9. Export Data

Call `extract_peer_review_dataset` to export all peer review data for external analysis:

- `output_format="csv"` or `output_format="json"`
- `include_analytics=true` -- appends quality metrics to the export
- `anonymize_data=true` -- recommended for sharing or archival
- `save_locally=true` -- saves to a local file; set to `false` to return data inline

### 10. Generate Instructor Reports

Call `generate_peer_review_feedback_report` for a formatted, shareable report:

- `report_type="comprehensive"` -- full analysis with samples of low-quality reviews
- `report_type="summary"` -- executive overview only
- `report_type="individual"` -- per-student breakdown
- `include_student_names=false` -- recommended for FERPA compliance

For a completion-focused report (rather than quality-focused), use `generate_peer_review_report` with options for executive summary, student details, action items, and timeline analysis. This report can be saved to a file with `save_to_file=true`.

## Use Cases

**"How are peer reviews going?"**
Run steps 1-2. Present completion rate, highlight any concerning patterns (e.g., "Only 60% complete, 8 students haven't started").

**"Who hasn't done their reviews?"**
Run steps 1-2, then step 7 with `priority_filter="urgent"`. List the students who need follow-up.

**"Are the reviews any good?"**
Run steps 4-6. Present quality scores, flag generic or low-effort reviews, and surface recommendations.

**"Send reminders to stragglers"**
Run steps 1-2 to identify incomplete reviewers, then step 8. Always confirm the recipient list before sending.

**"Give me a full report"**
Run steps 2, 5, 6, and 10. Combine completion analytics with quality analysis into a comprehensive instructor report.

**"Export everything for my records"**
Run step 9 with `output_format="csv"` and `anonymize_data=true` for a FERPA-safe dataset.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `list_courses` | Discover active courses |
| `list_assignments` | Find assignments with peer reviews enabled |
| `get_peer_review_assignments` | Full reviewer-to-reviewee mapping |
| `get_peer_review_completion_analytics` | Completion rates and per-student breakdown |
| `get_peer_review_comments` | Extract actual comment text |
| `analyze_peer_review_quality` | Quality metrics (scores, word counts, constructiveness) |
| `identify_problematic_peer_reviews` | Flag low-quality or empty reviews |
| `get_peer_review_followup_list` | Prioritized list of students needing follow-up |
| `send_peer_review_reminders` | Send targeted reminder messages |
| `send_peer_review_followup_campaign` | Automated analytics-to-messaging pipeline |
| `extract_peer_review_dataset` | Export data as CSV or JSON |
| `generate_peer_review_feedback_report` | Quality-focused instructor report |
| `generate_peer_review_report` | Completion-focused instructor report |

## Example

**User:** "How are peer reviews going for Assignment 3 in BADM 350?"

**Agent:** Calls `get_peer_review_completion_analytics` and presents:

```
## Peer Review Status: Assignment 3

- **Completion rate:** 72% (23/32 students fully complete)
- **Partial:** 5 students (started but not finished)
- **Not started:** 4 students

### Students Needing Follow-up
**Not started (urgent):**
- Student_a8f7e23 (0 of 3 reviews done)
- Student_b2c91d4 (0 of 3 reviews done)
- Student_f5e67a1 (0 of 3 reviews done)
- Student_d9c34b2 (0 of 3 reviews done)

**Partial (needs nudge):**
- Student_c1d82e5 (1 of 3 reviews done)
- Student_e4f03a9 (2 of 3 reviews done)
```

**User:** "Send reminders to the ones who haven't started"

**Agent:** Confirms the 4 recipients, then calls `send_peer_review_reminders` with their user IDs.

**User:** "Now check if the completed reviews are any good"

**Agent:** Calls `analyze_peer_review_quality` and presents quality scores, flags 3 reviews as too short, and recommends the instructor follow up with specific students.

## Safety Guidelines

- **Confirm before sending** -- Always present the recipient list and message content to the instructor before calling any messaging tool.
- **Use dry runs** -- When testing workflows, start with a single recipient or confirm the output of analytics tools before acting on the data.
- **Anonymize by default** -- Use `anonymize_students=true` or `anonymize_data=true` when reviewing data in shared contexts.
- **Respect rate limits** -- The Canvas API allows roughly 700 requests per 10 minutes. For large courses, the messaging tools send messages sequentially with built-in delays.
- **FERPA compliance** -- Never display student names in logs, shared screens, or exported files unless the instructor has explicitly confirmed the context is appropriate.

## Notes

- Peer reviews must be enabled on the assignment in Canvas before any of these tools return data.
- The `send_peer_review_followup_campaign` tool combines analytics and messaging into one call -- powerful but sends real messages. Use it only after confirming intent with the instructor.
- Quality analysis uses heuristics (word count, keyword matching, sentiment). It identifies likely low-quality reviews but is not a substitute for instructor judgment.
- This skill pairs well with `canvas-morning-check` for a full course health overview that includes peer review status alongside submission rates and grade distribution.
