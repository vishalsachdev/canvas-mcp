import { callCanvasTool } from "../../client.js";

export interface ListSubmissionsInput {
  courseIdentifier: string | number;
  assignmentId: string | number;
}

export interface Submission {
  id: string;
  userId: string;
  assignmentId: string;
  submittedAt: string | null;
  grade: string | null;
  score: number | null;
  attempt: number;
  workflowState: string;
  attachments?: Array<{
    id: string;
    filename: string;
    url: string;
    contentType: string;
  }>;
}

/**
 * Retrieve all submissions for a specific assignment.
 *
 * Returns array of student submissions with grades, submission times,
 * attachments, and workflow states.
 *
 * Use this to get submission data before processing/grading in bulk.
 * For token efficiency, process submissions locally rather than returning
 * all data to Claude's context.
 */
export async function listSubmissions(
  input: ListSubmissionsInput
): Promise<Submission[]> {
  return callCanvasTool<Submission[]>('list_submissions', input);
}
