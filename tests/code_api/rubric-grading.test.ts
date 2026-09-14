import { test } from 'node:test';
import assert from 'node:assert/strict';
import { gradeWithRubric } from '../../src/canvas_mcp/code_api/canvas/grading/gradeWithRubric.ts';

process.env.CANVAS_API_URL = 'https://canvas.example/api/v1';
process.env.CANVAS_API_TOKEN = 'test-only';
const input = {courseIdentifier: 1, assignmentId: 2, userId: 3,
  rubricAssessment: {a: {points: 5}, b: {points: 9}}, grade: 99};
for (const flag of [false, undefined, true]) {
  test(`rubric precheck flag ${flag}`, async () => {
    const writes: string[] = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (_url, options) => {
      if (options?.method === 'PUT') writes.push(String(options.body));
      return new Response(JSON.stringify(options?.method === 'GET'
        ? {use_rubric_for_grading: flag, rubric: [{id: 'a'}, {id: 'b', ignore_for_scoring: true}]}
        : {score: 5, grade: '5'}));
    };
    try {
      if (flag === true) {
        await gradeWithRubric(input);
        assert.equal(writes.length, 1);
        assert.ok(!writes[0].includes('posted_grade'));
      } else {
        await assert.rejects(gradeWithRubric(input));
        assert.equal(writes.length, 0);
      }
    } finally { globalThis.fetch = original; }
  });
}
for (const score of [null, 99]) {
  test(`unconfirmed score ${score} is not success`, async () => {
    const original = globalThis.fetch;
    globalThis.fetch = async (_url, options) => new Response(JSON.stringify(options?.method === 'GET'
      ? {use_rubric_for_grading: true, rubric: [{id: 'a'}, {id: 'b', ignore_for_scoring: true}]}
      : {score, grade: '99'}));
    try { await assert.rejects(gradeWithRubric(input), /unconfirmed/i); }
    finally { globalThis.fetch = original; }
  });
}

test('lookup failure never writes', async () => {
  let writes = 0;
  const original = globalThis.fetch;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === 'PUT') writes++;
    return new Response('lookup failed', {status: 403});
  };
  try {
    await assert.rejects(gradeWithRubric(input), /403/);
    assert.equal(writes, 0);
  } finally { globalThis.fetch = original; }
});

test('simple zero grade stays explicit without a rubric lookup', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (_url, options) => {
    assert.equal(options?.method, 'PUT');
    assert.equal(new URLSearchParams(String(options?.body)).get('submission[posted_grade]'), '0');
    return new Response(JSON.stringify({score: 0, grade: '0'}));
  };
  try {
    const response = await gradeWithRubric({courseIdentifier: 1, assignmentId: 2, userId: 3, grade: 0});
    assert.equal(response.score, 0);
  } finally { globalThis.fetch = original; }
});

for (const rubric of [undefined, [{id: 'a'}]]) {
  test(`missing or incomplete rubric metadata is unconfirmed: ${JSON.stringify(rubric)}`, async () => {
    const original = globalThis.fetch;
    globalThis.fetch = async (_url, options) => new Response(JSON.stringify(options?.method === 'GET'
      ? {use_rubric_for_grading: true, rubric} : {score: 14, grade: '14'}));
    try { await assert.rejects(gradeWithRubric(input), /unconfirmed/i); }
    finally { globalThis.fetch = original; }
  });
}
