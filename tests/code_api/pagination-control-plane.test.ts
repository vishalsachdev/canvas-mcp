import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fetchAllPaginated, initializeCanvasClient } from '../../src/canvas_mcp/code_api/client.ts';

const root = 'https://canvas.example/api/v1/courses';
function init() { initializeCanvasClient('https://canvas.example/api/v1', 'synthetic'); }
function page(data: unknown, next?: string) {
  return Response.json(data, {headers: next ? {Link: `<${next}>; rel="next"`} : {}});
}

for (const first of [[{id: 1}], []]) {
  test(`short/empty page ${first.length} follows opaque next query`, async t => {
    init(); const seen: string[] = [];
    const next = `${root}?cursor=a%2Bb,c&include[]=a&include[]=b`;
    t.mock.method(globalThis, 'fetch', async (url: string) => {
      seen.push(url);
      return seen.length === 1 ? page(first, next) : page([{id: 2}]);
    });
    assert.deepEqual(await fetchAllPaginated('/courses'), [...first, {id: 2}]);
    assert.equal(seen[1], next);
  });
}

test('full final page without next does not guess another page', async t => {
  init(); let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => { calls++; return page(calls === 1 ? [1] : []); });
  assert.deepEqual(await fetchAllPaginated('/courses', {per_page: 1}), [1]);
  assert.equal(calls, 1);
});

test('self cycle fails before fetching or appending the repeated page', async t => {
  init(); let calls = 0;
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    calls++;
    if (calls > 3) return new Response('finite test sentinel', {status: 400});
    return page([1], url);
  });
  await assert.rejects(fetchAllPaginated('/courses', {per_page: 1}), /cycle/i);
  assert.equal(calls, 1);
});

test('unending unique next chain stops at explicit budget without partial success', async t => {
  init(); let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    calls++;
    if (calls > 10000) return new Response('finite test sentinel', {status: 400});
    return page([calls], `${root}?cursor=${calls + 1}`);
  });
  await assert.rejects(fetchAllPaginated('/courses', {per_page: 1}), /10000.*pages/i);
  assert.equal(calls, 10000);
});

for (const next of ['https://other.example/api/v1/courses?p=2',
  'https://canvas.example/api/v1/users?p=2', 'https://user:pass@canvas.example/api/v1/courses?p=2',
  `${root}?p=2#fragment`, `${root}?p=2#`, 'http://canvas.example/api/v1/courses?p=2']) {
  test(`unsafe next link rejected before another dispatch: ${next}`, async t => {
    init(); let calls = 0;
    t.mock.method(globalThis, 'fetch', async () => { calls++; return page([1], next); });
    await assert.rejects(fetchAllPaginated('/courses'), /pagination link/i);
    assert.equal(calls, 1);
  });
}

for (const link of ['<broken; rel="next"', `<${root}?p=2>; rel="next", <${root}?p=3>; rel="next"`,
  `<${root}?p=2>; rel="next"; anchor="/other"`,
  `<${root}?p=2>`, `<${root}?p=2>; rel`, `<${root}?p=2>; rel=""`,
  `<${root}?p=2>; rel="next,prev"`]) {
  test(`malformed/ambiguous/context-changing next Link fails: ${link}`, async t => {
    init(); let calls = 0;
    t.mock.method(globalThis, 'fetch', async () => { calls++; return Response.json([1], {headers: {Link: link}}); });
    await assert.rejects(fetchAllPaginated('/courses'), /pagination link/i);
    assert.equal(calls, 1);
  });
}

test('quoted attributes and relation lists preserve relative opaque next', async t => {
  init(); const seen: string[] = [];
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    seen.push(url);
    return seen.length === 1 ? Response.json([1], {headers: {lInK:
      `<${root}?p=1>; rel="prev"; title="x, <fake>; \\"quote\\"", <?cursor=a%2Bb,c>; title="a;b,c"; ReL="next alternate"`}}) : page([2]);
  });
  assert.deepEqual(await fetchAllPaginated('/courses'), [1, 2]);
  assert.equal(seen[1], `${root}?cursor=a%2Bb,c`);
});

for (const data of [null, {unexpected: []}]) {
  test(`non-array response ${JSON.stringify(data)} is an error, not partial success`, async t => {
    init(); t.mock.method(globalThis, 'fetch', async () => page(data));
    await assert.rejects(fetchAllPaginated('/courses'), /expected an array/i);
  });
}

test('later HTTP error rejects instead of returning collected partial data', async t => {
  init(); let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => ++calls === 1 ? page([1], `${root}?p=2`) : new Response('forbidden', {status: 403}));
  await assert.rejects(fetchAllPaginated('/courses'), /403/);
  assert.equal(calls, 2);
});

test('concurrent callers have private cursors and preserve shared input', async t => {
  init(); const params = {per_page: 1, 'include[]': ['user']};
  const before = structuredClone(params);
  const seen: string[] = [];
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    seen.push(url); const u = new URL(url);
    await new Promise<void>(resolve => setImmediate(resolve));
    if (u.searchParams.has('cursor')) return page([`${u.pathname}:second`]);
    if (u.searchParams.get('page') !== '1') return page([]);
    return page([`${u.pathname}:first`], `${u.origin}${u.pathname}?cursor=opaque`);
  });
  const [a, b] = await Promise.all([fetchAllPaginated('/courses/1/submissions', params), fetchAllPaginated('/courses/2/submissions', params)]);
  assert.deepEqual(a, ['/api/v1/courses/1/submissions:first', '/api/v1/courses/1/submissions:second']);
  assert.deepEqual(b, ['/api/v1/courses/2/submissions:first', '/api/v1/courses/2/submissions:second']);
  assert.equal(seen.length, 4); assert.deepEqual(params, before);
});

test('pagination keeps its credential/config snapshot across awaits', async t => {
  init(); const seen: Array<[string, string]> = [];
  t.mock.method(globalThis, 'fetch', async (url: string, options: RequestInit) => {
    seen.push([url, new Headers(options.headers).get('Authorization')!]);
    if (seen.length === 1) {
      initializeCanvasClient('https://other.example/api/v1', 'other-token');
      return page([1], `${root}?cursor=next`);
    }
    return page(seen.length === 2 ? [2] : []);
  });
  assert.deepEqual(await fetchAllPaginated('/courses', {per_page: 1}), [1, 2]);
  assert.deepEqual(seen[1], [`${root}?cursor=next`, 'Bearer synthetic']);
});

test('bulk grading receives every linked page and writes each target once', async t => {
  const {bulkGrade} = await import('../../src/canvas_mcp/code_api/canvas/grading/bulkGrade.ts');
  init(); const writes: string[] = [];
  t.mock.method(globalThis, 'fetch', async (url: string, options: RequestInit) => {
    if (options.method === 'PUT') { writes.push(url); return Response.json({score: 5, grade: '5'}); }
    return url.includes('cursor=next') ? page([{user_id: 2}]) :
      page([{user_id: 1}], 'https://canvas.example/api/v1/courses/1/assignments/2/submissions?cursor=next');
  });
  const result = await bulkGrade({courseIdentifier: 1, assignmentId: 2, gradingFunction: () => ({grade: 5})});
  assert.equal(result.graded, 2);
  assert.deepEqual(writes.map(url => url.split('/').pop()), ['1', '2']);
});

test('paginated read retries do not append the same page twice', async t => {
  init(); let calls = 0;
  const original = globalThis.setTimeout;
  t.mock.method(globalThis, 'setTimeout', ((fn: (...args: any[]) => void) => original(fn, 0)) as typeof setTimeout);
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    calls++;
    if (calls === 1) return new Response('busy', {status: 503});
    return url.includes('cursor=next') ? page([2]) : page([1], `${root}?cursor=next`);
  });
  assert.deepEqual(await fetchAllPaginated('/courses'), [1, 2]);
  assert.equal(calls, 3);
});
