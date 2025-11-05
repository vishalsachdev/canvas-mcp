import { callCanvasTool } from "../../client.js";

export interface Course {
  id: string;
  name: string;
  courseCode: string;
  workflowState: string;
  startAt?: string;
  endAt?: string;
  enrollmentTermId?: string;
}

/**
 * List all courses for the current user.
 *
 * Returns courses where the user is enrolled as a teacher or student.
 * Useful for discovering course identifiers before performing other operations.
 */
export async function listCourses(): Promise<Course[]> {
  return callCanvasTool<Course[]>('list_courses', {});
}
