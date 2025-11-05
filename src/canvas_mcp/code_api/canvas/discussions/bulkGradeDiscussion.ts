import { canvasGet, canvasPut, fetchAllPaginated } from "../../client.js";

export interface DiscussionEntry {
  id: number;
  user_id: number;
  parent_id?: number | null;
  message: string;
  created_at: string;
  updated_at?: string;
  user_name?: string;
}

export interface StudentParticipation {
  userId: number;
  userName: string;
  hasInitialPost: boolean;
  initialPostId?: number;
  initialPostDate?: string;
  peerReviews: Array<{
    reviewedUserId: number;
    entryId: number;
    date: string;
  }>;
  peerReviewCount: number;
  totalPosts: number;
}

export interface GradingCriteria {
  initialPostPoints: number;        // Points for initial post
  peerReviewPointsEach: number;     // Points per peer review
  requiredPeerReviews: number;      // Minimum peer reviews needed
  maxPeerReviewPoints?: number;     // Cap on peer review points
  latePenalty?: {
    enabled: boolean;
    deadline: Date;
    penaltyPercent: number;         // e.g., 0.1 = 10% penalty
  };
}

export interface BulkGradeDiscussionInput {
  courseIdentifier: string | number;
  topicId: string | number;
  assignmentId?: string | number;   // Required if discussion is graded
  criteria: GradingCriteria;
  dryRun?: boolean;
  maxConcurrent?: number;
  rateLimitDelay?: number;
}

export interface GradingResult {
  userId: number;
  userName: string;
  participation: StudentParticipation;
  score: number;
  breakdown: {
    initialPostPoints: number;
    peerReviewPoints: number;
    latePenalty: number;
    finalScore: number;
  };
  notes: string[];  // Warning/info messages
}

export interface BulkGradeDiscussionResult {
  total: number;
  graded: number;
  skipped: number;
  failed: number;
  averageScore: number;
  summary: {
    withInitialPost: number;
    withoutInitialPost: number;
    metPeerReviewRequirement: number;
    belowPeerReviewRequirement: number;
  };
  gradingResults: GradingResult[];  // First 10 for review
  failedResults: Array<{
    userId: number;
    userName: string;
    error: string;
  }>;
}

/**
 * Fetch all discussion entries including nested replies
 */
async function fetchAllDiscussionEntries(
  courseIdentifier: string | number,
  topicId: string | number
): Promise<DiscussionEntry[]> {
  // Fetch all top-level entries
  const entries = await fetchAllPaginated<DiscussionEntry>(
    `/courses/${courseIdentifier}/discussion_topics/${topicId}/entries`,
    { per_page: 100 }
  );

  // Now fetch replies for each entry
  const allEntries: DiscussionEntry[] = [...entries];

  for (const entry of entries) {
    try {
      const replies = await fetchAllPaginated<DiscussionEntry>(
        `/courses/${courseIdentifier}/discussion_topics/${topicId}/entries/${entry.id}/replies`,
        { per_page: 100 }
      );

      if (replies && Array.isArray(replies)) {
        allEntries.push(...replies);
      }
    } catch (error) {
      console.warn(`Failed to fetch replies for entry ${entry.id}:`, error);
      // Continue processing other entries
    }
  }

  return allEntries;
}

/**
 * Find the top-level parent post for a reply
 */
function findTopLevelParent(
  reply: DiscussionEntry,
  allEntries: DiscussionEntry[]
): DiscussionEntry | null {

  let current = reply;

  while (current.parent_id) {
    const parent = allEntries.find(e => e.id === current.parent_id);
    if (!parent) break;
    current = parent;
  }

  return current.parent_id ? null : current;
}

/**
 * Organize entries by student and classify as initial post or peer review
 */
function analyzeStudentParticipation(
  entries: DiscussionEntry[]
): Map<number, StudentParticipation> {

  const participationMap = new Map<number, StudentParticipation>();

  // Separate top-level posts from replies
  const topLevelPosts = entries.filter(e => !e.parent_id);
  const replies = entries.filter(e => e.parent_id);

  // Build map of initial posts (top-level by each user)
  for (const post of topLevelPosts) {
    if (!participationMap.has(post.user_id)) {
      participationMap.set(post.user_id, {
        userId: post.user_id,
        userName: post.user_name || `User ${post.user_id}`,
        hasInitialPost: false,
        peerReviews: [],
        peerReviewCount: 0,
        totalPosts: 0
      });
    }

    const participation = participationMap.get(post.user_id)!;

    // First top-level post is the initial post
    if (!participation.hasInitialPost) {
      participation.hasInitialPost = true;
      participation.initialPostId = post.id;
      participation.initialPostDate = post.created_at;
    }

    participation.totalPosts++;
  }

  // Build map of replies (peer reviews)
  for (const reply of replies) {
    // Find the top-level post that was reviewed
    const parentPost = findTopLevelParent(reply, entries);

    if (!parentPost || parentPost.user_id === reply.user_id) {
      // Skip self-replies or invalid replies
      continue;
    }

    if (!participationMap.has(reply.user_id)) {
      participationMap.set(reply.user_id, {
        userId: reply.user_id,
        userName: reply.user_name || `User ${reply.user_id}`,
        hasInitialPost: false,
        peerReviews: [],
        peerReviewCount: 0,
        totalPosts: 0
      });
    }

    const participation = participationMap.get(reply.user_id)!;

    participation.peerReviews.push({
      reviewedUserId: parentPost.user_id,
      entryId: reply.id,
      date: reply.created_at
    });
    participation.peerReviewCount++;
    participation.totalPosts++;
  }

  return participationMap;
}

/**
 * Calculate grade based on participation and criteria
 */
function calculateGrade(
  participation: StudentParticipation,
  criteria: GradingCriteria
): GradingResult {

  const notes: string[] = [];
  let initialPostPoints = 0;
  let peerReviewPoints = 0;
  let latePenalty = 0;

  // Calculate initial post points
  if (participation.hasInitialPost) {
    initialPostPoints = criteria.initialPostPoints;
    notes.push(`Initial post: ${initialPostPoints} pts`);
  } else {
    notes.push(`Missing initial post: 0 pts`);
  }

  // Calculate peer review points
  const peerReviewsCompleted = Math.min(
    participation.peerReviewCount,
    criteria.maxPeerReviewPoints
      ? Math.floor(criteria.maxPeerReviewPoints / criteria.peerReviewPointsEach)
      : participation.peerReviewCount
  );

  peerReviewPoints = peerReviewsCompleted * criteria.peerReviewPointsEach;

  if (criteria.maxPeerReviewPoints) {
    peerReviewPoints = Math.min(peerReviewPoints, criteria.maxPeerReviewPoints);
  }

  if (participation.peerReviewCount >= criteria.requiredPeerReviews) {
    notes.push(
      `Peer reviews: ${participation.peerReviewCount}/${criteria.requiredPeerReviews} required = ${peerReviewPoints} pts`
    );
  } else {
    notes.push(
      `Peer reviews: ${participation.peerReviewCount}/${criteria.requiredPeerReviews} required (incomplete) = ${peerReviewPoints} pts`
    );
  }

  // Calculate late penalty
  if (criteria.latePenalty?.enabled && participation.initialPostDate) {
    const postDate = new Date(participation.initialPostDate);
    const deadline = criteria.latePenalty.deadline;

    if (postDate > deadline) {
      const baseScore = initialPostPoints + peerReviewPoints;
      latePenalty = baseScore * criteria.latePenalty.penaltyPercent;
      notes.push(
        `Late penalty: ${(criteria.latePenalty.penaltyPercent * 100).toFixed(0)}% = -${latePenalty.toFixed(2)} pts`
      );
    }
  }

  const finalScore = Math.max(0, initialPostPoints + peerReviewPoints - latePenalty);

  return {
    userId: participation.userId,
    userName: participation.userName,
    participation,
    score: finalScore,
    breakdown: {
      initialPostPoints,
      peerReviewPoints,
      latePenalty,
      finalScore
    },
    notes
  };
}

/**
 * Grade a discussion submission in Canvas
 */
async function gradeDiscussionSubmission(
  courseIdentifier: string | number,
  assignmentId: string | number,
  userId: number,
  score: number,
  comment: string
): Promise<void> {

  // Canvas discussions that are graded have an associated assignment
  // We grade them like any other assignment submission

  const endpoint = `/courses/${courseIdentifier}/assignments/${assignmentId}/submissions/${userId}`;

  // Build form data for Canvas API
  const formData: Record<string, string> = {
    'submission[posted_grade]': String(score)
  };

  if (comment) {
    formData['comment[text_comment]'] = comment;
  }

  await canvasPut(endpoint, formData);
}

/**
 * Grade a discussion topic based on initial posts and peer reviews.
 *
 * THIS IS THE MOST TOKEN-EFFICIENT WAY TO GRADE DISCUSSION BOARDS.
 *
 * Fetches all discussion entries and replies, analyzes participation locally,
 * and applies grading logic without loading all data into Claude's context.
 * Only summary results flow back to Claude.
 *
 * Common grading patterns:
 * - Initial post (10 pts) + 2 peer reviews (5 pts each) = 20 pts total
 * - Initial post (50%) + peer reviews (50%) with minimum requirements
 * - Participation credit with late penalties
 *
 * @param input - Configuration for discussion grading
 * @param input.criteria - Grading criteria and point allocation
 * @param input.assignmentId - Required for graded discussions (to write grades)
 * @param input.dryRun - If true, analyze but don't write grades
 *
 * @example
 * ```typescript
 * // Grade: 10 pts initial post + 5 pts per review (need 2, max 10 pts)
 * await bulkGradeDiscussion({
 *   courseIdentifier: "60365",
 *   topicId: "990001",
 *   assignmentId: "1234567",  // The graded assignment ID
 *   criteria: {
 *     initialPostPoints: 10,
 *     peerReviewPointsEach: 5,
 *     requiredPeerReviews: 2,
 *     maxPeerReviewPoints: 10
 *   },
 *   dryRun: true  // Preview grades first
 * });
 * ```
 *
 * @example
 * ```typescript
 * // Grade with late penalty
 * await bulkGradeDiscussion({
 *   courseIdentifier: "60365",
 *   topicId: "990001",
 *   assignmentId: "1234567",
 *   criteria: {
 *     initialPostPoints: 10,
 *     peerReviewPointsEach: 5,
 *     requiredPeerReviews: 2,
 *     latePenalty: {
 *       enabled: true,
 *       deadline: new Date('2025-11-01T00:00:00Z'),
 *       penaltyPercent: 0.1  // 10% penalty
 *     }
 *   },
 *   dryRun: false
 * });
 * ```
 */
export async function bulkGradeDiscussion(
  input: BulkGradeDiscussionInput
): Promise<BulkGradeDiscussionResult> {

  console.log(`Starting bulk discussion grading for topic ${input.topicId}...`);
  console.log(`Criteria:`, JSON.stringify(input.criteria, null, 2));

  // Step 1: Fetch all discussion entries with replies
  const entries = await fetchAllDiscussionEntries(
    input.courseIdentifier,
    input.topicId
  );

  console.log(`Fetched ${entries.length} total discussion entries`);

  // Step 2: Organize entries by student
  const participationMap = analyzeStudentParticipation(entries);

  console.log(`Analyzed participation for ${participationMap.size} students`);

  // Step 3: Calculate grades for each student
  const gradingResults: GradingResult[] = [];

  for (const [userId, participation] of participationMap.entries()) {
    const result = calculateGrade(participation, input.criteria);
    gradingResults.push(result);
  }

  // Step 4: Apply grades (if not dry run and assignmentId provided)
  let graded = 0;
  let skipped = 0;
  let failed = 0;
  const failedResults: Array<{ userId: number; userName: string; error: string }> = [];

  if (!input.dryRun && input.assignmentId) {
    console.log(`\nApplying grades to Canvas...`);

    const maxConcurrent = input.maxConcurrent || 5;
    const rateLimitDelay = input.rateLimitDelay || 1000;

    // Process in batches
    for (let i = 0; i < gradingResults.length; i += maxConcurrent) {
      const batch = gradingResults.slice(i, i + maxConcurrent);
      const batchNum = Math.floor(i / maxConcurrent) + 1;
      const totalBatches = Math.ceil(gradingResults.length / maxConcurrent);

      console.log(`Processing batch ${batchNum}/${totalBatches}...`);

      const results = await Promise.allSettled(
        batch.map(async (result) => {
          try {
            await gradeDiscussionSubmission(
              input.courseIdentifier,
              input.assignmentId!,
              result.userId,
              result.score,
              result.notes.join('\n')
            );
            graded++;
            console.log(`✓ Graded ${result.userName}: ${result.score} points`);
          } catch (error: any) {
            failed++;
            failedResults.push({
              userId: result.userId,
              userName: result.userName,
              error: error.message || String(error)
            });
            console.error(`✗ Failed to grade ${result.userName}: ${error.message || error}`);
          }
        })
      );

      // Rate limit between batches
      if (i + maxConcurrent < gradingResults.length) {
        await new Promise(resolve => setTimeout(resolve, rateLimitDelay));
      }
    }
  } else {
    skipped = gradingResults.length;
    if (input.dryRun) {
      console.log(`\nDry run mode - no grades applied`);
    } else if (!input.assignmentId) {
      console.log(`\nNo assignmentId provided - cannot apply grades`);
    }
  }

  // Step 5: Calculate summary statistics
  const totalScore = gradingResults.reduce((sum, r) => sum + r.score, 0);
  const averageScore = gradingResults.length > 0 ? totalScore / gradingResults.length : 0;

  const withInitialPost = gradingResults.filter(r => r.participation.hasInitialPost).length;
  const withoutInitialPost = gradingResults.length - withInitialPost;
  const metPeerReviewRequirement = gradingResults.filter(
    r => r.participation.peerReviewCount >= input.criteria.requiredPeerReviews
  ).length;
  const belowPeerReviewRequirement = gradingResults.length - metPeerReviewRequirement;

  console.log(`\n${'='.repeat(60)}`);
  console.log(`Bulk Discussion Grading Complete!`);
  console.log(`${'='.repeat(60)}`);
  console.log(`Total students: ${gradingResults.length}`);
  console.log(`Graded: ${graded}`);
  console.log(`Skipped: ${skipped}`);
  console.log(`Failed: ${failed}`);
  console.log(`Average score: ${averageScore.toFixed(2)}`);
  console.log(`\nParticipation Summary:`);
  console.log(`  With initial post: ${withInitialPost}`);
  console.log(`  Without initial post: ${withoutInitialPost}`);
  console.log(`  Met peer review requirement: ${metPeerReviewRequirement}`);
  console.log(`  Below peer review requirement: ${belowPeerReviewRequirement}`);

  return {
    total: gradingResults.length,
    graded,
    skipped,
    failed,
    averageScore,
    summary: {
      withInitialPost,
      withoutInitialPost,
      metPeerReviewRequirement,
      belowPeerReviewRequirement
    },
    gradingResults: gradingResults.slice(0, 10),  // First 10 for review
    failedResults
  };
}
