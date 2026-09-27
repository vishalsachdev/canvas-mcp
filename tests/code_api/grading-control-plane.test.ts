import { beforeEach, test, type TestContext } from 'node:test';
import assert from 'node:assert/strict';
import { initializeCanvasClient, canvasGet, canvasPost, canvasPut, canvasDelete } from '../../src/canvas_mcp/code_api/client.ts';
import { bulkGrade } from '../../src/canvas_mcp/code_api/canvas/grading/bulkGrade.ts';

// Tests inspect behavior and transport, not progress output. Keep synchronous
// console writes out of the worker IPC stream while global timers are mocked.
beforeEach(t => {
  t.mock.method(console, 'log', () => {});
  t.mock.method(console, 'warn', () => {});
  t.mock.method(console, 'error', () => {});
});

function fastTimers(t: TestContext): number[] {
  const delays: number[] = [];
  const original = globalThis.setTimeout;
  t.mock.method(globalThis, 'setTimeout', ((fn: (...args: any[]) => void, ms: number, ...args: any[]) => {
    delays.push(ms);
    return original(fn, 0, ...args);
  }) as typeof setTimeout);
  return delays;
}

function submissions(t: TestContext, users: number[]) {
  initializeCanvasClient('https://canvas.example/api/v1', 'synthetic');
  const writes: string[] = [];
  t.mock.method(globalThis, 'fetch', async (url: string, options: RequestInit) => {
    if (options.method === 'GET') return Response.json(users.map(user_id => ({user_id})));
    writes.push(url);
    return Response.json({score: 5, grade: '5'});
  });
  return writes;
}

test('duplicate submission targets reject before callbacks or writes', async t => {
  const writes = submissions(t, [7, 7]);
  let callbacks = 0;
  await assert.rejects(bulkGrade({courseIdentifier: 1, assignmentId: 2,
    gradingFunction: () => { callbacks++; return {grade: 5}; }}), /duplicate/i);
  assert.equal(callbacks, 0);
  assert.equal(writes.length, 0);
});

for (const maxConcurrent of [0, -1, 1.5, NaN, Infinity]) {
  test(`invalid maxConcurrent ${maxConcurrent} rejects before fetching`, async t => {
    let calls = 0;
    initializeCanvasClient('https://canvas.example/api/v1', 'synthetic');
    t.mock.method(globalThis, 'fetch', async () => { calls++; return Response.json([]); });
    await assert.rejects(bulkGrade({courseIdentifier: 1, assignmentId: 2,
      maxConcurrent, gradingFunction: () => ({grade: 5})}), /maxConcurrent/);
    assert.equal(calls, 0);
  });
}

for (const rateLimitDelay of [-1, NaN, Infinity, 2147483648, 0.5]) {
  test(`invalid rateLimitDelay ${rateLimitDelay} rejects before fetching`, async t => {
    let calls = 0;
    initializeCanvasClient('https://canvas.example/api/v1', 'synthetic');
    t.mock.method(globalThis, 'fetch', async () => { calls++; return Response.json([]); });
    await assert.rejects(bulkGrade({courseIdentifier: 1, assignmentId: 2,
      rateLimitDelay, gradingFunction: () => ({grade: 5})}), /rateLimitDelay/);
    assert.equal(calls, 0);
  });
}

test('explicit zero delay schedules no inter-batch timer', async t => {
  const delays = fastTimers(t);
  submissions(t, [1, 2]);
  const result = await bulkGrade({courseIdentifier: 1, assignmentId: 2,
    maxConcurrent: 1, rateLimitDelay: 0, gradingFunction: () => ({grade: 5})});
  assert.equal(result.graded, 2);
  assert.deepEqual(delays, []);
});

test('batch cap includes asynchronous writes and delay follows settlement', async t => {
  const events: string[] = [];
  const delays = fastTimers(t);
  const realTimer = globalThis.setTimeout;
  let active = 0, peak = 0;
  initializeCanvasClient('https://canvas.example/api/v1', 'synthetic');
  t.mock.method(globalThis, 'fetch', async (url: string, options: RequestInit) => {
    if (options.method === 'GET') return Response.json([1, 2, 3, 4, 5].map(user_id => ({user_id})));
    active++; peak = Math.max(peak, active); events.push(`start:${url.split('/').pop()}`);
    await new Promise<void>(resolve => setImmediate(resolve));
    events.push(`end:${url.split('/').pop()}`); active--;
    return Response.json({score: 5, grade: '5'});
  });
  t.mock.method(globalThis, 'setTimeout', ((fn: (...args: any[]) => void, ms: number) => {
    assert.equal(active, 0, 'delay must start after every write in the batch finishes');
    return realTimer(fn, ms);
  }) as typeof setTimeout);
  const result = await bulkGrade({courseIdentifier: 1, assignmentId: 2,
    maxConcurrent: 2, rateLimitDelay: 17, gradingFunction: () => ({grade: 5})});
  assert.equal(result.graded, 5); assert.equal(peak, 2);
  assert.deepEqual(delays, [17, 17]);
  assert.ok(events.indexOf('start:3') > events.indexOf('end:2'));
});

test('GET retries terminate after four attempts with 1,2,4 second backoff', async t => {
  const delays = fastTimers(t);
  let calls = 0;
  initializeCanvasClient('https://canvas.example/api/v1', 'synthetic');
  t.mock.method(globalThis, 'fetch', async () => { calls++; return new Response('unavailable', {status: 503}); });
  await assert.rejects(canvasGet('/courses'), /503/);
  assert.equal(calls, 4); assert.deepEqual(delays, [1000, 2000, 4000]);
});

for (const send of [() => canvasPost('/courses', {}), () => canvasPut('/courses/1', {}), () => canvasDelete('/courses/1')]) {
  test(`write operation ${send.toString()} is not automatically replayed`, async t => {
    fastTimers(t); let writes = 0;
    initializeCanvasClient('https://canvas.example/api/v1', 'synthetic');
    t.mock.method(globalThis, 'fetch', async () => { writes++; return new Response('unavailable', {status: 503}); });
    await assert.rejects(send(), /may have been applied/);
    assert.equal(writes, 1);
  });
}

test('dry run never writes and accounts for skip, callback failure and grade', async t => {
  const writes = submissions(t, [1, 2, 3]);
  const result = await bulkGrade({courseIdentifier: 1, assignmentId: 2, dryRun: true,
    gradingFunction: async s => { if (s.user_id === 1) return null;
      if (s.user_id === 2) throw new Error('callback failed'); return {grade: 5}; }});
  assert.equal(writes.length, 0);
  assert.deepEqual([result.total, result.graded, result.skipped, result.failed], [3, 1, 1, 1]);
});

test('fractional batch stride cannot exceed its requested cap', async t => {
  fastTimers(t); submissions(t, [1, 2, 3, 4]);
  let active = 0, peak = 0;
  try {
    await bulkGrade({courseIdentifier: 1, assignmentId: 2, maxConcurrent: 1.5,
      gradingFunction: async () => { active++; peak = Math.max(peak, active);
        await new Promise<void>(resolve => setImmediate(resolve)); active--; return {grade: 5}; }});
    assert.ok(peak <= 1.5, `observed ${peak} in-flight jobs with cap 1.5`);
  } catch (error) {
    assert.match(String(error), /maxConcurrent/);
    assert.equal(peak, 0);
  }
});

for (const user of [undefined, 0, -1, 1.5, '7']) {
  test(`invalid submission user ${user} fails before grading`, async t => {
    const writes = submissions(t, [user as number]);
    let callbacks = 0;
    await assert.rejects(bulkGrade({courseIdentifier: 1, assignmentId: 2,
      gradingFunction: () => { callbacks++; return {grade: 5}; }}), /user_id/);
    assert.equal(callbacks, 0); assert.equal(writes.length, 0);
  });
}

test('callback mutation cannot redirect two jobs to the same submission', async t => {
  const writes = submissions(t, [1, 2]);
  await bulkGrade({courseIdentifier: 1, assignmentId: 2,
    gradingFunction: submission => { submission.user_id = 7; return {grade: 5}; }});
  assert.deepEqual(writes.map(url => url.split('/').pop()), ['1', '2']);
});

for (const thrown of [null, undefined]) {
  test(`callback throwing ${thrown} keeps the failed target in the summary`, async t => {
    const writes = submissions(t, [1]);
    const result = await bulkGrade({courseIdentifier: 1, assignmentId: 2,
      gradingFunction: async () => { throw thrown; }});
    assert.equal(writes.length, 0);
    assert.equal(result.failed, 1);
    assert.deepEqual(result.failedResults, [{userId: 1, error: String(thrown)}]);
  });
}
