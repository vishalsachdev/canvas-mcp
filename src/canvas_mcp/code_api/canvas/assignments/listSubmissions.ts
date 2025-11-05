import { fetchAllPaginated } from "../../client.js";

export interface ListSubmissionsInput {
  courseIdentifier: string | number;
  assignmentId: string | number;
}

export interface Submission {
  id: number;
  user_id: number;
  assignment_id: number;
  submitted_at: string | null;
  grade: string | null;
  score: number | null;
  attempt: number;
  workflow_state: string;
  attachments?: Array<{
    id: number;
    filename: string;
    url: string;
    content_type: string;
    size: number;
  }>;
}

/**
 * Retrieve all submissions for a specific assignment.
 *
 * Makes direct Canvas API calls to fetch submission data efficiently.
 * Returns raw Canvas API response with snake_case field names.
 *
 * Use this to get submission data before processing/grading in bulk.
 * For token efficiency, process submissions locally rather than returning
 * all data to Claude's context.
 *
 * @param input - Course and assignment identifiers
 * @returns Array of submission objects from Canvas API
 */
export async function listSubmissions(
  input: ListSubmissionsInput
): Promise<Submission[]> {
  const { courseIdentifier, assignmentId } = input;

  // Canvas API endpoint for submissions
  const endpoint = `/courses/${courseIdentifier}/assignments/${assignmentId}/submissions`;

  // Fetch all paginated submissions
  const submissions = await fetchAllPaginated<Submission>(endpoint, {
    per_page: 100
  });

  return submissions;
}
