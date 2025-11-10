# Student Quick Start Guide

This guide shows common tasks students can accomplish with Canvas MCP.

## Setup

1. Install Canvas MCP following the [README](../README.md#installation)
2. Make sure your `.env` file has your Canvas API token
3. Restart Claude Desktop

## Common Tasks

### Check What's Due This Week

Just ask Claude:
```
What assignments do I have due this week?
```

Claude will:
- List all upcoming assignments across all your courses
- Show due dates and times
- Indicate which ones you've already submitted

### Track Your Grades

```
Show me my current grades in all my courses
```

Claude will provide:
- Current grade in each course
- Assignment-by-assignment breakdown
- What's missing or needs attention

### Find Unsubmitted Work

```
What assignments haven't I submitted yet?
```

Perfect before deadlines! Shows everything you still need to complete.

### Peer Review Management

```
What peer reviews do I need to complete?
```

Claude will:
- List all pending peer review assignments
- Show deadlines
- Tell you how many reviews you need to do for each

### Course-Specific Questions

```
Show me everything due in BADM 350 this week
```

```
What's my current grade in CS 101?
```

```
Have I submitted all assignments for Biology 205?
```

## Tips

- **Be specific**: Mention course names or codes when relevant
- **Use natural language**: Just ask like you would ask a friend
- **Check regularly**: Make it part of your weekly routine
- **Privacy**: Your data stays on your machine - Canvas MCP never sends it elsewhere

## Common Workflows

### Monday Morning Check-in
```
What's due this week across all my courses? Show me what I've completed and what's still pending.
```

### Before Class
```
What assignments are due for MATH 221 this week?
```

### End of Semester
```
Show me my final grades in all courses and any missing assignments
```

## Troubleshooting

**"I don't see my courses"**
- Make sure your `.env` file is configured correctly
- Verify your Canvas API token is valid
- Try: `canvas-mcp-server --test`

**"Some assignments are missing"**
- Canvas MCP shows what's in Canvas - check with your professor if something seems off

**Need help?** Check the [main documentation](../README.md) or [open an issue](https://github.com/vishalsachdev/canvas-mcp/issues).
