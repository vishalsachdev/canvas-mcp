/**
 * Common patterns and templates for Canvas Code API operations
 *
 * These templates provide reusable patterns for common bulk operations,
 * demonstrating best practices for token efficiency and error handling.
 */

import { canvasGet, canvasPut, canvasPost, fetchAllPaginated } from '../../client';

/**
 * Template: Filter and process submissions based on criteria
 *
 * Use this pattern when you need to:
 * - Process submissions that meet specific criteria
 * - Perform actions only on a subset of submissions
 * - Avoid loading unnecessary data into Claude's context
 */
export async function filterAndProcessSubmissions(
  courseId: string,
  assignmentId: string,
  filterFn: (submission: any) => boolean,
  processFn: (submission: any) => Promise<any>
): Promise<{ processed: number; skipped: number; errors: number }> {
  const submissions = await fetchAllPaginated(
    `/courses/${courseId}/assignments/${assignmentId}/submissions`,
    { include: ['user', 'submission_comments', 'rubric_assessment'] }
  );

  let processed = 0;
  let skipped = 0;
  let errors = 0;

  for (const submission of submissions) {
    try {
      if (filterFn(submission)) {
        await processFn(submission);
        processed++;
      } else {
        skipped++;
      }
    } catch (error) {
      console.error(`Error processing submission ${submission.id}:`, error);
      errors++;
    }
  }

  return { processed, skipped, errors };
}

/**
 * Template: Batch update with rate limiting
 *
 * Use this pattern when you need to:
 * - Update multiple items with API calls
 * - Respect Canvas API rate limits
 * - Process items in controlled batches
 */
export async function batchUpdateWithRateLimit<T>(
  items: T[],
  updateFn: (item: T) => Promise<any>,
  options: {
    batchSize?: number;
    delayMs?: number;
  } = {}
): Promise<{ successful: number; failed: number; results: any[] }> {
  const { batchSize = 5, delayMs = 1000 } = options;

  const results = [];
  let successful = 0;
  let failed = 0;

  // Process in batches
  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);

    const batchResults = await Promise.allSettled(
      batch.map(item => updateFn(item))
    );

    for (const result of batchResults) {
      if (result.status === 'fulfilled') {
        successful++;
        results.push(result.value);
      } else {
        failed++;
        console.error('Batch update failed:', result.reason);
      }
    }

    // Rate limit between batches
    if (i + batchSize < items.length) {
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }

  return { successful, failed, results };
}

/**
 * Template: Find students meeting criteria
 *
 * Use this pattern when you need to:
 * - Identify students based on performance/activity
 * - Send targeted communications
 * - Create intervention lists
 */
export async function findStudentsByCriteria(
  courseId: string,
  criteria: {
    minScore?: number;
    maxScore?: number;
    hasSubmitted?: boolean;
    isOverdue?: boolean;
  }
): Promise<Array<{ user_id: number; user_name: string; score: number | null }>> {
  const enrollments = await fetchAllPaginated(
    `/courses/${courseId}/enrollments`,
    {
      type: ['StudentEnrollment'],
      state: ['active'],
      include: ['user', 'grades']
    }
  );

  const matchingStudents = enrollments
    .filter(enrollment => {
      const score = enrollment.grades?.current_score;

      if (criteria.minScore !== undefined && (score === null || score < criteria.minScore)) {
        return false;
      }

      if (criteria.maxScore !== undefined && (score === null || score > criteria.maxScore)) {
        return false;
      }

      return true;
    })
    .map(enrollment => ({
      user_id: enrollment.user_id,
      user_name: enrollment.user?.name || 'Unknown',
      score: enrollment.grades?.current_score || null
    }));

  return matchingStudents;
}

/**
 * Template: Analyze and summarize data
 *
 * Use this pattern when you need to:
 * - Create statistical summaries
 * - Identify patterns or outliers
 * - Generate reports without loading all data into context
 */
export async function analyzeSubmissionQuality(
  courseId: string,
  assignmentId: string
): Promise<{
  totalSubmissions: number;
  averageScore: number;
  medianScore: number;
  distribution: Record<string, number>;
  outliers: Array<{ user_id: number; score: number }>;
}> {
  const submissions = await fetchAllPaginated(
    `/courses/${courseId}/assignments/${assignmentId}/submissions`,
    { include: ['user'] }
  );

  // Filter out submissions without scores
  const scoredSubmissions = submissions.filter(s => s.score !== null);

  if (scoredSubmissions.length === 0) {
    return {
      totalSubmissions: 0,
      averageScore: 0,
      medianScore: 0,
      distribution: {},
      outliers: []
    };
  }

  // Calculate statistics
  const scores = scoredSubmissions.map(s => s.score);
  const average = scores.reduce((a, b) => a + b, 0) / scores.length;

  const sorted = [...scores].sort((a, b) => a - b);
  const median = sorted.length % 2 === 0
    ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
    : sorted[Math.floor(sorted.length / 2)];

  // Grade distribution
  const distribution: Record<string, number> = {
    'A (90-100)': 0,
    'B (80-89)': 0,
    'C (70-79)': 0,
    'D (60-69)': 0,
    'F (0-59)': 0
  };

  scores.forEach(score => {
    if (score >= 90) distribution['A (90-100)']++;
    else if (score >= 80) distribution['B (80-89)']++;
    else if (score >= 70) distribution['C (70-79)']++;
    else if (score >= 60) distribution['D (60-69)']++;
    else distribution['F (0-59)']++;
  });

  // Find outliers (scores > 2 standard deviations from mean)
  const stdDev = Math.sqrt(
    scores.reduce((sum, score) => sum + Math.pow(score - average, 2), 0) / scores.length
  );

  const outliers = scoredSubmissions
    .filter(s => Math.abs(s.score - average) > 2 * stdDev)
    .map(s => ({ user_id: s.user_id, score: s.score }));

  return {
    totalSubmissions: scoredSubmissions.length,
    averageScore: average,
    medianScore: median,
    distribution,
    outliers
  };
}

/**
 * Template: Conditional grading with rubrics
 *
 * Use this pattern when you need to:
 * - Apply rubric-based grading with logic
 * - Grade based on file analysis or content checks
 * - Implement custom grading algorithms
 */
export async function conditionalRubricGrading(
  courseId: string,
  assignmentId: string,
  rubricCriterionId: string,
  gradingLogic: (submission: any) => {
    points: number;
    comments?: string;
  } | null
): Promise<{ graded: number; skipped: number; errors: number }> {
  const submissions = await fetchAllPaginated(
    `/courses/${courseId}/assignments/${assignmentId}/submissions`,
    { include: ['user', 'attachments'] }
  );

  let graded = 0;
  let skipped = 0;
  let errors = 0;

  for (const submission of submissions) {
    try {
      const result = gradingLogic(submission);

      if (result === null) {
        skipped++;
        continue;
      }

      const rubricAssessment: Record<string, any> = {};
      rubricAssessment[rubricCriterionId] = {
        points: result.points,
        ...(result.comments && { comments: result.comments })
      };

      // Convert rubric assessment to form data
      const formData: Record<string, string> = {};
      for (const [criterionId, assessment] of Object.entries(rubricAssessment)) {
        formData[`rubric_assessment[${criterionId}][points]`] = String(assessment.points);
        if (assessment.comments) {
          formData[`rubric_assessment[${criterionId}][comments]`] = assessment.comments;
        }
      }

      await canvasPut(
        `/courses/${courseId}/assignments/${assignmentId}/submissions/${submission.user_id}`,
        formData,
        true // use form encoding
      );

      graded++;
    } catch (error) {
      console.error(`Error grading submission ${submission.id}:`, error);
      errors++;
    }
  }

  return { graded, skipped, errors };
}

/**
 * Template: Export data to CSV format
 *
 * Use this pattern when you need to:
 * - Export gradebook data
 * - Create reports for external analysis
 * - Generate student rosters
 */
export function exportToCSV(
  data: Array<Record<string, any>>,
  columns: Array<{ key: string; header: string }>
): string {
  // Create header row
  const headers = columns.map(c => c.header).join(',');

  // Create data rows
  const rows = data.map(item =>
    columns.map(col => {
      const value = item[col.key];
      // Escape commas and quotes in CSV
      if (value === null || value === undefined) return '';
      const stringValue = String(value);
      if (stringValue.includes(',') || stringValue.includes('"')) {
        return `"${stringValue.replace(/"/g, '""')}"`;
      }
      return stringValue;
    }).join(',')
  );

  return [headers, ...rows].join('\n');
}

/**
 * Example usage of templates
 */
export async function exampleUsage() {
  // Example 1: Grade all ungraded Jupyter notebook submissions
  await filterAndProcessSubmissions(
    '12345',
    '67890',
    // Filter: Only ungraded submissions with .ipynb files
    submission => {
      return submission.score === null &&
        submission.attachments?.some((f: any) => f.filename.endsWith('.ipynb'));
    },
    // Process: Analyze and grade
    async submission => {
      // Your grading logic here
      console.log(`Grading submission ${submission.id}`);
      // Return grade result
    }
  );

  // Example 2: Find struggling students
  const strugglingStudents = await findStudentsByCriteria('12345', {
    maxScore: 70  // Students scoring below 70%
  });

  console.log(`Found ${strugglingStudents.length} students who may need support`);

  // Example 3: Get assignment statistics
  const stats = await analyzeSubmissionQuality('12345', '67890');
  console.log(`Assignment Statistics:`, stats);
}
