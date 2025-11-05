import { canvasPost } from "../../client.js";

export interface PostEntryInput {
  courseIdentifier: string | number;
  topicId: string | number;
  message: string;
  attachmentIds?: number[];
}

export interface DiscussionEntry {
  id: number;
  user_id: number;
  message: string;
  created_at: string;
}

/**
 * Post a new entry to a discussion topic.
 *
 * Creates a top-level entry in a discussion. Use this for participating
 * in class discussions or announcements.
 *
 * @param input - Discussion posting parameters
 * @returns Canvas API response with created entry data
 */
export async function postEntry(
  input: PostEntryInput
): Promise<DiscussionEntry> {
  const { courseIdentifier, topicId, message, attachmentIds } = input;

  const body: Record<string, any> = {
    message
  };

  if (attachmentIds && attachmentIds.length > 0) {
    body.attachment_ids = attachmentIds;
  }

  return canvasPost<DiscussionEntry>(
    `/courses/${courseIdentifier}/discussion_topics/${topicId}/entries`,
    body
  );
}
