# When Claude Code Becomes Your Co-Developer: Building a Canvas LMS Tool That Actually Works

**By Vishal Sachdev**
*June 20, 2025*

---

Picture this: It's 11:47 PM on a Tuesday. I'm staring at my Canvas dashboard, clicking through the same menus I've clicked through a thousand times before. Assignment submissions here, grade distributions there, trying to figure out which of my students might be struggling and need extra support.

Sound familiar?

Here's what hit me that night: Canvas is brilliant, but it wasn't built for the way educators actually think.

I don't want to click through seventeen screens to answer "Which students haven't engaged with discussions this week?" I want to ask that question directly and get an answer. Like, you know, having a conversation with someone who actually understands my courses.

The wild part? I'm not a developer. I'm an educator who got curious about whether Claude Code could build something that actually made sense.

Four months later, Claude Code is literally listed as a contributor on my GitHub project. Not as an assistant. As a *contributor*.

Let me tell you how we got here.

## The "Wait, What?" Moment: When AI Development Actually Makes Sense

Here's the thing about traditional software development—it's designed for developers, not educators. You want a simple tool to analyze discussion participation? Cool, that'll be 6 months of learning React, Node.js, database design, API development, authentication, deployment, and maintenance.

No thanks!

Claude Code flipped this entire model on its head by helping me build a Canvas integration tool based on a protocol called the Model Context Protocol (MCP). Instead of building apps, you build "tools" that Claude (and many other chat clients) can use directly.

Think of it like this: Instead of teaching yourself Spanish to order food in Mexico, you bring along a translator who already speaks both languages fluently.

Here's what blew my mind:

-   **Natural Language Interface:** I say "Show me grade distributions for my course" → Claude figures out the API calls, builds the tool and executes the query
-   **No Frontend/Backend Nonsense:** Write focused tools, Claude handles the interface
-   **Local and Secure:** Everything runs on your machine, no sketchy cloud services. More info on security/privacy features later.
-   **Start Small, Dream Big:** Begin with "list my courses" and evolve to advanced analytics

The moment I realized this was possible, I knew we were in uncharted territory. Not "AI helps you code faster" territory. More like "AI becomes your co-developer" territory.

## The Journey: From "Can This Work?" to "Holy Crap, It Actually Works"

### Phase 1: The Proof of Concept (February 2025)

February 27th, 2025. First commit. I literally just wanted to know: "Can I make Claude talk to Canvas?"

The answer? A resounding "yes" wrapped in 200 lines of Python that could list my courses.

But here's what I learned immediately: When you're building with AI, you think differently about architecture from day one. Not because you're smarter, but because Claude thinks about edge cases and security patterns that you might skip when you're just trying to make something work.

Key decisions that shaped everything:

-   **Security obsession:** API tokens in environment variables, never in code (Claude insisted)
-   **Type safety everywhere:** Even for simple functions (again, Claude's influence)
-   **FastMCP foundation:** Chose the most robust framework, not the quickest (guess who suggested that)

### Phase 2: The "Oh Shit, This Is Real" Phase (March-April 2025)

March hit different. What started as "list my courses" became assignment management, submission tracking, peer review workflows, discussion forum integration. The codebase exploded to 800+ lines.

Plot twist: mgckind submitted pull requests adding group management features. First external contributor! Someone else (wink, wink He’s a colleague, but I swear I did not tell him to contribute) saw what we were building and wanted to contribute. That's when you know you're onto something.

But here's the real kicker—Canvas's API is *complex*. Want to know which students haven't submitted assignments? That's not one API call. That's like 7 API calls, with pagination, error handling, and data normalization.

Claude Code handled all of that complexity while I focused on "what do educators actually need?"

### Phase 3: The Architecture Revolution (June 2025)

By June, we had 3,000 lines of code and a problem: it was getting unwieldy. Time for the big refactor.

Claude Code basically said: "Hey, let's build this like we mean it."

What emerged:

-   **Modular architecture:** Core utilities, domain-specific tools, comprehensive documentation
-   **Advanced features:** Rubric-based grading, student analytics, performance tracking, privacy preserving data exchange
-   **Real educational workflows:** Not just "Canvas API wrapper" but "how educators actually think"

Here's the interesting part: Check the GitHub contributors list. Claude Code is listed as a contributor. Not "assisted by Claude." Not "powered by AI." Listed as a *contributor*.

This isn't human-using-AI. This is human-*collaborating*-with-AI.

We are literally witnessing the birth of a new kind of software development partnership.

## WHAT WE BUILT: THE TOOLS THAT ACTUALLY MATTER

After 4 months of iteration, here's what we ended up with—tools that solve real problems, not theoretical ones:

### Course Management (AKA "Stop Clicking Through Menus")

**The Problem:** Getting a simple overview of your courses requires 47 browser tabs and a spreadsheet.

**What We Built:**
-   Ask Claude: "Show me all my courses with enrollment numbers and upcoming deadlines"
-   Get instant comprehensive summaries across multiple courses
-   Navigate complex module structures with plain English

### Student Support (AKA "Early Warning System")

**The Problem:** By the time you realize a student is struggling, it's often too late.

**What We Built:**
-   Discussion forum monitoring and AI-powered response suggestions
-   Early intervention analytics: "Show me students with declining participation"
-   Bulk assignment analysis: "Which students haven't submitted anything this week?"
-   Consistent, personalized feedback using rubric criteria

### Administrative Sanity (AKA "The Boring Stuff That Takes Forever")

**The Problem:** Scheduling announcements, exporting grades, managing enrollments—death by a thousand clicks.

**What We Built:**
-   Scheduled announcements that actually work
-   One-click gradebook export with analytics
-   Bulk user operations that don't make you want to cry

The key insight: Instead of building "Canvas but better," we built "Canvas but conversational."

### And Finally - Privacy-First Student Data Protection

**The Problem:** Using AI tools with student data creates FERPA compliance risks and privacy violations.

**What We Built:**
-   Source-level data anonymization that converts real names to consistent anonymous IDs (Student_xxxxxxxx)
-   Automatic email masking and PII filtering from discussion posts and submissions
-   Local-only processing with configurable privacy controls (`ENABLE_DATA_ANONYMIZATION=true`)
-   FERPA-compliant analytics: "Which students need support?" without exposing real identities

#VibeCoding at its finest.

## THE RESULTS: WHAT ACTUALLY CHANGED

Here's what I discovered after using this system for real course management:

### Time Compression

That 45-minute weekly ritual of checking assignment submissions, calculating participation, and identifying at-risk students? Now it's a 2-minute conversation with Claude.

"Show me students who haven't engaged with discussions this week and are behind on assignments."

Done. List appears. Interventions can start immediately instead of next Tuesday. Proof below in screenshots from Claude Code with names redacted. This was taken before the privacy features were implemented.

### Innovative teaching experiments on the fly

This week, while my Introductory Information Systems students shared eight nouns to describe themselves in an online forum, I ran an unplanned pilot—AI analysis of every word—to map our classroom’s "social DNA." I wrote about it.

> #### BEYOND CHATGPT: HOW AI TRANSFORMED MY CLASSROOM INTO A LIVING LABORATORY
>
> This week, while my Introductory Information Systems students shared eight nouns to describe themselves in an online forum, I ran an unplanned pilot—AI analysis of every word—to map our classroom’s "social DNA." What was a simple community building exercise turned into a demonstration of AI’s potential for pedagogical insight.

## Your Turn: Get Started Without Losing Your Mind

Want to try this? Here's the setup guide:

### What You Need

-   Canvas access (with API permissions)
-   Claude Desktop/ Claude Code or any other AI client that supports working with MCP tools
-   15 minutes and basic comfort with following setup instructions

### The Setup (Actually Simple)

1.  **Download and configure:** Clone the project, add your Canvas API credentials
2.  **Install dependencies:** One `pip install` command
3.  **Connect to Claude Desktop:** Add the MCP server to your config
4.  **Test:** Ask Claude to "list my courses" and watch the magic

### Start Here (Not Advanced Analytics)

-   "Show me my course enrollments"
-   "What assignments are due this week?"
-   "Give me a summary of discussion participation"

Build familiarity before attempting the complex stuff. Trust me on this.

### Pro Tips From Experience

-   **Start small:** Course listing before complex analytics
-   **Know your Canvas setup:** The tool surfaces existing data, so understanding your course structure helps
-   **Document what works:** Keep notes on useful commands
-   **Iterate gradually:** Add complexity as you get comfortable

#WeAreAllAppDevelopersNow

## What I Learned: The Real Insights

After 4 months of genuine AI-human collaboration, here are the patterns that emerged:

### AI as Co-Developer is Real

Having Claude Code as a GitHub contributor isn't a gimmick. The AI genuinely improved the architecture, suggested security patterns I wouldn't have considered, and wrote documentation that's clearer than what I would have produced alone.

This isn't "AI helps you code faster." This is "AI thinks about your code differently and makes it better."

### Incremental Beats Comprehensive

Every instinct says "build everything at once." Every successful feature started with "let's just make course listing work."

The magic happens in iteration. Start simple, discover what you actually need, evolve gradually.

### Documentation is Everything

1,000+ lines of documentation isn't excessive—it's essential. Educational tools need non-technical explanations or they don't get adopted.

Claude's obsession with clear documentation and its infinite patience is very welcome!

### Open Source Works for Education

mgckind's contributions proved something important: educators building for educators creates better tools than developers building for educators.

The community knows what it needs.

## What's Next: The Vision

This is just the beginning. What we've proven is that MCP + Claude Code creates a new category of possibility. Every educator can build personalized AI tools that understand their specific teaching context and student needs. Several more tools are possible. Perhaps a tool that helps send customized messages to students at risk using the Canvas mail feature? Share what you need or just build it yourself!

The bigger picture: This same approach works with any API. Student information systems, library databases, research platforms, learning analytics platforms. Have API, can build MCP Server. And if you are willing to work with remote MCP servers, take a look at this repository - https://github.com/sylviangth/awesome-remote-mcp-servers

What educational workflow could benefit from conversational AI in your context?

## Join the Movement

This isn't just about Canvas integration. This is about proving that educators can build sophisticated AI tools without traditional programming barriers.

-   **Try it:** GitHub repo with comprehensive setup guides
-   **Contribute:** Your teaching challenges might inspire the next breakthrough
-   **Think bigger:** What other educational APIs need conversational interfaces?

The future isn't AI replacing educators. It's AI empowering educators to focus on what they do best: teaching, not administrative overhead.

We are all app developers now. The question is: what will you build?

---

*Built with Claude Code—proving that the future of educational technology is collaborative, conversational, and available today.*