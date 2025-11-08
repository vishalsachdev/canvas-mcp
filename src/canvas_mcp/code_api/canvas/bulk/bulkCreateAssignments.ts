/**
 * Bulk create assignments from a template or configuration
 *
 * Token efficient: Creates multiple assignments without loading full course data into context
 */

import { callTool } from '../../../client';

interface AssignmentTemplate {
  name: string;
  description?: string;
  points_possible?: number;
  due_at?: string;
  submission_types?: string[];
  published?: boolean;
  grading_type?: string;
}

interface BulkCreateAssignmentsOptions {
  courseIdentifier: string;
  assignments: AssignmentTemplate[];
  dryRun?: boolean;
}

interface BulkCreateResult {
  success: number;
  failed: number;
  errors: Array<{ assignment: string; error: string }>;
  created: Array<{ id: number; name: string }>;
}

/**
 * Bulk create assignments in a course
 */
export async function bulkCreateAssignments(
  options: BulkCreateAssignmentsOptions
): Promise<BulkCreateResult> {
  const { courseIdentifier, assignments, dryRun = false } = options;

  const result: BulkCreateResult = {
    success: 0,
    failed: 0,
    errors: [],
    created: []
  };

  console.log(`📝 Bulk creating ${assignments.length} assignments in course ${courseIdentifier}`);

  if (dryRun) {
    console.log('🔍 DRY RUN MODE - No assignments will be created');
  }

  for (const assignment of assignments) {
    try {
      if (dryRun) {
        console.log(`  [DRY RUN] Would create: ${assignment.name}`);
        result.success++;
        continue;
      }

      // Create the assignment using MCP tool
      const createResult = await callTool('create_assignment', {
        course_identifier: courseIdentifier,
        name: assignment.name,
        description: assignment.description || '',
        points_possible: assignment.points_possible || 100,
        due_at: assignment.due_at,
        submission_types: assignment.submission_types || ['online_text_entry'],
        published: assignment.published || false,
        grading_type: assignment.grading_type || 'points'
      });

      // Parse the assignment ID from the result
      const idMatch = createResult.match(/Assignment ID: (\d+)/);
      if (idMatch) {
        const assignmentId = parseInt(idMatch[1]);
        result.created.push({ id: assignmentId, name: assignment.name });
        result.success++;
        console.log(`  ✅ Created: ${assignment.name} (ID: ${assignmentId})`);
      } else {
        throw new Error('Failed to parse assignment ID from response');
      }

    } catch (error) {
      result.failed++;
      result.errors.push({
        assignment: assignment.name,
        error: error instanceof Error ? error.message : String(error)
      });
      console.error(`  ❌ Failed to create ${assignment.name}:`, error);
    }
  }

  console.log(`\n📊 Summary: ${result.success} created, ${result.failed} failed`);

  return result;
}
