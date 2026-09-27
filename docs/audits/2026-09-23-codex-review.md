# Codex second review of the 2026-09-23 prompt audit

**Reviewer:** Codex CLI 0.154.0, `gpt-6-astra`, reasoning effort low, read-only sandbox
**Input:** `docs/audits/2026-09-23-prompt-audit.md` (first version) and the repo at `2265662`, with no
other context from the audit session · **Thread:** `01a0d0a3-3e72-72c2-b69c-9a46d7c48a83` · **Run:** 2026-09-23 (CDT)

## Disposition (added by the canvas-mcp session after checking each point against the code)

Codex's verdicts are reproduced verbatim below this section. Each WRONG verdict and each hunk
objection was re-checked by reading the cited code before the report was changed.

| Codex point | Checked against | Disposition |
|---|---|---|
| T-H10 WRONG ("always" overstated) | `resources.py:24-34`; `courses.py:321-325` requests `include[]=syllabus_body` because Canvas omits it otherwise | **Partly accepted.** Wording corrected to "never requests `syllabus_body`, which Canvas omits unless asked"; finding and fix kept |
| T-M3 WRONG | `listSubmissions.ts:38,45` already documents raw output and names/emails | **Dropped** |
| S-M7 WRONG | `CLAUDE.md:26,30`; 20 files incl. `__init__`, 1662 tests still "900+" | **Dropped** |
| S-M6 UNVERIFIED | Canvas revision retention for API edits not provable from the repo | **Downgraded to Low (flag)**; the same unverified claim was **removed** from the D-H2 hunk |
| `bulkGrade.ts` removes exported `GradeResult.points` | `bulkGrade.ts:5-14`, examples `:132,139` | **Accepted.** Field kept with `@deprecated`; examples no longer use it |
| `get_discussion_with_replies` promises the topic body | `discussions.py:690-724` (title + 200-char previews) | **Accepted.** Hunk rewritten |
| `gradeWithRubric.ts` "partial assessment is still saved" | `gradeWithRubric.ts:180-188` | **Accepted.** Now "is sent anyway, may have been saved" |
| `list_submissions` "one line per student" | `assignments.py:344-345` | **Accepted.** Now "one record per student" |
| `execute_typescript` hunk drops published isolation/storage/limits text; "output reports mode" is conditional | `code_execution.py:370-374,701-717` | **Accepted.** Those details restored; the reporting sentence is now conditional on sandboxing |
| `create_discussion_topic` "unpublish it afterwards" advice | `discussions.py:947-959` | **Accepted.** Replaced with `delayed_post_at` / confirm-first; the builder-skill hunk is fixed the same way |
| D-H4 front-page rule landed on `notify_of_update` | the hunk | **Accepted.** Now attached to `published` |
| D-H1 notification delivery not established by code | `discussions.py:1130` | **Accepted.** "may notify … depending on their notification settings" |
| D-M1 ignores access/unlock restrictions | `modules.py`, `pages.py` | **Accepted.** Caveat added |
| T-H13 `bulkGrade` wording ignores skips / dry run | `bulkGrade.ts` | **Accepted.** |
| S-H9 leaves line 225 "into one call" | `canvas-peer-review-manager/SKILL.md:225` | **Accepted.** Hunk added |
| D-M8 proposed instructions over-generalize (single-recipient sends are immediate; resources and TS reads are unfenced) | `messaging.py:503-508`; `resources.py:34,61`; `client.ts:149` | **Accepted.** Instruction text in the report revised (out of diff) |
| S-M9: don't remove the example's `dry_run: true` | `assignments.py:1024` | **Accepted.** Noted in the report (out of diff) |
| S-M8 "Student read tools" still overgeneralizes | `student_tools.py` | **Accepted.** Proposed wording now "personal student-tracking tools" |
| T-H2 / T-H3 would change the tested discovery contract | `tests/tools/test_discovery.py:122-133,185-189` | **Accepted.** Noted in the report: those need a schema-version decision (out of diff) |
| Publication warning outdated | `docs/.assetsignore` | **Accepted.** `audits/` was added after the first version; report updated |
| "text in the TS slice" is not in the report | the report | **Accepted.** Replacement text now given inline for T-M1, T-M2, T-M11 |

Net effect: **74 findings (30 High, 25 Medium, 19 Low)**, down from 76. The proposed diff is now
**49 hunks**; the stage-2 branch applies **47** (T-M5 and T-M10 wait for Vishal).

---

## Codex output (verbatim)

Verified all **58 IDs: 54 CONFIRMED, 3 WRONG, 0 STALE, 1 UNVERIFIED**. My earlier progress count of 59 was incorrect. All 46 proposed hunks match the current tree. In-memory verification preserved all 103 tool input contracts and reduced undescribed parameters from 16 to zero. However, several replacements introduce inaccurate descriptions or remove published information. No files were changed and no Canvas calls were made. Verdicts concern source facts; the report’s predictions about model behavior remain untested.

Paths below abbreviate `src/canvas_mcp/tools/` as **tools/** and `src/canvas_mcp/code_api/` as **api/**.

| ID | Verdict | Evidence (file:line + one-line quote or fact) | Note on the proposed replacement text (or "n/a") |
|---|---|---|---|
| D-H1 | CONFIRMED | `tools/discussions.py:1091,1130,1133`: brief description; sends `published=True`, with optional scheduling. | Publication is supported. Actual notification delivery is not established by this implementation; describe permission as Canvas’s announcement permission. |
| D-H2 | CONFIRMED | `tools/pages.py:375–388`: sends `wiki_page.body=new_content`, replacing the body. | Replacement guidance is accurate; UI revision recovery was not independently established here. |
| D-H3 | CONFIRMED | `tools/rubrics.py:1648–1671`; `tools/content_migrations.py:258–273,386–395`: no parameter documentation. Registry independently shows 16 missing descriptions. | Added descriptions match signatures and behavior. Association label exists at `tools/rubrics.py:949`. |
| D-H4 | CONFIRMED | `tools/pages.py:109,193`: both trailing rules are absent from registered descriptions and parameter descriptions. | Diff attaches the front-page rule to **`notify_of_update`**, not `published` as promised. Deleted bulk rule was not published. |
| D-H5 | CONFIRMED | `tools/discussions.py:915–936,947`: no `published` input; request hard-codes `True`. | “Unpublish afterwards” cannot ensure it stays hidden during creation. |
| T-H1 | CONFIRMED | `tools/discovery.py:233–243`: extracts first JSDoc. Actual results are private-helper descriptions from all three grading files. | New extractor selects their public JSDoc correctly. “Only description” overstates matters: other discovery/resource paths exist. |
| T-H2 | CONFIRMED | `tools/discovery.py:40,163–168`: 2,000-character cap. Independently measured public JSDoc offsets: 2,321 / 2,236 / 12,059. | Suggested digest would change the existing `file`/`content` response contract; not included in diff. |
| T-H3 | CONFIRMED | `tools/discovery.py:196–199`; `src/canvas_mcp/server.py:471–476`: TS discovery/resources remain available when execution is disabled. | Removing the section outright changes schema version 2’s tested shape; preserve shape or version the change. |
| T-H4 | CONFIRMED | `api/canvas/grading/bulkGrade.ts:6,61–67`: `points` is declared but never forwarded. Examples contain it at lines 132 and 139. | Removing an exported interface field is a TypeScript source-contract change; examples remain inconsistent. |
| T-H5 | CONFIRMED | `api/canvas/grading/bulkGrade.ts:59–72`: dry run skips grading validation, increments `graded`, and prints “✓ Graded.” | Accurately warns about validation limitations. “Writes nothing” applies to the helper’s writes, not arbitrary callback side effects. |
| T-H6 | CONFIRMED | `api/canvas/grading/gradeWithRubric.ts:142–188`: checks grading flag; sends partial assessments before checking completeness; ignores `grade` on rubric path. | **“A partial assessment is still saved” is too strong**: saving may fail or be uncertain. Say “may have been saved.” |
| T-H7 | CONFIRMED | `api/canvas/discussions/bulkGradeDiscussion.ts:231–265,404–409,511–522,590`: participants only, appended comment, first ten results. | Accurate. Instructor/TA entries are not filtered by enrollment role. |
| T-H8 | CONFIRMED | `api/canvas/discussions/listDiscussions.ts:23,30–32`; `tools/discussions.py:87–101`: implementation lacks the announcement filter described by its JSDoc. | Accurate correction for this endpoint. |
| T-H9 | CONFIRMED | `api/canvas/courses/getCourseDetails.ts:22–29`: interpolates identifier directly; does not request syllabus. | Accurate: no course-code resolution; syllabus is not requested. |
| T-H10 | WRONG | `src/canvas_mcp/resources/resources.py:24–34`: missing include is real, but it returns the syllabus whenever the response contains one—**not “always” the fallback**. | Adding the include is justified. Returned syllabus remains unfenced. |
| T-H11 | CONFIRMED | `src/canvas_mcp/resources/resources.py:117–127`: single-segment template; independently reproduced `NotFoundError` for nested path. | Wildcard proposal needs verification. Path example already exists in source docstring, but not the explicit resource description. |
| T-H12 | CONFIRMED | `tools/code_execution.py:363–379,674–725`; `api/client.ts:104–149`: missing output/import/write/privacy explanations are real. | Replacement loses published isolation/storage details and overstates mode reporting; see hunks below. |
| T-H13 | CONFIRMED | `tools/code_execution.py:788,794,804–818`; `api/canvas/communications/sendMessage.ts:50`: Inbox only; booster present; root `batching.ts` receives empty category/description. | Inbox correction is accurate. Bulk description should allow skipped submissions and dry runs. |
| S-H1 | CONFIRMED | `skills/canvas-course-qc/SKILL.md:132`; `tools/rubrics.py:1316`: skill names nonexistent `list_all_rubrics`. | Correct replacement: `list_rubrics`. |
| S-H2 | CONFIRMED | `skills/canvas-week-plan/SKILL.md:20`; `tools/student_tools.py:132`: actual parameter is `days`. | Correct. History search found no `days_ahead` under `src`. |
| S-H3 | CONFIRMED | `AGENTS.md:368`; `tools/assignments.py:1044,1253`: delay is seconds and passed directly to `asyncio.sleep`. | Correct default: `1.0` seconds. |
| S-H4 | CONFIRMED | `skills/canvas-course-builder/SKILL.md:95,192`; `tools/modules.py:229`, `tools/pages.py:296`, `tools/discussions.py:947`: publication defaults contradict skill. | Explicit module/page draft settings are correct; later unpublishing a discussion does not prevent initial exposure. |
| S-H5 | CONFIRMED | `skills/canvas-bulk-grading/SKILL.md:65,124–142`; `api/canvas/grading/bulkGrade.ts:20,59`: example omits `dryRun`, so helper writes. | Correct addition and spelling. |
| S-H6 | CONFIRMED | `.claude/skills/week-plan/SKILL.md:2,20`; `.claude/skills/morning-check/SKILL.md:14`; canonical files differ. | Directory-symlink targets resolve correctly. Other three **SKILL.md files**, not their directories, are symlinks. |
| S-H7 | CONFIRMED | `CLAUDE.md:93,96,102`; `pyproject.toml:62,74`: old union guidance conflicts with enabled pyupgrade rules. | Correct replacement. |
| S-H8 | CONFIRMED | `AGENTS.md:370`; `tools/assignments.py:1024`, `tools/accessibility.py:301`: registry has only two `dry_run` parameters and fifteen confirmation-token tools. | Correct distinction. |
| S-H9 | CONFIRMED | `skills/canvas-peer-review-manager/SKILL.md:114–119,225`; `tools/messaging.py:718–732,1084–1112`: first calls preview, not send. | Corrects main workflow, but leaves line 225’s “into one call” claim unchanged. Existing “dry run **or review**” wording alone is not false. |
| S-H10 | CONFIRMED | `AGENTS.md:453–470`: personal paths and approval specifically from Vishal appear in public agent guidance. | Audience correction is justified; proposed one-line policy materially narrows the existing approval rule. |
| S-H11 | CONFIRMED | `skills/canvas-bulk-grading/SKILL.md:15`; `AGENTS.md:328`; `tools/rubrics.py:1648`: guarded update tool exists. | Correct improvement. Canvas UI remains a valid option; the old advice is incomplete, not impossible. |
| S-H12 | CONFIRMED | `skills/canvas-morning-check/SKILL.md:96`; `tools/messaging.py:684–686`: reminder helper composes assignment-specific peer-review messages. | Generic deadline messaging belongs with `send_conversation`. |
| D-M1 | CONFIRMED | `tools/pages.py:296–305`; `tools/modules.py:229–240`: defaults appear in parameter documentation, not summaries. | Defaults are correct; unconditional immediate student visibility overlooks access/unlock restrictions. |
| D-M2 | CONFIRMED | `tools/modules.py:413,477,734`; `tools/rubrics.py:1204`: four labels exist. | Rewording retains their substantive constraints. Whether emphasis harms model behavior is unverified. |
| D-M3 | CONFIRMED | `tools/discussions.py:807–810,924–927`; `tests/tools/test_discussions.py:707–719`: warnings and text assertions exist. | Both assertions pass against patched descriptions in memory. |
| D-M4 | CONFIRMED | `tools/discussions.py:668,678–701`: “Enhanced” description; same entries endpoint, with topic **title** added. | **Wrong replacement:** no topic body is returned; entries are shortened at lines 713–715. |
| D-M5 | CONFIRMED | `tools/enrollment.py:55–56`: named login/email example is published as parameter text. | Generic example preserves the contract. |
| D-M6 | CONFIRMED | `tools/rubrics.py:1581`: parameter says “see docstring above”; registered tool description contains the schema/example. | Correct terminology; no schema/example text is lost. |
| D-M7 | CONFIRMED | `tools/assignments.py:309–345`; `tools/admin_tools.py:125–163`; `tools/modules.py:42–105`: brief summaries omit substantial output details. Registry confirms 42 short read descriptions. | “One line per student” is false: exemplar emits a multiline record. Shortness alone does not establish every tool needs expansion. |
| D-M8 | CONFIRMED | `src/canvas_mcp/server.py:423`: constructor supplies only `name`. | Proposed instructions falsely generalize all messages as two-call and all Canvas text as fenced. |
| T-M1 | CONFIRMED | `api/canvas/communications/sendMessage.ts:22–29,50`: aliases documented; immediacy/no-confirmation not documented. | No replacement text actually supplied in diff. |
| T-M2 | CONFIRMED | `api/canvas/discussions/postEntry.ts:17–24,39–42`: immediate POST, no confirmation or deduplication. | n/a |
| T-M3 | WRONG | `api/canvas/assignments/listSubmissions.ts:38,45`: already documents raw output and names/emails. Lines 51–63 interpolate identifiers without numeric-only validation. | Unsubmitted-record coverage is unstated, but “numeric ID only” and missing user-detail documentation overstate the defect. |
| T-M4 | CONFIRMED | `api/canvas/grading/bulkGrade.ts:90`; `api/canvas/discussions/bulkGradeDiscussion.ts:415`; `api/index.ts:24`: booster text exists. | Two JSDoc boosters removed; index comment remains. |
| T-M5 | CONFIRMED | `src/canvas_mcp/core/untrusted_content.py:152–155`; `tools/courses.py:345–351`: notice excludes current user as author although their syllabus is fenced too. | Corrects origin claim and preserves instruction/data separation. Predicted refusal behavior is untested. |
| T-M6 | CONFIRMED | `src/canvas_mcp/resources/resources.py:49–61`: assignment HTML returned directly. | Proposed fencing is appropriate, but absent from diff. |
| T-M7 | CONFIRMED | `tools/discovery.py:31–40,70,101–110,124–155`: substring matching, caps, and search root are not explained in parameter docs. | n/a |
| T-M8 | CONFIRMED | `api/client.ts:25,46–59`: mandatory initialization claim contradicts automatic environment initialization. | n/a |
| T-M9 | CONFIRMED | `api/index.ts:14,31–32`; `api/canvas/index.ts:12,25–29`; `tools/code_execution.py:537–545`: examples do not match script-relative module layout. | Suggested `./index.js` and full module path match the supported layout. |
| T-M10 | CONFIRMED | `src/canvas_mcp/core/write_confirmation.py:310–313`; `tools/messaging.py:575–579,727–731`: no explicit “wait for approval.” | Replacement adds that instruction. It does not technically enforce human approval or block unattended execution. |
| T-M11 | CONFIRMED | `src/canvas_mcp/resources/resources.py:67,106–115`: undescribed argument, identity sentence, repeated course code, open-ended suggestion. | No four-line replacement is actually included; stylistic impact is untested. |
| S-M1 | CONFIRMED | `CLAUDE.md:315,341–344,457–490`: extensive history remains in startup guidance. | Historical entries are dated; the old SDK statement is not a current dependency claim. Preserve operational/privacy rules at lines 458–466. |
| S-M2 | CONFIRMED | `CLAUDE.md:45–53,61–68`: main-branch allowance conflicts with read-only primary checkout guidance. | Consolidation is justified; not in diff. |
| S-M3 | CONFIRMED | `AGENTS.md:203–214,369`; `skills/canvas-bulk-grading/SKILL.md:62–65`; `src/canvas_mcp/server.py:471`: unconditional routing names an optional tool. | Recommendation hunk improves one location; table/tree/skill remain inconsistent. |
| S-M4 | CONFIRMED | `skills/canvas-course-builder/SKILL.md:194`; `tools/content_migrations.py:258–272`: skill omits available full-course copying. | Accurate addition. Per-page copying remains valid. |
| S-M5 | CONFIRMED | `skills/canvas-accessibility-auditor/SKILL.md:35–39,165–173`; `tools/accessibility.py:673–1007,297–317`: twenty scanner types and four automated fix categories exist. | Add only supported automated fixes; it cannot automatically resolve every listed issue. |
| S-M6 | UNVERIFIED | `skills/canvas-accessibility-auditor/SKILL.md:190`; `tools/pages.py:385–388`: repository performs a PUT but does not implement or verify Canvas revision retention. | Repository comments are insufficient independent evidence for the API/UI history claim. |
| S-M7 | WRONG | `CLAUDE.md:26,30`: **20 Python files including `__init__.py`**, nineteen implementation modules; 1,662 collected tests still satisfy “900+.” | Counts may be unhelpfully imprecise, but are not factually wrong. |
| S-M8 | CONFIRMED | `skills/canvas-week-plan/SKILL.md:146`; `tools/student_write.py:652,909,961`: three student-write names lack `get_my_`. | “Student read tools” still overgeneralizes shared reads. Say “personal student-tracking tools.” |
| S-M9 | CONFIRMED | `skills/canvas-bulk-grading/SKILL.md:60,65,90,108,114,162`: repeated dry-run directions exist. | Do not remove executable example’s `dry_run: true`; deleting it changes example behavior to a real write. |

## Hunks that break a contract or drop published text

- **`bulkGrade.ts`, interface hunk:** removes exported `GradeResult.points` (`api/canvas/grading/bulkGrade.ts:5–14`). Although ignored at runtime, typed callers using that property can stop compiling. Deprecation is compatible; removal is not.
- **`discussions.py`, `get_discussion_with_replies` hunk:** falsely promises the topic body. Current output includes its title and entry previews, with replies also shortened (`tools/discussions.py:694–724,759–775`).
- **`gradeWithRubric.ts`, JSDoc hunk:** “partial assessment is still saved” guarantees something the code explicitly calls uncertain (`api/canvas/grading/gradeWithRubric.ts:180–188`).
- **`assignments.py`, `list_submissions` hunk:** promises “one line per student”; actual output is four labeled lines per record (`tools/assignments.py:344–345`).
- **`code_execution.py`, description hunk:** removes published information about local temporary-file deletion, container execution avoiding host script storage, and explicit memory/CPU limits (`tools/code_execution.py:370–374`). It also weakens the best-effort isolation warning despite the documented bypass (`tools/code_execution.py:469–480,593–599`). “Output reports the mode and limits” is conditional: the sandbox section appears only when enabled (`tools/code_execution.py:701–717`).
- **`discussions.py`, creation hunk:** “To keep it hidden, unpublish it afterwards” is not a safe guarantee: creation publishes before any later update (`tools/discussions.py:947–959`). The builder-skill replacement repeats this problematic advice.

**Related proposals outside the unified diff:**

- **D-M8:** single-recipient messages send immediately (`tools/messaging.py:503–508`); resources and TypeScript reads are not universally fenced (`src/canvas_mcp/resources/resources.py:34,61`; `api/client.ts:149`). Proposed server instructions must retain these exceptions.
- **T-H2/T-H3:** replacing `content` or omitting `code_execution_api` changes tested discovery contracts (`tests/tools/test_discovery.py:122–133,185–189`).
- **S-M9:** removing the example’s `dry_run: true` activates writes because the default is false (`tools/assignments.py:1024`).

## Tests that pin changed text

- `tests/tools/test_discussions.py:707–719`: requires `create_announcement` plus “do not” or “never” in both discussion-write descriptions. **Both pass with the proposed descriptions.**
- `tests/security/test_untrusted_content.py:535,898`: compares notices with imported `UNTRUSTED_NOTICE`; these assertions do **not** pin its literal wording.
- `tests/tools/test_rubrics.py:1308–1312`: pins `list_rubrics` registration and absence of `list_all_rubrics`; consistent with the skill correction.
- `tests/tools/test_discovery.py:122–133,185–189`: pins response keys and truncated `content`, relevant to the proposals outside the diff.
- Searches found no additional assertions pinning the removed prose. Full suites were not run; the in-memory schema/description checks and collection of **1,662 tests** were independently completed.

## Additional observations

- The report’s publication warning is already outdated: `docs/.assetsignore:15–16` excludes `audits/`.
- The front-page rule becomes client-visible after the patch, but under the wrong parameter (`notify_of_update`).
- Adding syllabus retrieval without fencing leaves the newly retrieved resource text unmarked (`src/canvas_mcp/resources/resources.py:34`).
- Several findings refer to replacement text “in the TS slice” that is absent from the supplied report; those unspecified replacements cannot be reviewed.