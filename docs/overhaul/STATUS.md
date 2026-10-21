# Canvas MCP overhaul handoff

Date: 2026-10-20. Author: [Codex overhaul]. Branch: `overhaul/2026-10`.
Baseline: `b271b63`. Scope: the maintainer's local brief, both phases.

## Outcome and commits

Phase 1 was committed before production changes. All seven ranked implementation
tasks and all five independent review findings are complete. Public tool names,
arguments, result schemas and annotations match the six baseline profiles.
The proposed breaking changes in [PLAN.md](PLAN.md#breaking-changes-needs-vishal)
remain unimplemented. Commits are local; no push, PR, merge, tag, deployment or
live Canvas operation was performed. No learner records were accessed.

| Commit | Finished work | Full Python suite before commit |
|---|---|---|
| `18b4818` | Phase 1: architecture, evidence, ranked plan, compatibility limits, Review Focus | 3329 passed, 20 skipped |
| `4eb6029` | Prove announcement type before preview or deletion; invalidate changed targets | 3346 passed, 20 skipped |
| `7af1031` | Bound text stripping and email redaction; retain complete content | 3357 passed, 20 skipped |
| `4be18d9` | Bound accessibility scans and remove a discarded search | 3389 passed, 20 skipped |
| `7b00800` | Isolate caller statistics, fence author text, propagate read errors and verify fixes | 3404 passed, 20 skipped |
| `50ee7b5` | Verify pinned publisher bytes; narrow automation credentials and separate report publication | 3416 passed, 20 skipped |
| `1d17fd6` | Omit third-party labels from automatic startup context; parse statistics as data | 3432 passed, 20 skipped |
| `5e8dc3e` | Share exact grade-number helper, update maintained docs, exclude local files from packages | 3440 passed, 20 skipped |
| `d37b9d1` | Preserve quoted HTML and real attribute boundaries; request page bodies; correct all review findings | 3487 passed, 20 skipped |

The final documentation commit contains this report and completion marks in the
plan; its own SHA is visible in `git log`, rather than a self-referential value.
Ruff and mypy were clean before each implementation commit. No dependencies or
lockfiles changed; certifi remains pinned at **2026.10.19**.

## What changed for callers

- Announcement deletion refuses ordinary discussions, malformed records and
  target-type changes, while retaining the existing two-call confirmation flow.
- Long malformed HTML and dotted email-like text finish within controlled test
  budgets. Valid quoted delimiters, comments, script/style text, entities and
  complete syllabus text have explicit regression coverage.
- Accessibility checks preserve all documented issue categories. Fixes preserve
  row headers, respect CSS priority and handle both quote styles for alt text.
  Page scans request bodies and fail explicitly if readable content is absent.
  Failed reads, failed updates and mismatched read-back cannot become a clean
  scan or a confirmed change. Author-text fences are added only to output.
- HTTP callers cannot see another caller's pseudonym-cache samples or inherit
  the stdio cache after credentials are cleared. Stable pseudonyms are unchanged.
- Publisher downloads are version/hash pinned and verified before extraction.
  Maintenance analysis has read-only repository authority; a separate job can
  publish only the validated report artifact. Model reports remain untrusted.
- Automatic GitHub context retains useful IDs, links, ages, counts and status
  without injecting titles, labels or names. Remote statistics are validated
  as data and cannot become Python source or replace last-good data on failure.
- Actual package inspection found local brief/scratch files in the first source
  archive. Explicit exclusions and a release archive-member check now block
  those files; neither the private brief nor execution notes are committed.

## Verification results

The full suite ran before each commit; final runs used both Python 3.13.12 and
3.11.15. All Canvas responses were synthetic. No live Canvas call was needed.
Exact final summaries and artifact checks are pasted below.

```text
Python 3.13.12, full suite:
====================== 3487 passed, 20 skipped in 29.86s =======================
Python 3.11.15, full suite:
====================== 3487 passed, 20 skipped in 32.50s =======================
Python 3.13.12, full suite under coverage:
====================== 3487 passed, 20 skipped in 46.96s =======================
Coverage:
11123 / 13062 statements = 85.16%
Ruff, src/tests:
All checks passed!
mypy, src:
pyproject.toml: note: unused section(s): module = ['tests.*']
Success: no issues found in 61 source files
mypy, five helper scripts:
pyproject.toml: note: unused section(s): module = ['azure.*', 'tests.*']
Success: no issues found in 5 source files
TypeScript:
# tests 96
# pass 96
# fail 0
# skipped 0
TypeScript build:
> canvas-mcp-code-api@1.0.6 build
> tsc
Tool contracts:
student-default 51
educator-default 94
all-default 113
student-enabled 62
educator-enabled 96
all-enabled 126
All six tool name/argument/result-schema/annotation snapshots unchanged.
Packages:
Package privacy check passed for 2 artifacts.
Isolated installed wheel: import, bundled TypeScript, quoted text, row scope and scanner checks passed.
canvas-mcp-server --help: exit 0 (isolated installed wheel)
Dependency audit:
No known vulnerabilities found
```

The dependency audit separately inspected all 95 pinned Python dependencies,
including hosted extras: no vulnerability records were returned. The retained
existing ignored advisory did not hide any result. No dependency upgrade was
made. The actual official publisher archive was independently hashed and
extracted without executing it. Node dependencies were installed from their
lockfile; the TypeScript suite and build passed.

Full-suite commands were `uv run --locked python -m pytest tests/ -v -rfs`,
`uv run --locked ruff check src/ tests/`, and `uv run --locked mypy src/`.
Python 3.11 used an isolated environment from the unchanged lock. The final
coverage run adds temporary `pytest-cov==7.1.0` tooling without changing project
dependencies. The five new/changed Python helper scripts also passed Ruff/mypy;
`bash -n scripts/collect-impact-stats.sh` passed. New regression tests name the
production mutation they detect and were observed failing before the fixes.

## Independent review and resolution

One fresh read-only reviewer checked `b271b63..5e8dc3e`, the full diff, the plan
and its Review Focus. It independently passed 145 focused tests, checked caller
cancellation/credential clearing, compared all six tool contracts and inspected
the exact pinned agent action. It found no Critical issue, three Important and
two Minor issues. All five were accepted after reproduction and fixed in
`d37b9d1`; 46 new checks failed on the first implementation before correction.

1. Quoted `<`/`>` could hide visible text or expose script text. A shared forward
   tokenizer now respects quotes, comments and raw script/style text.
2. The header fixer could insert a column scope ahead of an existing row scope;
   the scanner could miss images. Both now inspect complete parsed attributes.
3. A page-list response normally omits the body unless requested. The scanner
   now requests `include[]=body` and rejects absent/unreadable bodies. See the
   [Canvas Pages API](https://documentation.instructure.com/doc/api/pages.html#method.wiki_pages_api.index).
4. CSS `!important` was discarded. Effective declaration priority is retained.
5. Single-quoted alt text was advertised as fixable but ignored by the fixer.
   It now receives the same supported repair as double-quoted text.

A suspected need for repository-write permission in interactive action setup
was rejected: the [exact pinned action creates its issue branch locally](https://github.com/anthropics/claude-code-action/blob/1d6de8cb0c237e7c15e9e1bdf973826ebae490cc/src/github/operations/branch.ts#L325-L337).
No token-permission broadening was needed. The reviewer made no changes; the
corrections were verified through failing regressions and full suites. This is
source-review evidence, not permission to merge or deploy.

## Remaining work and questions for Vishal

All scoped source work is complete. These explicit owner decisions remain:

- **F6:** confirm historical credential revocation/usage review and decide
  whether history cleanup is needed. Presence was checked without displaying
  the value or probing its validity; no history was rewritten.
- **F17:** repair the private launcher's token-in-argument behavior in its owning
  source/distribution. That file is outside this worktree and was not edited.
- **F18:** choose a staff-aware policy for course-topic contact information.
  Current exemptions can preserve student-authored contact details; removing
  them also changes documented staff-contact behavior. Reconcile with OAuth
  PRs #510/#441 before changing the client boundary.
- **#157:** decide the privileged code-execution replacement architecture.
  Opted-in execution can bypass Python confirmation and fencing. It remains
  disabled by default and disabled for hosted deployments; no new service or
  credential bridge was introduced.
- **Release settings:** review protected tags, publishing environments and
  OIDC audience isolation before using the revised workflows. These external
  settings and Azure/Entra authentication were not queried or changed.

Minimal overlaps with #441 are limited to anonymization cache/email handling
and `.gitignore`; no OAuth, client, server, config or lockfile rewrite was made.
#510's implementation files were avoided. Merge reconciliation belongs to the
maintainer after review; the primary checkout remains untouched.

Limits: no Windows run, live hosted authentication, actual GitHub workflow run,
Canvas sanitizer check or container-egress proof was attempted. Existing
formal models were not changed or rerun. Local green tests do not establish
penetration-test completeness or fix the explicitly deferred boundaries.
The scanner still only implements pages/assignments; advertised discussion/
syllabus scanning needs a separately scoped compatibility correction. Optional
security placeholders/skips are listed verbatim below, rather than counted as
coverage of their named guarantees.

## Failures encountered and resolved

No test failure remains. This section records every failed node observed during
the run, including deliberate RED tests and intermediate fixture/harness errors.
Repeated failures of the same node are listed once, with the run labels where
they appeared. Parameter values below are synthetic test inputs.

Intermediate full-suite failures were:

- `tests/test_collection_get_guard.py::test_no_single_request_get_on_a_collection_endpoint`:
  made the new read-back item path explicit; the guard was not weakened.
- `tests/test_text_encoding_guard.py::test_no_encoding_less_text_io_in_src_or_tests`:
  explicitly set UTF-8 for tar test/installer headers; the guard was unchanged.
- `tests/security/test_untrusted_content.py::TestRound9Surfaces::test_scan_accessibility_fences_content_title`:
  its old page fixture had no body and the assertions passed vacuously. Supply
  the requested-body response and require nonempty findings; keep fence checks.

Other intermediate issues: announcement fixtures needed Canvas's actual
`is_announcement` discriminator; GitHub brief expectations needed label-free
output. The first statistics harness invoked macOS's unrelated `log` utility
and never reached the target code. After adding an inert log stub, the original
source was restored temporarily and all three harmless synthetic payloads
executed their temporary marker files; six intended failures were observed.
The revised source passed. The invalid first harness run is not proof of RED.

Ruff caught one unused loop name; mypy caught a leaked comprehension variable,
script API-shape narrowing and a missing list annotation. Each was corrected
without weakening checking. The first audit attempt aborted in local ensurepip;
auditing the already fully pinned export with `--disable-pip --no-deps` passed.
The first final coverage invocation lacked the optional pytest-cov plugin and
collected no tests; rerunning with temporary pinned tooling produced the full
results above. The first standalone wheel probe assumed the wrong location
for `bulkGrade.ts`; archive inspection confirmed the actual nested path and
the corrected installed-package probe passed. No tests were omitted to obtain
a passing suite.

All 149 unique failed node names (run labels in brackets):

```text
tests/security/test_accessibility_processing.py::test_attributes_inside_title_do_not_satisfy_alt_scope_or_style [review-red]
tests/security/test_accessibility_processing.py::test_contrast_scanner_and_fixer_honor_important_priority [review-red]
tests/security/test_accessibility_processing.py::test_malformed_accessibility_input_finishes[_check_content_accessibility('<a href="a.pdf">' * 50_000, 'page', 7, 'Synthetic')] [task3-red-large]
tests/security/test_accessibility_processing.py::test_malformed_accessibility_input_finishes[_check_content_accessibility('<img style="' * 10_000, 'page', 7, 'Synthetic')] [task3-red-large, task3-red]
tests/security/test_accessibility_processing.py::test_malformed_accessibility_input_finishes[_check_content_accessibility('<span style="color:' + 'a' * 300_000, 'page', 7, 'Synthetic')] [task3-red-large]
tests/security/test_accessibility_processing.py::test_malformed_accessibility_input_finishes[_check_content_accessibility('<table>' * 50_000, 'page', 7, 'Synthetic')] [task3-red-large]
tests/security/test_accessibility_processing.py::test_malformed_accessibility_input_finishes[_extract_violations_from_html('WCAG 1.1.1\\npage ' + '<' * 300_000)] [task3-red-large, task3-red]
tests/security/test_accessibility_processing.py::test_malformed_accessibility_input_finishes[_fix_orange_contrast('style="' + 'background-color:#ff5f05;' * 25_000)] [task3-red-large]
tests/security/test_accessibility_processing.py::test_redundant_alt_fixer_handles_the_quotes_advertised_by_scanner["] [review-red]
tests/security/test_accessibility_processing.py::test_redundant_alt_fixer_handles_the_quotes_advertised_by_scanner['] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<a href="/detail"> </a>-empty_link-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<a href="/detail"> </a>-empty_link-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<a href="/detail">click here</a>-non_descriptive_link-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<a href="/detail">click here</a>-non_descriptive_link-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<a href="/detail">https://example.org</a>-url_as_link_text-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<a href="/detail">https://example.org</a>-url_as_link_text-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<a href="handout.pdf">Handout</a>-doc_link_no_type-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<a href="handout.pdf">Handout</a>-doc_link_no_type-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<h2> </h2>-empty_heading-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<h2> </h2>-empty_heading-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<h2>First</h2><h4>Skipped</h4>-heading_skip-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<h2>First</h2><h4>Skipped</h4>-heading_skip-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<iframe src="https://youtube.com/embed/synthetic"></iframe>-video_caption_check-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<iframe src="https://youtube.com/embed/synthetic"></iframe>-video_caption_check-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<img alt="chart.png">-filename_alt_text-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<img alt="chart.png">-filename_alt_text-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<img alt="image of a chart">-redundant_alt_prefix-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<img alt="image of a chart">-redundant_alt_prefix-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<img src="chart.png">-missing_alt_text-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<img src="chart.png">-missing_alt_text-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<p style="text-decoration:underline">Text</p>-underline_not_link-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<p style="text-decoration:underline">Text</p>-underline_not_link-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<span style="color:red">Important</span>-color_only_meaning-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<span style="color:red">Important</span>-color_only_meaning-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<table><td>Value</td></table>-table_without_headers-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<table><td>Value</td></table>-table_without_headers-'] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<th>Header</th>-th_missing_scope-"] [review-red]
tests/security/test_accessibility_processing.py::test_scanner_accepts_quoted_angle_brackets[<th>Header</th>-th_missing_scope-'] [review-red]
tests/security/test_accessibility_processing.py::test_scope_fixer_preserves_row_scope_and_changes_only_missing_attribute["] [review-red]
tests/security/test_accessibility_processing.py::test_scope_fixer_preserves_row_scope_and_changes_only_missing_attribute['] [review-red]
tests/security/test_announcement_delete_boundary.py::test_mixed_batch_deletes_only_proven_announcements[bulk_delete_announcements-args0] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_mixed_batch_deletes_only_proven_announcements[delete_announcements_by_criteria-args1] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[bulk_delete_announcements-None] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[bulk_delete_announcements-record0] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[bulk_delete_announcements-record1] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[bulk_delete_announcements-record2] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[bulk_delete_announcements-record3] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[bulk_delete_announcements-record5] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[delete_announcement_with_confirmation-None] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[delete_announcement_with_confirmation-record0] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[delete_announcement_with_confirmation-record1] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[delete_announcement_with_confirmation-record2] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[delete_announcement_with_confirmation-record3] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_refuses_unproven_announcement_without_token[delete_announcement_with_confirmation-record5] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_type_change_after_preview_cannot_redeem_token[bulk_delete_announcements-args1] [task1-red]
tests/security/test_announcement_delete_boundary.py::test_type_change_after_preview_cannot_redeem_token[delete_announcement_with_confirmation-args0] [task1-red, task1-type-revert-red]
tests/security/test_announcement_delete_boundary.py::test_type_change_after_preview_cannot_redeem_token[delete_announcements_by_criteria-args2] [task1-red, task1-type-revert-red]
tests/security/test_impact_stats_boundary.py::test_invalid_counter_does_not_replace_previous_snapshot[-1] [task6-stats-real-red]
tests/security/test_impact_stats_boundary.py::test_invalid_counter_does_not_replace_previous_snapshot[3.5] [task6-stats-real-red]
tests/security/test_impact_stats_boundary.py::test_invalid_counter_does_not_replace_previous_snapshot[True] [task6-stats-real-red]
tests/security/test_impact_stats_boundary.py::test_remote_counter_cannot_execute_python[GH_STARS] [task6-stats-real-red]
tests/security/test_impact_stats_boundary.py::test_remote_counter_cannot_execute_python[NPM_MONTH] [task6-stats-real-red]
tests/security/test_impact_stats_boundary.py::test_remote_counter_cannot_execute_python[PYPI_WEEK] [task6-stats-real-red]
tests/security/test_impact_stats_boundary.py::test_valid_statistics_are_numeric_and_keep_last_good_values [task6-focused, task6-red]
tests/security/test_overhaul_output_boundaries.py::test_all_prompts_have_a_reviewed_trust_policy [task4-red]
tests/security/test_overhaul_output_boundaries.py::test_cleared_http_credentials_do_not_reveal_global_history [task4-red]
tests/security/test_overhaul_output_boundaries.py::test_concurrent_http_cache_and_clear_cannot_affect_other_callers [task4-red]
tests/security/test_overhaul_output_boundaries.py::test_course_labels_are_data_inside_summary_prompt [task4-red]
tests/security/test_overhaul_output_boundaries.py::test_failed_source_read_cannot_be_reported_as_clean[assignments] [task4-red]
tests/security/test_overhaul_output_boundaries.py::test_failed_source_read_cannot_be_reported_as_clean[fix_accessibility_issues-assignments] [task4-fixer-read-red]
tests/security/test_overhaul_output_boundaries.py::test_failed_source_read_cannot_be_reported_as_clean[fix_accessibility_issues-pages] [task4-fixer-read-red]
tests/security/test_overhaul_output_boundaries.py::test_failed_source_read_cannot_be_reported_as_clean[pages] [task4-red]
tests/security/test_overhaul_output_boundaries.py::test_fixer_confirms_outcome_and_never_writes_fences[None-False] [task4-fixer-red]
tests/security/test_overhaul_output_boundaries.py::test_fixer_confirms_outcome_and_never_writes_fences[reply0-False] [task4-fixer-red]
tests/security/test_overhaul_output_boundaries.py::test_fixer_confirms_outcome_and_never_writes_fences[reply2-True] [task4-fixer-red]
tests/security/test_overhaul_output_boundaries.py::test_fixer_confirms_outcome_and_never_writes_fences[reply3-<table><th>Title</th></table>-False] [task4-readback-red]
tests/security/test_overhaul_output_boundaries.py::test_fixer_unreadable_page_is_an_error_before_any_write [task4-fixer-read-red]
tests/security/test_overhaul_output_boundaries.py::test_http_status_without_credentials_does_not_read_stdio_history [task4-red]
tests/security/test_overhaul_output_boundaries.py::test_scanner_descriptions_fence_copied_excerpts [task4-red]
tests/security/test_overhaul_output_boundaries.py::test_scanner_missing_page_text_is_unconfirmed_not_clean[invalid] [review-red]
tests/security/test_overhaul_output_boundaries.py::test_scanner_missing_page_text_is_unconfirmed_not_clean[page0] [review-red]
tests/security/test_overhaul_output_boundaries.py::test_scanner_missing_page_text_is_unconfirmed_not_clean[page1] [review-red]
tests/security/test_overhaul_output_boundaries.py::test_scanner_missing_page_text_is_unconfirmed_not_clean[page2] [review-red]
tests/security/test_overhaul_output_boundaries.py::test_scanner_requests_page_bodies_and_checks_actual_text [review-red]
tests/security/test_package_local_files.py::test_packages_refuse_local_only_files[sdist-.env] [task7-package-red]
tests/security/test_package_local_files.py::test_packages_refuse_local_only_files[sdist-.superpowers/sdd/PLAN/progress.md] [task7-package-red]
tests/security/test_package_local_files.py::test_packages_refuse_local_only_files[sdist-BRIEF.md] [task7-package-red]
tests/security/test_package_local_files.py::test_packages_refuse_local_only_files[sdist-internal/ops.local.md] [task7-package-red]
tests/security/test_package_local_files.py::test_packages_refuse_local_only_files[wheel-.env] [task7-package-red]
tests/security/test_package_local_files.py::test_packages_refuse_local_only_files[wheel-.superpowers/sdd/PLAN/progress.md] [task7-package-red]
tests/security/test_package_local_files.py::test_packages_refuse_local_only_files[wheel-BRIEF.md] [task7-package-red]
tests/security/test_package_local_files.py::test_packages_refuse_local_only_files[wheel-internal/ops.local.md] [task7-package-red]
tests/security/test_package_local_files.py::test_wheel_with_bundled_code_api_is_accepted [task7-package-red]
tests/security/test_release_automation_boundaries.py::test_agent_analysis_cannot_mint_app_tokens_or_publish_issues [task5-red]
tests/security/test_release_automation_boundaries.py::test_interactive_agent_uses_only_job_scoped_credentials [task5-red]
tests/security/test_release_automation_boundaries.py::test_publisher_archive_cannot_install_a_symlink [task5-red]
tests/security/test_release_automation_boundaries.py::test_publisher_checks_digest_before_replacing_executable[False] [task5-red]
tests/security/test_release_automation_boundaries.py::test_publisher_checks_digest_before_replacing_executable[True] [task5-red]
tests/security/test_release_automation_boundaries.py::test_release_installer_uses_an_immutable_version_and_checksum [task5-red]
tests/security/test_release_automation_boundaries.py::test_report_publication_rejects_paths_or_invalid_data[data0] [task5-red]
tests/security/test_release_automation_boundaries.py::test_report_publication_rejects_paths_or_invalid_data[data1] [task5-red]
tests/security/test_release_automation_boundaries.py::test_report_publication_rejects_paths_or_invalid_data[data2] [task5-red]
tests/security/test_release_automation_boundaries.py::test_report_publication_rejects_paths_or_invalid_data[data3] [task5-red]
tests/security/test_release_automation_boundaries.py::test_report_publication_rejects_paths_or_invalid_data[data4] [task5-red]
tests/security/test_release_automation_boundaries.py::test_report_shell_syntax_stays_literal_data [task5-red]
tests/security/test_text_processing_cost.py::test_plain_removal_keeps_all_inline_text_with_quoted_angles["] [review-red]
tests/security/test_text_processing_cost.py::test_plain_removal_keeps_all_inline_text_with_quoted_angles['] [review-red]
tests/security/test_text_processing_cost.py::test_quoted_delimiters_do_not_hide_or_invent_visible_text[<p title="x <script>">Retained syllabus text</p><p>After</p>-Retained syllabus text\nAfter] [review-red]
tests/security/test_text_processing_cost.py::test_quoted_delimiters_do_not_hide_or_invent_visible_text[<p title="x<y">Complete text</p>-Complete text] [review-red]
tests/security/test_text_processing_cost.py::test_quoted_delimiters_do_not_hide_or_invent_visible_text[<p title='x>y'>Complete text</p>-Complete text] [review-red]
tests/security/test_text_processing_cost.py::test_quoted_delimiters_do_not_hide_or_invent_visible_text[<p>A<!-- <img title="x>y"> hidden -->B</p>-AB] [review-red]
tests/security/test_text_processing_cost.py::test_quoted_delimiters_do_not_hide_or_invent_visible_text[<script data-rule="x<y">alert(1)</script><p>Safe</p>-Safe] [review-red]
tests/security/test_text_processing_cost.py::test_unterminated_author_text_finishes_without_suffix_rescanning[from canvas_mcp.core.anonymization import scrub_free_text; text = 'a.' * 150_000; assert scrub_free_text(text) == text] [task2-red]
tests/security/test_text_processing_cost.py::test_unterminated_author_text_finishes_without_suffix_rescanning[from canvas_mcp.tools.courses import strip_html_tags; assert strip_html_tags('<style>' * 30_000) == ''] [task2-red]
tests/security/test_text_processing_cost.py::test_unterminated_author_text_finishes_without_suffix_rescanning[from canvas_mcp.tools.courses import strip_html_tags; text = '<' * 300_000; assert strip_html_tags(text) == text] [task2-red]
tests/security/test_text_processing_cost.py::test_unterminated_author_text_finishes_without_suffix_rescanning[from canvas_mcp.tools.discussions import _discussion_text; text = '<' * 300_000; assert _discussion_text(text) == text] [task2-red]
tests/security/test_untrusted_content.py::TestRound9Surfaces::test_scan_accessibility_fences_content_title [review-final-pytest]
tests/test_collection_get_guard.py::test_no_single_request_get_on_a_collection_endpoint [task4-pytest]
tests/test_github_session_brief.py::test_automatic_brief_omits_all_author_controlled_labels[check] [task6-red]
tests/test_github_session_brief.py::test_automatic_brief_omits_all_author_controlled_labels[discussion] [task6-red]
tests/test_github_session_brief.py::test_automatic_brief_omits_all_author_controlled_labels[issue] [task6-red]
tests/test_github_session_brief.py::test_automatic_brief_omits_all_author_controlled_labels[pr] [task6-red]
tests/test_github_session_brief.py::test_ci_state_aggregation[runs4-CI RED (test (3.12))] [task6-focused]
tests/test_github_session_brief.py::test_fetch_issues_filters_pull_requests_and_flags_a_full_page [task6-focused]
tests/test_github_session_brief.py::test_issue_titles_are_fenced_and_cannot_close_the_fence [task6-focused]
tests/test_github_session_brief.py::test_malformed_ci_payload_reports_unknown [task6-shapes-red]
tests/test_github_session_brief.py::test_malformed_lists_fail_with_static_diagnostic[fetch_issues] [task6-shapes-red]
tests/test_github_session_brief.py::test_malformed_lists_fail_with_static_diagnostic[fetch_prs] [task6-shapes-red]
tests/test_text_encoding_guard.py::test_no_encoding_less_text_io_in_src_or_tests [task5-pytest]
tests/tools/test_delete_confirmation.py::test_announcement_title_mismatch_issues_no_token [task1-focused]
tests/tools/test_delete_confirmation.py::test_bulk_confirm_deletes_exactly_the_previewed_set [task1-focused]
tests/tools/test_delete_confirmation.py::test_bulk_limit_refuses_before_issuing_token [task1-focused]
tests/tools/test_delete_confirmation.py::test_bulk_preview_lists_titles_and_unreachable [task1-focused]
tests/tools/test_delete_confirmation.py::test_bulk_token_bound_to_id_list [task1-focused]
tests/tools/test_delete_confirmation.py::test_bulk_token_bound_to_requested_ids_not_just_resolved [task1-focused]
tests/tools/test_delete_confirmation.py::test_bulk_token_bound_to_stop_on_error_and_limit [task1-focused]
tests/tools/test_delete_confirmation.py::test_confirm_with_token_deletes_once[discussions-delete_announcement_with_confirmation-args0-payload0-Old Exam Info-renamed0] [task1-focused]
tests/tools/test_delete_confirmation.py::test_criteria_confirm_deletes_previewed_matches [task1-focused]
tests/tools/test_delete_confirmation.py::test_criteria_match_set_changed_refuses [task1-focused]
tests/tools/test_delete_confirmation.py::test_criteria_preview_shows_matches_and_token [task1-focused]
tests/tools/test_delete_confirmation.py::test_criteria_token_bound_to_displayed_posted_at [task1-focused]
tests/tools/test_delete_confirmation.py::test_delete_changed_then_reverted_preview_stays_burned[discussions-delete_announcement_with_confirmation-args0-payload0-Old Exam Info-renamed0] [task1-focused]
tests/tools/test_delete_confirmation.py::test_delete_confirm_is_exclusive_while_dispatch_is_pending[discussions-delete_announcement_with_confirmation-args0-payload0-Old Exam Info-renamed0] [task1-focused]
tests/tools/test_delete_confirmation.py::test_delete_plan_cannot_be_reentered_mid_batch[False] [task1-focused]
tests/tools/test_delete_confirmation.py::test_delete_plan_cannot_be_reentered_mid_batch[True] [task1-focused]
tests/tools/test_delete_confirmation.py::test_delete_token_cannot_move_to_an_identically_named_target[discussions-delete_announcement_with_confirmation-args0-payload0-Old Exam Info-renamed0] [task1-focused]
tests/tools/test_delete_confirmation.py::test_garbage_token_refuses[discussions-delete_announcement_with_confirmation-args0-payload0-Old Exam Info-renamed0] [task1-focused]
tests/tools/test_delete_confirmation.py::test_preview_without_token_deletes_nothing[discussions-delete_announcement_with_confirmation-args0-payload0-Old Exam Info-renamed0] [task1-focused]
tests/tools/test_delete_confirmation.py::test_target_changed_between_preview_and_confirm_refuses[discussions-delete_announcement_with_confirmation-args0-payload0-Old Exam Info-renamed0] [task1-focused]
```

## Final skipped checks (verbatim)

```text
SKIPPED [1] tests/core/test_dates.py:61: could not import 'tzdata': No module named 'tzdata'
SKIPPED [1] tests/security/test_authentication.py:101: .env file not found - skipping permissions check
SKIPPED [1] tests/security/test_authentication.py:169: Requires test Canvas accounts with different roles
SKIPPED [1] tests/security/test_authentication.py:176: MCP client authentication not yet implemented
SKIPPED [1] tests/security/test_code_execution.py:23: Sandboxing not yet fully implemented
SKIPPED [1] tests/security/test_code_execution.py:86: Command execution protection needed
SKIPPED [1] tests/security/test_code_execution.py:183: Code execution logging not yet implemented
SKIPPED [1] tests/security/test_code_execution.py:201: Resource limits not yet configurable
SKIPPED [1] tests/security/test_code_execution.py:211: Static code analysis not yet implemented
SKIPPED [1] tests/security/test_code_execution.py:218: Static code analysis not yet implemented
SKIPPED [1] tests/security/test_dependencies.py:56: pip-audit not installed
SKIPPED [1] tests/security/test_dependencies.py:91: pip-audit not installed
SKIPPED [1] tests/security/test_dependencies.py:116: Many outdated packages: 61
SKIPPED [1] tests/security/test_dependencies.py:150: License checking tool not yet integrated
SKIPPED [1] tests/security/test_dependencies.py:158: License checking tool not yet integrated
SKIPPED [1] tests/security/test_dependencies.py:219: Hash checking not yet implemented
SKIPPED [1] tests/security/test_dependencies.py:261: Security advisory monitoring not automated
SKIPPED [1] tests/security/test_ferpa_compliance.py:140: Audit logging not yet implemented
SKIPPED [1] tests/security/test_ferpa_compliance.py:146: Audit logging not yet implemented
SKIPPED [1] tests/security/test_ferpa_compliance.py:175: Data retention policy not yet implemented
```
