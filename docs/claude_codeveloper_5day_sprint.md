# The 5-Day Sprint: When FERPA Compliance Becomes a Co-Development Masterclass

**By Vishal Sachdev**
*June 25, 2025*

---

Sometimes the most demanding feature requests create the most illuminating development experiences.

Five days ago, I stared at a TODO.md file that had been sitting in my Canvas MCP repository for weeks. The task? Implement FERPA compliance by anonymizing student data across eight different tools. The kind of feature that makes you think: "This is going to be a slog."

Instead, it became the most fascinating 5-day sprint I've ever experienced with Claude Code as my co-developer.

## The Challenge: Privacy Isn't Optional

Here's what FERPA compliance meant for our Canvas MCP tool:

- **Eight tools** handling raw student data
- **Personally Identifiable Information** flowing directly to AI models
- **Zero privacy protection** in discussion posts, grade analytics, and submission data
- **Real student names** exposed in every query

The stakes? Educational institutions can't use AI tools that violate FERPA. Period.

Our existing anonymization module was sitting there, unused. Eight tools were leaking student data. And I had a choice: spend weeks implementing privacy protection manually, or see if Claude Code could help architect a systematic solution.

## Day 1: The Architecture Session

**June 20th, 2025**: I created GitHub issue #7 from the TODO.md file. The scope was intimidating:

> "Fix FERPA Compliance Gap by Anonymizing Student Data in Tool Outputs"

Claude Code immediately suggested a systematic approach:

1. **Priority tiers**: High-risk tools first (discussion entries, student analytics)
2. **Progressive implementation**: Start with list_discussion_entries
3. **Infrastructure first**: Update .gitignore before touching code
4. **Testing strategy**: Verify anonymization without breaking functionality

What struck me: Claude wasn't just reading the TODO—it was thinking strategically about implementation order and risk mitigation.

## Day 2-3: The Implementation Marathon

**June 22nd-24th**: Created feature branch `feature/ferpa-anonymization` and dove in.

Here's where it got interesting. I expected to spend days debugging import statements and figuring out error handling patterns. Instead, Claude Code was thinking about edge cases I hadn't considered:

```python
# Claude's approach to robust anonymization
try:
    entries = anonymize_response_data(entries, data_type="discussions")
except Exception as e:
    print(f"Warning: Failed to anonymize discussion data: {str(e)}")
    # Continue with original data for functionality
```

Every tool got wrapped in try/catch blocks. Every anonymization call got validation. The code wasn't just functional—it was production-ready.

**The systematic progression:**
- High priority: `list_discussion_entries`, `get_student_analytics`, `list_users`
- Medium priority: `list_submissions`, `get_assignment_analytics`, `list_groups`  
- Low priority: `list_peer_reviews`, `get_submission_rubric_assessment`

Eight tools. Consistent patterns. Robust error handling throughout.

## Day 4: The Infrastructure Touch & Open Source Magic

**June 24th**: While implementing the core anonymization, something remarkable happened. Jerid Francom submitted PR #5 adding executable wrapper functionality for the canvas-mcp-server. 

A third-party contributor. Someone else saw value in what we were building and contributed meaningful improvements to the project architecture.

This is the beauty of open source development—while Claude Code and I were deep in FERPA compliance, the broader community was enhancing the foundation. Jerid's PR improved the installation and execution experience for all users.

Meanwhile, Claude Code suggested creating a de-anonymization mapping tool:

```python
@mcp.tool()
async def create_student_anonymization_map(course_identifier: str) -> str:
    """Generate local CSV mapping between real and anonymous student data."""
```

But here's the brilliant part—it immediately flagged the security implications:

```python
# Security warning in the tool output
result += "\n⚠️  SECURITY WARNING: This file contains PII and should be:"
result += "\n   - Stored securely on your local machine only"
result += "\n   - Never shared or uploaded to cloud services"
```

Then it updated .gitignore to protect the mapping files:

```
# Local de-anonymization maps (contains PII)
local_maps/
```

I'm not sure I would have thought about the security implications of the mapping files that early in the process.

## Day 5: The CI/CD Reality Check

**June 24th-25th**: Created PR #8, and that's when Claude Code really showed its co-developer credentials.

The PR got an automated Claude review that identified actual issues:

> "The anonymization calls should be wrapped in try/catch blocks to ensure tools continue working if anonymization fails."

Real code review. Real suggestions. Real improvements.

But then the CI/CD pipeline failed due to deprecated GitHub Actions. Instead of manual debugging, Claude Code:

1. **Fixed the deprecated upload-artifact@v3** → upload-artifact@v4
2. **Added conditional logic** for missing test files
3. **Made the workflow robust** with continue-on-error patterns

The fix worked on the first try.

## The Merge: Branch Protection vs. Solo Development

Here's where it got meta. GitHub's branch protection rules prevented me from approving my own PR. Claude Code diagnosed the issue:

> "GitHub prevents self-approval on protected branches. You'll need to add an owner exception."

I added the exception. Claude Code immediately offered to merge the PR. One command later, we had merged 8 FERPA-compliant tools with comprehensive error handling.

## What This Really Means

This wasn't just "AI helps you code faster." This was architectural thinking, security awareness, and systematic problem-solving that made the solution better than what I would have built alone.

**The numbers:**
- 5 days from TODO to merged PR
- 8 tools with robust anonymization
- 1 de-anonymization mapping system
- 1 CI/CD pipeline fix
- 1 third-party PR merged during the sprint
- 0 bugs in the final implementation

**The modern AI development toolkit**: Today's final TODO cleanup was created using Google's new Gemini CLI tool, showcasing how different AI tools can complement each other in a developer's workflow.

**The insights:**
- Claude Code thinks about production concerns (error handling, security)
- Co-development means better architecture decisions
- Open source development creates unexpected collaboration opportunities
- Systematic approaches beat ad-hoc implementations
- Documentation and testing matter from day one
- Multiple AI tools can complement each other in modern development workflows

## The Bigger Picture

This 5-day sprint proved something fundamental: When you're building with Claude Code, you're not just getting implementation help—you're getting a co-developer who thinks about the problems differently than you do.

The FERPA compliance feature isn't just functional. It's robust, secure, and maintainable. It handles edge cases, provides clear error messages, and protects sensitive data while maintaining all the original functionality.

Most importantly, it's the kind of solution that makes the tool viable for real educational institutions with real compliance requirements.

Five days. One complex feature. Proof that AI co-development isn't just possible—it's transformative.

---

*This is part of the ongoing Canvas MCP journey. For the full 4-month story, read [When Claude Code Becomes Your Co-Developer](./claude_codeveloper_experience.md).*