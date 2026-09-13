export * from './listDiscussions.js';
export * from './postEntry.js';
export * from './bulkGradeDiscussion.js';
// Resolve the barrel's name collision while preserving both direct-module types.
export type { DiscussionEntry } from './postEntry.js';
