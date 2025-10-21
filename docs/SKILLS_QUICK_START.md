# Canvas MCP Skills: Quick Start Guide

## What are Skills?

**Skills** extend Claude's capabilities by providing workflow intelligence on top of Canvas MCP tools. Think of them as "expert playbooks" that teach Claude how to handle complex educational workflows.

### 30-Second Explanation

- **Canvas MCP**: Provides low-level Canvas API tools (get assignments, post grades, etc.)
- **Skills**: Provides high-level workflows that use those tools intelligently
- **Result**: You ask Claude to "plan my week" and get a complete strategic plan, not just raw data

## Quick Start: Install Your First Skill

### Step 1: Install a Skill (2 minutes)

```bash
# Navigate to Claude's skills directory
cd ~/.claude/skills/

# Copy the weekly planner skill
cp -r /path/to/canvas-mcp/examples/skills/weekly-planner ./

# That's it! The skill is installed.
```

### Step 2: Use the Skill (Immediate)

Just talk to Claude naturally:

```
You: "Help me plan my week"

Claude: [Automatically uses weekly-planner skill]
- Fetches your Canvas assignments
- Analyzes your grades
- Checks peer reviews
- Creates prioritized daily plan
- Provides time management tips
```

**No special commands needed.** Claude recognizes when to use the skill and activates it automatically.

## Available Skills

### For Students

#### Weekly Planner
**What**: Creates personalized weekly study plans
**Install**: Copy `examples/skills/weekly-planner`
**Use**: "Help me plan my week"

**You get**:
- Daily task breakdown
- Priority tiers (critical, important, upcoming)
- Time estimates
- Workload balancing
- Strategic recommendations

### For Educators

#### Grading Assistant
**What**: Efficient rubric-based grading with feedback
**Install**: Copy `examples/skills/grading-assistant`
**Use**: "Help me grade these submissions"

**You get**:
- Consistent rubric application
- Personalized feedback for each student
- Batch processing of submissions
- Common error identification
- Grading consistency checks

**Privacy**: FERPA-compliant, uses Canvas MCP anonymization

## Skills vs. Direct Tool Usage

### Without Skills (Manual Tool Usage)

```
You: "What should I work on this week?"

Claude: [Uses individual tools]
1. Fetches assignments → shows list
2. You analyze the list yourself
3. You create your own plan
```

### With Skills (Intelligent Workflow)

```
You: "What should I work on this week?"

Claude: [Activates weekly-planner skill]
1. Fetches assignments
2. Fetches grades
3. Checks peer reviews
4. Analyzes workload distribution
5. Prioritizes based on your situation
6. Creates structured daily plan
7. Provides strategic advice

You get: Complete actionable plan, not just data
```

## How Skills Work

```
Your message
    ↓
Claude checks: "Is there a relevant skill?"
    ↓
YES → Loads skill instructions
    ↓
Skill guides Claude through workflow:
    - Which MCP tools to use
    - How to analyze the data
    - How to structure output
    - What advice to provide
    ↓
You receive: Complete, structured solution
```

## Installing More Skills

### From Examples Directory

```bash
# List available example skills
ls canvas-mcp/examples/skills/

# Install a skill
cp -r canvas-mcp/examples/skills/[skill-name] ~/.claude/skills/
```

### Verify Installation

```bash
# Check installed skills
ls ~/.claude/skills/

# You should see your skill directories
```

Claude automatically detects skills in this directory. No restart needed!

## Creating Your Own Skill

### Minimum Viable Skill

1. **Create directory**: `~/.claude/skills/my-skill/`

2. **Create SKILL.md**:
```markdown
---
name: my-skill
description: What this skill does
---

# My Skill

## Purpose
What this skill accomplishes

## When to Activate
When users ask about [X]

## Process
1. Use Canvas MCP tool [tool-name]
2. Analyze the data
3. Provide [specific output]
```

3. **Test it**: Say something that matches "When to Activate"

### Full Tutorial

See `examples/skills/README.md` for complete skill development guide.

## Best Practices

### For Students

✅ **Do**:
- Use skills for weekly planning: "Plan my week"
- Ask for assignment help: "Help me with this assignment"
- Check status: "What do I need to do?"

❌ **Don't**:
- Try to manually invoke skills (they're automatic)
- Use overly generic prompts like "help" (be specific)

### For Educators

✅ **Do**:
- Enable anonymization: `ENABLE_DATA_ANONYMIZATION=true`
- Use batch grading: "Grade all submissions for Assignment 3"
- Review suggestions before finalizing

❌ **Don't**:
- Disable anonymization when working with student data
- Blindly accept all suggestions (you're still in charge)

## Troubleshooting

### "Skill doesn't seem to activate"

**Check**:
1. Is skill in `~/.claude/skills/`?
2. Does SKILL.md have proper YAML frontmatter?
3. Does your prompt match "When to Activate"?

**Fix**: Try more explicit prompts that clearly match skill's purpose

### "Getting raw data instead of analysis"

**Likely**: Skill isn't activating, Claude is using tools directly

**Fix**:
1. Verify skill installation
2. Use prompts that match skill's description
3. Example: "Plan my week" instead of "Show assignments"

### "Skill uses wrong tools"

**Check**: Does your skill's "Required MCP Tools" section list correct tool names?

**Fix**: Match tool names exactly to Canvas MCP tools (see `tools/README.md`)

## Examples

### Example 1: Student Weekly Planning

```
You: "I have a lot going on. Help me figure out what to do first."

Claude: [Activates weekly-planner skill]

📅 Your Weekly Plan

Week at a Glance
- Total Assignments Due: 7
- Peer Reviews Due: 2
- Busiest Day: Thursday

🎯 Priority Overview

🔴 Critical (Do First)
1. CSCI 101 Programming Assignment
   Due: Tomorrow at 11:59 PM
   Points: 100 (15% of grade)
   Time needed: 3-4 hours

[... complete structured plan ...]
```

### Example 2: Educator Grading

```
You: "Help me grade the essay submissions for ENGL 101"

Claude: [Activates grading-assistant skill]

Grading Assistant Ready

Assignment: Essay 1 - Rhetorical Analysis
Submissions: 28
Rubric: 4 criteria, 5 levels each

[For each submission, provides:]
- Rubric scores with reasoning
- Specific, personalized feedback
- Consistency checks

[After batch:]
- Common strengths and weaknesses
- Grade distribution
- Suggestions for future assignments
```

## What's Next?

### Students
1. Install `weekly-planner` skill
2. Try: "Help me plan my week"
3. Explore other student workflows
4. Consider creating your own skills

### Educators
1. Install `grading-assistant` skill
2. Configure: `ENABLE_DATA_ANONYMIZATION=true`
3. Try: "Help me grade [assignment]"
4. Explore rubric and analytics skills

### Everyone
- Read full analysis: `docs/SKILLS_IMPROVEMENT_ANALYSIS.md`
- Browse examples: `examples/skills/`
- Check skill development guide: `examples/skills/README.md`
- Share your skill ideas: GitHub issues

## Resources

- **Skills Examples**: `examples/skills/`
- **Full Analysis**: `docs/SKILLS_IMPROVEMENT_ANALYSIS.md`
- **Canvas MCP Tools**: `tools/README.md`
- **Claude Skills Docs**: https://docs.claude.com/en/docs/claude-code/skills

## Get Help

- **Canvas MCP Issues**: https://github.com/vishalsachdev/canvas-mcp/issues
- **Skills Questions**: Open a GitHub discussion
- **General Claude Support**: https://support.anthropic.com

---

**Ready to supercharge your Canvas experience?** Install your first skill and try it out!
