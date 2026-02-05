# Transdisciplinary Project Discovery

**Date:** 2026-02-05
**Status:** Brainstorm
**Author:** jdec + Claude

## What We're Building

Port the **TD Serendipity Generator** from TypeScript to Python as MCP tools. This system discovers transdisciplinary collaboration opportunities by analyzing student overlap, module timing, learning outcomes, and using AI to generate project ideas mapped to Franklin's 9 competencies.

### Core Capabilities (from existing tool)
1. **Student Overlap Detection** - Find courses that share students
2. **Concurrent Module Timing** - Parse week ranges, find temporally-aligned modules
3. **Learning Outcomes Extraction** - Pattern-match outcomes from Canvas pages
4. **AI-Powered Crossover Analysis** - Generate project ideas with competency mapping

### Key Constraint
**Temporal alignment required**: Only surface opportunities where modules overlap in time.

## Franklin's 9 Transdisciplinary Competencies

All crossover opportunities map to these institutional competencies:

| # | Competency | Description |
|---|------------|-------------|
| 1 | **Collaboration** | Works productively with others toward shared goals |
| 2 | **Communication & Storytelling** | Communicates ideas clearly, creatively, and appropriately |
| 3 | **Reflexivity** | Reflects critically on learning, decisions, and assumptions |
| 4 | **Empathy & Perspective-Taking** | Understands and respects others' perspectives |
| 5 | **Knowledge-Based Reasoning** | Applies disciplinary and interdisciplinary knowledge |
| 6 | **Futures Thinking** | Envisions and prepares for multiple and preferred futures |
| 7 | **Systems Thinking** | Identifies interconnections within and across systems |
| 8 | **Adaptability** | Responds constructively to change and ambiguity |
| 9 | **Agency** | Takes initiative and ownership of learning |

## Existing Implementation (TD Serendipity Generator)

**Location**: `/Users/jdec/Documents/TD_Serendipity_Generator_V1/`
**Stack**: TypeScript/Node.js
**Goal**: Replace with Python MCP tools

### Phase 1: Student Overlap Detection
- Sample 3 students from a selected course
- Find all courses those students are enrolled in (current term)
- Rank courses by number of shared students
- Detect multi-course cohorts (3+ courses with same students)

### Phase 2: Concurrent Module Timing
- Parse week ranges from module names using regex patterns:
  - `Week 8-15`, `Weeks 11+12`, `Week 8`
  - `T1 weeks 1-4`, `T1 Week 7-T2 Week 4`
  - `(Weeks 1-6)` parenthetical format
- Calculate overlap periods between modules
- Identify multi-course overlaps (3+ courses in same time period)

### Phase 3: Learning Outcomes Extraction
- Fetch pages within each module
- Pattern match for outcome indicators:
  - "students will be able to", "SWBAT"
  - "learning objectives", "learning outcomes"
  - "by the end of this unit/lesson/module"
- Extract list items from `<ol>` and `<ul>` tags
- Filter placeholder text

### Phase 4: AI-Powered Crossover Analysis
- Send concurrent module pairs to Claude
- Claude evaluates connection quality: `🔥 HIGH VALUE` / `⭐ GOOD` / `❌ SKIP`
- Maps to Franklin competencies with rationale
- Generates 2-3 project ideas per pair
- For multi-course cohorts (3+), generates more ambitious integrated projects

## MCP Tool Design

### Proposed Tools

| Tool | Phase | Purpose |
|------|-------|---------|
| `find_student_overlap` | 1 | Find courses sharing students with a given course |
| `find_concurrent_modules` | 2 | Find modules with overlapping week ranges |
| `extract_learning_outcomes` | 3 | Extract outcomes from module pages |
| `analyze_crossover_opportunity` | 4 | AI analysis of a module pair |
| `discover_opportunities` | All | End-to-end discovery pipeline |
| `list_competencies` | Ref | Show the 9 Franklin competencies |

### Data Flow

```
User: "Find transdisciplinary opportunities for ENG 100"

1. find_student_overlap(course_id)
   → Returns: overlapping_courses, multi_course_cohorts

2. find_concurrent_modules(course_id, overlapping_courses)
   → Returns: concurrent_pairs, multi_course_overlaps

3. For each promising pair:
   extract_learning_outcomes(module_a)
   extract_learning_outcomes(module_b)

4. analyze_crossover_opportunity(pair_with_outcomes)
   → Returns: thematic_overlaps, shared_skills, competency_mappings, project_ideas

5. Format and return comprehensive report
```

### Query Modes

**Course-focused:**
> "Find transdisciplinary opportunities for ENG 100"

**Theme-focused:**
> "What courses cover sustainability and when do they overlap?"

**Broad discovery:**
> "Discover all transdisciplinary opportunities this term"

**Specific pair:**
> "Could ENG 100 and ENV 200 collaborate? Analyze their modules."

## Key Implementation Details

### Week Range Parsing (from existing code)

```python
def parse_week_range(module_name: str) -> WeekRange | None:
    patterns = [
        r'[Ww]eeks?\s+(\d+)[-\s]+(\d+)',     # Week 8-15, Weeks 8-15
        r'[Ww]eeks?\s+(\d+)\+(\d+)',          # Weeks 11+12
        r'[Ww]eek\s+(\d+)',                    # Week 8 (single)
        r'T\d+\s+[Ww]eeks?\s+(\d+)[-\s]+(?:T\d+\s+[Ww]eek\s+)?(\d+)',  # T1 weeks 1-4
        r'\([Ww]eeks?\s+(\d+)[-\s]+(\d+)\)',   # (Weeks 1-6)
    ]
    # ... pattern matching logic
```

### Outcome Extraction Indicators

```python
OUTCOME_INDICATORS = [
    r'by the end of this (unit|lesson|module)',
    r'students will be able to',
    r'students will\s*:',
    r'learning objectives?',
    r'learning outcomes?',
    r'SWBAT',
]
```

### AI Analysis Prompt Structure

```
You are an educational consultant analyzing concurrent modules for transdisciplinary collaboration at Franklin School.

Course A: {course_name}
Module: {module_name}
Learning Outcomes: {outcomes}

Course B: {course_name}
Module: {module_name}
Learning Outcomes: {outcomes}

Overlap Period: Weeks {start}-{end}

# Franklin's 9 Competencies
[list competencies]

# Task
1. Rate connection quality: 🔥 HIGH VALUE / ⭐ GOOD / ❌ SKIP
2. Identify thematic overlaps
3. Map to Franklin competencies
4. Generate 2-3 crossover project ideas
```

### Multi-Course Cohort Detection

The system detects when 3+ courses share the same students AND have modules running concurrently. These are flagged as **high-value** opportunities because:
- More disciplines = richer integration
- Students already enrolled in all courses = easier logistics
- Projects can be more ambitious and systems-oriented

## Output Format

### Opportunity Report Structure

```
## 🔥 HIGH VALUE Opportunity: ENG 100 + ENV 200 + MATH 200

### Timing
All three courses have modules running Weeks 8-10

### Thematic Overlaps
- Data-driven storytelling
- Environmental impact analysis
- Quantitative reasoning applied to real-world problems

### Franklin Competencies Addressed
- **Systems Thinking**: Students analyze environmental systems using math modeling and communicate findings through narrative
- **Knowledge-Based Reasoning**: Integrates statistical analysis, environmental science, and persuasive writing
- **Communication & Storytelling**: Transform quantitative findings into compelling narratives

### Suggested Project: "Carbon Footprint Narrative"
Students analyze their school's carbon footprint using statistical methods (MATH 200),
research environmental implications (ENV 200), and craft a persuasive essay or documentary
script presenting their findings to stakeholders (ENG 100).

**Implementation Notes**:
- Week 8: Data collection and initial analysis
- Week 9: Research and synthesis
- Week 10: Narrative development and presentation
- Could culminate in school assembly presentation

### Teachers to Connect
- ENG 100: Sarah Johnson
- ENV 200: Michael Chen
- MATH 200: Lisa Park

### Bridge Students (enrolled in all three)
- Emma Wilson
- James Park
- Sofia Rodriguez
```

## Open Questions

1. **Lesson page identification**: How do we distinguish lesson pages from other pages? Is there a naming convention?

2. **Outcome quality**: Some courses may have sparse outcomes. Should we also analyze assignment descriptions?

3. **Teacher notification**: Should discovering an opportunity trigger a notification or email draft?

4. **Historical tracking**: Should we track which opportunities were acted on for future analysis?

5. **Competency weighting**: Are some competencies prioritized over others?

## Migration Notes

### TypeScript → Python Considerations

| TypeScript | Python Equivalent |
|------------|-------------------|
| `class OverlapFinder` | Python class or functional approach |
| `Map<number, ...>` | `dict[int, ...]` |
| Anthropic SDK (TS) | Already using Anthropic in Canvas MCP |
| Regex patterns | Same patterns work in Python `re` |
| `async/await` | Same in Python |

### Canvas MCP Integration Points

- Use existing `make_canvas_request()` for API calls
- Use existing `fetch_all_paginated_results()` for pagination
- Use existing `strip_html_tags()` for HTML cleaning
- Add new `core/competencies.py` for Franklin competency definitions
- Add new `tools/transdisciplinary.py` for discovery tools

## Success Criteria

1. Can replicate TD Serendipity Generator results in MCP
2. Discovers same opportunities with same quality
3. Maps accurately to Franklin's 9 competencies
4. Conversational interface ("Find opportunities for ENG 100")
5. Export capability for sharing with teachers
6. Faster iteration cycle than standalone tool

## Next Steps

1. **Extract competencies** - Create `core/competencies.py` with Franklin's 9 competencies
2. **Port Phase 1** - Student overlap detection
3. **Port Phase 2** - Week range parsing and module timing
4. **Port Phase 3** - Outcomes extraction
5. **Port Phase 4** - AI analysis with competency mapping
6. **Build pipeline tool** - End-to-end discovery
7. **Test on sandbox** - Compare results with existing tool
