import { canvasGet } from "../../client.js";

export interface GetCourseDetailsInput {
  courseIdentifier: string | number;
}

export interface CourseDetails {
  id: number;
  name: string;
  course_code: string;
  workflow_state: string;
  start_at?: string;
  end_at?: string;
  time_zone?: string;
  syllabus_body?: string;
  enrollment_term_id?: number;
}

/**
 * Get detailed information about a specific course.
 *
 * @param input - Numeric Canvas course ID (or "sis_course_id:<id>"); course codes are not resolved
 * @returns Course metadata including time_zone; syllabus_body is not requested
 */
export async function getCourseDetails(
  input: GetCourseDetailsInput
): Promise<CourseDetails> {
  const { courseIdentifier } = input;
  return canvasGet<CourseDetails>(`/courses/${courseIdentifier}`);
}
