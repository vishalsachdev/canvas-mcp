# The Moment Your Side Project Stops Being Yours

*How strangers across three continents turned a solo teaching tool into something I never expected*

---

A year ago, I pushed the first commit to canvas-mcp — a tool born from frustration with Canvas LMS's clunky interface. I built it for myself: an MCP server that let me talk to Canvas through Claude instead of clicking through seventeen screens to grade an assignment.

I never expected strangers to care.

But here I am, scrolling through pull requests from a professor in North Carolina, a student in Singapore, and an astrophysicist down the hall — and I'm realizing the most rewarding part of open source isn't the code. It's the people.

## The First Pull Request Was Not Mine

Forty-nine days after the first commit, I woke up to a notification. Matias Carrasco Kind — a colleague at UIUC, director of Data Science Research Services at Gies, former astrophysicist at NCSA — had submitted PR #1. His commit message was simple: *"update script so it get the folder from the same repo and not hardcoded."*

It was a one-line fix. But it meant someone was reading the code. Someone was *using* it.

The next day, Matias opened PR #2: *"add group and peer-review management."* Four contributions total. He'd seen what I was building and thought, *I need this too — and it needs peer review tools.* The feature he added is still in the codebase today, eleven months later, handling thousands of peer review assignments across real courses.

That first contribution changed something in my head. This wasn't my tool anymore. It was *ours*.

## Professors Don't Usually Submit Pull Requests

Jerid Francom is a linguistics professor at Wake Forest University. His GitHub bio reads: *"Fluent in both linguistic theory and shell scripting."* In June 2025, he submitted PR #5: an executable wrapper that made canvas-mcp dramatically easier to install.

Think about that for a moment. A professor at a university 700 miles away found my repo, tried to install it, hit friction, and instead of filing an issue saying "this is hard to set up" — he wrote the fix himself. That's the open source dream, and it happened three months in.

I've never met Jerid. We've never emailed. But his code runs every time someone installs canvas-mcp.

## The Ecosystem Finds You

In April 2025, Frank Fiegel from Glama opened Issue #3: *"Glama listing is missing Dockerfile."* I didn't know what Glama was — it's an MCP marketplace. Someone had listed canvas-mcp there, and they needed Docker support. This one issue led to PR #15, proper containerization, and eventually listing on the MCP Registry and PyPI.

In September, Bell Eapen — an assistant professor at the University of Illinois Springfield, formerly Mayo Clinic — opened a feature request for UDOIT accessibility integration. He wasn't asking for a bug fix. He was seeing canvas-mcp as *infrastructure* — a platform where accessibility tooling could plug in. That's a different kind of compliment entirely.

Daniel Traynor noticed I'd gotten the MCP acronym wrong in the README. He didn't just file an issue. He submitted the fix the same day, PR #12. Merged in eight minutes.

Ansh Tulsyan tried to set up the project and discovered the `env.template` file referenced in the README didn't exist. Classic open source moment — the maintainer never noticed because they'd had the file locally all along.

These aren't headline contributions. No one's writing blog posts about fixing an acronym or adding a template file. But each one made the project better for the next person who found it. That's the compound interest of open source.

## The Relay Race: Singapore to Illinois

This is my favorite story.

In early February 2026, a user named Soulfire filed Issue #64: a datetime comparison bug in `get_my_upcoming_assignments`. The tool was crashing when comparing timezone-naive and timezone-aware datetimes — a classic Python gotcha. Three days later, they filed Issue #66: another bug in the same tool, this time an `argument of type 'int' is not iterable` error.

Soulfire was a *student*. They were actually using canvas-mcp to check their upcoming assignments and hit real bugs in production.

Two weeks later, Justin Cheah — a computer science student at the National University of Singapore — submitted PR #72 and PR #73, fixing both of Soulfire's bugs. He'd found the repo independently, saw open issues he could fix, and knocked them out in the same afternoon.

A student in the US hit a bug. A student in Singapore fixed it. They've never spoken. The relay baton was the issue tracker.

This is the moment open source stops being about code and starts being about community. Two students, 9,500 miles apart, collaborating through nothing but a shared GitHub repository.

## When Someone Adds a Feature You Actually Needed

Last week, Samuel Parks submitted PR #75: file download and listing tools. Canvas-mcp could upload files to courses but couldn't download them — a gap I'd been meaning to address but kept deprioritizing.

Samuel didn't just add a basic download function. He followed the project's patterns exactly: `@mcp.tool()` decorators, `@validate_params`, `get_course_id()` for flexible identifiers, proper error handling. He'd clearly read the codebase carefully enough to write code that looked like mine.

During code review, GitHub's automated tools flagged a path traversal vulnerability — the filename from Canvas API was being used directly without sanitization. We also switched to streaming downloads for large files and added input validation. The collaboration between the initial contribution and the review process made the final result better than either of us would have produced alone.

Seventeen new tests. Zero lint errors. Merged the same day.

## The Numbers, If You Care About Numbers

Canvas-mcp turned one year old last week. Here's where it stands:

- **61 stars** and **26 forks** — modest by npm standards, extraordinary for a niche education tool
- **195 unique cloners** in the last two weeks alone — people actively installing it
- **84 MCP tools** across courses, assignments, discussions, grading, messaging, analytics, modules, pages, files, and accessibility
- **6 external contributors** with merged pull requests
- **5 external issue reporters** who shaped the roadmap
- Contributors spanning from Illinois to North Carolina to Singapore

When I described the technical evolution of this project last September in [Three Months of Canvas MCP Evolution](https://chatwithgpt.substack.com/p/three-months-of-canvas-mcp-evolution), the story was about commits and architecture. The story now is about something different.

## What They Don't Tell You About Maintaining OSS

Nobody prepares you for the emotional weight of it. Not the burden — that's well-documented in maintainer burnout literature. I mean the *weight of mattering*.

When Soulfire filed that bug report, it meant a student was relying on my code to check their assignments. When Bell Eapen requested accessibility integration, it meant someone saw educational equity potential in what started as a convenience hack. When Justin fixed bugs from across the Pacific, it meant the project had grown past my ability to imagine all its users.

Every notification is a small vote of confidence. Someone took time out of their day to make your thing better. Not because they were paid. Not because they were assigned. Because they cared enough.

The closed PRs matter too. Frank (Sallvainian) — bio: *"Vibe coding till I make it"* — submitted two PRs for token efficiency optimization. They didn't get merged, but they showed me that token cost was a real pain point for users. That insight shaped later architecture decisions even though the specific code didn't land.

## The Real Product

Canvas-mcp started as 200 lines of Python to avoid clicking through Canvas. It's now 84 tools, 250+ tests, published on PyPI and the MCP Registry, with security hardening, FERPA compliance, and a CI/CD pipeline.

But the real product isn't the code. It's the proof that a niche tool for a specific pain point, built honestly and maintained openly, can attract exactly the right people. Not thousands of drive-by stars — but professors who teach with Canvas, students who learn through Canvas, and developers who see what a well-structured MCP server looks like and want to contribute.

If you're sitting on a tool you built for yourself and wondering whether to open source it: do it. Not for the stars. Not for the resume line. For the morning you wake up and discover that a professor 700 miles away rewrote your installer, a student on the other side of the world fixed a bug you didn't know existed, and an astrophysicist added peer review management because he needed it too.

That's the joy. That's the whole thing.

---

*Canvas-mcp is open source at [github.com/vishalsachdev/canvas-mcp](https://github.com/vishalsachdev/canvas-mcp). The project accepts contributions of all sizes — from acronym fixes to new tool implementations. If you teach with Canvas, you might find it useful.*

*Thank you to Matias, Jerid, Daniel, Ansh, Suyash, Bell, Frank, Frank, Soulfire, Justin, and Samuel. This project is better because of you.*
