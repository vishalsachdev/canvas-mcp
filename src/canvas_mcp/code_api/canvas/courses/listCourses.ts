import { fetchAllPaginated } from "../../client.js";

export interface Course {
  id: number;
  name: string;
  course_code: string;
  workflow_state: string;
  start_at?: string;
  end_at?: string;
  enrollment_term_id?: number;
}

/**
 * List all courses for the current user.
 *
 * Returns courses where the user is enrolled as a teacher or student.
 * Useful for discovering course identifiers before performing other operations.
 */
export async function listCourses(): Promise<Course[]> {
  return fetchAllPaginated<Course>('/courses', {
    per_page: 100
  });
}
