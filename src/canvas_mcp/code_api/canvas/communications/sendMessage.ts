import { callCanvasTool } from "../../client.js";

export interface SendMessageInput {
  recipients: string[];
  subject: string;
  body: string;
  contextCode?: string;
  attachmentIds?: string[];
}

export interface SendMessageResponse {
  success: boolean;
  conversationId?: string;
  error?: string;
}

/**
 * Send a message to one or more recipients via Canvas inbox.
 *
 * Recipients can be specified by user ID or special identifiers like
 * "course_123_students" or "course_123_teachers".
 *
 * @param input - Message parameters
 * @returns Response with success status and conversation ID
 */
export async function sendMessage(
  input: SendMessageInput
): Promise<SendMessageResponse> {
  return callCanvasTool<SendMessageResponse>('send_message', input);
}
