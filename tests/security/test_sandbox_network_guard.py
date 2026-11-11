"""Behavior tests for the TypeScript sandbox's JavaScript network guard.

The guard (``_write_network_guard``) is preloaded with ``node -r`` and is the
egress control whenever the sandbox runs without ``--network=none``. These
tests run real Node against the generated guard file.

Rule under test: an outbound connection is allowed only when it names a host
on the allowlist. A connection that names no host (Node then defaults to
localhost), names a local socket path, or brings its own DNS lookup is refused.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from canvas_mcp.tools.code_execution import _write_network_guard

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

# Each case runs synchronously. BLOCKED means the guard threw
# SANDBOX_NETWORK_BLOCKED before any socket opened.
_SYNC_PROBE = r"""
const net = require('net'); const tls = require('tls');
const http = require('http'); const https = require('https');
const cases = {
  'net.connect(port)': () => net.connect(80),
  'net.connect(port, empty host)': () => net.connect(80, ''),
  'net.connect({port})': () => net.connect({port: 80}),
  'net.connect({path})': () => net.connect({path: '/tmp/x.sock'}),
  'net.connect(path string)': () => net.connect('/tmp/x.sock'),
  'net.createConnection({port})': () => net.createConnection({port: 80}),
  'net.createConnection(other host)': () => net.createConnection({host: 'evil.example', port: 80}),
  'new net.Socket().connect(other host)': () => new net.Socket().connect(80, 'evil.example'),
  'net.connect(allowed host, custom lookup)': () => net.connect({host: 'allowed.example', port: 80, lookup: (h, o, cb) => cb(null, '10.0.0.1', 4)}),
  'tls.connect({port})': () => tls.connect({port: 443}),
  'tls.connect(other host)': () => tls.connect({host: 'evil.example', port: 443}),
  'http.request({socketPath})': () => http.request({socketPath: '/tmp/x.sock', path: '/'}),
  'http.request(allowed host, socketPath)': () => http.request({host: 'allowed.example', socketPath: '/tmp/x.sock', path: '/'}),
  'https.request({socketPath})': () => https.request({socketPath: '/tmp/x.sock', path: '/'}),
  'http.request({}) defaults to localhost': () => http.request({path: '/'}),
  'http.get(other host)': () => http.get({host: 'evil.example', path: '/'}),
  'https.get(other url)': () => https.get('https://evil.example/'),
  'http.request(ipv6 literal)': () => http.request('http://[::1]:80/'),
  'net.connect(port string)': () => net.connect('80'),
  'http.request(hostname wins over allowed host)': () => http.request({hostname: 'evil.example', host: 'allowed.example', path: '/'}),
  'fetch(not a url)': () => fetch('not a url'),
  'fetch(other url)': () => fetch('https://evil.example/'),
  'CONTROL net.connect(allowed host)': () => net.connect({host: 'allowed.example', port: 1}),
  'CONTROL net.connect(port, allowed host)': () => net.connect(1, 'allowed.example'),
  'CONTROL http.request(allowed url)': () => http.request('http://allowed.example:1/'),
  'CONTROL https.get(allowed options)': () => https.get({hostname: 'allowed.example', port: 1, path: '/'}),
  'CONTROL fetch(allowed url)': () => fetch('https://allowed.example:1/'),
  'CONTROL net.connect(allowed host, upper case, trailing dot)': () => net.connect({host: 'ALLOWED.example.', port: 1}),
};
const out = {};
for (const [name, fn] of Object.entries(cases)) {
  try {
    const r = fn();
    if (r && typeof r.on === 'function') r.on('error', () => {});
    if (r && typeof r.catch === 'function') r.catch(() => {});
    if (r && typeof r.destroy === 'function') r.destroy();
    out[name] = 'ALLOWED';
  } catch (e) { out[name] = e.code === 'SANDBOX_NETWORK_BLOCKED' ? 'BLOCKED' : 'OTHER:' + e.code; }
}
console.log(JSON.stringify(out));
"""

# End to end against a local server: the guard must still let real traffic
# reach an allowlisted host, through every client API, and must stop it
# otherwise. Prints {api: status code or error code}.
_LIVE_PROBE = r"""
const http = require('http');
const net = require('net');
const server = http.createServer((req, res) => { res.end('ok'); });
server.listen(0, '127.0.0.1', async () => {
  const port = server.address().port;
  const out = {};
  const viaGet = () => new Promise((resolve) => {
    try {
      const req = http.get({host: '127.0.0.1', port, path: '/'}, (res) => { res.resume(); resolve(res.statusCode); });
      req.on('error', (e) => resolve(e.code));
    } catch (e) { resolve(e.code); }
  });
  const viaFetch = async () => {
    try { const r = await fetch(`http://127.0.0.1:${port}/`); await r.text(); return r.status; }
    catch (e) { return (e.cause && e.cause.code) || e.code || String(e); }
  };
  const viaNet = () => new Promise((resolve) => {
    try {
      const s = net.connect({host: '127.0.0.1', port}, () => { s.destroy(); resolve('connected'); });
      s.on('error', (e) => resolve(e.code));
    } catch (e) { resolve(e.code); }
  });
  out['http.get'] = await viaGet();
  out['fetch'] = await viaFetch();
  out['net.connect'] = await viaNet();
  console.log(JSON.stringify(out));
  server.close();
});
"""


def _run(probe: str, allowlist: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as d:
        guard = _write_network_guard(allowlist, Path(d))
        script = Path(d) / "probe.cjs"
        script.write_text(probe, encoding="utf-8")
        res = subprocess.run(
            [NODE, "-r", str(guard), str(script)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert res.returncode == 0, res.stderr
        return json.loads(res.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def sync_results() -> dict:
    return _run(_SYNC_PROBE, ["allowed.example"])


_BLOCKED_CASES = [
    "net.connect(port)",
    "net.connect(port, empty host)",
    "net.connect({port})",
    "net.connect({path})",
    "net.connect(path string)",
    "net.createConnection({port})",
    "net.createConnection(other host)",
    "new net.Socket().connect(other host)",
    "net.connect(allowed host, custom lookup)",
    "tls.connect({port})",
    "tls.connect(other host)",
    "http.request({socketPath})",
    "http.request(allowed host, socketPath)",
    "https.request({socketPath})",
    "http.request({}) defaults to localhost",
    "http.get(other host)",
    "https.get(other url)",
    "http.request(ipv6 literal)",
    "net.connect(port string)",
    "http.request(hostname wins over allowed host)",
    "fetch(not a url)",
    "fetch(other url)",
]

_ALLOWED_CASES = [
    "CONTROL net.connect(allowed host)",
    "CONTROL net.connect(port, allowed host)",
    "CONTROL http.request(allowed url)",
    "CONTROL https.get(allowed options)",
    "CONTROL fetch(allowed url)",
    "CONTROL net.connect(allowed host, upper case, trailing dot)",
]


@pytest.mark.parametrize("case", _BLOCKED_CASES)
def test_connection_without_allowlisted_host_is_blocked(sync_results, case):
    assert sync_results[case] == "BLOCKED"


@pytest.mark.parametrize("case", _ALLOWED_CASES)
def test_allowlisted_host_is_not_blocked(sync_results, case):
    assert sync_results[case] == "ALLOWED"


def test_allowlisted_local_server_is_reachable_through_every_client():
    out = _run(_LIVE_PROBE, ["127.0.0.1"])
    assert out == {"http.get": 200, "fetch": 200, "net.connect": "connected"}


def test_unlisted_local_server_is_unreachable_through_every_client():
    out = _run(_LIVE_PROBE, ["allowed.example"])
    assert out == {
        "http.get": "SANDBOX_NETWORK_BLOCKED",
        "fetch": "SANDBOX_NETWORK_BLOCKED",
        "net.connect": "SANDBOX_NETWORK_BLOCKED",
    }
