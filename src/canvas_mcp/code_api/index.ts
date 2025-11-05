/**
 * Canvas MCP Code Execution API - Main Entry Point
 *
 * This API enables token-efficient bulk operations by running code
 * locally in the execution environment rather than loading all data
 * into Claude's context.
 *
 * Token savings example:
 * - Traditional: 90 submissions × 15K tokens = 1.35M tokens
 * - Code execution: ~3.5K tokens (99.7% savings!)
 *
 * @example
 * ```typescript
 * import { bulkGrade, listCourses } from 'canvas-mcp/code_api';
 *
 * // Discover available tools
 * // Use search_canvas_tools MCP tool
 *
 * // Perform bulk grading
 * await bulkGrade({
 *   courseIdentifier: "60366",
 *   assignmentId: "123",
 *   gradingFunction: (submission) => {
 *     // This runs locally - no token cost!
 *     return analyzeSubmission(submission);
 *   }
 * });
 * ```
 */

export * from './canvas/index.js';
export * from './client.js';
