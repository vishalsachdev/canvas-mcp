import { callCanvasTool } from "../../client.js";

export interface GradeWithRubricInput {
  courseIdentifier: string | number;
  assignmentId: string | number;
  userId: string | number;
  rubricAssessment: Record<string, {
    points: number;
    ratingId?: string;
    comments?: string;
  }>;
  comment?: string;
}

export interface GradeResponse {
  success: boolean;
  submissionId?: string;
  grade?: number;
  error?: string;
}

/**
 * Grade a single submission using a rubric.
 *
 * The rubric must already be associated with the assignment.
 * Criterion IDs in Canvas often start with underscore (e.g., "_8027").
 *
 * Use list_assignment_rubrics or get_rubric_details to discover criterion IDs.
 *
 * Example:
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
  return callCanvasTool<GradeResponse>('grade_with_rubric', input);
}
