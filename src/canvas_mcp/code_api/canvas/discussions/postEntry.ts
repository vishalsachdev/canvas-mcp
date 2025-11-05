import { callCanvasTool } from "../../client.js";

export interface PostEntryInput {
  courseIdentifier: string | number;
  topicId: string | number;
  message: string;
  attachmentIds?: string[];
}

export interface PostResponse {
  success: boolean;
  entryId?: string;
  error?: string;
}

/**
 * Post a new entry to a discussion topic.
 *
 * Creates a top-level entry in a discussion. Use this for participating
 * in class discussions or announcements.
 *
 * @param input - Discussion posting parameters
 * @returns Response with success status and entry ID
 */
export async function postEntry(
  input: PostEntryInput
): Promise<PostResponse> {
  return callCanvasTool<PostResponse>('post_discussion_entry', input);
}
