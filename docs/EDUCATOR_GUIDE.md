# Canvas MCP for Educators

Welcome! This guide will help you set up Canvas MCP to enhance your teaching with AI-powered course management tools.

## What Can Canvas MCP Do for You?

Canvas MCP provides AI-powered assistance for common teaching workflows:

- **Assignment Management**: Track submissions, identify missing work, analyze completion rates
- **Grading & Rubrics**: Manage rubrics, grade submissions, provide feedback
- **Student Analytics**: Monitor student performance, identify at-risk students, track engagement
- **Peer Review Management**: Track peer review completion, analyze review quality, send reminders
- **Discussion Facilitation**: Monitor discussions, respond to students, analyze participation
- **Communication**: Send targeted messages, create announcements, automate reminders
- **FERPA Compliance**: Built-in data anonymization for AI-safe student analytics

## Prerequisites

- **Python 3.10+** installed on your computer
- **MCP Client** - Any MCP-compatible client:
  - [Claude Desktop](https://claude.ai/download) (Recommended for beginners)
  - [Cursor](https://cursor.sh) (AI code editor)
  - [Zed](https://zed.dev) (Fast code editor)
  - [Windsurf](https://codeium.com/windsurf) (AI-powered IDE)
  - [Continue](https://continue.dev) (Open-source AI assistant)
  - [Other MCP clients](https://modelcontextprotocol.io/clients)
- **Canvas Account** with instructor/TA permissions

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
5. Give it a purpose (e.g., "AI Teaching Assistant")
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
CANVAS_API_URL=https://canvas.youruniversity.edu

# MCP Server Configuration (optional)
MCP_SERVER_NAME=canvas-mcp

# Privacy Settings (IMPORTANT for FERPA compliance)
ENABLE_DATA_ANONYMIZATION=true  # Anonymizes student data before AI processing
ANONYMIZATION_DEBUG=false       # Set to true for debugging only

# Optional: Institution name for display
INSTITUTION_NAME=Your University Name
```

**Important Configuration Notes:**
- Replace `https://canvas.youruniversity.edu` with your actual Canvas URL
- **Set `ENABLE_DATA_ANONYMIZATION=true`** for FERPA-compliant student data handling
- The anonymization system converts student names to anonymous IDs (e.g., "Student_abc123") before sending data to AI

### 5. Configure Your MCP Client

Choose your MCP client and follow the appropriate configuration:

<details open>
<summary><strong>Claude Desktop</strong> (Recommended for beginners)</summary>

**Configuration file location:**
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**Add this configuration:**
```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

**macOS path example**: `/Users/yourname/canvas-mcp/.venv/bin/canvas-mcp-server`  
**Windows path example**: `C:\Users\yourname\canvas-mcp\.venv\Scripts\canvas-mcp-server.exe`

> Tip: Point your client at the absolute path to your virtualenv binary to avoid pyenv shim/path issues.

</details>

<details>
<summary><strong>Cursor</strong></summary>

**Configuration file location:**
- **macOS/Linux**: `~/.cursor/mcp_config.json`
- **Windows**: `%USERPROFILE%\.cursor\mcp_config.json`

**Configuration:**
```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

</details>

<details>
<summary><strong>Zed</strong></summary>

Add to Zed's `settings.json` (Settings menu → Open Settings):

```json
{
  "context_servers": {
    "canvas-api": {
      "command": {
        "path": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server",
        "args": []
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Windsurf IDE</strong></summary>

**Configuration file location:**
- **macOS**: `~/Library/Application Support/Windsurf/mcp_config.json`
- **Windows**: `%APPDATA%\Windsurf\mcp_config.json`

**Configuration:**
```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

</details>

<details>
<summary><strong>Continue</strong></summary>

Add to Continue's `config.json` (Continue settings):

```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

</details>

<details>
<summary><strong>Other MCP Clients</strong></summary>

For other MCP-compatible clients:

1. Locate your client's MCP configuration file
2. Add a server entry with the command path to `canvas-mcp-server`
3. Restart your client

Consult your client's documentation for specific configuration format.

</details>

### 6. Test Your Setup

```bash
# Test the Canvas API connection
canvas-mcp-server --test

# View your configuration
canvas-mcp-server --config
```

You should see: ✓ API connection successful!

### 7. Restart Your MCP Client

Close and reopen your MCP client to load the Canvas MCP server.

**Verification:**
- **Claude Desktop**: Look for the 🔨 hammer icon when you start a conversation
- **Other clients**: Check your client's documentation for how MCP tools are indicated

## FERPA Compliance & Privacy

### How Data Anonymization Works

When `ENABLE_DATA_ANONYMIZATION=true` is set, Canvas MCP automatically:

1. **Converts student names** to anonymous IDs (e.g., "John Smith" → "Student_abc123")
2. **Masks email addresses** (e.g., "john@university.edu" → "student_abc123@masked")
3. **Filters PII** from discussion posts and submissions (phone numbers, SSNs)
4. **Maintains consistency** - same student always gets the same anonymous ID
5. **Preserves relationships** - you can still identify patterns and trends

### De-Anonymization Mapping

The system creates local mapping files that let you correlate anonymous IDs with real students:

```
local_maps/
└── course_BADM_350_mapping.csv
```

This CSV file maps anonymous IDs back to real names - **keep it secure and never commit to version control**.

### Privacy Best Practices

- **Enable anonymization** - Always set `ENABLE_DATA_ANONYMIZATION=true`
- **Secure your token** - Never share or commit your Canvas API token
- **Protect mapping files** - Keep `local_maps/` folder secure (it's in `.gitignore`)
- **Local processing only** - All data stays on your machine; nothing sent to external servers
- **Review before sharing** - If sharing AI assistant conversations, ensure student data is anonymous

## How to Use Canvas MCP

### Quick Start Prompts for Educators

**Assignment Management:**
- "Which students haven't submitted Assignment 3 in BADM 350?"
- "Show me submission statistics for the latest assignment"
- "List all assignments in my Spring 2025 courses"

**Student Analytics:**
- "Which students are falling behind in BADM 350?"
- "Show me performance analytics for Assignment 5"
- "Who needs academic support based on recent grades?"

**Peer Review Management:**
- "How many students completed their peer reviews for Assignment 2?"
- "Show me peer review completion analytics"
- "Identify students who haven't completed peer reviews"
- "Analyze the quality of peer review comments"

**Grading & Rubrics:**
- "Show me the rubric for Assignment 4"
- "List all rubrics for BADM 350"
- "Create a rubric for the final project" (provide criteria)

**Discussion Facilitation:**
- "What are the active discussions in my course?"
- "Show me recent student posts in the Week 5 discussion"
- "Which students haven't participated in discussions?"

**Communication:**
- "Send a reminder to students who haven't completed peer reviews"
- "Create an announcement about tomorrow's exam"
- "Message students who are missing Assignment 3"

### Understanding Tool Calls

When you ask your AI assistant a question, it uses various "tools" to fetch data from Canvas. For educators, common tools include:

- `get_assignment_analytics` - Submission statistics and performance
- `list_submissions` - Student submission status
- `get_peer_review_completion_analytics` - Peer review tracking
- `send_peer_review_reminders` - Automated student messaging
- `list_discussion_topics` - Discussion management
- `create_rubric` - Rubric creation

> **Note**: Different MCP clients may display tool usage differently. Claude Desktop shows a 🔨 icon when using tools.

## Available Educator Tools

### Assignment Management
- **list_assignments** - View all assignments for a course
- **get_assignment_details** - Detailed assignment information
- **list_submissions** - Student submission status
- **get_assignment_analytics** - Performance and completion statistics

### Grading & Rubrics
- **create_rubric** - Create new rubrics
- **get_rubric_details** - View rubric criteria
- **associate_rubric** - Link rubric to assignment
- **grade_submission_with_rubric** - Grade using rubric

### Student Analytics
- **get_student_analytics** - Multi-dimensional performance analysis
- **identify_at_risk_students** - Flag students needing support
- **get_peer_review_completion_analytics** - Peer review tracking

### Peer Review Management
- **list_peer_reviews** - View peer review assignments
- **get_peer_review_comments** - Extract review text and metadata
- **analyze_peer_review_quality** - Quality metrics and analysis
- **identify_problematic_peer_reviews** - Flag low-quality reviews
- **assign_peer_review** - Manually assign reviews

### Communication & Messaging
- **send_conversation** - Send messages to students
- **send_peer_review_reminders** - Automated reminder workflow
- **create_announcement** - Post course announcements
- **send_peer_review_followup_campaign** - Complete analytics → messaging pipeline

### Discussion Management
- **list_discussion_topics** - View discussion forums
- **get_discussion_entry_details** - Read student posts
- **reply_to_discussion_entry** - Respond to students
- **create_discussion_topic** - Start new discussions

### Course Content
- **list_courses** - View all your courses
- **get_course_details** - Syllabus and course info
- **list_pages** - Access course pages
- **get_page_content** - Read page content

## Example Workflows

### Monday Morning Check-In
```
You: "Give me a status update on my courses"

Your AI assistant will:
1. List your active courses
2. Check recent assignment submissions
3. Identify missing work
4. Flag students needing attention
```

### After Assignment Due Date
```
You: "Assignment 3 was due Friday in BADM 350. Who hasn't submitted?"

Your AI assistant will:
1. Get submission statistics
2. List non-submitters (anonymized if enabled)
3. Suggest sending reminders
```

### Peer Review Management
```
You: "Check peer review completion for Assignment 2 in BADM 350"

Your AI assistant will:
1. Analyze completion rates
2. Identify incomplete reviews
3. Assess review quality
4. Suggest follow-up actions (reminders, manual assignments)
```

### Grading Session
```
You: "Show me the rubric for Assignment 4 and recent submissions"

Your AI assistant will:
1. Display rubric criteria
2. Show submission list
3. Help you grade efficiently
```

## Tips for Best Results

1. **Use course codes**: Be specific (e.g., "BADM 350" instead of "my course")
2. **Combine requests**: "Show submissions and analytics for Assignment 3"
3. **Ask for summaries**: "Summarize student performance in BADM 350"
4. **Leverage anonymization**: Work confidently knowing student data is protected
5. **Automate repetitive tasks**: Use messaging tools for reminders and follow-ups

## Advanced Features

### Automated Peer Review Follow-Up
```
You: "Run a peer review follow-up campaign for Assignment 2"

This will:
1. Analyze completion
2. Identify incomplete reviews
3. Send targeted reminders
4. Generate a report
```

### Student Performance Analysis
```
You: "Analyze student performance trends in BADM 350"

Your AI assistant can:
- Identify struggling students
- Track assignment completion patterns
- Suggest interventions
- Generate support lists
```

### Bulk Communication
```
You: "Message all students who haven't submitted Assignment 3"

Your AI assistant will:
- Identify non-submitters
- Draft appropriate message
- Send bulk communication
```

## Troubleshooting

### "Connection failed" or "Authentication error"
- Check your Canvas API token in `.env`
- Verify Canvas URL is correct
- Ensure token has instructor permissions

### "No students showing" or "empty results"
- Verify you have instructor/TA role in the course
- Check if students are enrolled
- Ensure assignments have submissions enabled

### Anonymization Not Working
- Set `ENABLE_DATA_ANONYMIZATION=true` in `.env`
- Restart Canvas MCP server
- Check `local_maps/` folder is created

### Need More Help?
- [Open an issue](https://github.com/vishalsachdev/canvas-mcp/issues) on GitHub
- Check the [main README](../README.md) for setup help
- Review [CLAUDE.md](./CLAUDE.md) for technical details

## Contributing

We welcome contributions! See the main [README](../README.md) for guidelines.

## Support

For questions or issues:
- GitHub Issues: [canvas-mcp/issues](https://github.com/vishalsachdev/canvas-mcp/issues)
- Documentation: See [README.md](../README.md) and [CLAUDE.md](./CLAUDE.md)

---

Happy teaching! 🎓
