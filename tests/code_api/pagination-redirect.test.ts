import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {fetchAllPaginated, initializeCanvasClient} from '../../src/canvas_mcp/code_api/client.ts';

test('HTTP redirect cannot bypass pagination endpoint validation', async () => {
  let redirected = 0;
  const server = createServer((req, res) => {
    if (req.url?.startsWith('/other')) {
      redirected++; res.end('[1]');
    } else { res.writeHead(302, {Location: '/other'}); res.end(); }
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const address = server.address(); assert.ok(address && typeof address !== 'string');
  initializeCanvasClient(`http://127.0.0.1:${address.port}`, 'synthetic');
  try {
    await assert.rejects(fetchAllPaginated('/courses'));
    assert.equal(redirected, 0);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});
