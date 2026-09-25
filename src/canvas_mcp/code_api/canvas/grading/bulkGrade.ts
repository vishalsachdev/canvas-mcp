import { createBatchRunner } from "../../batching.js";
import { listSubmissions, Submission } from "../assignments/listSubmissions.js";
import { createRubricGrader } from "./gradeWithRubric.js";

export interface GradeResult {
  /** @deprecated Ignored: never sent to Canvas. Use grade (or rubricAssessment) instead. */
  points?: number;
  /** Rubric scores keyed by criterion id (e.g. "_8027"). When non-empty, grade is ignored. */
  rubricAssessment?: Record<string, {
    points: number;
    ratingId?: string;
    comments?: string;
  }>;
  grade?: string | number;
  comment?: string;
}

export interface BulkGradeInput {
  courseIdentifier: string | number;
  assignmentId: string | number;
  gradingFunction: (submission: Submission) => GradeResult | null | Promise<GradeResult | null>;
  dryRun?: boolean;
  maxConcurrent?: number;
  rateLimitDelay?: number;
}

export interface BulkGradeResult {
  total: number;
  graded: number;
  skipped: number;
  failed: number;
  failedResults: Array<{
    userId: number;
    error: string;
  }>;
}

/**
 * Process one submission; scheduling belongs to the shared batch runner
 */
async function processSubmission(
  submission: Submission,
  input: BulkGradeInput,
  stats: { graded: number; skipped: number; failed: number },
  failedResults: Array<{ userId: number; error: string }>,
  gradeWithRubric: ReturnType<typeof createRubricGrader>
): Promise<void> {
  // The grading callback may edit its input; keep the validated target.
  const userId = submission.user_id;
  try {
    // Run grading function (may be async)
    const gradeResult = await Promise.resolve(input.gradingFunction(submission));

    if (!gradeResult) {
      // Skip this submission
      stats.skipped++;
      console.log(`Skipped submission for user ${userId}`);
      return;
    }

    if (!input.dryRun) {
      // Actually grade the submission
      await gradeWithRubric({
        courseIdentifier: input.courseIdentifier,
        assignmentId: input.assignmentId,
        userId,
        rubricAssessment: gradeResult.rubricAssessment,
        grade: gradeResult.grade,
        comment: gradeResult.comment
      });
    }

    stats.graded++;
    console.log(`✓ Graded submission for user ${userId}`);
    return;

  } catch (error: any) {
    stats.failed++;
    const errorMsg = error?.message || String(error);
    failedResults.push({
      userId,
      error: errorMsg
    });
    console.error(`✗ Failed to grade user ${userId}: ${errorMsg}`);
    return;
  }
}

/**
 * Grade multiple submissions efficiently with concurrent processing.
 *
 * The grading function runs locally in the execution environment,
 * processing submissions in parallel batches without loading all data into Claude's context.
 * Only the summary results flow back to Claude.
 *
 * This can reduce model-context use because per-submission processing stays
 * local and only selected output returns to the caller. Actual savings depend
 * on the workload and output.
 *
 * The grading function receives each submission and should return:
 * - GradeResult object if the submission should be graded
 * - null if the submission should be skipped
 * - Promise resolving to either (async functions supported)
 *
 * @param input - Configuration for bulk grading
 * @param input.gradingFunction - Function that analyzes each submission locally (can be async)
 * @param input.dryRun - If true, runs gradingFunction and writes nothing. "graded" then counts results that
 *   WOULD be submitted; payloads are not validated against Canvas or the rubric, so a clean dry run does not
 *   guarantee a clean real run.
 * @param input.maxConcurrent - Positive integer cap per run (default: 5)
 * @param input.rateLimitDelay - Integer delay between batches, 0..2147483647ms (default: 1000; 0 disables)
 *
 * @example
 * ```typescript
 * // Grade Jupyter notebooks that run without errors
 * await bulkGrade({
 *   courseIdentifier: "60366",
 *   assignmentId: "123",
 *   gradingFunction: async (submission) => {
 *     // Find notebook file
 *     const notebook = submission.attachments?.find(
 *       f => f.filename.endsWith('.ipynb')
 *     );
 *
 *     if (!notebook) {
 *       return null; // Skip - no notebook
 *     }
 *
 *     // Analyze notebook (runs locally, can be async!)
 *     const hasErrors = await checkNotebook(notebook.url);
 *
 *     if (hasErrors) {
 *       return {
 *         rubricAssessment: { "_8027": { points: 50 } },
 *         comment: "Notebook has errors. Please fix and resubmit."
 *       };
 *     }
 *
 *     return {
 *       rubricAssessment: { "_8027": { points: 100 } },
 *       comment: "Excellent! Notebook runs without errors."
 *     };
 *   }
 * });
 * ```
 */
export async function bulkGrade(
  input: BulkGradeInput
): Promise<BulkGradeResult> {
  const runBatches = createBatchRunner(input);

  // Fetch all submissions (stays in execution environment)
  const submissions = await listSubmissions({
    courseIdentifier: input.courseIdentifier,
    assignmentId: input.assignmentId
  });

  // Validate the complete work list before invoking any grading callback.
  // One submission target is one user within this run's fixed assignment.
  const targets = new Set<number>();
  for (const submission of submissions) {
    if (!Number.isSafeInteger(submission.user_id) || submission.user_id < 1) {
      throw new Error('Submission user_id must be a positive safe integer; no grades were submitted');
    }
    if (targets.has(submission.user_id)) {
      throw new Error(`Duplicate submission user_id ${submission.user_id}; no grades were submitted`);
    }
    targets.add(submission.user_id);
  }

  console.log(`Found ${submissions.length} submissions to process`);

  const stats = {
    graded: 0,
    skipped: 0,
    failed: 0
  };

  const failedResults: Array<{ userId: number; error: string }> = [];

  const gradeWithRubric = createRubricGrader();

  await runBatches(submissions, submission =>
    processSubmission(submission, input, stats, failedResults, gradeWithRubric));

  const summary: BulkGradeResult = {
    total: submissions.length,
    graded: stats.graded,
    skipped: stats.skipped,
    failed: stats.failed,
    failedResults: failedResults // Return ALL failures, not just first 5
  };

  console.log(`\n${'='.repeat(50)}`);
  console.log(`Bulk grading complete!`);
  console.log(`${'='.repeat(50)}`);
  console.log(`  Total:   ${summary.total}`);
  console.log(`  Graded:  ${summary.graded}`);
  console.log(`  Skipped: ${summary.skipped}`);
  console.log(`  Failed:  ${summary.failed}`);

  if (summary.failed > 0) {
    console.log(`\nFailed submissions:`);
    failedResults.forEach(({ userId, error }) => {
      console.log(`  User ${userId}: ${error}`);
    });
  }

  return summary;
}
