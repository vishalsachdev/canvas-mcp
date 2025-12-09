# Canvas MCP for Students

Welcome! This guide will help you set up Canvas MCP to use Claude as your personal Canvas assistant.

## What Can Canvas MCP Do for You?

Think of this as having an AI study buddy that knows everything about your Canvas courses:

- **Track assignments**: "What's due this week?" - Get a complete view of deadlines
- **Monitor grades**: "What's my current grade in all my courses?" - Stay on top of your performance
- **Manage peer reviews**: "What peer reviews do I need to complete?" - Never miss a review
- **Access course content**: "Show me the syllabus for BADM 350" - Quick access to pages and announcements
- **Check submission status**: "Have I submitted everything?" - Know what's missing

## Prerequisites

- **Python 3.10+** installed on your computer
- **Claude Desktop** - Download from [claude.ai](https://claude.ai/download)
- **Canvas Account** at your university/institution

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/vishalsachdev/canvas-mcp.git
cd canvas-mcp
```

### 2. Install Dependencies

```bash
# Install uv package manager (faster than pip)
pip install uv

# Install Canvas MCP
uv pip install -e .
```

### 3. Get Your Canvas API Token

1. Log in to your Canvas account
2. Go to **Account** → **Settings**
3. Scroll down to **Approved Integrations**
4. Click **+ New Access Token**
5. Give it a purpose (e.g., "Claude AI Assistant")
6. Click **Generate Token**
7. **Copy the token immediately** - you won't see it again!

### 4. Configure Canvas MCP

Create a `.env` file in the `canvas-mcp` directory:

```bash
# Copy the template
cp env.template .env

# Edit the .env file and add your credentials
```

Your `.env` file should look like this:

```bash
# Canvas API Configuration
CANVAS_API_TOKEN=your_token_here
CANVAS_API_URL=https://canvas.youruniversity.edu/api/v1

# MCP Server Configuration (optional)
MCP_SERVER_NAME=canvas-mcp

# Privacy Settings (students don't need anonymization)
ENABLE_DATA_ANONYMIZATION=false
```

**Important**: Replace `https://canvas.youruniversity.edu/api/v1` with your actual Canvas URL (including the `/api/v1` suffix).

### 5. Configure Claude Desktop

Add Canvas MCP to Claude Desktop's configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "/Users/vishal/code/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

> Tip: Use the absolute path to the virtualenv binary so Claude doesn't accidentally pick up a pyenv shim or other PATH entry that lacks the package.

### 6. Test Your Setup

```bash
# Test the Canvas API connection
canvas-mcp-server --test
```

You should see: ✓ API connection successful!

### 7. Restart Claude Desktop

Close and reopen Claude Desktop. You should see the 🔨 hammer icon when you start a conversation.

## How to Use Canvas MCP

### Quick Start Prompts

Try these with Claude:

**Assignment Tracking:**
- "What assignments do I have due this week?"
- "What's coming up in the next 3 days?"
- "Show me my Canvas TODO list"

**Grade Monitoring:**
- "What are my current grades in all my courses?"
- "Show me my grades"
- "How am I doing in BADM 350?"

**Submission Status:**
- "Have I submitted all my assignments?"
- "What haven't I turned in yet?"
- "Show me my submission status for CSCI 101"

**Peer Reviews:**
- "What peer reviews do I need to complete?"
- "Show me my pending peer reviews"

**Course Content:**
- "Show me the syllabus for BADM 350"
- "What are the recent announcements?"
- "What's on the homepage for my Marketing course?"

**Discussions:**
- "What are the active discussions in HIST 202?"
- "Show me recent posts in the Week 5 discussion"

### Understanding Tool Calls

When you ask Claude a question, you'll see it use various "tools" (indicated by the 🔨 icon). These tools fetch data from Canvas. For example:

- `get_my_upcoming_assignments` - Fetches your deadlines
- `get_my_course_grades` - Gets your current grades
- `list_discussion_topics` - Shows discussion forums
- `get_page_content` - Retrieves course pages

## Available Student Tools

### Personal Organization
- **get_my_upcoming_assignments** - View assignments due soon
- **get_my_todo_items** - Your Canvas TODO list
- **get_my_submission_status** - Check what you've submitted

### Academic Performance
- **get_my_course_grades** - Current grades across all courses

### Peer Review Management
- **get_my_peer_reviews_todo** - Peer reviews you need to complete

### Course Content (Shared Tools)
- **list_courses** - See all your enrolled courses
- **get_course_details** - View syllabus and course info
- **list_pages** - Access course pages
- **get_page_content** - Read page content
- **list_announcements** - See course announcements
- **list_discussion_topics** - View discussion forums

## Privacy & Security

### Your Data Stays Private
- **Local only**: Everything runs on your computer
- **Your data only**: Tools access only YOUR Canvas data (not other students')
- **No external servers**: No data sent anywhere except Canvas (via official API)
- **Canvas API security**: Uses the same security as Canvas mobile app

### Best Practices
- **Keep your API token secret** - Don't share it or commit it to version control
- **Use a strong token purpose** - Name it clearly so you can revoke it later if needed
- **Revoke if compromised** - If you accidentally share your token, revoke it in Canvas settings

## Troubleshooting

### "Connection failed" or "Authentication error"
- Check your Canvas API token is correct in `.env`
- Verify your Canvas URL is correct (should match your browser's Canvas URL)
- Make sure your token hasn't expired (some institutions have expiration policies)

### "No tools appearing in Claude"
- Restart Claude Desktop completely (Quit → Reopen)
- Check `canvas-mcp-server --test` runs successfully
- Verify your `claude_desktop_config.json` is correct

### "No assignments/courses showing up"
- Make sure you're enrolled in courses for the current term
- Check if assignments have due dates set
- Verify your Canvas account has the appropriate permissions

### Need More Help?
- [Open an issue](https://github.com/vishalsachdev/canvas-mcp/issues) on GitHub
- Check the [main README](../README.md) for general setup help
- Review the [CLAUDE.md](./CLAUDE.md) development guide for technical details

## Example Workflows

### Morning Check-In
```
You: "Good morning! What do I need to focus on today?"

Claude will:
1. Check your upcoming assignments (next 24-48 hours)
2. Show any incomplete peer reviews
3. List recent announcements
4. Highlight your TODO items
```

### Weekly Planning
```
You: "Help me plan my week"

Claude will:
1. Show all assignments due in the next 7 days
2. Identify which courses need attention
3. Check peer review deadlines
4. Summarize your current grade status
```

### Before a Big Assignment
```
You: "I have a paper due Friday in ENGL 101. What do I need to know?"

Claude will:
1. Find the assignment details
2. Check if you've submitted
3. Show the rubric (if available)
4. Review peer review requirements (if applicable)
```

## Tips for Best Results

1. **Be specific about courses**: Use course codes (e.g., "BADM 350") when you can
2. **Ask follow-up questions**: Claude remembers context within a conversation
3. **Request summaries**: "Summarize my workload for next week"
4. **Combine requests**: "Show me my grades and what's due this week"

## What's Next?

Now that you're set up, explore what Canvas MCP can do! Try different prompts and see how Claude can help streamline your academic workflow.

Happy studying! 📚
