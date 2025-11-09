import { canvasPutForm } from "../../client.js";

export interface GradeWithRubricInput {
  courseIdentifier: string | number;
  assignmentId: string | number;
  userId: string | number;
  rubricAssessment?: Record<string, {
    points: number;
    ratingId?: string;
    comments?: string;
  }>;
  grade?: string | number;
  comment?: string;
}

export interface GradeResponse {
  id: number;
  user_id: number;
  assignment_id: number;
  score: number;
  grade: string;
}

/**
 * Validate rubric assessment input
 */
function validateRubricAssessment(
  rubricAssessment: Record<string, any>
): void {
  for (const [criterionId, assessment] of Object.entries(rubricAssessment)) {
    if (!assessment.points && assessment.points !== 0) {
      throw new Error(
        `Criterion "${criterionId}" is missing required "points" field`
      );
    }

    if (typeof assessment.points !== 'number') {
      throw new Error(
        `Criterion "${criterionId}" points must be a number, got ${typeof assessment.points}`
      );
    }

    if (assessment.points < 0) {
      throw new Error(
        `Criterion "${criterionId}" points cannot be negative: ${assessment.points}`
      );
    }
  }
}

/**
 * Convert rubric assessment to Canvas form-encoded format
 */
function buildRubricAssessmentFormData(
  rubricAssessment: Record<string, {
    points: number;
    ratingId?: string;
    comments?: string;
  }>,
  comment?: string
): Record<string, string> {
  const formData: Record<string, string> = {};

  // Transform rubric_assessment object into Canvas's form-encoded format
  for (const [criterionId, assessment] of Object.entries(rubricAssessment)) {
    // Points are required
    formData[`rubric_assessment[${criterionId}][points]`] = String(assessment.points);

    // Rating ID is optional but recommended
    if (assessment.ratingId) {
      formData[`rubric_assessment[${criterionId}][rating_id]`] = assessment.ratingId;
    }

    // Comments are optional
    if (assessment.comments) {
      formData[`rubric_assessment[${criterionId}][comments]`] = assessment.comments;
    }
  }

  // Add optional overall comment
  if (comment) {
    formData["comment[text_comment]"] = comment;
  }

  return formData;
}

/**
 * Grade a single submission using a rubric.
 *
 * Makes direct Canvas API calls with form-encoded data.
 * The rubric must already be associated with the assignment.
 * Criterion IDs in Canvas often start with underscore (e.g., "_8027").
 *
 * @param input - Grading parameters
 * @returns Canvas API response with graded submission data
 *
 * @throws Error if rubric assessment is invalid
 *
 * @example
 * ```typescript
 * await gradeWithRubric({
 *   courseIdentifier: "60366",
 *   assignmentId: "123",
 *   userId: "456",
 *   rubricAssessment: {
 *     "_8027": { points: 100, comments: "Excellent work!" }
 *   },
 *   comment: "Great submission overall"
 * });
 * ```
 */
export async function gradeWithRubric(
  input: GradeWithRubricInput
): Promise<GradeResponse> {
  const { courseIdentifier, assignmentId, userId, rubricAssessment, grade, comment } = input;

  // Validate: Must have either rubricAssessment OR grade
  if (!rubricAssessment && !grade && grade !== 0) {
    throw new Error('Must provide either rubricAssessment or grade');
  }

  let formData: Record<string, string> = {};

  // Handle rubric-based grading
  if (rubricAssessment && Object.keys(rubricAssessment).length > 0) {
    validateRubricAssessment(rubricAssessment);
    formData = buildRubricAssessmentFormData(rubricAssessment, comment);
  }
  // Handle simple grading
  else if (grade !== undefined) {
    formData['submission[posted_grade]'] = String(grade);
    if (comment) {
      formData['comment[text_comment]'] = comment;
    }
  }

  // Canvas API endpoint for updating submission
  const endpoint = `/courses/${courseIdentifier}/assignments/${assignmentId}/submissions/${userId}`;

  try {
    // Submit the grade with rubric assessment using form encoding
    const response = await canvasPutForm<GradeResponse>(endpoint, formData);
    return response;
  } catch (error: any) {
    throw new Error(
      `Failed to grade submission: ${error.message}\n` +
      `Check that rubric is configured for grading and criterion IDs are correct.`
    );
  }
}
