# Canvas MCP: Comprehensive Implementation Review & Improvement Plan

## Executive Summary

**Request**: Comprehensive review of Canvas MCP tool implementation against Canvas API spec with plan for changes.

**Key Findings**:
- ✅ **Strong foundation**: 50+ tools implemented, 167 tests exist, solid architecture
- ⚠️ **Critical gap**: No `create_assignment` tool despite being referenced in badm350-canvas-builder skill
- ⚠️ **Quality issues**: ~30 security tests skipped, 6 instances of `error: any`, sandbox disabled by default
- ⚠️ **Documentation gaps**: No API coverage matrix, unclear which Canvas endpoints are covered vs. missing

**Impact on BADM 350**: Currently blocked from automating assignment creation (30-40 assignments), requiring 2.5+ hours of manual work.

**Recommended Approach**: Two-track plan addressing both immediate needs (documentation + create_assignment) and long-term quality (testing, security, type safety).

---

## Track 1: Immediate Needs (CRITICAL for BADM 350)

**Timeline**: Week 1-2 (10-15 hours)
**Priority**: CRITICAL
**Goal**: Unblock course development and provide clear API documentation

### 1.1 Document Canvas API Coverage (5 hours)

**Create**: `/Users/vishal/teaching/badm350/docs/canvas-mcp/`

**Files to create**:

1. **quick-reference.md** (2 hours)
   - Most-used tools for course building (create_page, create_module, add_module_item, etc.)
   - Known limitations table with workarounds
   - Course-specific context (Course ID 67619)

2. **badm350-workflows.md** (2 hours)
   - Workflow: Build complete week (step-by-step with actual tool calls)
   - Workflow: Create rubric from template
   - Workflow: Publish Module A-E structure
   - Common error patterns with troubleshooting

3. **limitations.md** (1 hour)
   - Critical gaps affecting BADM 350:
     - ❌ **create_assignment** (HIGH IMPACT) - No tool exists despite skill reference
     - ❌ **create_quiz** (MEDIUM IMPACT) - Cannot automate exam creation
     - ❌ **upload_file** (MEDIUM IMPACT) - Cannot bulk upload files
   - Each gap should document:
     - Canvas API support status (endpoint exists?)
     - Current workaround
     - Estimated manual time cost
     - Implementation priority

**Validation**: Test documented workflows by creating Week 2 content in Canvas 67619.

---

### 1.2 Implement create_assignment Tool (5-10 hours)

**Location**: `/Users/vishal/code/canvas-mcp/src/canvas_mcp/tools/assignments.py`

**Why P0**:
- Referenced in badm350-canvas-builder skill but doesn't exist
- Blocks automation of 30-40 assignments (2.5+ hours manual work)
- Canvas API fully supports: `POST /api/v1/courses/:course_id/assignments`

**Implementation Steps**:

1. **Research existing patterns** (1 hour)
   - Study `create_page` implementation as model
   - Review Canvas API assignment endpoint documentation
   - Check parameter requirements (name, points, submission types, due dates, etc.)

2. **Write Python MCP tool** (2-3 hours)
```python
@mcp.tool()
@validate_params
async def create_assignment(
    course_identifier: str | int,
    name: str,
    description: str,
    points_possible: int,
    submission_types: str,  # "online_text_entry,online_upload"
    due_at: str | None = None,  # ISO 8601
    published: bool = False,
    grading_type: str = "points"
) -> str:
    """Create a new assignment in a Canvas course."""
    course_id = await get_course_id(course_identifier)

    assignment_data = {
        "assignment": {
            "name": name,
            "description": description,
            "points_possible": points_possible,
            "submission_types": submission_types.split(","),
            "published": published,
            "grading_type": grading_type
        }
    }

    if due_at:
        assignment_data["assignment"]["due_at"] = due_at

    response = await make_canvas_request(
        "post",
        f"/courses/{course_id}/assignments",
        data=assignment_data
    )

    if "error" in response:
        return f"Error: {response['error']}"

    return json.dumps({
        "assignment_id": response["id"],
        "name": response["name"],
        "html_url": response["html_url"]
    }, indent=2)
```

3. **Add tests** (1-2 hours)
   - Create `tests/tools/test_assignments.py`
   - Test success case, validation errors, Canvas API errors
   - Test with BADM 350 course (67619)

4. **Update skill reference** (30 min)
   - Update `/Users/vishal/.claude/skills/badm350-canvas-builder/SKILL.md`
   - Change from placeholder to actual working tool
   - Add example usage

5. **Document in quick-reference.md** (30 min)

**Acceptance Criteria**:
- [ ] Tool creates assignment successfully in Canvas 67619
- [ ] All required parameters validated
- [ ] Returns assignment ID and URL
- [ ] 3+ tests passing
- [ ] Skill updated to use real tool
- [ ] Documented in quick-reference.md

---

## Track 2: Quality & Security (HIGH Priority)

**Timeline**: Weeks 2-4 (40-50 hours)
**Priority**: HIGH (production readiness)
**Goal**: Address security, testing, and type safety gaps

### 2.1 Security Hardening (12 hours)

**Critical Issues Found**:
- Sandbox disabled by default (`ENABLE_TS_SANDBOX=False`)
- ~30 security tests skipped
- No token validation on startup
- Environment variables not minimized

**Implementation**:

1. **Enable sandbox by default** (2 hours)
   - Update `/Users/vishal/code/canvas-mcp/src/canvas_mcp/core/config.py`
   - Change default to `ENABLE_TS_SANDBOX=True`
   - Document opt-out for trusted environments

2. **Add token validation** (3 hours)
   - Validate Canvas token on MCP server startup
   - Implement `validate_canvas_token()` in config.py
   - Fail fast with clear error message if invalid

3. **Minimize environment exposure** (2 hours)
   - Review subprocess creation in `tools/code_execution.py`
   - Only pass required env vars (PATH, NODE_PATH, Canvas credentials)
   - Remove HOME, USER, SSH_*, AWS_*, etc.

4. **Unskip security tests** (5 hours)
   - Fix tests in `tests/test_security.py`
   - Verify: token validation, sandbox enforcement, network restrictions
   - All security tests must pass before production

**Validation**: Run full security test suite, verify 100% pass rate.

---

### 2.2 Type Safety Improvements (8 hours)

**Issues Found**: 6 instances of `catch (error: any)` in TypeScript code

**Files to fix**:
- `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/canvas/grading/bulkGrade.ts:73`
- `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/canvas/grading/gradeWithRubric.ts:145`
- `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/canvas/discussions/bulkGradeDiscussion.ts` (3 instances)
- `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/client.ts:134`

**Implementation**:

1. **Create error types module** (2 hours)
```typescript
// src/canvas_mcp/code_api/types/errors.ts
export class CanvasAPIError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public details?: unknown
  ) {
    super(message);
    this.name = 'CanvasAPIError';
  }
}

export function formatError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
```

2. **Replace all `error: any`** (4 hours)
```typescript
// ❌ BEFORE
catch (error: any) {
  const errorMsg = error.message || String(error);
}

// ✅ AFTER
catch (error: unknown) {
  const errorMsg = formatError(error);
}
```

3. **Add input validation** (2 hours)
   - Create `validation.ts` module
   - Validate course IDs, assignment IDs before API calls
   - Throw ValidationError with clear messages

**Validation**: TypeScript compilation with `--strict` mode passes without warnings.

---

### 2.3 Testing Infrastructure (20 hours)

**Current State**: 167 Python tests exist, but no TypeScript test framework configured.

**Implementation**:

1. **Set up Vitest for TypeScript** (4 hours)
```bash
npm install --save-dev vitest @vitest/ui @types/node
```

Create `vitest.config.ts`:
```typescript
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/canvas_mcp/code_api/**/*.ts'],
      lines: 80,
      functions: 80,
      branches: 75
    }
  }
});
```

2. **Add coverage tools for Python** (2 hours)
```bash
pip install pytest-cov coverage
```

Update `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = "-v --tb=short --cov=src/canvas_mcp --cov-report=term-missing --cov-report=html"
```

3. **Create test fixtures** (4 hours)
   - Mock Canvas API responses
   - Test data for courses, assignments, submissions
   - Reusable across test files

4. **Write TypeScript tests** (10 hours)
   - Unit tests for validation functions
   - Integration tests for bulk operations
   - Mock Canvas API calls
   - Target: 80%+ coverage

**Validation**: Run `npm test` and `pytest`, verify ≥80% coverage for core modules.

---

## Track 3: Comprehensive Documentation (MEDIUM Priority)

**Timeline**: Weeks 3-5 (25-30 hours)
**Priority**: MEDIUM (can defer post-course launch)
**Goal**: Complete API reference and coverage analysis

### 3.1 API Coverage Matrix (15 hours)

**Create**: `/Users/vishal/teaching/badm350/docs/canvas-mcp/api-coverage-matrix.md`

**Methodology**:
1. Scrape Canvas API documentation (all_resources.html)
2. Extract all endpoint categories (~80 resources)
3. Map each endpoint → MCP tool (if exists)
4. Calculate coverage percentages
5. Prioritize gaps by BADM 350 impact

**Output Format**:

| Category | Total Endpoints | Covered | Missing | Coverage % | Priority |
|----------|-----------------|---------|---------|------------|----------|
| Assignments | 18 | 2 | 16 | 11% | HIGH |
| Pages | 12 | 8 | 4 | 67% | LOW |
| Modules | 15 | 9 | 6 | 60% | LOW |
| Discussions | 20 | 10 | 10 | 50% | MEDIUM |
| Quizzes | 25 | 0 | 25 | 0% | MEDIUM |
| Files | 15 | 0 | 15 | 0% | MEDIUM |

**For each gap**:
- Canvas API endpoint URL
- Parameters required
- Use case for BADM 350
- Implementation effort estimate
- Workaround (if exists)

**Effort**: 15 hours (systematic, detailed analysis)

---

### 3.2 Complete API Reference (10 hours)

**Create**: `/Users/vishal/teaching/badm350/docs/canvas-mcp/api-reference.md`

**Format**: Alphabetical listing of all 80+ tools

**Each entry**:
- Function signature with types
- Parameter descriptions
- Return value structure
- Canvas API endpoint mapping
- Example usage (copy-paste ready)
- Common errors
- Related tools

**Example**:
```markdown
## create_page

**Description**: Creates a new page in a Canvas course

**Signature**:
create_page(
    course_identifier: str | int,
    title: str,
    body: str,
    published: bool = True
)

**Canvas API**: POST /api/v1/courses/:course_id/pages
**Docs**: https://canvas.instructure.com/doc/api/pages.html

**Example**:
result = create_page(
    course_identifier="67619",
    title="Week 1 Start Here",
    body="<div>...</div>"
)

**Returns**:
{
  "page_id": 12345,
  "url": "week-1-start-here",
  "published": true
}

**Common Errors**:
- 401: Invalid API token
- 422: Invalid HTML
```

**Effort**: 10 hours (80+ tools × 7 minutes each)

---

## Implementation Schedule

### Week 1 (CRITICAL)
- [ ] Document Canvas API coverage (quick-reference, workflows, limitations) — 5 hours
- [ ] Start create_assignment implementation — 3 hours

### Week 2 (HIGH)
- [ ] Complete create_assignment tool — 2-7 hours (7 remaining)
- [ ] Test with BADM 350 course — 1 hour
- [ ] Begin security hardening — 4 hours

### Week 3 (HIGH)
- [ ] Complete security hardening — 8 hours (8 remaining)
- [ ] Fix type safety issues — 8 hours

### Week 4 (MEDIUM)
- [ ] Set up testing infrastructure — 6 hours
- [ ] Write initial tests — 6 hours

### Week 5 (MEDIUM)
- [ ] Complete test coverage — 8 hours
- [ ] Begin API coverage matrix — 7 hours

### Weeks 6-7 (DEFER)
- [ ] Complete API coverage matrix — 8 hours (8 remaining)
- [ ] Write complete API reference — 10 hours

**Total Effort**: 75-85 hours (approximately 2 engineer-months)

---

## Critical Files

### To Create (Track 1 — Immediate)
1. `/Users/vishal/teaching/badm350/docs/canvas-mcp/quick-reference.md`
2. `/Users/vishal/teaching/badm350/docs/canvas-mcp/badm350-workflows.md`
3. `/Users/vishal/teaching/badm350/docs/canvas-mcp/limitations.md`
4. `/Users/vishal/code/canvas-mcp/src/canvas_mcp/tools/assignments.py` (add create_assignment)
5. `/Users/vishal/code/canvas-mcp/tests/tools/test_assignments.py`

### To Modify (Track 2 — Quality)
6. `/Users/vishal/code/canvas-mcp/src/canvas_mcp/core/config.py` (enable sandbox, add token validation)
7. `/Users/vishal/code/canvas-mcp/src/canvas_mcp/tools/code_execution.py` (minimize env vars)
8. `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/client.ts` (fix `error: any`)
9. `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/canvas/grading/bulkGrade.ts` (fix `error: any`)
10. `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/canvas/grading/gradeWithRubric.ts` (fix `error: any`)
11. `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/canvas/discussions/bulkGradeDiscussion.ts` (fix 3× `error: any`)

### To Create (Track 2 — Quality)
12. `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/types/errors.ts`
13. `/Users/vishal/code/canvas-mcp/src/canvas_mcp/code_api/validation.ts`
14. `/Users/vishal/code/canvas-mcp/vitest.config.ts`
15. `/Users/vishal/code/canvas-mcp/tests/typescript/fixtures/mockData.ts`

### To Create (Track 3 — Documentation)
16. `/Users/vishal/teaching/badm350/docs/canvas-mcp/api-coverage-matrix.md`
17. `/Users/vishal/teaching/badm350/docs/canvas-mcp/api-reference.md`

---

## Success Criteria

### Track 1 (Immediate)
- [ ] Documentation enables building Week 2-16 without confusion
- [ ] create_assignment tool works in Canvas 67619
- [ ] Can automate 30-40 assignments (save 2.5 hours)
- [ ] All workarounds documented for known gaps

### Track 2 (Quality)
- [ ] Zero skipped security tests
- [ ] Zero `error: any` in TypeScript
- [ ] Sandbox enabled by default
- [ ] ≥80% test coverage for core modules

### Track 3 (Documentation)
- [ ] Complete API coverage matrix (all Canvas endpoints mapped)
- [ ] Complete API reference (all 80+ tools documented)
- [ ] New users can adopt tools without 1:1 assistance

---

## Verification Plan

### Phase 1: create_assignment Tool
1. Create test assignment in Canvas 67619 with tool
2. Verify assignment appears correctly in Canvas UI
3. Test with rubric association
4. Verify due dates, submission types work
5. Test error handling (invalid course ID, missing parameters)

### Phase 2: Security Hardening
1. Run full security test suite: `pytest -m security`
2. Verify all tests pass (no skipped)
3. Test sandbox enforcement: attempt network access, should fail
4. Verify token validation on startup
5. Check subprocess environment variables (should be minimal)

### Phase 3: Type Safety
1. Run TypeScript compiler: `npx tsc --noEmit --strict`
2. Should have zero errors
3. Run ESLint: `npx eslint src/canvas_mcp/code_api/`
4. No `@typescript-eslint/no-explicit-any` violations

### Phase 4: Test Coverage
1. Run Python tests: `pytest --cov=src/canvas_mcp --cov-report=html`
2. Verify ≥80% coverage for core modules
3. Run TypeScript tests: `npm test`
4. Verify ≥80% coverage for code_api

### Phase 5: Documentation
1. Use quick-reference.md to build Week 2 content
2. Should take <20 minutes without confusion
3. Verify all tool examples are copy-paste ready
4. Test common workflows end-to-end

---

## Risk Mitigation

### Risk 1: create_assignment Tool Complexity
**Probability**: MEDIUM
**Impact**: HIGH (blocks automation)
**Mitigation**:
- Start with minimal viable tool (name, points, due date only)
- Add advanced features iteratively (rubrics, groups, etc.)
- Keep manual workaround as fallback

### Risk 2: Security Test Failures
**Probability**: MEDIUM
**Impact**: HIGH (cannot enable sandbox)
**Mitigation**:
- Fix tests incrementally
- Document any tests that must remain skipped with rationale
- Consider containerized sandbox as ultimate fallback

### Risk 3: Time Overrun on Documentation
**Probability**: LOW
**Impact**: LOW (can defer Track 3)
**Mitigation**:
- Prioritize Track 1 (immediate needs)
- Defer Track 3 to post-semester
- Focus on BADM 350-specific workflows first

---

## Recommended Approach

### Option A: Phased Implementation (RECOMMENDED)
**Week 1-2**: Track 1 only (documentation + create_assignment)
**Week 3-4**: Track 2 (security + type safety)
**Post-semester**: Track 3 (comprehensive docs)

**Pros**: Unblocks course development immediately, addresses quality systematically
**Cons**: Full documentation delayed 3-4 months
**Best for**: Active course development timeline

### Option B: Documentation-First
**Week 1-2**: Tracks 1 + 3 (all documentation)
**Week 3-5**: Track 2 (quality improvements)

**Pros**: Complete reference available early
**Cons**: Quality issues persist longer, more upfront effort
**Best for**: Research/planning phase, not active course build

### Option C: Quality-First
**Week 1-3**: Track 2 (security + tests)
**Week 4-5**: Track 1 (documentation)
**Week 6-7**: Track 3 (comprehensive)

**Pros**: Production-ready codebase first
**Cons**: Course development blocked 3+ weeks
**Best for**: Pre-semester preparation, not mid-build

**My Recommendation**: **Option A** — You're actively building BADM 350 content now, need immediate unblocking via Track 1. Quality improvements (Track 2) can happen in parallel during Weeks 3-4 without blocking course work.

---

## Next Steps (This Week)

1. **Review this plan** — Approve or request modifications
2. **Create docs directory**: `mkdir -p /Users/vishal/teaching/badm350/docs/canvas-mcp/`
3. **Write quick-reference.md** (2 hours) — Most-used tools, limitations
4. **Write badm350-workflows.md** (2 hours) — Week build workflow
5. **Start create_assignment tool** (3 hours) — Basic implementation
6. **Test with Week 2** — Validate workflows and new tool

**Goal for Week 1**: Have documentation + create_assignment working, use to build Week 2-3 content.
