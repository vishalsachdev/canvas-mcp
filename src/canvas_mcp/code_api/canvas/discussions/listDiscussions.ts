import { callCanvasTool } from "../../client.js";

export interface ListDiscussionsInput {
  courseIdentifier: string | number;
}

export interface Discussion {
  id: string;
  title: string;
  message?: string;
  postedAt: string;
  author?: {
    id: string;
    displayName: string;
  };
  discussionType?: string;
  published: boolean;
}

/**
 * List all discussion topics in a course.
 *
 * Returns discussion topics including announcements and regular discussions.
 * Use this to discover discussion IDs before reading entries or posting.
 */
export async function listDiscussions(
  input: ListDiscussionsInput
): Promise<Discussion[]> {
  return callCanvasTool<Discussion[]>('list_discussions', input);
}
