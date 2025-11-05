import { callCanvasTool } from "../../client.js";
import { listSubmissions, Submission } from "../assignments/listSubmissions.js";
import { gradeWithRubric } from "./gradeWithRubric.js";

export interface GradeResult {
  points: number;
  rubricAssessment: Record<string, {
    points: number;
    ratingId?: string;
    comments?: string;
  }>;
  comment: string;
}

export interface BulkGradeInput {
  courseIdentifier: string | number;
  assignmentId: string | number;
  gradingFunction: (submission: Submission) => GradeResult | null;
  dryRun?: boolean;
  maxConcurrent?: number;
}

export interface BulkGradeResult {
  total: number;
  graded: number;
  skipped: number;
  failed: number;
  results: Array<{
    userId: string;
    success: boolean;
    error?: string;
  }>;
}

/**
 * Grade multiple submissions efficiently in the execution environment.
 *
 * THIS IS THE MOST TOKEN-EFFICIENT WAY TO GRADE BULK SUBMISSIONS.
 *
 * The grading function runs locally in the execution environment,
 * processing each submission without loading all data into Claude's context.
 * Only the summary results flow back to Claude.
 *
 * Token savings example:
 * - Traditional approach: 90 submissions × 15K tokens each = 1.35M tokens
 * - Bulk grade approach: ~3.5K tokens total (99.7% reduction!)
 *
 * The grading function receives each submission and should return:
 * - GradeResult object if the submission should be graded
 * - null if the submission should be skipped
 *
 * @param input - Configuration for bulk grading
 * @param input.gradingFunction - Function that analyzes each submission locally
 * @param input.dryRun - If true, analyze but don't actually grade (for testing)
 * @param input.maxConcurrent - Max concurrent grading operations (default: 5)
 *
 * @example
 * ```typescript
 * // Grade Jupyter notebooks that run without errors
 * await bulkGrade({
 *   courseIdentifier: "60366",
 *   assignmentId: "123",
 *   gradingFunction: (submission) => {
 *     // Find notebook file
 *     const notebook = submission.attachments?.find(
 *       f => f.filename.endsWith('.ipynb')
 *     );
 *
 *     if (!notebook) {
 *       return null; // Skip - no notebook
 *     }
 *
 *     // Analyze notebook (runs locally!)
 *     const hasErrors = checkNotebook(notebook.url);
 *
 *     if (hasErrors) {
 *       return {
 *         points: 50,
 *         rubricAssessment: { "_8027": { points: 50 } },
 *         comment: "Notebook has errors. Please fix and resubmit."
 *       };
 *     }
 *
 *     return {
 *       points: 100,
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
  console.log(`Starting bulk grading for assignment ${input.assignmentId}...`);

  // Fetch all submissions (stays in execution environment)
  const submissions = await listSubmissions({
    courseIdentifier: input.courseIdentifier,
    assignmentId: input.assignmentId
  });

  console.log(`Found ${submissions.length} submissions to process`);

  const results: Array<{
    userId: string;
    success: boolean;
    error?: string;
  }> = [];

  let graded = 0;
  let skipped = 0;
  let failed = 0;

  // Process submissions
  for (const submission of submissions) {
    try {
      // Run grading function locally
      const gradeResult = input.gradingFunction(submission);

      if (!gradeResult) {
        // Skip this submission
        skipped++;
        console.log(`Skipped submission for user ${submission.userId}`);
        continue;
      }

      if (!input.dryRun) {
        // Actually grade the submission
        await gradeWithRubric({
          courseIdentifier: input.courseIdentifier,
          assignmentId: input.assignmentId,
          userId: submission.userId,
          rubricAssessment: gradeResult.rubricAssessment,
          comment: gradeResult.comment
        });
      }

      graded++;
      results.push({
        userId: submission.userId,
        success: true
      });

      console.log(`✓ Graded submission for user ${submission.userId}`);

    } catch (error: any) {
      failed++;
      results.push({
        userId: submission.userId,
        success: false,
        error: error.message
      });

      console.error(`✗ Failed to grade user ${submission.userId}: ${error.message}`);
    }
  }

  const summary = {
    total: submissions.length,
    graded,
    skipped,
    failed,
    results: results.slice(0, 5) // Only return first 5 for review
  };

  console.log(`\nBulk grading complete:`);
  console.log(`  Total: ${summary.total}`);
  console.log(`  Graded: ${summary.graded}`);
  console.log(`  Skipped: ${summary.skipped}`);
  console.log(`  Failed: ${summary.failed}`);

  return summary;
}
