"""Behavior tests for the TypeScript sandbox's JavaScript network guard.

The guard (``_write_network_guard``) is preloaded with ``node -r`` and is the
egress control whenever the sandbox runs without ``--network=none``. These
tests run real Node against the generated guard file.

Rule under test: an outbound connection is allowed only when it names a host
on the allowlist. A connection that names no host (Node then defaults to
localhost) or names a local socket path is refused. A connection that brings
its own DNS lookup has that lookup replaced by Node's.
"""

import json
import os
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


def _run(
    probe: str,
    allowlist: list[str],
    node_args: tuple[str, ...] = (),
    preload: str = "cli",
    node_options: str = "",
) -> dict:
    """Run a probe with the guard preloaded.

    preload="cli" passes `-r` on the command line. preload="env" names the
    guard in NODE_OPTIONS only, which is how container mode loads it.
    """
    with tempfile.TemporaryDirectory() as d:
        guard = _write_network_guard(allowlist, Path(d))
        script = Path(d) / "probe.cjs"
        script.write_text(probe, encoding="utf-8")
        if preload == "env":
            cmd = [NODE, *node_args, str(script)]
            options = f"{node_options} --require {json.dumps(str(guard))}".strip()
            env = {**os.environ, "NODE_OPTIONS": options}
        else:
            cmd = [NODE, *node_args, "-r", str(guard), str(script)]
            env = {k: v for k, v in os.environ.items() if k != "NODE_OPTIONS"}
            if node_options:
                env["NODE_OPTIONS"] = node_options
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
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


def test_allowlist_entries_are_normalized_like_requested_hosts():
    probe = r"""
const net = require('net');
const out = {};
try { const s = net.connect({host: 'allowed.example', port: 1}); s.on('error', () => {}); s.destroy(); out.r = 'ALLOWED'; }
catch (e) { out.r = e.code; }
console.log(JSON.stringify(out));
"""
    assert _run(probe, ["Allowed.Example."]) == {"r": "ALLOWED"}


# The sandbox runs code with `npx tsx` and the guard in NODE_OPTIONS, so the
# guard loads into tsx's parent and child. The child opens a pipe back to the
# parent; that relay must keep working, and no other local socket may open.
_REPO_ROOT = Path(__file__).resolve().parents[2]
# The CLI entry itself, run with node: node_modules/.bin/tsx is a shell
# launcher that Windows cannot execute directly.
_TSX_CLI = _REPO_ROOT / "node_modules" / "tsx" / "dist" / "cli.mjs"

_TSX_SCRIPT = r"""
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
const x: number = 1;
const owner = process.geteuid ? process.geteuid() : os.userInfo().username;
const other = path.join(os.tmpdir(), `tsx-${owner}`, `${process.ppid + 1}.pipe`);
let otherPipe = 'ALLOWED';
try { const s = net.connect(other); s.on('error', () => {}); s.destroy(); }
catch (e: any) { otherPipe = e.code; }
setTimeout(() => console.log(JSON.stringify({ ran: x, otherPipe })), 50);
"""


@pytest.mark.skipif(not _TSX_CLI.exists(), reason="tsx not installed (npm ci)")
def test_guard_keeps_the_tsx_runner_working_and_blocks_other_pipes():
    with tempfile.TemporaryDirectory() as d:
        guard = _write_network_guard(["allowed.example"], Path(d))
        script = Path(d) / "code.ts"
        script.write_text(_TSX_SCRIPT, encoding="utf-8")
        # json.dumps quotes the path the way NODE_OPTIONS parses it (spaces,
        # Windows backslashes).
        env = {**os.environ, "NODE_OPTIONS": f"--require {json.dumps(str(guard))}"}
        res = subprocess.run(
            [NODE, str(_TSX_CLI), str(script)], capture_output=True, text=True, timeout=60, env=env
        )
        assert res.returncode == 0, res.stderr
        assert json.loads(res.stdout.strip().splitlines()[-1]) == {
            "ran": 1,
            "otherPipe": "SANDBOX_NETWORK_BLOCKED",
        }


# Guest code runs in the same JavaScript realm as the guard. These cases try to
# make the check see one target while Node dials another, or to change how the
# check itself runs. Each one aims at a local server that is NOT on the
# allowlist; CONNECTED would mean it got through.
_TAMPER_PROBE = r"""
const net = require('net'); const dns = require('dns'); const dgram = require('dgram');
const http = require('http'); const { Worker } = require('worker_threads');
const server = http.createServer((q, r) => r.end('ok'));
server.listen(0, '127.0.0.1', async () => {
  const port = server.address().port;
  const out = {};
  const attempt = (fn) => new Promise((resolve) => {
    try {
      const s = fn();
      s.on('connect', () => { s.destroy(); resolve('CONNECTED'); });
      s.on('error', (e) => resolve(e.code));
    } catch (e) { resolve(e.code); }
  });
  const flipping = (reads) => {
    let n = 0;
    return { port, get host() { return n++ < reads ? 'allowed.example' : '127.0.0.1'; } };
  };
  out['plain array argument'] = await attempt(() => {
    const a = [{ host: 'allowed.example', port }]; a.host = '127.0.0.1'; a.port = port;
    return new net.Socket().connect(a);
  });
  for (const reads of [1, 2, 3]) {
    out[`getter flips after ${reads} read(s)`] = await attempt(() => net.connect(flipping(reads)));
  }
  out['proxy options'] = await attempt(() => {
    let n = 0;
    return net.connect(new Proxy({ port }, { get: (t, k) => (k === 'host' ? (n++ ? '127.0.0.1' : 'allowed.example') : t[k]) }));
  });
  const realToLower = String.prototype.toLowerCase;
  String.prototype.toLowerCase = function () { return 'allowed.example'; };
  out['String.prototype patched'] = await attempt(() => net.connect({ host: '127.0.0.1', port }));
  String.prototype.toLowerCase = realToLower;
  const realHas = Set.prototype.has;
  Set.prototype.has = function () { return true; };
  out['Set.prototype.has patched'] = await attempt(() => net.connect({ host: '127.0.0.1', port }));
  Set.prototype.has = realHas;
  Object.defineProperty(Object.prototype, 'host', { configurable: true, get() { return '127.0.0.1'; }, set() {} });
  out['Object.prototype host'] = await attempt(() => net.connect({ port }));
  delete Object.prototype.host;
  // A caller's own lookup must never run: it would send the allowlisted name
  // to the unlisted local server.
  for (const [label, connect] of [
    ['custom lookup (net)', (lookup) => net.connect({ host: 'allowed.example', port, lookup })],
    ['custom lookup (http)', (lookup) => http.get({ host: 'allowed.example', port, lookup, agent: false })],
  ]) {
    let called = false;
    const lookup = (h, o, cb) => {
      called = true;
      if (typeof o === 'function') cb = o;
      if (o && o.all) cb(null, [{ address: '127.0.0.1', family: 4 }]); else cb(null, '127.0.0.1', 4);
    };
    const code = await new Promise((resolve) => {
      try {
        const r = connect(lookup);
        r.on('connect', () => resolve('CONNECTED'));
        r.on('response', () => resolve('CONNECTED'));
        r.on('error', (e) => resolve(e.code));
      } catch (e) { resolve(e.code); }
    });
    out[label] = called ? 'LOOKUP_CALLED' : code;
  }
  const realLookup = dns.lookup;
  dns.lookup = (h, o, cb) => {
    if (typeof o === 'function') cb = o;
    if (o && o.all) cb(null, [{ address: '127.0.0.1', family: 4 }]); else cb(null, '127.0.0.1', 4);
  };
  out['dns.lookup replaced'] = await attempt(() => net.connect({ host: 'allowed.example', port }));
  dns.lookup = realLookup;
  out['UDP send'] = await new Promise((resolve) => {
    const u = dgram.createSocket('udp4');
    try { u.send('x', port, '127.0.0.1', () => { u.close(); resolve('SENT'); }); }
    catch (e) { u.close(); resolve(e.code); }
  });
  const workerCode = `
      const { parentPort, workerData } = require('worker_threads');
      const s = (() => { try { return require('net').connect({ host: '127.0.0.1', port: workerData }); }
                          catch (e) { parentPort.postMessage(e.code); return null; } })();
      if (s) { s.on('connect', () => { s.destroy(); parentPort.postMessage('CONNECTED'); });
               s.on('error', (e) => parentPort.postMessage(e.code)); }`;
  const viaWorker = (options) => new Promise((resolve) => {
    let w;
    try { w = new Worker(workerCode, { eval: true, workerData: port, ...options }); }
    catch (e) { resolve(e.code); return; }
    w.once('message', (m) => { w.terminate(); resolve(m); });
    w.once('error', (e) => resolve('WORKER_ERROR:' + e.code));
  });
  out['worker thread'] = await viaWorker({});
  out['worker thread without the preload'] = await viaWorker({ execArgv: [], env: {} });
  out['worker thread with an empty env'] = await viaWorker({ env: {} });
  // Every route back to the unwrapped constructor, each run with execArgv: [].
  out['worker from the original constructor'] = await (async () => {
    const probe = new Worker('0', { eval: true });
    await probe.terminate();
    const routes = [probe.constructor, Object.getPrototypeOf(probe).constructor, Object.getPrototypeOf(Worker)];
    for (const C of routes) {
      const r = await new Promise((resolve) => {
        let w;
        try { w = new C(workerCode, { eval: true, workerData: port, execArgv: [] }); }
        catch (e) { resolve(e.code || 'NOT_A_CONSTRUCTOR'); return; }
        w.once('message', (m) => { w.terminate(); resolve(m); });
        w.once('error', (e) => resolve('WORKER_ERROR:' + e.code));
      });
      if (r === 'CONNECTED') return r;
    }
    return 'SANDBOX_NETWORK_BLOCKED';
  })();
  console.log(JSON.stringify(out));
  server.close();
});
"""

_TAMPER_CASES = [
    "plain array argument",
    "getter flips after 1 read(s)",
    "getter flips after 2 read(s)",
    "getter flips after 3 read(s)",
    "proxy options",
    "String.prototype patched",
    "Set.prototype.has patched",
    "Object.prototype host",
    "dns.lookup replaced",
    "custom lookup (net)",
    "custom lookup (http)",
    "UDP send",
    "worker thread",
    "worker thread without the preload",
    "worker thread with an empty env",
    "worker from the original constructor",
]

# Cases that must be refused by the guard itself, not merely sent to the
# allowlisted name (which happens not to resolve).
_TAMPER_REFUSED = {
    "plain array argument",
    "String.prototype patched",
    "Set.prototype.has patched",
    "Object.prototype host",
    "UDP send",
    "worker thread",
    "worker thread without the preload",
    "worker thread with an empty env",
    "worker from the original constructor",
}


@pytest.fixture(scope="module")
def tamper_results() -> dict:
    return _run(_TAMPER_PROBE, ["allowed.example"])


@pytest.mark.parametrize("case", _TAMPER_CASES)
def test_guest_tampering_cannot_reach_an_unlisted_host(tamper_results, case):
    if case in _TAMPER_REFUSED:
        assert tamper_results[case] == "SANDBOX_NETWORK_BLOCKED"
    else:
        # A replaced dns.lookup, or a getter or proxy that settles on the
        # allowlisted name: Node is sent to that name, which does not resolve.
        assert tamper_results[case] in {"SANDBOX_NETWORK_BLOCKED", "ENOTFOUND"}


# npm's agent passes its own lookup when npx fetches the tsx runner in
# container mode. That must still reach an allowlisted host, through Node's
# lookup and not the caller's.
_CUSTOM_LOOKUP_ALLOWED_PROBE = r"""
const net = require('net'); const http = require('http');
const server = http.createServer((q, r) => r.end('ok'));
server.listen(0, '127.0.0.1', async () => {
  const port = server.address().port;
  const out = {};
  for (const [label, connect] of [
    ['net', (lookup) => net.connect({ host: 'localhost', port, family: 4, lookup })],
    ['http', (lookup) => http.get({ host: 'localhost', port, family: 4, lookup, agent: false })],
  ]) {
    let called = false;
    const lookup = (h, o, cb) => { called = true; cb(new Error('caller lookup ran')); };
    const code = await new Promise((resolve) => {
      try {
        const r = connect(lookup);
        r.on('connect', () => resolve('CONNECTED'));
        r.on('response', (res) => { res.resume(); resolve('CONNECTED'); });
        r.on('error', (e) => resolve(e.code || e.message));
      } catch (e) { resolve(e.code); }
    });
    out[label] = called ? 'LOOKUP_CALLED' : code;
  }
  server.close();
  console.log(JSON.stringify(out));
  process.exit(0);
});
"""


def test_custom_lookup_is_replaced_and_an_allowlisted_host_still_connects():
    assert _run(_CUSTOM_LOOKUP_ALLOWED_PROBE, ["localhost"]) == {
        "net": "CONNECTED",
        "http": "CONNECTED",
    }


# A worker takes preloads from the environment it is given and from its
# execArgv. Each case tries to start one without the guard, or with guest code
# loaded ahead of it (which could keep the unwrapped connect). Run with the
# guard loaded both ways: on the command line, and through NODE_OPTIONS as in
# container mode, where `env: {}` alone used to drop it.
_WORKER_ENV_PROBE = r"""
const { Worker, SHARE_ENV } = require('worker_threads'); const http = require('http'); const fs = require('fs'); const path = require('path');
const server = http.createServer((q, r) => r.end('ok'));
server.listen(0, '127.0.0.1', async () => {
  const port = server.address().port; const out = {};
  const code = `const { parentPort, workerData } = require('worker_threads');
    try { const c = globalThis.__origConnect; const net = require('net');
      const s = c ? c.call(new net.Socket(), { host: '127.0.0.1', port: workerData }) : net.connect({ host: '127.0.0.1', port: workerData });
      s.on('connect', () => { s.destroy(); parentPort.postMessage('CONNECTED'); }); s.on('error', (e) => parentPort.postMessage(e.code)); }
    catch (e) { parentPort.postMessage(e.code); }`;
  const evil = path.join(__dirname, 'evil.cjs');
  fs.writeFileSync(evil, "globalThis.__origConnect = require('net').Socket.prototype.connect; process[Symbol.for('canvas-mcp.sandbox-network-guard')] = true;");
  const run = (opts) => new Promise((res) => { try { const w = new Worker(code, { eval: true, workerData: port, ...opts }); w.on('message', res); w.on('error', (e) => res('ERR ' + (e.code || e.message))); } catch (e) { res('THROW ' + e.code); } });
  out['default'] = await run({});
  out['env {}'] = await run({ env: {} });
  out['env NODE_OPTIONS empty'] = await run({ env: { NODE_OPTIONS: '' } });
  out['execArgv [] env {}'] = await run({ execArgv: [], env: {} });
  out['env evil preload'] = await run({ env: { NODE_OPTIONS: `--require ${JSON.stringify(evil)}` } });
  out['execArgv evil preload'] = await run({ execArgv: [`--require=${evil}`], env: {} });
  Object.defineProperty(Object.prototype, 'NODE_OPTIONS', { configurable: true, set() {}, get() { return ''; } });
  out['Object.prototype NODE_OPTIONS'] = await run({ env: {} });
  delete Object.prototype.NODE_OPTIONS;
  process.env.NODE_OPTIONS = `--require ${JSON.stringify(evil)}`;
  out['process.env evil, default'] = await run({});
  out['process.env evil, SHARE_ENV'] = await run({ env: SHARE_ENV });
  delete process.env.NODE_OPTIONS;
  out['process.env deleted, default'] = await run({});
  out['process.env deleted, SHARE_ENV'] = await run({ env: SHARE_ENV });
  out['env string (invalid)'] = await run({ env: 'x' });
  console.log(JSON.stringify(out)); process.exit(0);
});
"""

_WORKER_ENV_CASES = [
    "default",
    "env {}",
    "env NODE_OPTIONS empty",
    "execArgv [] env {}",
    "env evil preload",
    "execArgv evil preload",
    "Object.prototype NODE_OPTIONS",
    "process.env evil, default",
    "process.env evil, SHARE_ENV",
    "process.env deleted, default",
    "process.env deleted, SHARE_ENV",
]


@pytest.mark.parametrize("preload", ["cli", "env"])
def test_worker_cannot_start_without_the_guard_first(preload):
    results = _run(_WORKER_ENV_PROBE, ["allowed.example"], preload=preload)
    assert {case: results[case] for case in _WORKER_ENV_CASES} == dict.fromkeys(
        _WORKER_ENV_CASES, "SANDBOX_NETWORK_BLOCKED"
    )
    # An env of the wrong type is still Node's own error.
    assert results["env string (invalid)"] == "THROW ERR_INVALID_ARG_TYPE"


# The worker wrapper must behave like Node's own Worker for ordinary code.
_WORKER_COMPAT_PROBE = r"""
const { Worker } = require('worker_threads');
const run = (W, options) => new Promise((resolve) => {
  const w = new W(`require('worker_threads').parentPort.postMessage('up')`, { eval: true, ...options });
  w.once('message', (m) => { w.terminate(); resolve({ w, m }); });
  w.once('error', (e) => resolve({ w, m: 'ERROR:' + e.code }));
});
(async () => {
  class Tagged extends Worker { tag() { return 'tagged'; } }
  const plain = await run(Worker, {});
  const sub = await run(Tagged, {});
  const explicit = await run(Worker, { execArgv: [] });
  let noNew;
  try { Worker('0', { eval: true }); noNew = 'CONSTRUCTED'; } catch (e) { noNew = e.name; }
  console.log(JSON.stringify({
    plain: plain.m,
    instanceof: plain.w instanceof Worker,
    constructor: plain.w.constructor === Worker,
    subclass: sub.m,
    subclassMethod: typeof sub.w.tag === 'function' ? sub.w.tag() : 'missing',
    subclassInstanceof: sub.w instanceof Tagged && sub.w instanceof Worker,
    explicitExecArgv: explicit.m,
    calledWithoutNew: noNew,
  }));
})();
"""


@pytest.mark.parametrize("preload", ["cli", "env"])
def test_worker_wrapper_keeps_worker_behavior(preload):
    assert _run(_WORKER_COMPAT_PROBE, ["allowed.example"], preload=preload) == {
        "plain": "up",
        "instanceof": True,
        "constructor": True,
        "subclass": "up",
        "subclassMethod": "tagged",
        "subclassInstanceof": True,
        "explicitExecArgv": "up",
        "calledWithoutNew": "TypeError",
    }


@pytest.mark.parametrize("preload", ["cli", "env"])
def test_worker_starts_when_node_options_holds_a_per_process_flag(preload):
    # Node rejects a per-process flag in a worker's NODE_OPTIONS unless the
    # string equals the parent's, so an untouched environment must stay as is.
    out = _run(
        _WORKER_COMPAT_PROBE,
        ["allowed.example"],
        preload=preload,
        node_options="--title=sandbox --max-old-space-size=256",
    )
    assert out["plain"] == "up"
    assert out["explicitExecArgv"] == "up"
    assert out["subclass"] == "up"


# The one allowed local socket path must hold a socket itself: a symlink
# there would lead to some other local socket.
_PIPE_SYMLINK_PROBE = r"""
const net = require('net'); const fs = require('fs'); const os = require('os'); const path = require('path');
const dir = path.join(os.tmpdir(), `tsx-${process.geteuid()}`);
const pipe = path.join(dir, `${process.ppid}.pipe`);
const target = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'g-')), 's.sock');
fs.mkdirSync(dir, { recursive: true });
const attempt = () => new Promise((resolve) => {
  try {
    const s = net.connect(pipe);
    s.on('connect', () => { s.destroy(); resolve('CONNECTED'); });
    s.on('error', (e) => resolve(e.code));
  } catch (e) { resolve(e.code); }
});
const listen = (p) => new Promise((resolve) => { const srv = net.createServer((c) => c.end()); srv.listen(p, () => resolve(srv)); });
(async () => {
  const out = {};
  try { fs.unlinkSync(pipe); } catch (_) {}
  const other = await listen(target);
  fs.symlinkSync(target, pipe);
  out.symlink = await attempt();
  Object.defineProperty(process, 'platform', { value: 'win32' });
  out.symlinkPlatformPatched = await attempt();
  Object.defineProperty(process, 'platform', { value: os.platform() });
  fs.unlinkSync(pipe);
  out.missing = await attempt();
  const own = await listen(pipe);
  out.socket = await attempt();
  own.close(); other.close();
  try { fs.unlinkSync(pipe); } catch (_) {}
  console.log(JSON.stringify(out));
  process.exit(0);
})();
"""


@pytest.mark.skipif(os.name == "nt", reason="named pipes are not files on Windows")
def test_tsx_pipe_path_must_be_a_socket_not_a_symlink():
    assert _run(_PIPE_SYMLINK_PROBE, ["allowed.example"]) == {
        "symlink": "SANDBOX_NETWORK_BLOCKED",
        "symlinkPlatformPatched": "SANDBOX_NETWORK_BLOCKED",
        "missing": "SANDBOX_NETWORK_BLOCKED",
        "socket": "CONNECTED",
    }


def test_worker_inherits_v8_flags_from_the_parent():
    # A memory limit in the parent argv is a V8 flag; Node refuses it in an
    # explicit worker execArgv, so a worker without execArgv must inherit it.
    out = _run(_WORKER_COMPAT_PROBE, ["allowed.example"], node_args=("--max-old-space-size=256",))
    assert out["plain"] == "up"
    assert out["subclass"] == "up"


def test_allowlisted_ipv6_literal_and_entry_with_port_match():
    probe = r"""
const net = require('net');
const out = {};
for (const [name, opts] of [['ipv6', {host: '::1', port: 1}], ['ported entry', {host: 'ported.example', port: 1}]]) {
  try { const s = net.connect(opts); s.on('error', () => {}); s.destroy(); out[name] = 'ALLOWED'; }
  catch (e) { out[name] = e.code; }
}
console.log(JSON.stringify(out));
"""
    assert _run(probe, ["[::1]", "ported.example:443"]) == {"ipv6": "ALLOWED", "ported entry": "ALLOWED"}
