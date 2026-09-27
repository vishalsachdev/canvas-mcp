import { test } from 'node:test';
import assert from 'node:assert/strict';
import { initializeCanvasClient } from '../../src/canvas_mcp/code_api/client.ts';
import { bulkGradeDiscussion } from '../../src/canvas_mcp/code_api/canvas/discussions/bulkGradeDiscussion.ts';

const input = {
  courseIdentifier: 1, topicId: 2, assignmentId: 3,
  criteria: {initialPostPoints: 10, peerReviewPointsEach: 5, requiredPeerReviews: 1},
};
const entries = [7, 8].map(id => ({id, user_id: id, parent_id: null,
  message: 'Initial post', created_at: '2026-09-01T00:00:00Z'}));

for (const dryRun of [false, true]) {
  test(`incomplete replies reject ${dryRun ? 'preview' : 'grading'} before any writes`, async t => {
    initializeCanvasClient('https://canvas.example/api/v1', 'synthetic');
    const reads: string[] = [];
    const writes: string[] = [];
    t.mock.method(globalThis, 'fetch', async (url: string, options: RequestInit) => {
      if (options.method !== 'GET') { writes.push(url); return Response.json({}); }
      reads.push(new URL(url).pathname);
      if (url.includes('/8/replies')) return new Response('Forbidden', {status: 403});
      if (url.includes('/7/replies')) return Response.json([]);
      return Response.json(entries);
    });
    await assert.rejects(bulkGradeDiscussion({...input, dryRun}), /incomplete.*replies.*8.*403/i);
    assert.ok(reads.some(path => path.endsWith('/7/replies')));
    assert.deepEqual(writes, []);
  });
}

test('complete data with no replies keeps the existing initial-post score', async t => {
  initializeCanvasClient('https://canvas.example/api/v1', 'synthetic');
  const grades: string[] = [];
  t.mock.method(globalThis, 'fetch', async (url: string, options: RequestInit) => {
    if (options.method === 'GET') return Response.json(url.includes('/replies') ? [] : entries);
    grades.push(new URLSearchParams(String(options.body)).get('submission[posted_grade]')!);
    return Response.json({});
  });
  const result = await bulkGradeDiscussion({...input, dryRun: false});
  assert.deepEqual(grades, ['10', '10']);
  assert.equal(result.graded, 2);
  assert.equal(result.failed, 0);
  assert.equal(result.averageScore, 10);
  assert.deepEqual(result.gradingResults.map(r => r.participation.peerReviewCount), [0, 0]);
});
