# Canvas MCP Skills Examples

This directory contains example Claude Skills designed to work with the Canvas MCP server. These skills demonstrate how to create high-level educational workflows on top of Canvas MCP's low-level API tools.

## What are Skills?

**Skills** are modular capabilities for Claude that provide workflow intelligence, templates, and domain expertise. They complement MCP servers by adding higher-level automation on top of low-level tools.

### Skills vs. MCP Tools

| MCP Tools | Skills |
|-----------|--------|
| Low-level API access | High-level workflows |
| User explicitly calls tools | Claude autonomously activates |
| `get_assignment_details` | `weekly-planner` uses multiple tools |
| Data retrieval | Data analysis + recommendations |
| Building blocks | Complete solutions |

**Analogy**: If MCP tools are LEGO bricks, Skills are the instruction manuals for building specific creations.

## Example Skills Included

### 1. Weekly Planner (Student Skill)
**Location**: `weekly-planner/`
**Purpose**: Autonomous weekly academic planning

**What it does**:
- Analyzes upcoming Canvas assignments
- Evaluates workload distribution
- Considers current grades
- Creates prioritized daily plan
- Provides time management strategies

**Activation**: Student says "help me plan my week"

**Key features**:
- Uses 4+ Canvas MCP tools
- Intelligent prioritization based on grades and deadlines
- Personalized time management advice
- Buffer time and workload balancing

### 2. Grading Assistant (Educator Skill)
**Location**: `grading-assistant/`
**Purpose**: Efficient, consistent rubric-based grading

**What it does**:
- Applies rubrics consistently across submissions
- Generates personalized, specific feedback
- Batch processes multiple submissions
- Identifies common patterns and errors
- Checks grading consistency

**Activation**: Educator says "help me grade these submissions"

**Key features**:
- FERPA-compliant (uses Canvas MCP anonymization)
- Multiple grading modes (individual, batch, review)
- Feedback templates and best practices
- Consistency checking

## How to Use These Skills

### Installation

1. **Locate your Skills directory**:
   ```bash
   # Default location
   ~/.claude/skills/
   ```

2. **Copy skill directories**:
   ```bash
   # Copy from Canvas MCP examples to Claude skills
   cp -r canvas-mcp/examples/skills/weekly-planner ~/.claude/skills/
   cp -r canvas-mcp/examples/skills/grading-assistant ~/.claude/skills/
   ```

3. **Verify installation**:
   Skills should be automatically detected by Claude Code/Claude Desktop

### Usage

**No explicit invocation needed!** Claude automatically activates skills based on context.

**Example**:
```
You: "Help me plan my week"

Claude (internally):
1. Recognizes weekly-planner skill is relevant
2. Activates skill instructions
3. Uses Canvas MCP tools as directed by skill
4. Generates structured weekly plan

You see: Complete weekly plan with priorities and time management
```

## Creating Your Own Skills

### Skill Structure

```
your-skill-name/
├── SKILL.md              # Main skill file (required)
├── templates/           # Optional: output templates
│   └── template.md
└── scripts/             # Optional: helper scripts
    └── helper.py
```

### SKILL.md Format

```markdown
---
name: your-skill-name
description: What this skill does and when to use it
tags: [relevant, tags]
version: 1.0.0
mcp_server: canvas-api
---

# Your Skill Name

## Purpose
Clear statement of what this skill accomplishes

## When to Activate
List of contexts/prompts that should trigger this skill

## Required MCP Tools
- `tool_name_1` - What it's used for
- `tool_name_2` - What it's used for

## Process Flow
Step-by-step workflow the skill follows

## Output Template
How the skill formats its response

## Best Practices
Guidelines for optimal results
```

### Best Practices for Skill Development

1. **Clear activation contexts**: Be specific about when skill should activate
2. **Well-defined process**: Step-by-step workflow Claude should follow
3. **Use MCP tools efficiently**: Minimize API calls, combine data intelligently
4. **Structured output**: Use templates for consistency
5. **Error handling**: Account for missing data or API failures
6. **Privacy-first**: Respect FERPA and data protection

### Testing Your Skill

1. Install in `~/.claude/skills/`
2. Test with relevant prompts
3. Verify MCP tools are called correctly
4. Check output quality and consistency
5. Iterate based on results

## Skill Ideas for Canvas MCP

### Student Skills
- `assignment-strategist` - Break down complex assignments
- `grade-analyzer` - Track academic performance trends
- `peer-review-helper` - Guide through peer review process
- `study-group-organizer` - Coordinate group work

### Educator Skills
- `rubric-designer` - Create effective rubrics
- `peer-review-facilitator` - Manage peer review workflows
- `student-support-identifier` - Identify struggling students
- `assignment-creator` - Design assignments with rubrics
- `course-health-checker` - Comprehensive course analytics

### Setup/Admin Skills
- `canvas-mcp-setup` - Guided installation and configuration
- `canvas-mcp-tutor` - Interactive capability learning

## Technical Details

### How Skills Work with Canvas MCP

1. **Skill activation**: Claude reads your message and checks skill descriptions
2. **Skill loading**: If relevant, Claude loads the SKILL.md instructions
3. **MCP tool usage**: Skill directs Claude to use specific Canvas MCP tools
4. **Data processing**: Claude analyzes data according to skill process
5. **Output generation**: Formatted response using skill templates

### Skill + MCP Architecture

```
User Request
    ↓
Claude recognizes relevant skill
    ↓
Skill provides workflow instructions
    ↓
Skill directs use of Canvas MCP tools
    ↓
Canvas MCP tools fetch data from Canvas API
    ↓
Data returns to Claude
    ↓
Skill processes data into useful output
    ↓
Structured response to user
```

### Privacy & FERPA Compliance

Skills automatically inherit Canvas MCP's privacy settings:
- `ENABLE_DATA_ANONYMIZATION=true` → Skills work with anonymized data
- All processing happens locally
- No student PII sent to AI systems
- Educators can map anonymous IDs to students locally

## Troubleshooting

### Skill not activating
- Check SKILL.md has valid YAML frontmatter
- Ensure `name` and `description` fields are present
- Verify skill is in `~/.claude/skills/` directory
- Try more explicit prompts

### Skill using wrong tools
- Review "Required MCP Tools" section
- Check that Canvas MCP server is running
- Verify tool names match Canvas MCP tools exactly

### Inconsistent output
- Add more structure to "Output Template" section
- Provide clearer process steps
- Include examples in SKILL.md

### Performance issues
- Minimize number of MCP tool calls
- Batch API requests when possible
- Consider caching strategies

## Resources

- **Canvas MCP Documentation**: `../docs/`
- **Skills Official Docs**: https://docs.claude.com/en/docs/claude-code/skills
- **Skills Repository**: https://github.com/anthropics/skills
- **Canvas API Docs**: https://canvas.instructure.com/doc/api/

## Contributing

Have a great skill idea? Contributions welcome!

1. Design your skill using the template above
2. Test thoroughly with Canvas MCP
3. Document activation contexts and workflows
4. Submit a pull request to Canvas MCP repository

## License

These example skills are released under the MIT License, same as Canvas MCP.

---

**Questions?** Open an issue at https://github.com/vishalsachdev/canvas-mcp/issues
