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
 * @param input - Course identifier (code or ID)
 * @returns Detailed course information including syllabus and timezone
 */
export async function getCourseDetails(
  input: GetCourseDetailsInput
): Promise<CourseDetails> {
  const { courseIdentifier } = input;
  return canvasGet<CourseDetails>(`/courses/${courseIdentifier}`);
}
