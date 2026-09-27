import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { initializeCanvasClient } from '../../src/canvas_mcp/code_api/client.ts';
import { bulkGrade } from '../../src/canvas_mcp/code_api/canvas/grading/bulkGrade.ts';
import { bulkGradeDiscussion } from '../../src/canvas_mcp/code_api/canvas/discussions/bulkGradeDiscussion.ts';

type Controls = {maxConcurrent?: number; rateLimitDelay?: number; dryRun?: boolean};
beforeEach(t => {
  t.mock.method(console, 'log', () => {});
  t.mock.method(console, 'error', () => {});
});
const workflows = {
  submissions: (controls: Controls) => bulkGrade({courseIdentifier: 1, assignmentId: 3,
    gradingFunction: () => ({grade: 10}), ...controls}),
  discussions: (controls: Controls) => bulkGradeDiscussion({courseIdentifier: 1, topicId: 2,
    assignmentId: 3, criteria: {initialPostPoints: 10, peerReviewPointsEach: 5, requiredPeerReviews: 1}, ...controls}),
};
for (const [name, run] of Object.entries(workflows)) {
  for (const [key, values] of Object.entries({maxConcurrent: [0, -1, 1.5, NaN, Infinity],
    rateLimitDelay: [-1, 0.5, NaN, Infinity, 2147483648]})) {
    for (const value of values) test(`${name}: rejects ${key}=${value} before reads, including preview`, async t => {
      let requests = 0;
      t.mock.method(globalThis, 'fetch', async () => { requests++; return Response.json([]); });
      await assert.rejects(run({[key]: value, dryRun: true}), new RegExp(key));
      assert.equal(requests, 0);
    });
  }
  for (const delay of [0, 17]) test(`${name}: cap, settlement, failure accounting and delay ${delay}`, async t => {
    initializeCanvasClient('https://canvas.example/api/v1', 'synthetic');
    const records = [1, 2, 3, 4, 5].map(id => ({id, user_id: id, parent_id: null,
      message: 'Post', created_at: '2026-09-01T00:00:00Z'}));
    let active = 0, peak = 0;
    const targets: string[] = [], timers: number[] = [], settled: string[] = [];
    t.mock.method(globalThis, 'setTimeout', ((fn: () => void, ms: number) => {
      assert.equal(active, 0);
      timers.push(ms);
      return setImmediate(fn);
    }) as unknown as typeof setTimeout);
    t.mock.method(globalThis, 'fetch', async (url: string, options: RequestInit) => {
      if (options.method === 'GET') return Response.json(url.includes('/replies') ? [] : records);
      const target = new URL(url).pathname.split('/').pop()!;
      if (target === '3') assert.deepEqual(settled.sort(), ['1', '2']);
      targets.push(target); active++; peak = Math.max(peak, active);
      await new Promise<void>(resolve => setImmediate(resolve));
      active--; settled.push(target);
      return target === '2' ? new Response('Forbidden', {status: 403}) : Response.json({score: 10, grade: '10'});
    });
    const result = await run({maxConcurrent: 2, rateLimitDelay: delay});
    assert.equal(peak, 2);
    assert.deepEqual(targets, ['1', '2', '3', '4', '5']);
    assert.deepEqual(timers, delay ? [17, 17] : []);
    assert.deepEqual([result.total, result.graded, result.failed], [5, 4, 1]);
    assert.deepEqual(result.failedResults.map(r => r.userId), [2]);
  });
}

test('large valid batches retain outcomes without exceeding the argument limit', async () => {
  const { createBatchRunner } = await import('../../src/canvas_mcp/code_api/batching.ts');
  const results = await createBatchRunner({maxConcurrent: 200000, rateLimitDelay: 0})(
    Array.from({length: 200001}, (_, i) => i), async item => item);
  assert.equal(results.length, 200001);
  assert.deepEqual(results[200000], {status: 'fulfilled', value: 200000});
});
