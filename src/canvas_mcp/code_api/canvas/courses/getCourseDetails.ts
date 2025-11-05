import { callCanvasTool } from "../../client.js";

export interface GetCourseDetailsInput {
  courseIdentifier: string | number;
}

export interface CourseDetails {
  id: string;
  name: string;
  courseCode: string;
  workflowState: string;
  startAt?: string;
  endAt?: string;
  timeZone?: string;
  syllabus?: string;
  enrollmentTermId?: string;
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
  return callCanvasTool<CourseDetails>('get_course_details', input);
}
