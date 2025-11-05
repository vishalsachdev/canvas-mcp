/**
 * Canvas MCP Code Execution API
 *
 * This module provides TypeScript wrappers around Canvas MCP tools
 * for token-efficient code execution patterns.
 *
 * Use these when processing large datasets or performing bulk operations
 * to avoid loading all data into Claude's context.
 *
 * Example:
 * ```typescript
 * import { bulkGrade } from './grading';
 *
 * await bulkGrade({
 *   courseIdentifier: "60366",
 *   assignmentId: "123",
 *   gradingFunction: (submission) => {
 *     // Process locally
 *     return analyzeSubmission(submission);
 *   }
 * });
 * ```
 */

export * from './courses/index.js';
export * from './assignments/index.js';
export * from './grading/index.js';
export * from './discussions/index.js';
export * from './communications/index.js';
