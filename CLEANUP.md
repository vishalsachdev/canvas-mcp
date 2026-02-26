# Titan Codebase Refactor — Swarm Assignment Roadmap

## Branch: `claude/titan-codebase-refactor-l9nqr`

## Regression Baseline
- **252 tests passing**, 18 skipped, 0 failures
- **0 ruff violations**
- Total: 12,410 source lines, 5,322 test lines

---

## Batch Assignments

### Batch 1 — Critical Core (P0)
**Files:** `core/validation.py` (CC=47), `core/client.py` (CC=23), `core/peer_review_comments.py` (CC=27)
**Lines:** 1,215 | **Agent:** Alpha

| Gauntlet Pillar | Violations |
|----------------|------------|
| Complexity (CC>7) | validate_parameter CC=47, make_canvas_request CC=23, get_peer_review_comments CC=27 |
| Nesting (≥3 deep) | validate_parameter depth=10, make_canvas_request depth=7, get_peer_review_comments depth=6 |
| Silent failures | validation.py:177 |
| Print logging | client.py: 10 instances |
| Magic values | client.py: retry counts, timeout values hardcoded |

**Refactor plan:**
- [ ] Break `validate_parameter()` into type-specific dispatch functions
- [ ] Extract `make_canvas_request()` retry/rate-limit logic into helpers
- [ ] Flatten nested loops in `get_peer_review_comments()`
- [ ] Replace `print(stderr)` with structured logging
- [ ] Extract magic numbers to named constants
- [ ] Fix silent failure in validation.py:177

---

### Batch 2 — Core Remaining (P1)
**Files:** `core/peer_reviews.py`, `core/anonymization.py`, `core/cache.py`, `core/config.py`, `core/logging.py`, `core/dates.py`, `core/file_validation.py`, `core/audit.py`, `core/types.py`
**Lines:** 1,926 | **Agent:** Beta

| Gauntlet Pillar | Violations |
|----------------|------------|
| Complexity | anonymization.py CC=16/depth=8, peer_reviews CC=19/depth=5 |
| Print logging | config.py: 9, cache.py: 3, dates.py: 1, audit.py: 1 |
| Nesting | anonymize_response_data depth=8, _sanitize_context depth=4 |
| Magic values | Scattered hardcoded strings/numbers |

**Refactor plan:**
- [ ] Flatten `anonymize_response_data()` via early returns and helper extraction
- [ ] Replace all `print(stderr)` with `get_logger()` calls
- [ ] Extract constants from peer_reviews.py analysis thresholds
- [ ] Improve types.py with domain-specific type aliases
- [ ] Add guard clauses to reduce nesting in cache.py

---

### Batch 3 — Heavy Tools (P0)
**Files:** `tools/discussions.py` (CC=194), `tools/rubrics.py` (CC=106), `tools/assignments.py` (CC=139)
**Lines:** 3,611 | **Agent:** Gamma

| Gauntlet Pillar | Violations |
|----------------|------------|
| Complexity | Aggregate CC from nested tool definitions |
| Nesting | list_discussion_entries depth=6, validate_rubric_criteria depth=7 |
| Silent failures | assignments.py:493 |
| Magic values | Grade thresholds, pagination limits, string templates |

**Refactor plan:**
- [ ] Extract inner tool functions to module-level (pass `mcp` via closure or partial)
- [ ] Break `list_discussion_entries()` into fetch + format helpers
- [ ] Extract `validate_rubric_criteria()` branching into validator map
- [ ] Fix silent failure in assignments.py:493
- [ ] Extract response formatting to shared helpers

---

### Batch 4 — Medium Tools (P0)
**Files:** `tools/modules.py` (CC=99), `tools/other_tools.py` (CC=81), `tools/student_tools.py` (CC=64), `tools/code_execution.py` (CC=58)
**Lines:** 2,340 | **Agent:** Delta

| Gauntlet Pillar | Violations |
|----------------|------------|
| Complexity | All 4 files have CC>50 (aggregate from nested tools) |
| Silent failures | code_execution.py:580, code_execution.py:585 |
| Nesting | discovery depth=6, student_tools depth=6 |
| Magic values | Module item types, score thresholds, sandbox limits |

**Refactor plan:**
- [ ] Extract inner tool functions to module-level
- [ ] Fix 2 silent failures in code_execution.py
- [ ] Extract `add_module_item()` validation into a dispatch table
- [ ] Flatten student_tools nesting with guard clauses
- [ ] Move sandbox config magic values to constants

---

### Batch 5 — Light Tools (P1)
**Files:** `tools/messaging.py`, `tools/files.py`, `tools/accessibility.py`, `tools/courses.py`, `tools/peer_review_comments.py`, `tools/pages.py`, `tools/peer_reviews.py`, `tools/discovery.py`, `tools/message_templates.py`
**Lines:** 2,828 | **Agent:** Epsilon

**Refactor plan:**
- [ ] Standardize response formatting across all tools
- [ ] Extract shared course-validation patterns
- [ ] Reduce nesting in courses.py and discovery.py
- [ ] Ensure consistent error response format

---

### Batch 6 — Server & Resources (P2)
**Files:** `server.py`, `resources/resources.py`
**Lines:** 418 | **Agent:** Zeta

| Gauntlet Pillar | Violations |
|----------------|------------|
| Complexity | server.py main() CC=19, resources CC=18 |
| Silent failures | server.py:236 |
| Print logging | server.py: 2 instances |

**Refactor plan:**
- [ ] Extract server.py `main()` argument parsing into helper
- [ ] Fix silent failure at server.py:236
- [ ] Replace print statements with logging
- [ ] Break `register_resources_and_prompts()` into smaller registrations

---

## Execution Order

```
Phase 1: Batch 1 (Critical Core) + Batch 2 (Core Remaining) — in parallel
Phase 2: Batch 3 + Batch 4 + Batch 5 (All Tools) — in parallel, after core stabilizes
Phase 3: Batch 6 (Server/Resources) — after tools are refactored
Phase 4: Full test suite + regression check
Phase 5: Commit & Push
```

## Constraints
- All refactors must preserve the existing public API (MCP tool signatures)
- FastMCP `@mcp.tool()` decorator pattern must be maintained
- 252 tests must continue to pass after each batch
- No new dependencies allowed without justification
- Python 3.10+ compatibility required
