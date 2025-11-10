# Educator Quick Start Guide

This guide shows the most common tasks educators use Canvas MCP for.

## Setup

1. Install Canvas MCP following the [README](../README.md#installation)
2. Configure your `.env` file with Canvas API token
3. **For FERPA compliance**, add:
   ```
   ENABLE_DATA_ANONYMIZATION=true
   ```
4. Restart Claude Desktop

## Common Tasks

### Check Submission Status

```
Which students haven't submitted Assignment 5 in CS 101?
```

Claude will show you who's missing submissions and help you follow up.

### Grade Assignments with Rubrics

```
I need to grade Assignment 3 in BADM 350 using the rubric
```

Claude can:
- Show you the rubric criteria
- Help you grade submissions
- Apply consistent grading across students

### Send Reminders

```
Send a reminder to students who haven't submitted the midterm project
```

Claude will:
- Identify students with missing submissions
- Draft a message
- Send it through Canvas

### Analyze Participation

```
Who hasn't participated in the Discussion 4 in my Intro to Python course?
```

Get quick insights into discussion participation.

### Bulk Operations

For large classes, use the code execution API:

```
Grade all 90 Jupyter notebook submissions for Assignment 2 by checking if they run without errors
```

This uses the bulk grading feature that's **99.7% more efficient** than traditional methods.

### Check Assignment Statistics

```
Show me statistics for Quiz 3 in ECON 102
```

Get:
- Average score
- High/low scores
- Submission rate
- Common issues

## Advanced Workflows

### Weekly Check-in

```
For CS 225, show me:
1. Who's falling behind (missing multiple assignments)
2. Discussion participation rates
3. Average grades on the latest assignment
```

### Grade Discussion with Rubric

```
Grade Discussion Topic 5 in BADM 350. Give 10 points for initial post, 5 points per peer review (must do 2), max 10 points for peer reviews.
```

Uses bulk discussion grading - super fast!

### Peer Review Analysis

```
Show me peer review completion for Assignment 4. Who hasn't done their reviews?
```

### Course Health Check

```
Give me an overview of MATH 221:
- How many students are current on assignments?
- What's the average grade?
- Who might need extra support?
```

## FERPA Compliance Tips

With `ENABLE_DATA_ANONYMIZATION=true`:
- Student names appear as "Student_xxxxxxxx"
- You can still identify patterns and get insights
- Real identities stay private from AI processing
- You keep a local mapping to correlate IDs with real students

Example anonymized output:
```
Missing submissions:
- Student_a8f7e23d (submitted 2/5 assignments)
- Student_c9b21f84 (submitted 1/5 assignments)
```

## Performance Tips

**For small operations (< 10 students):** Just ask naturally

**For bulk operations (> 30 students):** Mention you want to use code execution:
```
Use the bulk grading code API to grade all submissions for Assignment 6
```

## Common Pitfalls

❌ **Don't**: "Grade all assignments" (too vague)
✅ **Do**: "Grade Assignment 5 in CS 101 using the provided rubric"

❌ **Don't**: Send messages without reviewing
✅ **Do**: "Draft a message to students missing Assignment 3, let me review before sending"

❌ **Don't**: Assume old data is current
✅ **Do**: Canvas MCP fetches fresh data, but cache may be a few minutes old

## Troubleshooting

**"Can't access student data"**
- Check that your Canvas API token has the right permissions
- Some institutions restrict educator access - contact your Canvas admin

**"Bulk operations are slow"**
- Use the code execution API for large batches
- Mention "use bulk grading" in your request to Claude

**"Anonymization isn't working"**
- Verify `ENABLE_DATA_ANONYMIZATION=true` in your `.env`
- Restart Claude Desktop after changing settings

Need help? Check [EDUCATOR_GUIDE.md](../docs/EDUCATOR_GUIDE.md) or [open an issue](https://github.com/vishalsachdev/canvas-mcp/issues).
