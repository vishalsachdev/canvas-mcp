# Rubric API behavior

Based on a review of canvas-mcp commit `531ec4f610975cb9984c011387bf9627635bbe7e`,
with the grading safeguards described below added in this change. Canvas documentation/source
was inspected on September 14, 2026. No live Canvas writes
were performed for this review.

## Creation and editing

Canvas documents both `POST /api/v1/courses/:course_id/rubrics` and
`PUT /api/v1/courses/:course_id/rubrics/:id`. Its criteria request parameter
is an indexed hash. The nested ratings also need indexed hashes: Canvas's
`Rubric#generate_criteria` reads their values as a hash.

canvas-mcp already implements creation. `build_rubric_create_form_data`
encodes both levels with numeric indices, for example:

```text
rubric[criteria][0][description]=Thesis
rubric[criteria][0][points]=10
rubric[criteria][0][ratings][0][description]=Clear
rubric[criteria][0][ratings][0][points]=10
```

It also sends the course bookmark or assignment association in the same
request. `create_rubric` and `associate_rubric` default `use_for_grading`
to false. Choose true explicitly when the rubric should calculate grades.

[Issue #375](https://github.com/vishalsachdev/canvas-mcp/issues/375) reports
that nested JSON works when both levels are index-keyed objects rather than
arrays. This is consistent with the indexed-hash contract; there is no need
to replace the existing form encoder. The report's false-to-null behavior
for `free_form_criterion_comments` was observed on one instance. Current
creation does not perform a strict false-versus-null read-back comparison,
so it does not establish a reason to change the boolean payload.

`update_rubric` exposes a deliberately narrow, guarded form of editing. Canvas
still performs a full replacement, so the tool fetches the current rubric and
requires an exact ID-keyed copy of every criterion and rating. It refuses
missing, extra, or mismatched IDs and preserves non-editable scoring/range
flags from the current rubric.

The preview displays complete current and proposed long descriptions for every
criterion and rating, including explicit clearing, plus preserved scoring/range
flags. Decoded replacement text is checked for provenance fence markers before
a confirmation token can be issued or used. Updates always send
`rubric[skip_updating_points_possible]=1` to preserve assignment gradebook totals
even when rubric criterion points change.

Updating is always two-step: the first call returns a no-write preview and a
single-use token bound to the caller, current rubric/association state, and
complete requested replacement. Confirmation re-fetches the rubric, so any
concurrent change invalidates the token before the PUT. The request includes
the explicit `rubric_association_id`, and success requires both the update
response and a fresh read-back to identify the original rubric and association
and match the requested content. A different rubric ID (Canvas may create a
copy in some permission/context cases), missing association, or content
mismatch is reported as unconfirmed and is never retried automatically.

The tool supports edits to existing text and points. Structural additions or
removals remain a Canvas UI operation because preserving assessment-key
integrity across those changes has not been established on a live instance.

## Assessments and grades

The association's `use_for_grading` flag is exposed on an assignment as
`use_rubric_for_grading`. In Canvas source, `RubricAssessment#update_artifact`
uses this flag before updating a submission score. It also checks grading
permission and excludes checkpoint parent assignments. An unchanged score
does not trigger another grade update. `RubricAssociation#assess` excludes
criteria marked `ignore_for_scoring` from the score.

| Current path | Request and checks |
| --- | --- |
| Python `grade_with_rubric` | Sends rubric assessment fields without `submission[posted_grade]`; requires an explicit true assignment flag and stops on a lookup error. |
| Python `bulk_grade_submissions`, rubric branch | Same dependency and fail-closed precheck; dry runs do not write. A nonempty rubric assessment takes precedence over a supplied `grade`. |
| TypeScript `gradeWithRubric` / rubric `bulkGrade` | Sends assessment fields without an explicit grade and requires an explicit true assignment flag before writing. A nonempty rubric assessment takes precedence over `grade`. |
| Simple-grade branch in Python bulk / TypeScript | Sends `submission[posted_grade]`; this is an explicit grade write, still subject to Canvas authorization and grading rules. |

Both Python and TypeScript verify rubric grading outcomes against Canvas's
returned score and non-null grade. For a complete assessment with available
rubric metadata, the expected score excludes `ignore_for_scoring` criteria.
A matching existing score is valid; this verifies the outcome, not that a new
change occurred or that the grade is visible to students.

Missing metadata, partial assessments, missing grades/scores, or a score
mismatch are reported as **unconfirmed** after the write. The assessment may
already have been saved: check the submission before retrying. Python bulk
reports these under failed submissions without counting them as graded;
TypeScript throws an explanatory error, which `bulkGrade` counts as failed.
Local sums shown in summaries or dry runs are raw rubric point totals, not
necessarily gradebook scores. Canvas grade posting policies still govern
student visibility.

The tools do not automatically enable grading or add `posted_grade` to
rubric writes. Permission and checkpoint restrictions remain Canvas's
responsibility; a successful HTTP response alone is insufficient evidence
of the requested grade outcome. Live-instance verification remains advisable.

## Sources

- [Canvas rubric API](https://developerdocs.instructure.com/services/canvas/resources/rubrics)
- [Canvas Rubric model: generate_criteria](https://github.com/instructure/canvas-lms/blob/master/app/models/rubric.rb)
- [Canvas RubricAssessment model: update_artifact](https://github.com/instructure/canvas-lms/blob/master/app/models/rubric_assessment.rb)
- [Canvas RubricAssociation model: assess](https://github.com/instructure/canvas-lms/blob/master/app/models/rubric_association.rb)
- [Issue #374](https://github.com/vishalsachdev/canvas-mcp/issues/374)

Canvas source links track `master`; deployed versions and feature flags can
differ. The source inspection supports the mechanism, not a live-instance
verification of every reported behavior.
