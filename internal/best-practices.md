# Claude Code Development Best Practices for Canvas MCP

*Based on 2025 Claude Code best practices and 6-month development history analysis*

## Your Current "Vibe Coding" Patterns (Analyzed)

**What I observed from your git history:**
- 42 commits over 6 months (about 1.5 commits/week)
- **Burst development**: Heavy activity in June (25 commits), then gaps
- **Feature-complete commits**: Large comprehensive implementations
- **Good commit messages**: Descriptive and include Claude Code attribution
- **Major architectural changes**: Privacy system, messaging, cleanup phases

## Core Claude Code Best Practices (2025)

### 1. **CLAUDE.md Configuration**
The CLAUDE.md file is Claude's automatic context - your project's permanent brain.

Key elements to include:
- Common bash commands: `npm run test`, `npm run build`, etc.
- Code style guidelines: "Use ES modules, not CommonJS," or "Always use functional components with hooks."
- Key files or architectural patterns: "State management is handled by Zustand; see src/stores for examples."
- Testing instructions: "New components require a corresponding test file using React Testing Library."
- Use more than one CLAUDE.md file for complex projects.

### 2. **Research and Planning First**
Steps #1-#2 are crucial—without them, Claude tends to jump straight to coding a solution. Ask Claude to research and plan first for problems requiring deeper thinking upfront.

### 3. **Test-Driven Development Workflow**
- Ask Claude to write tests based on expected input/output pairs
- Be explicit about doing test-driven development
- Tell Claude to run tests and confirm they fail first
- Ask Claude to commit tests when satisfied

### 4. **Git Branch Management**
Always start by having Claude create a new Git branch for every new feature or bug fix. This acts as a safety net.

### 5. **Active Collaboration vs Auto-Accept**
While auto-accept mode (shift+tab) lets Claude work autonomously, you'll get better results by being an active collaborator and guiding Claude's approach.

### 6. **Plan Mode for Complex Projects**
Use Plan Mode for exploring codebases, planning complex changes, or reviewing code safely with read-only operations.

### 7. **Context Management**
- Use tab-completion to quickly reference files or folders
- Paste specific URLs alongside prompts for Claude to fetch and read
- Use `/permissions` to add domains to your allowlist

### 8. **GitHub Integration**
Claude Code integrates with GitHub, GitLab, and command line tools to handle entire workflows—reading issues, writing code, running tests, and submitting PRs.

### 9. **Custom Commands and Automation**
Custom commands in `.claude/commands/` are automatically shared when team members clone your repository.

### 10. **Team Collaboration**
Treat Claude Code as a thought partner rather than a code generator. Focus on human workflows that it can augment.

## Recommended Development Workflow for Your Style

### 1. **Enhanced CLAUDE.md Strategy**
Your CLAUDE.md is already good, but add these sections:

```markdown
## Development Phases & Status
- **Current Phase**: [e.g., "Analytics Enhancement", "UI Polish", "Bug Fixes"]
- **Next Major Feature**: [e.g., "Grade Center Integration", "Mobile Support"]
- **Known Issues**: [Tracked issues that Claude should be aware of]

## Development Context
- **Last Session**: [Brief note about what you were working on]
- **Current Branch**: [If working on features]
- **Testing Status**: [What's tested, what needs testing]
```

### 2. **Embrace "Sprint Planning" for Vibe Coding**
Since you do burst development, plan better for those sessions:

```bash
# At start of coding session
echo "## Session $(date +%Y-%m-%d)" >> .dev-log.md
echo "Goals: [your goals]" >> .dev-log.md

# During development
echo "- Implemented X" >> .dev-log.md

# End of session
echo "Next: [what to do next time]" >> .dev-log.md
```

### 3. **Branch Strategy for Your Style**
```bash
# For major features (like your messaging system)
git checkout -b feature/messaging-system

# For experiments/vibe coding
git checkout -b experiment/$(date +%m%d)-idea-name

# Always merge back to main when satisfied
```

### 4. **Use Claude Code's Plan Mode More**
For your burst development style:
```bash
# Start each session with planning
claude --plan "I want to add [feature]. Analyze current state and create implementation plan"

# Then execute the plan
claude "Implement the plan we discussed"
```

### 5. **Development Journal Integration**
Create `.claude/commands/session-start.sh`:
```bash
#!/bin/bash
echo "=== Dev Session $(date) ===" >> DEV.md
echo "Branch: $(git branch --show-current)" >> DEV.md
echo "Last commit: $(git log -1 --oneline)" >> DEV.md
echo "Goals: " >> DEV.md
echo "" >> DEV.md
```

### 6. **Better Issue Tracking for Solo Development**
Instead of complex project management:

```markdown
# TODO.md (simple format)
## Now (Current Session)
- [ ] Fix peer review reminder bug
- [ ] Add template validation

## Next (Future Sessions)
- [ ] Grade center integration
- [ ] Mobile responsive design

## Someday/Maybe
- [ ] Machine learning grade prediction
- [ ] Integration with other LMS
```

### 7. **Automated Documentation Updates**
Create `.claude/commands/doc-update.sh`:
```bash
#!/bin/bash
claude "Update CLAUDE.md with any new functionality added in the last 3 commits"
```

## Specific Recommendations for Your Canvas MCP Project

### 1. **Phase-Based Development Tracking**
```markdown
# PHASES.md
## Phase 1: Core Infrastructure ✅ (June 2025)
- FastMCP foundation
- Privacy/anonymization system
- Basic Canvas API integration

## Phase 2: Analytics & Messaging ✅ (Sept 2025)
- Peer review analytics
- Messaging system
- Template system

## Phase 3: Advanced Features 🚧 (Current)
- Grade center integration
- Advanced analytics
- UI improvements

## Phase 4: Polish & Scale 📋 (Future)
- Performance optimization
- Error handling
- Documentation
```

### 2. **Feature Status Dashboard**
Add to CLAUDE.md:
```markdown
## Feature Status
- ✅ Basic Canvas API integration
- ✅ Student privacy protection
- ✅ Peer review analytics
- ✅ Messaging system
- 🚧 Grade center integration
- 📋 Mobile support
- 📋 Advanced reporting
```

### 3. **Use GitHub Issues for Big Ideas**
```bash
# Create issues for major features
gh issue create --title "Grade Center Integration" --body "Epic for integrating with Canvas gradebook"

# Link commits to issues
git commit -m "Add gradebook API client (#15)"
```

## Workflow for Your Next Session

### 1. **Session Start**:
```bash
./dev-session-start.sh
claude "What should I work on next based on the current state?"
```

### 2. **Development**:
```bash
# Use plan mode for complex features
claude --plan "Implement grade center integration"

# Then execute
claude "Implement the grade center plan"
```

### 3. **Session End**:
```bash
# Update docs
claude "Update CLAUDE.md and PHASES.md with what we accomplished"

# Clean commit
git add -A && git commit -m "Descriptive commit message"
```

## Key Takeaways

This approach respects your "vibe coding" style while adding just enough structure to:
- Track progress between burst development sessions
- Maintain context for Claude Code
- Document architectural decisions
- Plan future development phases
- Keep the project organized as it grows

Remember: Claude Code works best when you focus on human workflows that it can augment. Treat it as a thought partner rather than just a code generator.