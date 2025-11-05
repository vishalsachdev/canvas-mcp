import { canvasPost } from "../../client.js";

export interface SendMessageInput {
  recipients: string[];
  subject: string;
  body: string;
  contextCode?: string;
  attachmentIds?: number[];
}

export interface Conversation {
  id: number;
  subject: string;
  workflow_state: string;
  last_message: string;
  participants: Array<{
    id: number;
    name: string;
  }>;
}

/**
 * Send a message to one or more recipients via Canvas inbox.
 *
 * Recipients can be specified by user ID or special identifiers like
 * "course_123_students" or "course_123_teachers".
 *
 * @param input - Message parameters
 * @returns Canvas API response with conversation data
 */
export async function sendMessage(
  input: SendMessageInput
): Promise<Conversation[]> {
  const { recipients, subject, body, contextCode, attachmentIds } = input;

  const requestBody: Record<string, any> = {
    recipients,
    subject,
    body
  };

  if (contextCode) {
    requestBody.context_code = contextCode;
  }

  if (attachmentIds && attachmentIds.length > 0) {
    requestBody.attachment_ids = attachmentIds;
  }

  return canvasPost<Conversation[]>('/conversations', requestBody);
}
