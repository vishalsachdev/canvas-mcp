import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { initializeCanvasClient } from '../../src/canvas_mcp/code_api/client.ts';
import { gradeWithRubric } from '../../src/canvas_mcp/code_api/canvas/grading/gradeWithRubric.ts';

for (const failure of ['503', 'disconnect', 'invalid-json', 'redirect']) {
  test(`committed grade followed by ${failure} is not sent twice`, async () => {
    let applied = 0;
    const server = createServer((req, res) => {
      req.resume();
      req.on('end', () => {
        applied++;
        if (applied === 1) {
          if (failure === 'disconnect') { req.socket.destroy(); return; }
          if (failure === 'redirect') {
            res.writeHead(307, {Location: '/redirected'}); res.end(); return;
          }
          res.writeHead(failure === '503' ? 503 : 200);
          res.end(failure === '503' ? 'response lost after commit' : '{');
        } else {
          res.writeHead(200, {'Content-Type': 'application/json'});
          res.end(JSON.stringify({score: 5, grade: '5'}));
        }
      });
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const address = server.address();
    assert.ok(address && typeof address !== 'string');
    initializeCanvasClient(`http://127.0.0.1:${address.port}`, 'synthetic');
    try {
      const outcome = await gradeWithRubric({courseIdentifier: 1, assignmentId: 2,
        userId: 3, grade: 5, comment: 'One comment only'}).then(
          () => 'success', (error: Error) => error.message);
      assert.equal(applied, 1, 'one committed grade/comment must not be replayed');
      assert.match(outcome, /may have been applied.*before retrying/s);
    } finally {
      server.closeAllConnections();
      await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    }
  });
}
