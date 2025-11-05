import { fetchAllPaginated } from "../../client.js";

export interface ListDiscussionsInput {
  courseIdentifier: string | number;
}

export interface Discussion {
  id: number;
  title: string;
  message?: string;
  posted_at: string;
  author?: {
    id: number;
    display_name: string;
  };
  discussion_type?: string;
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
  const { courseIdentifier } = input;
  return fetchAllPaginated<Discussion>(
    `/courses/${courseIdentifier}/discussion_topics`,
    { per_page: 100 }
  );
}
