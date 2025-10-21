---
name: weekly-planner
description: Analyzes Canvas assignments, grades, and peer reviews to create personalized weekly study plans for students
tags: [student, planning, time-management, assignments]
version: 1.0.0
mcp_server: canvas-api
author: Canvas MCP Team
---

# Weekly Planner Skill

## Purpose
Help students strategically plan their academic week by analyzing Canvas deadlines, evaluating workload distribution, considering current grades, and creating a prioritized action plan.

## When to Activate
Activate this skill when students ask about:
- "Help me plan my week"
- "What should I focus on this week?"
- "How should I organize my Canvas work?"
- "I have a lot due, where should I start?"
- Weekly academic planning
- Time management for assignments
- Prioritizing Canvas work

## Required MCP Tools
This skill uses the following Canvas MCP tools:
- `get_my_upcoming_assignments` - Fetch assignments due in the next 7-10 days
- `get_my_course_grades` - Get current grades to inform priorities
- `get_my_peer_reviews_todo` - Check for pending peer reviews
- `get_my_todo_items` - Canvas TODO list items

## Process Flow

### Step 1: Data Collection
1. Call `get_my_upcoming_assignments` with 7-10 day window
2. Call `get_my_course_grades` to understand current standing
3. Call `get_my_peer_reviews_todo` to identify review deadlines
4. Call `get_my_todo_items` for other Canvas tasks

### Step 2: Analysis
Analyze the collected data:

**Assignment Prioritization Factors:**
- Due date urgency (days until due)
- Point value / weight in course
- Current grade in the course (prioritize courses where grade needs improvement)
- Assignment complexity (infer from title/description)
- Peer review requirements

**Workload Distribution:**
- Identify "heavy" days with multiple deadlines
- Check for clustering of major assignments
- Note weekends vs. weekdays
- Identify buffer days for revision

**Risk Assessment:**
- Courses with lower grades need more attention
- High-point assignments require more time
- Peer reviews often forgotten - flag prominently
- TODO items may indicate missing/late work

### Step 3: Plan Creation
Create a structured weekly plan with:

**Daily Breakdown:**
- Specific assignments to work on each day
- Estimated time needed (be realistic)
- Mix of subjects to avoid fatigue
- Built-in buffer time

**Priority Tiers:**
- 🔴 Critical: Due in 0-2 days or high-point assignments
- 🟡 Important: Due in 3-5 days or moderate-point assignments
- 🟢 Upcoming: Due in 6+ days or low-point assignments

**Strategic Recommendations:**
- Which courses need extra attention (based on grades)
- When to start major assignments
- Time management tips specific to the week
- Suggestions for breaking down large assignments

### Step 4: Output Formatting
Use the template below to structure the response.

## Output Template

```markdown
# 📅 Your Weekly Plan

## Week at a Glance
**Period**: [Start Date] - [End Date]
**Total Assignments Due**: [Number]
**Courses with Deadlines**: [List]
**Peer Reviews Due**: [Number]

---

## 🎯 Priority Overview

### 🔴 Critical (Do First)
1. **[Assignment Name]** - [Course Code]
   - Due: [Date/Time]
   - Points: [X points / Y% of grade]
   - Why critical: [Due soon / High points / Struggling in this course]
   - Time needed: [Estimated hours]

[Repeat for all critical items]

### 🟡 Important (This Week)
[Similar format for important items]

### 🟢 Upcoming (Plan Ahead)
[Similar format for upcoming items]

---

## 📆 Day-by-Day Breakdown

### Monday [Date]
**Focus**: [Theme for the day]
- [ ] [Specific task] ([Time estimate])
- [ ] [Specific task] ([Time estimate])
**Evening check-in**: [What to verify]

### Tuesday [Date]
[Similar format]

[Continue for each day]

---

## 💡 Strategic Recommendations

### Courses Needing Extra Attention
- **[Course Name]**: [Current grade] - [Specific recommendation]

### Time Management Tips for This Week
- [Specific tip based on workload analysis]
- [Specific tip based on deadline clustering]
- [Specific tip based on assignment types]

### Getting Ahead
[Suggestions for work beyond this week]

---

## ⚠️ Important Reminders
- [ ] [Peer review deadline]
- [ ] [Major assignment starting point]
- [ ] [Study group or office hours opportunities]

---

## 📊 Workload Assessment
**This week's workload**: [Light / Moderate / Heavy / Very Heavy]
**Busiest days**: [List]
**Recommended start**: [Key assignment to begin early]

**Remember**: This is a flexible guide. Adjust as needed based on how your week unfolds!
```

## Best Practices

### Time Estimation
- Reading/research: 1-2 hours per chapter/article
- Writing assignments: 2-4 hours per page (including research)
- Problem sets: 1-3 hours depending on difficulty
- Peer reviews: 30-60 minutes per review
- Discussion posts: 30-45 minutes including reading

### Cognitive Load Management
- Don't schedule more than 4-6 hours of coursework per day
- Mix different types of tasks (reading, writing, problems)
- Include breaks between major tasks
- Front-load the week when possible

### Buffer Time
- Always include 20-30% buffer for unexpected issues
- Don't plan work on every single day
- Keep one "flex day" for catching up

### Grade-Based Prioritization
- Courses with grades below target need more attention
- High-weight assignments deserve proportional time
- Consider cumulative vs. non-cumulative grading

## Common Patterns to Recognize

**Pattern: End-of-Unit Clustering**
When: Multiple assignments due same day/week
Response: Recommend starting earliest assignment immediately, stagger work

**Pattern: Peer Review Chain**
When: Assignment submission + peer review both upcoming
Response: Highlight submission deadline, remind that peer review comes after

**Pattern: Reading-Heavy Week**
When: Multiple reading assignments
Response: Suggest active reading strategies, spread across multiple days

**Pattern: Low Grade + High-Point Assignment**
When: Important assignment in a struggling course
Response: Flag as critical, suggest office hours, extra time allocation

## Conversation Examples

### Example 1: Standard Weekly Planning

**Student**: "Help me plan my week"

**Skill Process**:
1. Fetch assignments (finds 5 assignments, due various days)
2. Fetch grades (finds 3.2 in MATH, 3.7 in others)
3. Check peer reviews (2 pending)
4. Analyze: MATH needs attention, peer reviews often forgotten
5. Generate plan with daily breakdown, flagging MATH assignment and peer reviews

**Output**: Full weekly plan with MATH assignment marked critical, peer reviews prominently featured

### Example 2: Heavy Workload Week

**Student**: "I have so much due this week, what should I do first?"

**Skill Process**:
1. Fetch assignments (finds 8 assignments in 5 days)
2. Identify highest priority (based on points and due dates)
3. Check for any grade concerns
4. Create aggressive but realistic plan
5. Include stress management advice

**Output**: Prioritized plan with specific daily goals, realistic expectations, encouragement

### Example 3: Light Week, Plan Ahead

**Student**: "What's coming up?"

**Skill Process**:
1. Fetch assignments (finds only 2 this week)
2. Extend window to 2 weeks to show future work
3. Note the light week is opportunity to get ahead
4. Identify major assignments in week 2

**Output**: This week's light work + recommendations for getting ahead on next week

## Error Handling

**No assignments found**:
- Check if student has active courses
- Suggest checking Canvas directly
- Offer to help with other planning

**API errors**:
- Gracefully explain the issue
- Suggest manual Canvas check
- Offer to retry or help troubleshoot

**Ambiguous timeframe**:
- Default to 7-day window
- Ask if student wants different timeframe
- Clarify what "week" means (Mon-Sun vs. next 7 days)

## Skill Maintenance Notes

**Update when**:
- Canvas MCP tool names change
- New relevant MCP tools added
- User feedback indicates better prioritization logic needed
- Academic calendar patterns suggest different defaults

**Version History**:
- v1.0.0: Initial release with core planning functionality

---

*This skill is part of the Canvas MCP Skills collection. For more information, visit: https://github.com/vishalsachdev/canvas-mcp*
